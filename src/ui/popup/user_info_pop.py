from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.global_state import GlobalState
from src.ui.style.style import create_common_button


class UserInfoPop(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self.set_layout()

    def _make_window_icon(self) -> QIcon:
        pix = QPixmap(32, 32)
        pix.fill(QColor("transparent"))
        painter = QPainter(pix)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, 32, 32)
        painter.end()
        return QIcon(pix)

    def _center_window(self) -> None:
        frame = self.frameGeometry()
        screen = self.screen()
        if screen is None:
            return

        center = screen.availableGeometry().center()
        frame.moveCenter(center)
        frame.moveTop(frame.top() - 300)
        self.move(frame.topLeft())

    def _get_user_id(self) -> str:
        state = GlobalState()
        user_id = str(state.get(GlobalState.USER_ID, "") or "").strip()
        return user_id or "-"

    def set_layout(self) -> None:
        self.setWindowTitle("유저정보")
        self.resize(400, 180)
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: white; color: #111; } QLabel { color: #111; }")
        self.setWindowIcon(self._make_window_icon())

        popup_layout = QVBoxLayout(self)
        popup_layout.setContentsMargins(10, 10, 10, 10)
        popup_layout.setSpacing(5)

        title_label = QLabel("유저정보")
        title_label.setStyleSheet(
            """
            font-size: 18px;
            font-weight: bold;
            """
        )
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        popup_layout.addWidget(title_label)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 15, 0, 10)
        content_layout.setSpacing(5)

        id_label = QLabel("ID")
        id_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        content_layout.addWidget(id_label)

        id_value_label = QLabel(self._get_user_id())
        id_value_label.setStyleSheet(
            """
            border-radius: 10%;
            border: 2px solid #888888;
            padding: 10px;
            font-size: 14px;
            color: #333333;
            """
        )
        id_value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(id_value_label)

        popup_layout.addLayout(content_layout)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 15, 0, 0)
        button_layout.addStretch()

        confirm_button = create_common_button("확인", self.accept, "black", 140)
        button_layout.addWidget(confirm_button)

        popup_layout.addLayout(button_layout)

        self._center_window()