# src/ui/popup/excel_drag_drop_label.py
from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel


class ExcelDragDropLabel(QLabel):
    # PySide6: Signal 사용 + 타입은 런타임 강제는 아니지만 문서화/IDE 도움 됨
    fileDropped: Signal = Signal(list)

    _ALLOWED_EXTS = {".xlsx", ".xlsm", ".csv"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setAcceptDrops(True)
        self._set_hint("엑셀 파일을 여기에 드래그하세요.")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 2px dashed #aaaaaa; padding: 10px; font-size: 14px;")
        self.setFixedHeight(100)

    def _set_hint(self, text: str) -> None:
        self.setText(text)

    def _is_valid_file(self, path: str) -> bool:
        # pathlib로 확장자 판별 안정화
        try:
            return Path(path).suffix.lower() in self._ALLOWED_EXTS
        except Exception:
            return False

    # Qt 이벤트 오버라이드는 시그니처만 맞추면 충분 (타입 힌트는 유지)
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        md = event.mimeData()
        if md is not None and md.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        md = event.mimeData()
        if md is None or not md.hasUrls():
            event.ignore()
            return

        # urls()는 보통 None이 아니지만 방어적으로 처리
        urls = md.urls() or []
        files: List[str] = [u.toLocalFile() for u in urls if u.isLocalFile()]

        valid_files: List[str] = [f for f in files if self._is_valid_file(f)]

        if valid_files:
            self.fileDropped.emit(valid_files)
        else:
            self._set_hint("지원하지 않는 파일 형식입니다. 엑셀 파일을 드래그하세요.")

        event.acceptProposedAction()