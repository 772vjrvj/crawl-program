# main.py
from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from src.app_manager import AppManager
from src.core.global_state import GlobalState


def show_already_running_alert(existing_app: Optional[QApplication] = None) -> None:
    """
    콘솔 대신 경고창을 최상단으로 띄움.
    - QApplication이 없으면 임시 생성하여 메시지 표시 후 정리
    """
    app_created = False
    app = existing_app or QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app_created = True

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle("이미 실행 중")
    msg.setText("프로그램이 이미 실행 중입니다.\n기존 실행 중인 창을 확인해 주세요.")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    msg.exec()

    if app_created:
        try:
            app.exit(0)
        except Exception:
            pass


def main() -> None:
    app = QApplication(sys.argv)

    state = GlobalState()
    state.initialize()

    app_manager = AppManager()
    app_manager.go_to_login()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()