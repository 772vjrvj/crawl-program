# src/workers/main/api_naver_place_url_all_set_worker.py
import os
import random
import time
from typing import Any, Dict,List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup
import json
from src.core.global_state import GlobalState
from requests import Session, Response
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
from src.utils.config import server_url

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
        self.api_client: Optional[APIClient] = None

        self._cookie_ready: bool = False
        self._cache: dict[str, str] = {}

        # 저장 하위 폴더
        self.out_dir: str = "output_bizno"

        # 대량 휴식/세션 운영 파라미터
        self._rest_every_n: int = 30
        self._rest_range_sec = (60.0, 120.0)

        self._long_rest_every_n: int = 200
        self._long_rest_range_sec = (120.0, 240.0)

        self._super_rest_every_n: int = 1000
        self._super_rest_range_sec = (600.0, 1200.0)

        self._cookie_refresh_every_n: int = 500  # 쿠키 재발급 주기(권장)

        # 선제 장기 휴식 (150건마다 5분)
        self._preemptive_rest_every_n: int = 150
        self._preemptive_rest_sec: int = 300

        # 차단 누적 쿨다운 (5분 -> 10분 -> 20분)
        self._block_hit_count: int = 0
        self._block_cooldown_step_sec: int = 300   # 5분
        self._block_cooldown_max_sec: int = 7200   # 120분
        self._block_total_wait_sec: int = 0        # 누적 대기시간 로그용

        # 간단 차단 감지 키워드(사이트가 바뀌어도 크게 무리 없는 수준)
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

        # 순환형 요청 채널
        self._request_modes: List[str] = ["api", "selenium"]
        self._request_mode_index: int = 0

        state = GlobalState()
        self.session: Session = state.get("session")


        self.bizno_search_url: str = f"{server_url}/bizno/search"
        self.bizno_detail_url: str = f"{server_url}/bizno/detail"

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func(f"크롤링 시작. 전체 수 {len(self.excel_data_list)}")

            folder_path: str = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

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

                # 주기적 쿠키 재발급 (세션/쿠키 기반 차단 대비)
                if self._cookie_refresh_every_n > 0 and (index % self._cookie_refresh_every_n == 0):
                    self.log_signal_func(f"🔁 쿠키 재발급 타이밍 도달 ({index}건). 쿠키 재세팅 진행")
                    if not self.refresh_cookie():
                        self.log_signal_func("⛔ 쿠키 재발급 중단 감지. main 루프 종료")
                        return True

                # 진행 로그
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

                # 선제 장기 휴식 (150건마다 5분)
                if self._preemptive_rest_every_n > 0 and (index % self._preemptive_rest_every_n == 0):
                    self.log_signal_func(
                        f"🕒 선제 장기 휴식 ({self._preemptive_rest_every_n}건마다): "
                        f"{self._preemptive_rest_sec // 60}분"
                    )
                    if not self.sleep_s(self._preemptive_rest_sec):
                        self.log_signal_func("⛔ 선제 장기 휴식 중단 감지. main 루프 종료")
                        return True

                # 대량 요청 방지 휴식(패턴 분산)
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

        # 셀레니움 로그도 UI로 전달
        self.selenium_driver = SeleniumUtils(
            headless=False,
            log_func=self.log_signal_func
        )
        self.selenium_driver.set_capture_options(enabled=True, block_images=False)

        self.driver = self.selenium_driver.start_driver(1200)
        self.log_signal_func("✅ 드라이버 세팅 완료")


    def cleanup(self) -> None:
        self.log_signal_func("🧹 cleanup 시작")

        folder_path: str = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

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

        # === 신규 === selenium 종료
        try:
            if self.selenium_driver:
                self.log_signal_func("🔌 selenium_driver.quit 시작")
                self.selenium_driver.quit()
                self.log_signal_func("🔌 selenium_driver.quit 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] selenium_driver.quit 실패: {e}")

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
            return "selenium"


    def rotate_request_mode(self) -> str:
        self._request_mode_index = (self._request_mode_index + 1) % len(self._request_modes)
        next_mode = self.get_current_request_mode()
        self.log_signal_func(f"🔁 요청 채널 변경: {next_mode}")
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

    # 차단 의심 감지
    def is_blocked_html(self, html: str) -> bool:
        try:
            if not html:
                return True

            low = html.lower()

            for k in self._block_keywords:
                if k.lower() in low:
                    # 실제 차단 키워드 로그
                    self.log_signal_func(f"🚫 차단 키워드 감지: {k}")
                    return True

            if len(html) < 1200:
                # HTML 길이 기반 차단 로그
                self.log_signal_func(f"🚫 차단 의심 (HTML 길이 짧음): {len(html)}")
                return True

        except Exception:
            return False


        return False
    # 차단 누적 쿨다운 시간 계산
    def get_block_cooldown_sec(self) -> int:
        if self._block_hit_count <= 1:
            return 300   # 5분
        if self._block_hit_count == 2:
            return 600   # 10분
        return 1200      # 20분

    # === 신규 === 브라우저 재시작
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

    # === 신규 === 차단 의심 시 브라우저 종료 + 대기 + 재시작 + 쿠키 재발급
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

        self.log_signal_func("🌐 쿠키 세팅을 위해 메인 페이지 접속: https://bizno.net/")
        self.driver.get("https://bizno.net/")

        self.log_signal_func("쿠키 대기 전 잠시 쉽니다. (2.00s)")
        if not self.sleep_s(2.0):
            self.log_signal_func("⛔ cookie sleep 중단 감지")
            return

        # requests용 쿠키 저장은 이제 사실상 필수는 아니지만, 기존 구조 유지
        cnt = 0
        try:
            for c in self.driver.get_cookies():
                name = c.get("name")
                value = c.get("value")
                if name and value and self.api_client:
                    self.api_client.cookie_set(name, value)
                    cnt += 1
        except Exception as e:
            self.log_signal_func(f"⚠️ 쿠키 복사 중 예외: {e}")

        self._cookie_ready = True
        self.log_signal_func(f"✅ 쿠키 세팅 완료 (count={cnt})")

    # === 신규 === 쿠키 재발급 (가능한 최소 변경)
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


    def get_html(self, url: str, headers: dict) -> str:
        # 저장해둔 HTML을 그대로 재사용
        if url in self._cache:
            self.log_signal_func(f"🧠 cache hit: {url}")
            return self._cache[url]

        attempt = 0
        max_attempts = 12  # 무한루프 방지

        while self.running and attempt < max_attempts:
            attempt += 1
            mode = self.get_current_request_mode()

            self.log_signal_func(f"🌐 GET 시도 (attempt={attempt}, mode={mode}): {url}")

            html = ""
            ok = False

            try:
                if mode == "selenium":
                    html = self.get_html_by_selenium(url, headers)
                elif mode == "api":
                    html = self.get_html_by_api(url, headers)
                elif mode == "proxy":
                    html = self.get_html_by_proxy(url, headers)
                else:
                    self.log_signal_func(f"⚠️ 알 수 없는 mode: {mode}")
                    html = ""

                if html and not self.is_blocked_html(html):
                    ok = True

            except Exception as e:
                self.log_signal_func(f"❌ GET 예외 (mode={mode}, attempt={attempt}): {e}")
                ok = False

            if ok:
                self.log_signal_func(f"✅ 응답 성공 (mode={mode}, attempt={attempt})")

                if len(self._cache) < 2000:
                    self._cache[url] = html
                    self.log_signal_func(f"🧠 cache save: {url} (size={len(self._cache)})")

                return html or ""

            self.log_signal_func(f"⚠️ 응답 실패/차단 (mode={mode}, attempt={attempt})")

            # 다음 채널로 회전
            self.rotate_request_mode()

            # 너무 빠른 연속 요청 방지
            sleep_t = random.uniform(2.0, 5.0)
            self.log_signal_func(f"🕒 채널 전환 후 대기: {sleep_t:.2f}s")
            if not self.sleep_s(sleep_t):
                return ""

        self.log_signal_func("⛔ get_html 최대 재시도 초과 또는 running=False")
        return ""


    def get_html_by_selenium(self, url: str, headers: dict) -> str:
        self.driver.get(url)
        wait_sec = random.uniform(3.0, 5.0)
        self.log_signal_func(f"[selenium] 페이지 로딩 후 대기 ({wait_sec:.2f}s)")
        if not self.sleep_s(wait_sec):
            return ""

        return self.driver.page_source or ""


    def request_bizno_search_api(self, company_name: str, owner_name: str) -> Response:
        self.log_signal_func(f"[api-search] 요청 시작: company_name={company_name}, owner_name={owner_name}")

        # 예시: APIClient 내부에 get_json 같은 함수가 있다고 가정
        # 없으면 requests로 직접 호출해도 됩니다.
        payload: Dict[str, Any] = {
            "companyName": company_name,
            "ownerName": owner_name,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = self.session.get(
            self.bizno_search_url,
            params=payload,
            headers=headers,
            timeout=15,
        )

        return resp


    def request_bizno_detail_api(self, article: str) -> Response:
        self.log_signal_func(f"[api-detail] 요청 시작: article={article}")

        payload: Dict[str, Any] = {
            "article": article,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = self.session.get(
            self.bizno_detail_url,
            params=payload,
            headers=headers,
            timeout=15,
        )

        return resp


    def get_html_by_api(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"[api] 요청 시작: {url}")

        # === 여기에 나중에 직접 구현 ===
        # 예시:
        # response = self.api_client.post("/crawl/html", json={"url": url, "headers": headers})
        # return response.get("html", "")

        raise NotImplementedError("API 서버 연동 로직을 여기에 구현하세요.")

    def get_html_by_proxy(self, url: str, headers: dict) -> str:
        self.log_signal_func(f"[proxy] 요청 시작: {url}")

        # === 여기에 나중에 직접 구현 ===
        # 예시:
        # response = self.api_client.post("/proxy/fetch", json={"url": url, "headers": headers})
        # return response.get("html", "")

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


    # =========================
    # bizno: search
    # =========================
    def fetch_search_results(self, item: dict) -> None:
        raw_company_name = (item.get("검색회사명") or "").strip()
        filtered_company_name = self.normalize_search_company_name(raw_company_name)
        owner = (item.get("검색대표자명") or "").strip()
    
        item["검색필터회사명"] = filtered_company_name
        item["article"] = ""
    
        mode = self.get_current_request_mode()
        self.log_signal_func(
            f"[search] mode={mode}, company='{filtered_company_name}', owner='{owner}'"
        )
    
        if mode == "api":
            try:
                resp = self.request_bizno_search_api(filtered_company_name, owner)
                self.log_signal_func(f"[api-search] 응답: {resp}")
                res = self._loads_if_needed(resp.text)
    
                if res.get("success") and res.get("article"):
                    item["article"] = str(res.get("article") or "").strip()
                    item["회사명"] = str(res.get("회사명") or "").strip()
                    self.log_signal_func(
                        f"[search][api] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
                    )
                else:
                    self.log_signal_func(f"[search][api] ⚠️ match 없음: {res.get('message')}")
                return
    
            except Exception as e:
                self.log_signal_func(f"[search][api] ❌ 예외: {e}")
                self.rotate_request_mode()

        if mode == "proxy":
            # 준비중
            return
    
        url = f"https://bizno.net/?area=&query={quote(filtered_company_name)}"
        self.log_signal_func(f"[search] url={url}")
    
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
        if not html:
            self.log_signal_func("[search] ⚠️ HTML 없음")
            return
    
        soup = BeautifulSoup(html, "html.parser")
    
        self.log_signal_func(
            f"[search] 매칭 기준: 대표자명='{owner}', 검색필터회사명='{filtered_company_name}'"
        )
    
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
                f"[search] ✅ match found: 회사명='{item.get('회사명')}', article='{item.get('article')}'"
            )
            return
    
        self.log_signal_func(f"[search] 결과 스캔 완료. details_count={hit}, match=0")

    # =========================
    # bizno: detail
    # =========================
    def fetch_article_detail(self, item: dict) -> None:
        article = str(item.get("article") or "").strip()
        if not article:
            self.log_signal_func("[detail] ⚠️ article 없음")
            return

        mode = self.get_current_request_mode()
        self.log_signal_func(f"[detail] mode={mode}, article={article}")

        if mode == "api":
            try:
                resp = self.request_bizno_detail_api(article)
                self.log_signal_func(f"[api-detail] 응답: {resp}")
                res = self._loads_if_needed(resp.text)

                if res.get("success"):
                    item["url"] = str(res.get("url") or "")
                    data = res.get("data") or {}

                    if isinstance(data, dict):
                        row_cnt = 0
                        for key, val in data.items():
                            if key:
                                item[str(key)] = str(val or "")
                                row_cnt += 1
                        self.log_signal_func(f"[detail][api] ✅ 테이블 반영 완료. row_count={row_cnt}")
                        return

                self.log_signal_func(f"[detail][api] ⚠️ 상세 실패: {res.get('message')}")
                self.rotate_request_mode()

            except Exception as e:
                self.log_signal_func(f"[detail][api] ❌ 예외: {e}")
                self.rotate_request_mode()


        if mode == "proxy":
            return


        url = f"https://bizno.net/article/{article}"
        self.log_signal_func(f"[detail] url={url}")

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
        if not html:
            self.log_signal_func("[detail] ⚠️ HTML 없음")
            return

        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table.table_guide01")
        item["url"] = url

        if not table:
            self.log_signal_func("[detail] ⚠️ table.table_guide01 없음")
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

        self.log_signal_func(f"[detail] ✅ 테이블 파싱 완료. row_count={row_cnt}")