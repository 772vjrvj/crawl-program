# src/workers/main/api_bizno_excel_set_worker.py
import json
import os
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from datetime import datetime
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

        # 대량 휴식/세션 운영 파라미터
        self._rest_every_n: int = 30
        self._rest_range_sec = (60.0, 120.0)

        self._long_rest_every_n: int = 200
        self._long_rest_range_sec = (120.0, 240.0)

        self._super_rest_every_n: int = 1000
        self._super_rest_range_sec = (600.0, 1200.0)

        # 선제 장기 휴식 (150건마다 5분)
        self._preemptive_rest_every_n: int = 150
        self._preemptive_rest_sec: int = 300

        # === 변경 ===
        # 기존 2000건마다 채널 선회는 라운드로빈 분산으로 대체
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

        # === 변경 ===
        # request + active server 들을 라운드로빈으로 순환
        self._request_channels: List[Dict[str, Any]] = []
        self._request_mode_index: int = 0

        state = GlobalState()
        self.api_user_id: str = state.get("user_id")
        self.session: Optional[Session] = state.get("session")

        self.bizno_search_url: str = f"{server_url}/bizno/search"
        self.bizno_detail_url: str = f"{server_url}/bizno/detail"
        self.active_list_url: str = f"{server_url}/internal/api-key-info/active-list"

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

        self.log_signal_func(
            f"요청 채널 목록 : {[self.channel_label(ch) for ch in self._request_channels]}"
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

                # === 변경 ===
                # 기존보다 전체적으로 5~10초 정도 더 늘린 대기
                sleep1 = random.uniform(5.0, 8.0)
                self.log_signal_func(f"검색 전 잠시 쉽니다. ({sleep1:.2f}s)")
                if not self.sleep_s(sleep1):
                    self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                    return True

                self.log_signal_func("🔎 검색 결과 조회 시작")
                self.fetch_search_results(item)
                self.log_signal_func(f"item1 : {item}")

                if item.get("article"):
                    self.log_signal_func(f"✅ 검색 매칭 성공. article={item.get('article')}")

                    sleep2 = random.uniform(6.0, 10.0)
                    self.log_signal_func(f"상세 조회 전 잠시 쉽니다. ({sleep2:.2f}s)")
                    if not self.sleep_s(sleep2):
                        self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                        return True

                    self.log_signal_func("📄 상세 조회 시작")
                    self.fetch_article_detail(item)
                    self.log_signal_func("📄 상세 조회 완료")

                    sleep3 = random.uniform(8.0, 12.0)
                    self.log_signal_func(f"상세 조회 후 잠시 쉽니다. ({sleep3:.2f}s)")
                    if not self.sleep_s(sleep3):
                        self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                        return True
                else:
                    self.log_signal_func("⚠️ 검색 매칭 실패. article 없음")

                self.log_signal_func(f"item2 : {item}")

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
                self.file_driver.close()
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
            "label": "request",
            "server_id": "direct",
            "base_url": "",
            "api_key": "",
        }

    def build_fallback_server_channel(self) -> Dict[str, Any]:
        return {
            "mode": "server",
            "type": "server",
            "label": "main_server",
            "server_id": "main",
            "base_url": self.normalize_base_url(server_url),
            "api_key": "",
        }

    def request_active_server_list(self) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("session 없음(active-list 조회 불가)")

        headers = {
            "Accept": "application/json",
        }

        if self.api_user_id:
            headers["X-USER-ID"] = self.api_user_id

        self.log_signal_func(f"[channel] active-list 조회 시작: {self.active_list_url}")

        resp = self.session.get(
            self.active_list_url,
            headers=headers,
            timeout=(5, 30),
        )

        self.log_signal_func(
            f"[channel] active-list 응답: status={getattr(resp, 'status_code', 'unknown')}"
        )

        return self._loads_if_needed(resp.text)


    def extract_active_server_items(self, payload: Any) -> List[Dict[str, Any]]:
        def find_list(value: Any) -> List[Any]:
            if isinstance(value, list):
                return value
            if not isinstance(value, dict):
                return []

            for key in ["list", "rows", "items", "activeList", "data", "result"]:
                child = value.get(key)
                if isinstance(child, list):
                    return child
                if isinstance(child, dict):
                    found = find_list(child)
                    if found:
                        return found
            return []

        raw_items = find_list(payload)
        result: List[Dict[str, Any]] = []

        for idx, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                continue

            use_yn = str(
                raw.get("useYn")
                or raw.get("use_yn")
                or raw.get("USE_YN")
                or "Y"
            ).strip().upper()

            if use_yn == "N":
                continue

            server_id_value = str(
                raw.get("serverId")
                or raw.get("server_id")
                or raw.get("SERVER_ID")
                or f"main_server_{idx}"
            ).strip()

            result.append({
                "mode": "server",
                "type": "server",
                "label": server_id_value,
                "server_id": server_id_value,
            })

        return result


    def load_request_channels(self) -> None:
        channels: List[Dict[str, Any]] = [self.build_direct_channel()]

        try:
            payload = self.request_active_server_list()
            active_servers = self.extract_active_server_items(payload)

            self.log_signal_func(f"[channel] active server count={len(active_servers)}")

            if active_servers:
                channels.extend(active_servers)
            else:
                self.log_signal_func("[channel] active server 없음. fallback main_server 사용")
                channels.append(self.build_fallback_server_channel())

        except Exception as e:
            self.log_signal_func(f"[channel] active-list 조회 실패: {e}")
            self.log_signal_func("[channel] fallback main_server 채널 사용")
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

    def get_request_channel_count(self) -> int:
        if not self._request_channels:
            return 1
        return len(self._request_channels)

    def resolve_server_id(self, channel: Optional[Dict[str, Any]] = None) -> str:
        ch = channel or self.get_current_request_channel()
        return str(ch.get("server_id") or ch.get("label") or ch.get("mode") or "unknown").strip()

    def rotate_request_mode(self, reason: str = "") -> str:
        prev_channel = self.get_current_request_channel()
        prev_mode = self.channel_label(prev_channel)

        if self._request_channels:
            self._request_mode_index = (self._request_mode_index + 1) % len(self._request_channels)

        next_channel = self.get_current_request_channel()
        next_mode = self.channel_label(next_channel)

        self.rotate_api_trace(reason or f"{prev_mode}->{next_mode}")

        self.log_signal_func(
            f"🔁 요청 채널 변경: {prev_mode} -> {next_mode}, "
            f"api_trace_id={self.api_trace_id}"
        )
        return next_mode

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
        return bool(input_owner and scraped_owner and scraped_owner in input_owner)

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

    def get_html(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"🌐 GET: {url}")
        html = self.api_client.get(url, headers=headers)
        return html

    def request_bizno_search_api(
            self,
            company_name: str,
            owner_name: str,
            trace_headers: Optional[Dict[str, str]] = None
    ) -> Response:
        if not self.session:
            raise RuntimeError("session 없음")

        target_url = self.bizno_search_url

        self.log_signal_func(
            f"[api-search] 요청 시작: url={target_url}, company_name={company_name}, owner_name={owner_name}"
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

    def request_bizno_detail_api(
            self,
            article: str,
            user_id: Optional[str] = None,
            trace_headers: Optional[Dict[str, str]] = None
    ) -> Response:
        if not self.session:
            raise RuntimeError("session 없음")

        target_url = self.bizno_detail_url
        resolved_user_id = str(user_id or self.api_user_id or "").strip()

        self.log_signal_func(f"[api-detail] 요청 시작: url={target_url}, article={article}")

        payload: Dict[str, Any] = {
            "article": article,
        }

        if resolved_user_id:
            payload["userId"] = resolved_user_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if resolved_user_id:
            headers["X-USER-ID"] = resolved_user_id

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

    def sleep_after_mode_fail(self) -> None:
        sleep_t = random.uniform(2.0, 5.0)
        self.log_signal_func(f"🕒 채널 전환 후 대기: {sleep_t:.2f}s")
        self.sleep_s(sleep_t)

    def handle_mode_fail(self, reason: str) -> None:
        current_mode = self.get_current_request_mode()
        self.log_signal_func(f"⚠️ 현재 채널 실패: mode={current_mode}, reason={reason}")

        self.rotate_request_mode(reason=reason)
        self.sleep_after_mode_fail()

    def complete_current_channel(self, reason: str) -> None:
        self.rotate_request_mode(reason=reason)

    def touch_request_trace(self, channel: Dict[str, Any]) -> None:
        self.attempt_no += 1
        self.request_trace_id = self.generate_trace_id("R")
        self.server_id = self.resolve_server_id(channel)

    # =========================
    # bizno: search
    # =========================
    def fetch_search_results(self, item: dict) -> None:
        raw_company_name = (item.get("검색회사명") or "").strip()
        filtered_company_name = self.normalize_search_company_name(raw_company_name)
        owner = (item.get("검색대표자명") or "").strip()

        item["검색필터회사명"] = filtered_company_name
        item["article"] = ""

        self.start_request_flow(
            job_name="bizno_search",
            item_key=f"{filtered_company_name}|{owner}"
        )

        max_try = self.get_request_channel_count()

        for attempt in range(max_try):
            channel = self.get_current_request_channel()
            mode = str(channel.get("mode") or "").strip()
            channel_name = self.channel_label(channel)

            self.log_signal_func(
                f"[search] 시도 {attempt + 1}/{max_try}, channel={channel_name}, "
                f"company='{filtered_company_name}', owner='{owner}'"
            )

            try:
                if mode == "request":
                    self.touch_request_trace(channel)

                    url = f"https://bizno.net/?area=&query={quote(filtered_company_name)}"

                    headers = {
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

                    html = self.get_html(url, headers=headers)

                    if not html or self.is_blocked_html(html):
                        self.log_signal_func("[search][request] ❌ 실패/차단")
                        self.handle_mode_fail("search request fail/blocked")
                        continue

                    soup = BeautifulSoup(html, "html.parser")
                    hit = 0

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

                        self.log_signal_func(
                            f"[search][request] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )

                        self.complete_current_channel("search request success")
                        return

                    self.log_signal_func(f"[search][request] 결과 스캔 완료. details_count={hit}, match=0")
                    self.complete_current_channel("search request no-match")
                    return

                if mode == "server":
                    trace_headers = self.build_request_trace_headers(
                        channel=channel
                    )

                    resp = self.request_bizno_search_api(
                        filtered_company_name,
                        owner,
                        trace_headers=trace_headers,
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(f"[search][api] ❌ 서버 에러: {res.get('message')}")
                        self.handle_mode_fail(f"search api error: {res.get('message')}")
                        continue

                    if res.get("success") and res.get("article"):
                        item["article"] = str(res.get("article") or "").strip()
                        item["회사명"] = str(res.get("회사명") or "").strip()

                        self.log_signal_func(
                            f"[search][api] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )

                        self.complete_current_channel("search api success")
                        return

                    self.log_signal_func(f"[search][api] ⚠️ 매칭 없음: {res.get('message')}")
                    self.complete_current_channel("search api no-match")
                    return

                self.log_signal_func(f"[search] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")
                continue

            except Exception as e:
                self.log_signal_func(f"[search][{channel_name}] ❌ 예외: {e}")
                self.handle_mode_fail(f"search exception: {e}")
                continue

        self.log_signal_func("[search] ❌ 모든 채널 시도했지만 실패")

    # =========================
    # bizno: detail
    # =========================
    def fetch_article_detail(self, item: dict) -> None:
        article = str(item.get("article") or "").strip()
        if not article:
            self.log_signal_func("[detail] ⚠️ article 없음")
            return

        self.start_request_flow(
            job_name="bizno_detail",
            item_key=article
        )

        max_try = self.get_request_channel_count()

        for attempt in range(max_try):
            channel = self.get_current_request_channel()
            mode = str(channel.get("mode") or "").strip()
            channel_name = self.channel_label(channel)

            self.log_signal_func(
                f"[detail] 시도 {attempt + 1}/{max_try}, channel={channel_name}, article={article}"
            )

            try:
                if mode == "request":
                    self.touch_request_trace(channel)
                    url = f"https://bizno.net/article/{article}"

                    headers = {
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

                    html = self.get_html(url, headers=headers)

                    if not html or self.is_blocked_html(html):
                        self.log_signal_func("[detail][request] ❌ 실패/차단")
                        self.handle_mode_fail("detail request fail/blocked")
                        continue

                    soup = BeautifulSoup(html, "html.parser")
                    table = soup.select_one("table.table_guide01")
                    item["url"] = url

                    if not table:
                        self.log_signal_func("[detail][request] ❌ table.table_guide01 없음")
                        self.handle_mode_fail("detail request table missing")
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

                    self.log_signal_func(f"[detail][request] ✅ 테이블 파싱 완료. row_count={row_cnt}")
                    self.complete_current_channel("detail request success")
                    return

                if mode == "server":
                    trace_headers = self.build_request_trace_headers(
                        channel=channel
                    )

                    self.log_signal_func(f"[detail][server] article : {article}")
                    resp = self.request_bizno_detail_api(
                        article,
                        trace_headers=trace_headers
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(f"[detail][api] ❌ 서버 에러: {res.get('message')}")
                        self.handle_mode_fail(f"detail api error: {res.get('message')}")
                        continue

                    if res.get("success"):
                        item["url"] = str(res.get("url") or "")
                        data = res.get("data") or {}

                        row_cnt = 0
                        for key, val in data.items():
                            if key:
                                item[str(key)] = str(val or "")
                                row_cnt += 1

                        self.log_signal_func(f"[detail][api] ✅ 테이블 반영 완료. row_count={row_cnt}")
                        self.complete_current_channel("detail api success")
                        return

                    self.log_signal_func(f"[detail][api] ⚠️ 상세 데이터 없음: {res.get('message')}")
                    self.complete_current_channel("detail api no-data")
                    return

                self.log_signal_func(f"[detail] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")
                continue

            except Exception as e:
                self.log_signal_func(f"[detail][{channel_name}] ❌ 예외: {e}")
                self.handle_mode_fail(f"detail exception: {e}")
                continue

        self.log_signal_func(f"[detail] ❌ 모든 채널 시도했지만 실패. article={article}")

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