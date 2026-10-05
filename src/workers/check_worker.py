# src/workers/check_worker.py
from __future__ import annotations

from threading import Event

import requests
from requests import Session
from PySide6.QtCore import QThread, Signal


class CheckWorker(QThread):
    api_failure = Signal(str)
    log_signal = Signal(str)

    CHECK_INTERVAL_SECONDS = 60
    RETRY_MAX_SECONDS = 60

    def __init__(self, session: Session, server_url: str) -> None:
        super().__init__()
        self.session = session
        self.server_url = server_url.rstrip("/")
        self.running = True
        self._stop_event = Event()

    def _active(self) -> bool:
        return self.running and not self._stop_event.is_set()

    def run(self) -> None:
        url = f"{self.server_url}/session/check-me"
        failures = 0
        while self._active():
            reason = ""
            terminal = False
            try:
                res = self.session.get(
                    url,
                    headers={"Accept": "text/plain, application/json"},
                    timeout=(5, 10),
                    allow_redirects=False,
                )
                if not self._active():
                    return
                body = (res.text or "").strip()
                if res.status_code == 200 and body == "success":
                    if failures:
                        self.log_signal.emit("[세션 체크] 통신 복구: 로그인 유지 확인")
                    failures = 0
                    self._stop_event.wait(self.CHECK_INTERVAL_SECONDS)
                    continue
                if res.status_code == 401 or (res.status_code == 200 and body == "fail"):
                    reason = f"로그인 인증이 유효하지 않습니다. 다시 로그인해 주세요. (HTTP {res.status_code})"
                    terminal = True
                elif res.status_code == 403:
                    reason = "세션 확인 권한이 거부되었습니다. 계정 권한을 확인해 주세요. (HTTP 403)"
                    terminal = True
                else:
                    # 서버 오류, 리다이렉트, 예상 밖 응답은 인증 만료로 단정하지 않는다.
                    reason = f"예상하지 못한 서버 응답 (HTTP {res.status_code})"
            except requests.exceptions.Timeout:
                reason = "서버 응답 시간 초과"
            except requests.exceptions.RequestException as exc:
                # URL, 쿠키 등 인증 정보를 로그에 노출하지 않는다.
                reason = f"통신 오류 ({type(exc).__name__})"
            except Exception as exc:
                reason = f"체크 처리 오류 ({type(exc).__name__})"

            if not self._active():
                return
            if terminal:
                self.log_signal.emit(f"[세션 체크] 인증/권한 확인 실패: {reason}")
                self.api_failure.emit(reason)
                return

            failures += 1
            delay = min(5 * (2 ** min(failures - 1, 4)), self.RETRY_MAX_SECONDS)
            self.log_signal.emit(
                f"[세션 체크] 일시 오류 {failures}회: {reason}. {delay}초 후 재확인"
            )
            self._stop_event.wait(delay)

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
