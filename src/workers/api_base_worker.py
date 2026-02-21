# src/workers/api_base_worker.py
from __future__ import annotations

from typing import Any, Optional, Sequence

from PySide6.QtCore import QThread, Signal


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
        self.user: Optional[Any] = None
        self.excel_data_list: Optional[Any] = None
        self.region: Optional[Any] = None

        self.columns: list[str] = []
        self.sites: list[str] = []
        self.setting: Optional[Any] = None

        self.running: bool = True

    # =========================
    # thread entry
    # =========================
    def run(self) -> None:
        try:
            if not self.init():
                self.log_signal_func("초기화 실패 → 종료")
                self.destroy()
                return

            self.log_signal_func("초기화 성공")

            if not self.main():
                self.log_signal_func("메인 실패")
            else:
                self.log_signal_func("메인 성공")

            self.destroy()
            self.log_signal_func("종료 완료")

        except Exception as e:
            self.log_signal_func("❌ 예외 발생: " + str(e))
            try:
                self.destroy()
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

    # =========================
    # settings
    # =========================
    def get_setting_value(self, setting_list: Sequence[dict[str, Any]], code_name: str) -> Optional[Any]:
        for item in setting_list:
            if item.get("code") == code_name:
                return item.get("value")
        return None

    def set_setting(self, setting_list: Any) -> None:
        self.setting = setting_list

    def set_setting_detail(self, setting_detail: Any) -> None:
        self.setting_detail = setting_detail

    def set_excel_data_list(self, excel_data_list: Any) -> None:
        self.excel_data_list = excel_data_list

    def set_user(self, user: Any) -> None:
        self.user = user

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

    # =========================
    # hooks (override required)
    # =========================
    def init(self) -> bool:
        raise NotImplementedError("init() must be implemented by subclass")

    def main(self) -> bool:
        raise NotImplementedError("main() must be implemented by subclass")

    def destroy(self) -> None:
        raise NotImplementedError("destroy() must be implemented by subclass")