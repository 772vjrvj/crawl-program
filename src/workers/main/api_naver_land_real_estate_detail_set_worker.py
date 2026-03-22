# src/workers/main/api_naver_land_real_estate_detail_set_load_worker.py
from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverLandRealEstateDetailSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.search_trade_labels: List[str] = []
        self.search_trade_codes: List[str] = []
        self.search_rlet_labels: List[str] = []
        self.search_rlet_codes: List[str] = []

        self.csv_filename: Optional[str] = None
        self.current_cnt: int = 0
        self.total_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.driver: Any = None
        self.columns: List[Any] = []
        self.output_columns: List[str] = []
        self.region: List[Dict[str, Any]] = []
        self.setting_detail: List[Any] = []

        self.site_name: str = "네이버 부동산 상세"
        self.folder_path: str = ""
        self.out_dir: str = "output_naver_land_real_estate_detail"

        self.naver_loc_all_real_detail: List[Dict[str, Any]] = []
        self.detail_region_article_list: List[Dict[str, Any]] = []
        self.result_data_list: List[Dict[str, Any]] = []

        self.same_addr_article_url: str = "https://m.land.naver.com/article/getSameAddrArticle"
        self.fin_land_article_url: str = "https://fin.land.naver.com/articles"

        self.excel_driver: Optional[ExcelUtils] = None
        self.file_driver: Optional[FileUtils] = None
        self.selenium_driver: Optional[SeleniumUtils] = None
        self.api_client: Optional[APIClient] = None

        self.resource_sub_dir: str = ""
        self._cleaned_up: bool = False

        self.headers: Dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "referer": "https://m.land.naver.com/",
            "user-agent": (
                "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Mobile Safari/537.36"
            ),
        }

        self.RLET_TYPE_MAP: Dict[str, str] = {
            "A01": "아파트",
            "A02": "오피스텔",
            "C02": "빌라",
            "A06": "다세대/연립",
            "B01": "아파트 분양권",
            "B02": "오피스텔분양권",
            "A04": "재건축",
            "C04": "전원주택",
            "C03": "단독/다가구",
            "D05": "상가주택",
            "C06": "한옥주택",
            "F01": "재개발",
            "C01": "원룸",
            "D02": "상가",
            "D01": "사무실",
            "E02": "공장/창고",
            "D03": "건물",
            "E03": "토지",
            "E04": "지식산업센터",
            "D04": "상가건물",
            "Z00": "기타",
        }

        self.TRADE_TYPE_MAP: Dict[str, str] = {
            "A1": "매매",
            "B1": "전세",
            "B2": "월세",
            "B3": "단기임대",
        }

    # 초기화
    def init(self) -> bool:
        self._cleaned_up = False
        self.current_cnt = 0
        self.total_cnt = 0
        self.before_pro_value = 0.0
        self.detail_region_article_list = []
        self.result_data_list = []
        self.search_trade_labels = []
        self.search_trade_codes = []
        self.search_rlet_labels = []
        self.search_rlet_codes = []
        self.naver_loc_all_real_detail = []

        if self.columns is None:
            self.columns = []
        if self.region is None:
            self.region = []
        if self.setting_detail is None:
            self.setting_detail = []

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
        self.output_columns = self._extract_output_columns(self.columns)

        self.driver_set(False)

        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func(f"출력 컬럼 : {self.output_columns}")
        self.log_signal_func(f"상세 정보 : {self.setting_detail}")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        self.log_signal_func("시작합니다.")

        if self.file_driver is None:
            self.log_signal_func("[ERROR] file_driver 가 초기화되지 않았습니다.")
            return False

        if self.excel_driver is None:
            self.log_signal_func("[ERROR] excel_driver 가 초기화되지 않았습니다.")
            return False

        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

        self.excel_driver.init_csv(
            self.csv_filename,
            self.output_columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )

        self.naver_loc_all_real_detail = self.file_driver.read_json_array_from_resources(
            "naver_real_estate_data.json",
            "customers/naver_land_real_estate_detail"
        )

        if not self.naver_loc_all_real_detail:
            self.log_signal_func("지역 상세 JSON 데이터가 없습니다.")
            return False

        self._set_region_articles()

        if not self.detail_region_article_list:
            self.log_signal_func("수집 대상 지역/기사 목록이 없습니다.")
            return False

        self.log_signal_func(f"대상 지역 수: {len(self.detail_region_article_list)}")

        for index, article in enumerate(self.detail_region_article_list, start=1):
            if not self.running:
                self.log_signal_func("중지됨")
                break

            self.log_signal_func(
                f"지역 진행 {index}/{len(self.detail_region_article_list)} : "
                f"{article.get('시도', '')} {article.get('시군구', '')} {article.get('읍면동', '')}"
            )

            self._crawl_article_list(article)

            pro_value = (index / max(len(self.detail_region_article_list), 1)) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

        if self.result_data_list:
            self.excel_driver.append_to_csv(
                self.csv_filename,
                self.result_data_list,
                self.output_columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )
            self.result_data_list = []

        return True

    # 정리
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        try:
            if self.csv_filename and self.excel_driver:
                self.excel_driver.convert_csv_to_excel_and_delete(
                    csv_filename=self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.log_signal_func(f"[cleanup] driver.quit 실패: {e}")

        try:
            if self.api_client:
                self.api_client.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")

        try:
            if self.selenium_driver and hasattr(self.selenium_driver, "close"):
                self.selenium_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] selenium_driver.close 실패: {e}")

        self.driver = None
        self.api_client = None
        self.file_driver = None
        self.excel_driver = None
        self.selenium_driver = None
        self.csv_filename = None
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    # 드라이버 세팅
    def driver_set(self, headless: bool) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.selenium_driver = SeleniumUtils(headless=headless)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        # 기존 프로젝트 SeleniumUtils 시그니처에 맞게 사용
        self.driver = self.selenium_driver.start_driver(
            timeout=1200,
            view_mode="mobile",
            window_size=(520, 980),
            mobile_metrics=(430, 932),
        )

    # =========================
    # 메인 수집
    # =========================

    def _set_region_articles(self) -> None:
        self.detail_region_article_list = []

        if not self.region:
            self.detail_region_article_list = list(self.naver_loc_all_real_detail)
            self.total_cnt = len(self.detail_region_article_list)
            return

        for item in self.region:
            sido = str(item.get("시도") or "").strip()
            sigungu = str(item.get("시군구") or "").strip()
            eupmyeondong = str(item.get("읍면동") or "").strip()

            found = self._find_location_detail(sido, sigungu, eupmyeondong)
            if found:
                self.detail_region_article_list.append(found)
            else:
                self.log_signal_func(f"지역 상세 정보 없음: {sido} {sigungu} {eupmyeondong}")

        self.total_cnt = len(self.detail_region_article_list)

    def _find_location_detail(
            self,
            sido: str,
            sigungu: str,
            eupmyeondong: str
    ) -> Optional[Dict[str, Any]]:
        for row in self.naver_loc_all_real_detail:
            if (
                    str(row.get("시도") or "").strip() == sido
                    and str(row.get("시군구") or "").strip() == sigungu
                    and str(row.get("읍면동") or "").strip() == eupmyeondong
            ):
                return row
        return None

    def _crawl_article_list(self, article: Dict[str, Any]) -> None:
        article_list_url = str(article.get("articleList") or "").strip()
        if not article_list_url:
            self.log_signal_func("articleList URL 없음")
            return

        trad_codes, rlet_codes = self._pick_detail_codes()

        page = 1
        empty_count = 0

        while self.running:
            list_url = self._replace_query_params(
                article_list_url,
                page=page,
                tradTpCd=self._join_codes(trad_codes) if trad_codes else None,
                rletTpCd=self._join_codes(rlet_codes) if rlet_codes else None,
            )

            self.log_signal_func(f"목록 조회 page={page} url={list_url}")

            try:
                if self.api_client is None:
                    self.log_signal_func("api_client 없음")
                    return

                res = self.api_client.get(url=list_url, headers=self.headers)
            except Exception as e:
                self.log_signal_func(f"목록 요청 실패: {e}")
                return

            items = self._extract_article_items(res)
            if not items:
                empty_count += 1
                if empty_count >= 1:
                    break
                page += 1
                continue

            empty_count = 0

            for idx, item in enumerate(items, start=1):
                if not self.running:
                    break

                item_dict = item if isinstance(item, dict) else {}
                atcl_no = str(
                    item_dict.get("atclNo")
                    or item_dict.get("articleNo")
                    or item_dict.get("atclNoEnc")
                    or ""
                ).strip()

                if not atcl_no:
                    continue

                self.log_signal_func(
                    f"매물 진행 page={page}, idx={idx}/{len(items)}, atclNo={atcl_no}"
                )

                if self._should_fetch_detail(item_dict):
                    detail_url = f"{self.fin_land_article_url}/{atcl_no}"
                    out_obj = self._fetch_detail(detail_url, item_dict, atcl_no, article)
                    self.log_signal_func(f"매물 결과: {out_obj}")
                    if out_obj:
                        self.result_data_list.append(out_obj)
                else:
                    self._crawl_same_addr(atcl_no, article)

                self.current_cnt += 1

                if len(self.result_data_list) >= 20 and self.excel_driver and self.csv_filename:
                    self.excel_driver.append_to_csv(
                        self.csv_filename,
                        self.result_data_list,
                        self.output_columns,
                        folder_path=self.folder_path,
                        sub_dir=self.out_dir
                    )
                    self.result_data_list = []

                time.sleep(random.uniform(0.4, 0.9))

            page += 1
            if page > 50:
                break

    def _crawl_same_addr(self, atcl_no: str, article: Dict[str, Any]) -> None:
        try:
            if self.api_client is None:
                return

            params: Dict[str, Any] = {
                "atclNo": atcl_no,
            }

            cortar_no = article.get("cortarNo") or article.get("cortar_no")
            if cortar_no:
                params["cortarNo"] = cortar_no

            trad_codes, rlet_codes = self._pick_detail_codes()
            if trad_codes:
                params["tradTpCd"] = self._join_codes(trad_codes)
            if rlet_codes:
                params["rletTpCd"] = self._join_codes(rlet_codes)

            res = self.api_client.get(
                url=self.same_addr_article_url,
                headers=self.headers,
                params=params
            )

            items = self._extract_article_items(res)
            if not items:
                return

            for same_item in items:
                if not self.running:
                    break

                same_dict = same_item if isinstance(same_item, dict) else {}
                if not self._should_fetch_detail(same_dict):
                    continue

                article_number = str(
                    same_dict.get("atclNo")
                    or same_dict.get("articleNo")
                    or ""
                ).strip()
                if not article_number:
                    continue

                detail_url = f"{self.fin_land_article_url}/{article_number}"
                out_obj = self._fetch_detail(detail_url, same_dict, article_number, article)
                self.log_signal_func(f"매물 결과: {out_obj}")
                if out_obj:
                    self.result_data_list.append(out_obj)

        except Exception as e:
            self.log_signal_func(f"_crawl_same_addr 실패: {e}")

    def _should_fetch_detail(self, first: Dict[str, Any]) -> bool:
        if not isinstance(first, dict):
            return False

        trad_codes, rlet_codes = self._pick_detail_codes()

        item_trad = str(first.get("tradTpCd") or first.get("tradeTypeCode") or "").strip()
        item_rlet = str(first.get("rletTpCd") or first.get("realEstateTypeCode") or "").strip()

        if trad_codes and item_trad and item_trad not in trad_codes:
            return False

        if rlet_codes and item_rlet and item_rlet not in rlet_codes:
            return False

        return True

    def _fetch_detail(
            self,
            url: str,
            parent: Dict[str, Any],
            article_number: str,
            article: Dict[str, Any]
    ) -> Dict[str, Any]:
        result_data: Dict[str, Any] = {}

        try:
            if self.driver is None:
                self.log_signal_func("driver 없음")
                return result_data

            self.driver.get(url)
            self._wait_ready_state_complete(7)
            time.sleep(random.uniform(0.8, 1.5))

            html = self.driver.page_source or ""
            if not html:
                self.log_signal_func(f"상세 HTML 비어있음: {article_number}")
                return result_data

            payload_text = self._collect_next_f_payload_text(html)
            results_by_key = self._extract_dehydrated_state(payload_text)
            result_data = self._build_result_data(
                results_by_key=results_by_key,
                parent=parent,
                article_number=article_number,
                article=article,
                url=url,
                html=html
            )

            return result_data

        except Exception as e:
            self.log_signal_func(f"_fetch_detail 실패 ({article_number}): {e}")
            return result_data

    # =========================
    # 결과 객체 생성
    # =========================

    def _build_result_data(
            self,
            results_by_key: Dict[str, Any],
            parent: Dict[str, Any],
            article_number: str,
            article: Dict[str, Any],
            url: str,
            html: str
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        trade_code = self._to_text(self._first_value(
            [results_by_key, parent],
            ["tradTpCd", "tradeTypeCode", "tradeType"]
        ))
        rlet_code = self._normalize_rlet_code(self._first_value(
            [results_by_key, parent],
            ["rletTpCd", "realEstateTypeCode", "realEstateType", "buildingType"]
        ))

        brokerage_phone, mobile_phone = self._pick_phone_numbers(results_by_key)
        floor_text = self._pick_floor_text(results_by_key)
        if not floor_text:
            floor_text = self._parse_floor_text_from_dom(html)

        supply_space = self._first_value(
            [results_by_key, parent],
            ["supplySpace", "spc1", "supplyArea", "area1"]
        )
        exclusive_space = self._first_value(
            [results_by_key, parent],
            ["exclusiveSpace", "spc2", "exclusiveArea", "area2"]
        )

        pyeong_area = self._first_value(
            [results_by_key, parent],
            ["pyeongArea", "exclusivePy", "supplyPy"]
        )
        if pyeong_area in [None, "", [], {}]:
            pyeong_area = self._calc_pyeong(exclusive_space if exclusive_space not in [None, "", [], {}] else supply_space)

        out["게시번호"] = self._to_text(article_number)
        out["단지명"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["complexName", "cpxNm"]
        ))
        out["동이름"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["dongName", "bildNm", "buildingName"]
        ))
        out["매매가"] = self._first_value(
            [results_by_key, parent],
            ["price", "dealOrWarrantPrc", "prcInfo"]
        )
        out["보증금"] = self._first_value(
            [results_by_key, parent],
            ["warrantyAmount", "wrtPrc", "depositPrice"]
        )
        out["월세"] = self._first_value(
            [results_by_key, parent],
            ["rentAmount", "rentPrc", "rentPrice"]
        )
        out["공급면적"] = self._to_text(supply_space)
        out["평수"] = self._to_text(pyeong_area)
        out["대지면적"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["landSpace", "landArea", "siteArea"]
        ))
        out["연면적"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["floorSpace", "totalFloorArea", "grossFloorArea"]
        ))
        out["건축면적"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["buildingSpace", "buildingArea"]
        ))
        out["전용면적"] = self._to_text(exclusive_space)
        out["매물특징"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["articleFeatureDescription", "articleFeatureDesc", "featureDesc", "detailDescription", "description"]
        ))
        out["매물확인일"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["exposureStartDate", "articleConfirmYmd", "articleConfirmDate", "confirmDate"]
        ))
        out["건축물용도"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["buildingPrincipalUse", "principalUse", "buildingUse"]
        ))
        out["층정보"] = self._to_text(floor_text)

        out["시도"] = self._to_text(article.get("시도") or self._first_value(results_by_key, ["city"]))
        out["시군구"] = self._to_text(article.get("시군구") or self._first_value(results_by_key, ["division"]))
        out["읍면동"] = self._to_text(article.get("읍면동") or self._first_value(results_by_key, ["sector"]))
        out["번지"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["jibun", "jibunAddress"]
        ))
        out["도로명주소"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["roadName", "roadAddress", "detailAddress"]
        ))
        out["우편번호"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["zipCode", "zipcode"]
        ))
        out["전체주소"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["full_addr", "fullAddress", "regionName", "address"]
        ))

        out["중개사무소이름"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["brokerage_name", "tradeBizNm", "agentName", "realtorName", "brokerageName"]
        ))
        out["중개사이름"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["broker_name", "bossName", "representativeName", "brokerName"]
        ))
        out["중개사무소주소"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["broker_address", "brokerageAddress", "agentAddress", "address"]
        ))
        out["중개사무소번호"] = self._to_text(brokerage_phone)
        out["중개사핸드폰번호"] = self._to_text(mobile_phone)

        out["URL"] = self._to_text(url)

        out["상위매물명"] = self._to_text(self._first_value(
            parent,
            ["atclNm", "articleName", "articleTitle"]
        ))
        out["상위매물동"] = self._to_text(self._first_value(
            parent,
            ["bildNm", "dongName", "buildingName"]
        ))
        out["상위매물게시번호"] = self._to_text(self._first_value(
            parent,
            ["atclNo", "articleNo"]
        ))
        out["매물유형"] = self.RLET_TYPE_MAP.get(rlet_code, self._to_text(self._first_value(
            [results_by_key, parent],
            ["rletType", "realEstateTypeName"]
        )))
        out["거래유형"] = self.TRADE_TYPE_MAP.get(trade_code, self._to_text(self._first_value(
            [results_by_key, parent],
            ["tradeTypeName", "tradeType"]
        )))
        out["검색 주소"] = self._build_parts_text(article)
        out["검색 매물유형"] = ", ".join(self.search_rlet_labels)
        out["검색 거래유형"] = ", ".join(self.search_trade_labels)

        # 선택되지 않은 컬럼은 append_to_csv 에서 걸러질 수 있지만,
        # 혹시 모를 누락 방지용으로 출력 컬럼 기본값도 맞춰둠
        self._ensure_output_keys(out)

        return out

    # =========================
    # Next.js / payload 파싱
    # =========================

    def _collect_next_f_payload_text(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            texts: List[str] = []

            for script in soup.find_all("script"):
                script_text = script.string or script.get_text()
                if not script_text:
                    continue

                if "__NEXT_DATA__" in script_text:
                    texts.append(script_text)
                elif "self.__next_f.push" in script_text:
                    texts.append(script_text)
                elif "__PRELOADED_STATE__" in script_text:
                    texts.append(script_text)
                elif "dehydratedState" in script_text:
                    texts.append(script_text)

            if texts:
                return "\n".join(texts)

            return html
        except Exception:
            return html

    def _extract_dehydrated_state(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}

        # 1) __NEXT_DATA__
        m = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
            text,
            flags=re.S
        )
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 2) window.__PRELOADED_STATE__
        m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*', text)
        if m:
            start_idx = text.find("{", m.end())
            if start_idx >= 0:
                json_str = self._extract_balanced_braces(text, start_idx)
                if json_str:
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass

        # 3) dehydratedState
        m = re.search(r'"dehydratedState"\s*:\s*', text)
        if m:
            start_idx = text.find("{", m.end())
            if start_idx >= 0:
                json_str = self._extract_balanced_braces(text, start_idx)
                if json_str:
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass

        # 4) self.__next_f.push(...)
        if "self.__next_f.push" in text:
            data = self._extract_next_f_state(text)
            if data:
                return data

        # 5) 첫 JSON 객체 시도
        first_brace = text.find("{")
        if first_brace >= 0:
            json_str = self._extract_balanced_braces(text, first_brace)
            if json_str:
                try:
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        return {}

    def _extract_next_f_state(self, text: str) -> Dict[str, Any]:
        chunks = self._extract_next_f_chunks(text)
        if not chunks:
            return {}

        out: Dict[str, Any] = {
            "queries": [],
            "query_map": {},
            "merged_result": {},
            "raw_chunks": chunks,
        }

        for chunk in chunks:
            for raw_line in chunk.splitlines():
                line = str(raw_line or "").strip()
                if not line or ":" not in line:
                    continue

                prefix, payload = line.split(":", 1)
                prefix = prefix.strip()
                payload = payload.strip()

                if not re.fullmatch(r"[0-9a-zA-Z]+", prefix):
                    continue

                if not payload or payload[0] not in ["[", "{"]:
                    continue

                try:
                    obj = json.loads(payload)
                except Exception:
                    continue

                self._collect_next_f_query_info(obj, out)

        if out["queries"] or out["query_map"] or out["merged_result"]:
            return out

        return {}

    def _extract_next_f_chunks(self, text: str) -> List[str]:
        chunks: List[str] = []

        pattern = re.compile(
            r'self\.__next_f\.push\(\[\s*\d+\s*,\s*"((?:\\.|[^"\\])*)"\s*\]\)',
            flags=re.S
        )

        for match in pattern.finditer(text):
            raw_chunk = match.group(1)
            if not raw_chunk:
                continue

            try:
                decoded = json.loads(f"\"{raw_chunk}\"")
                if decoded:
                    chunks.append(decoded)
            except Exception:
                try:
                    decoded = bytes(raw_chunk, "utf-8").decode("unicode_escape")
                    if decoded:
                        chunks.append(decoded)
                except Exception:
                    continue

        return chunks

    def _collect_next_f_query_info(self, data: Any, out: Dict[str, Any]) -> None:
        if isinstance(data, dict):
            state = data.get("state")
            if isinstance(state, dict):
                queries = state.get("queries")
                if isinstance(queries, list):
                    self._append_query_infos(queries, out)

            for value in data.values():
                self._collect_next_f_query_info(value, out)

        elif isinstance(data, list):
            for item in data:
                self._collect_next_f_query_info(item, out)

    def _append_query_infos(self, queries: List[Any], out: Dict[str, Any]) -> None:
        for query in queries:
            if not isinstance(query, dict):
                continue

            out["queries"].append(query)

            query_key = query.get("queryKey")
            query_name = ""

            if isinstance(query_key, list) and query_key:
                query_name = str(query_key[0] or "").strip()

            if not query_name:
                query_name = str(query.get("queryHash") or "").strip()

            state = query.get("state") if isinstance(query.get("state"), dict) else {}
            data_obj = state.get("data") if isinstance(state.get("data"), dict) else {}
            result = data_obj.get("result")

            if query_name:
                out["query_map"][query_name] = result

            if isinstance(result, dict):
                self._merge_dict_recursive(out["merged_result"], result)

    def _merge_dict_recursive(self, target: Dict[str, Any], src: Dict[str, Any]) -> None:
        for key, value in src.items():
            if key not in target:
                target[key] = value
                continue

            if isinstance(target.get(key), dict) and isinstance(value, dict):
                self._merge_dict_recursive(target[key], value)

    def _extract_balanced_braces(self, s: str, start_idx: int) -> str:
        if start_idx < 0 or start_idx >= len(s) or s[start_idx] != "{":
            return ""

        depth = 0
        in_str = False
        escape = False

        for i in range(start_idx, len(s)):
            ch = s[i]

            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start_idx:i + 1]

        return ""

    # =========================
    # 파싱 보조
    # =========================

    def _wait_ready_state_complete(self, timeout_sec: int = 7) -> None:
        try:
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: self._is_ready_state_complete(d)
            )
        except TimeoutException:
            self.log_signal_func("readyState complete 대기 timeout")

    def _is_ready_state_complete(self, driver: Any) -> bool:
        try:
            state = driver.execute_script("return document.readyState")
            return state == "complete"
        except Exception:
            return False

    def _parse_floor_text_from_dom(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text("\n", strip=True)

            patterns = [
                r"층\s*정보[:\s]*([^\n]+)",
                r"해당층[:\s]*([^\n]+)",
                r"층수[:\s]*([^\n]+)",
                r"(\d+층\s*/\s*\d+층)",
            ]

            for pattern in patterns:
                m = re.search(pattern, text)
                if m:
                    return m.group(1).strip()

            return ""
        except Exception:
            return ""

    def _pick_floor_text(self, results_by_key: Dict[str, Any]) -> str:
        floor_value = self._first_value(
            results_by_key,
            ["floorText", "flrInfo", "floorInfo", "targetFloor", "totalFloor"]
        )

        if isinstance(floor_value, dict):
            target_floor = str(floor_value.get("targetFloor") or "").strip()
            total_floor = str(floor_value.get("totalFloor") or "").strip()

            if target_floor and total_floor:
                return f"{target_floor}/{total_floor}층"
            if target_floor:
                return target_floor
            if total_floor:
                return f"{total_floor}층"

        return self._to_text(floor_value)

    def _pick_phone_numbers(self, results_by_key: Dict[str, Any]) -> Tuple[str, str]:
        phone_value = self._first_value(
            results_by_key,
            ["cpPc", "phone", "phoneNo", "mobile"]
        )

        brokerage_phone = ""
        mobile_phone = ""

        if isinstance(phone_value, dict):
            brokerage_phone = str(
                phone_value.get("brokerage")
                or phone_value.get("phone")
                or phone_value.get("tel")
                or ""
            ).strip()

            mobile_phone = str(
                phone_value.get("mobile")
                or phone_value.get("cell")
                or ""
            ).strip()
            return brokerage_phone, mobile_phone

        phone_text = self._to_text(phone_value)
        return phone_text, ""

    def _calc_pyeong(self, value: Any) -> str:
        number = self._extract_first_float(value)
        if number is None:
            return ""
        return f"{round(number / 3.305785, 2)}"

    def _extract_first_float(self, value: Any) -> Optional[float]:
        if value in [None, "", [], {}]:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value)
        match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
        if not match:
            return None

        try:
            return float(match.group(1))
        except Exception:
            return None

    # =========================
    # 컬럼 / 코드 / 텍스트 유틸
    # =========================

    def _extract_output_columns(self, columns: List[Any]) -> List[str]:
        out: List[str] = []

        for col in columns or []:
            if isinstance(col, dict):
                checked = bool(col.get("checked", False))
                value = str(col.get("value") or "").strip()
                if checked and value:
                    out.append(value)
            else:
                value = str(col).strip()
                if value:
                    out.append(value)

        return out

    def _ensure_output_keys(self, out: Dict[str, Any]) -> None:
        for col in self.output_columns:
            if col not in out:
                out[col] = ""

    def _pick_detail_codes(self) -> Tuple[List[str], List[str]]:
        if self.search_trade_codes or self.search_rlet_codes:
            return self.search_trade_codes, self.search_rlet_codes

        self.search_trade_codes, self.search_trade_labels = self._normalize_search_config(
            raw_value=(
                    self.get_setting_value(self.setting, "search_trade")
                    or self.get_setting_value(self.setting, "trade_type")
                    or self.get_setting_value(self.setting, "tradTpCd")
            ),
            code_map=self.TRADE_TYPE_MAP
        )

        self.search_rlet_codes, self.search_rlet_labels = self._normalize_search_config(
            raw_value=(
                    self.get_setting_value(self.setting, "search_rlet")
                    or self.get_setting_value(self.setting, "rlet_type")
                    or self.get_setting_value(self.setting, "rletTpCd")
            ),
            code_map=self.RLET_TYPE_MAP
        )

        # setting_detail 도 같이 보조 반영
        for item in self.setting_detail or []:
            if not isinstance(item, dict):
                continue

            key = str(item.get("key") or item.get("name") or "").strip()
            value = item.get("value")

            if key in ["거래유형", "search_trade", "trade_type", "tradTpCd"] and not self.search_trade_codes:
                self.search_trade_codes, self.search_trade_labels = self._normalize_search_config(
                    raw_value=value,
                    code_map=self.TRADE_TYPE_MAP
                )

            if key in ["매물유형", "search_rlet", "rlet_type", "rletTpCd"] and not self.search_rlet_codes:
                self.search_rlet_codes, self.search_rlet_labels = self._normalize_search_config(
                    raw_value=value,
                    code_map=self.RLET_TYPE_MAP
                )

        return self.search_trade_codes, self.search_rlet_codes

    def _normalize_search_config(
            self,
            raw_value: Any,
            code_map: Dict[str, str]
    ) -> Tuple[List[str], List[str]]:
        if raw_value is None:
            return [], []

        values: List[str] = []

        if isinstance(raw_value, list):
            for v in raw_value:
                s = str(v).strip()
                if s:
                    values.append(s)
        else:
            text = str(raw_value).strip()
            if text:
                values = re.split(r"[,|:/]+", text)

        reverse_map: Dict[str, str] = {v: k for k, v in code_map.items()}
        codes: List[str] = []
        labels: List[str] = []

        for item in values:
            s = str(item).strip()
            if not s:
                continue

            if s in code_map:
                if s not in codes:
                    codes.append(s)
                label = code_map.get(s, "")
                if label and label not in labels:
                    labels.append(label)
                continue

            if s in reverse_map:
                code = reverse_map[s]
                if code not in codes:
                    codes.append(code)
                if s not in labels:
                    labels.append(s)

        return codes, labels

    def _replace_query_params(self, url: str, **repl: Any) -> str:
        parsed = urlparse(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_map: Dict[str, str] = {k: v for k, v in pairs}

        for k, v in repl.items():
            if v is None:
                continue
            query_map[k] = str(v)

        new_query = urlencode(query_map, doseq=True)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        ))

    def _join_codes(self, values: List[Any]) -> str:
        new_values: List[str] = []
        for v in values:
            s = str(v).strip()
            if s and s not in new_values:
                new_values.append(s)
        return ":".join(new_values)

    def _extract_article_items(self, res: Any) -> List[Dict[str, Any]]:
        if res is None:
            return []

        if isinstance(res, list):
            return [x for x in res if isinstance(x, dict)]

        if isinstance(res, dict):
            candidates = [
                res.get("body"),
                res.get("result"),
                res.get("articleList"),
                res.get("list"),
                res.get("items"),
            ]

            for candidate in candidates:
                if isinstance(candidate, list):
                    return [x for x in candidate if isinstance(x, dict)]

                if isinstance(candidate, dict):
                    for key in ["list", "items", "articleList"]:
                        arr = candidate.get(key)
                        if isinstance(arr, list):
                            return [x for x in arr if isinstance(x, dict)]

        if isinstance(res, str):
            try:
                data = json.loads(res)
                return self._extract_article_items(data)
            except Exception:
                return []

        return []

    def _build_parts_text(self, article: Dict[str, Any]) -> str:
        parts = [
            str(article.get("시도") or "").strip(),
            str(article.get("시군구") or "").strip(),
            str(article.get("읍면동") or "").strip(),
        ]
        return " ".join([x for x in parts if x])

    def _normalize_rlet_code(self, value: Any) -> str:
        code = str(value or "").strip()
        if not code:
            return ""

        if code in self.RLET_TYPE_MAP:
            return code

        if len(code) >= 3 and code[:3] in self.RLET_TYPE_MAP:
            return code[:3]

        return code

    def _to_text(self, value: Any) -> str:
        if value in [None, "", [], {}]:
            return ""

        if isinstance(value, dict):
            for key in [
                "full_addr", "fullAddress", "regionName", "address",
                "roadName", "roadAddress", "jibunAddress"
            ]:
                inner = value.get(key)
                if inner not in [None, "", [], {}]:
                    return self._to_text(inner)

            parts: List[str] = []
            for v in value.values():
                s = self._to_text(v)
                if s and s not in parts:
                    parts.append(s)
            return " / ".join(parts)

        if isinstance(value, list):
            parts = []
            for item in value:
                s = self._to_text(item)
                if s and s not in parts:
                    parts.append(s)
            return ", ".join(parts)

        return str(value).strip()

    def _first_value(self, data: Any, keys: List[str]) -> Any:
        for key in keys:
            value = self._deep_find_first(data, key)
            if value not in [None, "", [], {}]:
                return value
        return ""

    def _deep_find_first(self, data: Any, target_key: str) -> Any:
        if isinstance(data, dict):
            if target_key in data:
                return data.get(target_key)

            # === 신규 === Next.js merged_result / query_map 우선 탐색
            if "merged_result" in data:
                found = self._deep_find_first(data.get("merged_result"), target_key)
                if found not in [None, "", [], {}]:
                    return found

            if "query_map" in data and isinstance(data.get("query_map"), dict):
                for qv in data["query_map"].values():
                    found = self._deep_find_first(qv, target_key)
                    if found not in [None, "", [], {}]:
                        return found

            for v in data.values():
                found = self._deep_find_first(v, target_key)
                if found not in [None, "", [], {}]:
                    return found

        elif isinstance(data, list):
            for item in data:
                found = self._deep_find_first(item, target_key)
                if found not in [None, "", [], {}]:
                    return found

        return None