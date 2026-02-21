# src/app_manager.py
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from src.ui.login_window import LoginWindow
    from src.ui.select_window import SelectWindow
    from src.ui.main_window import MainWindow


class AppManager:
    """
    화면(윈도우) 전환 담당.
    - login/select/main 윈도우를 lazy 생성 후 재사용
    - UI 모듈은 순환 import를 피하기 위해 메서드 내부에서 import
    """

    login_window: Optional["LoginWindow"]
    select_window: Optional["SelectWindow"]
    main_window: Optional["MainWindow"]

    def __init__(self, app: QApplication) -> None:
        self.app = app

        self.login_window = None
        self.select_window = None
        self.main_window = None

        self._current: Optional[QWidget] = None  # 현재 보여지는 창

    # =========================================================
    # Start
    # =========================================================
    def start(self) -> None:
        self.go_to_login()

    # =========================================================
    # Internal: switch
    # =========================================================
    def _switch_to(self, win: QWidget) -> None:
        # 기존 창 정리(보통 hide가 안전)
        if self._current is not None and self._current is not win:
            self._current.hide()

        self._current = win
        win.show()
        win.raise_()
        win.activateWindow()

    # =========================================================
    # Navigation
    # =========================================================
    def go_to_login(self) -> None:
        if self.login_window is None:
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

        if self.select_window is None:
            self.select_window = SelectWindow(self, site_list)
        else:
            self.select_window.set_sites(site_list)  # public

        self._switch_to(self.select_window)

    def go_to_main(self) -> None:
        if self.main_window is None:
            from src.ui.main_window import MainWindow
            self.main_window = MainWindow(self)

        # 메인 진입 시 상태 초기화가 필요하면 여기서만
        self.main_window.init_reset()
        self._switch_to(self.main_window)