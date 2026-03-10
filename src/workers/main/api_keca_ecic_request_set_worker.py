# src/workers/main/api_keca_ecic_set_worker.py
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse

from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiKecaEcicExcelSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "KECA_ECIC"
        self.site_url: str = "https://www.keca.or.kr/ecic/ad/ad0101.do?menuCd=6047"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.driver = None
        self.selenium_driver = None
        self.folder_path: str = ""

        # 저장 하위 폴더
        self.out_dir: str = "output_keca_ecic"

        self._stop_event = threading.Event()
        self.excel_data_list: List[dict] = []
        self.current_search_url: str = ""
        self.current_cookie_str: str = ""

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func("main 시작")

            # 저장경로
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            # 파일명
            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            # 초기 파일 생성
            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.wait_for_user_confirmation()

            if self._stop_event.is_set():
                self.log_signal_func("⛔ 사용자 확인 대기 중 중지됨")
                return False

            self.fetch_all_company_list()
            self.log_signal_func(f"✅ 총 수집 건수: {len(self.excel_data_list)}")


        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")

        self.log_signal_func("✅ main 종료")
        return True

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("드라이버 세팅 시작========================================")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func, timeout=(10, 30))
        self.selenium_driver = SeleniumUtils(
            headless=False,
            log_func=self.log_signal_func
        )
        self.selenium_driver.set_capture_options(enabled=True, block_images=False)
        self.driver = self.selenium_driver.start_driver(1200)
        self.log_signal_func("✅ 드라이버 세팅 완료")

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

    def wait_for_user_confirmation(self) -> None:
        self.driver.get(self.site_url)

        event = threading.Event()
        self.msg_signal_func(
            "등록업체 지역선택 선택 후 검색이 끝나면 OK를 눌러주세요. \n또는 전체 검색인 경우는 OK를 바로 눌러주세요.",
            "info",
            event
        )
        event.wait()
        if self._stop_event.is_set():
            return

        self.current_search_url = self.driver.current_url
        self.driver_cookie_set()

        self.log_signal_func("✅ 상세 목록 진입 완료")
        self.log_signal_func(f"현재 URL: {self.current_search_url}")

    def driver_cookie_set(self) -> None:
        cnt = 0
        cookie_parts: List[str] = []

        try:
            for c in self.driver.get_cookies():
                name = c.get("name")
                value = c.get("value")
                if name and value:
                    cookie_parts.append(f"{name}={value}")

                    if self.api_client:
                        self.api_client.cookie_set(name, value)

                    cnt += 1

            self.current_cookie_str = "; ".join(cookie_parts)

        except Exception as e:
            self.log_signal_func(f"⚠️ 쿠키 복사 중 예외: {e}")

        self.log_signal_func(f"✅ 쿠키 세팅 완료 (count={cnt})")

    def map_row_for_excel(self, row: Dict[str, str], row_no: int, page_no: int) -> Dict[str, str]:
        return {
            "페이지": str(page_no),
            "번호": str(row_no),
            "등록번호": str(row.get("등록번호", "")).strip(),
            "검색회사명": str(row.get("상호", "")).strip(),
            "검색대표자명": str(row.get("대표자", "")).strip(),
            "검색회사주소": str(row.get("소재지", "")).strip(),
        }

    # === 신규 ===
    def get_request_context(self) -> Tuple[str, Dict[str, str], str]:
        current_url = (self.current_search_url or self.driver.current_url or "").strip()
        if not current_url:
            raise ValueError("현재 검색 URL이 없습니다.")

        parsed = urlparse(current_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params: Dict[str, str] = dict(parse_qsl(parsed.query, keep_blank_values=True))

        # currentPageNo는 매 요청마다 덮어쓸 거라 제거
        params.pop("currentPageNo", None)

        cookie_str = (self.current_cookie_str or "").strip()
        if not cookie_str:
            raise ValueError("현재 쿠키 문자열이 없습니다.")

        return base_url, params, cookie_str

    # === 신규 ===
    def fetch_page_html(
            self,
            base_url: str,
            base_params: Dict[str, str],
            page_no: int,
            cookie_str: str,
            referer: str,
    ) -> str:
        params = dict(base_params)
        params["currentPageNo"] = str(page_no)

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "cookie": cookie_str,
            "host": "www.keca.or.kr",
            "pragma": "no-cache",
            "referer": referer,
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

        request_url = f"{base_url}?{urlencode(params, doseq=True)}"
        self.log_signal_func(f"요청 URL: {request_url}")

        if not self.api_client:
            raise ValueError("api_client 가 초기화되지 않았습니다.")

        # APIClient.get 이 params를 지원하면 그대로 쓰고,
        # 지원하지 않으면 완성 URL로 다시 호출
        html_text = self.api_client.get(
            base_url,
            headers=headers,
            params=params
        )

        if not html_text:
            raise ValueError(f"page={page_no} 응답이 비어 있습니다.")

        return str(html_text)

    def parse_company_table(self, html_text: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html_text, "html.parser")

        table = soup.select_one("table.txtC")
        if not table:
            self.log_signal_func("⚠️ table.txtC 를 찾지 못했습니다.")
            return []

        headers: List[str] = []
        for th in table.select("thead th"):
            key = th.get_text(" ", strip=True)
            if key:
                headers.append(key)

        if not headers:
            self.log_signal_func("⚠️ thead th 를 찾지 못했습니다.")
            return []

        tbody = table.select_one("tbody")
        if not tbody:
            self.log_signal_func("⚠️ tbody 를 찾지 못했습니다.")
            return []

        rows: List[Dict[str, str]] = []
        tr_list = tbody.find_all("tr", recursive=False)

        for tr in tr_list:
            tds = tr.find_all("td", recursive=False)
            if not tds:
                continue

            row_text = tr.get_text(" ", strip=True)
            if "검색된 정보가 없습니다" in row_text:
                return []

            obj: Dict[str, str] = {}

            for idx, th_text in enumerate(headers):
                value = ""
                if idx < len(tds):
                    td = tds[idx]
                    value = td.get_text(" ", strip=True)
                obj[th_text] = value

            # 상호의 a href 안에 js_detailAction 값이 있으면 같이 보관
            if len(tds) >= 2:
                a_tag = tds[1].find("a")
                if a_tag:
                    href = (a_tag.get("href") or "").strip()
                    m = re.search(r"js_detailAction\('([^']+)'\s*,\s*'([^']+)'\)", href)
                    if m:
                        obj["_detail_id"] = m.group(1)
                        obj["_detail_region_cd"] = m.group(2)

            rows.append(obj)

        return rows


    def fetch_all_company_list(self) -> None:
        base_url, base_params, cookie_str = self.get_request_context()
        referer = self.site_url

        all_items: List[Dict[str, str]] = []
        page_no = 1
        row_no = 1

        while self.running:
            try:
                html_text = self.fetch_page_html(
                    base_url=base_url,
                    base_params=base_params,
                    page_no=page_no,
                    cookie_str=cookie_str,
                    referer=referer,
                )

                page_items = self.parse_company_table(html_text)

                if not page_items:
                    self.log_signal_func(f"✅ page={page_no} 데이터 없음 -> 종료")
                    break

                excel_page_items: List[Dict[str, str]] = []
                for item in page_items:
                    excel_page_items.append(
                        self.map_row_for_excel(item, row_no=row_no, page_no=page_no)
                    )
                    row_no += 1

                self.excel_data_list.extend(excel_page_items)
                self.log_signal_func(f"✅ page={page_no} 수집 건수: {len(excel_page_items)} / 누적: {len(self.excel_data_list)}")

                self.excel_driver.append_to_csv(
                    self.csv_filename,
                    excel_page_items,
                    self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )

                page_no += 1
                time.sleep(0.2)

            except Exception as e:
                self.log_signal_func(f"⚠️ page={page_no} 처리 중 예외: {e}")
                break


    def cleanup(self) -> None:
        self.log_signal_func("🧹 cleanup 시작")

        try:
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
            self.log_signal_func("🔌 driver.quit 시작")
            self.driver.quit()
            self.driver = None
            self.log_signal_func("🔌 driver.quit 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            self.log_signal_func("🔌 selenium_driver.quit 시작")
            self.selenium_driver.quit()
            self.selenium_driver = None
            self.log_signal_func("🔌 selenium_driver.quit 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            self.log_signal_func("🔌 api_client.close 시작")
            self.api_client.close()
            self.log_signal_func("🔌 api_client.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            self.log_signal_func("🔌 file_driver.close 시작")
            self.file_driver.close()
            self.log_signal_func("🔌 file_driver.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            self.log_signal_func("🔌 excel_driver.close 시작")
            self.excel_driver.close()
            self.log_signal_func("🔌 excel_driver.close 완료")
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")

        self.log_signal_func("🧹 cleanup 완료")