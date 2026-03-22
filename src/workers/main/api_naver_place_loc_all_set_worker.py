import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.str_utils import split_comma_keywords
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverPlaceLocAllSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.out_dir = "output_naver_place_loc_all"
        self.folder_path = ""
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.keyword_list: Optional[List[str]] = None
        self.site_name: str = "네이버 플레이스 전국"
        self.total_cnt: int = 0
        self.total_pages: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.saved_ids: Set[str] = set()
        self._destroyed: bool = False
        self._cleaned_up: bool = False

    # 런타임 상태 초기화
    def _reset_runtime_state(self) -> None:
        self.total_cnt = 0
        self.total_pages = 0
        self.current_cnt = 0
        self.before_pro_value = 0.0
        self.saved_ids.clear()
        self.csv_filename = None
        self._destroyed = False

    # 초기화
    def init(self) -> bool:
        self._reset_runtime_state()

        keyword_str: str = self.get_setting_value(self.setting, "keyword")
        self.keyword_list = split_comma_keywords(keyword_str)
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        self.log_signal_func("크롤링 사이트 인증에 성공하였습니다.")
        self.log_signal_func("전체 수 계산을 시작합니다. 잠시만 기다려주세요.")

        if self.file_driver is None:
            self.log_signal_func("파일 드라이버가 초기화되지 않았습니다.")
            return False

        self.csv_filename = self.get_csv_filename()

        self.excel_driver.init_csv(
            filename=self.csv_filename,
            columns=self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )

        if self.region:
            self.loc_all_keyword_list()
        else:
            self.only_keywords_keyword_list()

        return True

    def safe_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "").strip())
        return (name or "output")[:120]

    def now_stamp(self) -> str:
        return time.strftime("%Y%m%d_%H%M%S")

    def get_csv_filename(self) -> str:
        return f"{self.safe_filename(self.site_name)}_{self.now_stamp()}.csv"


    # 전국 키워드 조회
    def loc_all_keyword_list(self) -> None:
        if not self.region or not self.keyword_list:
            self.log_signal_func("지역 또는 키워드 정보가 없습니다.")
            return

        loc_all_len: int = len(self.region)
        keyword_list_len: int = len(self.keyword_list)
        self.total_cnt = loc_all_len * keyword_list_len * 300
        self.total_pages = loc_all_len * keyword_list_len * 15

        self.log_signal_func(f"예상 전체 수 {self.total_cnt} 개")
        self.log_signal_func(f"예상 전체 페이지수 {self.total_pages} 개")

        for index, loc in enumerate(self.region, start=1):
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            name = f'{loc["시도"]} {loc["시군구"]} {loc["읍면동"]} '

            for idx, query_keyword in enumerate(self.keyword_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                full_name = name + query_keyword
                self.log_signal_func(
                    f"전국: {index} / {loc_all_len}, 키워드: {idx} / {keyword_list_len}, 검색어: {full_name}"
                )
                self.loc_all_keyword_list_detail(
                    full_name,
                    keyword_list_len,
                    idx,
                    loc_all_len,
                    index,
                    loc,
                    query_keyword
                )

    # 전국 상세
    def loc_all_keyword_list_detail(
            self,
            query: str,
            total_queries: int,
            current_query_index: int,
            total_locs: int,
            locs_index: int,
            loc: Dict[str, str],
            query_keyword: str
    ) -> None:
        try:
            page: int = 1
            result_ids: List[str] = []

            while True:
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                time.sleep(random.uniform(1, 2))

                result = self.fetch_search_results(query, page)
                if not result:
                    break

                result_ids.extend(result)
                self.log_signal_func(
                    f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, 검색어: {query}, 페이지: {page}"
                )
                self.log_signal_func(f"목록: {result}")
                page += 1

            new_ids: List[str] = list(dict.fromkeys(result_ids))
            results: List[Dict[str, Any]] = []

            for idx, place_id in enumerate(new_ids, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                if place_id in self.saved_ids:
                    self.log_signal_func(
                        f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, "
                        f"검색어: {query}, 수집: {idx} / {len(new_ids)}, 중복 아이디: {place_id}"
                    )
                    continue

                time.sleep(random.uniform(2, 4))

                place_info = self.fetch_place_info(place_id, loc, query_keyword, query)
                if not place_info:
                    self.log_signal_func(f"⚠️ ID {place_id}의 상세 정보를 가져오지 못했습니다.")
                    continue

                self.log_signal_func(
                    f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, "
                    f"검색어: {query}, 수집: {idx} / {len(new_ids)}, 아이디: {place_id}, 이름: {place_info['이름']}"
                )
                results.append(place_info)

            self.saved_ids.update(new_ids)

            self.excel_driver.append_to_csv(
                filename=self.csv_filename,
                data_list=results,
                columns=self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.current_cnt = locs_index * current_query_index * 300
            pro_value = (self.current_cnt / self.total_cnt) * 1000000 if self.total_cnt > 0 else 0
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

        except Exception as e:
            self.log_signal_func(f"loc_all_keyword_list_detail 크롤링 에러: {e}")

    # 키워드만 조회
    def only_keywords_keyword_list(self) -> None:
        result_list: List[Any] = []
        all_ids_list = self.total_cnt_cal()

        if not all_ids_list:
            self.log_signal_func("수집할 ID가 없습니다.")
            return

        self.log_signal_func(f"전체 항목 수 {self.total_cnt} 개")
        self.log_signal_func(f"전체 페이지 수 {self.total_pages} 개")

        for index, place_id in enumerate(all_ids_list, start=1):
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            loc: Dict[str, str] = {
                "시도": "",
                "시군구": "",
                "읍면동": "",
            }

            obj = self.fetch_place_info(place_id, loc, "", "")
            if obj:
                result_list.append(obj)

            if index % 5 == 0:
                self.excel_driver.append_to_csv(
                    filename=self.csv_filename,
                    data_list=result_list,
                    columns=self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )

            self.current_cnt = self.current_cnt + 1
            pro_value = (self.current_cnt / self.total_cnt) * 1000000 if self.total_cnt > 0 else 0
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

            self.log_signal_func(f"현재 페이지 {self.current_cnt}/{self.total_cnt} : {obj}")
            time.sleep(random.uniform(1, 2))

        if result_list:
            self.excel_driver.append_to_csv(
                filename=self.csv_filename,
                data_list=result_list,
                columns=self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )


    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)


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

        self.api_client = None
        self.file_driver = None
        self.excel_driver = None
        self.csv_filename = None
        self._cleaned_up = True

    # 마무리
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()


    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 전체 갯수 조회
    def total_cnt_cal(self) -> Optional[List[str]]:
        try:
            if not self.keyword_list:
                self.log_signal_func("키워드 정보가 없습니다.")
                return []

            page_all: int = 0
            result_ids: List[str] = []

            for index, keyword in enumerate(self.keyword_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                page: int = 1
                while True:
                    if not self.running:
                        self.log_signal_func("크롤링이 중지되었습니다.")
                        break

                    time.sleep(random.uniform(1, 2))
                    self.log_signal_func(f"전체 {index}/{len(self.keyword_list)}, keyword: {keyword}, page: {page}")

                    result = self.fetch_search_results(keyword, page)
                    if not result:
                        break

                    result_ids.extend(result)
                    page += 1
                    page_all += 1

            all_ids_list: List[str] = list(dict.fromkeys(result_ids))
            self.log_signal_func(f"전체 : {all_ids_list}")
            self.total_cnt = len(all_ids_list)
            self.total_pages = page_all
            return all_ids_list

        except Exception as e:
            self.log_signal_func(f"Error calculating total count: {e}")
            return None

    # 플레이스 목록
    def fetch_search_results(self, keyword: str, page: int) -> List[str]:
        url = "https://pcmap-api.place.naver.com/graphql"

        headers: Dict[str, str] = {
            "method": "POST",
            "accept-language": "ko",
            "content-type": "application/json",
            "referer": "https://pcmap.place.naver.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        }

        payload: List[Dict[str, Any]] = [{
            "operationName": "getPlacesList",
            "variables": {
                "useReverseGeocode": True,
                "input": {
                    "query": keyword,
                    "start": (page - 1) * 100 + 1,
                    "display": 100,
                    "adult": True,
                    "spq": True,
                    "queryRank": "",
                    "x": "",
                    "y": "",
                    "clientX": "",
                    "clientY": "",
                    "deviceType": "pcmap",
                    "bounds": ""
                },
                "isNmap": True,
                "isBounds": True,
                "reverseGeocodingInput": {
                    "x": "",
                    "y": ""
                }
            },
            "query": "query getPlacesList($input: PlacesInput, $isNmap: Boolean!, $isBounds: Boolean!, $reverseGeocodingInput: ReverseGeocodingInput, $useReverseGeocode: Boolean = false) {  businesses: places(input: $input) {    total    items {      id      name      normalizedName      category      cid      detailCid {        c0        c1        c2        c3        __typename      }      categoryCodeList      dbType      distance      roadAddress      address      fullAddress      commonAddress      bookingUrl      phone      virtualPhone      businessHours      daysOff      imageUrl      imageCount      x      y      poiInfo {        polyline {          shapeKey {            id            name            version            __typename          }          boundary {            minX            minY            maxX            maxY            __typename          }          details {            totalDistance            arrivalAddress            departureAddress            __typename          }          __typename        }        polygon {          shapeKey {            id            name            version            __typename          }          boundary {            minX            minY            maxX            maxY            __typename          }          __typename        }        __typename      }      subwayId      markerId @include(if: $isNmap)      markerLabel @include(if: $isNmap) {        text        style        stylePreset        __typename      }      imageMarker @include(if: $isNmap) {        marker        markerSelected        __typename      }      oilPrice @include(if: $isNmap) {        gasoline        diesel        lpg        __typename      }      isPublicGas      isDelivery      isTableOrder      isPreOrder      isTakeOut      isCvsDelivery      hasBooking      naverBookingCategory      bookingDisplayName      bookingBusinessId      bookingVisitId      bookingPickupId      baemin {        businessHours {          deliveryTime {            start            end            __typename          }          closeDate {            start            end            __typename          }          temporaryCloseDate {            start            end            __typename          }          __typename        }        __typename      }      yogiyo {        businessHours {          actualDeliveryTime {            start            end            __typename          }          bizHours {            start            end            __typename          }          __typename        }        __typename      }      isPollingStation      hasNPay      talktalkUrl      visitorReviewCount      visitorReviewScore      blogCafeReviewCount      bookingReviewCount      streetPanorama {        id        pan        tilt        lat        lon        __typename      }      naverBookingHubId      bookingHubUrl      bookingHubButtonName      newOpening      newBusinessHours {        status        description        dayOff        dayOffDescription        __typename      }      coupon {        total        promotions {          promotionSeq          couponSeq          conditionType          image {            url            __typename          }          title          description          type          couponUseType          __typename        }        __typename      }      mid      hasMobilePhoneNumber      hiking {        distance        startName        endName        __typename      }      __typename    }    optionsForMap @include(if: $isBounds) {      ...OptionsForMap      displayCorrectAnswer      correctAnswerPlaceId      __typename    }    searchGuide {      queryResults {        regions {          displayTitle          query          region {            rcode            __typename          }          __typename        }        isBusinessName        __typename      }      queryIndex      types      __typename    }    queryString    siteSort    __typename  }  reverseGeocodingAddr(input: $reverseGeocodingInput) @include(if: $useReverseGeocode) {    ...ReverseGeocodingAddr    __typename  }}fragment OptionsForMap on OptionsForMap {  maxZoom  minZoom  includeMyLocation  maxIncludePoiCount  center  spotId  keepMapBounds  __typename}fragment ReverseGeocodingAddr on ReverseGeocodingResult {  rcode  region  __typename}"
        }]

        try:
            if self.api_client is None:
                self.log_signal_func("[에러] api_client 가 초기화되지 않았습니다.")
                return []

            res = self.api_client.post(url=url, headers=headers, json=payload)
            if not isinstance(res, list) or not res or not isinstance(res[0], dict):
                return []

            items = res[0].get("data", {}).get("businesses", {}).get("items", [])
            if not isinstance(items, list):
                return []

            return [item.get("id") for item in items if isinstance(item, dict) and item.get("id")]

        except Exception as e:
            self.log_signal_func(f"[에러] fetch_search_results 실패: {e}")
            return []

    # 숫자 체크
    def clean_number(self, value: Any) -> Any:
        try:
            num = float(value)
            return "" if num == 0 else num
        except (ValueError, TypeError):
            return ""

    # placeDetail ROOT_QUERY key 유연하게 찾기
    def _find_place_detail_key(self, root_query: Dict[str, Any], place_id: str) -> str:
        if not isinstance(root_query, dict):
            return ""

        candidates = [
            f'placeDetail({{"input":{{"deviceType":"pc","id":"{place_id}","isNx":false}}}})',
            f'placeDetail({{"input":{{"checkRedirect":true,"deviceType":"pc","id":"{place_id}","isNx":false}}}})',
            f'placeDetail({{"input":{{"deviceType":"mobile","id":"{place_id}","isNx":false}}}})',
            f'placeDetail({{"input":{{"checkRedirect":true,"deviceType":"mobile","id":"{place_id}","isNx":false}}}})',
        ]

        for k in candidates:
            if k in root_query:
                return k

        needle = f'"id":"{place_id}"'
        for k in root_query.keys():
            if isinstance(k, str) and k.startswith("placeDetail(") and needle in k:
                return k

        return ""

    # placeDetail 객체에서 bookingBusinessId 추출
    def _extract_booking_business_id(self, place_detail_obj: Dict[str, Any]) -> str:
        if not isinstance(place_detail_obj, dict):
            return ""

        v = place_detail_obj.get('naverBooking({"bookingType":"accommodation"})')
        if isinstance(v, dict) and v.get("bookingBusinessId"):
            return str(v.get("bookingBusinessId"))

        for k, vv in place_detail_obj.items():
            if not isinstance(k, str):
                continue
            if k.startswith("naverBooking(") and isinstance(vv, dict):
                bid = vv.get("bookingBusinessId")
                if bid:
                    return str(bid)

        return ""

    def fetch_booking_agency_info(self, booking_business_id: str) -> Dict[str, str]:
        try:
            if not booking_business_id:
                return {}

            if self.api_client is None:
                self.log_signal_func("[에러] api_client 가 초기화되지 않았습니다.")
                return {}

            url = f"https://booking.naver.com/booking/3/bizes/{booking_business_id}"
            headers: Dict[str, str] = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                "referer": "https://booking.naver.com/",
            }

            html = self.api_client.get(url=url, headers=headers)
            if not html:
                return {}

            soup = BeautifulSoup(html, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"window\.__APOLLO_STATE__"))
            if not script_tag or not script_tag.string:
                return {}

            text = script_tag.string
            m = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.*\})\s*;?', text, flags=re.S)
            if not m:
                return {}

            raw_json = m.group(1).strip()

            try:
                data = json.loads(raw_json)
            except Exception as e:
                self.log_signal_func(f"⚠️ booking JSON decode 실패: {e}")
                return {}

            business_key = f"Business:{booking_business_id}"
            biz = data.get(business_key, {})
            if not isinstance(biz, dict):
                return {}

            agencies = biz.get("agencies") or []
            if not isinstance(agencies, list) or not agencies:
                return {}

            ag0 = agencies[0] or {}
            if not isinstance(ag0, dict):
                return {}

            return {
                "대행사 상호": ag0.get("name", "") or "",
                "대행사 대표자명": ag0.get("reprName", "") or "",
                "대행사 소재지": ag0.get("address", "") or "",
                "대행사 사업자번호": ag0.get("bizNumber", "") or "",
                "대행사 통신판매업번호": ag0.get("cbizNumber", "") or "",
                "대행사 연락처": ag0.get("phone", "") or "",
                "대행사 홈페이지": ag0.get("websiteUrl", "") or "",
            }

        except Exception as e:
            self.log_signal_func(f"[에러] fetch_booking_agency_info 실패: {e}")
            return {}

    # 상세조회
    def fetch_place_info(
            self,
            place_id: str,
            loc: Dict[str, str],
            query_keyword: str,
            query: str
    ) -> Optional[Dict[str, Any]]:
        try:
            if self.api_client is None:
                self.log_signal_func("[에러] api_client 가 초기화되지 않았습니다.")
                return None

            url = f"https://m.place.naver.com/place/{place_id}"
            headers: Dict[str, str] = {
                "authority": "m.place.naver.com",
                "method": "GET",
                "scheme": "https",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "priority": "u=0, i",
                "sec-ch-ua": '"Not/A)Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "referer": f"https://m.place.naver.com/place/{place_id}",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            }

            response = self.api_client.get(url=url, headers=headers)

            if not response:
                self.log_signal_func(f"⚠️ Place ID {place_id} 응답 없음.")
                return None

            soup = BeautifulSoup(response, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"window\.__APOLLO_STATE__"))
            if not script_tag or not script_tag.string:
                self.log_signal_func(f"⚠️ Place ID {place_id}의 스크립트 태그 없음 또는 비어 있음.")
                return None

            script_text = script_tag.string

            marker = "window.__APOLLO_STATE__"
            marker_index = script_text.find(marker)
            if marker_index < 0:
                self.log_signal_func(f"⚠️ Place ID {place_id} APOLLO_STATE marker 없음.")
                return None

            equal_index = script_text.find("=", marker_index)
            if equal_index < 0:
                self.log_signal_func(f"⚠️ Place ID {place_id} APOLLO_STATE = 없음.")
                return None

            json_start = script_text.find("{", equal_index)
            if json_start < 0:
                self.log_signal_func(f"⚠️ Place ID {place_id} APOLLO_STATE JSON 시작 없음.")
                return None

            try:
                data, _ = json.JSONDecoder().raw_decode(script_text[json_start:])
            except Exception as e:
                self.log_signal_func(f"⚠️ Place ID {place_id} JSON decode 실패: {e}")
                return None

            if not isinstance(data, dict):
                self.log_signal_func(f"⚠️ Place ID {place_id} data가 dict가 아님: {type(data)}")
                return None

            base = data.get(f"PlaceDetailBase:{place_id}", {})
            name = base.get("name", "")
            road = base.get("road", "")
            address = base.get("address", "")
            roadAddress = base.get("roadAddress", "")
            category = base.get("category", "")
            conveniences = base.get("conveniences", [])
            phone = base.get("phone", "")
            virtualPhone = base.get("virtualPhone", "")

            review_stats = data.get(f"VisitorReviewStatsResult:{place_id}", {})
            review = review_stats.get("review", {}) or {}
            analysis = review_stats.get("analysis", {}) or {}

            visitorReviewsScore = self.clean_number(review.get("avgRating", ""))
            visitorReviewsTotal = self.clean_number(review.get("totalCount", ""))
            voted_keyword = analysis.get("votedKeyword") or {}
            fsasReviewsTotal = self.clean_number(voted_keyword.get("userCount", ""))

            root_query = data.get("ROOT_QUERY", {})
            place_detail_key = self._find_place_detail_key(root_query, place_id)
            if not place_detail_key:
                self.log_signal_func(f"⚠️ Place ID {place_id} placeDetail key를 찾지 못했습니다.")
                return None

            place_detail_obj = root_query.get(place_detail_key, {}) or {}

            business_hours = place_detail_obj.get(
                'businessHours({"source":["tpirates","shopWindow"]})', []
            )
            if not business_hours:
                business_hours = place_detail_obj.get(
                    'businessHours({"source":["tpirates","jto","shopWindow"]})', []
                )

            new_business_hours_json = place_detail_obj.get("newBusinessHours", [])
            if not new_business_hours_json:
                new_business_hours_json = place_detail_obj.get(
                    'newBusinessHours({"format":"restaurant"})',
                    []
                )

            urls: List[str] = []
            homepages = place_detail_obj.get("shopWindow", {}).get("homepages", "")
            if homepages:
                for item in homepages.get("etc", []):
                    urls.append(item.get("url", ""))

                repr_data = homepages.get("repr")
                if repr_data:
                    repr_url = repr_data.get("url", "")
                    if repr_url:
                        urls.append(repr_url)

            category_list = category.split(",") if category else ["", ""]
            main_category = category_list[0] if len(category_list) > 0 else ""
            sub_category = category_list[1] if len(category_list) > 1 else ""

            zipCode = ""
            if self.columns and "우편번호" in self.columns:
                zipCode = self.fetch_zipcode_by_addr(address, roadAddress)

            result: Dict[str, Any] = {
                "아이디": place_id,
                "이름": name,
                "주소(지번)": address,
                "주소(도로명)": roadAddress,
                "우편번호": zipCode,
                "대분류": main_category,
                "소분류": sub_category,
                "별점": visitorReviewsScore,
                "방문자리뷰수": visitorReviewsTotal,
                "블로그리뷰수": fsasReviewsTotal,
                "이용시간1": self.format_new_business_hours(new_business_hours_json),
                "이용시간2": self.format_business_hours(business_hours),
                "카테고리": category,
                "URL": f"https://m.place.naver.com/place/{place_id}/home",
                "지도": f"https://map.naver.com/p/entry/place/{place_id}",
                "편의시설": ", ".join(conveniences) if conveniences else "",
                "가상번호": virtualPhone,
                "전화번호": phone,
                "사이트": urls,
                "주소지정보": road,
                "시도(검색)": loc.get("시도", ""),
                "시군구(검색)": loc.get("시군구", ""),
                "읍면동(검색)": loc.get("읍면동", ""),
                "키워드(검색)": query_keyword,
                "전체 검색어": query
            }

            AGENCY_COLS = [
                "대행사 상호",
                "대행사 대표자명",
                "대행사 소재지",
                "대행사 사업자번호",
                "대행사 통신판매업번호",
                "대행사 연락처",
                "대행사 홈페이지",
            ]

            want_agency = any(col in (self.columns or []) for col in AGENCY_COLS)

            if want_agency:
                booking_business_id = self._extract_booking_business_id(place_detail_obj)
                if booking_business_id:
                    time.sleep(random.uniform(2, 4))
                    agency_info = self.fetch_booking_agency_info(booking_business_id)

                    if isinstance(agency_info, dict):
                        for col in AGENCY_COLS:
                            if self.columns and col in self.columns:
                                result[col] = agency_info.get(col, "")

            return result

        except requests.exceptions.RequestException as e:
            self.log_signal_func(f"❌ 네트워크 에러: Place ID {place_id}: {e}")
        except Exception as e:
            self.log_signal_func(f"❌ 처리 중 에러: Place ID {place_id}: {e}")

        return None

    def fetch_zipcode_by_addr(self, addr_jibun: str, addr_road: str) -> str:
        """
        1) 지번 주소로 조회
        2) 실패 시 도로명 주소로 조회
        - 네이버 event HTML 파싱
        - 우편번호는 문자열로만 처리
        - 4자리면 앞에 0 붙여 5자리로 복원
        - 6자리는 구우편번호로 판단 → 무시
        """
        try:
            if self.api_client is None:
                self.log_signal_func("[에러] api_client 가 초기화되지 않았습니다.")
                return ""

            url = "https://event.naver.com/personalInfo/zipCode"
            headers: Dict[str, str] = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "cache-control": "max-age=0",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://event.naver.com",
                "referer": "https://event.naver.com/personalInfo/zipCode",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            }

            def extract_zip(html: str) -> str:
                soup = BeautifulSoup(html, "html.parser")

                for li in soup.select("div.line ul li"):
                    p = li.find("p")
                    if p:
                        text = p.get_text(" ", strip=True)
                        m = re.search(r"\b(\d{4,6})\b", text)
                        if m:
                            z = m.group(1)
                            if len(z) == 4:
                                return "0" + z
                            if len(z) == 5:
                                return z

                    a = li.select_one("a.copy[roadZipCode]")
                    if a:
                        z = (a.get("roadZipCode") or "").strip()
                        if z.isdigit():
                            if len(z) == 4:
                                return "0" + z
                            if len(z) == 5:
                                return z

                return ""

            def try_one(keyword: str) -> str:
                if not keyword:
                    return ""

                kw = str(keyword).strip()
                if not kw:
                    return ""

                html = self.api_client.post(url=url, headers=headers, data={"keyword": kw})
                if not html or not isinstance(html, str):
                    return ""

                return extract_zip(html)

            zc = try_one(addr_jibun)
            if zc:
                return zc

            return try_one(addr_road)

        except Exception as e:
            self.log_signal_func(f"우편번호 조회 실패: {e}")
            return ""

    # 영업시간 함수1
    def format_business_hours(self, business_hours: List[Dict[str, Any]]) -> str:
        formatted_hours: List[str] = []
        try:
            if business_hours:
                for hour in business_hours:
                    day = hour.get("day", "") or ""
                    start_time = hour.get("startTime", "") or ""
                    end_time = hour.get("endTime", "") or ""
                    if day and start_time and end_time:
                        formatted_hours.append(f"{day} {start_time} - {end_time}")
        except Exception as e:
            self.log_signal_func(f"Unexpected error: {e}")
            return ""

        return "\n".join(formatted_hours).strip() if formatted_hours else ""

    # 영업시간 함수2
    def format_new_business_hours(self, new_business_hours: List[Dict[str, Any]]) -> str:
        formatted_hours: List[str] = []
        try:
            if new_business_hours:
                for item in new_business_hours:
                    status_description = item.get("businessStatusDescription", {}) or {}
                    status = status_description.get("status", "") or ""
                    description = status_description.get("description", "") or ""

                    if status:
                        formatted_hours.append(status)
                    if description:
                        formatted_hours.append(description)

                    for info in item.get("businessHours", []) or []:
                        day = info.get("day", "") or ""
                        business_hours = info.get("businessHours", {}) or {}
                        start_time = business_hours.get("start", "") or ""
                        end_time = business_hours.get("end", "") or ""

                        break_hours = info.get("breakHours", []) or []
                        break_times = [
                            f"{bh.get('start', '') or ''} - {bh.get('end', '') or ''}"
                            for bh in break_hours
                        ]
                        break_times_str = ", ".join(break_times) + " 브레이크타임" if break_times else ""

                        last_order_times = info.get("lastOrderTimes", []) or []
                        last_order_times_str = ", ".join(
                            [f"{lo.get('type', '')}: {lo.get('time', '')}" for lo in last_order_times]
                        ) + " 라스트오더" if last_order_times else ""

                        if day:
                            formatted_hours.append(day)
                        if start_time and end_time:
                            formatted_hours.append(f"{start_time} - {end_time}")
                        if break_times_str:
                            formatted_hours.append(break_times_str)
                        if last_order_times_str:
                            formatted_hours.append(last_order_times_str)

        except Exception as e:
            self.log_signal_func(f"영업시간 에러: {e}")
            return ""

        return "\n".join(formatted_hours).strip() if formatted_hours else ""
