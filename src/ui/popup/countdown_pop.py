# src/ui/popup/countdown_pop.py
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class CountdownPop(QDialog):
    def __init__(self, seconds: int, parent: QDialog | None = None) -> None:
        super().__init__(parent)

        self.remaining: int = int(seconds)

        self.setWindowTitle("대기 중...")
        self.setFixedSize(300, 100)

        self.label: QLabel = QLabel(self._make_text(), self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout: QVBoxLayout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        # 1초마다 업데이트
        self.timer: QTimer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)  # type: ignore[arg-type]
        self.timer.start(1000)

    def _make_text(self) -> str:
        return f"남은 시간: {self.remaining}초"

    def update_countdown(self) -> None:
        self.remaining -= 1

        if self.remaining <= 0:
            self.timer.stop()
            self.accept()  # 팝업 종료
            return

        self.label.setText(self._make_text())