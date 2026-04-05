# src/workers/main/api_naver_place_url_all_set_worker.py
import os
import time
from typing import List, Optional
import random

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverLandRealEstateDetailSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.brokerage_yn = None
        self.eng = None
        self.article_sort_type = None
        self.to_date = None
        self.fr_date = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None

        self.site_name: str = "네이버 부동산"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.driver = None
        self.selenium_driver = None
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.folder_path: str = ""
        self.out_dir: str = "output"

        self.naver_loc_all_real_detail = None
        self.detail_region_article_list = None


    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 정지
    def cleanup(self) -> None:
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.log_signal_func(f"[cleanup] driver.quit 실패: {e}")
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
                self.selenium_driver.quit()
        except Exception as e:
            self.log_signal_func(f"[cleanup] selenium_driver.quit 실패: {e}")
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
        self.cleanup()
        self.log_signal_func("✅ stop 완료")


    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(1200)

    # 프로그램 실행
    def main(self) -> bool:
        self.log_signal_func(" main 시작")

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

        # 1. 지역세팅
        # [전체 상세 지역] 목록
        self.naver_loc_all_real_detail = self.file_driver.read_json_array_from_resources(
            "korea_eup_myeon_dong.json",
            "customers/naver_land_real_estate_detail/region",
        )
        # [선택한 지역] 목록
        region_key_set = {
            (item.get("시도"), item.get("시군구"), item.get("읍면동"))
            for item in self.region
        }
        # [선택한 상세 지역] 목록
        self.detail_region_article_list = [
            item
            for item in self.naver_loc_all_real_detail
            if (item.get("시도"), item.get("시군구"), item.get("읍면동")) in region_key_set
        ]
        self.log_signal_func(f"[선택한 상세 지역] 목록 : {self.detail_region_article_list}")

        # 2. filter 확인
        self.log_signal_func(f"filter 확인 : {self.setting_detail_all_style}")

        # 3. 등록일
        self.fr_date: str = str(self.get_setting_value(self.setting, "fr_date") or "").strip()
        self.to_date: str = str(self.get_setting_value(self.setting, "to_date") or "").strip()
        self.log_signal_func(f"등록 시작일 : {self.fr_date}")
        self.log_signal_func(f"등록 종료일 : {self.to_date}")

        # 4. 정렬방식
        self.article_sort_type: str = self.get_setting_value(self.setting, "articleSortType")
        self.log_signal_func(f"정렬 방식 : {self.to_date}")

        # 5. 영어컬럼 여부
        self.eng: str = self.get_setting_value(self.setting, "eng")
        self.log_signal_func(f"영어컬럼 여부 : {self.eng}")

        # 6. 부동산 중개사 기준 매물 가져오기 여부
        self.brokerage_yn: str = self.get_setting_value(self.setting, "brokerage_yn")
        self.log_signal_func(f"부동산 중개사 기준 매물 가져오기 여부 : {self.brokerage_yn}")

        # 7. 위 세팅에 맞는 매물 목록 크롤링
        self._crawl_article_list()



        return True


    def _crawl_article_list(self):
        for index, region_item in enumerate(self.detail_region_article_list,start=1):
            sido = region_item.get("시도")
            sigungu = region_item.get("시군구")
            eup_myeon_dong = region_item.get("읍면동")

            self.log_signal_func(f"[지역] {sido} {sigungu} {eup_myeon_dong}")

            data = region_item.get("data", {})
            coordinates = data.get("coordinates", {})

            x = coordinates.get("xCoordinate")
            y = coordinates.get("yCoordinate")

            url = self._build_region_map_url(x, y, self.setting_detail_all_style)

            self.log_signal_func(f"[URL] {url}")

            pro_value = (index / max(len(self.detail_region_article_list), 1)) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value
            time.sleep(random.uniform(2, 4))



    def _build_region_map_url(self, x, y, filter_items):
        params = [
            ("center", f"{x}-{y}"),
            ("showOnlySelectedRegion", "true"),
            ("zoom", "13"),
        ]

        for item in filter_items:
            self._append_filter_params(params, item, None)

        merged_params = {}

        for key, value in params:
            if key in ["center", "showOnlySelectedRegion", "zoom"]:
                merged_params[key] = value
                continue

            if key not in merged_params:
                merged_params[key] = value
                continue

            merged_params[key] = f"{merged_params[key]}-{value}"

        query = "&".join(
            f"{key}={value}"
            for key, value in merged_params.items()
            if value not in [None, ""]
        )

        return f"https://fin.land.naver.com/map?{query}"


    def _append_filter_params(self, params, item, parent_code=None):
        item_type = item.get("type")
        current_code = item.get("code")
        effective_code = current_code or parent_code

        if item_type == "title":
            for child in item.get("children", []):
                self._append_filter_params(params, child, effective_code)

            for child in item.get("items", []):
                self._append_filter_params(params, child, effective_code)
            return

        if item_type == "two_input":
            min_value = ""
            max_value = ""

            for sub in item.get("items", []):
                if sub.get("code") == "min":
                    min_value = sub.get("value")
                elif sub.get("code") == "max":
                    max_value = sub.get("value")

            if effective_code in ["dealPrice", "warrantyPrice", "managementFee", "rentPrice"]:
                if min_value not in [None, ""]:
                    min_value = f"{min_value}0000"
                if max_value not in [None, ""]:
                    max_value = f"{max_value}0000"

            if effective_code and (min_value != "" or max_value != ""):
                params.append((effective_code, f"{min_value}-{max_value}"))
            return

        if item_type == "input":
            value = item.get("value")
            if effective_code and value not in [None, ""]:
                params.append((effective_code, value))
            return

        if item_type == "checkbox":
            value = item.get("value")
            if current_code and value is True:
                params.append((current_code, "true"))
            return

        if item_type == "checkbox_single_group":
            checked_codes = [
                sub.get("code")
                for sub in item.get("items", [])
                if sub.get("value") is True and sub.get("code")
            ]

            if effective_code and checked_codes:
                params.append((effective_code, checked_codes[0]))
            return

        if item_type == "checkbox_multi_group":
            checked_codes = []

            for sub in item.get("items", []):
                if sub.get("value") is True and sub.get("code"):
                    checked_codes.append(sub.get("code"))

            for child in item.get("children", []):
                checked_codes.extend(self._collect_checked_codes_from_children(child))

            if effective_code and checked_codes:
                params.append((effective_code, "-".join(checked_codes)))
            return

        for child in item.get("children", []):
            self._append_filter_params(params, child, effective_code)

        for child in item.get("items", []):
            self._append_filter_params(params, child, effective_code)


    def _collect_checked_codes_from_children(self, item):
        checked_codes = []

        for sub in item.get("items", []):
            if sub.get("value") is True and sub.get("code"):
                checked_codes.append(sub.get("code"))

        for child in item.get("children", []):
            checked_codes.extend(self._collect_checked_codes_from_children(child))

        return checked_codes