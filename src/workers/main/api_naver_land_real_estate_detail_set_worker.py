# src/workers/main/api_naver_place_url_all_set_worker.py
import os
import time
from typing import List, Optional, Any
import random

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
import json
import requests
import urllib3
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

        self.list_api_url: str = "https://fin.land.naver.com/front-api/v1/article/boundedArticles"
        self.agent_detail_url: str = "https://fin.land.naver.com/front-api/v1/article/agent"
        self.detail_api_url: str = "https://fin.land.naver.com/front-api/v1/article/basicInfo"
        self.url: str = "https://fin.land.naver.com/"
        self.headers = None



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
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func, verify=False)
        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(timeout=1200, view_mode="browser", window_size=(1600, 1000))

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

        # 5. 영어컬럼 여부
        self.eng: str = self.get_setting_value(self.setting, "eng")
        self.log_signal_func(f"영어컬럼 여부 : {self.eng}")


        # 6. 부동산 중개사 기준 매물 가져오기 여부
        self.brokerage_yn: bool = self.get_setting_value(self.setting, "brokerage_yn")
        self.log_signal_func(f"부동산 중개사 기준 매물 가져오기 여부 : {self.brokerage_yn}")

        # 7. 위 세팅에 맞는 매물 목록 크롤링
        self._crawl_article_list()

        return True


    def _crawl_article_list(self):
        for index, region_item in enumerate(self.detail_region_article_list, start=1):
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

            # driver.get
            self.driver.get(url)
            time.sleep(5)

            # 목록 후킹 설치
            self.log_signal_func("[후킹] 목록 후킹 설치")
            self.inject_list_hook()
            time.sleep(1)

            # 매물 버튼 클릭
            self.log_signal_func("[클릭] 매물 버튼 클릭 시도")
            self.click_article_button(wait_sec=20)
            time.sleep(3)

            hook_data: dict[str, Any] = self.get_first_list_hook_data(20)
            body_text: str = hook_data.get("bodyText", "")
            response_json: dict[str, Any] = hook_data.get("responseJson", {})

            self.log_signal_func(f"[후킹] 수신 여부={bool(hook_data)}")
            self.log_signal_func(f"self.fr_date self.to_date은 이미 위에서 yyyymmdd로 값이 세팅된상태로 여기서는 그냥쓰면돼[후킹] bodyText 존재={bool(body_text)}")
            self.log_signal_func(f"[후킹] responseJson 존재={bool(response_json)}")
            base_payload: dict[str, Any] = json.loads(body_text)

            self.set_cookie()
            self.set_headers()

            items: list[dict[str, Any]] = self.collect_next_list_pages(base_payload)
            details: list[dict[str, Any]] = self.collect_detail(items)

            self.detail_map_save(details)

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


    def qq(self, selector: str, wait_sec: int = 20) -> list[Any]:
        end = time.time() + wait_sec
        while time.time() < end:
            try:
                els = self.driver.execute_script(
                    "return Array.from(document.querySelectorAll(arguments[0]));",
                    selector,
                )
                if els:
                    return els
            except Exception as e:
                self.log_signal_func(f"[qq] 조회 실패: {e}")
            time.sleep(1)
        return []


    def click_article_button(self, wait_sec: int = 20) -> None:
        end = time.time() + wait_sec

        while time.time() < end:
            try:
                buttons = self.driver.execute_script(
                    "return Array.from(document.querySelectorAll('button.BottomInfoControls_link-item___xLdX'));"
                )

                if buttons:
                    self.log_signal_func(f"[매물 버튼] 발견 개수={len(buttons)}")
                    self.driver.execute_script("arguments[0].click();", buttons[0])
                    self.log_signal_func("[매물 버튼] 첫 번째 버튼 클릭 완료")
                    return
            except Exception as e:
                self.log_signal_func(f"[매물 버튼] 클릭 실패: {e}")

            time.sleep(1)

        raise Exception("매물 버튼을 찾지 못했습니다.")


    def inject_list_hook(self) -> None:
        self.driver.execute_script(
            """
            window.__naverListHookData = null;
            if (window.__naverListHookInstalled) return;
            window.__naverListHookInstalled = true;
    
            const target = '/front-api/v1/article/boundedArticles';
    
            const saveData = async (url, bodyText, response) => {
                try {
                    const cloned = response.clone();
                    const jsonData = await cloned.json();
                    if (!window.__naverListHookData) {
                        window.__naverListHookData = {
                            url: url,
                            bodyText: bodyText || '',
                            responseJson: jsonData
                        };
                    }
                } catch (e) {}
            };
    
            const oldFetch = window.fetch;
            window.fetch = async function(...args) {
                const res = await oldFetch.apply(this, args);
                try {d
                    const req = args[0];
                    const url = typeof req === 'string' ? req : req.url;
                    const opts = args[1] || {};
                    const bodyText = opts && opts.body ? opts.body : '';
                    if (url && url.includes(target)) saveData(url, bodyText, res);
                } catch (e) {}
                return res;
            };
    
            const oldOpen = XMLHttpRequest.prototype.open;
            const oldSend = XMLHttpRequest.prototype.send;
    
            XMLHttpRequest.prototype.open = function(method, url) {
                this.__hookUrl = url;
                return oldOpen.apply(this, arguments);
            };
    
            XMLHttpRequest.prototype.send = function(body) {
                this.addEventListener('load', function() {
                    try {
                        if (this.__hookUrl && this.__hookUrl.includes(target) && !window.__naverListHookData) {
                            window.__naverListHookData = {
                                url: this.__hookUrl,
                                bodyText: body || '',
                                responseJson: JSON.parse(this.responseText)
                            };
                        }
                    } catch (e) {}
                });
                return oldSend.apply(this, arguments);
            };
            """
        )


    def get_first_list_hook_data(self, wait_sec: int = 20):
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


    def set_cookie(self):
        for c in self.driver.get_cookies():
            self.api_client.cookie_set(c["name"], c["value"])


    def set_headers(self):
        self.headers = {
            "User-Agent": self.driver.execute_script("return navigator.userAgent;"),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.url,
            "Referer": self.driver.current_url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        }


    def collect_next_list_pages(
            self,
            base_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        use_date_filter: bool = bool(self.fr_date and self.to_date)
        def normalize_date_yyyymmdd(value: Any) -> str:
            return str(value or "").replace("-", "").replace(".", "").replace("/", "").strip()

        def get_confirm_date_from_item(item: dict[str, Any]) -> str:
            info: dict[str, Any] = item.get("representativeArticleInfo", {})
            verification_info: dict[str, Any] = info.get("verificationInfo", {})
            return normalize_date_yyyymmdd(verification_info.get("articleConfirmDate", ""))

        def is_target_date(confirm_date: str) -> bool:
            if not use_date_filter:
                return True
            return self.fr_date <= confirm_date <= self.to_date

        def should_stop_by_date(page_list: list[dict[str, Any]]) -> bool:
            if not use_date_filter:
                return False

            for item in page_list:
                confirm_date: str = get_confirm_date_from_item(item)
                if confirm_date < self.fr_date:
                    return True

            return False

        def add_items(page_list: list[dict[str, Any]]) -> None:
            for item in page_list:
                if self.brokerage_yn:
                    duplicated_info: dict[str, Any] = item.get("duplicatedArticleInfo", {})
                    article_info_list: list[dict[str, Any]] = duplicated_info.get("articleInfoList", []) or []

                    if article_info_list:
                        for article_info in article_info_list:
                            article_no: str = str(article_info.get("articleNumber", "")).strip()
                            verification_info: dict[str, Any] = article_info.get("verificationInfo", {})
                            confirm_date: str = normalize_date_yyyymmdd(
                                verification_info.get("articleConfirmDate", "")
                            )

                            if not is_target_date(confirm_date):
                                continue

                            if article_no and article_no not in seen:
                                seen.add(article_no)
                                items.append(article_info)
                        continue

                info: dict[str, Any] = item.get("representativeArticleInfo", {})
                article_no: str = str(info.get("articleNumber", "")).strip()
                verification_info: dict[str, Any] = info.get("verificationInfo", {})
                confirm_date: str = normalize_date_yyyymmdd(
                    verification_info.get("articleConfirmDate", "")
                )

                if not is_target_date(confirm_date):
                    continue

                if article_no and article_no not in seen:
                    seen.add(article_no)
                    items.append(info)

        page: int = 1
        seed: str | None = None
        last_info: list[Any] = []
        has_next: bool = True

        while has_next:
            req: dict[str, Any] = json.loads(json.dumps(base_payload))
            req.setdefault("articlePagingRequest", {})
            req["articlePagingRequest"]["articleSortType"] = self.article_sort_type

            if page >= 2:
                req["articlePagingRequest"]["seed"] = seed
                req["articlePagingRequest"]["lastInfo"] = last_info
            else:
                req["articlePagingRequest"]["seed"] = None
                req["articlePagingRequest"]["lastInfo"] = []

            self.log_signal_func(f"[목록] page={page} 요청")

            res = self.api_client.post(
                url=self.list_api_url,
                headers=self.headers,
                json=req,
                timeout=30
            )

            result: dict[str, Any] = res["result"]
            page_list: list[dict[str, Any]] = result.get("list", [])

            self.log_signal_func(
                f"[목록] page={page} "
                f"count={len(page_list)} "
                f"hasNext={result.get('hasNextPage')} "
                f"total={result.get('totalCount')}"
            )

            if not page_list:
                break

            add_items(page_list)

            seed = result.get("seed", seed)
            last_info = result.get("lastInfo", []) or []
            has_next = bool(result.get("hasNextPage"))

            if should_stop_by_date(page_list):
                self.log_signal_func(f"[목록] 시작일({self.fr_date}) 이전 데이터 발견으로 목록 조회 중단")
                break

            page += 1

            if has_next:
                time.sleep(random.uniform(0.8, 1.2))

        self.log_signal_func(f"[목록] 최종 수집 건수={len(items)}")
        return items


    def collect_detail(self, items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []

        for i, info in enumerate(items, 1):
            article_no: str = str(info["articleNumber"])
            real_estate_type: str = str(info["realEstateType"])
            trade_type: str = str(info["tradeType"])

            print(f"[상세] {i}/{len(items)} articleNumber={article_no}")

            res = self.api_client.get(
                self.detail_api_url,
                headers=self.headers,
                params={
                    "articleNumber": article_no,
                    "realEstateType": real_estate_type,
                    "tradeType": trade_type,
                },
                timeout=1200
            )

            agent_res = self.api_client.get(
                self.agent_detail_url,
                headers=self.headers,
                params={
                    "articleNumber": article_no
                },
                timeout=1200
            )

            time.sleep(random.uniform(1.5, 2.2))

            details.append(
                {
                    "articleNumber": article_no,
                    "realEstateType": real_estate_type,
                    "tradeType": trade_type,
                    "listItem": info,
                    "detail": res,
                    "agent_detail": agent_res
                }
            )

            time.sleep(random.uniform(2.2, 3.2))

        print(f"[상세] 최종 수집 건수={len(details)}")
        return details


    def detail_map_save(self, details):
        return ""

