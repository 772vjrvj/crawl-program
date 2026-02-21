# src/workers/login_worker.py
from __future__ import annotations

from typing import Tuple
import requests
from requests import Session
from PySide6.QtCore import QThread, Signal

from src.utils.config import server_url


class LoginWorker(QThread):
    login_success: Signal = Signal(object)   # Session
    login_failed: Signal = Signal(str)

    def __init__(self, username: str, password: str) -> None:
        super().__init__()
        self.username = username
        self.password = password

    def run(self) -> None:
        session: Session = requests.Session()
        ok, msg = self._login(session)

        if ok:
            self.login_success.emit(session)
        else:
            self.login_failed.emit(msg)

    def _login(self, session: Session) -> Tuple[bool, str]:
        url = f"{server_url}/auth/login"
        payload = {"username": self.username, "password": self.password}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        try:
            res = session.post(url, json=payload, headers=headers, timeout=15)

            if res.status_code == 200:
                return True, "로그인 성공"
            if res.status_code == 401:
                return False, "아이디 또는 비밀번호가 잘못되었습니다."
            return False, f"서버 오류: {res.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"네트워크 오류: {e}"
        except Exception as e:
            return False, f"알 수 없는 오류: {e}"