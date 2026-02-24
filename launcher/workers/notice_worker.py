# launcher/workers/notice_worker.py
from __future__ import annotations  # === 신규 ===

from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QThread, Signal

from launcher.core.api import fetch_latest_notice, NoticeInfo


@dataclass
class NoticeResult:
    ok: bool
    message: str
    notice: Optional[NoticeInfo] = None


class NoticeWorker(QThread):
    sig_done: Signal = Signal(object)  # NoticeResult

    def __init__(self, server_url: str, program_id: str) -> None:
        super().__init__()
        self.server_url = server_url
        self.program_id = program_id

    def run(self) -> None:
        try:
            ok, msg, notice = fetch_latest_notice(self.server_url, self.program_id)
            self.sig_done.emit(NoticeResult(ok, msg, notice))
        except Exception as e:
            self.sig_done.emit(NoticeResult(False, f"unexpected error: {str(e)}", None))