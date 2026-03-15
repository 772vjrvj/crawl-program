# src/workers/main/api_naver_blog_contents_set_load_worker.py
import json
import os
import random
import re
import threading
import time
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from src.core.global_state import GlobalState
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverBlogContentsSetLoadWorker(BaseApiWorker):

    # 초기화
    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        self._stop_event = threading.Event()

        self.setting: Any = setting
        self.blog_id: Optional[str] = None
        self.category_list: List[Dict[str, Any]] = []
        self.cookies: Optional[Dict[str, str]] = None
        self.keyword: Optional[str] = None

        self.base_main_url: str = "https://m.blog.naver.com"
        self.base_url: str = ""
        self.site_name: str = "네이버 블로그 글조회"

        self.running: bool = True
        self.driver: Any = None

        self.total_cnt: int = 0
        self.total_pages: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.columns: Optional[List[str]] = None
        self.file_driver: Optional[FileUtils] = None
        self.selenium_driver: Optional[SeleniumUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.current_cookie_str: Optional[str] = None
        self.init_flag = False

        self.csv_filename: Optional[str] = None
        self.folder_path: str = ""
        self.out_dir: str = "output_naver_blog_contents"

    # 초기화
    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화 실행 완료")
                return True

            self.driver_set()
            self.driver.get(self.base_main_url)
            time.sleep(2)
            self.driver_cookie_set()
            self.log_signal_func("✅ init 완료")
            self.init_flag = True
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func(f"setting : {self.setting}")
            self.log_signal_func(f"선택 항목 : {self.columns}")

            state = GlobalState()
            worker_obj = state.get(state.WORKER_OBJ)
            self.blog_id = worker_obj.get("blog_id")

            st_page = int(self.get_setting_value(self.setting, "st_page"))
            ed_page = int(self.get_setting_value(self.setting, "ed_page"))
            category_no = int(self.get_setting_value(self.setting, "url_select"))
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.total_pages = max(0, ed_page - st_page + 1)
            self.log_signal_func(f"요청 페이지 수 {self.total_pages} 개")
            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))
            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )
            for pg in range(st_page, ed_page + 1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break
                items = self.fetch_search_results(pg, category_no)
                if not items:
                    break
                self.fetch_search_detail_results(items, self.csv_filename, self.columns)
                pro_value = (pg / self.total_pages) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"🚨 예외 발생: {e}")
            return False

    def fetch_search_detail_results(
            self,
            items: List[Dict[str, Any]],
            csv_filename: str,
            columns: List[str]
    ) -> None:
        result_list: List[Dict[str, Any]] = []

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "referer": f"https://m.blog.naver.com/{self.blog_id}",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        }

        for index, item in enumerate(items):
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            url = str(item.get("URL") or "").strip()
            if not url:
                continue

            html = self.api_client.get(url=url, headers=headers) if self.api_client else None

            if html:
                soup = BeautifulSoup(html, "html.parser")
                content_area = soup.find("div", class_="se-main-container")

                if content_area:
                    # ❌ id가 'ad-'로 시작하는 모든 하위 요소 제거
                    for ad_div in content_area.find_all(id=lambda x: x and x.startswith("ad-")):
                        ad_div.decompose()

                    text = content_area.get_text(separator="\n", strip=True)
                    item["내용"] = text
                else:
                    item["내용"] = ""

                self.log_signal_func(f"item : {item}")
                result_list.append(item)

            if len(result_list) >= 5:
                if self.excel_driver:
                    self.excel_driver.append_to_csv(
                        csv_filename,
                        result_list,
                        columns,
                        folder_path=self.folder_path,
                        sub_dir=self.out_dir
                    )

            time.sleep(random.uniform(1, 1.5))


        if result_list:
            self.excel_driver.append_to_csv(
                csv_filename,
                result_list,
                columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.selenium_driver = SeleniumUtils(headless=True, debug=True, log_func=self.log_signal_func)
        self.driver = self.selenium_driver.start_driver(1200)
        self.log_signal_func("✅ driver_set 완료")

    # 로그인 확인 / 쿠키 세팅
    def driver_cookie_set(self) -> None:
        self.log_signal_func("📢 쿠키 세팅 시작")

        cnt = 0
        cookie_parts: List[str] = []

        try:
            if not self.driver:
                self.log_signal_func("⚠️ driver가 없어 쿠키 세팅을 건너뜁니다.")
                return

            cookies = self.driver.get_cookies()

            for cookie in cookies:
                name = cookie.get("name")
                value = cookie.get("value")
                if name and value:
                    cookie_parts.append(f"{name}={value}")

                    if self.api_client:
                        self.api_client.cookie_set(name, value)

                    cnt += 1

            self.current_cookie_str = "; ".join(cookie_parts)

        except Exception as e:
            self.log_signal_func(f"⚠️ 쿠키 복사 중 예외: {e}")

        self.log_signal_func(f"📢 쿠키 세팅 완료 (count={cnt})")

    # 목록조회
    def fetch_search_results(self, page: int, category_no: int) -> List[Dict[str, Any]]:
        result_list: List[Dict[str, Any]] = []

        if not self.blog_id:
            self.log_signal_func("❌ blog_id가 없습니다.")
            return result_list

        url = f"https://m.blog.naver.com/api/blogs/{self.blog_id}/post-list"

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "referer": f"https://m.blog.naver.com/{self.blog_id}?categoryNo={category_no}&tab=1",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        }

        params = {
            "categoryNo": category_no,
            "itemCount": "24",
            "page": page
        }

        res_json = self.api_client.get(url=url, headers=headers, params=params) if self.api_client else None

        if res_json and res_json.get("isSuccess"):
            items = res_json.get("result", {}).get("items", [])

            for item in items:
                log_no = item.get("logNo")
                title = item.get("titleWithInspectMessage", "")
                if log_no:
                    result_list.append({
                        "no": log_no,
                        "제목": title,
                        "내용": "",
                        "URL": f"https://m.blog.naver.com/PostView.naver?blogId={self.blog_id}&logNo={log_no}&navType=by"
                    })

        return result_list

    # 카테고리 목록 조회
    def get_list(self, blog_url: str) -> List[Dict[str, Any]]:
        try:
            self.init()
            match = re.match(r"https?://blog\.naver\.com/([^/?#]+)", blog_url)
            if not match:
                raise ValueError("블로그 URL 형식이 잘못되었습니다.")
            state = GlobalState()
            self.blog_id = match.group(1)
            state.set(GlobalState.WORKER_OBJ, {
                "blog_id": match.group(1)
            })

            url = f"https://m.blog.naver.com/api/blogs/{self.blog_id}/category-list"

            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "referer": f"https://m.blog.naver.com/{self.blog_id}?tab=1",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
            }

            res_json = self.api_client.get(url=url, headers=headers) if self.api_client else None

            if res_json and res_json.get("isSuccess") is True:
                self.category_list = res_json.get("result", {}).get("mylogCategoryList", [])
                return [
                    {"key": c["categoryName"], "value": c["categoryNo"]}
                    for c in self.category_list
                    if c.get("categoryName") != "구분선"
                ]

            return []

        except Exception as e:
            self.log_signal_func(f"블로그 목록 조회 중 에러: {e}")
            return []


    # 정리
    def cleanup(self) -> None:
        try:
            if self.csv_filename and self.excel_driver:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
                    keep_csv=True
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
                self.csv_filename = None
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
                try:
                    self.selenium_driver.quit()
                except Exception:
                    pass
        finally:
            self.selenium_driver = None

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")
        finally:
            self.file_driver = None

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

        self.api_client = None

    # 중지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()