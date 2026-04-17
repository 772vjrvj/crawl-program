import os
import time
from typing import Any, Dict, List, Optional
import random
import json
from decimal import Decimal, InvalidOperation

from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
from src.utils.time_utils import yyyy_mm_dd_to
from urllib.parse import quote
from pyproj import Transformer

class ApiNaverLandRealEstateDetailSetWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        self.base_amount = None
        self.eng_yn = None
        self.remove_duplicate_yn = None
        self.filter_data = None
        self.brokerage_yn = None
        self.link_yn = None
        self.detail_column_yn = None
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

        self.folder_path: str = ""
        self.out_dir: str = "output"

        self.naver_loc_all_real_detail = None
        self.detail_region_article_list = None
        self.work_items: list[dict[str, Any]] = []

        self.list_api_url: str = "https://fin.land.naver.com/front-api/v1/article/boundedArticles"
        self.agent_detail_url: str = "https://fin.land.naver.com/front-api/v1/article/agent"
        self.detail_api_url: str = "https://fin.land.naver.com/front-api/v1/article/basicInfo"
        self.article_key_url: str = "https://fin.land.naver.com/front-api/v1/article/key"
        self.complex_api_url: str = "https://fin.land.naver.com/front-api/v1/complex"
        self.url: str = "https://fin.land.naver.com"

        self.list_hook_js = None
        self.browser_fetch_json_js = None
        self.click_sort_button_js = None
        self.click_article_button_js = None

    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    def cleanup(self) -> None:
        try:
            self.excel_driver.convert_csv_to_excel_and_delete(
                csv_filename=self.csv_filename,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
                column_widths=[
                    {"컬럼": "간략설명", "너비": 49},
                    {"컬럼": "매물설명", "너비": 49}
                ]
            )
            self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

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

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(timeout=1200, view_mode="browser", window_size=(1600, 1000))

    def main(self) -> bool:
        self.log_signal_func(" main 시작")

        # 저장경로
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        # 파일명
        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

        # 영어컬럼 여부
        self.eng_yn: bool = self.get_setting_value(self.setting, "eng_yn")
        self.log_signal_func(f"영어컬럼 여부 : {self.eng_yn}")
        if self.eng_yn:
            self.columns = self._get_eng_columns()

        # 초기 파일 생성
        self.excel_driver.init_csv(
            self.csv_filename,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )

        self.filter_data = self.file_driver.read_json_array_from_resources(
            "filter_data.json",
            "customers/naver_land_real_estate_detail",
        )

        self._load_js_assets()

        # 1. 전체 지역 원본 로드
        self.naver_loc_all_real_detail = self.file_driver.read_json_array_from_resources(
            "korea_eup_myeon_dong.json",
            "customers/naver_land_real_estate_detail/region",
        )

        # 2. 등록일
        self.fr_date: str = str(self.get_setting_value(self.setting, "fr_date") or "").strip()
        self.to_date: str = str(self.get_setting_value(self.setting, "to_date") or "").strip()
        self.log_signal_func(f"등록 시작일 : {self.fr_date}")
        self.log_signal_func(f"등록 종료일 : {self.to_date}")

        # 3. 정렬방식
        self.article_sort_type: str = str(self.get_setting_value(self.setting, "articleSortType") or "").strip()
        self.log_signal_func(f"정렬 방식 : {self.article_sort_type}")

        # 4. 영어컬럼 여부
        self.eng: str = self.get_setting_value(self.setting, "eng")
        self.log_signal_func(f"영어컬럼 여부 : {self.eng}")

        # 5. 부동산 중개사 기준 매물 가져오기 여부
        self.brokerage_yn: bool = self.get_setting_value(self.setting, "brokerage_yn")
        self.log_signal_func(f"부동산 중개사 기준 매물 가져오기 여부 : {self.brokerage_yn}")

        # 6. 중복제거 여부
        self.remove_duplicate_yn: bool = self.get_setting_value(self.setting, "remove_duplicate_yn")
        self.log_signal_func(f"중복제거 여부 : {self.remove_duplicate_yn}")

        self.link_yn: bool = self.get_setting_value(self.setting, "link_yn")
        self.log_signal_func(f"링크 여부 : {self.link_yn}")

        self.detail_column_yn: bool = self.get_setting_value(self.setting, "detail_column_yn")
        self.log_signal_func(f"상세조회 여부 : {self.detail_column_yn}")

        self.base_amount: str = self.get_setting_value(self.setting, "baseAmount")
        self.log_signal_func(f"기준금액 : {self.base_amount}")


        # 7. 작업목록 생성
        self.work_items = []

        favorite_list = self.setting_region_filter_favorite
        if not isinstance(favorite_list, list):
            favorite_list = []

        checked_favorite_list = []

        for row in favorite_list:
            if isinstance(row, dict) and row.get("checked"):
                checked_favorite_list.append(row)

        # favorite가 있으면 기존 self.region, self.setting_detail_all_style는 사용하지 않음
        if checked_favorite_list:
            self.log_signal_func(f"[즐겨찾기 모드] 사용 즐겨찾기 수 : {len(checked_favorite_list)}")

            for fav_index, favorite in enumerate(checked_favorite_list, start=1):
                favorite_regions = favorite.get("regions") or []
                favorite_filters = favorite.get("filters") or []

                region_key_set = {
                    (item.get("시도"), item.get("시군구"), item.get("읍면동"))
                    for item in favorite_regions
                }

                detail_region_article_list = [
                    item
                    for item in self.naver_loc_all_real_detail
                    if (item.get("시도"), item.get("시군구"), item.get("읍면동")) in region_key_set
                ]

                self.work_items.append({
                    "type": "favorite",
                    "favorite_index": fav_index,
                    "regions": favorite_regions,
                    "filters": favorite_filters,
                    "detail_region_article_list": detail_region_article_list,
                })

                self.log_signal_func(
                    f"[즐겨찾기 {fav_index}] 지역 {len(favorite_regions)}개 / "
                    f"상세지역 {len(detail_region_article_list)}개"
                )
        else:
            self.log_signal_func("[기본 모드] 기존 지역/필터 사용")

            if not self.region:
                region_list = self.file_driver.read_json_array_from_resources(
                    "naver_loc_all_real.json",
                    "customers/naver_place_loc_all",
                ) or []

                self.region = [
                    {
                        "시도": item.get("시도"),
                        "시군구": item.get("시군구"),
                        "읍면동": item.get("읍면동"),
                        "value": bool(item.get("value", False)),
                    }
                    for item in region_list
                    if type(item) is dict and bool(item.get("value", False))
                ]

            region_key_set = {
                (item.get("시도"), item.get("시군구"), item.get("읍면동"))
                for item in (self.region or [])
            }

            detail_region_article_list = [
                item
                for item in self.naver_loc_all_real_detail
                if (item.get("시도"), item.get("시군구"), item.get("읍면동")) in region_key_set
            ]

            self.work_items.append({
                "type": "default",
                "favorite_index": 0,
                "regions": self.region or [],
                "filters": self.setting_detail_all_style or [],
                "detail_region_article_list": detail_region_article_list,
            })

            self.log_signal_func(f"[선택한 상세 지역] 목록 : {detail_region_article_list}")
            self.log_signal_func(f"filter 확인 : {self.setting_detail_all_style}")

        # 8. 작업목록에 따라 매물 목록 크롤링
        self._crawl_article_list()

        return True

    def _make_excel_hyperlink_value(self, url: Any, text: Any) -> str:
        url_text = str(url or "").strip()
        display_text = str(text or "").strip()

        if not url_text or not display_text:
            return display_text

        if display_text.startswith("__HYPERLINK__"):
            return display_text

        return "__HYPERLINK__" + json.dumps({
            "url": url_text,
            "text": display_text,
        }, ensure_ascii=False)

    def _make_hyperlink_cell(self, url: Any, text: Any) -> str:
        url_text = str(url or "").strip()
        display_text = str(text or "").strip()

        if not url_text or not display_text:
            return str(text or "").strip()

        return "__HYPERLINK__" + json.dumps({
            "url": url_text,
            "text": display_text,
        }, ensure_ascii=False)

    def _build_map_search_url(self, search_text: Any, lat: Any = "", lng: Any = "") -> str:
        search_value = str(search_text or "").strip()
        lat_value = str(lat or "").strip()
        lng_value = str(lng or "").strip()

        # 1. 주소(도로명/지번)가 있으면 무조건 검색 URL 우선
        if search_value:
            return f"https://map.naver.com/p/search/{quote(search_value)}"

        # 2. 주소가 없을 때만 위도/경도로 네이버 v5 좌표 URL
        if lat_value and lng_value:
            try:
                transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
                x, y = transformer.transform(float(lng_value), float(lat_value))
                return f"https://map.naver.com/v5/?c={x},{y},16,0,0,0,dh"
            except Exception:
                return ""

        return ""

    def _apply_excel_hyperlinks_to_row(self, rs: Dict[str, Any]) -> Dict[str, Any]:
        if not self.link_yn:
            return rs

        out = dict(rs or {})

        article_no = str(out.get("매물번호") or "").strip()
        full_addr = str(out.get("전체주소") or "").strip()
        url_text = str(out.get("URL") or "").strip()

        if article_no:
            out["매물번호"] = self._make_excel_hyperlink_value(
                f"{self.url}/articles/{article_no}",
                article_no,
            )

        road_addr = str(out.get("도로명주소") or "").strip()
        jibun = str(out.get("번지") or "").strip()

        search_addr = ""
        if road_addr:
            search_addr = full_addr
        elif jibun:
            search_addr = full_addr

        out["전체주소"] = self._make_hyperlink_cell(
            self._build_map_search_url(
                search_text=search_addr,
                lat=out.get("위도", ""),
                lng=out.get("경도", ""),
            ),
            full_addr,
        )

        if url_text:
            out["URL"] = self._make_excel_hyperlink_value(url_text, url_text)

        return out

    def _get_eng_columns(self) -> List[str]:
        return [
            "date",
            "atclNo",
            "atclNm",
            "tradTpNm",
            "hanPrc",
            "rentPrc",
            "ho",
            "flrInfo",
            "spc1",
            "spc2",
            "jibun",
            "atclFetrDesc",
            "tagList",
            "rltrNm",
            "phone",
            "direction",
            "ipjuday",
            "keyword",
            "atclUrl",
            "id",
            "searchRequirement",
            "atclCfmYmd",
            "rletTpNm",
            "articlePriceInfo",
            "supplySpaceName",
            "bildNm",
            "upperAtclNo",
            "parentYn",
            "sameAddrMinPrc",
            "sameAddrMaxPrc",
            "sameAddrCnt",
            "vrfcTpCd",
            "rank",
            "lat",
            "lng",
        ]

    def _build_article_price_info(self, out: Dict[str, Any]) -> str:
        price = str(out.get("매매가") or "").strip()
        warranty = str(out.get("보증금") or "").strip()
        rent = str(out.get("월세") or "").strip()

        if price:
            return price
        if warranty and rent:
            return f"{warranty}/{rent}"
        if warranty:
            return warranty
        if rent:
            return rent
        return ""

    def _build_search_requirement_text(self, out: Dict[str, Any]) -> str:
        parts: List[str] = []

        search_addr = str(out.get("검색 주소") or "").strip()
        search_rlet = str(out.get("검색 매물유형") or out.get("매물유형") or "").strip()
        search_trade = str(out.get("검색 거래유형") or out.get("거래유형") or "").strip()

        if search_addr:
            parts.append(search_addr)
        if search_rlet:
            parts.append(f"매물유형:{search_rlet}")
        if search_trade:
            parts.append(f"거래유형:{search_trade}")

        return " / ".join(parts)

    def _map_out_to_eng(self, out: Dict[str, Any]) -> Dict[str, Any]:
        eng_out: Dict[str, Any] = {
            "date": str(out.get("매물노출시작일") or ""),
            "atclNo": str(out.get("매물번호") or ""),
            "atclNm": str(out.get("상위매물명") or ""),
            "tradTpNm": str(out.get("거래유형") or ""),
            "hanPrc": str(out.get("매매가") or out.get("보증금/전세") or ""),
            "rentPrc": str(out.get("월세") or ""),
            "ho": "",
            "flrInfo": f'{str(out.get("해당층") or "")}/{str(out.get("전체층") or "")}',
            "spc1": str(out.get("공급면적") or ""),
            "spc2": str(out.get("전용면적") or ""),
            "jibun": str(out.get("번지") or ""),
            "atclFetrDesc": str(out.get("매물상세설명") or out.get("매물설명")),
            "tagList": str(out.get("매물태그") or ""),
            "rltrNm": str(out.get("중개사무소이름") or ""),
            "phone": str(out.get("중개사무소번호") or out.get("중개사핸드폰번호") or ""),
            "direction": str(out.get("방향정보") or ""),
            "ipjuday": str(out.get("매물확인일") or ""),
            "keyword": str(out.get("검색 주소") or ""),
            "atclUrl": str(out.get("URL") or ""),
            "id": "",
            "searchRequirement": self._build_search_requirement_text(out),
            "atclCfmYmd": str(out.get("등록일자") or ""),
            "rletTpNm": str(out.get("매물유형") or ""),
            "articlePriceInfo": self._build_article_price_info(out),
            "supplySpaceName": str(out.get("평수") or ""),
            "bildNm": str(out.get("상위매물동") or out.get("동이름") or ""),
            "upperAtclNo": str(out.get("상위매물번호") or ""),
            "parentYn": str(out.get("부모여부") or ""),
            "sameAddrMinPrc": str(out.get("동일주소최소가") or ""),
            "sameAddrMaxPrc": str(out.get("동일주소최대가") or ""),
            "sameAddrCnt": str(out.get("동일주소매물수") or ""),
            "vrfcTpCd": str(out.get("매물확인코드") or ""),
            "rank": "",
            "lat": str(out.get("위도") or ""),
            "lng": str(out.get("경도") or ""),
        }

        return eng_out

    def _load_js_assets(self) -> None:
        js_dir = "customers/naver_land_real_estate_detail/js"
        self.list_hook_js = self.file_driver.read_text_from_resources("list_hook.js", js_dir)
        self.browser_fetch_json_js = self.file_driver.read_text_from_resources("browser_fetch_json.js", js_dir)
        self.click_sort_button_js = self.file_driver.read_text_from_resources("click_sort_button.js", js_dir)
        self.click_article_button_js = self.file_driver.read_text_from_resources("click_article_button.js", js_dir)

    def _split_codes(self, code_value: Any) -> list[str]:
        code_text = str(code_value or "").strip()
        if not code_text:
            return []
        return [x.strip() for x in code_text.split("-") if str(x).strip()]

    def _find_name_by_code_in_items(self, items: list[dict[str, Any]], target_code: str) -> str:
        for item in items or []:
            item_code = str(item.get("code") or "").strip()
            item_name = str(item.get("name") or "").strip()

            if target_code in self._split_codes(item_code):
                return item_name

        return ""

    def _find_filter_name_by_index_and_code(self, filter_index: int, target_code: str) -> str:
        if not target_code:
            return ""

        filter_list = self.filter_data or []
        if filter_index >= len(filter_list):
            return ""

        target_filter = filter_list[filter_index] or {}

        found_name = self._find_name_by_code_in_items(target_filter.get("items", []) or [], target_code)
        if found_name:
            return found_name

        for child in target_filter.get("children", []) or []:
            found_name = self._find_name_by_code_in_items(child.get("items", []) or [], target_code)
            if found_name:
                return found_name

        return ""

    def _merge_list_item_with_representative(self, representative_info, article_info):
        row = dict(representative_info or {})

        merge_keys = [
            "spaceInfo",
            "brokerInfo",
            "articleDetail",
            "address",
            "priceInfo",
            "verificationInfo",
            "buildingInfo",
        ]

        for key in merge_keys:
            merged = dict(representative_info.get(key) or {})
            merged.update(article_info.get(key) or {})
            if merged:
                row[key] = merged

        for key, value in (article_info or {}).items():
            if key in merge_keys:
                continue
            if value not in [None, "", {}, []]:
                row[key] = value

        return row

    def _crawl_article_list(self):
        total_region_count = 0
        for work_item in self.work_items:
            total_region_count += len(work_item.get("detail_region_article_list") or [])

        done_region_count = 0

        def emit_region_progress() -> None:
            pro_value = (done_region_count / max(total_region_count, 1)) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

        for work_index, work_item in enumerate(self.work_items, start=1):
            current_filters = work_item.get("filters") or []
            current_region_list = work_item.get("detail_region_article_list") or []
            favorite_index = work_item.get("favorite_index", 0)
            work_type = work_item.get("type", "default")

            if work_type == "favorite":
                self.log_signal_func(
                    f"[즐겨찾기 작업 시작] {favorite_index} / "
                    f"지역수={len(current_region_list)}"
                )
                self.log_signal_func(f"[즐겨찾기 {favorite_index}] filter 확인 : {current_filters}")
            else:
                self.log_signal_func("[기본 작업 시작] 기존 지역/필터 기준")
                self.log_signal_func(f"[기본] filter 확인 : {current_filters}")

            for region_item in current_region_list:
                if not self.running:
                    self.log_signal_func("중단 요청 감지")
                    return

                done_region_count += 1

                sido = region_item.get("시도")
                sigungu = region_item.get("시군구")
                eup_myeon_dong = region_item.get("읍면동")

                if work_type == "favorite":
                    self.log_signal_func(
                        f"[즐겨찾기 {favorite_index}] "
                        f"[지역] {sido} {sigungu} {eup_myeon_dong}"
                    )
                else:
                    self.log_signal_func(f"[지역] {sido} {sigungu} {eup_myeon_dong}")

                data = region_item.get("data", {})
                coordinates = data.get("coordinates", {})

                x = coordinates.get("xCoordinate")
                y = coordinates.get("yCoordinate")

                url = self._build_region_map_url(x, y, current_filters)
                self.log_signal_func(f"[URL] {url}")

                success = False
                skip_current_region = False
                base_payload: dict[str, Any] = {}
                first_result: dict[str, Any] = {}

                for attempt in range(1, 4):

                    if not self.running:
                        return True

                    try:
                        self.log_signal_func(f"[지역 진입] 시도 {attempt}/3")

                        self.driver.get(url)
                        time.sleep(5)

                        self.log_signal_func("[후킹] 목록 후킹 설치 시작")
                        self._inject_list_hook()
                        time.sleep(2)
                        self.log_signal_func("[후킹] 목록 후킹 설치 끝")

                        try:
                            self.driver.execute_script("window.__naverListHookData = null;")
                            self.log_signal_func("[후킹] 지역 진입 후 hook 데이터 초기화")
                        except Exception as e:
                            self.log_signal_func(f"[후킹] 초기화 실패: {e}")

                        self.log_signal_func("[클릭] 매물 버튼 클릭 시도")
                        try:
                            self._click_article_button(wait_sec=5)
                        except Exception as e:
                            self.log_signal_func(f"[목록] 매물 버튼 없음/클릭 실패 -> 다음 지역으로 이동 / {e}")
                            skip_current_region = True
                            success = True
                            break

                        time.sleep(3)

                        # 정렬 전, 먼저 초기 목록 응답 확보
                        initial_hook_data: dict[str, Any] = self._get_first_list_hook_data(5)
                        initial_body_text: str = initial_hook_data.get("bodyText", "")
                        initial_response_json: dict[str, Any] = initial_hook_data.get("responseJson", {}) or {}

                        self.log_signal_func(f"[후킹-초기] 수신 여부={bool(initial_hook_data)}")
                        self.log_signal_func(f"[후킹-초기] bodyText 존재={bool(initial_body_text)}")
                        self.log_signal_func(f"[후킹-초기] responseJson 존재={bool(initial_response_json)}")

                        if not initial_body_text:
                            raise Exception("초기 목록 후킹 bodyText 없음")

                        try:
                            base_payload = json.loads(initial_body_text)
                        except Exception as e:
                            raise Exception(f"초기 bodyText json 파싱 실패: {e}")

                        first_result = initial_response_json.get("result", {}) or {}

                        if not first_result:
                            self.log_signal_func("[후킹-초기] 첫 응답 result 없음 -> 첫 페이지 재요청")
                            retry_res = self._browser_fetch_json(
                                url=self.list_api_url,
                                method="POST",
                                payload=base_payload,
                                wait_sec=30,
                            )

                            self.log_signal_func(
                                f"[후킹-초기 재요청] status={retry_res.get('status')} ok={retry_res.get('ok')}"
                            )

                            retry_json: dict[str, Any] = retry_res.get("json") or {}
                            first_result = retry_json.get("result", {}) or {}

                        if not first_result:
                            raise Exception("초기 첫 페이지 result 확보 실패")

                        initial_list: list[dict[str, Any]] = first_result.get("list", []) or []
                        initial_total_count: int = int(first_result.get("totalCount") or len(initial_list) or 0)

                        self.log_signal_func(
                            f"[목록-초기] count={len(initial_list)} "
                            f"total={initial_total_count} "
                            f"hasNext={first_result.get('hasNextPage')}"
                        )

                        # 조회 결과 자체가 없는 경우
                        if not initial_list or initial_total_count == 0:
                            self.log_signal_func("[목록] 조회 결과 없음 -> 다음 지역으로 이동")
                            skip_current_region = True
                            success = True
                            break

                        # 1건 이하이면 정렬 버튼이 없을 수 있으므로 스킵
                        if initial_total_count <= 1 or len(initial_list) <= 1:
                            self.log_signal_func("[정렬] 매물 1건 이하 -> 정렬 클릭 스킵")
                            success = True
                            break

                        # 2건 이상일 때만 정렬 시도
                        try:
                            self.driver.execute_script("window.__naverListHookData = null;")
                            self.log_signal_func("[후킹] 정렬 전 hook 데이터 초기화")
                        except Exception as e:
                            self.log_signal_func(f"[후킹] 초기화 실패: {e}")

                        try:
                            self.log_signal_func(f"[정렬] 정렬 클릭 시도 : {self.article_sort_type}")
                            self._click_sort_button_by_setting(wait_sec=5)
                            time.sleep(3)

                            sorted_hook_data: dict[str, Any] = self._get_first_list_hook_data(5)
                            sorted_body_text: str = sorted_hook_data.get("bodyText", "")
                            sorted_response_json: dict[str, Any] = sorted_hook_data.get("responseJson", {}) or {}

                            self.log_signal_func(f"[후킹-정렬] 수신 여부={bool(sorted_hook_data)}")
                            self.log_signal_func(f"[후킹-정렬] bodyText 존재={bool(sorted_body_text)}")
                            self.log_signal_func(f"[후킹-정렬] responseJson 존재={bool(sorted_response_json)}")

                            if not sorted_body_text:
                                raise Exception("정렬 후 목록 후킹 bodyText 없음")

                            try:
                                base_payload = json.loads(sorted_body_text)
                            except Exception as e:
                                raise Exception(f"정렬 후 bodyText json 파싱 실패: {e}")

                            first_result = sorted_response_json.get("result", {}) or {}

                            if not first_result:
                                self.log_signal_func("[후킹-정렬] 첫 응답 result 없음 -> 첫 페이지 재요청")
                                retry_res = self._browser_fetch_json(
                                    url=self.list_api_url,
                                    method="POST",
                                    payload=base_payload,
                                    wait_sec=30,
                                )

                                self.log_signal_func(
                                    f"[후킹-정렬 재요청] status={retry_res.get('status')} ok={retry_res.get('ok')}"
                                )

                                retry_json: dict[str, Any] = retry_res.get("json") or {}
                                first_result = retry_json.get("result", {}) or {}

                            if not first_result:
                                raise Exception("정렬 후 첫 페이지 result 확보 실패")

                        except Exception as e:
                            # 정렬 버튼이 없거나 정렬 실패해도 초기 목록으로 계속 진행
                            self.log_signal_func(f"[정렬] 버튼 없음 또는 정렬 실패 -> 초기 목록으로 진행 / {e}")

                        success = True
                        break

                    except Exception as e:
                        self.log_signal_func(
                            f"[지역 처리 실패] {sido} {sigungu} {eup_myeon_dong} "
                            f"/ 시도 {attempt}/3 / {e}"
                        )

                        if attempt < 3:
                            self.log_signal_func("[재시도] 화면 새로 로드 후 다시 시도")
                            time.sleep(2)
                        else:
                            self.log_signal_func("[재시도 실패] 3회 모두 실패하여 다음 지역으로 이동")

                if not success:
                    emit_region_progress()
                    continue

                if skip_current_region:
                    emit_region_progress()
                    time.sleep(random.uniform(1, 2))
                    continue

                items: list[dict[str, Any]] = self._collect_next_list_pages(
                    base_payload=base_payload,
                    first_result=first_result,
                )

                if not items:
                    self.log_signal_func("[목록] 수집된 매물 없음 -> 저장 스킵")
                    emit_region_progress()
                    time.sleep(random.uniform(1, 2))
                    continue

                if self.detail_column_yn:
                    self._collect_detail(items, region_item)
                else:
                    self._save_list_items(items, region_item)

                emit_region_progress()
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

    def _click_article_button(self, wait_sec: int = 5) -> None:
        end = time.time() + wait_sec
        last_reason = ""

        while time.time() < end:
            try:
                result = self.driver.execute_script(self.click_article_button_js) or {}

                if result.get("ok"):
                    self.log_signal_func(
                        f"[매물 버튼] 클릭 완료 / 타입={result.get('foundType', '')} / text={result.get('text', '')}"
                    )
                    return

                last_reason = str(result.get("reason") or "")
                self.log_signal_func(f"[매물 버튼] 대기중 / reason={last_reason}")

            except Exception as e:
                last_reason = str(e)
                self.log_signal_func(f"[매물 버튼] 클릭 실패: {e}")

            time.sleep(1)

        raise Exception(f"매물 버튼을 찾지 못했습니다. reason={last_reason}")

    def _click_sort_button_by_setting(self, wait_sec: int = 5) -> None:
        click_map: dict[str, tuple[str, int]] = {
            "RANKING_DESC": ("filterOrder1", 1),
            "PRICE_DESC": ("filterOrder2", 1),
            "PRICE_ASC": ("filterOrder2", 2),
            "DATE_DESC": ("filterOrder3", 1),
            "SPACE_DESC": ("filterOrder4", 1),
            "SPACE_ASC": ("filterOrder4", 2),
        }

        sort_id, click_count = click_map.get(self.article_sort_type or "", ("filterOrder1", 1))

        end = time.time() + wait_sec

        while time.time() < end:
            try:
                clicked = self.driver.execute_script(self.click_sort_button_js, sort_id, click_count)

                if clicked and clicked.get("ok"):
                    self.log_signal_func(f"[정렬] 클릭 완료 : {clicked.get('labelText')}")
                    return
            except Exception as e:
                self.log_signal_func(f"[정렬] 클릭 실패: {e}")

            time.sleep(1)

        raise Exception(f"정렬 버튼 클릭 실패: {self.article_sort_type}")

    def _inject_list_hook(self) -> None:
        script = self.list_hook_js.replace("__TARGET__", "/front-api/v1/article/boundedArticles")
        self.driver.execute_script(script)

    def _get_first_list_hook_data(self, wait_sec: int = 5):
        end = time.time() + wait_sec

        while time.time() < end:
            try:
                data = self.driver.execute_script("return window.__naverListHookData;")
                if data:
                    return data
            except Exception as e:
                self.log_signal_func(f"[후킹] 데이터 조회 실패: {e}")

            time.sleep(1)

        return {}

    def _browser_fetch_json(self, url: str, method: str = "GET", payload: dict[str, Any] = None, params: dict[str, Any] = None, wait_sec: int = 30) -> dict[str, Any]:
        script = self.browser_fetch_json_js
        self.driver.set_script_timeout(wait_sec)
        return self.driver.execute_async_script(script, url, method, payload, params)

    def _collect_next_list_pages(self, base_payload: dict[str, Any], first_result: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        use_date_filter: bool = bool(self.fr_date and self.to_date)

        def normalize_date_yyyymmdd(value: Any) -> str:
            return str(value or "").replace("-", "").replace(".", "").replace("/", "").strip()

        def get_confirm_date_from_info(info: dict[str, Any]) -> str:
            verification_info: dict[str, Any] = info.get("verificationInfo", {}) or {}
            return normalize_date_yyyymmdd(verification_info.get("articleConfirmDate", ""))

        def get_confirm_date_from_item(item: dict[str, Any]) -> str:
            info: dict[str, Any] = item.get("representativeArticleInfo", {}) or {}
            return get_confirm_date_from_info(info)

        def is_target_date(confirm_date: str) -> bool:
            if not use_date_filter:
                return True
            if not confirm_date:
                return False
            return self.fr_date <= confirm_date <= self.to_date

        def should_stop_by_date(page_list: list[dict[str, Any]]) -> bool:
            if not use_date_filter:
                return False

            for item in page_list:
                confirm_date: str = get_confirm_date_from_item(item)
                if confirm_date and confirm_date < self.fr_date:
                    return True

            return False

        def build_same_addr_meta(dup_info: dict[str, Any]) -> dict[str, Any]:
            article_info_list: list[dict[str, Any]] = dup_info.get("articleInfoList", []) or []
            rep_price_info: dict[str, Any] = dup_info.get("representativePriceInfo", {}) or {}
            rep_deal_price: dict[str, Any] = rep_price_info.get("dealPrice", {}) or {}

            deal_prices = []
            for row in article_info_list:
                price_info = row.get("priceInfo", {}) or {}
                deal_price = price_info.get("dealPrice")
                if deal_price not in [None, ""]:
                    deal_prices.append(deal_price)

            same_addr_cnt = len(article_info_list)
            same_addr_min = ""
            same_addr_max = ""

            if deal_prices:
                same_addr_min = min(deal_prices)
                same_addr_max = max(deal_prices)
            else:
                same_addr_min = rep_deal_price.get("minPrice", "")
                same_addr_max = rep_deal_price.get("maxPrice", "")

            return {
                "sameAddrCnt": same_addr_cnt,
                "sameAddrMinPrc": same_addr_min,
                "sameAddrMaxPrc": same_addr_max,
            }

        def apply_same_addr_meta(info: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
            rs = dict(info or {})
            rs.update(meta or {})
            return rs

        def enrich_parent_meta(
                info: dict[str, Any],
                representative_info: dict[str, Any],
                parent_yn: str,
        ) -> dict[str, Any]:
            rs = dict(info or {})
            rs["parentYn"] = parent_yn
            rs["upperArticleNumber"] = str(representative_info.get("articleNumber", "")).strip()
            rs["upperArticleName"] = str(representative_info.get("articleName", "")).strip()
            rs["upperDongName"] = str(representative_info.get("dongName", "")).strip()
            return rs

        def add_items(page_list: list[dict[str, Any]]) -> int:
            added_count = 0

            for item in page_list:
                representative_info: dict[str, Any] = item.get("representativeArticleInfo", {}) or {}
                duplicated_info: dict[str, Any] = item.get("duplicatedArticleInfo", {}) or {}
                article_info_list: list[dict[str, Any]] = duplicated_info.get("articleInfoList", []) or []

                confirm_date: str = get_confirm_date_from_info(representative_info)

                if not is_target_date(confirm_date):
                    continue

                # 1) 부동산 중개사 기준으로 가져오는 경우
                if self.brokerage_yn:
                    if article_info_list:
                        same_addr_meta = build_same_addr_meta(duplicated_info)

                        for article_info in article_info_list:
                            article_no: str = str(article_info.get("articleNumber", "")).strip()

                            if article_no:
                                merged_info = self._merge_list_item_with_representative(
                                    representative_info,
                                    article_info,
                                )
                                row = apply_same_addr_meta(merged_info, same_addr_meta)
                                row = enrich_parent_meta(row, representative_info, "N")

                                if self.remove_duplicate_yn:
                                    if article_no not in seen:
                                        seen.add(article_no)
                                        items.append(row)
                                        added_count += 1
                                else:
                                    items.append(row)
                                    added_count += 1
                        continue

                    article_no: str = str(representative_info.get("articleNumber", "")).strip()
                    confirm_date = get_confirm_date_from_info(representative_info)

                    if not is_target_date(confirm_date):
                        continue

                    if article_no:
                        if self.remove_duplicate_yn and article_no in seen:
                            continue
                        if self.remove_duplicate_yn:
                            seen.add(article_no)

                        single_info = dict(representative_info)
                        deal_price = ((single_info.get("priceInfo") or {}).get("dealPrice", ""))
                        single_info.update({
                            "sameAddrCnt": 1,
                            "sameAddrMinPrc": deal_price,
                            "sameAddrMaxPrc": deal_price,
                        })

                        single_info = enrich_parent_meta(single_info, representative_info, "Y")
                        items.append(single_info)
                        added_count += 1
                    continue

                # 2) 부동산 중개사 기준이 아닌 경우 -> 무조건 대표 1개만
                article_no: str = str(representative_info.get("articleNumber", "")).strip()
                if article_no:
                    if self.remove_duplicate_yn and article_no in seen:
                        continue

                    if self.remove_duplicate_yn:
                        seen.add(article_no)

                    if article_info_list:
                        same_addr_meta = build_same_addr_meta(duplicated_info)
                        row = apply_same_addr_meta(representative_info, same_addr_meta)
                        row = enrich_parent_meta(row, representative_info, "Y")
                        items.append(row)
                        added_count += 1
                    else:
                        single_info = dict(representative_info)
                        deal_price = ((single_info.get("priceInfo") or {}).get("dealPrice", ""))
                        single_info.update({
                            "sameAddrCnt": 1,
                            "sameAddrMinPrc": deal_price,
                            "sameAddrMaxPrc": deal_price,
                        })
                        single_info = enrich_parent_meta(single_info, representative_info, "Y")
                        items.append(single_info)
                        added_count += 1

            return added_count

        first_list: list[dict[str, Any]] = first_result.get("list", []) or []
        total_count: int = int(first_result.get("totalCount") or 0)

        self.log_signal_func(
            f"[목록] first "
            f"count={len(first_list)} "
            f"hasNext={first_result.get('hasNextPage')} "
            f"total={total_count}"
        )

        if not first_list:
            self.log_signal_func("[목록] 첫 페이지 list 비어있음")
            return items

        add_items(first_list)

        if total_count > 0 and len(items) >= total_count:
            self.log_signal_func(f"[목록] totalCount 도달로 중단 collected={len(items)} total={total_count}")
            return items

        if should_stop_by_date(first_list):
            self.log_signal_func(f"[목록] 시작일({self.fr_date}) 이전 데이터 발견으로 목록 조회 중단")
            self.log_signal_func(f"[목록] 최종 수집 건수={len(items)}")
            return items

        seed: str | None = first_result.get("seed")
        last_info: list[Any] = first_result.get("lastInfo", []) or []
        has_next: bool = bool(first_result.get("hasNextPage"))
        page: int = 2
        max_page: int = 300

        prev_seed = seed
        prev_last_info_text = json.dumps(last_info, ensure_ascii=False, sort_keys=True)

        while True:
            if not self.running:
                return items

            if not has_next:
                self.log_signal_func("[목록] hasNextPage=false 로 종료")
                break

            if not last_info:
                self.log_signal_func("[목록] lastInfo 없음으로 종료")
                break

            if total_count > 0 and len(items) >= total_count:
                self.log_signal_func(f"[목록] totalCount 도달로 종료 collected={len(items)} total={total_count}")
                break

            if page > max_page:
                self.log_signal_func(f"[목록] max_page({max_page}) 초과로 강제 종료")
                break

            req: dict[str, Any] = json.loads(json.dumps(base_payload))
            req["articlePagingRequest"]["seed"] = seed
            req["articlePagingRequest"]["lastInfo"] = last_info

            self.log_signal_func(
                f"[목록] page={page} 요청 seed={'Y' if seed else 'N'} lastInfo={len(last_info)}"
            )

            fetch_res = self._browser_fetch_json(
                url=self.list_api_url,
                method="POST",
                payload=req,
                wait_sec=200,
            )

            status = fetch_res.get("status")
            json_res = fetch_res.get("json") or {}

            self.log_signal_func(
                f"[목록] page={page} status={status} ok={fetch_res.get('ok')}"
            )

            if status != 200:
                self.log_signal_func(f"[목록] page={page} 실패 body={fetch_res.get('text', '')[:500]}")
                break

            result: dict[str, Any] = json_res.get("result", {}) or {}
            page_list: list[dict[str, Any]] = result.get("list", []) or []

            before_len = len(items)
            add_items(page_list)
            added_now = len(items) - before_len

            self.log_signal_func(
                f"[목록] page={page} "
                f"페이지건수={len(page_list)} "
                f"추가건수={added_now} "
                f"누적건수={len(items)} "
                f"hasNext={result.get('hasNextPage')} "
                f"total={result.get('totalCount')}"
            )

            if not page_list:
                self.log_signal_func(f"[목록] page={page} list 없음으로 종료")
                break

            if total_count > 0 and len(items) >= total_count:
                self.log_signal_func(f"[목록] totalCount 도달로 종료 collected={len(items)} total={total_count}")
                break

            next_seed = result.get("seed", seed)
            next_last_info = result.get("lastInfo", []) or []
            next_has_next = bool(result.get("hasNextPage"))

            next_last_info_text = json.dumps(next_last_info, ensure_ascii=False, sort_keys=True)

            if next_has_next and next_seed == prev_seed and next_last_info_text == prev_last_info_text:
                self.log_signal_func("[목록] seed/lastInfo 변화 없음으로 무한루프 방지 종료")
                break

            if added_now == 0 and self.remove_duplicate_yn:
                self.log_signal_func("[목록] 이번 페이지 신규 추가 0건으로 종료")
                break

            seed = next_seed
            last_info = next_last_info
            has_next = next_has_next

            if should_stop_by_date(page_list):
                self.log_signal_func(f"[목록] 시작일({self.fr_date}) 이전 데이터 발견으로 목록 조회 중단")
                break

            prev_seed = seed
            prev_last_info_text = json.dumps(last_info, ensure_ascii=False, sort_keys=True)

            page += 1

            if has_next:
                time.sleep(random.uniform(0.8, 1.2))

        self.log_signal_func(f"[목록] 최종 수집 건수={len(items)}")
        return items

    def _collect_detail(self, items: list[dict[str, Any]], region_item) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []

        for i, info in enumerate(items, 1):

            if not self.running:
                return details

            try:
                article_no: str = str(info["articleNumber"])
                real_estate_type: str = str(info["realEstateType"])
                trade_type: str = str(info["tradeType"])

                self.log_signal_func(f"[상세] {i}/{len(items)} articleNumber={article_no} 시작")

                detail_fetch_res = self._browser_fetch_json(
                    url=self.detail_api_url,
                    method="GET",
                    params={
                        "articleNumber": article_no,
                        "realEstateType": real_estate_type,
                        "tradeType": trade_type,
                    },
                    wait_sec=120,
                )
                if detail_fetch_res.get("status") != 200:
                    self.log_signal_func(
                        f"[상세] basicInfo 실패 articleNumber={article_no} "
                        f"status={detail_fetch_res.get('status')} "
                        f"body={detail_fetch_res.get('text', '')[:500]}"
                    )

                agent_fetch_res = self._browser_fetch_json(
                    url=self.agent_detail_url,
                    method="GET",
                    params={
                        "articleNumber": article_no
                    },
                    wait_sec=120,
                )

                if agent_fetch_res.get("status") != 200:
                    self.log_signal_func(
                        f"[상세] agent 실패 articleNumber={article_no} "
                        f"status={agent_fetch_res.get('status')} "
                        f"body={agent_fetch_res.get('text', '')[:500]}"
                    )

                article_key_res = self._browser_fetch_json(
                    url=self.article_key_url,
                    method="GET",
                    params={
                        "articleNumber": article_no
                    },
                    wait_sec=120,
                )

                if article_key_res.get("status") != 200:
                    self.log_signal_func(
                        f"[상세] article key 실패 articleNumber={article_no} "
                        f"status={article_key_res.get('status')} "
                        f"body={article_key_res.get('text', '')[:500]}"
                    )

                article_key_json = article_key_res.get("json") or {}
                article_key_result = article_key_json.get("result", {}) or {}
                key_info = article_key_result.get("key", {}) or {}
                complex_no = key_info.get("complexNumber", "")

                complex_fetch_res = {}
                if complex_no not in [None, ""]:
                    complex_fetch_res = self._browser_fetch_json(
                        url=self.complex_api_url,
                        method="GET",
                        params={
                            "complexNumber": complex_no
                        },
                        wait_sec=120,
                    )

                    if complex_fetch_res.get("status") != 200:
                        self.log_signal_func(
                            f"[상세] complex 실패 articleNumber={article_no} complexNumber={complex_no} "
                            f"status={complex_fetch_res.get('status')} "
                            f"body={complex_fetch_res.get('text', '')[:500]}"
                        )

                time.sleep(random.uniform(1.5, 2.2))

                detail = {
                    "articleNumber": article_no,
                    "realEstateType": real_estate_type,
                    "tradeType": trade_type,
                    "listItem": info,
                    "detail": detail_fetch_res.get("json"),
                    "agent_detail": agent_fetch_res.get("json"),
                    "article_key": article_key_json,
                    "complex_detail": complex_fetch_res.get("json"),
                }

                self._detail_map_save(detail, region_item)

                details.append(detail)

                time.sleep(random.uniform(2.2, 3.2))

            except Exception as e:
                self.log_signal_func(f"[상세] 실패 {i}/{len(items)} articleNumber={info.get('articleNumber')} / {e}")
                continue

        self.log_signal_func(f"[상세] 최종 수집 건수={len(details)}")
        return details

    def _save_list_items(self, items: list[dict[str, Any]], region_item) -> None:
        try:
            save_rows = []
            save_count = len(save_rows)

            for info in items:
                rs = self._make_list_row(info, region_item)
                rs = self._apply_excel_hyperlinks_to_row(rs)

                if self.eng_yn:
                    rs = self._map_out_to_eng(rs)

                save_rows.append(rs)

            if not save_rows:
                self.log_signal_func("[일반저장] 저장할 데이터 없음")
                return

            self.excel_driver.append_to_csv(
                self.csv_filename,
                save_rows,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

        except Exception as e:
            self.log_signal_func(f"[일반저장] 일괄 저장 실패 / {e}")

    def _append_save_row(self, rs):
        save_row = self._apply_excel_hyperlinks_to_row(rs)
        if self.eng_yn:
            save_row = self._map_out_to_eng(save_row)

        self.excel_driver.append_to_csv(
            self.csv_filename,
            [save_row],
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def _join_tag_list(self, tag_list):
        if isinstance(tag_list, list):
            return ", ".join([str(x).strip() for x in tag_list if str(x).strip()])
        return str(tag_list or "").strip()

    def _empty_if_zero(self, value):
        if value in [0, 0.0, "0", "0.0"]:
            return ""
        return value

    def _get_base_amount_divisor(self):
        base_amount = str(self.base_amount or "").strip().upper()

        if base_amount == "10K":
            return Decimal("10000")

        if base_amount == "100M":
            return Decimal("100000000")

        return Decimal("1")

    def _convert_price_by_base_amount(self, value):
        if value in [None, ""]:
            return value

        text = str(value).strip().replace(",", "")
        if not text:
            return value

        try:
            amount = Decimal(text)
        except (InvalidOperation, ValueError, TypeError):
            return value

        if amount == 0:
            return ""

        divisor = self._get_base_amount_divisor()

        if divisor == Decimal("1"):
            return value

        converted = amount / divisor

        if converted == converted.to_integral_value():
            return int(converted)

        return float(converted)

    def _make_list_row(self, list_item, region_item):
        sido = region_item.get("시도")
        sigungu = region_item.get("시군구")
        eup_myeon_dong = region_item.get("읍면동")

        list_land = list_item.get("landInfo") or {}
        list_space = list_item.get("spaceInfo") or {}
        list_broker = list_item.get("brokerInfo") or {}
        list_article_detail = list_item.get("articleDetail") or {}
        list_address = list_item.get("address") or {}
        list_price = list_item.get("priceInfo") or {}
        list_verification = list_item.get("verificationInfo") or {}
        list_building = list_item.get("buildingInfo") or {}

        list_coords = list_address.get("coordinates") or {}
        list_floor_detail = list_article_detail.get("floorDetailInfo") or {}
        articleName = list_item.get("articleName", "")

        target_floor = ""
        total_floor = ""
        floor_text = str(list_article_detail.get("floorInfo", "")).strip()
        if floor_text:
            parts = [x.strip() for x in floor_text.split("/", 1)]
            target_floor = parts[0] if len(parts) > 0 else ""
            total_floor = parts[1] if len(parts) > 1 else ""
        else:
            target_floor = str(list_floor_detail.get("targetFloor", "")).strip()
            total_floor = str(list_floor_detail.get("totalFloor", "")).strip()

        city = list_address.get("city", "")
        division = list_address.get("division", "")
        sector = list_address.get("sector", "")
        jibun = list_item.get("jibun", "")
        road_name = list_item.get("roadName", "")
        zip_code = list_item.get("zipCode", "")

        full_addr_parts = [city, division, sector]
        if road_name:
            full_addr_parts.append(road_name)
        elif jibun:
            full_addr_parts.append(jibun)
        elif articleName:
            full_addr_parts.append(articleName)

        full_addr = " ".join([str(v).strip() for v in full_addr_parts if str(v).strip()])

        trade_type_code = list_item.get("tradeType", "")
        real_estate_type_code = list_item.get("realEstateType", "")
        direction_code = list_article_detail.get("direction", "")

        trade_type_name = self._find_filter_name_by_index_and_code(0, trade_type_code)
        real_estate_type_name = self._find_filter_name_by_index_and_code(1, real_estate_type_code)
        direction = self._find_filter_name_by_index_and_code(8, direction_code) or direction_code

        article_no = list_item.get("articleNumber", "")

        rs = {
            "매물번호": article_no,
            "단지명": list_item.get("complexName", ""),
            "동이름": list_item.get("dongName", ""),
            "매매가": self._convert_price_by_base_amount(list_price.get("dealPrice", "")),
            "보증금/전세": self._convert_price_by_base_amount(list_price.get("warrantyPrice", "")),
            "월세": self._convert_price_by_base_amount(list_price.get("rentPrice", "")),
            "공급면적": self._empty_if_zero(list_space.get("supplySpace", "")),
            "평수": self._empty_if_zero(list_item.get("pyeongArea", "") or list_space.get("pyeongArea", "")),
            "대지면적": self._empty_if_zero(list_space.get("landSpace", "")),
            "연면적": self._empty_if_zero(list_space.get("floorSpace", "")),
            "건축면적": self._empty_if_zero(list_space.get("buildingSpace", "")),
            "전용면적": self._empty_if_zero(list_space.get("exclusiveSpace", "")),
            "매물확인일": list_verification.get("articleConfirmDate", ""),
            "매물노출시작일": list_verification.get("exposureStartDate", ""),
            "건축물용도": list_item.get("buildingPrincipalUse", ""),
            "해당층": self._empty_if_zero(target_floor),
            "전체층": self._empty_if_zero(total_floor),
            "시도": city,
            "시군구": division,
            "읍면동": sector,
            "번지": jibun,
            "도로명주소": road_name,
            "우편번호": zip_code,
            "전체주소": full_addr,
            "중개사무소이름": list_broker.get("brokerageName", ""),
            "중개사이름": list_broker.get("brokerName", ""),
            "중개사무소주소": list_broker.get("address", ""),
            "중개사무소번호": list_broker.get("brokeragePhone", ""),
            "중개사핸드폰번호": list_broker.get("mobilePhone", ""),
            "URL": f"{self.url}/articles/{article_no}",
            "상위매물명": list_item.get("upperArticleName", "") or articleName,
            "상위매물동": list_item.get("upperDongName", "") or list_item.get("dongName", ""),
            "부모여부": list_item.get("parentYn", "Y"),
            "상위매물번호": list_item.get("upperArticleNumber", "") or list_item.get("articleNumber", ""),
            "매물유형": real_estate_type_name or real_estate_type_code,
            "거래유형": trade_type_name or trade_type_code,
            "매물태그": self._join_tag_list(list_item.get("tagList", [])),
            "등록일자": list_item.get("atclCfmYmd", "") or list_verification.get("articleConfirmDate", ""),
            "위도": list_coords.get("yCoordinate", ""),
            "경도": list_coords.get("xCoordinate", ""),
            "방향정보": direction,
            "동일주소매물수": self._empty_if_zero(list_item.get("sameAddrCnt", "")),
            "동일주소최소가": self._empty_if_zero(list_item.get("sameAddrMinPrc", "")),
            "동일주소최대가": self._empty_if_zero(list_item.get("sameAddrMaxPrc", "")),
            "매물설명": list_article_detail.get("articleFeatureDescription", ""),
            "매물상세설명": list_article_detail.get("articleDescription", ""),
            "매물확인코드": list_item.get("vrfctpcd", "") or list_verification.get("verificationType", ""),
            "현재업종": list_land.get("currentPurpose", ""),
            "추천업종": list_land.get("recommendedPurpose", ""),
            "사용승인일": yyyy_mm_dd_to(list_building.get("buildingConjunctionDate", "")),
            "검색 주소": sido + " " + sigungu + " " + eup_myeon_dong,
        }

        return rs

    def _list_map_save(self, list_item, region_item):
        rs = self._make_list_row(list_item, region_item)
        self._append_save_row(rs)

    def _detail_map_save(self, detail, region_item):
        list_item = (detail or {}).get("listItem") or {}
        rs = self._make_list_row(list_item, region_item)

        detail_result = ((detail or {}).get("detail") or {}).get("result") or {}
        agent_result = ((detail or {}).get("agent_detail") or {}).get("result") or {}
        article_key_result = ((detail or {}).get("article_key") or {}).get("result") or {}
        complex_result = ((detail or {}).get("complex_detail") or {}).get("result") or {}

        detail_price = detail_result.get("priceInfo") or {}
        detail_info = detail_result.get("detailInfo") or {}
        detail_article = detail_info.get("articleDetailInfo") or {}
        detail_verification = detail_info.get("verificationInfo") or {}
        detail_space = detail_info.get("spaceInfo") or {}
        detail_floor = detail_space.get("floorInfo") or {}
        detail_size = detail_info.get("sizeInfo") or {}
        detail_complex = detail_result.get("communalComplexInfo") or {}
        detail_coords = detail_article.get("coordinates") or {}

        phone = agent_result.get("phone") or {}
        key_address = article_key_result.get("address") or {}
        complex_address = complex_result.get("address") or {}
        complex_coords = complex_result.get("coordinates") or {}

        if detail_complex.get("complexName") not in [None, ""]:
            rs["단지명"] = detail_complex.get("complexName", "")

        if detail_complex.get("dongName") not in [None, ""]:
            rs["동이름"] = detail_complex.get("dongName", "")

        if detail_price.get("price") not in [None, ""]:
            rs["매매가"] = self._convert_price_by_base_amount(detail_price.get("price", ""))

        if detail_price.get("warrantyAmount") not in [None, ""]:
            rs["보증금/전세"] = self._convert_price_by_base_amount(detail_price.get("warrantyAmount", ""))

        if detail_price.get("rentAmount") not in [None, ""]:
            rs["월세"] = self._convert_price_by_base_amount(detail_price.get("rentAmount", ""))

        if detail_size.get("supplySpace") not in [None, ""]:
            rs["공급면적"] = self._empty_if_zero(detail_size.get("supplySpace", ""))

        if detail_size.get("pyeongArea") not in [None, ""]:
            rs["평수"] = self._empty_if_zero(detail_size.get("pyeongArea", ""))

        if detail_size.get("exclusiveSpace") not in [None, ""]:
            rs["전용면적"] = self._empty_if_zero(detail_size.get("exclusiveSpace", ""))
        elif detail_space.get("exclusiveSpace") not in [None, ""]:
            rs["전용면적"] = self._empty_if_zero(detail_size.get("exclusiveSpace", ""))

        if detail_verification.get("articleConfirmDate") not in [None, ""]:
            rs["매물확인일"] = detail_verification.get("articleConfirmDate", "")

        if detail_verification.get("exposureStartDate") not in [None, ""]:
            rs["매물노출시작일"] = detail_verification.get("exposureStartDate", "")

        if detail_article.get("buildingPrincipalUse") not in [None, ""]:
            rs["건축물용도"] = detail_article.get("buildingPrincipalUse", "")
        elif complex_result.get("buildingUse") not in [None, ""]:
            rs["건축물용도"] = complex_result.get("buildingUse", "")

        rs["해당층"] = self._empty_if_zero(detail_floor.get("targetFloor", ""))
        rs["전체층"] = self._empty_if_zero(detail_floor.get("totalFloor", ""))

        city = complex_address.get("city", "") or rs.get("시도", "")
        division = complex_address.get("division", "") or rs.get("시군구", "")
        sector = complex_address.get("sector", "") or rs.get("읍면동", "")
        jibun = key_address.get("jibun", "") or complex_address.get("jibun", "") or rs.get("번지", "")
        road_name = complex_address.get("roadName", "") or rs.get("도로명주소", "")
        zip_code = complex_address.get("zipCode", "") or rs.get("우편번호", "")

        rs["시도"] = city
        rs["시군구"] = division
        rs["읍면동"] = sector
        rs["번지"] = jibun
        rs["도로명주소"] = road_name
        rs["우편번호"] = zip_code

        articleName = detail_article.get("articleName", "")

        full_addr_parts = [city, division, sector]
        if road_name:
            full_addr_parts.append(road_name)
        elif jibun:
            full_addr_parts.append(jibun)
        elif articleName:
            full_addr_parts.append(articleName)

        full_addr = " ".join([str(v).strip() for v in full_addr_parts if str(v).strip()])

        rs["전체주소"] = full_addr

        if agent_result.get("brokerageName") not in [None, ""]:
            rs["중개사무소이름"] = agent_result.get("brokerageName", "")

        if agent_result.get("brokerName") not in [None, ""]:
            rs["중개사이름"] = agent_result.get("brokerName", "")

        if agent_result.get("address") not in [None, ""]:
            rs["중개사무소주소"] = agent_result.get("address", "")

        if phone.get("brokerage") not in [None, ""]:
            rs["중개사무소번호"] = phone.get("brokerage", "")

        if phone.get("mobile") not in [None, ""]:
            rs["중개사핸드폰번호"] = phone.get("mobile", "")

        direction_code = detail_space.get("direction", "")
        if direction_code:
            rs["방향정보"] = self._find_filter_name_by_index_and_code(8, direction_code) or direction_code

        if detail_article.get("articleFeatureDescription") not in [None, ""]:
            rs["매물설명"] = detail_article.get("articleFeatureDescription", "")

        if detail_article.get("articleDescription") not in [None, ""]:
            rs["매물상세설명"] = detail_article.get("articleDescription", "")

        if detail_verification.get("verificationType") not in [None, ""]:
            rs["매물확인코드"] = detail_verification.get("verificationType", "")

        if detail_space.get("currentBusinessType") not in [None, ""]:
            rs["현재업종"] = detail_space.get("currentBusinessType", "")

        if detail_space.get("recommendedBusinessType") not in [None, ""]:
            rs["추천업종"] = detail_space.get("recommendedBusinessType", "")

        y = detail_coords.get("yCoordinate", "") or complex_coords.get("yCoordinate", "")
        x = detail_coords.get("xCoordinate", "") or complex_coords.get("xCoordinate", "")
        if y not in [None, ""]:
            rs["위도"] = y
        if x not in [None, ""]:
            rs["경도"] = x

        self._append_save_row(rs)