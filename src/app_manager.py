# src/app_manager.py
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

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

    def __init__(self) -> None:
        self.login_window = None
        self.select_window = None
        self.main_window = None

    def go_to_login(self) -> None:
        if self.login_window is None:
            from src.ui.login_window import LoginWindow
            self.login_window = LoginWindow(self)
        self.login_window.show()

    def go_to_select(self) -> None:
        if self.select_window is None:
            from src.ui.select_window import SelectWindow
            from src.utils.config import SITE_LIST
            self.select_window = SelectWindow(self, SITE_LIST)
        self.select_window.show()

    def go_to_main(self) -> None:
        if self.main_window is None:
            from src.ui.main_window import MainWindow
            self.main_window = MainWindow(self)

        self.main_window.init_reset()
        self.main_window.show()