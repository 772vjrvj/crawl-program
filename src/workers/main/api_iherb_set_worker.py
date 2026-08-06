import os
import random
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pyautogui
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.repositories.worker_db_repository import WorkerDbRepository
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiIherbSetLoadWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.base_main_url: str = "https://kr.iherb.com"
        self.sub_url: str = (
            "https://kr.iherb.com/pr/"
            "doctor-s-best-alpha-lipoic-acid-150-150-mg-120-veggie-caps"
        )
        self.site_name: str = "iHerb"
        self.out_dir: str = "output"

        self.numbers_file_path: str = ""
        self.folder_path: str = ""
        self.auto_save_yn: bool = False
        self.st_page: int = 1
        self.ed_page: int = 1

        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.driver = None
        self.file_driver: Optional[FileUtils] = None
        self.selenium_driver: Optional[SeleniumUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None

        self.worker_name: str = "iherb"
        self.detail_table_name: str = "iherb"
        self.db_repository: Optional[WorkerDbRepository] = None

        self._cleaned_up: bool = False

    # 초기화
    def init(self) -> bool:
        self.log_signal_func("크롤링 시작 ========================================")

        try:
            self.st_page = self._positive_int(
                self.get_setting_value(self.setting, "st_page"), 1
            )
            self.ed_page = self._positive_int(
                self.get_setting_value(self.setting, "ed_page"), self.st_page
            )

            if self.ed_page < self.st_page:
                self.log_signal_func(
                    f"❌ 종료 번호({self.ed_page})는 시작 번호({self.st_page})보다 작을 수 없습니다."
                )
                return False

            configured_path = str(
                self.get_setting_value(self.setting, "numbers_file_path") or ""
            ).strip()
            self.numbers_file_path = self._resolve_numbers_file_path(configured_path)

            self.folder_path = str(
                self.get_setting_value(self.setting, "folder_path") or ""
            ).strip()
            self.auto_save_yn = bool(
                self.get_setting_value(self.setting, "auto_save_yn")
            )

            self.log_signal_func(f"✅ 품번 파일 : {self.numbers_file_path}")
            self.log_signal_func(f"✅ 시작 번호 : {self.st_page}")
            self.log_signal_func(f"✅ 종료 번호 : {self.ed_page}")
            self.log_signal_func(f"✅ 엑셀 자동 저장 여부 : {self.auto_save_yn}")

            if not os.path.isfile(self.numbers_file_path):
                self.log_signal_func(
                    "❌ 품번 파일을 찾을 수 없습니다. "
                    f"파일 위치를 확인해주세요: {self.numbers_file_path}"
                )
                return False

            self.driver_set(False)

            if not self.db_set():
                return False

            screen_width, screen_height = pyautogui.size()
            self.driver.set_window_size(screen_width, screen_height)
            self.driver.set_window_position(0, 0)
            self.driver.get(self.base_main_url)
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 초기화 실패: {e}")
            return False

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.selected_country()
            time.sleep(3)

            all_numbers = self.read_numbers_from_file(self.numbers_file_path)
            numbers = all_numbers[self.st_page - 1:self.ed_page]

            self.total_cnt = len(numbers)
            self.log_signal_func(f"전체 품번 수 : {len(all_numbers)} 개")
            self.log_signal_func(f"이번 작업 대상 : {self.total_cnt} 개")

            if self.total_cnt == 0:
                self.finish_job("FAIL", "설정한 범위에 수집할 품번이 없습니다.")
                return False

            for index, num in enumerate(numbers, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                row_start_at = self._now_db()
                try:
                    row = self.data_set(num)
                    row_end_at = self._now_db()
                    self.insert_detail_row(
                        row,
                        row_status="SUCCESS",
                        row_start_at=row_start_at,
                        row_end_at=row_end_at,
                    )
                except Exception as e:
                    row_end_at = self._now_db()
                    error_message = f"품번 {num} 수집 실패: {e}"
                    self.log_signal_func(f"❌ {error_message}")
                    self.insert_detail_row(
                        self._build_failed_row(num),
                        row_status="FAIL",
                        row_error_message=error_message,
                        row_start_at=row_start_at,
                        row_end_at=row_end_at,
                    )

                self.current_cnt = index
                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value

                time.sleep(random.uniform(1, 1.5))

            if self.db_repository and self.db_repository.status == "RUNNING":
                if self.running:
                    self.finish_job("SUCCESS")
                else:
                    self.finish_job("STOP", "사용자 중단")

            return True

        except Exception as e:
            self.log_signal_func(f"🚨 예외 발생: {e}")
            self.finish_job("FAIL", str(e))
            return False

    # 국가 통화 설정
    def selected_country(self) -> None:
        wait = WebDriverWait(self.driver, 10)

        button = wait.until(
            EC.element_to_be_clickable((By.CLASS_NAME, "selected-country-wrapper"))
        )
        button.click()

        wait.until(
            EC.visibility_of_element_located((By.CLASS_NAME, "selection-list-wrapper"))
        )

        texts = ["일본", "한국어", "USD ($)", "미터법(kg, cm)"]
        for idx, text in enumerate(texts):
            inputs = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "input.search-input.gh-dropdown-search.gh-fake-input")
                )
            )
            if idx >= len(inputs):
                raise RuntimeError(
                    f"국가/언어/통화 설정 입력 박스 부족: idx={idx}, inputs={len(inputs)}"
                )

            inp = inputs[idx]
            inp.click()
            inp.clear()
            inp.send_keys(text)
            inp.send_keys(Keys.ENTER)
            self.log_signal_func(f"✅ '{text}' 선택 입력 및 엔터 완료")
            time.sleep(1.5)

        save_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.save-selection.gh-btn.gh-btn-primary")
            )
        )
        save_button.click()

    # 상세 수집
    def data_set(self, num: str) -> Dict[str, Any]:
        sub_url = f"{self.sub_url}/{num}"
        self.driver.get(sub_url)

        obj: Dict[str, Any] = {
            "product_no": num,
            "discount_period": "해당없음",
            "discount_percent": "해당없음",
            "price": "해당없음",
            "stock": "해당없음",
        }

        title_text = ""
        expiration_date_text = ""

        try:
            title_text = self.driver.find_element(
                By.CSS_SELECTOR, "div.discount-title"
            ).text.strip()
        except Exception:
            pass

        try:
            expiration_date_text = self.driver.find_element(
                By.CSS_SELECTOR, "span.expiration-date"
            ).text.strip()
        except Exception:
            pass

        full_text = f"{title_text} {expiration_date_text}".strip()

        if "슈퍼 세일" in full_text:
            obj["discount_period"] = "SS"
        else:
            date_match = re.search(
                r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*"
                r"(오전|오후)\s*(\d{1,2})시(?:에)?",
                full_text,
            )
            if date_match:
                year, month, day, am_pm, hour_text = date_match.groups()
                hour = int(hour_text)
                if am_pm == "오후" and hour != 12:
                    hour += 12
                elif am_pm == "오전" and hour == 12:
                    hour = 0

                dt = datetime(int(year), int(month), int(day), hour)
                obj["discount_period"] = dt.strftime("%Y-%m-%d")

        percent_match = re.search(r"(\d+%)", full_text)
        if percent_match:
            obj["discount_percent"] = percent_match.group(1)

        try:
            for element in self.driver.find_elements(By.CSS_SELECTOR, "span.list-price"):
                price_text = element.text.strip()
                if price_text:
                    obj["price"] = price_text
                    break

            if obj["price"] == "해당없음":
                fallback = self.driver.find_element(
                    By.CSS_SELECTOR, "div.price-inner-text > p"
                ).text.strip()
                if fallback:
                    obj["price"] = fallback
        except Exception:
            pass

        try:
            prohibited = self.driver.find_element(
                By.CSS_SELECTOR, "span.title.title-prohibited"
            )
            if "판매 제외" in prohibited.text:
                obj["price"] = "해당없음"
        except Exception:
            pass

        try:
            obj["stock"] = self.driver.find_element(
                By.CSS_SELECTOR, "strong.text-primary"
            ).text.strip()
        except Exception:
            pass

        self.log_signal_func(f"📦 수집 결과: {obj}")
        return obj

    # 드라이버 세팅
    def driver_set(self, headless: bool) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.selenium_driver = SeleniumUtils(headless)
        self.driver = self.selenium_driver.start_driver(1200)

    # DB Repository
    def db_set(self) -> bool:
        config_data = self.read_runtime_customer_config(
            customer_name=self.worker_name
        )
        column_defs = config_data.get("columns") or []

        if not isinstance(column_defs, list) or not column_defs:
            self.log_signal_func("❌ [config] columns가 없거나 형식이 올바르지 않습니다.")
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
                detail_log_fields=("product_no", "price", "stock"),
            )
        except Exception as e:
            self.log_signal_func(f"❌ [DB] Repository 생성 실패: {e}")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        return self.db_repository.initialize(schema_files, start_job=True)

    def insert_detail_row(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        if not self.db_repository:
            self.log_signal_func("❌ [DB] Repository 없음 - detail 저장 실패")
            return False

        return self.db_repository.insert_detail(
            row,
            row_status=row_status,
            row_error_message=row_error_message,
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        if self.db_repository:
            self.db_repository.set_job_result(status, error_message)

    def export_detail_to_excel(self) -> bool:
        if not self.excel_driver:
            self.log_signal_func("❌ [엑셀] excel_driver 없음")
            return False
        if not self.db_repository:
            self.log_signal_func("❌ [엑셀] DB Repository 없음")
            return False

        excel_columns, excel_rows = self.db_repository.get_excel_data()
        if not excel_rows:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        excel_filename = f"{self.site_name}_{self.db_repository.job_id}.xlsx"
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
            if self.db_repository.status == "RUNNING":
                self.db_repository.set_job_result("FAIL", "비정상 종료")

            if self.db_repository.finish_job():
                self.log_signal_func("✅ [DB] hist 최종 업데이트 완료")
            else:
                self.log_signal_func("❌ [DB] hist 최종 업데이트 실패")

            if self.auto_save_yn:
                if self.export_detail_to_excel():
                    self.log_signal_func("✅ [엑셀] detail 자동 저장 완료")
                else:
                    self.log_signal_func("❌ [엑셀] detail 자동 저장 실패")
            else:
                self.log_signal_func("ℹ️ [엑셀] 자동 저장 미사용(auto_save_yn=False)")

        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")

    # 정리
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        self.finalize_db_and_excel()

        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.log_signal_func(f"[cleanup] driver.quit 실패: {e}")
        finally:
            self.driver = None

        try:
            if self.db_repository:
                self.db_repository.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] db_repository.close 실패: {e}")
        finally:
            self.db_repository = None

        for name, target in (
                ("file_driver", self.file_driver),
                ("excel_driver", self.excel_driver),
        ):
            try:
                if target and hasattr(target, "close"):
                    target.close()
            except Exception as e:
                self.log_signal_func(f"[cleanup] {name}.close 실패: {e}")

        self.file_driver = None
        self.excel_driver = None
        self.selenium_driver = None
        self._cleaned_up = True

    # 마무리
    def destroy(self) -> None:
        self.cleanup()
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("=============== 크롤링 종료중...")
        time.sleep(2.5)
        self.log_signal_func("=============== 크롤링 종료")
        self.progress_end_signal.emit()

    # 중지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self.finish_job("STOP", "사용자 중단")
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _runtime_base_dir() -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.abspath(os.getcwd())

    def _resolve_numbers_file_path(self, configured_path: str) -> str:
        path = configured_path or os.path.join("file", "numbers.txt")
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isabs(path):
            path = os.path.join(self._runtime_base_dir(), path)
        return os.path.normpath(os.path.abspath(path))

    @staticmethod
    def read_numbers_from_file(file_path: str) -> List[str]:
        numbers: List[str] = []
        with open(file_path, "r", encoding="utf-8-sig") as file:
            for line_no, line in enumerate(file, start=1):
                value = line.strip()
                if not value:
                    continue
                if not value.isdigit():
                    raise ValueError(
                        f"numbers.txt {line_no}번째 줄이 숫자가 아닙니다: {value}"
                    )
                numbers.append(value)
        return numbers

    @staticmethod
    def _build_failed_row(num: str) -> Dict[str, Any]:
        return {
            "product_no": num,
            "discount_period": "해당없음",
            "discount_percent": "해당없음",
            "price": "해당없음",
            "stock": "해당없음",
        }

    @staticmethod
    def _now_db() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]