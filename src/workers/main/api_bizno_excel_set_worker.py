import json
import os
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bs4 import BeautifulSoup
from requests import Response, Session

from src.core.global_state import GlobalState
from src.utils.api_utils import APIClient
from src.utils.config import server_url
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiBiznoExcelSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.api_client = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "BIZNO"
        self.total_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.folder_path: str = ""

        # 저장 하위 폴더
        self.out_dir: str = "output_bizno"

        # =========================
        # 전체 요청 휴식 정책
        # =========================

        # === 변경 ===
        # 30건마다 70~110초 쉬기
        self._rest_every_n: int = 30
        self._rest_range_sec = (70.0, 110.0)

        # === 변경 ===
        # 110건마다 5~8분 쉬기
        self._long_rest_every_n: int = 110
        self._long_rest_range_sec = (300.0, 480.0)

        # === 변경 ===
        # 320건마다 15~25분 쉬기
        self._super_rest_every_n: int = 320
        self._super_rest_range_sec = (900.0, 1500.0)

        # === 유지 ===
        self._preemptive_rest_every_n: int = 0
        self._preemptive_rest_sec: int = 0

        # === 변경 ===
        # 70분마다 4~6분 쉬기
        self._time_rest_every_sec: int = 4200
        self._time_rest_range_sec = (240.0, 360.0)

        self._run_started_monotonic: float = 0.0
        self._last_time_rest_monotonic: float = 0.0

        # =========================
        # 호출 사이 휴식 정책
        # =========================

        # === 변경 ===
        # 로컬 search -> detail 사이 휴식
        self._local_search_detail_gap_range_sec = (4.0, 7.0)

        # === 변경 ===
        # 채널 실패 후 다음 채널로 넘어가기 전 휴식
        self._between_channel_rest_range_sec = (12.0, 22.0)

        # === 변경 ===
        # 아이템 시작 전 / 완료 후 기본 텀
        self._before_item_request_range_sec = (7.0, 10.0)
        self._after_item_request_range_sec = (11.0, 15.0)

        # === 유지 ===
        self._rotate_every_n: int = 0

        # 간단 차단 감지 키워드
        self._block_keywords = [
            "접근이 차단",
            "비정상적인 접근",
            "잠시 후 다시",
            "Too Many Requests",
            "Request blocked",
            "Access Denied",
            "Forbidden",
            "현재 접속인원이 많아 접속이 지연되고 있습니다",
            "접속대기중",
            "접속 대기중",
            "stand-by state",
            "Please try again. (1)",
        ]

        # === 신규 ===
        # 하드 스톱 메시지
        self._hard_stop_keywords = [
            "사용 가능한 처리 서버가 없습니다.",
            "bizno 검색 차단/제한 페이지 감지",
            "접근이 차단",
            "비정상적인 접근",
            "Too Many Requests",
            "Request blocked",
            "Access Denied",
            "Forbidden",
            "접속대기중",
            "접속 대기중",
        ]

        # === 유지 ===
        self._request_channels: List[Dict[str, Any]] = []
        self._request_mode_index: int = 0

        # === 변경 ===
        self._kst = timezone(timedelta(hours=9))
        self._use_direct_request_channel: bool = True

        # === 변경 ===
        self._channel_min_gap_sec: int = 155

        # === 변경 ===
        # 리밋 제거
        self._channel_daily_limit: int = 0

        self._channel_daily_counts: Dict[str, int] = {}
        self._channel_last_used_monotonic: Dict[str, float] = {}
        self._daily_limit_date_key: str = ""
        self._force_stop_requested: bool = False
        self._force_stop_reason: str = ""

        # === 신규 ===
        # 로컬 차단 등으로 당일 제외 처리된 채널
        self._channel_disabled_today: Dict[str, str] = {}

        state = GlobalState()
        self.api_user_id: str = state.get("user_id")
        self.session: Optional[Session] = state.get("session")

        self.bizno_search_and_detail_url: str = f"{server_url}/bizno/search-and-detail"
        self.active_server_count_url: str = f"{server_url}/internal/api-key-info/active-server-count"

        # trace context
        self.program_trace_id: str = ""
        self.api_trace_id: str = ""
        self.request_trace_id: str = ""
        self.attempt_no: int = 0
        self.server_id: str = ""
        self.job_name: str = ""
        self.item_key: str = ""

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.load_request_channels()
        self.init_trace_context()
        self.init_runtime_rest_context()
        self.reset_daily_channel_state_if_needed()

        self.log_signal_func(
            f"요청 채널 목록 : {[self.channel_label(ch) for ch in self._request_channels]}"
        )
        self.log_signal_func(
            f"안전 운용 정책 : direct={self._use_direct_request_channel}, "
            f"channel_min_gap={self._channel_min_gap_sec}s, "
            f"channel_daily_limit={'unlimited' if self._channel_daily_limit <= 0 else self._channel_daily_limit}"
        )
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func(f"크롤링 시작. 전체 수 {len(self.excel_data_list)}")

            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            self.csv_filename = os.path.basename(
                self.file_driver.get_csv_filename(self.site_name)
            )

            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.log_signal_func(f"✅ CSV 생성: {self.csv_filename}")

            self.total_cnt = len(self.excel_data_list)

            for index, item in enumerate(self.excel_data_list, start=1):
                if not self.running:
                    self.log_signal_func("⛔ running=False 감지. main 루프 종료")
                    return True

                if self._force_stop_requested:
                    self.log_signal_func(f"⛔ 강제 종료 플래그 감지: {self._force_stop_reason}")
                    return True

                try:
                    q_name = (item.get("검색회사명") or "").strip()
                    q_owner = (item.get("검색대표자명") or "").strip()
                    q_addr = (item.get("검색회사주소") or "").strip()
                except Exception:
                    q_name, q_owner, q_addr = "", "", ""

                self.log_signal_func(f"==================== [{index}/{self.total_cnt}] 처리 시작 ====================")
                self.log_signal_func(
                    f"입력값: 검색회사명='{q_name}', 검색대표자명='{q_owner}', 검색회사주소='{q_addr}'"
                )
                self.log_signal_func(f"현재 요청 채널: {self.get_current_request_mode()}")

                sleep1 = random.uniform(
                    self._before_item_request_range_sec[0],
                    self._before_item_request_range_sec[1]
                )
                self.log_signal_func(f"조회 전 잠시 쉽니다. ({sleep1:.2f}s)")
                if not self.sleep_s(sleep1):
                    self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                    return True

                self.log_signal_func("🔎 search + detail 통합 조회 시작")
                ok = self.fetch_search_and_detail(item)
                self.log_signal_func("🔎 search + detail 통합 조회 완료")

                if not ok:
                    self.log_signal_func("⛔ fetch_search_and_detail 중단 요청 감지. main 루프 종료")
                    return True

                if self._force_stop_requested:
                    self.log_signal_func(f"⛔ 강제 종료 사유: {self._force_stop_reason}")
                    return True

                sleep2 = random.uniform(
                    self._after_item_request_range_sec[0],
                    self._after_item_request_range_sec[1]
                )
                self.log_signal_func(f"조회 후 잠시 쉽니다. ({sleep2:.2f}s)")
                if not self.sleep_s(sleep2):
                    self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                    return True

                self.log_signal_func(f"item : {item}")

                pro_value: float = (index / self.total_cnt) * 1000000
                pct = (index / self.total_cnt) * 100.0 if self.total_cnt else 0.0
                self.log_signal_func(f"진행률: {pct:.2f}% ({index}/{self.total_cnt})")
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value

                self.log_signal_func("💾 CSV 저장(append) 시작")
                self.excel_driver.append_to_csv(
                    self.csv_filename,
                    [item],
                    self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("💾 CSV 저장(append) 완료")

                # 선제 장기 휴식
                if self._preemptive_rest_every_n > 0 and (index % self._preemptive_rest_every_n == 0):
                    self.log_signal_func(
                        f"🕒 선제 장기 휴식 ({self._preemptive_rest_every_n}건마다): "
                        f"{self._preemptive_rest_sec // 60}분"
                    )
                    if not self.sleep_s(self._preemptive_rest_sec):
                        self.log_signal_func("⛔ 선제 장기 휴식 중단 감지. main 루프 종료")
                        return True

                # 대량 요청 방지 휴식
                if self._rest_every_n > 0 and (index % self._rest_every_n == 0):
                    sleep_t = random.uniform(self._rest_range_sec[0], self._rest_range_sec[1])
                    self.log_signal_func(f"🕒 대량 요청 방지 휴식 ({self._rest_every_n}건마다): {sleep_t:.1f}s")
                    if not self.sleep_s(sleep_t):
                        self.log_signal_func("⛔ 휴식 중단 감지. main 루프 종료")
                        return True

                if self._long_rest_every_n > 0 and (index % self._long_rest_every_n == 0):
                    sleep_t = random.uniform(self._long_rest_range_sec[0], self._long_rest_range_sec[1])
                    self.log_signal_func(f"🕒 긴 휴식 ({self._long_rest_every_n}건마다): {sleep_t:.1f}s")
                    if not self.sleep_s(sleep_t):
                        self.log_signal_func("⛔ 긴 휴식 중단 감지. main 루프 종료")
                        return True

                if self._super_rest_every_n > 0 and (index % self._super_rest_every_n == 0):
                    sleep_t = random.uniform(self._super_rest_range_sec[0], self._super_rest_range_sec[1])
                    self.log_signal_func(f"🕒 초긴 휴식 ({self._super_rest_every_n}건마다): {sleep_t:.1f}s")
                    if not self.sleep_s(sleep_t):
                        self.log_signal_func("⛔ 초긴 휴식 중단 감지. main 루프 종료")
                        return True

                # 시간 기반 휴식
                if not self.apply_time_based_rest_if_needed(index):
                    self.log_signal_func("⛔ 시간 기반 휴식 중단 감지. main 루프 종료")
                    return True

                self.log_signal_func(f"다음 요청 예정 채널: {self.get_current_request_mode()}")
                self.log_signal_func(f"==================== [{index}/{self.total_cnt}] 처리 완료 ====================")

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")

        self.log_signal_func("✅ main 종료")
        return True

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func, timeout=(10, 30))
        self.log_signal_func("✅ 드라이버 세팅 완료")

    def cleanup(self) -> None:
        self.log_signal_func("🧹 cleanup 시작")

        try:
            setting = self.setting if self.setting is not None else []
            self.folder_path = str(self.get_setting_value(setting, "folder_path") or "").strip()
        except Exception as e:
            self.log_signal_func(f"[cleanup] folder_path 조회 실패: {e}")
            self.folder_path = ""

        try:
            if self.csv_filename and self.excel_driver:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.api_client:
                self.log_signal_func("🔌 api_client.close 시작")
                self.api_client.close()
                self.log_signal_func("🔌 api_client.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            if self.file_driver:
                self.log_signal_func("🔌 file_driver.close 시작")
                self.log_signal_func("🔌 file_driver.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            if self.excel_driver:
                self.log_signal_func("🔌 excel_driver.close 시작")
                self.excel_driver.close()
                self.log_signal_func("🔌 excel_driver.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")

        self.log_signal_func("🧹 cleanup 완료")

    # 정지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self.log_signal_func("⛔ running=False 설정 완료. 2초 후 cleanup 진행")

        try:
            self.cleanup()
        except Exception as e:
            self.log_signal_func(f"[stop] cleanup 실패: {e}")

        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.log_signal_func("✅ destroy 시작")
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2)
        self.progress_end_signal.emit()
        self.log_signal_func("✅ progress_end_signal emit 완료")

    # =========================
    # runtime rest helpers
    # =========================
    def init_runtime_rest_context(self) -> None:
        now = time.monotonic()
        self._run_started_monotonic = now
        self._last_time_rest_monotonic = now

        self.log_signal_func(
            f"[rest] 시간 기반 휴식 초기화: every={self._time_rest_every_sec}s, "
            f"range={self._time_rest_range_sec}"
        )

    def apply_time_based_rest_if_needed(self, index: int) -> bool:
        if self._time_rest_every_sec <= 0:
            return True

        now = time.monotonic()

        if self._last_time_rest_monotonic <= 0:
            self._last_time_rest_monotonic = now
            return True

        elapsed_since_last_rest = now - self._last_time_rest_monotonic
        total_elapsed = now - self._run_started_monotonic

        if elapsed_since_last_rest < self._time_rest_every_sec:
            return True

        sleep_t = random.uniform(self._time_rest_range_sec[0], self._time_rest_range_sec[1])

        self.log_signal_func(
            f"🕒 시간 기반 휴식: index={index}, "
            f"누적운영={total_elapsed / 3600.0:.2f}h, "
            f"최근휴식후={elapsed_since_last_rest / 60.0:.1f}분, "
            f"휴식={sleep_t:.1f}s"
        )

        if not self.sleep_s(sleep_t):
            return False

        self._last_time_rest_monotonic = time.monotonic()
        return True

    # =========================
    # request channel helpers
    # =========================
    def normalize_base_url(self, value: Any) -> str:
        return str(value or "").strip().rstrip("/")

    def channel_label(self, channel: Optional[Dict[str, Any]]) -> str:
        if not channel:
            return "request"
        return str(
            channel.get("label")
            or channel.get("server_id")
            or channel.get("mode")
            or "request"
        ).strip()

    def build_direct_channel(self) -> Dict[str, Any]:
        return {
            "mode": "request",
            "type": "direct",
            "label": "local_1",
            "server_id": "local_1",
            "base_url": "",
            "api_key": "",
        }

    def build_server_channel(self, index: int) -> Dict[str, Any]:
        server_id_value = f"server_{index}"
        return {
            "mode": "server",
            "type": "server",
            "label": server_id_value,
            "server_id": server_id_value,
            "base_url": self.normalize_base_url(server_url),
            "api_key": "",
        }

    def build_fallback_server_channel(self) -> Dict[str, Any]:
        return {
            "mode": "server",
            "type": "server",
            "label": "server_1",
            "server_id": "server_1",
            "base_url": self.normalize_base_url(server_url),
            "api_key": "",
        }

    def request_active_server_count(self) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("session 없음(active-server-count 조회 불가)")

        headers = {
            "Accept": "application/json",
        }

        if self.api_user_id:
            headers["X-USER-ID"] = self.api_user_id

        self.log_signal_func(f"[channel] active-server-count 조회 시작: {self.active_server_count_url}")

        resp = self.session.get(
            self.active_server_count_url,
            headers=headers,
            timeout=(5, 30),
        )

        self.log_signal_func(
            f"[channel] active-server-count 응답: status={getattr(resp, 'status_code', 'unknown')}"
        )

        return self._loads_if_needed(resp.text)

    def extract_active_server_count(self, payload: Any) -> int:
        if isinstance(payload, dict):
            value = payload.get("count")
            if value is None and isinstance(payload.get("data"), dict):
                value = payload.get("data", {}).get("count")
            if value is None and isinstance(payload.get("result"), dict):
                value = payload.get("result", {}).get("count")

            try:
                count = int(value or 0)
            except Exception:
                count = 0

            if count < 0:
                count = 0

            return count

        return 0

    def load_request_channels(self) -> None:
        channels: List[Dict[str, Any]] = []

        if self._use_direct_request_channel:
            channels.append(self.build_direct_channel())

        try:
            payload = self.request_active_server_count()
            active_server_count = self.extract_active_server_count(payload)

            self.log_signal_func(f"[channel] active server count={active_server_count}")

            if active_server_count > 0:
                for i in range(1, active_server_count + 1):
                    channels.append(self.build_server_channel(i))
            else:
                self.log_signal_func("[channel] active server count=0. fallback server_1 사용")
                channels.append(self.build_fallback_server_channel())

        except Exception as e:
            self.log_signal_func(f"[channel] active-server-count 조회 실패: {e}")
            self.log_signal_func("[channel] fallback server_1 채널 사용")
            channels.append(self.build_fallback_server_channel())

        self._request_channels = channels
        self._request_mode_index = 0

        self.log_signal_func(
            f"[channel] 최종 채널 목록: {[self.channel_label(ch) for ch in self._request_channels]}"
        )

    def get_current_request_channel(self) -> Dict[str, Any]:
        if not self._request_channels:
            return self.build_direct_channel()

        try:
            return self._request_channels[self._request_mode_index]
        except Exception:
            return self.build_direct_channel()

    def get_current_request_mode(self) -> str:
        return self.channel_label(self.get_current_request_channel())

    def now_kst_date_key(self) -> str:
        return datetime.now(self._kst).strftime("%Y-%m-%d")

    def reset_daily_channel_state_if_needed(self) -> None:
        date_key = self.now_kst_date_key()

        if self._daily_limit_date_key == date_key:
            return

        self._daily_limit_date_key = date_key
        self._channel_daily_counts = {}
        self._channel_last_used_monotonic = {}
        self._channel_disabled_today = {}

        self.log_signal_func(
            f"[channel] 일일 채널 상태 초기화: date={self._daily_limit_date_key}, "
            f"channel_daily_limit={'unlimited' if self._channel_daily_limit <= 0 else self._channel_daily_limit}"
        )

    def get_channel_daily_count(self, channel: Optional[Dict[str, Any]]) -> int:
        self.reset_daily_channel_state_if_needed()
        label = self.channel_label(channel)
        try:
            return int(self._channel_daily_counts.get(label, 0) or 0)
        except Exception:
            return 0

    def is_channel_disabled_today(self, channel: Optional[Dict[str, Any]]) -> bool:
        self.reset_daily_channel_state_if_needed()
        label = self.channel_label(channel)
        return label in self._channel_disabled_today

    def disable_channel_for_today(self, channel: Optional[Dict[str, Any]], reason: str) -> None:
        self.reset_daily_channel_state_if_needed()
        label = self.channel_label(channel)
        self._channel_disabled_today[label] = str(reason or "").strip()

        self.log_signal_func(
            f"[channel] 당일 제외 처리: label={label}, reason={self._channel_disabled_today[label]}"
        )

    def is_channel_daily_exhausted(self, channel: Optional[Dict[str, Any]]) -> bool:
        if self.is_channel_disabled_today(channel):
            return True

        if self._channel_daily_limit <= 0:
            return False

        return self.get_channel_daily_count(channel) >= self._channel_daily_limit

    def get_available_request_channel_count(self) -> int:
        self.reset_daily_channel_state_if_needed()

        count = 0
        for ch in self._request_channels:
            if not self.is_channel_daily_exhausted(ch):
                count += 1
        return count

    def find_next_available_channel_index(self, start_index: int = 0) -> int:
        self.reset_daily_channel_state_if_needed()

        if not self._request_channels:
            return -1

        total = len(self._request_channels)

        for offset in range(total):
            idx = (start_index + offset) % total
            ch = self._request_channels[idx]

            if not self.is_channel_daily_exhausted(ch):
                return idx

        return -1

    def ensure_current_request_channel_available(self) -> bool:
        self.reset_daily_channel_state_if_needed()

        if not self._request_channels:
            self.request_force_stop("요청 채널이 비어 있습니다.")
            return False

        current_channel = self.get_current_request_channel()

        if not self.is_channel_daily_exhausted(current_channel):
            return True

        next_index = self.find_next_available_channel_index(self._request_mode_index + 1)
        if next_index < 0:
            self.request_force_stop("오늘 사용 가능한 요청 채널이 없습니다.")
            return False

        prev_mode = self.channel_label(current_channel)
        self._request_mode_index = next_index
        next_channel = self.get_current_request_channel()
        next_mode = self.channel_label(next_channel)

        self.rotate_api_trace(f"skip-unavailable {prev_mode}->{next_mode}")

        self.log_signal_func(
            f"[channel] 사용 불가 채널 건너뜀: {prev_mode} -> {next_mode}"
        )
        return True

    def resolve_server_id(self, channel: Optional[Dict[str, Any]] = None) -> str:
        ch = channel or self.get_current_request_channel()
        return str(ch.get("server_id") or ch.get("label") or ch.get("mode") or "unknown").strip()

    def rotate_request_mode(self, reason: str = "") -> str:
        prev_channel = self.get_current_request_channel()
        prev_mode = self.channel_label(prev_channel)

        next_index = self.find_next_available_channel_index(self._request_mode_index + 1)
        if next_index < 0:
            self.request_force_stop(
                f"rotate 실패: 사용 가능한 요청 채널 없음, reason={reason}, prev_mode={prev_mode}"
            )
            return prev_mode

        self._request_mode_index = next_index

        next_channel = self.get_current_request_channel()
        next_mode = self.channel_label(next_channel)

        self.rotate_api_trace(reason or f"{prev_mode}->{next_mode}")

        self.log_signal_func(
            f"🔁 요청 채널 변경: {prev_mode} -> {next_mode}, "
            f"api_trace_id={self.api_trace_id}"
        )
        return next_mode

    def wait_channel_gap_if_needed(self, channel: Dict[str, Any]) -> bool:
        if self._channel_min_gap_sec <= 0:
            return True

        label = self.channel_label(channel)
        last_used = float(self._channel_last_used_monotonic.get(label, 0.0) or 0.0)

        if last_used <= 0:
            return True

        now = time.monotonic()
        elapsed = now - last_used
        remain = self._channel_min_gap_sec - elapsed

        if remain <= 0:
            return True

        self.log_signal_func(
            f"[channel-gap] {label} 최소 간격 대기: remain={remain:.2f}s, "
            f"min_gap={self._channel_min_gap_sec}s"
        )
        return self.sleep_s(remain)

    def mark_channel_used(self, channel: Dict[str, Any]) -> None:
        self.reset_daily_channel_state_if_needed()

        label = self.channel_label(channel)
        used_count = self.get_channel_daily_count(channel) + 1

        self._channel_daily_counts[label] = used_count
        self._channel_last_used_monotonic[label] = time.monotonic()

        if self._channel_daily_limit <= 0:
            self.log_signal_func(
                f"[channel] 사용 기록: label={label}, daily_count={used_count}, daily_limit=unlimited"
            )
        else:
            self.log_signal_func(
                f"[channel] 사용 기록: label={label}, daily_count={used_count}/{self._channel_daily_limit}"
            )

    # =========================
    # helpers
    # =========================
    def safe_text(self, el, sep: str = " ", strip: bool = True) -> str:
        try:
            return el.get_text(sep, strip=strip) if el else ""
        except Exception:
            return ""

    def normalize_search_company_name(self, name: str) -> str:
        if not name:
            return ""

        value = str(name).strip()
        value = value.replace("(주)", "")
        value = value.replace("주식회사", "")
        value = value.strip()
        return value

    def is_owner_match(self, input_owner: str, scraped_owner: str) -> bool:
        input_owner = str(input_owner or "").strip()
        scraped_owner = str(scraped_owner or "").replace("*", "").strip()

        if not input_owner:
            return False

        return bool(scraped_owner and scraped_owner in input_owner)

    def is_blocked_html(self, html: str) -> bool:
        try:
            low = html.lower()
            for k in self._block_keywords:
                if k.lower() in low:
                    self.log_signal_func(f"🚫 차단 키워드 감지: {k}")
                    return True

            if len(html) < 1200:
                self.log_signal_func(f"🚫 차단 의심 (HTML 길이 짧음): {len(html)}")
                return True

        except Exception:
            return False

        return False

    def is_hard_stop_message(self, message: Any) -> bool:
        text = str(message or "").strip()
        if not text:
            return False

        low = text.lower()
        for keyword in self._hard_stop_keywords:
            if keyword.lower() in low:
                return True

        return False

    def request_force_stop(self, reason: str) -> None:
        if self._force_stop_requested:
            return

        self._force_stop_requested = True
        self._force_stop_reason = str(reason or "").strip()
        self.running = False

        self.log_signal_func(f"🛑 당일 운영 중단: {self._force_stop_reason}")

    def get_html(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"🌐 GET: {url}")
        html = self.api_client.get(url, headers=headers)
        return html

    def request_bizno_search_and_detail_api(
            self,
            company_name: str,
            owner_name: str,
            trace_headers: Optional[Dict[str, str]] = None
    ) -> Response:
        if not self.session:
            raise RuntimeError("session 없음")

        target_url = self.bizno_search_and_detail_url

        self.log_signal_func(
            f"[api-search-and-detail] 요청 시작: "
            f"url={target_url}, company_name={company_name}, owner_name={owner_name}"
        )

        payload: Dict[str, Any] = {
            "companyName": company_name,
            "ownerName": owner_name,
        }

        if self.api_user_id:
            payload["userId"] = self.api_user_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.api_user_id:
            headers["X-USER-ID"] = self.api_user_id

        if trace_headers:
            headers.update(trace_headers)

        resp = self.session.get(
            target_url,
            params=payload,
            headers=headers,
            timeout=(5, 30),
        )
        return resp

    def _loads_if_needed(self, value: Any) -> Dict[str, Any]:
        text = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value).strip()
        if not text:
            return {}

        try:
            return json.loads(text)
        except Exception:
            self.log_signal_func(f"[JSON 파싱 실패] 앞부분: {text[:200]}")
            return {}

    def is_api_error_response(self, res: Dict[str, Any]) -> bool:
        return int(res.get("error", 0) or 0) == 1

    def extract_search_and_detail_api_result(self, res: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {
            "success": bool(res.get("success")),
            "message": str(res.get("message") or ""),
            "article": "",
            "회사명": "",
            "url": "",
            "data": {},
        }

        blocks: List[Dict[str, Any]] = []

        if isinstance(res, dict):
            blocks.append(res)

        data_block = res.get("data")
        if isinstance(data_block, dict):
            blocks.append(data_block)

        result_block = res.get("result")
        if isinstance(result_block, dict):
            blocks.append(result_block)

        for block in blocks:
            if not normalized["article"]:
                normalized["article"] = str(
                    block.get("article")
                    or block.get("ARTICLE")
                    or ""
                ).strip()

            if not normalized["회사명"]:
                normalized["회사명"] = str(
                    block.get("회사명")
                    or block.get("companyName")
                    or block.get("name")
                    or ""
                ).strip()

            if not normalized["url"]:
                normalized["url"] = str(
                    block.get("url")
                    or block.get("URL")
                    or ""
                ).strip()

        detail_candidates: List[Any] = []

        detail_candidates.append(res.get("detailData"))
        detail_candidates.append(res.get("detail"))
        detail_candidates.append(res.get("data"))

        if isinstance(data_block, dict):
            detail_candidates.append(data_block.get("detailData"))
            detail_candidates.append(data_block.get("detail"))
            detail_candidates.append(data_block.get("data"))

        if isinstance(result_block, dict):
            detail_candidates.append(result_block.get("detailData"))
            detail_candidates.append(result_block.get("detail"))
            detail_candidates.append(result_block.get("data"))

        for candidate in detail_candidates:
            if isinstance(candidate, dict) and candidate:
                normalized["data"] = candidate
                break

        # res["data"] 자체가 상세 데이터인 경우 처리
        if not normalized["data"] and isinstance(res.get("data"), dict):
            data_value = res.get("data") or {}
            wrapper_keys = {
                "success", "message", "article", "companyName", "회사명", "url",
                "detail", "detailData", "data", "error"
            }
            has_wrapper_key = False
            for k in data_value.keys():
                if str(k) in wrapper_keys:
                    has_wrapper_key = True
                    break

            if not has_wrapper_key:
                normalized["data"] = data_value

        return normalized

    def sleep_between_channel_attempts(self) -> None:
        sleep_t = random.uniform(
            self._between_channel_rest_range_sec[0],
            self._between_channel_rest_range_sec[1]
        )
        self.log_signal_func(f"🕒 채널 전환 후 대기: {sleep_t:.2f}s")
        self.sleep_s(sleep_t)

    def sleep_between_local_search_and_detail(self) -> bool:
        sleep_t = random.uniform(
            self._local_search_detail_gap_range_sec[0],
            self._local_search_detail_gap_range_sec[1]
        )
        self.log_signal_func(f"🕒 로컬 search -> detail 사이 대기: {sleep_t:.2f}s")
        return self.sleep_s(sleep_t)

    def handle_mode_fail(self, reason: str) -> None:
        current_mode = self.get_current_request_mode()
        self.log_signal_func(f"⚠️ 현재 채널 실패: mode={current_mode}, reason={reason}")

        if self._force_stop_requested:
            self.log_signal_func("⛔ 강제 종료 상태이므로 채널 전환 생략")
            return

        self.rotate_request_mode(reason=reason)

        if self._force_stop_requested:
            self.log_signal_func("⛔ 강제 종료 상태이므로 채널 전환 후 대기 생략")
            return

        self.sleep_between_channel_attempts()

    def complete_current_channel(self, reason: str) -> None:
        if self._force_stop_requested:
            return
        self.rotate_request_mode(reason=reason)

    def touch_request_trace(self, channel: Dict[str, Any]) -> None:
        self.attempt_no += 1
        self.request_trace_id = self.generate_trace_id("R")
        self.server_id = self.resolve_server_id(channel)

    # =========================
    # bizno: search + detail
    # =========================
    def fetch_search_and_detail(self, item: dict) -> bool:
        raw_company_name = (item.get("검색회사명") or "").strip()
        filtered_company_name = self.normalize_search_company_name(raw_company_name)
        owner = (item.get("검색대표자명") or "").strip()

        item["검색필터회사명"] = filtered_company_name
        item["article"] = ""

        self.start_request_flow(
            job_name="bizno_search_and_detail",
            item_key=f"{filtered_company_name}|{owner}"
        )

        if not self.ensure_current_request_channel_available():
            return False

        max_try = self.get_available_request_channel_count()

        if max_try <= 0:
            self.request_force_stop(
                f"오늘 사용 가능한 요청 채널 수가 0입니다. date={self._daily_limit_date_key}"
            )
            return False

        for attempt in range(max_try):
            if self._force_stop_requested:
                return False

            if not self.ensure_current_request_channel_available():
                return False

            channel = self.get_current_request_channel()
            mode = str(channel.get("mode") or "").strip()
            channel_name = self.channel_label(channel)

            self.log_signal_func(
                f"[search-and-detail] 시도 {attempt + 1}/{max_try}, "
                f"channel={channel_name}, company='{filtered_company_name}', owner='{owner}'"
            )

            try:
                if not self.wait_channel_gap_if_needed(channel):
                    self.log_signal_func("⛔ 채널 최소 간격 대기 중단 감지")
                    return False

                self.mark_channel_used(channel)

                if mode == "request":
                    self.touch_request_trace(channel)

                    search_url = f"https://bizno.net/?area=&query={quote(filtered_company_name)}"

                    search_headers = {
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                        "cache-control": "no-cache",
                        "pragma": "no-cache",
                        "referer": "https://bizno.net/",
                        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "same-origin",
                        "upgrade-insecure-requests": "1",
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                    }

                    html = self.get_html(search_url, headers=search_headers)

                    if not html:
                        self.log_signal_func("[search-and-detail][request] 빈 HTML 응답")
                        self.handle_mode_fail("local search empty html")
                        continue

                    if self.is_blocked_html(html):
                        self.disable_channel_for_today(channel, "local bizno search blocked")
                        self.handle_mode_fail("local search blocked")
                        continue

                    soup = BeautifulSoup(html, "html.parser")
                    hit = 0
                    matched = False

                    for d in soup.select(".details"):
                        hit += 1

                        biz_owner = self.safe_text(d.select_one("h5"), strip=True)
                        if not self.is_owner_match(owner, biz_owner):
                            continue

                        a_tag = d.select_one('a[href^="/article/"]')
                        if not a_tag:
                            continue

                        href = a_tag.get("href") or ""
                        if not href:
                            continue

                        item["article"] = href.split("/article/")[1]
                        item["회사명"] = self.safe_text(d.select_one("h4"), strip=True)
                        matched = True

                        self.log_signal_func(
                            f"[search-and-detail][request] ✅ search match found: "
                            f"회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )
                        break

                    if not matched:
                        self.log_signal_func(
                            f"[search-and-detail][request] 결과 스캔 완료. details_count={hit}, match=0"
                        )
                        self.complete_current_channel("search-and-detail request no-match")
                        return True

                    if not self.sleep_between_local_search_and_detail():
                        self.log_signal_func("⛔ 로컬 search/detail 사이 sleep 중단 감지")
                        return False

                    article = str(item.get("article") or "").strip()
                    detail_url = f"https://bizno.net/article/{article}"

                    detail_headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/145.0.0.0 Safari/537.36"
                        ),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Referer": "https://bizno.net/",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    }

                    detail_html = self.get_html(detail_url, headers=detail_headers)

                    if not detail_html:
                        self.log_signal_func("[search-and-detail][request] detail 빈 HTML 응답")
                        self.handle_mode_fail("local detail empty html")
                        continue

                    if self.is_blocked_html(detail_html):
                        self.disable_channel_for_today(channel, "local bizno detail blocked")
                        self.handle_mode_fail("local detail blocked")
                        continue

                    detail_soup = BeautifulSoup(detail_html, "html.parser")
                    table = detail_soup.select_one("table.table_guide01")
                    item["url"] = detail_url

                    if not table:
                        self.log_signal_func("[search-and-detail][request] detail table 없음")
                        self.handle_mode_fail("local detail table missing")
                        continue

                    row_cnt = 0
                    for tr in table.select("tr"):
                        th = tr.find("th")
                        td = tr.find("td")

                        key = self.safe_text(th, strip=True)
                        val = self.safe_text(td, sep="\n", strip=True)

                        if key:
                            item[key] = val
                            row_cnt += 1

                    self.log_signal_func(
                        f"[search-and-detail][request] ✅ search+detail 완료. row_count={row_cnt}"
                    )
                    self.complete_current_channel("search-and-detail request success")
                    return True

                if mode == "server":
                    trace_headers = self.build_request_trace_headers(
                        channel=channel
                    )

                    resp = self.request_bizno_search_and_detail_api(
                        filtered_company_name,
                        owner,
                        trace_headers=trace_headers,
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        message = str(res.get("message") or "").strip()

                        if self.is_hard_stop_message(message):
                            self.request_force_stop(
                                f"원격 서버 하드 차단/소진 감지: {message}"
                            )
                            return False

                        self.log_signal_func(
                            f"[search-and-detail][api] ❌ 서버 에러: {message}"
                        )
                        self.handle_mode_fail(
                            f"search-and-detail api error: {message}"
                        )
                        continue

                    normalized = self.extract_search_and_detail_api_result(res)
                    normalized_message = str(normalized.get("message") or res.get("message") or "").strip()

                    if self.is_hard_stop_message(normalized_message):
                        self.request_force_stop(
                            f"원격 서버 하드 차단/소진 감지: {normalized_message}"
                        )
                        return False

                    if normalized.get("success") and (
                            normalized.get("article")
                            or normalized.get("회사명")
                            or normalized.get("data")
                    ):
                        article = str(normalized.get("article") or "").strip()
                        company_name = str(normalized.get("회사명") or "").strip()
                        url = str(normalized.get("url") or "").strip()
                        data = normalized.get("data") or {}

                        if article:
                            item["article"] = article

                        if company_name:
                            item["회사명"] = company_name

                        if url:
                            item["url"] = url

                        row_cnt = 0
                        if isinstance(data, dict):
                            for key, val in data.items():
                                if key:
                                    item[str(key)] = str(val or "")
                                    row_cnt += 1

                        self.log_signal_func(
                            f"[search-and-detail][api] ✅ search+detail 완료. "
                            f"회사명='{item.get('회사명')}', article='{item.get('article')}', row_count={row_cnt}"
                        )

                        self.complete_current_channel("search-and-detail api success")
                        return True

                    self.log_signal_func(
                        f"[search-and-detail][api] ⚠️ 매칭 없음: {normalized_message}"
                    )
                    self.complete_current_channel("search-and-detail api no-match")
                    return True

                self.log_signal_func(f"[search-and-detail] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")
                continue

            except Exception as e:
                text = str(e)
                if self.is_hard_stop_message(text):
                    self.request_force_stop(f"예외 기반 하드 차단 감지: {text}")
                    return False

                self.log_signal_func(f"[search-and-detail][{channel_name}] ❌ 예외: {e}")
                self.handle_mode_fail(f"search-and-detail exception: {e}")
                continue

        self.log_signal_func("[search-and-detail] ❌ 모든 채널 시도했지만 실패")
        return True

    # =========================
    # trace helpers
    # =========================
    def generate_trace_id(self, prefix: str) -> str:
        return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S%f')}{uuid4().hex[:6].upper()}"

    def init_trace_context(self) -> None:
        current_channel = self.get_current_request_channel()

        self.program_trace_id = self.generate_trace_id("P")
        self.api_trace_id = self.generate_trace_id("A")
        self.request_trace_id = ""
        self.attempt_no = 0
        self.server_id = self.resolve_server_id(current_channel)
        self.job_name = ""
        self.item_key = ""

        self.log_signal_func(
            f"[trace] 초기화 완료: "
            f"program_trace_id={self.program_trace_id}, "
            f"api_trace_id={self.api_trace_id}, "
            f"server_id={self.server_id}"
        )

    def start_request_flow(self, job_name: str, item_key: str = "") -> None:
        self.job_name = str(job_name or "").strip()
        self.item_key = str(item_key or "").strip()
        self.attempt_no = 0
        self.request_trace_id = ""

        self.log_signal_func(
            f"[trace] 요청 흐름 시작: "
            f"job_name={self.job_name}, item_key={self.item_key}, "
            f"program_trace_id={self.program_trace_id}, api_trace_id={self.api_trace_id}"
        )

    def build_request_trace_headers(self, channel: Dict[str, Any]) -> Dict[str, str]:
        self.attempt_no += 1
        self.request_trace_id = self.generate_trace_id("R")
        self.server_id = self.resolve_server_id(channel)

        headers: Dict[str, str] = {
            "X-PROGRAM-TRACE-ID": self.program_trace_id,
            "X-API-TRACE-ID": self.api_trace_id,
            "X-REQUEST-TRACE-ID": self.request_trace_id,
            "X-ATTEMPT-NO": str(self.attempt_no),
            "X-SERVER-ID": self.server_id,
        }

        if self.api_user_id:
            headers["X-USER-ID"] = self.api_user_id

        if self.job_name:
            headers["X-JOB-NAME"] = self.job_name

        if self.item_key:
            headers["X-ITEM-KEY"] = self.encode_header_value(self.item_key)

        return headers

    def rotate_api_trace(self, reason: str = "") -> None:
        prev_api_trace_id = self.api_trace_id
        prev_server_id = self.server_id or "unknown"

        current_channel = self.get_current_request_channel()

        self.api_trace_id = self.generate_trace_id("A")
        self.request_trace_id = ""
        self.server_id = self.resolve_server_id(current_channel)

        self.log_signal_func(
            f"[trace] api_trace_id 변경: "
            f"{prev_api_trace_id} -> {self.api_trace_id}, "
            f"prev_server_id={prev_server_id}, "
            f"current_server_id={self.server_id}, "
            f"reason={reason}"
        )

    def encode_header_value(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return quote(text, safe="")