import os
import time
from typing import Any, Dict, List, Optional
import random
import json
from decimal import Decimal, InvalidOperation

from src.utils.api_utils import APIClient
from src.utils.excel_hybrid_utils import ExcelHybridUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker
from src.utils.time_utils import yyyy_mm_dd_to
from urllib.parse import quote
from pyproj import Transformer

class ApiNaverLandRealEstateDetailSetWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        # === 신규 === DB 저장용 공통 상태
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None
        # 사용자 중지 중복 실행 방지
        self._stopping: bool = False
        self.worker_name: str = "naver_land_real_estate_detail"
        self.detail_table_name: str = "naver_land_real_estate_detail"
        self.stat_table_name: str = "naver_land_real_estate_stat"
        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0
        self.auto_save_yn: bool = False
        self.sigungu_count_yn: bool = False

        self.base_amount = None
        self.eng_yn = None
        self.remove_duplicate_yn = None
        self.filter_data = None
        self.brokerage_yn = None
        self.link_yn = None
        self.detail_column_yn = None
        self.eng = None
        self.article_sort_type = None
        self.all_date_yn: bool = False
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
        self.excel_driver: Optional[ExcelHybridUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
        self.api_client: Optional[APIClient] = None

        self.folder_path: str = ""
        self.out_dir: str = "output"

        self.naver_loc_all_real_detail = None
        self.naver_loc_si_gun_gu = None
        self.detail_region_article_list = None
        self.work_items: list[dict[str, Any]] = []

        self.list_api_url: str = "https://fin.land.naver.com/front-api/v1/article/boundedArticles"
        self.agent_detail_url: str = "https://fin.land.naver.com/front-api/v1/article/agent"
        self.detail_api_url: str = "https://fin.land.naver.com/front-api/v1/article/basicInfo"
        self.article_key_url: str = "https://fin.land.naver.com/front-api/v1/article/key"
        self.complex_api_url: str = "https://fin.land.naver.com/front-api/v1/complex"
        self.sigungu_article_count_url: str = "https://fin.land.naver.com/front-api/v1/article/legalDivisionArticleClusters"
        self.sigungu_complex_count_url: str = "https://fin.land.naver.com/front-api/v1/complex/legalDivisionComplexClusters"
        self.url: str = "https://fin.land.naver.com"

        self.list_hook_js = None
        self.browser_fetch_json_js = None
        self.click_sort_button_js = None
        self.click_article_button_js = None

    def init(self) -> bool:
        try:
            self.excel_driver = ExcelHybridUtils(self.log_signal_func)
            self.file_driver = FileUtils(self.log_signal_func)
            self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

            if not self.db_set():
                return False

            self.driver_set()

            self.log_signal_func(f"선택 항목 : {self.columns}")
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.finish_job("FAIL", str(e))
            self.log_signal_func(f"❌ 초기화 에러: {e}")
            return False

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
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
                self.log_signal_func("✅ [DB] 기존 연결 해제")
        except Exception as e:
            self.log_signal_func(f"[cleanup] sqlite_driver.close 실패: {e}")
        finally:
            self.sqlite_driver = None

        self.finalize_db_and_excel()

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

    def stop(self) -> None:
        # MainWindow의 중지/정리 과정에서 stop()이 중복 호출될 수 있으므로 1회만 수행한다.
        if self._stopping:
            return

        self._stopping = True
        self.log_signal_func("✅ stop 시작")
        self.running = False

        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        self.progress_end_signal.emit()

    def driver_set(self) -> None:
        if not self.excel_driver:
            self.excel_driver = ExcelHybridUtils(self.log_signal_func)

        if not self.file_driver:
            self.file_driver = FileUtils(self.log_signal_func)

        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(timeout=1200, view_mode="browser", window_size=(1600, 1000))

    # =========================================================
    # DB 저장 / 마감 처리
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)

        db_path = self.get_runtime_db_path()
        self.log_signal_func(f"[DB] 실제 경로 = {os.path.abspath(db_path)}")

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_stat.sql"),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        self.log_signal_func("✅ [DB] 스키마 초기화 완료")

        # 통계 컬럼은 schema_stat.sql의 별도 통계 테이블에서 관리한다.
        # 기존 상세 테이블에 통계 컬럼을 추가/수정하지 않는다.

        if not self.insert_hist_start():
            return False

        return True

    def _ensure_detail_validation_columns(self) -> bool:
        if not self.sqlite_driver:
            return False

        validation_columns = {
            "totalCount": "INTEGER",
            "crawledCount": "INTEGER",
            "trueFalse": "TEXT",
            "sigunguTotalCount": "INTEGER",
            "sigunguCrawledCount": "INTEGER",
            "sigunguTrueFalse": "TEXT",
            "failedDongNames": "TEXT",
            "sigunguDiffCount": "INTEGER",
            "sigunguErrorRate": "REAL",
        }

        try:
            rows = self.sqlite_driver.fetchall(f"PRAGMA table_info({self.detail_table_name})", ()) or []
            existing_columns = {str(row["name"]) for row in rows if row and row["name"]}

            for column_name, column_type in validation_columns.items():
                if column_name in existing_columns:
                    continue

                query = f"ALTER TABLE {self.detail_table_name} ADD COLUMN {column_name} {column_type}"
                if not self.sqlite_driver.execute(query, ()):
                    self.log_signal_func(f"❌ [DB] 검증 컬럼 추가 실패 : {column_name}")
                    return False

                self.log_signal_func(f"✅ [DB] 검증 컬럼 자동 추가 : {column_name} {column_type}")

            return True

        except Exception as e:
            self.log_signal_func(f"❌ [DB] 검증 컬럼 확인/추가 실패 : {e}")
            return False

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def insert_hist_start(self) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id,
                    table_name,
                    site_name,
                    worker_name,
                    user_id,
                    start_at,
                    status,
                    total_count,
                    success_count,
                    fail_count,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

        params = (
            self.job_id,
            self.detail_table_name,
            self.site_name,
            self.worker_name,
            str(self.user).strip() if self.user else None,
            now,
            "RUNNING",
            0,
            0,
            0,
            now,
            now,
        )

        if not self.sqlite_driver.execute(query, params):
            self.log_signal_func("❌ [DB] hist 시작 row 저장 실패")
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None

        self.log_signal_func(f"✅ [DB] hist 시작 row 저장 완료 | hist_id={self.hist_id}")
        return True

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver

        if not sqlite_driver:
            return False

        if not self.hist_id:
            self.log_signal_func("⚠️ [DB] hist_id 없음 - 종료 update 스킵")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = """
                UPDATE worker_job_hist
                SET
                    end_at = ?,
                    status = ?,
                    total_count = ?,
                    success_count = ?,
                    fail_count = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE hist_id = ?
                """

        params = (
            now,
            self.hist_status,
            self.detail_success_count + self.detail_fail_count,
            self.detail_success_count,
            self.detail_fail_count,
            self.hist_error_message,
            now,
            self.hist_id,
        )

        if not sqlite_driver.execute(query, params):
            self.log_signal_func(f"❌ [DB] hist 종료 row 수정 실패 | hist_id={self.hist_id}")
            return False

        self.log_signal_func(
            f"✅ [DB] hist 종료 row 수정 완료 | hist_id={self.hist_id} | status={self.hist_status}"
        )
        return True

    def insert_detail_row(self, rs: Dict[str, Any]) -> bool:
        if not self.sqlite_driver:
            self.detail_fail_count += 1
            self.log_signal_func("❌ [DB] sqlite_driver 없음 - detail 저장 실패")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        db_columns = self._get_db_columns()
        db_rs = self._map_out_to_db(rs)

        base_columns = [
            "hist_id",
            "site_name",
            "worker_name",
            "table_name",
            "job_id",
            "user_id",
            "row_status",
        ]

        all_columns = base_columns + db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(all_columns)

        query = f"""
                INSERT INTO {self.detail_table_name} (
                    {column_text}
                ) VALUES ({placeholders})
                """

        params = (
            self.hist_id,
            self.site_name,
            self.worker_name,
            self.detail_table_name,
            self.job_id,
            str(self.user).strip() if self.user else None,
            "SUCCESS",
            *[db_rs.get(col, "") for col in db_columns],
            now,
            now,
        )

        ok = self.sqlite_driver.execute(query, params)

        if ok:
            self.detail_success_count += 1
            self.log_signal_func(
                f"✅ [DB] detail 저장 완료 | hist_id={self.hist_id} | 매물번호={rs.get('매물번호')}"
            )
        else:
            self.detail_fail_count += 1
            self.log_signal_func(
                f"❌ [DB] detail 저장 실패 | hist_id={self.hist_id} | 매물번호={rs.get('매물번호')}"
            )

        return ok


    def bulk_insert_detail_rows(self, rs_list: list[dict[str, Any]]) -> bool:
        """
        리스트에 담긴 여러 row를 executemany를 사용해 한 번에 DB에 밀어 넣는 함수
        """
        if not self.sqlite_driver or not rs_list:
            self.detail_fail_count += len(rs_list)
            self.log_signal_func("❌ [DB] sqlite_driver 없거나 저장할 데이터가 없음")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        db_columns = self._get_db_columns()

        base_columns = [
            "hist_id", "site_name", "worker_name", "table_name", "job_id", "user_id", "row_status"
        ]
        all_columns = base_columns + db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(all_columns)

        query = f"""
                    INSERT INTO {self.detail_table_name} (
                        {column_text}
                    ) VALUES ({placeholders})
                    """

        # executemany에 던질 파라미터 리스트(튜플들의 리스트) 생성
        params_list = []
        for rs in rs_list:
            db_rs = self._map_out_to_db(rs)
            params = (
                self.hist_id,
                self.site_name,
                self.worker_name,
                self.detail_table_name,
                self.job_id,
                str(self.user).strip() if self.user else None,
                "SUCCESS",
                *[db_rs.get(col, "") for col in db_columns],
                now,
                now,
            )
            params_list.append(params)

        try:
            # sqlite3 커넥션에 직접 접근하여 executemany 실행 (가장 빠름)
            conn = self.sqlite_driver.conn
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()

            self.detail_success_count += len(rs_list)
            self.log_signal_func(f"✅ [DB] bulk insert 완료 | hist_id={self.hist_id} | count={len(rs_list)}")
            return True

        except Exception as e:
            self.detail_fail_count += len(rs_list)
            self.log_signal_func(f"❌ [DB] bulk insert 실패 | hist_id={self.hist_id} | error={e}")
            return False


    def _get_db_columns(self) -> List[str]:
        # 실제 매물 컬럼을 먼저 두고, 수집 검증 컬럼 9개는 맨 뒤에 배치한다.
        return ['atclNo',
                'articleName',
                'complexName',
                'dongName',
                'hanPrc',
                'warrantyAmount',
                'rentPrc',
                'spc1',
                'landSpace',
                'floorSpace',
                'buildingSpace',
                'spc2',
                'ipjuday',
                'date',
                'targetFloor',
                'totalFloor',
                'city',
                'division',
                'sector',
                'zipCode',
                'full_addr',
                'rltrNm',
                'broker_name',
                'atclUrl',
                'atclNm',
                'bildNm',
                'parentYn',
                'upperAtclNo',
                'rletTpNm',
                'tradTpNm',
                'tagList',
                'atclCfmYmd',
                'lat',
                'lng',
                'direction',
                'sameAddrCnt',
                'sameAddrMinPrc',
                'sameAddrMaxPrc',
                'atclFetrDesc',
                'currentBusinessType',
                'recommendedBusinessType',
                'vrfcTpCd',
                'buildingConjunctionDate',
                'keyword',
                'supplySpaceName',
                'buildingPrincipalUse',
                'articleDescription',
                'broker_address',
                'phone',
                'phone_mobile',
                'roadName',
                'jibun',
                'ho',
                'flrInfo',
                'id',
                'searchRequirement',
                'articlePriceInfo',
                'rank']


    def _get_kor_header_map(self) -> Dict[str, str]:
        # === 신규 ===
        # 한글명(value)은 기존 columns.json 기준 그대로 유지한다.
        return {'atclNo': '매물번호',
                'articleName': '매물명',
                'complexName': '단지명',
                'dongName': '동이름',
                'hanPrc': '매매가',
                'warrantyAmount': '보증금/전세',
                'rentPrc': '월세',
                'spc1': '공급면적',
                'landSpace': '대지면적',
                'floorSpace': '연면적',
                'buildingSpace': '건축면적',
                'spc2': '전용면적',
                'ipjuday': '매물확인일',
                'date': '매물노출시작일',
                'targetFloor': '해당층',
                'totalFloor': '전체층',
                'city': '시도',
                'division': '시군구',
                'sector': '읍면동',
                'zipCode': '우편번호',
                'full_addr': '전체주소',
                'rltrNm': '중개사무소이름',
                'broker_name': '중개사이름',
                'atclUrl': 'URL',
                'atclNm': '상위매물명',
                'bildNm': '상위매물동',
                'parentYn': '부모여부',
                'upperAtclNo': '상위매물번호',
                'rletTpNm': '매물유형',
                'tradTpNm': '거래유형',
                'tagList': '매물태그',
                'atclCfmYmd': '등록일자',
                'lat': '위도',
                'lng': '경도',
                'direction': '방향정보',
                'sameAddrCnt': '동일주소매물수',
                'sameAddrMinPrc': '동일주소최소가',
                'sameAddrMaxPrc': '동일주소최대가',
                'atclFetrDesc': '매물설명',
                'currentBusinessType': '현재업종',
                'recommendedBusinessType': '추천업종',
                'vrfcTpCd': '매물확인코드',
                'buildingConjunctionDate': '사용승인일',
                'keyword': '검색 주소',
                'supplySpaceName': '평수',
                'buildingPrincipalUse': '건축물용도',
                'articleDescription': '매물상세설명',
                'broker_address': '중개사무소주소',
                'phone': '중개사무소번호',
                'phone_mobile': '중개사핸드폰번호',
                'roadName': '도로명주소',
                'jibun': '번지',
                'ho': '호',
                'flrInfo': '층정보',
                'id': 'ID',
                'searchRequirement': '검색조건',
                'articlePriceInfo': '가격정보',
                'rank': '순위',
                'totalCount': '읍면동 전체 수',
                'crawledCount': '읍면동 전체 크롤링 수',
                'trueFalse': '읍면동 T/F',
                'sigunguTotalCount': '시군구 전체 수',
                'sigunguCrawledCount': '시군구 전체 크롤링 수',
                'sigunguTrueFalse': '시군구 T/F',
                'failedDongNames': '실패 또는 스킵 읍면동',
                'sigunguDiffCount': '오차 갯수',
                'sigunguErrorRate': '오차 비율'}

    def _get_kor_columns(self) -> List[str]:
        header_map = self._get_kor_header_map()
        return [header_map.get(code, code) for code in self._get_db_columns()]

    def _db_rows_to_kor_rows(self, row_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        header_map = self._get_kor_header_map()
        result: List[Dict[str, Any]] = []

        for row in row_list or []:
            out: Dict[str, Any] = {}
            for code in self._get_db_columns():
                kor_name = header_map.get(code, code)
                out[kor_name] = row.get(code, "")
            result.append(out)

        return result

    def export_detail_to_excel(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver

        if not self.excel_driver:
            self.log_signal_func("❌ [엑셀] excel_driver 없음")
            return False

        if not sqlite_driver:
            self.log_signal_func("❌ [엑셀] sqlite_driver 없음")
            return False

        if not self.hist_id:
            self.log_signal_func("❌ [엑셀] hist_id 없음")
            return False

        try:
            # ============================================================
            # Sheet1 - 상세 데이터
            # ============================================================
            if self.eng_yn:
                detail_db_columns = self._get_eng_columns()
            else:
                detail_db_columns = self._get_db_columns()

            if not detail_db_columns:
                self.log_signal_func("❌ [엑셀] detail 컬럼이 없습니다.")
                return False

            detail_select_text = ",\n                    ".join(detail_db_columns)
            detail_query = f"""
                    SELECT
                        {detail_select_text}
                    FROM {self.detail_table_name}
                    WHERE hist_id = ?
                    ORDER BY detail_id
                    """

            detail_rows = sqlite_driver.fetchall(detail_query, (self.hist_id,)) or []
            detail_rows = [dict(row) for row in detail_rows]

            if not detail_rows:
                self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
                return False

            self.log_signal_func(f"[엑셀] detail 조회 완료 | count={len(detail_rows)}")

            # ============================================================
            # Sheet1 출력 데이터 구성
            # ============================================================
            if self.eng_yn:
                excel_detail_rows = detail_rows
                excel_detail_columns = self.columns or self._get_eng_columns()
            else:
                excel_detail_rows = self._db_rows_to_kor_rows(detail_rows)

                if self.link_yn:
                    excel_detail_rows = [
                        self._apply_excel_hyperlinks_to_row(row)
                        for row in excel_detail_rows
                    ]

                excel_detail_columns = self.columns or self._get_kor_columns()

            # ============================================================
            # Sheet2 - 통계 데이터
            # ============================================================
            stat_columns = self._get_stat_columns()
            stat_rows: List[Dict[str, Any]] = []

            if stat_columns:
                stat_select_text = ",\n                    ".join(stat_columns)
                stat_query = f"""
                        SELECT
                            {stat_select_text}
                        FROM {self.stat_table_name}
                        WHERE hist_id = ?
                        ORDER BY stat_id
                        """

                fetched_stat_rows = sqlite_driver.fetchall(stat_query, (self.hist_id,)) or []
                stat_rows = [dict(row) for row in fetched_stat_rows]

            self.log_signal_func(f"[엑셀] 통계 조회 완료 | count={len(stat_rows)}")

            stat_header_map = self._get_stat_header_map()
            excel_filename = f"{self.site_name}_{self.job_id}.xlsx"

            # ============================================================
            # Sheet1 + Sheet2를 하나의 ExcelWriter에서 작성한다.
            # 기존처럼 Sheet1 저장 후 load_workbook()으로 다시 열지 않는다.
            # ============================================================
            # URL은 항상 하이퍼링크 처리한다.
            # 설정의 "링크(주소,매물번호)"가 켜진 경우에만
            # 매물번호와 전체주소 링크를 추가 처리한다.
            if self.eng_yn:
                hyperlink_columns = ["atclUrl"]
                if self.link_yn:
                    hyperlink_columns.extend(["atclNo", "full_addr"])
            else:
                hyperlink_columns = ["URL"]
                if self.link_yn:
                    hyperlink_columns.extend(["매물번호", "전체주소"])

            sheets = [
                {
                    "sheet_name": "Sheet1",
                    "row_list": excel_detail_rows,
                    "columns": excel_detail_columns,
                    "header_map": None,
                    "column_widths": [
                        {"컬럼": column_name, "너비": 16}
                        for column_name in excel_detail_columns
                    ],
                    "default_width": 16,
                    "hyperlink_columns": hyperlink_columns,
                }
            ]

            if stat_rows:
                sheets.append({
                    "sheet_name": "Sheet2",
                    "row_list": stat_rows,
                    "columns": stat_columns,
                    "header_map": stat_header_map,
                    "column_widths": [
                        {"컬럼": stat_header_map.get(col, col), "너비": 18}
                        for col in stat_columns
                    ],
                    "default_width": 18,
                    "hyperlink_columns": [],
                })

            result = self.excel_driver.save_db_sheets_to_excel(
                excel_filename=excel_filename,
                sheets=sheets,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

            if not result:
                self.log_signal_func("❌ [엑셀] detail + 통계 자동 저장 실패")
                return False

            self.log_signal_func("✅ [엑셀] detail + 통계 자동 저장 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ [엑셀] 자동 저장 중 오류: {e}")
            return False

    def finalize_db_and_excel(self) -> None:
        # 실제 작업이 시작되지 않은 경우
        # worker 객체만 생성된 상태에서는 hist_id가 없으므로
        # DB 종료 처리 및 엑셀 저장을 수행하지 않는다.
        if not self.hist_id:
            return

        temp_sqlite_driver = None

        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            db_path = self.get_runtime_db_path()

            if not temp_sqlite_driver.connect(db_path):
                self.log_signal_func("❌ [DB] 최종 마감용 연결 실패")
                return

            # 작업 이력 종료 처리
            if self.update_hist_end(temp_sqlite_driver):
                self.log_signal_func("✅ [DB] hist 최종 업데이트 완료")
            else:
                self.log_signal_func("❌ [DB] hist 최종 업데이트 실패")

            # 엑셀 자동 저장
            if self.auto_save_yn:
                if self.export_detail_to_excel(temp_sqlite_driver):
                    self.log_signal_func("✅ [엑셀] detail 자동 저장 완료")
                else:
                    self.log_signal_func("❌ [엑셀] detail 자동 저장 실패")
            else:
                self.log_signal_func(
                    "ℹ️ [엑셀] 자동 저장 미사용(auto_save_yn=False)"
                )

        except Exception as e:
            self.log_signal_func(
                f"[cleanup] finalize_db_and_excel 실패: {e}"
            )

        finally:
            try:
                if temp_sqlite_driver:
                    temp_sqlite_driver.close()
            except Exception:
                pass

    def main(self) -> bool:
        self.log_signal_func(" main 시작")

        # 저장경로
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        # === 신규 === DB 저장 후 종료 시 엑셀 자동 저장 여부
        self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))
        self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")

        # 시군구 전체 갯수 검증 사용 여부
        self.sigungu_count_yn = bool(self.get_setting_value(self.setting, "sigungu_count_yn"))
        self.log_signal_func(f"시군구 갯수 조회 여부 : {self.sigungu_count_yn}")

        # 영어컬럼 여부
        self.eng_yn: bool = self.get_setting_value(self.setting, "eng_yn")
        self.log_signal_func(f"영어컬럼 여부 : {self.eng_yn}")
        if self.eng_yn:
            self.columns = self._get_eng_columns()

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

        if self.sigungu_count_yn:
            self.naver_loc_si_gun_gu = self.file_driver.read_json_array_from_resources(
                "korea_si_gun_gu.json",
                "customers/naver_land_real_estate_detail/region",
            ) or []
            self.log_signal_func(f"시군구 법정동 코드 로드 : {len(self.naver_loc_si_gun_gu)}건")
        else:
            self.naver_loc_si_gun_gu = []

        # 2. 등록일
        self.all_date_yn: bool = bool(self.get_setting_value(self.setting, "all_date_yn"))
        self.log_signal_func(f"매물 전체 등록일 사용 여부 : {self.all_date_yn}")

        if self.all_date_yn:
            # 전체 등록일을 사용하는 경우 아래 기간 설정은 적용하지 않는다.
            self.fr_date = ""
            self.to_date = ""
            self.log_signal_func("전체 등록일 사용 설정으로 날짜 범위 필터를 적용하지 않습니다.")
        else:
            self.fr_date = str(self.get_setting_value(self.setting, "fr_date") or "").strip()
            self.to_date = str(self.get_setting_value(self.setting, "to_date") or "").strip()
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

        if self.hist_status == "RUNNING":
            if self.running:
                self.finish_job("SUCCESS")
            else:
                self.finish_job("STOP", "사용자 중단")

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

    def _validation_value_to_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _build_article_price_info(self, out: Dict[str, Any]) -> str:
        price = str(out.get("매매가") or "").strip()
        warranty = str(out.get("보증금/전세") or out.get("보증금") or "").strip()
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
            "atclFetrDesc": str(out.get("매물설명") or ""),
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

            # 수집 검증 정보
            "totalCount": self._validation_value_to_text(out.get("읍면동 전체 수", out.get("갯수"))),
            "crawledCount": self._validation_value_to_text(out.get("읍면동 전체 크롤링 수")),
            "trueFalse": self._validation_value_to_text(out.get("읍면동 T/F", out.get("T/F"))),
            "sigunguTotalCount": self._validation_value_to_text(out.get("시군구 전체 수")),
            "sigunguCrawledCount": self._validation_value_to_text(out.get("시군구 전체 크롤링 수")),
            "sigunguTrueFalse": self._validation_value_to_text(out.get("시군구 T/F")),
            "failedDongNames": self._validation_value_to_text(out.get("실패 또는 스킵 읍면동")),
            "sigunguDiffCount": self._validation_value_to_text(out.get("오차 갯수")),
            "sigunguErrorRate": self._validation_value_to_text(out.get("오차 비율")),
        }

        return eng_out

    def _map_out_to_db(self, out: Dict[str, Any]) -> Dict[str, Any]:
        # === 신규 ===
        # _get_eng_columns()에 있는 값은 먼저 영어 매핑값을 사용하고,
        # 기존 columns.json에만 있던 컬럼은 기존 한글 row에서 그대로 채운다.
        db_out: Dict[str, Any] = dict(self._map_out_to_eng(out))

        db_out.update({
            "articleName": str(out.get("매물명") or ""),
            "complexName": str(out.get("단지명") or ""),
            "dongName": str(out.get("동이름") or ""),
            "warrantyAmount": str(out.get("보증금/전세") or ""),
            "landSpace": str(out.get("대지면적") or ""),
            "floorSpace": str(out.get("연면적") or ""),
            "buildingSpace": str(out.get("건축면적") or ""),
            "targetFloor": str(out.get("해당층") or ""),
            "totalFloor": str(out.get("전체층") or ""),
            "city": str(out.get("시도") or ""),
            "division": str(out.get("시군구") or ""),
            "sector": str(out.get("읍면동") or ""),
            "zipCode": str(out.get("우편번호") or ""),
            "full_addr": str(out.get("전체주소") or ""),
            "broker_name": str(out.get("중개사이름") or ""),
            "currentBusinessType": str(out.get("현재업종") or ""),
            "recommendedBusinessType": str(out.get("추천업종") or ""),
            "buildingConjunctionDate": str(out.get("사용승인일") or ""),
            "buildingPrincipalUse": str(out.get("건축물용도") or ""),
            "articleDescription": str(out.get("매물상세설명") or ""),
            "broker_address": str(out.get("중개사무소주소") or ""),
            "phone_mobile": str(out.get("중개사핸드폰번호") or ""),
            "roadName": str(out.get("도로명주소") or ""),
        })

        return db_out

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

    def _upsert_stat_dong(
            self,
            sido: Any,
            sigungu: Any,
            eup_myeon_dong: Any,
            total_count: int,
            crawled_count: int,
            true_false: str,
    ) -> bool:
        """
        읍면동 단위 검증값을 통계 테이블에 저장한다.

        기존 detail 성공/실패 카운트에는 영향을 주지 않는다.
        동일 job_id + 시도 + 시군구 + 읍면동이면 기존 행을 갱신한다.
        """
        if not self.sqlite_driver or not self.hist_id or not self.job_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = f"""
                INSERT INTO {self.stat_table_name} (
                    hist_id,
                    job_id,
                    city,
                    division,
                    sector,
                    totalCount,
                    crawledCount,
                    trueFalse,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, city, division, sector)
                DO UPDATE SET
                    hist_id = excluded.hist_id,
                    totalCount = excluded.totalCount,
                    crawledCount = excluded.crawledCount,
                    trueFalse = excluded.trueFalse,
                    created_at = excluded.created_at
                """

        params = (
            self.hist_id,
            self.job_id,
            str(sido or "").strip(),
            str(sigungu or "").strip(),
            str(eup_myeon_dong or "").strip(),
            int(total_count or 0),
            int(crawled_count or 0),
            str(true_false or ""),
            now,
        )

        ok = bool(self.sqlite_driver.execute(query, params))
        if not ok:
            self.log_signal_func(
                f"❌ [DB] 통계 읍면동 저장 실패 | "
                f"{sido} {sigungu} {eup_myeon_dong}"
            )
        return ok

    def _update_stat_sigungu(
            self,
            sido: Any,
            sigungu: Any,
            total_count: Optional[int],
            crawled_count: int,
            true_false: str,
            failed_dong_names: str,
            diff_count: Optional[int],
            error_rate: Optional[float],
    ) -> bool:
        """
        시군구 최종 검증값을 해당 시군구의 통계 행 전체에 반영한다.

        기존 _finalize_sigungu_validation_map()에서 이미 계산한 값을 그대로 사용한다.
        """
        if not self.sqlite_driver or not self.hist_id or not self.job_id:
            return False

        query = f"""
                UPDATE {self.stat_table_name}
                SET
                    sigunguTotalCount = ?,
                    sigunguCrawledCount = ?,
                    sigunguTrueFalse = ?,
                    failedDongNames = ?,
                    sigunguDiffCount = ?,
                    sigunguErrorRate = ?
                WHERE job_id = ?
                  AND city = ?
                  AND division = ?
                """

        return bool(self.sqlite_driver.execute(
            query,
            (
                total_count,
                int(crawled_count or 0),
                str(true_false or ""),
                str(failed_dong_names or ""),
                diff_count,
                error_rate,
                self.job_id,
                str(sido or "").strip(),
                str(sigungu or "").strip(),
            ),
        ))

    def _get_stat_columns(self) -> List[str]:
        return [
            "city",
            "division",
            "sector",
            "totalCount",
            "crawledCount",
            "trueFalse",
            "sigunguTotalCount",
            "sigunguCrawledCount",
            "sigunguTrueFalse",
            "failedDongNames",
            "sigunguDiffCount",
            "sigunguErrorRate",
        ]

    def _get_stat_header_map(self) -> Dict[str, str]:
        return {
            "city": "시도",
            "division": "시군구",
            "sector": "읍면동",
            "totalCount": "읍면동 전체 수",
            "crawledCount": "읍면동 전체 크롤링 수",
            "trueFalse": "읍면동 T/F",
            "sigunguTotalCount": "시군구 전체 수",
            "sigunguCrawledCount": "시군구 전체 크롤링 수",
            "sigunguTrueFalse": "시군구 T/F",
            "failedDongNames": "실패 또는 스킵 읍면동",
            "sigunguDiffCount": "오차 갯수",
            "sigunguErrorRate": "오차 비율",
        }

    def _get_current_max_detail_id(self) -> int:
        if not self.sqlite_driver or not self.hist_id:
            return 0

        try:
            row = self.sqlite_driver.fetchone(
                f"SELECT COALESCE(MAX(detail_id), 0) AS max_id FROM {self.detail_table_name} WHERE hist_id = ?",
                (self.hist_id,),
            )
            return int(row["max_id"] or 0) if row else 0
        except Exception as e:
            self.log_signal_func(f"[시군구 검증] detail_id 조회 실패 : {e}")
            return 0

    def _find_sigungu_legal_division_number(self, sido: Any, sigungu: Any) -> str:
        sido_text = str(sido or "").strip()
        sigungu_text = str(sigungu or "").strip()

        for item in self.naver_loc_si_gun_gu or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("시도") or "").strip() != sido_text:
                continue
            if str(item.get("시군구") or "").strip() != sigungu_text:
                continue

            data = item.get("data") or {}
            legal_no = str(data.get("legalDivisionNumber") or "").strip()
            if legal_no:
                return legal_no

        return ""

    def _build_sigungu_cluster_payload(self, base_payload: Dict[str, Any], legal_division_number: str) -> Dict[str, Any]:
        # boundedArticles에서 실제 사용한 filter를 그대로 복사하고 지역 레벨만 GUN으로 교체한다.
        source_filter = (base_payload or {}).get("filter") or {}
        filter_payload = json.loads(json.dumps(source_filter, ensure_ascii=False))
        filter_payload["legalDivisionNumbers"] = [legal_division_number]
        filter_payload["legalDivisionType"] = "GUN"
        return {"filter": filter_payload}

    def _extract_legal_division_cluster_count(
            self,
            response_json: Dict[str, Any],
            legal_division_number: str,
    ) -> Optional[int]:
        if not isinstance(response_json, dict) or response_json.get("isSuccess") is False:
            return None

        result = response_json.get("result") or []
        if not isinstance(result, list):
            return None

        for row in result:
            if not isinstance(row, dict):
                continue
            if str(row.get("legalDivisionNumber") or "").strip() != legal_division_number:
                continue
            try:
                return int(row.get("count") or 0)
            except (TypeError, ValueError):
                return None

        return None

    def _fetch_sigungu_counts(
            self,
            sido: Any,
            sigungu: Any,
            base_payload: Dict[str, Any],
    ) -> tuple[Optional[int], Optional[int]]:
        legal_no = self._find_sigungu_legal_division_number(sido, sigungu)
        if not legal_no:
            self.log_signal_func(f"⚠️ [시군구 검증] 법정동 코드 없음 : {sido} {sigungu}")
            return None, None

        payload = self._build_sigungu_cluster_payload(base_payload, legal_no)

        article_count: Optional[int] = None
        complex_count: Optional[int] = None

        try:
            article_res = self._browser_fetch_json(
                url=self.sigungu_article_count_url,
                method="POST",
                payload=payload,
                wait_sec=60,
            )
            if article_res.get("status") == 200:
                article_count = self._extract_legal_division_cluster_count(
                    article_res.get("json") or {},
                    legal_no,
                    )

            self.log_signal_func(
                f"[시군구 매물수] {sido} {sigungu} / legalDivisionNumber={legal_no} / count={article_count}"
            )
        except Exception as e:
            self.log_signal_func(f"❌ [시군구 매물수] 조회 실패 : {sido} {sigungu} / {e}")

        # 단지수는 현재 DB에는 저장하지 않고 로그만 남긴다.
        try:
            complex_res = self._browser_fetch_json(
                url=self.sigungu_complex_count_url,
                method="POST",
                payload=payload,
                wait_sec=60,
            )
            if complex_res.get("status") == 200:
                complex_count = self._extract_legal_division_cluster_count(
                    complex_res.get("json") or {},
                    legal_no,
                    )

            self.log_signal_func(
                f"[시군구 단지수-로그만] {sido} {sigungu} / legalDivisionNumber={legal_no} / count={complex_count}"
            )
        except Exception as e:
            self.log_signal_func(f"❌ [시군구 단지수] 조회 실패 : {sido} {sigungu} / {e}")

        return article_count, complex_count

    def _get_sigungu_validation_state(
            self,
            state_map: Dict[str, Dict[str, Any]],
            sido: Any,
            sigungu: Any,
    ) -> Dict[str, Any]:
        key = f"{str(sido or '').strip()}|{str(sigungu or '').strip()}"
        if key not in state_map:
            state_map[key] = {
                "sido": str(sido or "").strip(),
                "sigungu": str(sigungu or "").strip(),
                "total_count": None,
                "crawled_count": 0,
                "failed_dongs": [],
                "detail_ranges": [],
                "api_attempts": 0,
            }
        return state_map[key]

    def _load_sigungu_total_if_needed(
            self,
            state: Dict[str, Any],
            base_payload: Dict[str, Any],
    ) -> None:
        if not self.sigungu_count_yn:
            return
        if state.get("total_count") is not None:
            return
        if not base_payload or not (base_payload.get("filter") or {}):
            return
        if int(state.get("api_attempts") or 0) >= 3:
            return

        state["api_attempts"] = int(state.get("api_attempts") or 0) + 1
        article_count, _complex_count = self._fetch_sigungu_counts(
            state.get("sido"),
            state.get("sigungu"),
            base_payload,
        )
        if article_count is not None:
            state["total_count"] = article_count

    def _append_failed_dong(self, state: Dict[str, Any], dong_name: Any) -> None:
        dong_text = str(dong_name or "").strip()
        if not dong_text:
            return
        failed_dongs = state.setdefault("failed_dongs", [])
        if dong_text not in failed_dongs:
            failed_dongs.append(dong_text)

    def _register_sigungu_dong_validation(
            self,
            state: Dict[str, Any],
            dong_name: Any,
            actual_count: int,
            true_false: str,
    ) -> None:
        state["crawled_count"] = int(state.get("crawled_count") or 0) + int(actual_count or 0)
        if true_false != "T":
            self._append_failed_dong(state, dong_name)

    def _update_sigungu_validation_range(
            self,
            start_detail_id: int,
            end_detail_id: int,
            total_count: Optional[int],
            crawled_count: int,
            true_false: str,
            failed_dong_names: str,
            diff_count: Optional[int],
            error_rate: Optional[float],
    ) -> bool:
        if not self.sqlite_driver or end_detail_id <= start_detail_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        query = f"""
                UPDATE {self.detail_table_name}
                SET
                    sigunguTotalCount = ?,
                    sigunguCrawledCount = ?,
                    sigunguTrueFalse = ?,
                    failedDongNames = ?,
                    sigunguDiffCount = ?,
                    sigunguErrorRate = ?,
                    updated_at = ?
                WHERE hist_id = ?
                  AND detail_id > ?
                  AND detail_id <= ?
                """

        return bool(self.sqlite_driver.execute(
            query,
            (
                total_count,
                crawled_count,
                true_false,
                failed_dong_names,
                diff_count,
                error_rate,
                now,
                self.hist_id,
                start_detail_id,
                end_detail_id,
            ),
        ))

    def _finalize_sigungu_validation_map(self, state_map: Dict[str, Dict[str, Any]]) -> None:
        if not self.sigungu_count_yn:
            return

        for state in state_map.values():
            total_count = state.get("total_count")
            crawled_count = int(state.get("crawled_count") or 0)
            failed_dong_names = ", ".join(state.get("failed_dongs") or [])

            if total_count is None:
                true_false = ""
                diff_count = None
                error_rate = None
            else:
                total_count = int(total_count)
                diff_count = abs(total_count - crawled_count)
                true_false = "T" if total_count == crawled_count else "F"
                if total_count > 0:
                    error_rate = round((diff_count / total_count) * 100, 2)
                else:
                    error_rate = 0.0 if crawled_count == 0 else 100.0

            for start_id, end_id in state.get("detail_ranges") or []:
                self._update_sigungu_validation_range(
                    start_detail_id=int(start_id),
                    end_detail_id=int(end_id),
                    total_count=total_count,
                    crawled_count=crawled_count,
                    true_false=true_false,
                    failed_dong_names=failed_dong_names,
                    diff_count=diff_count,
                    error_rate=error_rate,
                )

            # 기존 시군구 검증 계산 결과를 별도 통계 테이블에 반영한다.
            self._update_stat_sigungu(
                sido=state.get("sido"),
                sigungu=state.get("sigungu"),
                total_count=total_count,
                crawled_count=crawled_count,
                true_false=true_false,
                failed_dong_names=failed_dong_names,
                diff_count=diff_count,
                error_rate=error_rate,
            )

            error_rate_text = "" if error_rate is None else f"{error_rate:.2f}%"
            self.log_signal_func(
                f"[시군구 검증] {state.get('sido')} {state.get('sigungu')} "
                f"/ 시군구 전체 수={total_count} "
                f"/ 동 크롤링 수 합={crawled_count} "
                f"/ T/F={true_false} "
                f"/ 실패 읍면동={failed_dong_names or '-'} "
                f"/ 오차 갯수={diff_count} "
                f"/ 오차 비율={error_rate_text}"
            )

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
            sigungu_validation_map: Dict[str, Dict[str, Any]] = {}

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
                region_start_detail_id = self._get_current_max_detail_id() if self.sigungu_count_yn else 0

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

                # 로그와 실제 동작을 동일하게 맞춘다.
                # range(1, 5)는 1~4까지만 실행되므로 5회 재시도하려면 6을 사용해야 한다.
                for attempt in range(1, 6):

                    if not self.running:
                        return True

                    try:
                        self.log_signal_func(f"[지역 진입] 시도 {attempt}/5")

                        self.driver.get(url)
                        time.sleep(5)

                        self.log_signal_func("[후킹] 목록 후킹 설치 시작")
                        self._inject_list_hook()
                        time.sleep(2)
                        self.log_signal_func("[후킹] 목록 후킹 설치 끝")

                        try:
                            self._clear_list_hook()
                            self.log_signal_func("[후킹] 매물 클릭 전 hook 데이터 전체 초기화")
                        except Exception as e:
                            self.log_signal_func(f"[후킹] 전체 초기화 실패: {e}")

                        self.log_signal_func("[클릭] 매물 버튼 클릭 시도")
                        try:
                            # 목록을 열기 전에 버튼에 표시된 매물 수를 먼저 저장한다.
                            # 버튼 클릭 후에는 목록 패널 때문에 지도가 움직여 다른 범위의
                            # boundedArticles 요청이 추가로 발생할 수 있으므로 이 값이 기준이다.
                            expected_article_count: int = self._click_article_button(wait_sec=10)
                        except Exception as e:
                            self.log_signal_func(f"[목록] 매물 버튼 없음/클릭 실패 -> 다음 지역으로 이동 / {e}")
                            skip_current_region = True
                            success = True
                            break

                        time.sleep(8)

                        # 정렬 전, 먼저 초기 목록 응답 확보
                        # 클릭 후 수신된 여러 목록 응답 중에서 클릭 직전 버튼 수와
                        # totalCount가 같은 응답만 현재 지역의 정상 응답으로 사용한다.
                        initial_hook_data: dict[str, Any] = self._get_first_list_hook_data(
                            wait_sec=20,
                            expected_total_count=expected_article_count,
                            hook_stage="초기",
                        )
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
                        initial_list: list[dict[str, Any]] = first_result.get("list", []) or []
                        if not initial_list:
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
                            self._clear_list_hook()
                            self.log_signal_func("[후킹] 정렬 전 hook 데이터 전체 초기화")
                        except Exception as e:
                            self.log_signal_func(f"[후킹] 전체 초기화 실패: {e}")

                        try:
                            self.log_signal_func(f"[정렬] 정렬 클릭 시도 : {self.article_sort_type}")
                            self._click_sort_button_by_setting(wait_sec=5)
                            time.sleep(3)

                            # 정렬은 순서만 바꾸므로 전체 매물 수는 클릭 직전 값과 같아야 한다.
                            sorted_hook_data: dict[str, Any] = self._get_first_list_hook_data(
                                wait_sec=20,
                                expected_total_count=expected_article_count,
                                hook_stage="정렬",
                            )
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
                            f"/ 시도 {attempt}/5 / {e}"
                        )

                        if attempt < 5:
                            self.log_signal_func("[재시도] 화면 새로 로드 후 다시 시도")
                            time.sleep(2)
                        else:
                            self.log_signal_func("[재시도 실패] 5회 모두 실패하여 다음 지역으로 이동")

                if not success:
                    if self.sigungu_count_yn:
                        state = self._get_sigungu_validation_state(sigungu_validation_map, sido, sigungu)
                        self._append_failed_dong(state, eup_myeon_dong)
                    emit_region_progress()
                    continue

                if skip_current_region:
                    if self.sigungu_count_yn:
                        state = self._get_sigungu_validation_state(sigungu_validation_map, sido, sigungu)
                        self._load_sigungu_total_if_needed(state, base_payload)

                        if first_result:
                            skip_total_count = int(first_result.get("totalCount") or 0)
                            skip_true_false = "T" if skip_total_count == 0 else "F"
                            self._register_sigungu_dong_validation(
                                state,
                                eup_myeon_dong,
                                actual_count=0,
                                true_false=skip_true_false,
                            )
                        else:
                            self._append_failed_dong(state, eup_myeon_dong)

                    emit_region_progress()
                    time.sleep(random.uniform(1, 2))
                    continue

                items: list[dict[str, Any]] = self._collect_next_list_pages(
                    base_payload=base_payload,
                    first_result=first_result,
                )

                # 크롤링 시작 전 전체 갯수와 실제 수집한 갯수를 비교한다.
                total_count: int = int(first_result.get("totalCount") or 0)
                actual_count: int = len(items)
                true_false: str = "T" if total_count == actual_count else "F"

                for item in items:
                    item["_totalCount"] = total_count
                    item["_crawledCount"] = actual_count
                    item["_trueFalse"] = true_false

                sigungu_state = None
                if self.sigungu_count_yn:
                    sigungu_state = self._get_sigungu_validation_state(sigungu_validation_map, sido, sigungu)
                    self._load_sigungu_total_if_needed(sigungu_state, base_payload)
                    self._register_sigungu_dong_validation(
                        sigungu_state,
                        eup_myeon_dong,
                        actual_count=actual_count,
                        true_false=true_false,
                    )

                self.log_signal_func(
                    f"[목록 검증] 전체 갯수={total_count} "
                    f"/ 실제 크롤링 갯수={actual_count} "
                    f"/ 일치 여부={true_false}"
                )

                # 기존 검증 계산은 그대로 두고 결과만 별도 통계 테이블에 저장한다.
                self._upsert_stat_dong(
                    sido=sido,
                    sigungu=sigungu,
                    eup_myeon_dong=eup_myeon_dong,
                    total_count=total_count,
                    crawled_count=actual_count,
                    true_false=true_false,
                )

                if not items:
                    self.log_signal_func("[목록] 수집된 매물 없음 -> 저장 스킵")
                    emit_region_progress()
                    time.sleep(random.uniform(1, 2))
                    continue

                if self.detail_column_yn:
                    self._collect_detail(items, region_item)
                else:
                    # self._save_list_items(items, region_item)
                    self._save_list_items_multi(items, region_item)

                if self.sigungu_count_yn and sigungu_state is not None:
                    region_end_detail_id = self._get_current_max_detail_id()
                    if region_end_detail_id > region_start_detail_id:
                        sigungu_state.setdefault("detail_ranges", []).append(
                            (region_start_detail_id, region_end_detail_id)
                        )

                emit_region_progress()
                time.sleep(random.uniform(2, 4))

            self._finalize_sigungu_validation_map(sigungu_validation_map)

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

    def _read_article_button_count(self) -> dict[str, Any]:
        """
        매물 버튼을 클릭하기 직전에 화면에 실제로 보이는 매물 수를 읽는다.

        네이버의 숫자 애니메이션 DOM에는 각 자리마다 0~9가 전부 존재한다.
        단순 innerText/textContent를 사용하면 숨겨진 숫자까지 모두 합쳐지므로,
        aria-hidden="false"인 한 자리 숫자만 왼쪽부터 이어 붙여야 한다.

        예: 화면에 384가 보이는 경우 각 자리의 활성 요소는 3, 8, 4이고
        나머지 숫자는 aria-hidden="true" 상태다.
        """
        return self.driver.execute_script("""
            const target = document.querySelector(
                'button[data-nlogs-area="map.alist"]'
            );

            if (!target) {
                return {
                    ok: false,
                    reason: "button_not_found"
                };
            }

            const digitTexts = Array.from(
                target.querySelectorAll('span[aria-hidden="false"]')
            )
                .map((el) => (el.textContent || "").trim())
                .filter((text) => /^[0-9]$/.test(text));

            if (!digitTexts.length) {
                return {
                    ok: false,
                    reason: "visible_digit_not_found"
                };
            }

            const countText = digitTexts.join("");
            const count = Number(countText);

            if (!Number.isInteger(count) || count < 0) {
                return {
                    ok: false,
                    reason: "invalid_count",
                    countText: countText
                };
            }

            return {
                ok: true,
                count: count,
                countText: countText
            };
        """) or {}

    def _click_article_button(self, wait_sec: int = 5) -> int:
        """
        클릭 직전 매물 수를 확보한 뒤 매물 버튼을 클릭하고 그 수를 반환한다.

        반환한 값은 클릭 이후 발생하는 여러 boundedArticles 응답 중에서
        현재 지역의 정확한 응답을 선택하는 검증 기준으로 사용한다.
        """
        end = time.time() + wait_sec
        last_reason = ""
        last_logged_reason = ""

        while time.time() < end:
            try:
                # 숫자 애니메이션이 아직 끝나지 않았으면 다음 반복에서 다시 읽는다.
                count_result: dict[str, Any] = self._read_article_button_count()
                if not count_result.get("ok"):
                    last_reason = str(count_result.get("reason") or "count_not_ready")
                    # 같은 대기 사유가 반복되면 최초 한 번만 로그를 남긴다.
                    if last_reason != last_logged_reason:
                        self.log_signal_func(
                            f"[매물 버튼] 클릭 전 갯수 대기중 / reason={last_reason}"
                        )
                        last_logged_reason = last_reason
                    time.sleep(0.5)
                    continue

                before_click_count: int = int(count_result.get("count"))
                result = self.driver.execute_script(self.click_article_button_js) or {}

                if result.get("ok"):
                    self.log_signal_func(
                        f"[매물 버튼] 클릭 완료 / "
                        f"클릭 전 갯수={before_click_count} / "
                        f"타입={result.get('foundType', '')}"
                    )
                    return before_click_count

                last_reason = str(result.get("reason") or "")
                # 클릭 대상 탐색도 같은 사유는 최초 한 번만 출력한다.
                if last_reason != last_logged_reason:
                    self.log_signal_func(f"[매물 버튼] 대기중 / reason={last_reason}")
                    last_logged_reason = last_reason

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

    def _clear_list_hook(self) -> None:
        """
        다음 사용자 동작(매물 버튼/정렬 버튼)에서 발생한 요청만 수집하도록
        후킹 결과를 전부 초기화한다.

        __naverListHookData만 비우면 __naverListHookList에 이전 요청이 남아서
        지도 백그라운드 요청이나 정렬 전 응답을 다시 사용할 수 있다.
        """
        self.driver.execute_script("""
            window.__naverListHookData = null;
            window.__naverListHookList = [];
            window.__naverListHookUrls = [];
        """)


    def _get_first_list_hook_data(
            self,
            wait_sec: int = 20,
            expected_total_count: int | None = None,
            hook_stage: str = "목록",
    ) -> dict[str, Any]:
        """
        후킹된 boundedArticles 응답 중 현재 지역에 해당하는 응답을 반환한다.

        매물 버튼 클릭 후 목록 패널이 열리면서 지도가 움직이면 동일 API가
        여러 번 호출될 수 있다. 따라서 단순히 첫 응답이나 마지막 응답을
        선택하지 않고, 클릭 직전 버튼 수와 response.result.totalCount가
        일치하는 응답만 정상 응답으로 인정한다.
        """
        end = time.time() + wait_sec
        logged_candidates: set[tuple[int, int]] = set()

        while time.time() < end:
            # 중지 시 driver가 cleanup에서 None이 될 수 있으므로 즉시 후킹 대기를 끝낸다.
            if not self.running or self.driver is None:
                return {}

            try:
                hook_list = self.driver.execute_script(
                    "return window.__naverListHookList || [];"
                )

                if not hook_list:
                    time.sleep(0.5)
                    continue

                # 최근 완료 응답부터 검사하되 totalCount 검증을 반드시 수행한다.
                for hook_index in range(len(hook_list) - 1, -1, -1):
                    item = hook_list[hook_index]
                    response_json = item.get("responseJson") or {}
                    url = item.get("url", "")

                    if "/boundedArticles" not in url:
                        continue

                    # 개수 전용 API는 목록/페이징 payload가 없으므로 제외한다.
                    if "boundedArticlesCount" in url:
                        continue

                    result: dict[str, Any] = response_json.get("result", {}) or {}
                    try:
                        response_total_count: int = int(result.get("totalCount") or 0)
                    except (TypeError, ValueError):
                        continue

                    # 같은 후보 로그가 0.5초마다 반복되지 않도록 한 번만 출력한다.
                    candidate_key = (hook_index, response_total_count)
                    if candidate_key not in logged_candidates:
                        logged_candidates.add(candidate_key)
                        self.log_signal_func(
                            f"[HOOK CANDIDATE-{hook_stage}] "
                            f"index={hook_index + 1}/{len(hook_list)} "
                            f"total={response_total_count} "
                            f"expected={expected_total_count}"
                        )

                    if (
                            expected_total_count is not None
                            and response_total_count != expected_total_count
                    ):
                        continue

                    self.log_signal_func(
                        f"[HOOK SUCCESS-{hook_stage}] "
                        f"index={hook_index + 1}/{len(hook_list)} "
                        f"total={response_total_count} "
                        f"url={url}"
                    )
                    return item

            except Exception as e:
                self.log_signal_func(
                    f"[후킹] 데이터 조회 실패: {e}"
                )

            time.sleep(0.5)

        if not self.running or self.driver is None:
            return {}

        try:
            hook_info = self.driver.execute_script("""
            return {
                data: window.__naverListHookData,
                urls: window.__naverListHookUrls || [],
                listCount: (window.__naverListHookList || []).length
            };
            """)

            self.log_signal_func(
                f"[HOOK TIMEOUT-{hook_stage}] "
                f"expected={expected_total_count} / {hook_info}"
            )

        except Exception as e:
            self.log_signal_func(
                f"[HOOK TIMEOUT] hook_data 조회 실패: {e}"
            )

        return {}

    def _browser_fetch_json(self, url: str, method: str = "GET", payload: dict[str, Any] = None, params: dict[str, Any] = None, wait_sec: int = 30) -> dict[str, Any]:
        # 사용자 중지 후 Selenium driver 접근을 막아 NoneType/invalid session 오류를 방지한다.
        if not self.running or self.driver is None:
            return {
                "ok": False,
                "status": None,
                "json": {},
                "text": "",
                "stopped": True,
            }

        script = self.browser_fetch_json_js
        self.driver.set_script_timeout(wait_sec)
        return self.driver.execute_async_script(script, url, method, payload, params)

    def _collect_next_list_pages(self, base_payload: dict[str, Any], first_result: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        use_date_filter: bool = (
                not self.all_date_yn
                and bool(self.fr_date and self.to_date)
        )

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
            save_count = 0

            for info in items:
                rs = self._make_list_row(info, region_item)
                if self.insert_detail_row(rs):
                    save_count += 1

            if save_count == 0:
                self.log_signal_func("[DB저장] 저장된 데이터 없음")
                return

            self.log_signal_func(f"✅ [DB저장] 일반목록 저장 완료 | count={save_count}")

        except Exception as e:
            self.detail_fail_count += 1
            self.log_signal_func(f"[DB저장] 일반목록 저장 실패 / {e}")


    def _save_list_items_multi(self, items: list[dict[str, Any]], region_item) -> None:
        try:
            if not items:
                self.log_signal_func("[DB저장] 저장할 데이터 없음")
                return

            chunk_size = 20
            total_save_count = 0

            for i in range(0, len(items), chunk_size):
                chunk = items[i:i + chunk_size]

                # 1. 서버에서 주소 목록 받아오기
                api_results = self._fetch_addresses_from_server(chunk, region_item)

                # 🌟 2. 서버 응답을 'id(매물번호)'를 키로 가지는 딕셔너리로 변환 (검색 속도 O(1))
                api_res_map = {
                    res.get("id"): res
                    for res in api_results if isinstance(res, dict) and res.get("id")
                }

                rows_to_insert = []

                # 3. 매핑 작업 (ID 기반으로 정확하게 매칭)
                for info in chunk:
                    rs = self._make_list_row(info, region_item)
                    article_no = str(info.get("articleNumber", ""))

                    # 🌟 응답 맵에서 해당 매물번호의 결과를 가져옴
                    api_res = api_res_map.get(article_no)

                    # API 응답이 정상적으로 존재할 경우 주소 덮어쓰기
                    if api_res:
                        road_info = api_res.get("road_address") or {}
                        jibun_info = api_res.get("address") or {}

                        road_name = road_info.get("address_name", "")
                        jibun_name = jibun_info.get("address_name", "")

                        if road_name:
                            rs["도로명주소"] = road_name
                            rs["전체주소"] = road_name # 도로명 우선
                        if jibun_name:
                            rs["번지"] = jibun_name
                            # 도로명이 없으면 지번을 전체주소로 사용
                            if not road_name:
                                rs["전체주소"] = jibun_name

                    rows_to_insert.append(rs)

                # 4. 20개 데이터를 DB에 한 번에 Bulk Insert
                if self.bulk_insert_detail_rows(rows_to_insert):
                    total_save_count += len(rows_to_insert)

            if total_save_count == 0:
                self.log_signal_func("[DB저장] 저장된 데이터 없음")
                return

            self.log_signal_func(f"✅ [DB저장] 일반목록 벌크 저장 완료 | 누적 count={total_save_count}")

        except Exception as e:
            self.detail_fail_count += len(items)
            self.log_signal_func(f"❌ [DB저장] 일반목록 벌크 저장 실패 / {e}")

    def _fetch_addresses_from_server(self, items_chunk: list[dict[str, Any]], region_item) -> list[dict[str, Any]]:
        """
        20개 단위의 배열을 서버로 보내서 지번/도로명 주소를 받아오는 함수
        """
        # SERVER_URL = "http://localhost:5001/geocode/reverse-batch"
        SERVER_URL = "http://220.94.196.191:5001/geocode/reverse-batch"
        MASTER_API_KEY = "my_secret_master_key_1234!"

        payload = []
        for info in items_chunk:
            article_no = str(info.get("articleNumber", ""))  # 🌟 매물번호 추출
            list_address = info.get("address", {}) or {}
            list_coords = list_address.get("coordinates", {}) or {}

            try:
                lat = float(list_coords.get("yCoordinate") or 0.0)
                lng = float(list_coords.get("xCoordinate") or 0.0)
            except ValueError:
                lat, lng = 0.0, 0.0

            payload.append({
                "id": article_no,  # 🌟 고유 ID로 매물번호를 담아서 보냄
                "lat": lat,
                "lng": lng,
                "sido": region_item.get("시도", ""),
                "sigungu": region_item.get("시군구", ""),
                "eupmyeondong": region_item.get("읍면동", "")
            })

        headers = {
            "X-API-KEY": MASTER_API_KEY,
            "Content-Type": "application/json"
        }

        try:
            # 🌟 수정: response 객체가 리스트(list) 자체일 확률이 높음
            response = self.api_client.post(url=SERVER_URL, headers=headers, json=payload, timeout=60)

            # 1. response가 list라면 성공으로 간주
            if isinstance(response, list):
                return response

            # 2. 만약 response가 특정 객체(응답랩퍼)라면 여기서 status 체크를 해야 함
            # 하지만 현재 에러로 보아 response가 list이므로, 위 1번 조건에서 바로 통과될 거야.

            self.log_signal_func(f"⚠️ [API 서버 응답 오류] 리스트 형식이 아님: {type(response)}")
            return []

        except Exception as e:
            self.log_signal_func(f"❌ [API 서버 통신 실패] {e}")
            return []


    def _append_save_row(self, rs):
        try:
            self.insert_detail_row(rs)
        except Exception as e:
            self.detail_fail_count += 1
            self.log_signal_func(f"[DB저장] 단건 저장 실패 / {e}")

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
            "매물명": articleName,
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

            # 읍면동 단위 검증 정보
            "읍면동 전체 수": list_item.get("_totalCount", ""),
            "읍면동 전체 크롤링 수": list_item.get("_crawledCount", ""),
            "읍면동 T/F": list_item.get("_trueFalse", ""),
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
        rs["매물명"] = articleName

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
