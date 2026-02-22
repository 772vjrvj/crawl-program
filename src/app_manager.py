# src/app_manager.py
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid  # ✅ 추가

if TYPE_CHECKING:
    from src.ui.login_window import LoginWindow
    from src.ui.select_window import SelectWindow
    from src.ui.main_window import MainWindow


class AppManager:
    login_window: Optional["LoginWindow"]
    select_window: Optional["SelectWindow"]
    main_window: Optional["MainWindow"]

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.login_window = None
        self.select_window = None
        self.main_window = None
        self._current: Optional[QWidget] = None

    def start(self) -> None:
        self.go_to_login()

    def _switch_to(self, win: QWidget) -> None:
        if self._current is not None and self._current is not win:
            try:
                if isValid(self._current):
                    self._current.hide()
            except Exception:
                pass

        self._current = win
        win.show()
        win.raise_()
        win.activateWindow()

    # === 신규 ===
    def _ensure_main(self) -> "MainWindow":
        if self.main_window is None:
            from src.ui.main_window import MainWindow
            self.main_window = MainWindow(self)
            return self.main_window

        # ✅ 파이썬 객체는 있는데 C++ 객체가 삭제된 경우
        if not isValid(self.main_window):
            self.main_window = None
            from src.ui.main_window import MainWindow
            self.main_window = MainWindow(self)

        return self.main_window

    def go_to_login(self) -> None:
        if self.login_window is None or (self.login_window is not None and not isValid(self.login_window)):
            from src.ui.login_window import LoginWindow
            self.login_window = LoginWindow(self)

        self._switch_to(self.login_window)

    def go_to_select(self) -> None:
        from src.core.global_state import GlobalState
        from src.models.site import Site
        from src.ui.select_window import SelectWindow

        st = GlobalState()
        raw_list = st.get(GlobalState.SITE_CONFIGS, [])
        site_list = [Site.from_dict(d) for d in (raw_list or [])]

        if self.select_window is None or (self.select_window is not None and not isValid(self.select_window)):
            self.select_window = SelectWindow(self, site_list)
        else:
            self.select_window.set_sites(site_list)

        self._switch_to(self.select_window)

    def go_to_main(self) -> None:
        w = self._ensure_main()      # ✅ 여기만 바뀜
        w.init_reset()
        self._switch_to(w)