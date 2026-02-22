# src/workers/logout_worker.py
from __future__ import annotations

from typing import Tuple
from requests import Session
import requests
from PySide6.QtCore import QThread, Signal

from src.utils.config import server_url


class LogoutWorker(QThread):
    logout_success: Signal = Signal(str)
    logout_failed: Signal = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def run(self) -> None:
        ok, msg = self._logout()
        if ok:
            self.logout_success.emit(msg)
        else:
            self.logout_failed.emit(msg)

    def _logout(self) -> Tuple[bool, str]:
        url = f"{server_url}/auth/logout"
        try:
            res = self.session.post(url, timeout=15)
            if res.status_code == 200:
                return True, "로그아웃 성공"
            return False, f"로그아웃 실패: {res.status_code} {res.text}"
        except requests.exceptions.RequestException as e:
            return False, f"네트워크 오류: {e}"
        except Exception as e:
            return False, f"알 수 없는 오류: {e}"