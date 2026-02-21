# src/ui/login_window.py
from __future__ import annotations

from typing import Any, Optional

import keyring
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from requests import Session  # === 신규 ===

from src.core.global_state import GlobalState
from src.ui.password_change_window import PasswordChangeWindow
from src.ui.style.style import create_common_button, create_line_edit
from src.utils.config import server_name
from src.workers.login_worker import LoginWorker


class LoginWindow(QWidget):
    def __init__(self, app_manager: Any) -> None:
        super().__init__()

        self.app_manager = app_manager
        self.login_worker: Optional[LoginWorker] = None

        self.setWindowTitle("로그인")
        self.setWindowIcon(self._make_window_icon())
        self.resize(500, 300)
        self.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        self.id_input = create_line_edit("ID를 입력하세요", False, "#888888", 300)
        self.password_input = create_line_edit("비밀번호를 입력하세요", True, "#888888", 300)

        self.auto_login_checkbox = QCheckBox("자동 로그인", self)
        self.auto_login_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_login_checkbox.setStyleSheet(
            """
            QCheckBox {
                font-size: 13px;
                color: #444;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid #888;
                background-color: #f0f0f0;
            }
            QCheckBox::indicator:checked {
                background-color: #4682B4;
                image: url();
            }
            """
        )
        self.auto_login_checkbox.setChecked(False)

        button_layout = QHBoxLayout()
        self.login_button = create_common_button("로그인", self.login, "#4682B4", 140)
        self.change_password_button = create_common_button("비밀번호 변경", self.change_password, "#4682B4", 140)

        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.change_password_button)
        button_layout.setSpacing(20)

        layout.addWidget(self.id_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.auto_login_checkbox)
        layout.addLayout(button_layout)

        # === 신규 === QDesktopWidget 제거(Deprecated) → screen geometry로 중앙 배치
        self._center_window()

        # ✅ 자동 로그인 시도
        self.try_auto_login()

    # =========================
    # ui helpers
    # =========================
    def _make_window_icon(self) -> QIcon:
        pix = QPixmap(32, 32)
        pix.fill(QColor("transparent"))

        painter = QPainter(pix)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#e0e0e0"))
        painter.drawRect(0, 0, 32, 32)
        painter.end()

        return QIcon(pix)

    def _center_window(self) -> None:
        screen = self.screen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(avail.center())
        self.move(geo.topLeft())

    # =========================
    # actions
    # =========================
    def try_auto_login(self) -> None:
        try:
            username = keyring.get_password(server_name, "username")
            password = keyring.get_password(server_name, "password")

            if username and password:
                self.id_input.setText(username)
                self.password_input.setText(password)
                self.auto_login_checkbox.setChecked(True)
                self.login()  # 자동 로그인 실행
        except Exception:
            # 자동 로그인은 실패해도 조용히 패스(기존 유지)
            pass

    @Slot()
    def login(self) -> None:
        username = self.id_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self.show_message("로그인 실패", "아이디와 비밀번호를 입력해주세요.")
            return

        # === 신규 === 기존 워커가 살아있으면 참조 해제(중복 클릭 대비)
        self.login_worker = LoginWorker(username, password)

        # === 신규 === LoginWorker가 Session을 emit 하는 형태로 연결
        self.login_worker.login_success.connect(self.on_login_success)
        self.login_worker.login_failed.connect(self.show_error_message)
        self.login_worker.start()

    @Slot(str)
    def show_error_message(self, message: str) -> None:
        QMessageBox.critical(self, "로그인 실패", message)

    def show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    @Slot()
    def change_password(self) -> None:
        popup = PasswordChangeWindow(parent=self)
        popup.exec()  # PySide6: exec_() → exec()

    # === 신규 === cookies 대신 Session을 받는다
    @Slot(object)
    def on_login_success(self, session_obj: object) -> None:
        # PySide6 Signal(object)로 넘어오므로 런타임 캐스팅만 수행
        session = session_obj  # type: ignore[assignment]
        if not isinstance(session, Session):
            # 방어 코드: 예상 타입이 아니면 실패 처리
            QMessageBox.critical(self, "로그인 실패", "세션 객체가 올바르지 않습니다.")
            return

        state = GlobalState()
        state.set("session", session)  # === 신규 === cookies -> session

        if self.auto_login_checkbox.isChecked():
            username = self.id_input.text()
            password = self.password_input.text()
            keyring.set_password(server_name, "username", username)
            keyring.set_password(server_name, "password", password)
        else:
            try:
                keyring.delete_password(server_name, "username")
                keyring.delete_password(server_name, "password")
            except keyring.errors.PasswordDeleteError:
                pass

        self.close()
        self.app_manager.go_to_select()