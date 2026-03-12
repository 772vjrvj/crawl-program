# src/workers/main/api_naver_place_url_all_set_worker.py
import json
import os
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup
from requests import Response, Session

from src.core.global_state import GlobalState
from src.utils.api_utils import APIClient
from src.utils.config import server_url
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiBiznoExcelSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.driver = None
        self.selenium_driver = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "BIZNO"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None

        self._cookie_ready: bool = False

        # 저장 하위 폴더
        self.out_dir: str = "output_bizno"

        # 대량 휴식/세션 운영 파라미터
        self._rest_every_n: int = 30
        self._rest_range_sec = (60.0, 120.0)

        self._long_rest_every_n: int = 200
        self._long_rest_range_sec = (120.0, 240.0)

        self._super_rest_every_n: int = 1000
        self._super_rest_range_sec = (600.0, 1200.0)

        self._cookie_refresh_every_n: int = 100

        # 선제 장기 휴식 (150건마다 5분)
        self._preemptive_rest_every_n: int = 150
        self._preemptive_rest_sec: int = 300

        # 500건마다 실패 기다리지 않고 채널 선회
        self._rotate_every_n: int = 500

        # 차단 누적 쿨다운
        self._block_hit_count: int = 0
        self._block_cooldown_step_sec: int = 300
        self._block_cooldown_max_sec: int = 7200
        self._block_total_wait_sec: int = 0

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
        self._request_modes: List[str] = ["selenium", "main_server"]
        self._request_mode_index: int = 0

        # === 신규 ===
        self._api_server_mode_map: Dict[str, Dict[str, str]] = {}


        state = GlobalState()
        self.api_user_id: str = state.get("user_id")
        self.session: Session = state.get("session")

        self.bizno_search_url: str = f"{server_url}/bizno/search"
        self.bizno_detail_url: str = f"{server_url}/bizno/detail"

        # === 신규 ===
        self.api_key_active_list_url: str = f"{server_url}/internal/api-key-info/active-list"

    # 초기화
    def init(self) -> bool:
        self.driver_set()

        # === 신규 ===
        self.load_active_api_server_modes()
        self.log_signal_func(f"요청 채널 목록 : {self._request_modes}")

        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func(f"크롤링 시작. 전체 수 {len(self.excel_data_list)}")

            folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            self.csv_filename = os.path.basename(
                self.file_driver.get_csv_filename(self.site_name)
            )

            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=folder_path,
                sub_dir=self.out_dir
            )

            self.log_signal_func(f"✅ CSV 생성: {self.csv_filename}")

            self.total_cnt = len(self.excel_data_list)

            # 쿠키 1회 세팅
            self.log_signal_func("쿠키 세팅을 진행합니다. (1회)")
            self.ensure_cookie()

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
                if self._rotate_every_n > 0 and index > 1 and ((index - 1) % self._rotate_every_n == 0):
                    prev_mode = self.get_current_request_mode()
                    next_mode = self.rotate_request_mode()
                    self.log_signal_func(
                        f"🔄 {self._rotate_every_n}건 도달로 선제 채널 변경: {prev_mode} -> {next_mode}"
                    )

                    if next_mode == "selenium":
                        self.log_signal_func("🔁 selenium 채널 복귀로 브라우저/쿠키 재정비")
                        if not self.restart_browser():
                            self.log_signal_func("⛔ 브라우저 재시작 실패. main 루프 종료")
                            return True
                        if not self.refresh_cookie():
                            self.log_signal_func("⛔ 쿠키 재발급 실패. main 루프 종료")
                            return True

                # selenium 채널에서만 주기적 쿠키 재발급
                if (
                        self.get_current_request_mode() == "selenium"
                        and self._cookie_refresh_every_n > 0
                        and (index % self._cookie_refresh_every_n == 0)
                ):
                    self.log_signal_func(f"🔁 쿠키 재발급 타이밍 도달 ({index}건). 쿠키 재세팅 진행")
                    if not self.refresh_cookie():
                        self.log_signal_func("⛔ 쿠키 재발급 중단 감지. main 루프 종료")
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
                    folder_path=folder_path,
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

        self.selenium_driver = SeleniumUtils(
            headless=False,
            log_func=self.log_signal_func
        )
        self.selenium_driver.set_capture_options(enabled=True, block_images=False)

        self.driver = self.selenium_driver.start_driver(1200)
        self.log_signal_func("✅ 드라이버 세팅 완료")

    def cleanup(self) -> None:
        self.log_signal_func("🧹 cleanup 시작")

        folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        try:
            if self.csv_filename and self.excel_driver:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.selenium_driver:
                self.log_signal_func("🔌 selenium_driver.quit 시작")
                self.selenium_driver.quit()
                self.log_signal_func("🔌 selenium_driver.quit 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] selenium_driver.quit 실패: {e}")

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
            return "selenium"

    def rotate_request_mode(self) -> str:
        prev_mode = self.get_current_request_mode()
        self._request_mode_index = (self._request_mode_index + 1) % len(self._request_modes)
        next_mode = self.get_current_request_mode()
        self.log_signal_func(f"🔁 요청 채널 변경: {prev_mode} -> {next_mode}")
        return next_mode

    # === 신규 ===
    def get_request_user_id(self) -> str:
        try:
            user_id = str(self.get_setting_value(self.setting, "user_id") or "").strip()
            if user_id:
                return user_id
        except Exception:
            pass
        return self.api_user_id

    # === 신규 ===
    def is_dynamic_api_server_mode(self, mode: str) -> bool:
        return str(mode or "").startswith("api_server::")

    # === 신규 ===
    def get_api_server_info_by_mode(self, mode: str) -> Dict[str, str]:
        return self._api_server_mode_map.get(mode, {})

    # === 신규 ===
    def load_active_api_server_modes(self) -> None:
        self.log_signal_func(f"[active-list] 요청 시작: {self.api_key_active_list_url}")

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

    def get_block_cooldown_sec(self) -> int:
        if self._block_hit_count <= 1:
            return 300
        if self._block_hit_count == 2:
            return 600
        return 1200

    def restart_browser(self) -> bool:
        try:
            self.log_signal_func("🔄 차단 후 브라우저 재시작 시작")

            try:
                if self.selenium_driver:
                    self.log_signal_func("🔌 기존 selenium_driver.quit 시작")
                    self.selenium_driver.quit()
                    self.log_signal_func("🔌 기존 selenium_driver.quit 완료")
            except Exception as e:
                self.log_signal_func(f"⚠️ 기존 selenium_driver.quit 실패: {e}")

            self.driver = None
            self.selenium_driver = None
            self._cookie_ready = False

            self.selenium_driver = SeleniumUtils(
                headless=False,
                log_func=self.log_signal_func
            )
            self.selenium_driver.set_capture_options(enabled=True, block_images=False)

            self.driver = self.selenium_driver.start_driver(1200)
            self.log_signal_func("✅ 차단 후 브라우저 재시작 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ restart_browser 실패: {e}")
            return False

    def backoff_and_refresh_if_blocked(self, url: str, html: str) -> bool:
        if not self.is_blocked_html(html):
            return True

        self._block_hit_count += 1

        cooldown_sec = self.get_block_cooldown_sec()
        self._block_total_wait_sec += cooldown_sec

        cooldown_min = cooldown_sec // 60
        total_wait_min = self._block_total_wait_sec // 60

        self.log_signal_func(f"⚠️ 차단/제한 의심 페이지 감지: {url}")
        self.log_signal_func(
            f"🕒 차단 의심 쿨다운: {cooldown_min}분 "
            f"(누적 차단 {self._block_hit_count}회, 총 대기 {total_wait_min}분)"
        )

        try:
            if self.selenium_driver:
                self.log_signal_func("🛑 차단 감지로 브라우저 종료 시작")
                self.selenium_driver.quit()
                self.log_signal_func("🛑 차단 감지로 브라우저 종료 완료")
        except Exception as e:
            self.log_signal_func(f"⚠️ 차단 후 브라우저 종료 실패: {e}")

        self.driver = None
        self.selenium_driver = None
        self._cookie_ready = False

        if not self.sleep_s(cooldown_sec):
            self.log_signal_func("⛔ 차단 쿨다운 중단 감지")
            return False

        self.log_signal_func("🔄 차단 대기 후 브라우저 재시작 시도")
        if not self.restart_browser():
            return False

        self.log_signal_func("🔁 차단 의심으로 쿠키 재발급 시도")
        if not self.refresh_cookie():
            return False

        return True

    def ensure_cookie(self) -> None:
        if self._cookie_ready:
            self.log_signal_func("✅ 쿠키 이미 세팅됨 (skip)")
            return

        if not self.driver:
            self.log_signal_func("⚠️ driver 없음. 쿠키 세팅 skip")
            return

        self.log_signal_func("🌐 쿠키 세팅을 위해 메인 페이지 접속: https://bizno.net/")
        self.driver.get("https://bizno.net/")

        self.log_signal_func("쿠키 대기 전 잠시 쉽니다. (2.00s)")
        if not self.sleep_s(2.0):
            self.log_signal_func("⛔ cookie sleep 중단 감지")
            return

    def refresh_cookie(self) -> bool:
        try:
            self._cookie_ready = False
            self.ensure_cookie()
            if not self.running:
                return False
        except Exception as e:
            self.log_signal_func(f"❌ refresh_cookie 실패: {e}")
            return False
        return True

    def get_html_by_selenium(self, url: str, headers: dict) -> str:
        if not self.driver:
            return ""
        self.driver.get(url)
        wait_sec = random.uniform(3.0, 5.0)
        self.log_signal_func(f"[selenium] 페이지 로딩 후 대기 ({wait_sec:.2f}s)")
        if not self.sleep_s(wait_sec):
            return ""
        return self.driver.page_source or ""

    def request_bizno_search_api(
            self,
            company_name: str,
            owner_name: str,
            base_url: Optional[str] = None,
            api_key: Optional[str] = None,
            user_id: Optional[str] = None
    ) -> Response:
        target_url = f"{str(base_url or '').rstrip('/')}/bizno/search" if base_url else self.bizno_search_url

        self.log_signal_func(
            f"[api-search] 요청 시작: url={target_url}, company_name={company_name}, owner_name={owner_name}"
        )

        payload: Dict[str, Any] = {
            "companyName": company_name,
            "ownerName": owner_name,
        }

        # === 신규 ===
        if user_id:
            payload["userId"] = user_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # === 신규 ===
        if api_key:
            headers["X-API-KEY"] = api_key

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
            user_id: Optional[str] = None
    ) -> Response:
        target_url = f"{str(base_url or '').rstrip('/')}/bizno/detail" if base_url else self.bizno_detail_url

        self.log_signal_func(f"[api-detail] 요청 시작: url={target_url}, article={article}")

        payload: Dict[str, Any] = {
            "article": article,
        }

        # === 신규 ===
        if user_id:
            payload["userId"] = user_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # === 신규 ===
        if api_key:
            headers["X-API-KEY"] = api_key

        resp = self.session.get(
            target_url,
            params=payload,
            headers=headers,
            timeout=(5, 30),  # connect 5초, read 30초
        )
        return resp

    def get_html_by_api(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"[api] 요청 시작: {url}")
        raise NotImplementedError("API 서버 연동 로직을 여기에 구현하세요.")

    def get_html_by_proxy(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"[proxy] 요청 시작: {url}")
        raise NotImplementedError("프록시 서버 연동 로직을 여기에 구현하세요.")

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

    def sleep_after_mode_fail(self) -> bool:
        sleep_t = random.uniform(2.0, 5.0)
        self.log_signal_func(f"🕒 채널 전환 후 대기: {sleep_t:.2f}s")
        return self.sleep_s(sleep_t)

    # === 신규 ===
    def handle_mode_fail(self, reason: str) -> None:
        current_mode = self.get_current_request_mode()
        self.log_signal_func(f"⚠️ 현재 채널 실패: mode={current_mode}, reason={reason}")

        next_mode = self.rotate_request_mode()

        if next_mode == "selenium":
            self.log_signal_func("🔁 다음 채널이 selenium 이므로 브라우저/쿠키 재정비 시도")
            if not self.restart_browser():
                self.log_signal_func("❌ 브라우저 재시작 실패")
                return
            if not self.refresh_cookie():
                self.log_signal_func("❌ 쿠키 재발급 실패")
                return

        self.sleep_after_mode_fail()

    # =========================
    # bizno: search
    # =========================
    def fetch_search_results(self, item: dict) -> None:
        raw_company_name = (item.get("검색회사명") or "").strip()
        filtered_company_name = self.normalize_search_company_name(raw_company_name)
        owner = (item.get("검색대표자명") or "").strip()

        item["검색필터회사명"] = filtered_company_name
        item["article"] = ""

        max_try = len(self._request_modes)

        for attempt in range(max_try):
            mode = self.get_current_request_mode()
            self.log_signal_func(f"[search] 시도 {attempt + 1}/{max_try}, mode={mode}, company='{filtered_company_name}', owner='{owner}'")


            try:
                if mode == "selenium":
                    url = f"https://bizno.net/?area=&query={quote(filtered_company_name)}"
                    self.log_signal_func(f"[search][selenium] url={url}")

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

                    html = self.get_html_by_selenium(url, headers=headers)
                    if not html or self.is_blocked_html(html):
                        self.log_signal_func("[search][selenium] ❌ 실패/차단")
                        self.handle_mode_fail("search selenium fail/blocked")
                        return

                    soup = BeautifulSoup(html, "html.parser")
                    hit = 0

                    for d in soup.select(".details"):
                        hit += 1
                        if self.safe_text(d.select_one("h5"), strip=True) != owner:
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
                            f"[search][selenium] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )
                        return

                    self.log_signal_func(f"[search][selenium] 결과 스캔 완료. details_count={hit}, match=0")
                    return

                if mode == "main_server":
                    resp = self.request_bizno_search_api(filtered_company_name, owner)
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(f"[search][api] ❌ 서버 에러: {res.get('message')}")
                        self.handle_mode_fail(f"search api error: {res.get('message')}")
                        return

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
                    user_id = self.get_request_user_id()

                    if not server_base_url or not server_api_key:
                        self.log_signal_func(f"[search][{mode}] ❌ 서버 정보 없음")
                        self.handle_mode_fail(f"search dynamic api server info missing: {mode}")
                        return

                    resp = self.request_bizno_search_api(
                        filtered_company_name,
                        owner,
                        base_url=server_base_url,
                        api_key=server_api_key,
                        user_id=user_id
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(
                            f"[search][{server_id}] ❌ 서버 에러: {res.get('message')}"
                        )
                        self.handle_mode_fail(f"search dynamic api error [{server_id}]: {res.get('message')}")
                        return

                    if res.get("success") and res.get("article"):
                        item["article"] = str(res.get("article") or "").strip()
                        item["회사명"] = str(res.get("회사명") or "").strip()
                        self.log_signal_func(
                            f"[search][{server_id}] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                        )
                        return

                    self.log_signal_func(f"[search][{server_id}] ⚠️ 매칭 없음: {res.get('message')}")
                    return

                if mode == "api2":
                    self.log_signal_func("[api2] ❌ 미구현 -> 다음 채널로 회전")
                    return

                self.log_signal_func(f"[search] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")

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

        max_try = len(self._request_modes)

        for attempt in range(max_try):
            mode = self.get_current_request_mode()
            self.log_signal_func(f"[detail] 시도 {attempt + 1}/{max_try}, mode={mode}, article={article}")


            try:
                if mode == "selenium":
                    url = f"https://bizno.net/article/{article}"
                    self.log_signal_func(f"[detail][selenium] article : {article}")

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

                    html = self.get_html_by_selenium(url, headers=headers)
                    if not html or self.is_blocked_html(html):
                        self.log_signal_func("[detail][selenium] ❌ 실패/차단")
                        self.handle_mode_fail("detail selenium fail/blocked")
                        return

                    soup = BeautifulSoup(html, "html.parser")
                    table = soup.select_one("table.table_guide01")
                    item["url"] = url

                    if not table:
                        self.log_signal_func("[detail][selenium] ❌ table.table_guide01 없음")
                        self.handle_mode_fail("detail selenium table missing")
                        return

                    row_cnt = 0
                    for tr in table.select("tr"):
                        th = tr.find("th")
                        td = tr.find("td")

                        key = self.safe_text(th, strip=True)
                        val = self.safe_text(td, sep="\n", strip=True)

                        if key:
                            item[key] = val
                            row_cnt += 1

                    self.log_signal_func(f"[detail][selenium] ✅ 테이블 파싱 완료. row_count={row_cnt}")
                    return

                if mode == "main_server":
                    self.log_signal_func(f"[detail][main_server] article : {article}")
                    resp = self.request_bizno_detail_api(article)
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(f"[detail][api] ❌ 서버 에러: {res.get('message')}")
                        self.handle_mode_fail(f"detail api error: {res.get('message')}")
                        return

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
                    user_id = self.get_request_user_id()

                    if not server_base_url or not server_api_key:
                        self.log_signal_func(f"[detail][{mode}] ❌ 서버 정보 없음")
                        self.handle_mode_fail(f"detail dynamic api server info missing: {mode}")
                        return

                    resp = self.request_bizno_detail_api(
                        article,
                        base_url=server_base_url,
                        api_key=server_api_key,
                        user_id=user_id
                    )
                    res = self._loads_if_needed(resp.text)

                    if self.is_api_error_response(res):
                        self.log_signal_func(
                            f"[detail][{server_id}] ❌ 서버 에러: {res.get('message')}"
                        )
                        self.handle_mode_fail(f"detail dynamic api error [{server_id}]: {res.get('message')}")
                        return

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

                if mode == "api2":
                    self.log_signal_func("[detail][api2] ❌ 미구현 -> 다음 채널로 회전")
                    return

                self.log_signal_func(f"[detail] ❌ 알 수 없는 mode: {mode}")
                self.handle_mode_fail(f"unknown mode: {mode}")

            except Exception as e:
                self.log_signal_func(f"[detail][{mode}] ❌ 예외: {e}")
                self.handle_mode_fail(f"detail exception: {e}")
                continue

        self.log_signal_func(f"[detail] ❌ 모든 채널 시도했지만 실패. article={article}")