# main.py
from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_manager import AppManager
from src.core.global_state import GlobalState


def show_already_running_alert(existing_app: Optional[QApplication] = None) -> None:
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


def main() -> int:
    app = QApplication(sys.argv)

    state = GlobalState()
    state.initialize()

    manager = AppManager(app)
    manager.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())