# src/workers/main/api_comento_job_set_worker.py
import os
import random
import threading
import time
from typing import Any, Dict
from typing import List, Optional

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiComentoJobSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.site_login_url = "https://comento.kr/login"
        self.site_main_url = "https://comento.kr/job-wiki"
        self.driver = None
        self.selenium_driver = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "Base"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.folder_path: str = ""
        self.current_cookie_str: Optional[str] = None
        self.site_name: str = "COMENTO_JOB"
        self.out_dir: str = "output_comento_job"


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
                return False

            self.driver_cookie_set()
            self.fetch_all_list()

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")
            return False


    def _request_job_page(self, page: int) -> Dict[str, Any]:
        base_url = "https://comento.kr/api/job-wiki/index"

        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://comento.kr/job-wiki",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }

        if self.current_cookie_str:
            headers["cookie"] = self.current_cookie_str

        params = {
            "page": page,
            "perPage": 500,
            "jobGroup": "all",
        }

        resp = self.api_client.get(
            base_url,
            headers=headers,
            params=params
        )

        return resp


    def fetch_all_list(self) -> None:
        first_data = self._request_job_page(1)
        meta = first_data.get("meta") or {}

        last_page = int(meta.get("last_page") or 1)
        total = int(meta.get("total") or 0)
        self.total_cnt = total

        self.log_signal_func(f"✅ 전체 페이지: {last_page}, 전체 건수: {total}")

        for page in range(1, last_page + 1):
            if self._stop_event.is_set() or not self.running:
                self.log_signal_func("⏹️ fetch_all_list 중지")
                break

            data = first_data if page == 1 else self._request_job_page(page)
            items = data.get("data") or []

            rows = []
            for item in items:
                self.current_cnt += 1

                row = {
                    "아이디": item.get("id", ""),
                    "작성자": item.get("writer", ""),
                    "회사명": item.get("company", ""),
                    "직군": item.get("jobGroup", ""),
                    "직무": item.get("job", ""),
                    "경력": item.get("career", ""),
                    "설명": item.get("description", ""),
                    "역량": item.get("competency", ""),
                    "장점": item.get("advantage", ""),
                    "단점": item.get("disAdvantage", ""),
                    "수정일시": item.get("updatedAt", ""),
                }
                rows.append(row)

            self.excel_driver.append_to_csv(
                self.csv_filename,
                rows,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

            pro: float = (page / last_page) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro)
            self.before_pro_value = pro

            self.log_signal_func(f"✅ page={page}/{last_page}, 저장건수={self.current_cnt}/{self.total_cnt}")

            time.sleep(random.uniform(1, 2))


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



    def wait_for_user_confirmation(self) -> None:
        self.driver.get(self.site_login_url)
        event = threading.Event()
        self.msg_signal_func("로그인 완료 후 OK를 눌러주세요", "info", event)

        while not event.wait(0.2):
            if self._stop_event.is_set():
                return

        if self._stop_event.is_set():
            return

        self.driver.get(self.site_main_url)
        self.log_signal_func("✅ 직무소개 진입 완료")


    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.log_signal_func("✅ driver_set 완료")

        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(1200)

    # 정지
    def cleanup(self) -> None:
        try:
            if self.csv_filename:
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


    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()
        self.cleanup()
        self.log_signal_func("✅ stop 완료")


    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()