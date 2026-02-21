# src/ui/style/style.py
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPushButton

LOG_STYLE = """
    background-color: #f9f9f9;
    border: 1px solid #ccc;
    padding: 5px;
"""

HEADER_TEXT_STYLE = """
    font-size: 16px;
    font-weight: bold;
    background-color: white;
    color: black;
    padding: 20px;
"""


# =========================
# styles
# =========================
def main_style(color: str) -> str:
    # 활성 스타일 (배경 없음, 테두리/폰트만)
    return f"""
        border-radius: 10px;
        border: 2px solid {color};
        padding: 10px;
        font-weight: 490;
        font-size: 15px;
        color: #333333;
    """

def input_style(color: str) -> str:
    return f"""
        QLineEdit {{
            border-radius: 10px;
            border: 2px solid {color};
            padding: 0px 12px;          /* ✅ 세로 padding 제거, 좌우만 */
            font-size: 15px;
            color: #333333;
        }}
    """


def main_disabled_style() -> str:
    return """
        border-radius: 10px;
        border: 2px solid #B0B0B0;
        padding: 10px;
        font-weight: 490;
        font-size: 15px;
        color: #B0B0B0;
        background-color: #F0F0F0;
    """


# =========================
# common button
# =========================
def apply_common_button_style(
        button: QPushButton,
        bg_color: str = "#4682B4",
        width: int = 140,
        enabled: bool = True,
) -> None:
    # 원색 저장해두면 이후 토글 때 재사용 가능
    button.setProperty("bgColor", bg_color)

    if enabled:
        button.setStyleSheet(main_style(bg_color))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    else:
        button.setStyleSheet(main_disabled_style())
        button.setCursor(Qt.CursorShape.ArrowCursor)

    button.setFixedHeight(40)
    button.setFixedWidth(width)
    button.setEnabled(enabled)


def create_common_button(
        text: str,
        on_click: Callable[[], None],
        bg_color: str = "#4682B4",
        width: int = 140,
        enabled: bool = True,
) -> QPushButton:
    button = QPushButton(text)
    apply_common_button_style(button, bg_color, width, enabled)
    button.clicked.connect(on_click)
    return button


# =========================
# line edit
# =========================
def create_line_edit(
        placeholder: str,
        pw: bool = False,
        color: str = "#888888",
        width: int = 300,
) -> QLineEdit:
    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setStyleSheet(input_style(color))
    line_edit.setFixedHeight(40)
    line_edit.setFixedWidth(width)

    if pw:
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # === 신규 === 패스워드 ● 잘림 방지(일부 폰트에서 효과 큼)
        f = line_edit.font()
        f.setPointSize(14)  # 필요하면 13~15로 조절
        line_edit.setFont(f)

    return line_edit