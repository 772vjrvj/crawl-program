# src/ui/popup/closing_pop.py  (원하는 위치에 파일 하나 추가)
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar


class ClosingPop(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # 모달 + X 버튼/타이틀 최소화
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.setStyleSheet("""
        QDialog {
            background: white;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        QLabel {
            font-size: 14px;
        }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        self.lbl = QLabel("프로그램 종료중입니다...\n자원을 정리하고 있습니다.", self)
        self.lbl.setAlignment(Qt.AlignCenter)

        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(30)
        self.bar.setTextVisible(False)

        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)

        self.resize(320, 120)

    def set_done(self, ok: bool) -> None:
        self.bar.setValue(100)
        if ok:
            self.lbl.setText("정상 종료 준비 완료!\n잠시 후 프로그램이 종료됩니다.")
        else:
            self.lbl.setText("종료 정리 중 일부 오류가 발생했습니다.\n잠시 후 프로그램이 종료됩니다.")