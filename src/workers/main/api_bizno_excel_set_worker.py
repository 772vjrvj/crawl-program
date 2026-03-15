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

        # 500건마다 실패 기다리지 않고 채널 선회
        self._rotate_every_n: int = 500

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

        # 현재 채널 유지 -> 실패 시 다음 채널로 회전
        self._request_modes: List[str] = ["request", "main_server"]
        self._request_mode_index: int = 0
        self._api_server_mode_map: Dict[str, Dict[str, str]] = {}
        state = GlobalState()
        self.api_user_id: str = state.get("user_id")
        self.session: Optional[Session] = state.get("session")
        self.bizno_search_url: str = f"{server_url}/bizno/search"
        self.bizno_detail_url: str = f"{server_url}/bizno/detail"
        self.api_key_active_list_url: str = f"{server_url}/internal/api-key-info/active-list"

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
        self.init_trace_context()

        self.load_active_api_server_modes()
        self.log_signal_func(f"요청 채널 목록 : {self._request_modes}")

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

                # 테스트 서버 (test server)용: 2건째부터 매 건마다 요청 채널 순환
                # if index > 1:
                #     prev_mode = self.get_current_request_mode()
                #     next_mode = self.rotate_request_mode()
                #     self.log_signal_func(f"🧪 테스트용 채널 변경: {prev_mode} -> {next_mode}")

                # 500건마다 선제 채널 변경
                if index > 1 and ((index - 1) % self._rotate_every_n == 0):
                    prev_mode = self.get_current_request_mode()
                    next_mode = self.rotate_request_mode()
                    self.log_signal_func(
                        f"🔄 {self._rotate_every_n}건 도달로 선제 채널 변경: {prev_mode} -> {next_mode}"
                    )

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

                # 검색 전 텀
                sleep1 = random.uniform(3.0, 6.0)
                self.log_signal_func(f"검색 전 잠시 쉽니다. ({sleep1:.2f}s)")
                if not self.sleep_s(sleep1):
                    self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                    return True

                self.log_signal_func("🔎 검색 결과 조회 시작")
                self.fetch_search_results(item)
                self.log_signal_func(f"item1 : {item}")

                if item.get("article"):
                    self.log_signal_func(f"✅ 검색 매칭 성공. article={item.get('article')}")

                    # 상세 전 텀
                    sleep2 = random.uniform(4.0, 8.0)
                    self.log_signal_func(f"상세 조회 전 잠시 쉽니다. ({sleep2:.2f}s)")
                    if not self.sleep_s(sleep2):
                        self.log_signal_func("⛔ sleep 중단 감지. main 루프 종료")
                        return True

                    self.log_signal_func("📄 상세 조회 시작")
                    self.fetch_article_detail(item)
                    self.log_signal_func("📄 상세 조회 완료")

                    # 상세 후 텀
                    sleep3 = random.uniform(5.0, 10.0)
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

                self.log_signal_func(f"현재 요청 채널 유지: {self.get_current_request_mode()}")
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

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

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
        time.sleep(2)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.log_signal_func("✅ destroy 시작")
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2)
        self.progress_end_signal.emit()
        self.log_signal_func("✅ progress_end_signal emit 완료")

    def get_current_request_mode(self) -> str:
        try:
            return self._request_modes[self._request_mode_index]
        except Exception:
            return "request"

    def rotate_request_mode(self, reason: str = "") -> str:
        prev_mode = self.get_current_request_mode()
        self._request_mode_index = (self._request_mode_index + 1) % len(self._request_modes)
        next_mode = self.get_current_request_mode()

        self.rotate_api_trace(reason or f"{prev_mode}->{next_mode}")

        self.log_signal_func(
            f"🔁 요청 채널 변경: {prev_mode} -> {next_mode}, "
            f"api_trace_id={self.api_trace_id}"
        )
        return next_mode

    def is_dynamic_api_server_mode(self, mode: str) -> bool:
        return str(mode or "").startswith("api_server::")

    def get_api_server_info_by_mode(self, mode: str) -> Dict[str, str]:
        return self._api_server_mode_map.get(mode, {})


    # api 목록 조회
    def load_active_api_server_modes(self) -> None:
        self.log_signal_func(f"[active-list] 요청 시작: {self.api_key_active_list_url}")

        if not self.session:
            self.log_signal_func("[active-list] ❌ session 없음")
            return

        try:
            headers = {
                "Accept": "application/json",
            }

            resp = self.session.get(
                self.api_key_active_list_url,
                headers=headers,
                timeout=(5, 30),  # connect 5초, read 30초
            )

            res = self._loads_if_needed(resp.text)

            if self.is_api_error_response(res):
                self.log_signal_func(f"[active-list] ❌ 서버 에러: {res.get('message')}")
                return

            if not res.get("success"):
                self.log_signal_func(f"[active-list] ❌ 조회 실패: {res.get('message')}")
                return

            server_list = res.get("list") or []
            added_count = 0

            for row in server_list:
                server_id = str(row.get("serverId") or "").strip()
                server_base_url = str(row.get("serverUrl") or "").strip().rstrip("/")
                server_api_key = str(row.get("serverApiKey") or "").strip()

                if not server_id or not server_base_url or not server_api_key:
                    self.log_signal_func(
                        f"[active-list] ⚠️ 서버 정보 누락으로 skip: "
                        f"serverId={server_id}, serverUrl={server_base_url}"
                    )
                    continue

                mode_name = f"api_server::{server_id}"

                self._api_server_mode_map[mode_name] = {
                    "serverId": server_id,
                    "serverUrl": server_base_url,
                    "serverApiKey": server_api_key,
                }

                if mode_name not in self._request_modes:
                    self._request_modes.append(mode_name)
                    added_count += 1

            self.log_signal_func(
                f"[active-list] ✅ 동적 API 서버 모드 추가 완료. "
                f"추가건수={added_count}, 전체모드={len(self._request_modes)}"
            )

        except Exception as e:
            self.log_signal_func(f"[active-list] ❌ 예외: {e}")

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
            if not html:
                return True

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

    def request_bizno_search_api(self,
            company_name: str,
            owner_name: str,
            base_url: Optional[str] = None,
            api_key: Optional[str] = None,
            trace_headers: Optional[Dict[str, str]] = None
    ) -> Response:
        if not self.session:
            raise RuntimeError("session 없음")

        target_url = f"{str(base_url or '').rstrip('/')}/bizno/search" if base_url else self.bizno_search_url

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

        if api_key:
            headers["X-API-KEY"] = api_key

        if self.api_user_id:
            headers["X-USER-ID"] = self.api_user_id

        if trace_headers:
            headers.update(trace_headers)

        resp = self.session.get(
            target_url,
            params=payload,
            headers=headers,
            timeout=(5, 30),  # connect 5초, read 30초
        )
        return resp

    def request_bizno_detail_api(
            self,
            article: str,
            base_url: Optional[str] = None,
            api_key: Optional[str] = None,
            user_id: Optional[str] = None,
            trace_headers: Optional[Dict[str, str]] = None
    ) -> Response:
        if not self.session:
            raise RuntimeError("session 없음")

        target_url = f"{str(base_url or '').rstrip('/')}/bizno/detail" if base_url else self.bizno_detail_url
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

        if api_key:
            headers["X-API-KEY"] = api_key

        if resolved_user_id:
            headers["X-USER-ID"] = resolved_user_id

        if trace_headers:
            headers.update(trace_headers)

        resp = self.session.get(
            target_url,
            params=payload,
            headers=headers,
            timeout=(5, 30),  # connect 5초, read 30초
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


    def touch_request_trace(self, mode: str) -> None:
        self.attempt_no += 1
        self.request_trace_id = self.generate_trace_id("R")
        self.server_id = self.resolve_server_id_by_mode(mode)

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

        max_try = len(self._request_modes)

        for attempt in range(max_try):
            mode = self.get_current_request_mode()
            self.log_signal_func(
                f"[search] 시도 {attempt + 1}/{max_try}, mode={mode}, company='{filtered_company_name}', owner='{owner}'"
            )

            try:
                if mode == "request":
                    self.touch_request_trace(mode)

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
                        return

                    self.log_signal_func(f"[search][request] 결과 스캔 완료. details_count={hit}, match=0")
                    return

                if mode == "main_server":
                    trace_headers = self.build_request_trace_headers(
                        mode=mode,
                        request_url=self.bizno_search_url
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
                        return

                    self.log_signal_func(f"[search][api] ⚠️ 매칭 없음: {res.get('message')}")
                    return

                if self.is_dynamic_api_server_mode(mode):
                    server_info = self.get_api_server_info_by_mode(mode)
                    server_id = str(server_info.get("serverId") or "").strip()
                    server_base_url = str(server_info.get("serverUrl") or "").strip()
                    server_api_key = str(server_info.get("serverApiKey") or "").strip()

                    if not server_base_url or not server_api_key:
                        self.log_signal_func(f"[search][{mode}] ❌ 서버 정보 없음")
                        self.handle_mode_fail(f"search dynamic api server info missing: {mode}")
                        continue

                    trace_headers = self.build_request_trace_headers(
                        mode=mode,
                        request_url=f"{server_base_url.rstrip('/')}/bizno/search"
                    )

                    resp = self.request_bizno_search_api(
                        filtered_company_name,
                        owner,
                        base_url=server_base_url,
                        api_key=server_api_key,
                        trace_headers=trace_headers
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(
                            f"[search][{server_id}] ❌ 서버 에러: {res.get('message')}"
                        )
                        self.handle_mode_fail(f"search dynamic api error [{server_id}]: {res.get('message')}")
                        continue

                    if res.get("success") and res.get("article"):
                        item["article"] = str(res.get("article") or "").strip()
                        item["회사명"] = str(res.get("회사명") or "").strip()
                        self.log_signal_func(
                            f"[search][{server_id}] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )
                        return

                    self.log_signal_func(f"[search][{server_id}] ⚠️ 매칭 없음: {res.get('message')}")
                    return

                self.log_signal_func(f"[search] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")
                continue

            except Exception as e:
                self.log_signal_func(f"[search][{mode}] ❌ 예외: {e}")
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

        max_try = len(self._request_modes)

        for attempt in range(max_try):
            mode = self.get_current_request_mode()
            self.log_signal_func(f"[detail] 시도 {attempt + 1}/{max_try}, mode={mode}, article={article}")

            try:
                if mode == "request":
                    self.touch_request_trace(mode)
                    url = f"https://bizno.net/article/{article}"

                    headers = {
                        "authority": "bizno.net",
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                        "accept-encoding": "gzip, deflate, br, zstd",
                        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                        "cache-control": "no-cache",
                        "pragma": "no-cache",
                        "priority": "u=0, i",
                        "referer": "https://bizno.net/",
                        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "same-origin",
                        "sec-fetch-user": "?1",
                        "upgrade-insecure-requests": "1",
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
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
                    return

                if mode == "main_server":
                    trace_headers = self.build_request_trace_headers(
                        mode=mode,
                        request_url=self.bizno_detail_url
                    )

                    self.log_signal_func(f"[detail][main_server] article : {article}")
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
                        return

                    self.log_signal_func(f"[detail][api] ⚠️ 상세 데이터 없음: {res.get('message')}")
                    return

                if self.is_dynamic_api_server_mode(mode):
                    self.log_signal_func(f"[detail][{mode}] article : {article}")
                    server_info = self.get_api_server_info_by_mode(mode)
                    server_id = str(server_info.get("serverId") or "").strip()
                    server_base_url = str(server_info.get("serverUrl") or "").strip()
                    server_api_key = str(server_info.get("serverApiKey") or "").strip()
                    user_id = self.api_user_id

                    if not server_base_url or not server_api_key:
                        self.log_signal_func(f"[detail][{mode}] ❌ 서버 정보 없음")
                        self.handle_mode_fail(f"detail dynamic api server info missing: {mode}")
                        continue

                    trace_headers = self.build_request_trace_headers(
                        mode=mode,
                        request_url=f"{server_base_url.rstrip('/')}/bizno/detail"
                    )

                    resp = self.request_bizno_detail_api(
                        article,
                        base_url=server_base_url,
                        api_key=server_api_key,
                        user_id=user_id,
                        trace_headers=trace_headers
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(
                            f"[detail][{server_id}] ❌ 서버 에러: {res.get('message')}"
                        )
                        self.handle_mode_fail(f"detail dynamic api error [{server_id}]: {res.get('message')}")
                        continue

                    if res.get("success"):
                        item["url"] = str(res.get("url") or "")
                        data = res.get("data") or {}

                        row_cnt = 0
                        for key, val in data.items():
                            if key:
                                item[str(key)] = str(val or "")
                                row_cnt += 1

                        self.log_signal_func(f"[detail][{server_id}] ✅ 테이블 반영 완료. row_count={row_cnt}")
                        return

                    self.log_signal_func(f"[detail][{server_id}] ⚠️ 상세 데이터 없음: {res.get('message')}")
                    return

                self.log_signal_func(f"[detail] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")
                continue

            except Exception as e:
                self.log_signal_func(f"[detail][{mode}] ❌ 예외: {e}")
                self.handle_mode_fail(f"detail exception: {e}")
                continue

        self.log_signal_func(f"[detail] ❌ 모든 채널 시도했지만 실패. article={article}")

    # =========================
    # trace helpers
    # =========================
    def generate_trace_id(self, prefix: str) -> str:
        return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S%f')}{uuid4().hex[:6].upper()}"

    def resolve_server_id_by_mode(self, mode: str) -> str:
        mode = str(mode or "").strip()

        if mode == "request":
            return "direct"

        if mode == "main_server":
            return "main"

        if self.is_dynamic_api_server_mode(mode):
            server_info = self.get_api_server_info_by_mode(mode)
            server_id = str(server_info.get("serverId") or "").strip()
            if server_id:
                return server_id
            return mode.replace("api_server::", "").strip() or "unknown"

        return mode or "unknown"

    def init_trace_context(self) -> None:

        self.program_trace_id = self.generate_trace_id("P")
        self.api_trace_id = self.generate_trace_id("A")
        self.request_trace_id = ""
        self.attempt_no = 0
        self.server_id = self.resolve_server_id_by_mode(self.get_current_request_mode())
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

    def build_request_trace_headers(self, mode: str, request_url: str = "") -> Dict[str, str]:
        self.attempt_no += 1
        self.request_trace_id = self.generate_trace_id("R")
        self.server_id = self.resolve_server_id_by_mode(mode)

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
            headers["X-ITEM-KEY"] = self.item_key

        return headers

    def rotate_api_trace(self, reason: str = "") -> None:
        prev_api_trace_id = self.api_trace_id
        prev_server_id = self.server_id or self.resolve_server_id_by_mode(self.get_current_request_mode())

        self.api_trace_id = self.generate_trace_id("A")
        self.request_trace_id = ""
        self.server_id = self.resolve_server_id_by_mode(self.get_current_request_mode())

        self.log_signal_func(
            f"[trace] api_trace_id 변경: "
            f"{prev_api_trace_id} -> {self.api_trace_id}, "
            f"prev_server_id={prev_server_id}, "
            f"current_server_id={self.server_id}, "
            f"reason={reason}"
        )