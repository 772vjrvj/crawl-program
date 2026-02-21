# src/workers/change_password_woker.py

from __future__ import annotations

from typing import Tuple

import requests
from requests import Session

from PySide6.QtCore import QThread, Signal

from src.utils.config import server_url


class ChangePasswordWorker(QThread):
    password_change_success: Signal = Signal()
    password_change_failed: Signal = Signal(str)

    def __init__(self, session: Session, username: str, current_pw: str, new_pw: str) -> None:
        super().__init__()
        self.session: Session = session
        self.username: str = username
        self.current_pw: str = current_pw
        self.new_pw: str = new_pw

    def run(self) -> None:
        ok, msg = self._change_password()
        if ok:
            self.password_change_success.emit()
        else:
            self.password_change_failed.emit(msg)

    def _change_password(self) -> Tuple[bool, str]:
        url = f"{server_url}/auth/change-password"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        payload = {
            "id": self.username,
            "currentPassword": self.current_pw,
            "newPassword": self.new_pw,
        }

        try:
            # 서버가 params를 기대하는 구조 유지(기존 코드 유지)
            res = self.session.put(url, params=payload, headers=headers, timeout=15)

            if res.status_code == 200:
                return True, "비밀번호 변경 성공"
            if res.status_code == 400:
                return False, "현재 비밀번호가 올바르지 않습니다."
            if res.status_code == 403:
                return False, "권한이 없습니다."
            return False, f"서버 오류: {res.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"네트워크 오류: {e}"
        except Exception as e:
            return False, f"예상치 못한 오류: {e}"