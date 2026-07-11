import json
import os
import random
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.str_utils import split_comma_keywords
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.repositories.worker_db_repository import WorkerDbRepository
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverPlaceLocAllSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.out_dir = "output"
        self.folder_path = ""
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.keyword_list: Optional[List[str]] = None
        self.site_name: str = "네이버 플레이스 전국"
        self.total_cnt: int = 0
        self.total_pages: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.saved_ids: Set[str] = set()
        self.remove_duplicate_yn = None
        self._destroyed: bool = False
        self._cleaned_up: bool = False
        self.naver_loc: str = "읍면동"

        # driver
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        # DB Repository
        self.worker_name: str = "naver_place_loc_all"
        self.detail_table_name: str = "naver_place_loc_all"
        self.auto_save_yn: bool = False
        self.db_repository: Optional[WorkerDbRepository] = None

        # 상세 조회 실패 원인을 FAIL 행의 row_error_message로 저장하기 위한 임시 값
        self._last_detail_error_message: Optional[str] = None

    # 초기화
    def init(self) -> bool:

        keyword_str: str = self.get_setting_value(self.setting, "keyword")
        self.keyword_list = split_comma_keywords(keyword_str)
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
        self.naver_loc = str(self.get_setting_value(self.setting, "naver_loc") or "읍면동").strip()

        # DB 저장 후 종료 시 엑셀 자동 저장 여부
        self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))
        self.log_signal_func(f"✅ 엑셀 자동 저장 여부 : {self.auto_save_yn}")

        # 중복제거 여부
        self.remove_duplicate_yn: bool = self.get_setting_value(self.setting, "remove_duplicate_yn")
        self.log_signal_func(f"✅ 중복제거 여부 : {self.remove_duplicate_yn}")

        self.driver_set()

        if not self.db_set():
            return False

        self.log_signal_func(f"선택 항목 : {self.columns}")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        self.log_signal_func("크롤링 사이트 인증에 성공하였습니다.")
        self.log_signal_func("전체 수 계산을 시작합니다. 잠시만 기다려주세요.")
        if self.region:
            self._loc_all_keyword_list()
        else:
            self._only_keywords_keyword_list()

        if self.db_repository and self.db_repository.status == "RUNNING":
            if self.running:
                self.finish_job("SUCCESS")
            else:
                self.finish_job("STOP", "사용자 중단")

        return True

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("✅ 드라이버 세팅")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func, verify=True)

    # 정리
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        # DB 작업 종료 및 자동 엑셀 저장은 연결을 닫기 전에 처리한다.
        self.finalize_db_and_excel()

        try:
            if self.db_repository:
                self.db_repository.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] db_repository.close 실패: {e}")
        finally:
            self.db_repository = None

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
        # BaseApiWorker의 정상 종료 경로에서도 DB 마감/엑셀 저장이 실행되도록 한다.
        self.cleanup()
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    # 중지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False

        self.finish_job("STOP", "사용자 중단")

        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # =========================================================
    # DB Repository
    # =========================================================
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
                user_id=self._get_db_user_id(),
                log_func=self.log_signal_func,
                detail_log_fields=("id", "name"),
            )
        except Exception as e:
            self.log_signal_func(f"❌ [DB] Repository 생성 실패: {e}")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        if not self.db_repository.initialize(schema_files, start_job=True):
            return False

        # 화면/엑셀은 checked=true인 value(한글명)를 사용한다.
        self.columns = list(self.db_repository.excel_columns)

        self.log_signal_func(
            f"✅ [config] DB 컬럼 수={len(self.db_repository.db_columns)} / "
            f"엑셀 컬럼 수={len(self.db_repository.excel_columns)}"
        )
        return True

    def _get_db_user_id(self) -> Optional[Any]:
        if self.user is None:
            return None
        if isinstance(self.user, dict):
            return self.user.get("user_id") or self.user.get("id")
        if isinstance(self.user, (str, int)):
            return self.user
        return getattr(self.user, "user_id", None)

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        if self.db_repository:
            self.db_repository.set_job_result(status, error_message)

    def insert_detail_row(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        """상세 조회 결과와 행 단위 처리 상태를 Repository에 저장한다."""
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

    @staticmethod
    def _now_db() -> str:
        """행 시작·종료시간을 Repository와 동일한 형식으로 반환한다."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _set_detail_error(self, message: str) -> None:
        """현재 상세 조회의 대표 오류 메시지를 저장하고 로그로 출력한다."""
        self._last_detail_error_message = str(message or "상세 조회 실패")
        self.log_signal_func(self._last_detail_error_message)

    def _build_failed_detail_row(
            self,
            place_id: str,
            loc: Dict[str, str],
            query_keyword: str,
            query: str,
    ) -> Dict[str, Any]:
        """상세 조회에 실패해도 검색 기준과 ID를 Detail 테이블에 남긴다."""
        return {
            "id": place_id,
            "name": "",
            "url": f"https://m.place.naver.com/place/{place_id}/home",
            "map": f"https://map.naver.com/p/entry/place/{place_id}",
            "city": loc.get("시도", ""),
            "division": loc.get("시군구", ""),
            "sector": loc.get("읍면동", ""),
            "keyword": query_keyword,
            "all_keyword": query,
        }

    def _fetch_and_save_place_detail(
            self,
            place_id: str,
            loc: Dict[str, str],
            query_keyword: str,
            query: str,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """상세 조회 시간을 측정하고 성공·실패 결과를 모두 Detail에 저장한다."""
        row_start_at = self._now_db()
        self._last_detail_error_message = None

        try:
            place_info = self._fetch_place_info(
                place_id,
                loc,
                query_keyword,
                query,
            )
            row_end_at = self._now_db()

            if place_info:
                save_ok = self.insert_detail_row(
                    place_info,
                    row_status="SUCCESS",
                    row_start_at=row_start_at,
                    row_end_at=row_end_at,
                )
                return place_info, save_ok

            error_message = (
                    self._last_detail_error_message
                    or f"Place ID {place_id} 상세 정보 조회 실패"
            )
            failed_row = self._build_failed_detail_row(
                place_id,
                loc,
                query_keyword,
                query,
            )
            save_ok = self.insert_detail_row(
                failed_row,
                row_status="FAIL",
                row_error_message=error_message,
                row_start_at=row_start_at,
                row_end_at=row_end_at,
            )
            return None, save_ok

        except Exception as e:
            row_end_at = self._now_db()
            error_message = f"Place ID {place_id} 상세 조회 처리 예외: {e}"
            self._set_detail_error(error_message)

            failed_row = self._build_failed_detail_row(
                place_id,
                loc,
                query_keyword,
                query,
            )
            save_ok = self.insert_detail_row(
                failed_row,
                row_status="FAIL",
                row_error_message=error_message,
                row_start_at=row_start_at,
                row_end_at=row_end_at,
            )
            return None, save_ok

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
            # 정상 main 종료라면 SUCCESS/STOP이 이미 설정되어 있다.
            # RUNNING으로 남았다면 예외 또는 초기화 중 비정상 종료로 처리한다.
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


    # 실행용 지역 목록 가공
    def _get_run_region_list(self) -> List[Dict[str, str]]:
        if not self.region:
            return []

        if self.naver_loc == "읍면동":
            return self.region

        result: List[Dict[str, str]] = []
        seen: Set[tuple] = set()

        for item in self.region:
            if not isinstance(item, dict):
                continue

            sido = str(item.get("시도") or "").strip()
            sigungu = str(item.get("시군구") or "").strip()
            eup_myeon_dong = str(item.get("읍면동") or "").strip()

            if self.naver_loc == "시도":
                key = (sido,)
                row = {
                    "시도": sido,
                    "시군구": "",
                    "읍면동": "",
                }
            elif self.naver_loc == "시군구":
                key = (sido, sigungu)
                row = {
                    "시도": sido,
                    "시군구": sigungu,
                    "읍면동": "",
                }
            else:
                key = (sido, sigungu, eup_myeon_dong)
                row = {
                    "시도": sido,
                    "시군구": sigungu,
                    "읍면동": eup_myeon_dong,
                }

            if key in seen:
                continue

            seen.add(key)
            result.append(row)

        return result

    # 전국 키워드 조회
    def _loc_all_keyword_list(self) -> None:
        if not self.region or not self.keyword_list:
            self.log_signal_func("지역 또는 키워드 정보가 없습니다.")
            return

        run_region_list = self._get_run_region_list()
        if not run_region_list:
            self.log_signal_func("실행할 지역 정보가 없습니다.")
            return

        loc_all_len: int = len(run_region_list)
        keyword_list_len: int = len(self.keyword_list)
        self.total_cnt = loc_all_len * keyword_list_len * 300
        self.total_pages = loc_all_len * keyword_list_len * 15

        self.log_signal_func(f"예상 전체 수 {self.total_cnt} 개")
        self.log_signal_func(f"예상 전체 페이지수 {self.total_pages} 개")

        for index, loc in enumerate(run_region_list, start=1):
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            name_parts = [
                str(loc.get("시도") or "").strip(),
                str(loc.get("시군구") or "").strip(),
                str(loc.get("읍면동") or "").strip(),
            ]
            name = " ".join([x for x in name_parts if x])
            if name:
                name += " "

            for idx, query_keyword in enumerate(self.keyword_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                full_name = name + query_keyword
                self.log_signal_func(
                    f"전국: {index} / {loc_all_len}, 키워드: {idx} / {keyword_list_len}, 검색어: {full_name}"
                )
                self._loc_all_keyword_list_detail(
                    full_name,
                    keyword_list_len,
                    idx,
                    loc_all_len,
                    index,
                    loc,
                    query_keyword
                )

    # 전국 상세
    def _loc_all_keyword_list_detail(self, query: str, total_queries: int, current_query_index: int, total_locs: int, locs_index: int, loc: Dict[str, str], query_keyword: str) -> None:
        try:
            page: int = 1
            result_ids: List[str] = []

            while True:
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                time.sleep(random.uniform(1, 2))

                result = self._fetch_search_results(query, page)
                if not result:
                    break

                result_ids.extend(result)
                self.log_signal_func(
                    f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, 검색어: {query}, 페이지: {page}"
                )
                self.log_signal_func(f"목록: {result}")
                page += 1


            for idx, place_id in enumerate(result_ids, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                # 중복제거 사용 시, 이미 저장한 place_id는 스킵
                if self.remove_duplicate_yn and place_id in self.saved_ids:
                    self.log_signal_func(
                        f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, "
                        f"검색어: {query}, 수집: {idx} / {len(result_ids)}, 중복 아이디: {place_id}"
                    )
                    continue

                time.sleep(random.uniform(2, 4))

                place_info, save_ok = self._fetch_and_save_place_detail(
                    place_id,
                    loc,
                    query_keyword,
                    query,
                )
                if not place_info:
                    self.log_signal_func(
                        f"⚠️ ID {place_id} 상세 조회 실패 행 저장 | "
                        f"error={self._last_detail_error_message or '상세 조회 실패'}"
                    )
                    continue

                self.log_signal_func(
                    f"전국: {locs_index} / {total_locs}, 키워드: {current_query_index} / {total_queries}, "
                    f"검색어: {query}, 수집: {idx} / {len(result_ids)}, 아이디: {place_id}, 이름: {place_info['name']}"
                )

                # 상세 조회와 DB 저장이 모두 성공한 경우에만 중복 목록에 추가
                if save_ok and self.remove_duplicate_yn:
                    self.saved_ids.add(place_id)

            self.current_cnt = locs_index * current_query_index * 300
            pro_value = (self.current_cnt / self.total_cnt) * 1000000 if self.total_cnt > 0 else 0
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

        except Exception as e:
            self.log_signal_func(f"loc_all_keyword_list_detail 크롤링 에러: {e}")

    # 키워드만 조회
    def _only_keywords_keyword_list(self) -> None:
        all_ids_list = self._total_cnt_cal()

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

            obj, _ = self._fetch_and_save_place_detail(
                place_id,
                loc,
                "",
                "",
            )

            self.current_cnt = self.current_cnt + 1
            pro_value = (self.current_cnt / self.total_cnt) * 1000000 if self.total_cnt > 0 else 0
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

            self.log_signal_func(f"현재 페이지 {self.current_cnt}/{self.total_cnt} : {obj}")
            time.sleep(random.uniform(1, 2))

    # 전체 갯수 조회
    def _total_cnt_cal(self) -> Optional[List[str]]:
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

                    result = self._fetch_search_results(keyword, page)
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
    def _fetch_search_results(self, keyword: str, page: int) -> List[str]:
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

    # 대행사 정보
    def _fetch_booking_agency_info(self, booking_business_id: str) -> Dict[str, str]:
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
                "agency_name": ag0.get("name", "") or "",
                "agency_ceo": ag0.get("reprName", "") or "",
                "agency_address": ag0.get("address", "") or "",
                "agency_bizno": ag0.get("bizNumber", "") or "",
                "agency_mailno": ag0.get("cbizNumber", "") or "",
                "agency_phone": ag0.get("phone", "") or "",
                "agency_site": ag0.get("websiteUrl", "") or "",
            }

        except Exception as e:
            self.log_signal_func(f"[에러] fetch_booking_agency_info 실패: {e}")
            return {}

    # 상세조회
    def _fetch_place_info(self, place_id: str, loc: Dict[str, str], query_keyword: str, query: str) -> Optional[Dict[str, Any]]:
        try:
            if self.api_client is None:
                self._set_detail_error(
                    f"❌ Place ID {place_id}: api_client가 초기화되지 않았습니다."
                )
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
                self._set_detail_error(f"⚠️ Place ID {place_id} 응답 없음.")
                return None

            soup = BeautifulSoup(response, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"window\.__APOLLO_STATE__"))
            if not script_tag or not script_tag.string:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id}의 스크립트 태그 없음 또는 비어 있음."
                )
                return None

            script_text = script_tag.string

            marker = "window.__APOLLO_STATE__"
            marker_index = script_text.find(marker)
            if marker_index < 0:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} APOLLO_STATE marker 없음."
                )
                return None

            equal_index = script_text.find("=", marker_index)
            if equal_index < 0:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} APOLLO_STATE = 없음."
                )
                return None

            json_start = script_text.find("{", equal_index)
            if json_start < 0:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} APOLLO_STATE JSON 시작 없음."
                )
                return None

            try:
                data, _ = json.JSONDecoder().raw_decode(script_text[json_start:])
            except Exception as e:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} JSON decode 실패: {e}"
                )
                return None

            if not isinstance(data, dict):
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} data가 dict가 아님: {type(data)}"
                )
                return None

            base = data.get(f"PlaceDetailBase:{place_id}", {})
            main_name = base.get("name", "")
            road = base.get("road", "")
            address = base.get("address", "")
            roadAddress = base.get("roadAddress", "")
            category = base.get("category", "")

            # AI요약
            microReviews = base.get("microReviews", [])

            # 결제수단
            paymentInfo = base.get("paymentInfo", [])
            phone = base.get("phone", "")
            virtualPhone = base.get("virtualPhone", "")

            root_query = data.get("ROOT_QUERY", {})
            place_detail_key = self._find_place_detail_key(root_query, place_id)
            if not place_detail_key:
                self._set_detail_error(
                    f"⚠️ Place ID {place_id} placeDetail key를 찾지 못했습니다."
                )
                return None

            place_detail_obj = root_query.get(place_detail_key, {}) or {}


            # 영업시간
            business_hours = []
            new_business_hours_json = []
            for key in place_detail_obj:
                if not business_hours and key.startswith("businessHours"):
                    business_hours = place_detail_obj.get(key, [])

                if not new_business_hours_json and key.startswith("newBusinessHours"):
                    new_business_hours_json = place_detail_obj.get(key, [])

                if business_hours and new_business_hours_json:
                    break

            # 사이트 리스트
            urls: List[str] = []
            shop_window = place_detail_obj.get("shopWindow") or {}
            homepages = shop_window.get("homepages") or {}
            if homepages:
                for item in homepages.get("etc", []) or []:
                    url = (item or {}).get("url", "")
                    if url:
                        urls.append(url)

                repr_data = homepages.get("repr") or {}
                repr_url = repr_data.get("url", "")
                if repr_url:
                    urls.append(repr_url)


            category_list = category.split(",") if category else ["", ""]
            main_category = category_list[0] if len(category_list) > 0 else ""
            sub_category = category_list[1] if len(category_list) > 1 else ""

            zipCode = ""
            if self.db_repository and self.db_repository.is_column_checked("zip_code"):
                zipCode = self._fetch_zipcode_by_addr(address, roadAddress)

            # 대표 이미지
            images = []
            img_origin = ""
            for key in place_detail_obj:
                if key.startswith("images"):
                    image_obj = place_detail_obj.get(key) or {}
                    images = image_obj.get("images", []) or []
                    if images:
                        first_image = images[0] or {}
                        img_origin = first_image.get("origin", "")
                    break

            # 소개
            main_description = ""
            for key in place_detail_obj:
                if key.startswith("description"):
                    main_description = place_detail_obj.get(key) or ""
                    break

            # 테마
            themes = place_detail_obj.get("themes") or ""

            # 연관 키워드
            keywordList = []
            for key in place_detail_obj:
                if key.startswith("informationTab"):
                    info_tab = place_detail_obj.get(key) or {}
                    keywordList = info_tab.get("keywordList", []) or []
                    break

            ## ========== 주차 [시작] ==========
            parking_info = {}
            for key in place_detail_obj:
                if key.startswith("informationTab"):
                    info_tab = place_detail_obj.get(key) or {}
                    parking_info = info_tab.get("parkingInfo", {}) or {}
                    break

            # 주차가능
            basic_parking = parking_info.get("basicParking", {})
            parkingAvailable = ""

            if basic_parking:
                parking_pay = "무료" if basic_parking.get("isFree") else "유료"
                parking_fee = str(basic_parking.get("normalFeeDescription", "") or "").strip()

                if parking_fee:
                    parkingAvailable = f"{parking_pay} : {parking_fee}"
                else:
                    parkingAvailable = parking_pay

            # 발렛가능
            valet_parking = parking_info.get("valetParking", {})
            valetAvailable = ""

            if valet_parking:
                valet_pay = "무료" if valet_parking.get("isFree") else "유료"
                valet_fee = str(valet_parking.get("valetFeeDescription", "") or "").strip()

                if valet_fee:
                    valetAvailable = f"{valet_pay} : {valet_fee}"
                else:
                    valetAvailable = valet_pay

            # 주차
            parkingDesc = parking_info.get("description", "")

            ## ========== 주차 [끝] ==========

            # 메뉴
            menuText = ""
            menu_lines = []
            for key, value in data.items():
                if key.startswith("Menu:"):
                    value = value or {}
                    menu_name = str(value.get("name", "")).strip()
                    price = str(value.get("price", "")).strip()

                    if price.isdigit():
                        price = format(int(price), ",")

                    if menu_name:
                        line = f"메뉴명 : {menu_name}, 가격 : {price}"
                        menu_lines.append(line)
            menuText = "\n".join(menu_lines)


            # 좌석·공간
            seatText = ""
            seat_lines = []
            for key, value in data.items():
                if key.startswith("RestaurantSeatItems:"):
                    value = value or {}
                    seat_name = str(value.get("name", "")).strip()
                    description = str(value.get("description", "")).strip()

                    if seat_name:
                        if description:
                            seat_lines.append(f"{seat_name} : {description}")
                        else:
                            seat_lines.append(seat_name)

            seatText = "\n".join(seat_lines)


            # 편의시설 및 서비스
            conveniences = ""
            facility_names = []
            for key, value in data.items():
                if key.startswith("InformationFacilities:"):
                    value = value or {}
                    facility_name = str(value.get("name", "")).strip()
                    if facility_name:
                        facility_names.append(facility_name)
            conveniences = ", ".join(facility_names)
            if not conveniences:
                conveniences = base.get("conveniences", [])


            # ========== 리뷰 평점[시작] ==========

            # 방문자 리뷰 평점
            visitorReviewsScore = ""

            # 방문자 리뷰 수
            visitorReviewsTotal = ""

            # 영수증 리뷰 수
            votedKeywordReviewCount = ""

            # 키워드·별점 리뷰
            ratingReviewsTotal = ""

            # 블로그 리뷰수
            blogReviewTotal = ""

            for key in data:
                if key.startswith("VisitorReview"):
                    review = data.get(key, {}) or {}

                    review_info = review.get("review", {}) or {}
                    visitorReviewsScore = review_info.get("avgRating", "")

                    analysis = review.get("analysis", {}) or {}
                    votedKeyword = analysis.get("votedKeyword", {}) or {}
                    votedKeywordReviewCount = votedKeyword.get("reviewCount", "")

                    rating_total = int(review.get("ratingReviewsTotal", 0) or 0)
                    visitor_total = int(review.get("visitorReviewsTotal", 0) or 0)

                    ratingReviewsTotal = rating_total
                    visitorReviewsTotal = visitor_total - rating_total
                    break

            # 없는 경우 대비
            review_stats = data.get(f"VisitorReviewStatsResult:{place_id}", {}) or {}
            review = review_stats.get("review", {}) or {}
            analysis = review_stats.get("analysis", {}) or {}
            voted_keyword = analysis.get("votedKeyword", {}) or {}

            # 방문자 리뷰 평점
            if not visitorReviewsScore:
                visitorReviewsScore = review.get("avgRating", "")

            # 방문자 리뷰 수
            if visitorReviewsTotal == "":
                visitor_total = int(review_stats.get("visitorReviewsTotal", 0) or 0)
                rating_total = int(ratingReviewsTotal or 0)
                visitorReviewsTotal = visitor_total - rating_total

            # 키워드·별점 리뷰
            if not ratingReviewsTotal:
                ratingReviewsTotal = int(review_stats.get("ratingReviewsTotal", 0) or 0)

            # 영수증 리뷰 수
            if not votedKeywordReviewCount:
                votedKeywordReviewCount = voted_keyword.get("reviewCount", "")

            # 블로그 리뷰수
            for key in place_detail_obj:
                if "fsasReviews" in key:
                    fsas_reviews = place_detail_obj.get(key) or {}
                    blogReviewTotal = fsas_reviews.get("total", "")
                    break

            # 출력용으로 0이면 공백 처리하고 싶으면 마지막에만
            if visitorReviewsTotal == 0:
                visitorReviewsTotal = ""

            if ratingReviewsTotal == 0:
                ratingReviewsTotal = ""

            # ========== 리뷰 평점[끝] ==========

            # DB 저장 기준은 config.json columns[].code와 동일한 영문 key를 사용한다.
            result: Dict[str, Any] = {
                "id": place_id,
                "name": main_name,
                "addr_jibun": address,
                "addr_road": roadAddress,
                "category_main": main_category,
                "category_sub": sub_category,
                "visitorReviewsScore": visitorReviewsScore,
                "visitorReviewsTotal": visitorReviewsTotal,
                "ratingReviewsTotal": ratingReviewsTotal,
                "blogReviewTotal": blogReviewTotal,
                "votedKeywordReviewCount": votedKeywordReviewCount,
                "open_time1": self._format_new_business_hours(new_business_hours_json),
                "open_time2": self._format_business_hours(business_hours),
                "category": category,
                "url": f"https://m.place.naver.com/place/{place_id}/home",
                "img_origin": img_origin,
                "map": f"https://map.naver.com/p/entry/place/{place_id}",
                "amenities": conveniences,
                "themes": ", ".join(themes) if themes else "",
                "menuText": menuText,
                "seatText": seatText,
                "parkingAvailable": parkingAvailable,
                "valetAvailable": valetAvailable,
                "parkingDesc": parkingDesc,
                "keywordList": ", ".join(keywordList) if keywordList else "",
                "microReviews": ", ".join(microReviews) if microReviews else "",
                "description": main_description,
                "paymentInfo": ", ".join(paymentInfo) if paymentInfo else "",
                "virtual_phone": virtualPhone,
                "phone": phone,
                "site": ", ".join(urls) if urls else "",
                "region_info": road,
                "city": loc.get("시도", ""),
                "division": loc.get("시군구", ""),
                "sector": loc.get("읍면동", ""),
                "keyword": query_keyword,
                "all_keyword": query,
                "zip_code": zipCode,
            }

            agency_codes = [
                "agency_name",
                "agency_ceo",
                "agency_address",
                "agency_bizno",
                "agency_mailno",
                "agency_phone",
                "agency_site",
            ]

            want_agency = bool(
                self.db_repository
                and self.db_repository.are_any_columns_checked(agency_codes)
            )

            if want_agency:
                booking_business_id = self._extract_booking_business_id(place_detail_obj)
                if booking_business_id:
                    time.sleep(random.uniform(2, 4))
                    agency_info = self._fetch_booking_agency_info(booking_business_id)

                    if isinstance(agency_info, dict):
                        for code in agency_codes:
                            if self.db_repository and self.db_repository.is_column_checked(code):
                                result[code] = agency_info.get(code, "")

            return result

        except requests.exceptions.RequestException as e:
            self._set_detail_error(
                f"❌ 네트워크 에러: Place ID {place_id}: {e}"
            )
        except Exception as e:
            self._set_detail_error(
                f"❌ 처리 중 에러: Place ID {place_id}: {e}"
            )

        return None

    # 우편번호
    def _fetch_zipcode_by_addr(self, addr_jibun: str, addr_road: str) -> str:
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
    def _format_business_hours(self, business_hours: List[Dict[str, Any]]) -> str:
        formatted_hours: List[str] = []
        try:
            if business_hours:
                for hour in business_hours:
                    day = hour.get("day", "") or ""
                    start_time = hour.get("startTime", "") or ""
                    end_time = hour.get("endTime", "") or ""
                    description = hour.get("description", "") or ""
                    if day and start_time and end_time:
                        line = f"{day} {start_time} - {end_time}"
                        if description:
                            line += f" {description}"
                        formatted_hours.append(line)
        except Exception as e:
            self.log_signal_func(f"Unexpected error: {e}")
            return ""

        return "\n".join(formatted_hours).strip() if formatted_hours else ""

    # 영업시간 함수2
    def _format_new_business_hours(self, new_business_hours: List[Dict[str, Any]]) -> str:
        formatted_hours: List[str] = []

        try:
            day_order = {
                "일": 0,
                "월": 1,
                "화": 2,
                "수": 3,
                "목": 4,
                "금": 5,
                "토": 6,
            }

            if new_business_hours:
                for item in new_business_hours:
                    business_hours_list = item.get("businessHours", []) or []

                    business_hours_list = sorted(
                        business_hours_list,
                        key=lambda x: day_order.get(x.get("day", "") or "", 99)
                    )

                    for info in business_hours_list:
                        day = info.get("day", "") or ""
                        info_description = info.get("description", "") or ""

                        business_hours = info.get("businessHours", {}) or {}
                        start_time = business_hours.get("start", "") or ""
                        end_time = business_hours.get("end", "") or ""

                        break_hours = info.get("breakHours", []) or []
                        break_times: List[str] = []
                        for bh in break_hours:
                            bh_start = bh.get("start", "") or ""
                            bh_end = bh.get("end", "") or ""
                            if bh_start and bh_end:
                                break_times.append(f"{bh_start} - {bh_end}")
                        break_times_str = ", ".join(break_times) + " 브레이크타임" if break_times else ""

                        last_order_times = info.get("lastOrderTimes", []) or []
                        last_order_list: List[str] = []
                        for lo in last_order_times:
                            lo_time = lo.get("time", "") or ""
                            if lo_time:
                                last_order_list.append(lo_time)
                        last_order_times_str = ", ".join(last_order_list) + " 라스트오더" if last_order_list else ""

                        if day:
                            formatted_hours.append(day)

                        if start_time and end_time:
                            formatted_hours.append(f"{start_time} - {end_time}")
                        elif info_description:
                            formatted_hours.append(info_description)

                        if break_times_str:
                            formatted_hours.append(break_times_str)

                        if last_order_times_str:
                            formatted_hours.append(last_order_times_str)

            return "\n".join(formatted_hours).strip()

        except Exception as e:
            self.log_signal_func(f"❌ 영업시간 포맷 실패: {e}")
            return ""
