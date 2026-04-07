import os
import time
from typing import List, Optional, Any
import random
import json

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

        self.folder_path: str = ""
        self.out_dir: str = "output"

        self.naver_loc_all_real_detail = None
        self.detail_region_article_list = None

        self.list_api_url: str = "https://fin.land.naver.com/front-api/v1/article/boundedArticles"
        self.agent_detail_url: str = "https://fin.land.naver.com/front-api/v1/article/agent"
        self.detail_api_url: str = "https://fin.land.naver.com/front-api/v1/article/basicInfo"
        self.url: str = "https://fin.land.naver.com/"

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
        self.article_sort_type: str = str(self.get_setting_value(self.setting, "articleSortType") or "").strip()
        self.log_signal_func(f"정렬 방식 : {self.article_sort_type}")

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

            # 정렬 버튼 클릭
            self.log_signal_func(f"[정렬] 정렬 클릭 시도 : {self.article_sort_type}")
            self.click_sort_button_by_setting(wait_sec=20)
            time.sleep(3)

            hook_data: dict[str, Any] = self.get_first_list_hook_data(20)
            body_text: str = hook_data.get("bodyText", "")
            response_json: dict[str, Any] = hook_data.get("responseJson", {}) or {}

            self.log_signal_func(f"[후킹] 수신 여부={bool(hook_data)}")
            self.log_signal_func(f"[후킹] bodyText 존재={bool(body_text)}")
            self.log_signal_func(f"[후킹] responseJson 존재={bool(response_json)}")

            if not body_text:
                self.log_signal_func("[후킹] bodyText 없음")
                continue

            try:
                base_payload: dict[str, Any] = json.loads(body_text)
            except Exception as e:
                self.log_signal_func(f"[후킹] bodyText json 파싱 실패: {e}")
                continue

            first_result: dict[str, Any] = response_json.get("result", {}) or {}

            if not first_result:
                self.log_signal_func("[후킹] 첫 응답 result 없음 -> 첫 페이지 재요청")
                retry_res = self.browser_fetch_json(
                    url=self.list_api_url,
                    method="POST",
                    payload=base_payload,
                    wait_sec=30,
                )

                self.log_signal_func(
                    f"[후킹 재요청] status={retry_res.get('status')} ok={retry_res.get('ok')}"
                )

                retry_json: dict[str, Any] = retry_res.get("json") or {}
                first_result = retry_json.get("result", {}) or {}

            if not first_result:
                self.log_signal_func("[목록] 첫 페이지 result 확보 실패")
                continue

            items: list[dict[str, Any]] = self.collect_next_list_pages(
                base_payload=base_payload,
                first_result=first_result,
            )

            details: list[dict[str, Any]] = self.collect_detail(items, region_item)

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

    def click_sort_button_by_setting(self, wait_sec: int = 20) -> None:
        click_map: dict[str, tuple[str, int]] = {
            "RANKING_DESC": ("filterOrder1", 1),
            "PRICE_DESC": ("filterOrder2", 1),
            "PRICE_ASC": ("filterOrder2", 2),
            "DATE_DESC": ("filterOrder3", 1),
            "SPACE_DESC": ("filterOrder4", 1),
            "SPACE_ASC": ("filterOrder4", 2),
        }

        sort_id, click_count = click_map.get(self.article_sort_type or "", ("filterOrder1", 1))
        self.log_signal_func(
            f"[정렬] articleSortType={self.article_sort_type} sort_id={sort_id} click_count={click_count}"
        )

        end = time.time() + wait_sec

        while time.time() < end:
            try:
                clicked = self.driver.execute_script(
                    """
                    const sortId = arguments[0];
                    const clickCount = arguments[1];

                    const input = document.getElementById(sortId);
                    if (!input) return { ok: false, message: "input 없음" };

                    let label = document.querySelector(`label[for="${sortId}"]`);
                    if (!label && input.nextElementSibling && input.nextElementSibling.tagName === "LABEL") {
                        label = input.nextElementSibling;
                    }
                    if (!label) return { ok: false, message: "label 없음" };

                    for (let i = 0; i < clickCount; i++) {
                        label.click();
                    }

                    return {
                        ok: true,
                        labelText: (label.innerText || label.textContent || "").trim()
                    };
                    """,
                    sort_id,
                    click_count,
                )

                if clicked and clicked.get("ok"):
                    self.log_signal_func(f"[정렬] 클릭 완료 : {clicked.get('labelText')}")
                    return
            except Exception as e:
                self.log_signal_func(f"[정렬] 클릭 실패: {e}")

            time.sleep(1)

        raise Exception(f"정렬 버튼 클릭 실패: {self.article_sort_type}")

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
                try {
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

    def browser_fetch_json(
            self,
            url: str,
            method: str = "GET",
            payload: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
            wait_sec: int = 30,
    ) -> dict[str, Any]:
        script = """
        const url = arguments[0];
        const method = arguments[1];
        const payload = arguments[2];
        const params = arguments[3];
        const done = arguments[arguments.length - 1];

        try {
            const u = new URL(url);

            if (params) {
                Object.keys(params).forEach((key) => {
                    const value = params[key];
                    if (value !== undefined && value !== null) {
                        u.searchParams.set(key, String(value));
                    }
                });
            }

            const options = {
                method: method,
                credentials: "include",
                headers: {
                    "Accept": "application/json, text/plain, */*"
                }
            };

            if (method != "GET") {
                options.headers["Content-Type"] = "application/json";
            }

            if (payload) {
                options.body = JSON.stringify(payload);
            }

            fetch(u.toString(), options)
                .then(async (res) => {
                    let text = "";
                    try {
                        text = await res.text();
                    } catch (e) {}

                    let jsonData = null;
                    try {
                        jsonData = text ? JSON.parse(text) : null;
                    } catch (e) {}

                    done({
                        ok: res.ok,
                        status: res.status,
                        statusText: res.statusText,
                        url: res.url,
                        text: text,
                        json: jsonData
                    });
                })
                .catch((e) => {
                    done({
                        ok: false,
                        status: -1,
                        statusText: String(e),
                        url: "",
                        text: "",
                        json: null
                    });
                });
        } catch (e) {
            done({
                ok: false,
                status: -1,
                statusText: String(e),
                url: "",
                text: "",
                json: null
            });
        }
        """
        self.driver.set_script_timeout(wait_sec)
        return self.driver.execute_async_script(script, url, method, payload, params)

    def collect_next_list_pages(
            self,
            base_payload: dict[str, Any],
            first_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
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

        def add_items(page_list: list[dict[str, Any]]) -> None:
            for item in page_list:
                if self.brokerage_yn:
                    duplicated_info: dict[str, Any] = item.get("duplicatedArticleInfo", {}) or {}
                    article_info_list: list[dict[str, Any]] = duplicated_info.get("articleInfoList", []) or []

                    if article_info_list:
                        for article_info in article_info_list:
                            article_no: str = str(article_info.get("articleNumber", "")).strip()
                            confirm_date: str = get_confirm_date_from_info(article_info)

                            if not is_target_date(confirm_date):
                                continue

                            if article_no and article_no not in seen:
                                seen.add(article_no)
                                items.append(article_info)
                        continue

                info: dict[str, Any] = item.get("representativeArticleInfo", {}) or {}
                article_no: str = str(info.get("articleNumber", "")).strip()
                confirm_date: str = get_confirm_date_from_info(info)

                if not is_target_date(confirm_date):
                    continue

                if article_no and article_no not in seen:
                    seen.add(article_no)
                    items.append(info)

        first_list: list[dict[str, Any]] = first_result.get("list", []) or []

        self.log_signal_func(
            f"[목록] first "
            f"count={len(first_list)} "
            f"hasNext={first_result.get('hasNextPage')} "
            f"total={first_result.get('totalCount')}"
        )

        if not first_list:
            self.log_signal_func("[목록] 첫 페이지 list 비어있음")
            return items

        add_items(first_list)

        if should_stop_by_date(first_list):
            self.log_signal_func(f"[목록] 시작일({self.fr_date}) 이전 데이터 발견으로 목록 조회 중단")
            self.log_signal_func(f"[목록] 최종 수집 건수={len(items)}")
            return items

        seed: str | None = first_result.get("seed")
        last_info: list[Any] = first_result.get("lastInfo", []) or []
        has_next: bool = bool(first_result.get("hasNextPage"))
        page: int = 2

        while has_next and last_info:
            req: dict[str, Any] = json.loads(json.dumps(base_payload))
            req["articlePagingRequest"]["seed"] = seed
            req["articlePagingRequest"]["lastInfo"] = last_info

            self.log_signal_func(
                f"[목록] page={page} 요청 seed={'Y' if seed else 'N'} lastInfo={len(last_info)}"
            )

            fetch_res = self.browser_fetch_json(
                url=self.list_api_url,
                method="POST",
                payload=req,
                wait_sec=30,
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

    def collect_detail(self, items: list[dict[str, Any]], region_item) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []

        for i, info in enumerate(items, 1):
            article_no: str = str(info["articleNumber"])
            real_estate_type: str = str(info["realEstateType"])
            trade_type: str = str(info["tradeType"])

            self.log_signal_func(f"[상세] {i}/{len(items)} articleNumber={article_no} 시작")

            detail_fetch_res = self.browser_fetch_json(
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

            agent_fetch_res = self.browser_fetch_json(
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

            time.sleep(random.uniform(1.5, 2.2))

            detail = {
                "articleNumber": article_no,
                "realEstateType": real_estate_type,
                "tradeType": trade_type,
                "listItem": info,
                "detail": detail_fetch_res.get("json"),
                "agent_detail": agent_fetch_res.get("json")
            }

            self.detail_map_save(detail,region_item)



            time.sleep(random.uniform(2.2, 3.2))

        self.log_signal_func(f"[상세] 최종 수집 건수={len(details)}")
        return details



    def detail_map_save(self, detail, region_item):

        sido = region_item.get("시도")
        sigungu = region_item.get("시군구")
        eup_myeon_dong = region_item.get("읍면동")

        list_item = (detail or {}).get("listItem") or {}
        detail_result = ((detail or {}).get("detail") or {}).get("result") or {}
        agent_result = ((detail or {}).get("agent_detail") or {}).get("result") or {}

        list_space = list_item.get("spaceInfo") or {}
        list_building = list_item.get("buildingInfo") or {}
        list_verification = list_item.get("verificationInfo") or {}
        list_broker = list_item.get("brokerInfo") or {}
        list_article_detail = list_item.get("articleDetail") or {}
        list_address = list_item.get("address") or {}
        list_price = list_item.get("priceInfo") or {}
        list_coords = list_address.get("coordinates") or {}

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

        floor_text = list_article_detail.get("floorInfo", "")
        if not floor_text:
            target_floor = detail_floor.get("targetFloor", "")
            total_floor = detail_floor.get("totalFloor", "")
            if target_floor or total_floor:
                floor_text = f"{target_floor}/{total_floor}".strip("/")

        x = list_coords.get("xCoordinate", "")
        y = list_coords.get("yCoordinate", "")
        if x == "":
            x = detail_coords.get("xCoordinate", "")
        if y == "":
            y = detail_coords.get("yCoordinate", "")

        rs = {
            "게시번호": list_item.get("articleNumber", "") or detail_article.get("articleNumber", ""),
            "단지명": list_item.get("complexName", "") or detail_complex.get("complexName", ""),
            "동이름": list_item.get("dongName", "") or detail_complex.get("dongName", ""),
            "매매가": list_price.get("dealPrice", "") if list_price.get("dealPrice", "") != "" else detail_price.get("price", ""),
            "보증금": list_price.get("warrantyPrice", ""),
            "월세": list_price.get("rentPrice", ""),
            "공급면적": list_space.get("supplySpace", "") or detail_size.get("supplySpace", ""),
            "평수": detail_size.get("pyeongArea", ""),
            "대지면적": list_space.get("landSpace", ""),
            "연면적": list_space.get("floorSpace", ""),
            "건축면적": list_space.get("buildingSpace", ""),
            "전용면적": list_space.get("exclusiveSpace", "") or detail_size.get("exclusiveSpace", ""),
            "매물특징": list_article_detail.get("articleFeatureDescription", "") or detail_article.get("articleFeatureDescription", ""),
            "매물확인일": list_verification.get("articleConfirmDate", "") or detail_verification.get("articleConfirmDate", ""),
            "건축물용도": detail_article.get("buildingPrincipalUse", ""),
            "층정보": floor_text,
            "시도": list_address.get("city", ""),
            "시군구": list_address.get("division", ""),
            "읍면동": list_address.get("sector", ""),
            "중개사무소이름": agent_result.get("brokerageName", "") or list_broker.get("brokerageName", ""),
            "중개사이름": agent_result.get("brokerName", "") or list_broker.get("brokerName", ""),
            "중개사무소주소": agent_result.get("address", ""),
            "중개사무소번호": phone.get("brokerage", ""),
            "중개사핸드폰번호": phone.get("mobile", ""),
            "상위매물명": list_item.get("articleName", ""),
            "매물유형": list_item.get("realEstateType", ""),
            "거래유형": list_item.get("tradeType", ""),
            "등록일자": list_verification.get("exposureStartDate", "") or detail_verification.get("exposureStartDate", ""),
            "위도": y,
            "경도": x,
            "방향정보": list_article_detail.get("direction", "") or detail_space.get("direction", ""),
            "검색 주소": sido + " " + sigungu + " " + eup_myeon_dong,
        }

        self.excel_driver.append_to_csv(
            self.csv_filename,
            [rs],
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

        return ""