from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
# QDragMoveEvent가 추가되었습니다.
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDragMoveEvent
from PySide6.QtWidgets import QLabel


class ExcelDragDropLabel(QLabel):
    fileDropped: Signal = Signal(list)

    _ALLOWED_EXTS = {".xlsx", ".xlsm", ".csv"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setAcceptDrops(True)
        self._set_hint("엑셀 파일을 여기에 드래그하세요.")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 2px dashed #aaaaaa; padding: 10px; font-size: 14px; background:white; color:#111;")
        self.setFixedHeight(100)

    def _set_hint(self, text: str) -> None:
        self.setText(text)

    def _is_valid_file(self, path: str) -> bool:
        try:
            return Path(path).suffix.lower() in self._ALLOWED_EXTS
        except Exception:
            return False

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        md = event.mimeData()
        if md is not None and md.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    # 다중 파일 인식을 확실히 하기 위해 dragMoveEvent 추가
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]
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

        urls = md.urls() or []
        files: List[str] = [u.toLocalFile() for u in urls if u.isLocalFile()]

        valid_files: List[str] = [f for f in files if self._is_valid_file(f)]

        if valid_files:
            self.fileDropped.emit(valid_files)
        else:
            self._set_hint("지원하지 않는 파일 형식입니다. 엑셀 파일을 드래그하세요.")

        event.acceptProposedAction()