# src/workers/api_base_worker.py
from __future__ import annotations

from typing import Any, Optional, Sequence

from PySide6.QtCore import QThread, Signal
import time
import os
import sys
import json
import requests
from requests import Session
from src.utils.config import server_name, server_url

class BaseApiWorker(QThread):
    # =========================
    # signals
    # =========================
    log_signal = Signal(str)
    progress_signal = Signal(float, float)
    progress_end_signal = Signal()
    msg_signal = Signal(str, str, object)
    show_countdown_signal = Signal(int)

    # =========================
    # lifecycle
    # =========================
    def __init__(self) -> None:
        super().__init__()

        self.setting_detail: Optional[Any] = None
        self.setting_detail_all_style: Optional[Any] = None
        self.setting_region_filter_favorite = None
        self.user: Optional[Any] = None
        self.excel_data_list: Optional[Any] = None
        self.region: Optional[Any] = None

        self.columns: list[str] = []
        self.sites: list[str] = []
        self.setting: Optional[Any] = None
        self.running: bool = True

        self.session: Optional[Session] = None

        self.program_start_sent: bool = False
        self.program_end_sent: bool = False

    # =========================
    # thread entry
    # =========================
    def run(self) -> None:
        try:

            if not self.running:
                return

            if not self.init():
                self.log_signal_func("초기화 실패 → 종료")
                if self.running:
                    self.destroy()
                return

            self.log_signal_func("초기화 성공")

            # init 성공 후 중앙 서버에 프로그램 시작 전송
            self.send_program_start()

            if not self.running:
                self.log_signal_func("중단 요청 감지")
                self.destroy_with_program_end()
                return

            if not self.main():
                self.log_signal_func("메인 실패")
            else:
                self.log_signal_func("메인 성공")

            if self.running:
                self.destroy_with_program_end()
            else:
                self.send_program_end()

            self.log_signal_func("종료 완료")

        except Exception as e:
            self.log_signal_func("❌ 예외 발생: " + str(e))

            try:
                if self.running:
                    self.destroy_with_program_end()
                else:
                    self.send_program_end()
            except Exception:
                pass

    # =========================
    # signal helpers
    # =========================
    def log_signal_func(self, msg: str) -> None:
        self.log_signal.emit(msg)

    def progress_signal_func(self, before: float, current: float) -> None:
        self.progress_signal.emit(before, current)

    def progress_end_signal_func(self) -> None:
        self.progress_end_signal.emit()

    def msg_signal_func(self, content: str, type_name: str, obj: object) -> None:
        self.msg_signal.emit(content, type_name, obj)

    def show_countdown_signal_func(self, sec: int) -> None:
        self.show_countdown_signal.emit(sec)

    def get_setting_value(self, setting_list: Sequence[dict[str, Any]], code_name: str) -> Optional[Any]:
        for item in setting_list:
            if item.get("code") == code_name:
                return item.get("value")
        return None

    def set_setting(self, setting_list: Any) -> None:
        self.setting = setting_list

    def set_setting_detail(self, setting_detail: Any) -> None:
        self.setting_detail = setting_detail

    def set_setting_detail_all_style(self, setting_detail_all_style: Any) -> None:
        self.setting_detail_all_style = setting_detail_all_style

    def set_setting_region_filter_favorite(self, setting_region_filter_favorite: Any) -> None:
        self.setting_region_filter_favorite = setting_region_filter_favorite

    def set_excel_data_list(self, excel_data_list: Any) -> None:
        self.excel_data_list = excel_data_list

    def set_user(self, user: Any) -> None:
        self.user = user

    def set_session(self, session: Optional[Session]) -> None:
        self.session = session

    def set_columns(self, columns: Optional[Sequence[dict[str, Any]]]) -> None:
        self.columns = []
        if columns:
            self.columns = [str(col.get("value")) for col in columns if col.get("checked", False)]

    def set_sites(self, sites: Optional[Sequence[dict[str, Any]]]) -> None:
        self.sites = []
        if sites:
            self.sites = [str(col.get("value")) for col in sites if col.get("checked", False)]

    def set_region(self, region: Any) -> None:
        self.region = region

    def get_project_root(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)

        return os.path.dirname(os.path.abspath(sys.argv[0]))


    def get_resource_root(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), "_internal")

        return self.get_project_root()


    def get_runtime_db_path(self, db_name: str = "worker_hist.db") -> str:
        return os.path.join(
            self.get_project_root(),
            "runtime",
            "customers",
            "common",
            "db",
            db_name
        )

    def get_runtime_customer_config_path(
            self,
            customer_name: Optional[str] = None,
            file_name: str = "config.json"
    ) -> str:
        """
        runtime/customers/{customer_name}/config.json 경로 반환.
        customer_name이 없으면 worker_name을 사용.
        """
        target_customer_name = customer_name or getattr(self, "worker_name", None)

        if not target_customer_name:
            raise ValueError("customer_name 또는 self.worker_name이 필요합니다.")

        return os.path.join(
            self.get_project_root(),
            "runtime",
            "customers",
            str(target_customer_name),
            file_name
        )


    def read_runtime_customer_config(
            self,
            customer_name: Optional[str] = None,
            file_name: str = "config.json"
    ) -> dict[str, Any]:
        """
        runtime 고객 config.json 읽기.
        파일이 없거나 JSON이 잘못되면 빈 dict 반환.
        """
        config_path = self.get_runtime_customer_config_path(
            customer_name=customer_name,
            file_name=file_name
        )

        if not os.path.exists(config_path):
            self.log_signal_func(f"⚠️ config 파일 없음: {config_path}")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self.log_signal_func(f"⚠️ config 형식 오류(dict 아님): {config_path}")
                return {}

            return data

        except Exception as e:
            self.log_signal_func(f"❌ config 읽기 실패: {config_path} / {e}")
            return {}


    def get_runtime_customer_config_value(
            self,
            key_name: str,
            default: Optional[Any] = None,
            customer_name: Optional[str] = None,
            file_name: str = "config.json"
    ) -> Optional[Any]:
        """
        runtime 고객 config.json에서 특정 key 값 반환.
        기본적으로 self.worker_name 기준 config를 읽음.
        """
        config = self.read_runtime_customer_config(
            customer_name=customer_name,
            file_name=file_name
        )

        return config.get(key_name, default)


    def sleep_s(self, seconds: float) -> bool:
        end = time.time() + float(seconds)
        while time.time() < end:
            if not self.running:
                return False
            time.sleep(0.05)
        return True


    def get_program_id(self) -> Optional[str]:
        """
        runtime/customers/{worker_name}/config.json 에서 key 값을 programId로 사용.
        """
        program_id = self.get_runtime_customer_config_value("key")
        return str(program_id) if program_id else None


    def get_center_server_base_url(self) -> str:
        """
        중앙 서버 base url 반환.
        server_url 우선 사용, 없으면 server_name 사용.
        """
        base_url = str(server_url or "").strip()

        if not base_url:
            base_url = str(server_name or "").strip()

        return base_url.rstrip("/")


    def send_program_status(self, status: str) -> bool:
        """
        중앙 서버에 프로그램 시작/종료 상태 전송.

        status:
            start -> /user/program/start
            end   -> /user/program/end
        """
        if status not in ("start", "end"):
            self.log_signal_func(f"⚠️ 잘못된 프로그램 상태값: {status}")
            return False

        user_id = str(self.user).strip() if self.user else None
        program_id = self.get_program_id()
        base_url = self.get_center_server_base_url()

        if not user_id:
            self.log_signal_func("⚠️ 프로그램 상태 전송 실패: 사용자 id 없음")
            return False

        if not program_id:
            self.log_signal_func("⚠️ 프로그램 상태 전송 실패: programId 없음(config.json key 확인)")
            return False

        if not base_url:
            self.log_signal_func("⚠️ 프로그램 상태 전송 실패: 중앙 서버 주소 없음")
            return False

        url = f"{base_url}/user/program/{status}"

        params = {
            "id": user_id,
            "programId": program_id,
        }

        headers = {
            "Accept": "application/json"
        }

        try:
            client = self.session if self.session is not None else requests

            response = client.get(url, params=params, headers=headers, timeout=5)

            if 200 <= response.status_code < 300:
                self.log_signal_func(
                    f"✅ 프로그램 {status} 전송 성공: id={user_id}, programId={program_id}"
                )
                return True

            self.log_signal_func(
                f"⚠️ 프로그램 {status} 전송 실패: "
                f"status={response.status_code}, body={response.text[:300]}"
            )
            return False

        except Exception as e:
            self.log_signal_func(f"⚠️ 프로그램 {status} 전송 예외: {e}")
            return False


    def send_program_start(self) -> None:
        """
        프로그램 시작 전송.
        중복 전송 방지.
        """
        if self.program_start_sent:
            return

        if self.send_program_status("start"):
            self.program_start_sent = True


    def send_program_end(self) -> None:
        """
        프로그램 종료 전송.
        start가 성공한 경우에만 end 전송.
        중복 전송 방지.
        """
        if self.program_end_sent:
            return

        if not self.program_start_sent:
            return

        if self.send_program_status("end"):
            self.program_end_sent = True


    def destroy_with_program_end(self) -> None:
        """
        destroy 실행 후 프로그램 종료 상태 전송.
        destroy에서 예외가 나도 end는 최대한 전송 시도.
        """
        try:
            self.destroy()
        finally:
            self.send_program_end()


    # =========================
    # hooks (override required)
    # =========================
    def init(self) -> bool:
        raise NotImplementedError("init() must be implemented by subclass")

    def main(self) -> bool:
        raise NotImplementedError("main() must be implemented by subclass")

    def destroy(self) -> None:
        raise NotImplementedError("destroy() must be implemented by subclass")