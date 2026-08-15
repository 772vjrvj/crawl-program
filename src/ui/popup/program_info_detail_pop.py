# src/ui/popup/program_info_detail_pop.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.style.style import create_common_button


# ============================================================
# 공지사항 / 릴리즈 노트 공통 상세 팝업
# ============================================================
class ProgramInfoDetailPop(QDialog):
    """
    공지사항과 릴리즈 노트에서 공통으로 사용하는 상세 팝업.

    현재는 공지사항에서 실제 사용한다.
    릴리즈 노트 API가 추가되면 동일한 상세 UI를 재사용할 수 있다.
    """

    def __init__(
            self,
            parent: Optional[QWidget],
            window_title: str,
            title: str,
            content: str,
            meta_text: str = "",
            badge_text: str = "",
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(window_title)
        self.resize(620, 500)
        self.setMinimumSize(560, 420)
        self.setStyleSheet("background-color: white; color: #111;")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        if badge_text:
            badge = QLabel(badge_text)
            badge.setStyleSheet(
                """
                QLabel {
                    padding: 5px 9px;
                    background-color: #f2f4f6;
                    color: #333333;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                }
                """
            )
            header_row.addWidget(badge)

        title_label = QLabel(title or "제목 없음")
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #111111;"
        )
        header_row.addWidget(title_label, 1)

        root.addLayout(header_row)

        if meta_text:
            meta_label = QLabel(meta_text)
            meta_label.setStyleSheet(
                "font-size: 12px; color: #888888;"
            )
            root.addWidget(meta_label)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(content or "")
        body.setStyleSheet(
            """
            QTextEdit {
                border: 1px solid #d9d9d9;
                border-radius: 10px;
                background-color: #ffffff;
                color: #222222;
                padding: 12px;
                font-size: 13px;
            }

            QScrollBar:vertical {
                width: 8px;
                background: transparent;
                margin: 10px 2px 10px 0px;
            }

            QScrollBar::handle:vertical {
                min-height: 24px;
                background: rgba(120, 120, 120, 160);
                border-radius: 4px;
            }

            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                border: none;
                background: transparent;
                height: 0px;
            }
            """
        )
        root.addWidget(body, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        close_button = create_common_button(
            "확인",
            self.accept,
            "black",
            120,
        )
        button_row.addWidget(close_button)

        root.addLayout(button_row)
