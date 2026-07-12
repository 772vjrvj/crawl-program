# src/workers/main/api_yeogi_admin_set_worker.py
from __future__ import annotations

import json
import os
import random
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from src.repositories.worker_db_repository import WorkerDbRepository
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class AccessBlockedError(RuntimeError):
    """여기어때에서 접속을 제한한 경우."""


class SellerButtonTimeoutError(RuntimeError):
    """판매자 정보 버튼을 제한 시간 안에 찾지 못한 경우."""


class SellerModalTimeoutError(RuntimeError):
    """판매자 정보 모달 또는 표 데이터를 찾지 못한 경우."""


class ApiYeogiAdminSetWorker(BaseApiWorker):
    """
    여기어때 검색 결과의 숙소 ID를 API로 수집한 뒤,
    각 숙소 상세 페이지의 판매자 정보를 Selenium으로 수집한다.

    실행 흐름
    1. Selenium으로 https://www.yeogi.com 접속
    2. 사용자가 브라우저에서 날짜·인원·지역/숙소 검색
    3. 프로그램 안내창의 확인 버튼 클릭
    4. 현재 검색 URL을 기준으로 검색 API를 page=1부터 끝까지 호출
    5. body.items[].meta.id 수집
    6. 상세 페이지에서 판매자 정보 모달 수집
    7. WorkerDbRepository에 성공·실패 행 저장
    8. 종료 시 설정에 따라 엑셀 자동 저장

    DB/Excel/cleanup 공통 로직을 이 Worker 내부에 직접 포함한다.
    """

    HOME_URL = "https://www.yeogi.com"
    SEARCH_RESULT_PATH = "/domestic-accommodations"
    SEARCH_API_PATH = "/api/gateway/web-product-api/places/search"
    DETAIL_URL_FORMAT = "https://www.yeogi.com/domestic-accommodations/{place_id}"

    PAGE_LOAD_TIMEOUT = 60
    API_REQUEST_TIMEOUT_MS = 45_000
    MAX_SEARCH_PAGES = 500
    MAX_DETAIL_ATTEMPTS = 2

    FAST_SEARCH_TIMEOUT = 15
    SLOW_SEARCH_TIMEOUT = 35
    FAST_MODAL_TIMEOUT = 10
    SLOW_MODAL_TIMEOUT = 20

    SELLER_FIELD_MAP: Dict[str, str] = {
        "상호": "business_name",
        "대표자명": "representative_name",
        "주소": "address",
        "전화번호": "phone",
        "이메일": "email",
        "사업자 번호": "business_number",
    }

    def __init__(self) -> None:
        super().__init__()

        # 출력 설정
        self.out_dir: str = "output"
        self.folder_path: str = ""
        self.columns: Optional[List[str]] = None

        # Worker 정보
        self.site_name: str = "여기어때 관리자"
        self.worker_name: str = "yeogi_admin"
        self.detail_table_name: str = "yeogi_admin"

        # 실행 설정
        self.auto_save_yn: bool = False
        self.remove_duplicate_yn: bool = True

        # 실행 상태
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self._cleaned_up: bool = False
        self._stop_event = threading.Event()
        self._guide_event: Optional[threading.Event] = None

        # 검색 정보
        self.search_page_url: str = ""
        self.search_keyword: str = ""

        # 드라이버
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.selenium_utils: Optional[SeleniumUtils] = None
        self.driver: Optional[WebDriver] = None

        # DB Repository
        self.db_repository: Optional[WorkerDbRepository] = None

    # =========================================================
    # 초기화
    # =========================================================
    def init(self) -> bool:
        try:
            setting_list = self.setting or []

            self.folder_path = str(
                self.get_setting_value(setting_list, "folder_path") or ""
            ).strip()
            self.auto_save_yn = bool(
                self.get_setting_value(setting_list, "auto_save_yn")
            )

            remove_duplicate_value = self.get_setting_value(
                setting_list,
                "remove_duplicate_yn",
            )
            if remove_duplicate_value is not None:
                self.remove_duplicate_yn = bool(remove_duplicate_value)

            self.log_signal_func(f"✅ 저장경로 : {self.folder_path}")
            self.log_signal_func(
                f"✅ 엑셀 자동 저장 여부 : {self.auto_save_yn}"
            )
            self.log_signal_func(
                f"✅ 중복제거 여부 : {self.remove_duplicate_yn}"
            )

            self.driver_set()

            if not self.db_set():
                return False

            self.log_signal_func(f"선택 항목 : {self.columns}")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.log_signal_func("✅ 드라이버 세팅")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)

        self.selenium_utils = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.selenium_utils.set_capture_options(
            enabled=False,
            block_images=False,
        )

    # =========================================================
    # 프로그램 실행
    # =========================================================
    def main(self) -> bool:
        try:
            self.log_signal_func("✅ 여기어때 판매자 정보 수집 시작")

            self._start_browser()
            self._open_home()

            if not self._show_search_guide_and_wait():
                self.finish_job("STOP", "사용자 중단")
                return True

            if not self._switch_to_search_result_window():
                raise ValueError(
                    "숙소 검색 결과 화면을 찾지 못했습니다. "
                    "여기어때 브라우저에서 검색을 완료한 뒤 확인을 눌러주세요."
                )

            if self.driver is None:
                raise RuntimeError("Selenium driver가 없습니다.")

            self.search_page_url = str(self.driver.current_url or "").strip()
            self._validate_search_page_url(self.search_page_url)
            self.search_keyword = self._get_query_value(
                self.search_page_url,
                "keyword",
            )

            self.log_signal_func(f"검색 결과 URL : {self.search_page_url}")
            self.log_signal_func(f"검색어 : {self.search_keyword}")
            self.log_signal_func("검색 결과 숙소 ID 수집을 시작합니다.")

            place_ids = self._collect_place_ids(self.search_page_url)

            if not self.running:
                self.finish_job("STOP", "사용자 중단")
                return True

            if not place_ids:
                raise RuntimeError("검색 결과에서 숙소 ID를 찾지 못했습니다.")

            self.total_cnt = len(place_ids)
            self.log_signal_func(f"✅ 전체 숙소 ID 수 : {self.total_cnt}개")

            self._collect_seller_details(place_ids)

            if self.db_repository and self.db_repository.status == "RUNNING":
                if self.running:
                    self.finish_job("SUCCESS")
                else:
                    self.finish_job("STOP", "사용자 중단")

            self.log_signal_func("✅ 여기어때 판매자 정보 수집 종료")
            return True

        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
            self.log_signal_func(
                f"❌ 전체 실행 중 예외 발생: {error_message}"
            )
            self.finish_job("FAIL", error_message)
            return False

    # =========================================================
    # Selenium 시작 / 사용자 검색 대기
    # =========================================================
    def _start_browser(self) -> None:
        if self.selenium_utils is None:
            raise RuntimeError("SeleniumUtils가 초기화되지 않았습니다.")

        self.driver = self.selenium_utils.start_driver(
            timeout=self.PAGE_LOAD_TIMEOUT,
            view_mode="browser",
            window_size=(1400, 1000),
        )

        self.driver.set_script_timeout(
            max(60, int(self.API_REQUEST_TIMEOUT_MS / 1000) + 10)
        )

    def _open_home(self) -> None:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        self.log_signal_func(f"초기 접속 : {self.HOME_URL}")

        try:
            self.driver.get(self.HOME_URL)
        except TimeoutException:
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass

        self._wait_document_ready(timeout=20)

        if self._is_access_blocked():
            raise AccessBlockedError(
                "여기어때 메인 페이지 접속이 제한되었습니다."
            )

    def _show_search_guide_and_wait(self) -> bool:
        """
        MainWindow.show_message()는 전달받은 event를 확인 버튼 클릭 후 set한다.
        Worker 스레드는 event가 set될 때까지 대기한다.
        """
        self._guide_event = threading.Event()

        message = (
            "여기어때 브라우저에서 날짜, 인원, 숙소 또는 지역을 검색해주세요.\n\n"
            "검색 결과 목록이 화면에 표시되면 이 안내창의 확인 버튼을 눌러주세요."
        )

        self.msg_signal_func(message, "info", self._guide_event)

        while self.running:
            if self._guide_event.wait(0.2):
                return True

        return False

    def _switch_to_search_result_window(self) -> bool:
        """검색 결과가 새 탭에 열린 경우에도 해당 탭으로 전환한다."""
        if self.driver is None:
            return False

        try:
            handles = list(self.driver.window_handles)
        except Exception:
            handles = []

        # 최근에 열린 탭부터 확인한다.
        for handle in reversed(handles):
            try:
                self.driver.switch_to.window(handle)
                current_url = str(self.driver.current_url or "").strip()

                if self._is_search_result_url(current_url):
                    return True
            except Exception:
                continue

        return self._is_search_result_url(
            str(self.driver.current_url or "").strip()
        )

    @classmethod
    def _is_search_result_url(cls, url: str) -> bool:
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/") or "/"

            return (
                    parsed.netloc in {"www.yeogi.com", "yeogi.com"}
                    and path == cls.SEARCH_RESULT_PATH
                    and bool(parsed.query)
            )
        except Exception:
            return False

    @classmethod
    def _validate_search_page_url(cls, url: str) -> None:
        if not cls._is_search_result_url(url):
            raise ValueError(
                "숙소 검색 결과 URL이 아닙니다. "
                "여기어때에서 날짜와 숙소/지역 검색을 완료한 뒤 "
                "확인 버튼을 눌러주세요."
            )

    @staticmethod
    def _get_query_value(url: str, key: str) -> str:
        values = parse_qs(urlparse(url).query).get(key) or []
        return str(values[0]).strip() if values else ""

    # =========================================================
    # 검색 API
    # =========================================================
    def _build_search_api_url(
            self,
            search_page_url: str,
            page: int,
    ) -> str:
        parsed = urlparse(search_page_url)

        # 검색 화면 URL의 파라미터 순서와 중복값을 최대한 유지한다.
        params: List[Tuple[str, str]] = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key != "page"
        ]

        existing_keys = {key for key, _ in params}
        default_params = {
            "sortType": "RECOMMEND",
            "category": "0",
            "limit": "20",
            "isBusinessExternal": "false",
        }

        for key, value in default_params.items():
            if key not in existing_keys:
                params.append((key, value))

        params.append(("page", str(page)))

        return urlunparse(
            (
                "https",
                "www.yeogi.com",
                self.SEARCH_API_PATH,
                "",
                urlencode(params, doseq=True),
                "",
            )
        )

    def _fetch_search_api(self, api_url: str) -> Dict[str, Any]:
        """
        현재 Selenium 브라우저 안에서 fetch를 실행한다.

        별도 requests 세션보다 현재 브라우저 fetch가 유리한 이유
        - 사용자가 생성한 쿠키/Cloudflare 세션을 그대로 사용
        - 실제 브라우저 User-Agent와 same-origin 환경을 그대로 사용
        - 목록을 직접 스크롤하지 않고 page만 변경 가능
        """
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        script = """
            const apiUrl = arguments[0];
            const timeoutMs = arguments[1];
            const done = arguments[arguments.length - 1];

            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);

            fetch(apiUrl, {
                method: 'GET',
                credentials: 'include',
                cache: 'no-store',
                headers: {
                    'accept': 'application/json, text/plain, */*',
                    'content-type': 'application/json',
                    'x-api-max-version': '2.0.0',
                    'x-channel': 'YEOGI',
                    'x-device-id': 'WEB',
                    'x-device-platform': 'NEW_WEB',
                    'uosgubn': 'W'
                },
                signal: controller.signal
            })
            .then(async response => {
                const text = await response.text();
                clearTimeout(timer);
                done({
                    ok: response.ok,
                    status: response.status,
                    statusText: response.statusText,
                    text: text
                });
            })
            .catch(error => {
                clearTimeout(timer);
                done({
                    ok: false,
                    status: 0,
                    statusText: '',
                    error: String(error)
                });
            });
        """

        raw = self.driver.execute_async_script(
            script,
            api_url,
            self.API_REQUEST_TIMEOUT_MS,
        )

        if not isinstance(raw, dict):
            raise RuntimeError("검색 API 응답 형식이 올바르지 않습니다.")

        status = int(raw.get("status") or 0)

        if status in {401, 403, 429}:
            raise AccessBlockedError(
                f"검색 API 요청이 제한되었습니다. status={status}"
            )

        if not raw.get("ok"):
            raise RuntimeError(
                "검색 API 호출 실패 | "
                f"status={status} | "
                f"error={raw.get('error') or raw.get('statusText') or ''}"
            )

        response_text = str(raw.get("text") or "")
        if not response_text:
            raise RuntimeError("검색 API 응답 본문이 비어 있습니다.")

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"검색 API JSON 변환 실패: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError("검색 API JSON이 객체 형식이 아닙니다.")

        return data

    @staticmethod
    def _extract_ids_from_api(data: Dict[str, Any]) -> List[str]:
        body = data.get("body") or {}
        if not isinstance(body, dict):
            return []

        items = body.get("items") or []
        if not isinstance(items, list):
            return []

        result: List[str] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            meta = item.get("meta") or {}
            if not isinstance(meta, dict):
                continue

            place_id = meta.get("id")
            if place_id is not None and str(place_id).strip():
                result.append(str(place_id).strip())

        return result

    @staticmethod
    def _get_pagination(data: Dict[str, Any]) -> Dict[str, Any]:
        pagination = data.get("pagination")
        if isinstance(pagination, dict):
            return pagination

        body = data.get("body") or {}
        if isinstance(body, dict):
            pagination = body.get("pagination")
            if isinstance(pagination, dict):
                return pagination

        return {}

    def _collect_place_ids(self, search_page_url: str) -> List[str]:
        collected: List[str] = []
        seen: Set[str] = set()

        total_pages: Optional[int] = None
        page = 1

        while self.running and page <= self.MAX_SEARCH_PAGES:
            api_url = self._build_search_api_url(search_page_url, page)
            self.log_signal_func(f"검색 API 요청 : page={page}")

            data = self._fetch_search_api(api_url)
            page_ids = self._extract_ids_from_api(data)
            pagination = self._get_pagination(data)

            if total_pages is None:
                try:
                    total_pages = int(
                        pagination.get("totalPageCount") or 0
                    )
                except (TypeError, ValueError):
                    total_pages = 0

                try:
                    total_count = int(pagination.get("totalCount") or 0)
                except (TypeError, ValueError):
                    total_count = 0

                self.log_signal_func(
                    f"검색 결과 전체 건수={total_count} / "
                    f"전체 페이지={total_pages or '미확인'}"
                )

            if not page_ids:
                self.log_signal_func(
                    f"검색 API 데이터 없음 : page={page}"
                )
                break

            for place_id in page_ids:
                if self.remove_duplicate_yn:
                    if place_id in seen:
                        continue
                    seen.add(place_id)

                collected.append(place_id)

            self.log_signal_func(
                f"검색 API 완료 : page={page} / "
                f"페이지 ID={len(page_ids)}개 / 누적={len(collected)}개"
            )

            if total_pages and page >= total_pages:
                break

            page += 1

            if not self.sleep_s(random.uniform(0.4, 0.9)):
                break

        if page > self.MAX_SEARCH_PAGES:
            self.log_signal_func(
                f"⚠️ 검색 API 최대 페이지 제한 도달: {self.MAX_SEARCH_PAGES}"
            )

        if not self.running:
            self.log_signal_func(
                "사용자 중단으로 검색 API 수집을 종료합니다."
            )

        return collected

    # =========================================================
    # 상세 판매자 정보 수집
    # =========================================================
    def _collect_seller_details(
            self,
            place_ids: Sequence[str],
    ) -> None:
        total = len(place_ids)

        for index, place_id in enumerate(place_ids, start=1):
            if not self.running:
                self.log_signal_func(
                    "사용자 중단으로 상세 수집을 종료합니다."
                )
                break

            url = self.DETAIL_URL_FORMAT.format(place_id=place_id)
            row_start_at = self._now_db()

            try:
                seller_info = self._collect_detail_with_retry(
                    url=url,
                    current=index,
                    total=total,
                )
                row_end_at = self._now_db()

                row: Dict[str, Any] = {
                    **seller_info,
                    "search_keyword": self.search_keyword,
                    "url": url,
                }

                save_ok = self.insert_detail_row(
                    row,
                    row_status="SUCCESS",
                    row_start_at=row_start_at,
                    row_end_at=row_end_at,
                )

                self.log_signal_func(
                    f"상세 완료 {index}/{total} | "
                    f"ID={place_id} | "
                    f"상호={row.get('business_name', '')} | "
                    f"DB저장={'SUCCESS' if save_ok else 'FAIL'}"
                )

            except AccessBlockedError as e:
                row_end_at = self._now_db()
                error_message = str(e) or "사이트에서 접속을 제한했습니다."

                self.insert_detail_row(
                    self._build_failed_detail_row(url),
                    row_status="FAIL",
                    row_error_message=error_message,
                    row_start_at=row_start_at,
                    row_end_at=row_end_at,
                )

                self.log_signal_func(
                    f"❌ 접속 제한 {index}/{total} | "
                    f"ID={place_id} | {error_message}"
                )
                raise

            except Exception as e:
                row_end_at = self._now_db()
                error_message = f"{type(e).__name__}: {e}"

                self.insert_detail_row(
                    self._build_failed_detail_row(url),
                    row_status="FAIL",
                    row_error_message=error_message,
                    row_start_at=row_start_at,
                    row_end_at=row_end_at,
                )

                self.log_signal_func(
                    f"⚠️ 상세 실패 {index}/{total} | "
                    f"ID={place_id} | error={error_message}"
                )

                self._save_error_screenshot(index, place_id)

            self.current_cnt = index
            self._update_progress(index, total)

            if index < total and self.running:
                if not self.sleep_s(random.uniform(2.0, 2.5)):
                    break

    def _build_failed_detail_row(self, url: str) -> Dict[str, Any]:
        return {
            "business_name": "",
            "representative_name": "",
            "address": "",
            "phone": "",
            "email": "",
            "business_number": "",
            "search_keyword": self.search_keyword,
            "url": url,
        }

    def _collect_detail_with_retry(
            self,
            *,
            url: str,
            current: int,
            total: int,
    ) -> Dict[str, str]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_DETAIL_ATTEMPTS + 1):
            if not self.running:
                raise RuntimeError("사용자 중단")

            slow_mode = attempt >= 2
            mode_text = "느린 재시도" if slow_mode else "일반 시도"

            self.log_signal_func(
                f"상세 접속 {current}/{total} | "
                f"시도={attempt}/{self.MAX_DETAIL_ATTEMPTS} | "
                f"{mode_text} | {url}"
            )

            try:
                return self._collect_one_detail(url, slow_mode)

            except AccessBlockedError:
                raise

            except Exception as e:
                last_error = e
                self.log_signal_func(
                    f"상세 시도 실패 {current}/{total} | "
                    f"시도={attempt} | {type(e).__name__}: {e}"
                )

                if attempt < self.MAX_DETAIL_ATTEMPTS:
                    try:
                        if self.driver is not None:
                            self.driver.get("about:blank")
                    except Exception:
                        pass

                    if not self.sleep_s(2.0):
                        break

        if last_error is None:
            raise RuntimeError("상세 조회 실패")

        raise last_error

    def _collect_one_detail(
            self,
            url: str,
            slow_mode: bool,
    ) -> Dict[str, str]:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        try:
            self.driver.get(url)
        except TimeoutException:
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass

        self._wait_document_ready(
            timeout=20 if slow_mode else 10
        )

        if not self.sleep_s(2.0 if slow_mode else 0.6):
            raise RuntimeError("사용자 중단")

        if self._is_access_blocked():
            raise AccessBlockedError(
                "상세 페이지 접속이 제한되었습니다."
            )

        dialog = self._open_seller_dialog(slow_mode)
        return self._extract_seller_info(dialog)

    # =========================================================
    # 페이지 상태 확인
    # =========================================================
    def _wait_document_ready(self, timeout: int = 15) -> None:
        if self.driver is None:
            return

        try:
            WebDriverWait(self.driver, timeout).until(
                lambda current_driver: current_driver.execute_script(
                    "return document.readyState"
                ) in ("interactive", "complete")
            )

            WebDriverWait(self.driver, timeout).until(
                lambda current_driver: current_driver.execute_script(
                    "return document.body !== null"
                )
            )
        except TimeoutException:
            # 일부 DOM만 생성되어도 판매자 정보 탐색은 계속한다.
            pass

    def _is_access_blocked(self) -> bool:
        if self.driver is None:
            return False

        title = ""
        body_text = ""
        page_source = ""

        try:
            title = str(self.driver.title or "").lower()
        except Exception:
            pass

        try:
            body_text = self.driver.find_element(
                By.TAG_NAME,
                "body",
            ).text.lower()
        except Exception:
            pass

        try:
            page_source = str(
                self.driver.page_source or ""
            ).lower()
        except Exception:
            pass

        combined_text = (
            f"{title}\n{body_text}\n{page_source[:30_000]}"
        )

        blocked_keywords = (
            "403 forbidden",
            "http 403",
            "access denied",
            "request blocked",
            "temporarily blocked",
            "접근이 제한",
            "접속이 제한",
            "요청이 차단",
            "비정상적인 접근",
            "서비스 이용이 제한",
        )

        return any(
            keyword in combined_text
            for keyword in blocked_keywords
        )

    # =========================================================
    # 판매자 정보 버튼 탐색
    # =========================================================
    @staticmethod
    def _get_visible_element(
            elements: Sequence[WebElement],
    ) -> Optional[WebElement]:
        for element in reversed(list(elements)):
            try:
                if element.is_displayed():
                    return element
            except (StaleElementReferenceException, WebDriverException):
                continue

        return None

    def _find_visible_seller_button(self) -> Optional[WebElement]:
        if self.driver is None:
            return None

        selectors = (
            (
                By.CSS_SELECTOR,
                '[aria-label="판매자 정보"][role="button"]',
            ),
            (By.CSS_SELECTOR, '[aria-label="판매자 정보"]'),
            (
                By.XPATH,
                "//h2[normalize-space()='판매자 정보']"
                "/ancestor::*[@role='button'][1]",
            ),
            (
                By.XPATH,
                "//*[normalize-space()='판매자 정보']"
                "/ancestor::*[@role='button'][1]",
            ),
        )

        for by, selector in selectors:
            try:
                element = self._get_visible_element(
                    self.driver.find_elements(by, selector)
                )
                if element is not None:
                    return element
            except Exception:
                continue

        try:
            element = self.driver.execute_script(
                """
                const candidates = Array.from(
                    document.querySelectorAll(
                        '[role="button"], [aria-label="판매자 정보"]'
                    )
                );

                for (let i = candidates.length - 1; i >= 0; i--) {
                    const element = candidates[i];
                    const ariaLabel = (
                        element.getAttribute('aria-label') || ''
                    ).trim();
                    const text = (
                        element.innerText || element.textContent || ''
                    ).trim();
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);

                    const visible = (
                        rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || '1') > 0
                    );

                    if (
                        visible
                        && (
                            ariaLabel === '판매자 정보'
                            || text === '판매자 정보'
                            || text.startsWith('판매자 정보')
                        )
                    ) {
                        return element;
                    }
                }

                return null;
                """
            )

            if element is not None:
                return element

        except Exception:
            pass

        return None

    def _get_page_height(self) -> int:
        if self.driver is None:
            return 0

        try:
            value = self.driver.execute_script(
                """
                return Math.max(
                    document.body ? document.body.scrollHeight : 0,
                    document.documentElement
                        ? document.documentElement.scrollHeight
                        : 0
                );
                """
            )
            return int(value or 0)
        except Exception:
            return 0

    def _get_scroll_position(self) -> int:
        if self.driver is None:
            return 0

        try:
            value = self.driver.execute_script(
                """
                return window.pageYOffset
                    || document.documentElement.scrollTop
                    || document.body.scrollTop
                    || 0;
                """
            )
            return int(value or 0)
        except Exception:
            return 0

    def _scroll_to_bottom_with_lazy_loading(
            self,
            slow_mode: bool,
    ) -> Optional[WebElement]:
        if self.driver is None:
            return None

        wait_seconds = 0.8 if slow_mode else 0.35
        max_cycles = 8 if slow_mode else 4
        previous_height = -1
        same_height_count = 0

        for _ in range(max_cycles):
            if not self.running:
                raise RuntimeError("사용자 중단")

            button = self._find_visible_seller_button()
            if button is not None:
                return button

            try:
                self.driver.execute_script(
                    """
                    window.scrollTo(
                        0,
                        Math.max(
                            document.body ? document.body.scrollHeight : 0,
                            document.documentElement
                                ? document.documentElement.scrollHeight
                                : 0
                        )
                    );
                    """
                )
            except JavascriptException:
                pass

            if not self.sleep_s(wait_seconds):
                raise RuntimeError("사용자 중단")

            button = self._find_visible_seller_button()
            if button is not None:
                return button

            new_height = self._get_page_height()

            if new_height == previous_height:
                same_height_count += 1
            else:
                same_height_count = 0

            previous_height = new_height

            if same_height_count >= 2:
                break

        return None

    def _scroll_page_step_by_step(
            self,
            slow_mode: bool,
    ) -> Optional[WebElement]:
        if self.driver is None:
            return None

        search_timeout = (
            self.SLOW_SEARCH_TIMEOUT
            if slow_mode
            else self.FAST_SEARCH_TIMEOUT
        )
        scroll_wait = 0.45 if slow_mode else 0.15
        scroll_step = 500 if slow_mode else 900
        started_at = time.monotonic()

        self.driver.execute_script("window.scrollTo(0, 0);")

        if not self.sleep_s(0.8 if slow_mode else 0.2):
            raise RuntimeError("사용자 중단")

        while time.monotonic() - started_at < search_timeout:
            if not self.running:
                raise RuntimeError("사용자 중단")

            button = self._find_visible_seller_button()
            if button is not None:
                return button

            if self._is_access_blocked():
                raise AccessBlockedError(
                    "상세 페이지 접속이 제한되었습니다."
                )

            current_position = self._get_scroll_position()
            page_height = self._get_page_height()

            viewport_height = int(
                self.driver.execute_script(
                    "return window.innerHeight || 900;"
                ) or 900
            )

            self.driver.execute_script(
                "window.scrollTo(0, arguments[0]);",
                current_position + scroll_step,
                )

            if not self.sleep_s(scroll_wait):
                raise RuntimeError("사용자 중단")

            new_position = self._get_scroll_position()

            if new_position + viewport_height >= page_height - 100:
                if not self.sleep_s(1.5 if slow_mode else 0.5):
                    raise RuntimeError("사용자 중단")

                button = self._find_visible_seller_button()
                if button is not None:
                    return button

                # IntersectionObserver 반응을 위해 약간 위로 갔다가 다시 내린다.
                self.driver.execute_script("window.scrollBy(0, -500);")

                if not self.sleep_s(0.5 if slow_mode else 0.2):
                    raise RuntimeError("사용자 중단")

                self.driver.execute_script(
                    """
                    window.scrollTo(
                        0,
                        Math.max(
                            document.body ? document.body.scrollHeight : 0,
                            document.documentElement
                                ? document.documentElement.scrollHeight
                                : 0
                        )
                    );
                    """
                )

                if not self.sleep_s(1.5 if slow_mode else 0.5):
                    raise RuntimeError("사용자 중단")

                button = self._find_visible_seller_button()
                if button is not None:
                    return button

                if self._get_page_height() <= page_height:
                    break

        return None

    def _find_seller_button(self, slow_mode: bool) -> WebElement:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        button = self._find_visible_seller_button()
        if button is not None:
            return button

        button = self._scroll_to_bottom_with_lazy_loading(slow_mode)
        if button is not None:
            return button

        button = self._scroll_page_step_by_step(slow_mode)
        if button is not None:
            return button

        self.driver.execute_script(
            """
            window.scrollTo(
                0,
                Math.max(
                    document.body ? document.body.scrollHeight : 0,
                    document.documentElement
                        ? document.documentElement.scrollHeight
                        : 0
                )
            );
            """
        )

        if not self.sleep_s(2.0 if slow_mode else 0.7):
            raise RuntimeError("사용자 중단")

        button = self._find_visible_seller_button()
        if button is not None:
            return button

        if self._is_access_blocked():
            raise AccessBlockedError(
                "상세 페이지 접속이 제한되었습니다."
            )

        raise SellerButtonTimeoutError(
            "페이지 하단까지 확인했지만 판매자 정보 버튼을 찾지 못했습니다."
        )

    # =========================================================
    # 판매자 정보 모달 처리
    # =========================================================
    def _click_seller_button(self, button: WebElement) -> None:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        try:
            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });
                """,
                button,
            )
        except Exception:
            pass

        if not self.sleep_s(0.3):
            raise RuntimeError("사용자 중단")

        try:
            ActionChains(self.driver).move_to_element(button).pause(
                0.1
            ).click().perform()
            return

        except (
                ElementClickInterceptedException,
                ElementNotInteractableException,
                StaleElementReferenceException,
                WebDriverException,
        ):
            pass

        try:
            self.driver.execute_script(
                "arguments[0].click();",
                button,
            )
        except Exception as e:
            raise RuntimeError(
                f"판매자 정보 버튼 클릭 실패: {e}"
            ) from e

    def _get_visible_seller_dialog(self) -> Optional[WebElement]:
        if self.driver is None:
            return None

        for selector in (
                '#modal-wrapper [role="dialog"]',
                '[role="dialog"]',
        ):
            try:
                dialogs = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    selector,
                )

                for dialog in reversed(dialogs):
                    try:
                        if (
                                dialog.is_displayed()
                                and "판매자 정보" in dialog.text.strip()
                        ):
                            return dialog
                    except (
                            StaleElementReferenceException,
                            WebDriverException,
                    ):
                        continue

            except Exception:
                continue

        return None

    def _wait_seller_dialog(self, slow_mode: bool) -> WebElement:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        timeout = (
            self.SLOW_MODAL_TIMEOUT
            if slow_mode
            else self.FAST_MODAL_TIMEOUT
        )

        try:
            return WebDriverWait(self.driver, timeout).until(
                lambda _driver: self._get_visible_seller_dialog()
            )
        except TimeoutException as e:
            raise SellerModalTimeoutError(
                "판매자 정보 버튼은 클릭했지만 모달이 나타나지 않았습니다."
            ) from e

    def _open_seller_dialog(self, slow_mode: bool) -> WebElement:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        seller_button = self._find_seller_button(slow_mode)
        self._click_seller_button(seller_button)

        try:
            return self._wait_seller_dialog(slow_mode)

        except SellerModalTimeoutError:
            if not self.sleep_s(1.5 if slow_mode else 0.5):
                raise RuntimeError("사용자 중단")

            seller_button = self._find_seller_button(True)
            self.driver.execute_script(
                "arguments[0].click();",
                seller_button,
            )
            return self._wait_seller_dialog(True)

    def _extract_seller_info(
            self,
            dialog: WebElement,
    ) -> Dict[str, str]:
        if self.driver is None:
            raise RuntimeError("Selenium driver가 없습니다.")

        def table_rows_loaded(_driver: WebDriver) -> bool:
            try:
                rows = dialog.find_elements(
                    By.CSS_SELECTOR,
                    "table tbody tr",
                )
                return len(rows) > 0
            except StaleElementReferenceException:
                return False

        try:
            WebDriverWait(self.driver, 10).until(table_rows_loaded)
        except TimeoutException as e:
            raise SellerModalTimeoutError(
                "판매자 정보 모달은 열렸지만 표 데이터가 로드되지 않았습니다."
            ) from e

        result: Dict[str, str] = {
            code: ""
            for code in self.SELLER_FIELD_MAP.values()
        }

        for row in dialog.find_elements(
                By.CSS_SELECTOR,
                "table tbody tr",
        ):
            try:
                label = row.find_element(
                    By.TAG_NAME,
                    "th",
                ).text.strip()
                value = row.find_element(
                    By.TAG_NAME,
                    "td",
                ).text.strip()

                code = self.SELLER_FIELD_MAP.get(label)
                if code:
                    result[code] = value

            except (
                    NoSuchElementException,
                    StaleElementReferenceException,
            ):
                continue

        if not result.get("business_name"):
            raise RuntimeError(
                "판매자 정보 표는 찾았지만 상호 값이 비어 있습니다."
            )

        return result

    # =========================================================
    # 진행률 / 오류 화면
    # =========================================================
    def _update_progress(self, current: int, total: int) -> None:
        if total <= 0:
            return

        # destroy()에서 마지막 100% 처리를 하므로 상세 수집은 98%까지 사용한다.
        progress = (current / total) * 980_000
        self.progress_signal.emit(self.before_pro_value, progress)
        self.before_pro_value = progress

    def _save_error_screenshot(
            self,
            index: int,
            place_id: str,
    ) -> None:
        if self.driver is None:
            return

        try:
            base_folder = self.folder_path or self.get_project_root()
            screenshot_dir = os.path.join(
                base_folder,
                self.out_dir,
                "error_screenshots",
            )
            os.makedirs(screenshot_dir, exist_ok=True)

            screenshot_path = os.path.join(
                screenshot_dir,
                f"yeogi_admin_error_{index}_{place_id}.png",
            )

            if self.driver.save_screenshot(screenshot_path):
                self.log_signal_func(
                    f"오류 화면 저장 : {screenshot_path}"
                )

        except Exception as e:
            self.log_signal_func(f"오류 화면 저장 실패: {e}")

    # =========================================================
    # DB Repository
    # =========================================================
    def db_set(self) -> bool:
        config_data = self.read_runtime_customer_config(
            customer_name=self.worker_name
        )
        column_defs = config_data.get("columns") or []

        if not isinstance(column_defs, list) or not column_defs:
            self.log_signal_func(
                "❌ [config] columns가 없거나 형식이 올바르지 않습니다."
            )
            return False

        try:
            self.db_repository = WorkerDbRepository(
                db_path=self.get_runtime_db_path(),
                site_name=self.site_name,
                worker_name=self.worker_name,
                detail_table_name=self.detail_table_name,
                column_defs=column_defs,
                user_id=self.user,
                log_func=self.log_signal_func,
                detail_log_fields=(
                    "business_name",
                    "business_number",
                ),
            )
        except Exception as e:
            self.log_signal_func(
                f"❌ [DB] Repository 생성 실패: {e}"
            )
            return False

        schema_files = [
            os.path.join(
                "resources",
                "customers",
                "common",
                "db",
                "schema_hist.sql",
            ),
            os.path.join(
                "resources",
                "customers",
                self.worker_name,
                "db",
                "schema_detail.sql",
            ),
        ]

        if not self.db_repository.initialize(
                schema_files,
                start_job=True,
        ):
            return False

        # 화면/엑셀은 checked=true인 value(한글명)를 사용한다.
        self.columns = list(self.db_repository.excel_columns)

        self.log_signal_func(
            f"✅ [config] DB 컬럼 수="
            f"{len(self.db_repository.db_columns)} / "
            f"엑셀 컬럼 수="
            f"{len(self.db_repository.excel_columns)}"
        )
        return True

    def finish_job(
            self,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        if self.db_repository:
            self.db_repository.set_job_result(
                status,
                error_message,
            )

    def insert_detail_row(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        """상세 조회 결과와 행 단위 처리 상태를 Repository에 저장한다."""
        if not self.db_repository:
            self.log_signal_func(
                "❌ [DB] Repository 없음 - detail 저장 실패"
            )
            return False

        return self.db_repository.insert_detail(
            row,
            row_status=row_status,
            row_error_message=row_error_message,
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    @staticmethod
    def _now_db() -> str:
        """행 시작·종료시간을 Repository와 동일한 형식으로 반환한다."""
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

    # =========================================================
    # Excel / 작업 마감
    # =========================================================
    def export_detail_to_excel(self) -> bool:
        if not self.excel_driver:
            self.log_signal_func("❌ [엑셀] excel_driver 없음")
            return False

        if not self.db_repository:
            self.log_signal_func("❌ [엑셀] DB Repository 없음")
            return False

        excel_columns, excel_rows = self.db_repository.get_excel_data()

        if not excel_rows:
            self.log_signal_func(
                "⚠️ [엑셀] 저장할 detail 데이터가 없습니다."
            )
            return False

        job_id = self.db_repository.job_id or datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        excel_filename = f"{self.site_name}_{job_id}.xlsx"

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=excel_filename,
            row_list=excel_rows,
            columns=excel_columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def finalize_db_and_excel(self) -> None:
        if not self.db_repository:
            return

        try:
            # 정상 main 종료라면 SUCCESS/STOP이 이미 설정되어 있다.
            # RUNNING으로 남았다면 예외 또는 초기화 중 비정상 종료로 처리한다.
            if self.db_repository.status == "RUNNING":
                self.db_repository.set_job_result(
                    "FAIL",
                    "비정상 종료",
                )

            if self.db_repository.finish_job():
                self.log_signal_func(
                    "✅ [DB] hist 최종 업데이트 완료"
                )
            else:
                self.log_signal_func(
                    "❌ [DB] hist 최종 업데이트 실패"
                )

            if self.auto_save_yn:
                if self.export_detail_to_excel():
                    self.log_signal_func(
                        "✅ [엑셀] detail 자동 저장 완료"
                    )
                else:
                    self.log_signal_func(
                        "❌ [엑셀] detail 자동 저장 실패"
                    )
            else:
                self.log_signal_func(
                    "ℹ️ [엑셀] 자동 저장 미사용"
                    "(auto_save_yn=False)"
                )

        except Exception as e:
            self.log_signal_func(
                f"[cleanup] finalize_db_and_excel 실패: {e}"
            )

    # =========================================================
    # 종료 / 정리
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        # DB 작업 종료와 자동 엑셀 저장은 Repository 연결을 닫기 전에 처리한다.
        self.finalize_db_and_excel()

        try:
            if self.db_repository:
                self.db_repository.close()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] db_repository.close 실패: {e}"
            )
        finally:
            self.db_repository = None

        try:
            if self.selenium_utils:
                self.selenium_utils.quit()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] Selenium 종료 실패: {e}"
            )
        finally:
            self.driver = None
            self.selenium_utils = None

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] file_driver.close 실패: {e}"
            )

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] excel_driver.close 실패: {e}"
            )

        self.file_driver = None
        self.excel_driver = None
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()

        # 안내 팝업 확인 대기 중이라면 Worker 대기를 즉시 해제한다.
        if self._guide_event is not None:
            self._guide_event.set()

        if (
                self.db_repository
                and self.db_repository.status == "RUNNING"
        ):
            self.finish_job("STOP", "사용자 중단")

        time.sleep(1)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.cleanup()
        self.progress_signal.emit(
            self.before_pro_value,
            1_000_000,
        )
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()
