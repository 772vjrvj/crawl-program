# launcher/ui/notice_dialog.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QCheckBox, QPushButton
)

from launcher.core.api import NoticeInfo
from launcher.ui.style.style import (
    BTN_GRAY,
    btn_style,
    msgbox_style,
)


# === 신규 === 공지 모달 (LauncherWindow에서 분리)
class NoticeDialog(QDialog):
    def __init__(self, parent: QWidget, notice: NoticeInfo, allow_hide_day: bool) -> None:
        super().__init__(parent)
        self.notice = notice
        self.setWindowTitle("공지사항")
        self.setMinimumWidth(520)

        # === 신규 === 다이얼로그 공통 스타일
        self.setStyleSheet(msgbox_style(primary_color=BTN_GRAY))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel(f"{notice.title}")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(title)

        lvl = QLabel(f"중요도: {notice.level}")
        lvl.setStyleSheet("color: #666;")
        root.addWidget(lvl)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setText(notice.content)
        body.setMinimumHeight(220)
        root.addWidget(body)

        self.chk_hide = QCheckBox("오늘 하루 안보기")
        self.chk_hide.setEnabled(bool(allow_hide_day))
        root.addWidget(self.chk_hide)

        row = QHBoxLayout()
        row.addStretch(1)

        btn_ok = QPushButton("확인")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(btn_style(BTN_GRAY))  # === 신규 ===
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_ok)

        root.addLayout(row)

        # === 신규 === 엔터키 기본 동작
        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)

    def hide_day_checked(self) -> bool:
        return self.chk_hide.isEnabled() and self.chk_hide.isChecked()