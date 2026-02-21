# src/workers/check_worker.py
from __future__ import annotations

from typing import Optional

import requests
from requests import Session  # === 신규 ===

from PySide6.QtCore import QThread, Signal


class CheckWorker(QThread):
    api_failure: Signal = Signal(str)
    log_signal: Signal = Signal(str)

    def __init__(self, session: Session, server_url: str) -> None:
        super().__init__()
        self.session: Session = session            # === 신규 === cookies -> session
        self.server_url: str = server_url
        self.running: bool = True

    def run(self) -> None:
        url = f"{self.server_url}/session/check-me"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # 60초 대기(중간 stop 즉시 반응하도록 200ms 단위로 쪼갬)
        sleep_total_ms = 60_000
        sleep_step_ms = 200

        while self.running:
            try:
                res = self.session.get(            # === 신규 === requests.get -> session.get
                    url,
                    headers=headers,
                    timeout=15,
                )
                if res.status_code != 200 or (res.text or "").strip() == "fail":
                    self.api_failure.emit("세션 오류: 유효하지 않음")
                    break

            except requests.exceptions.RequestException as e:
                self.api_failure.emit(f"네트워크 오류: {e}")
                break
            except Exception as e:
                self.api_failure.emit(f"예상치 못한 오류: {e}")
                break

            # stop() 누르면 바로 빠지도록 쪼개서 sleep
            waited = 0
            while self.running and waited < sleep_total_ms:
                self.msleep(sleep_step_ms)
                waited += sleep_step_ms

    def stop(self) -> None:
        self.log_signal.emit("로그인 체크 종료")
        self.running = False