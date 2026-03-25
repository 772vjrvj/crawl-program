# src/workers/main/api_naver_land_real_estate_detail_set_load_worker.py

from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime  # === 신규 ===
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

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

        # === 신규 ===
        self.eng: bool = False

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

        self.SORT_MAP = {
            "랭킹순": "rank",
            "높은가격순": "highPrc",
            "낮은가격순": "lowPrc",
            "최신순": "dates",
            "면적순": "highSpc",
        }

    # 실행 전 준비
    def init(self) -> bool:
        self.current_cnt = 0
        self.total_cnt = 0
        self.before_pro_value = 0.0
        self.detail_region_article_list = []
        self.result_data_list = []
        self.naver_loc_all_real_detail = []
        self.search_trade_codes = []
        self.search_trade_labels = []
        self.search_rlet_codes = []
        self.search_rlet_labels = []

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        # === 신규 ===
        self.eng = bool(self.get_setting_value(self.setting, "eng"))
        if self.eng:
            self.columns = self._get_eng_columns()

        self._resolve_search_filters()
        self.driver_set(False)

        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func(f"상세 정보 : {self.setting_detail}")
        self.log_signal_func(self._build_filter_log_text())
        return True

    # 프로그램 실행
    def main(self) -> bool:
        self.log_signal_func("시작합니다.")

        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))
        self.excel_driver.init_csv(
            self.csv_filename,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )
        if not self.region:
            self.log_signal_func("지역 데이터가 없습니다.")
            return False

        self.naver_loc_all_real_detail = self.file_driver.read_json_array_from_resources(
            "naver_real_estate_data.json",
            "customers/naver_land_real_estate_detail",
        )
        if not self.naver_loc_all_real_detail:
            self.log_signal_func("지역 상세 JSON 데이터가 없습니다.")
            return False

        self._set_region_articles()
        if not self.detail_region_article_list:
            self.log_signal_func("수집 대상 지역/기사 목록이 없습니다.")
            return False

        total_region_count = len(self.detail_region_article_list)
        self.log_signal_func(f"대상 지역 수: {total_region_count}")

        for index, article in enumerate(self.detail_region_article_list, start=1):
            if not self.running:
                self.log_signal_func("중지됨")
                break

            self.log_signal_func(
                f"지역 진행 {index}/{total_region_count} : "
                f"{article.get('시도', '')} {article.get('시군구', '')} {article.get('읍면동', '')}"
            )
            self._crawl_article_list(article)

            pro_value = (index / max(total_region_count, 1)) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

            time.sleep(random.uniform(2, 4))

        self._flush_result_data()
        return True

    # 정리
    def cleanup(self) -> None:
        try:
            if self.csv_filename and self.excel_driver:
                self.excel_driver.convert_csv_to_excel_and_delete(
                    csv_filename=self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
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
        self.driver = self.selenium_driver.start_driver(
            timeout=1200,
            view_mode="mobile",
            window_size=(520, 980),
            mobile_metrics=(430, 932),
        )

    # 지역별 article URL 세팅
    def _set_region_articles(self) -> None:
        self.detail_region_article_list = []

        for item in self.region:
            found = self._find_location_detail(
                sido=str(item.get("시도") or "").strip(),
                sigungu=str(item.get("시군구") or "").strip(),
                eupmyeondong=str(item.get("읍면동") or "").strip(),
            )
            if found:
                self.detail_region_article_list.append(self._apply_search_filters_to_article(found))
            else:
                self.log_signal_func(
                    f"지역 상세 정보 없음: {item.get('시도', '')} {item.get('시군구', '')} {item.get('읍면동', '')}"
                )

        self.total_cnt = len(self.detail_region_article_list)

    def _find_location_detail(self, sido: str, sigungu: str, eupmyeondong: str) -> Optional[Dict[str, Any]]:
        for row in self.naver_loc_all_real_detail:
            if (
                    str(row.get("시도") or "").strip() == sido
                    and str(row.get("시군구") or "").strip() == sigungu
                    and str(row.get("읍면동") or "").strip() == eupmyeondong
            ):
                return row
        return None

    def _apply_search_filters_to_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(article)
        article_list_url = str(item.get("articleList") or "").strip()
        cluster_list_url = str(item.get("clusterList_url") or "").strip()

        if article_list_url:
            updated_article_list = self._apply_url_filters(article_list_url)
            item["articleList"] = updated_article_list
            if updated_article_list != article_list_url:
                self.log_signal_func(
                    f"articleList 필터 적용 [{self._build_parts_text(item)}] "
                    f"tradTpCd={self._get_query_value(updated_article_list, 'tradTpCd')} "
                    f"rletTpCd={self._get_query_value(updated_article_list, 'rletTpCd')} "
                    f"sort={self._get_query_value(updated_article_list, 'sort')}"
                )

        if cluster_list_url:
            updated_cluster_list = self._apply_url_filters(cluster_list_url)
            item["clusterList_url"] = updated_cluster_list

        cortar_no = self._pick_cortar_no(item)
        if cortar_no:
            item["cortarNo"] = cortar_no

        return item

    def _crawl_article_list(self, article: Dict[str, Any]) -> None:
        article_list_url = str(article.get("articleList") or "").strip()
        if not article_list_url:
            self.log_signal_func("articleList URL 없음")
            return

        fr_date: str = str(self.get_setting_value(self.setting, "fr_date") or "").strip()
        to_date: str = str(self.get_setting_value(self.setting, "to_date") or "").strip()
        sort_code: str = self._get_selected_sort_code()
        is_latest_sort: bool = (sort_code == "dates")

        page = 1
        max_count = 100

        while self.running:
            replace_values: Dict[str, Any] = {"page": page}
            if sort_code:
                replace_values["sort"] = sort_code

            list_url = self._replace_query_params(article_list_url, **replace_values)
            self.log_signal_func(f"목록 조회 page={page} sort={sort_code or '원본유지'} url={list_url}")

            res = self.api_client.get(url=list_url, headers=self.headers)
            items = self._extract_article_items(res)
            if not items:
                break

            should_break_paging = False

            for idx, item in enumerate(items, start=1):
                if not self.running:
                    break

                item_atcl_cfm_ymd = self._normalize_atcl_cfm_ymd(item.get("atclCfmYmd"))

                # 최신순일 때만 시작일 이전이면 이후 페이지도 볼 필요 없음
                if is_latest_sort and fr_date and item_atcl_cfm_ymd and item_atcl_cfm_ymd < fr_date:
                    self.log_signal_func(
                        f"등록일자 기준 페이지 조회 종료: page={page}, idx={idx}, "
                        f"atclCfmYmd={item_atcl_cfm_ymd}, fr_date={fr_date}"
                    )
                    should_break_paging = True
                    break

                # 목록 단계에서 바로 등록일자 필터
                if not self._is_date_in_range(item_atcl_cfm_ymd, fr_date, to_date):
                    continue

                atcl_no = str(item.get("atclNo") or item.get("articleNo") or item.get("atclNoEnc") or "").strip()
                if not atcl_no:
                    continue

                self.log_signal_func(
                    f"매물 진행 page={page}, idx={idx}/{len(items)}, "
                    f"atclNo={atcl_no}, atclCfmYmd={item_atcl_cfm_ymd}"
                )

                if self._should_fetch_detail(item):
                    self._apply_same_addr_price_range(item)
                    detail_url = f"{self.fin_land_article_url}/{atcl_no}"
                    out_obj = self._fetch_detail(detail_url, item, atcl_no, article)
                    self.log_signal_func(f"매물 결과: {out_obj}")
                    if out_obj:
                        self.result_data_list.append(out_obj)
                else:
                    self._crawl_same_addr(atcl_no, article)

                self.current_cnt += 1
                if len(self.result_data_list) >= 20:
                    self._flush_result_data()

                time.sleep(random.uniform(0.4, 0.9))

            if should_break_paging:
                break

            time.sleep(random.uniform(1, 1.5))
            page += 1
            if page > max_count:
                break

    def _crawl_same_addr(self, atcl_no: str, article: Dict[str, Any]) -> None:
        try:
            if not self.api_client:
                return

            fr_date: str = str(self.get_setting_value(self.setting, "fr_date") or "").strip()
            to_date: str = str(self.get_setting_value(self.setting, "to_date") or "").strip()

            params: Dict[str, Any] = {"atclNo": atcl_no}

            cortar_no = self._pick_cortar_no(article)
            if cortar_no:
                params["cortarNo"] = cortar_no
            if self.search_trade_codes:
                params["tradTpCd"] = self._join_codes(self.search_trade_codes)
            if self.search_rlet_codes:
                params["rletTpCd"] = self._join_codes(self.search_rlet_codes)

            self.log_signal_func(
                f"동일주소 조회 atclNo={atcl_no} tradTpCd={params.get('tradTpCd', '')} "
                f"rletTpCd={params.get('rletTpCd', '')}"
            )

            res = self.api_client.get(
                url=self.same_addr_article_url,
                headers=self.headers,
                params=params,
            )
            items = self._extract_article_items(res)
            if not items:
                return

            same_addr_min_prc, same_addr_max_prc = self._extract_same_addr_price_range(items)
            for same_item in items:
                same_item["sameAddrMinPrc"] = same_addr_min_prc
                same_item["sameAddrMaxPrc"] = same_addr_max_prc

            for same_item in items:
                if not self.running:
                    break

                item_atcl_cfm_ymd = self._normalize_atcl_cfm_ymd(same_item.get("atclCfmYmd"))
                if not self._is_date_in_range(item_atcl_cfm_ymd, fr_date, to_date):
                    continue

                if not self._should_fetch_detail(same_item):
                    continue

                article_number = str(same_item.get("atclNo") or same_item.get("articleNo") or "").strip()
                if not article_number:
                    continue

                detail_url = f"{self.fin_land_article_url}/{article_number}"
                out_obj = self._fetch_detail(detail_url, same_item, article_number, article)
                self.log_signal_func(f"매물 결과: {out_obj}")
                if out_obj:
                    self.result_data_list.append(out_obj)

        except Exception as e:
            self.log_signal_func(f"_crawl_same_addr 실패: {e}")

    def _should_fetch_detail(self, item: Dict[str, Any]) -> bool:
        item_trad = str(item.get("tradTpCd") or item.get("tradeTypeCode") or "").strip()
        item_rlet = self._normalize_rlet_code(item.get("rletTpCd") or item.get("realEstateTypeCode") or "")

        if self.search_trade_codes and item_trad and item_trad not in self.search_trade_codes:
            return False
        if self.search_rlet_codes and item_rlet and item_rlet not in self.search_rlet_codes:
            return False
        return True

    def _fetch_detail(
            self,
            url: str,
            parent: Dict[str, Any],
            article_number: str,
            article: Dict[str, Any],
    ) -> Dict[str, Any]:
        result_data: Dict[str, Any] = {}

        try:
            if not self.driver:
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
                html=html,
            )
            return result_data

        except Exception as e:
            self.log_signal_func(f"_fetch_detail 실패 ({article_number}): {e}")
            return result_data

    # 결과 객체 생성
    def _build_result_data(
            self,
            results_by_key: Dict[str, Any],
            parent: Dict[str, Any],
            article_number: str,
            article: Dict[str, Any],
            url: str,
            html: str,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        trade_code = self._to_text(self._first_value(
            [results_by_key, parent],
            ["tradTpCd", "tradeTypeCode", "tradeType"],
        ))
        rlet_code = self._normalize_rlet_code(self._first_value(
            [results_by_key, parent],
            ["rletTpCd", "realEstateTypeCode", "realEstateType", "buildingType"],
        ))

        brokerage_phone, mobile_phone = self._pick_phone_numbers(results_by_key)
        floor_text = self._pick_floor_text(results_by_key) or self._parse_floor_text_from_dom(html)

        supply_space = self._first_value(
            [results_by_key, parent],
            ["supplySpace", "spc1", "supplyArea", "area1"],
        )
        exclusive_space = self._first_value(
            [results_by_key, parent],
            ["exclusiveSpace", "spc2", "exclusiveArea", "area2"],
        )

        pyeong_area = self._first_value(
            [results_by_key, parent],
            ["pyeongArea", "exclusivePy", "supplyPy"],
        )
        if not pyeong_area:
            pyeong_area = self._calc_pyeong(exclusive_space or supply_space)

        out["게시번호"] = self._to_text(article_number)
        out["단지명"] = self._to_text(self._first_value([results_by_key, parent], ["complexName", "cpxNm"]))
        out["동이름"] = self._to_text(self._first_value([results_by_key, parent], ["dongName", "bildNm", "buildingName"]))
        out["매매가"] = self._format_price_value(self._first_value([results_by_key, parent], ["price", "dealOrWarrantPrc", "prcInfo"]))
        out["보증금"] = self._format_price_value(self._first_value([results_by_key, parent], ["warrantyAmount", "wrtPrc", "depositPrice"]))
        out["월세"] = self._format_price_value(self._first_value([results_by_key, parent], ["rentAmount", "rentPrc", "rentPrice"]))
        out["공급면적"] = self._to_text(supply_space)
        out["평수"] = self._to_text(pyeong_area)
        out["대지면적"] = self._to_text(self._first_value([results_by_key, parent], ["landSpace", "landArea", "siteArea"]))
        out["연면적"] = self._to_text(self._first_value([results_by_key, parent], ["floorSpace", "totalFloorArea", "grossFloorArea"]))
        out["건축면적"] = self._to_text(self._first_value([results_by_key, parent], ["buildingSpace", "buildingArea"]))
        out["전용면적"] = self._to_text(exclusive_space)
        out["매물특징"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["articleFeatureDescription", "articleFeatureDesc", "featureDesc", "detailDescription", "description"],
        ))
        out["매물확인일"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["exposureStartDate", "articleConfirmYmd", "articleConfirmDate", "confirmDate"],
        ))
        out["건축물용도"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["buildingPrincipalUse", "principalUse", "buildingUse"],
        ))
        out["층정보"] = self._normalize_floor_text(floor_text)

        out["시도"] = self._to_text(article.get("시도") or self._first_value(results_by_key, ["city"]))
        out["시군구"] = self._to_text(article.get("시군구") or self._first_value(results_by_key, ["division"]))
        out["읍면동"] = self._to_text(article.get("읍면동") or self._first_value(results_by_key, ["sector"]))
        out["번지"] = self._to_text(self._first_value([results_by_key, parent], ["jibun", "jibunAddress"]))
        out["도로명주소"] = self._to_text(self._first_value([results_by_key, parent], ["roadName", "roadAddress", "detailAddress"]))
        out["우편번호"] = self._to_text(self._first_value([results_by_key, parent], ["zipCode", "zipcode"]))
        out["전체주소"] = self._to_text(self._first_value([results_by_key, parent], ["full_addr", "fullAddress", "regionName", "address"]))

        out["중개사무소이름"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["brokerage_name", "tradeBizNm", "agentName", "realtorName", "brokerageName"],
        ))
        out["중개사이름"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["broker_name", "bossName", "representativeName", "brokerName"],
        ))
        out["중개사무소주소"] = self._to_text(self._first_value(
            [results_by_key, parent],
            ["broker_address", "brokerageAddress", "agentAddress", "address"],
        ))
        out["중개사무소번호"] = self._to_text(brokerage_phone)
        out["중개사핸드폰번호"] = self._to_text(mobile_phone)

        out["URL"] = self._to_text(url)
        out["상위매물명"] = self._to_text(self._first_value(parent, ["atclNm", "articleName", "articleTitle"]))
        out["상위매물동"] = self._to_text(self._first_value(parent, ["bildNm", "dongName", "buildingName"]))
        out["상위매물게시번호"] = self._to_text(self._first_value(parent, ["atclNo", "articleNo"]))
        out["매물유형"] = self.RLET_TYPE_MAP.get(rlet_code, self._to_text(self._first_value([results_by_key, parent], ["rletType", "realEstateTypeName"])))
        out["거래유형"] = self.TRADE_TYPE_MAP.get(trade_code, self._to_text(self._first_value([results_by_key, parent], ["tradeTypeName", "tradeType"])))
        out["검색 주소"] = self._build_parts_text(article)
        out["검색 매물유형"] = ", ".join(self.search_rlet_labels)
        out["검색 거래유형"] = ", ".join(self.search_trade_labels)

        # === 신규 ===
        tag_list = parent.get("tagList")
        if isinstance(tag_list, list):
            out["매물태그"] = ", ".join(
                [self._to_text(x) for x in tag_list if self._to_text(x)]
            )
        else:
            out["매물태그"] = self._to_text(tag_list)

        out["동일주소매물수"] = self._to_text(parent.get("sameAddrCnt"))
        out["동일주소최소가"] = self._to_text(parent.get("sameAddrMinPrc"))
        out["동일주소최대가"] = self._to_text(parent.get("sameAddrMaxPrc"))
        out["등록일자"] = self._to_text(parent.get("atclCfmYmd"))
        out["방향정보"] = self._to_text(parent.get("direction"))
        out["매물확인유형코드"] = self._to_text(parent.get("vrfcTpCd"))

        out["위도"] = self._to_text(parent.get("lat"))
        out["경도"] = self._to_text(parent.get("lng"))

        self._ensure_output_keys(out)
        return out

    # Next.js / payload 파싱
    def _collect_next_f_payload_text(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            texts: List[str] = []
            for script in soup.find_all("script"):
                script_text = script.string or script.get_text()
                if not script_text:
                    continue
                if (
                        "__NEXT_DATA__" in script_text
                        or "self.__next_f.push" in script_text
                        or "__PRELOADED_STATE__" in script_text
                        or "dehydratedState" in script_text
                ):
                    texts.append(script_text)
            return "\n".join(texts) if texts else html
        except Exception:
            return html

    def _extract_dehydrated_state(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}

        for extractor in [
            self._extract_next_data_state,
            self._extract_preloaded_state,
            self._extract_dehydrated_json,
            self._extract_next_f_state_from_text,
            self._extract_first_json_object,
        ]:
            data = extractor(text)
            if data:
                return data
        return {}

    def _extract_next_data_state(self, text: str) -> Dict[str, Any]:
        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
            text,
            flags=re.S,
        )
        return self._json_load_dict(match.group(1) if match else "")

    def _extract_preloaded_state(self, text: str) -> Dict[str, Any]:
        match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*', text)
        if not match:
            return {}
        start_idx = text.find("{", match.end())
        return self._json_load_dict(self._extract_balanced_braces(text, start_idx))

    def _extract_dehydrated_json(self, text: str) -> Dict[str, Any]:
        match = re.search(r'"dehydratedState"\s*:\s*', text)
        if not match:
            return {}
        start_idx = text.find("{", match.end())
        return self._json_load_dict(self._extract_balanced_braces(text, start_idx))

    def _extract_next_f_state_from_text(self, text: str) -> Dict[str, Any]:
        if "self.__next_f.push" not in text:
            return {}
        return self._extract_next_f_state(text)

    def _extract_first_json_object(self, text: str) -> Dict[str, Any]:
        first_brace = text.find("{")
        return self._json_load_dict(self._extract_balanced_braces(text, first_brace))

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

                obj = self._json_load_any(payload)
                if obj is not None:
                    self._collect_next_f_query_info(obj, out)

        if out["queries"] or out["query_map"] or out["merged_result"]:
            return out
        return {}

    def _extract_next_f_chunks(self, text: str) -> List[str]:
        chunks: List[str] = []
        pattern = re.compile(
            r'self\.__next_f\.push\(\[\s*\d+\s*,\s*"((?:\\.|[^"\\])*)"\s*\]\)',
            flags=re.S,
        )

        for match in pattern.finditer(text):
            raw_chunk = match.group(1)
            if not raw_chunk:
                continue
            try:
                decoded = json.loads(f'"{raw_chunk}"')
            except Exception:
                try:
                    decoded = bytes(raw_chunk, "utf-8").decode("unicode_escape")
                except Exception:
                    decoded = ""
            if decoded:
                chunks.append(decoded)

        return chunks

    def _collect_next_f_query_info(self, data: Any, out: Dict[str, Any]) -> None:
        if isinstance(data, dict):
            state = data.get("state")
            queries = state.get("queries") if isinstance(state, dict) else None
            if isinstance(queries, list):
                self._append_query_infos(queries, out)
            for value in data.values():
                self._collect_next_f_query_info(value, out)
            return

        if isinstance(data, list):
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

    def _extract_balanced_braces(self, text: str, start_idx: int) -> str:
        if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
            return ""

        depth = 0
        in_str = False
        escape = False

        for idx in range(start_idx, len(text)):
            ch = text[idx]
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
                    return text[start_idx:idx + 1]

        return ""

    # 파싱 보조
    def _wait_ready_state_complete(self, timeout_sec: int = 7) -> None:
        try:
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: self._is_ready_state_complete(d)
            )
        except TimeoutException:
            self.log_signal_func("readyState complete 대기 timeout")

    def _is_ready_state_complete(self, driver: Any) -> bool:
        try:
            return driver.execute_script("return document.readyState") == "complete"
        except Exception:
            return False

    def _parse_floor_text_from_dom(self, html: str) -> str:
        try:
            text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
            for pattern in [
                r"층\s*정보[:\s]*([^\n]+)",
                r"해당층[:\s]*([^\n]+)",
                r"층수[:\s]*([^\n]+)",
                r"(\d+층\s*/\s*\d+층)",
            ]:
                match = re.search(pattern, text)
                if match:
                    return self._normalize_floor_text(match.group(1).strip())
        except Exception:
            pass
        return ""

    def _pick_floor_text(self, results_by_key: Dict[str, Any]) -> str:
        floor_value = self._first_value(
            results_by_key,
            ["floorText", "flrInfo", "floorInfo", "targetFloor", "totalFloor"],
        )
        if isinstance(floor_value, dict):
            target_floor = str(floor_value.get("targetFloor") or "").strip()
            total_floor = str(floor_value.get("totalFloor") or "").strip()
            if target_floor and total_floor:
                return self._normalize_floor_text(f"{target_floor}/{total_floor}층")
            if target_floor:
                return self._normalize_floor_text(target_floor)
            if total_floor:
                return self._normalize_floor_text(f"{total_floor}층")
        return self._normalize_floor_text(self._to_text(floor_value))

    def _pick_phone_numbers(self, results_by_key: Dict[str, Any]) -> Tuple[str, str]:
        phone_value = self._first_value(results_by_key, ["cpPc", "phone", "phoneNo", "mobile"])
        if isinstance(phone_value, dict):
            brokerage_phone = str(phone_value.get("brokerage") or phone_value.get("phone") or phone_value.get("tel") or "").strip()
            mobile_phone = str(phone_value.get("mobile") or phone_value.get("cell") or "").strip()
            return brokerage_phone, mobile_phone
        return self._to_text(phone_value), ""

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
        match = re.search(r"(\d+(?:\.\d+)?)", str(value).replace(",", ""))
        return float(match.group(1)) if match else None

    # === 신규 ===
    def _normalize_floor_text(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        text = re.sub(r"(?i)for\s*info", "", text)
        text = re.sub(r"층\s*정보", "", text)
        text = re.sub(r"해당층", "", text)
        text = re.sub(r"층수", "", text)
        text = text.replace("층", "")
        text = text.replace(" ", "")
        text = re.sub(r"/+", "/", text)
        text = re.sub(r"^[/:\-]+", "", text)
        text = re.sub(r"[/:\-]+$", "", text)
        return text.strip()

    # === 신규 ===
    def _get_selected_sort_code(self) -> str:
        sort_label = str(self.get_setting_value(self.setting, "sort") or "").strip()
        return str(self.SORT_MAP.get(sort_label) or "").strip()

    # === 신규 ===
    def _normalize_atcl_cfm_ymd(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        digits = re.sub(r"[^0-9]", "", text)
        if len(digits) == 8:
            return digits

        if len(digits) == 6:
            yy = int(digits[:2])
            year = 2000 + yy
            return f"{year:04d}{digits[2:]}"

        return ""

    # === 신규 ===
    def _is_date_in_range(self, ymd: str, fr_date: str, to_date: str) -> bool:
        if not fr_date and not to_date:
            return True

        if not ymd or len(ymd) != 8 or not ymd.isdigit():
            return False

        if fr_date and ymd < fr_date:
            return False
        if to_date and ymd > to_date:
            return False
        return True

    # === 신규 ===
    def _apply_same_addr_price_range(self, item: Dict[str, Any]) -> None:
        try:
            same_addr_cnt = int(str(item.get("sameAddrCnt") or "0").strip())
        except Exception:
            same_addr_cnt = 0

        if same_addr_cnt <= 1:
            item["sameAddrMinPrc"] = ""
            item["sameAddrMaxPrc"] = ""
            return

        if str(item.get("sameAddrMinPrc") or "").strip() or str(item.get("sameAddrMaxPrc") or "").strip():
            return

        if not self.api_client:
            return

        params: Dict[str, Any] = {"atclNo": str(item.get("atclNo") or item.get("articleNo") or "").strip()}
        cortar_no = self._pick_cortar_no(item)
        if cortar_no:
            params["cortarNo"] = cortar_no
        if self.search_trade_codes:
            params["tradTpCd"] = self._join_codes(self.search_trade_codes)
        if self.search_rlet_codes:
            params["rletTpCd"] = self._join_codes(self.search_rlet_codes)

        if not params.get("atclNo"):
            return

        res = self.api_client.get(
            url=self.same_addr_article_url,
            headers=self.headers,
            params=params,
        )
        items = self._extract_article_items(res)
        if not items:
            return

        item["sameAddrMinPrc"], item["sameAddrMaxPrc"] = self._extract_same_addr_price_range(items)

    # === 신규 ===
    def _extract_same_addr_price_range(self, items: List[Dict[str, Any]]) -> Tuple[str, str]:
        prices: List[int] = []

        for item in items or []:
            raw_price = self._extract_same_addr_base_price(item)
            digits = re.sub(r"[^0-9]", "", str(raw_price or ""))
            if digits:
                prices.append(int(digits))

        if len(prices) <= 1:
            return "", ""

        return self._format_price_value(min(prices)), self._format_price_value(max(prices))

    # === 신규 ===
    def _extract_same_addr_base_price(self, item: Dict[str, Any]) -> str:
        trad_tp = str(item.get("tradTpCd") or item.get("tradeTypeCode") or "").strip()

        if trad_tp == "A1":
            return str(item.get("price") or item.get("dealOrWarrantPrc") or item.get("prcInfo") or "").strip()

        if trad_tp == "B1":
            return str(item.get("warrantyAmount") or item.get("dealOrWarrantPrc") or item.get("price") or "").strip()

        if trad_tp == "B2":
            return str(item.get("warrantyAmount") or item.get("dealOrWarrantPrc") or item.get("price") or "").strip()

        return str(
            item.get("warrantyAmount")
            or item.get("dealOrWarrantPrc")
            or item.get("price")
            or item.get("prcInfo")
            or ""
        ).strip()

    # === 신규 ===
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
            "Jibun",
            "atclFetrDesc",
            "tagList",
            "rltrNm",
            "phone",
            "direction",
            "ipjuday",
            "keyword",
            "atcURL",
            "id",
            "search_requirement",
            "atclCfmYmd",
            "rletTpNm",
            "ArticlePriceInfo",
            "supply_space_name",
            "bildNm",
            "sameAddrMinPrc",
            "sameAddrMaxPrc",
            "sameAddrCnt",
            "vrfcTpCd",
            "rank",
            "lat",
            "lng",
        ]

    # === 신규 ===
    def _format_price_value(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        digits = re.sub(r"[^0-9]", "", text)
        if not digits:
            return text

        try:
            number = int(digits)
            number = number // 10000
            return f"{number:,}"
        except Exception:
            return text

    # === 신규 ===
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

    # === 신규 ===
    def _build_search_requirement_text(self, out: Dict[str, Any]) -> str:
        parts: List[str] = []

        search_addr = str(out.get("검색 주소") or "").strip()
        search_rlet = str(out.get("검색 매물유형") or "").strip()
        search_trade = str(out.get("검색 거래유형") or "").strip()

        if search_addr:
            parts.append(search_addr)
        if search_rlet:
            parts.append(f"매물유형:{search_rlet}")
        if search_trade:
            parts.append(f"거래유형:{search_trade}")

        return " / ".join(parts)

    # === 신규 ===
    def _map_out_to_eng(self, out: Dict[str, Any]) -> Dict[str, Any]:
        eng_out: Dict[str, Any] = {
            "date": str(out.get("매물확인일") or ""),
            "atclNo": str(out.get("게시번호") or ""),
            "atclNm": str(out.get("상위매물명") or ""),
            "tradTpNm": str(out.get("거래유형") or ""),
            "hanPrc": str(out.get("매매가") or out.get("보증금") or ""),
            "rentPrc": str(out.get("월세") or ""),
            "ho": "",
            "flrInfo": str(out.get("층정보") or ""),
            "spc1": str(out.get("공급면적") or ""),
            "spc2": str(out.get("전용면적") or ""),
            "Jibun": str(out.get("번지") or ""),
            "atclFetrDesc": str(out.get("매물특징") or ""),
            "tagList": str(out.get("매물태그") or ""),
            "rltrNm": str(out.get("중개사무소이름") or ""),
            "phone": str(out.get("중개사무소번호") or out.get("중개사핸드폰번호") or ""),
            "direction": str(out.get("방향정보") or ""),
            "ipjuday": str(out.get("매물확인일") or ""),
            "keyword": str(out.get("검색 주소") or ""),
            "atcURL": str(out.get("URL") or ""),
            "id": "",
            "search_requirement": self._build_search_requirement_text(out),
            "atclCfmYmd": str(out.get("등록일자") or ""),
            "rletTpNm": str(out.get("매물유형") or ""),
            "ArticlePriceInfo": self._build_article_price_info(out),
            "supply_space_name": str(out.get("평수") or ""),
            "bildNm": str(out.get("동이름") or out.get("상위매물동") or ""),
            "sameAddrMinPrc": str(out.get("동일주소최소가") or ""),
            "sameAddrMaxPrc": str(out.get("동일주소최대가") or ""),
            "sameAddrCnt": str(out.get("동일주소매물수") or ""),
            "vrfcTpCd": str(out["매물확인유형코드"] or ""),
            "rank": "",
            "lat": str(out.get("위도") or ""),
            "lng": str(out.get("경도") or ""),
        }

        for col in self._get_eng_columns():
            eng_out.setdefault(col, "")

        return eng_out

    # 설정 / URL / 공통 유틸
    def _ensure_output_keys(self, out: Dict[str, Any]) -> None:
        for col in self.columns:
            out.setdefault(col, "")

    # 세팅
    def _resolve_search_filters(self) -> None:
        self.search_trade_codes = []
        self.search_trade_labels = []
        self.search_rlet_codes = []
        self.search_rlet_labels = []

        for item in self.setting_detail or []:
            if item.get("row_type") != "item" or not item.get("checked"):
                continue

            item_type = str(item.get("type") or "").strip()
            code = str(item.get("code") or "").strip()
            label = str(item.get("value") or "").strip()

            if item_type == "trade_types" and code in self.TRADE_TYPE_MAP:
                self._append_unique(self.search_trade_codes, code)
                self._append_unique(self.search_trade_labels, label or self.TRADE_TYPE_MAP[code])

            if item_type == "rlet_types" and code in self.RLET_TYPE_MAP:
                self._append_unique(self.search_rlet_codes, code)
                self._append_unique(self.search_rlet_labels, label or self.RLET_TYPE_MAP[code])

    def _build_filter_log_text(self) -> str:
        trade_text = self._format_code_label_pairs(self.search_trade_codes, self.TRADE_TYPE_MAP)
        rlet_text = self._format_code_label_pairs(self.search_rlet_codes, self.RLET_TYPE_MAP)
        return f"검색 필터 설정 - 거래유형: {trade_text or '원본 유지'}, 매물유형: {rlet_text or '원본 유지'}"

    def _format_code_label_pairs(self, codes: List[str], code_map: Dict[str, str]) -> str:
        parts: List[str] = []
        for code in codes:
            label = code_map.get(code, code)
            parts.append(f"{label}({code})")
        return ", ".join(parts)

    def _normalize_search_config(self, raw_value: Any, code_map: Dict[str, str]) -> Tuple[List[str], List[str]]:
        if raw_value is None:
            return [], []

        values: List[str] = []
        if isinstance(raw_value, list):
            values = [str(v).strip() for v in raw_value if str(v).strip()]
        else:
            text = str(raw_value).strip()
            if text:
                values = [v.strip() for v in re.split(r"[,|:/]+", text) if v.strip()]

        reverse_map = {value: key for key, value in code_map.items()}
        codes: List[str] = []
        labels: List[str] = []

        for item in values:
            if item in code_map:
                self._append_unique(codes, item)
                self._append_unique(labels, code_map[item])
                continue
            if item in reverse_map:
                self._append_unique(codes, reverse_map[item])
                self._append_unique(labels, item)

        return codes, labels

    def _apply_url_filters(self, url: str) -> str:
        replace_params: Dict[str, Any] = {}
        if self.search_trade_codes:
            replace_params["tradTpCd"] = self._join_codes(self.search_trade_codes)
        if self.search_rlet_codes:
            replace_params["rletTpCd"] = self._join_codes(self.search_rlet_codes)

        sort_code = self._get_selected_sort_code()
        if sort_code:
            replace_params["sort"] = sort_code

        if not replace_params:
            return url
        return self._replace_query_params(url, **replace_params)

    def _replace_query_params(self, url: str, **replace_values: Any) -> str:
        parsed = urlparse(url)
        query_map = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in replace_values.items():
            if value is None:
                continue
            query_map[key] = str(value)

        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_map, doseq=True),
            parsed.fragment,
        ))

    def _join_codes(self, values: List[str]) -> str:
        return ":".join([value for value in values if value])

    def _pick_cortar_no(self, article: Dict[str, Any]) -> str:
        value = str(article.get("cortarNo") or article.get("cortar_no") or "").strip()
        if value:
            return value

        for key in ["articleList", "clusterList_url"]:
            url = str(article.get(key) or "").strip()
            if not url:
                continue
            query = parse_qs(urlparse(url).query)
            values = query.get("cortarNo") or query.get("cortar_no") or []
            if values and str(values[0]).strip():
                return str(values[0]).strip()

        return ""

    def _get_query_value(self, url: str, key: str) -> str:
        query = parse_qs(urlparse(url).query)
        values = query.get(key) or []
        return str(values[0]).strip() if values else ""

    def _extract_article_items(self, res: Any) -> List[Dict[str, Any]]:
        if isinstance(res, str):
            res = self._json_load_any(res)

        if isinstance(res, list):
            return [item for item in res if isinstance(item, dict)]

        if not isinstance(res, dict):
            return []

        for candidate in [
            res.get("body"),
            res.get("result"),
            res.get("articleList"),
            res.get("list"),
            res.get("items"),
        ]:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
            if isinstance(candidate, dict):
                for key in ["list", "items", "articleList"]:
                    nested = candidate.get(key)
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]

        return []

    def _build_parts_text(self, article: Dict[str, Any]) -> str:
        return " ".join([
            value for value in [
                str(article.get("시도") or "").strip(),
                str(article.get("시군구") or "").strip(),
                str(article.get("읍면동") or "").strip(),
            ] if value
        ])

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
                "roadName", "roadAddress", "jibunAddress",
            ]:
                inner = value.get(key)
                if inner not in [None, "", [], {}]:
                    return self._to_text(inner)
            parts = [self._to_text(v) for v in value.values()]
            return " / ".join([part for part in parts if part])

        if isinstance(value, list):
            parts = [self._to_text(item) for item in value]
            unique_parts: List[str] = []
            for part in parts:
                if part and part not in unique_parts:
                    unique_parts.append(part)
            return ", ".join(unique_parts)

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

            merged_result = data.get("merged_result")
            if isinstance(merged_result, dict):
                found = self._deep_find_first(merged_result, target_key)
                if found not in [None, "", [], {}]:
                    return found

            query_map = data.get("query_map")
            if isinstance(query_map, dict):
                for value in query_map.values():
                    found = self._deep_find_first(value, target_key)
                    if found not in [None, "", [], {}]:
                        return found

            for value in data.values():
                found = self._deep_find_first(value, target_key)
                if found not in [None, "", [], {}]:
                    return found
            return None

        if isinstance(data, list):
            for item in data:
                found = self._deep_find_first(item, target_key)
                if found not in [None, "", [], {}]:
                    return found

        return None

    def _flush_result_data(self) -> None:
        if not self.result_data_list:
            return

        save_list: List[Dict[str, Any]] = self.result_data_list

        # === 신규 === eng=True면 영문 컬럼 매핑 후 저장
        if self.eng:
            save_list = [self._map_out_to_eng(row) for row in save_list]

        if save_list:
            self.excel_driver.append_to_csv(
                self.csv_filename,
                save_list,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

        self.result_data_list = []

    def _append_unique(self, target: List[str], value: str) -> None:
        if value and value not in target:
            target.append(value)

    def _json_load_any(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _json_load_dict(self, text: str) -> Dict[str, Any]:
        data = self._json_load_any(text)
        return data if isinstance(data, dict) else {}