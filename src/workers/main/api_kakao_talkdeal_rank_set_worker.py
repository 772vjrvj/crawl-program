import json
import os
import re
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker
import urllib3

# HTTPS 인증서 검증 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ApiKaKaoTalkdealRankSetWorker(BaseApiWorker):

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        self.current_cnt = None
        self.total_cnt = None
        self._stop_event = threading.Event()
        self.setting: Any = setting

        self.site_name: str = "카카오톡 톡딜 랭킹"
        self.worker_name: str = "kakao_talkdeal_rank"

        self.running: bool = True
        self.before_pro_value: float = 0.0

        # UI 셋팅값
        self.detail_yn: bool = False
        self.auto_save_yn: bool = False

        # 상태값 / 드라이버
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
        self.api_client: Optional[APIClient] = None

        self.init_flag: bool = False
        self._cleaned_up: bool = False

        self.folder_path: str = ""
        self.out_dir: str = "output"

        # DB 저장용 공통 상태
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None
        self.detail_table_name: str = "KAKAO_TALKDEAL_RANK"
        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0

        # config columns
        self.config_data: Dict[str, Any] = {}
        self.column_defs: List[Dict[str, Any]] = []
        self.db_columns: List[str] = []
        self.excel_columns: List[str] = []
        self.code_value_map: Dict[str, str] = {}

    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화 실행 완료")
                return True

            # 셋팅값 추출
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))
            self.log_signal_func(f"저장경로 : {self.folder_path}")
            self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")
            
            # 컬럼세팅
            if not self.load_runtime_config_columns():
                return False

            self.driver_set()

            if not self.db_set():
                return False

            self.log_signal_func("✅ init 완료")
            self.init_flag = True
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)


    def main(self) -> bool:
        try:
            self.log_signal_func("크롤링 시작")

            sections = self.get_sections()
            if not sections:
                self.log_signal_func("setting_detail에 section이 없습니다.")
                return True

            result_list = []

            for sec in sections:
                if self._stop_event.is_set() or not self.running:
                    self.log_signal_func("⛔ 중지 감지 (섹션) → 저장 후 종료")
                    return True

                sec_id = sec.get("id")
                sec_title = (sec.get("title") or sec_id or "").replace("\n", "").strip()
                self.log_signal_func(f"[섹션] {sec_title}")

                for it in self.get_items(sec_id):
                    if self._stop_event.is_set() or not self.running:
                        self.log_signal_func("⛔ 중지 감지 (카테고리) → 저장 후 종료")
                        return True

                    if not it.get("checked", True):
                        continue

                    code = it.get("code")
                    value = it.get("value")
                    self.log_signal_func(f"\n==================================================")
                    self.log_signal_func(f">> [{value}({code})] 카테고리 수집 시작 (최대 100개 제한)")
                    self.log_signal_func(f"==================================================")

                    # --- 톡딜 랭킹 수집 로직 시작 ---
                    base_url = "https://store.kakao.com/a/f-s/ranking/product-sale-ranking"

                    headers = {
                        "accept": "application/json, text/plain, */*",
                        "accept-encoding": "gzip, deflate, br, zstd",
                        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                        "cache-control": "no-cache",
                        "content-type": "application/json",
                        "pragma": "no-cache",
                        "priority": "u=1, i",
                        "referer": "https://store.kakao.com/home/best?__ld__=&oldRef=https:%2F%2Fwww.google.com%2F&tab=contProduct&groupId=6&period=HOURLY",
                        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "empty",
                        "sec-fetch-mode": "cors",
                        "sec-fetch-site": "same-origin",
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                        "x-shopping-referrer": "https://store.kakao.com/home/best?__ld__=&oldRef=https:%2F%2Fwww.google.com%2F&tab=contProduct&groupId=4&period=HOURLY",
                    }

                    page = 0
                    previous_page_id_list = []

                    while True:
                        # 루프 도중에도 프로그램 중단 요청이 오면 즉시 빠져나감
                        if self._stop_event.is_set() or not self.running:
                            self.log_signal_func("⛔ 중지 감지 (페이징) → 종료")
                            return True

                        # size=20 기준 page=5(6번째 요청)가 되는 순간 101개째이므로 루프 종료
                        if page >= 5:
                            self.log_signal_func(f"  -> ⏹️ [목표 달성] 100개 수집 완료 (카테고리: {code})")
                            break

                        timestamp = int(time.time() * 1000)
                        params = {
                            "page": page,
                            "rankingTabType": "contProduct",
                            "categoryType": code,
                            "periodType": "HOURLY",
                            "size": 20,
                            "displayPlaceType": "RANKING_TAB",
                            "_": timestamp
                        }

                        try:
                            # API 호출 (api_client 활용)
                            response = self.api_client.get(base_url, headers=headers, params=params)

                            if not response.get("result"):
                                self.log_signal_func(f"[{code} | P.{page}] ⚠️ API 응답 'result'가 false입니다.")
                                break

                            data_node = response.get("data", {})
                            products = data_node.get("products", [])
                            is_last = data_node.get("last", False)
                            current_count = len(products)

                            self.log_signal_func(f"[{code} | P.{page}] 응답 상품 수: {current_count}개 | last 여부: {is_last}")

                            if current_count == 0:
                                self.log_signal_func(f"  -> ⏹️ [종료] 상품 데이터가 없습니다.")
                                break

                            # 현재 페이지 상품 ID 추출
                            current_page_id_list = [prod.get("productId") for prod in products if prod.get("productId")]

                            # 직전 데이터와 중복 시 방어 로직
                            if current_page_id_list == previous_page_id_list:
                                self.log_signal_func(f"  -> ⏹️ [종료] 데이터가 직전 페이지와 중복됩니다.")
                                break
                            previous_page_id_list = current_page_id_list

                            # 데이터 추출 및 DB 적재 (상세보기 작업 전)
                            for rank_index, prod in enumerate(products, start=1 + (page * 20)):
                                out = {
                                    "categoryType": value,
                                    "ranking": str(rank_index),
                                    "productId": str(prod.get("productId", "")),
                                    "productName": str(prod.get("productName", "")),
                                    "storeDomain": str(prod.get("storeDomain", ""))
                                }

                                result_list.append(out)

                            if is_last is True:
                                self.log_signal_func(f"  -> ⏹️ [종료] API 응답에서 last=true 임을 확인했습니다.")
                                break

                            page += 1
                            time.sleep(0.3)  # 디도스 방지를 위한 딜레이

                        except Exception as e:
                            self.log_signal_func(f"[{code} | P.{page}] 💥 예외 오류 발생: {e}")
                            break

            # =========================================================
            # 2단계: 수집된 result_list를 함수로 넘겨 상세정보 처리
            # =========================================================
            if result_list:
                self.process_details(result_list)
            else:
                self.log_signal_func("⚠️ 수집된 목록 데이터가 없습니다.")

            if self.hist_status == "RUNNING":
                if self.running:
                    self.finish_job("SUCCESS")
                else:
                    self.finish_job("STOP", "사용자 중단")

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 전체 실행 중 예외 발생: {e}")
            self.finish_job("FAIL", str(e))
            return False

    
    def process_details(self, result_list: List[Dict[str, Any]]) -> None:
        """
        1차로 수집된 목록(result_list)을 순회하며 스토어 상세 정보를 가져오고 DB에 적재합니다.
        """
        self.log_signal_func(f"\n🚀 목록 수집 완료. 총 {len(result_list)}건의 상세 정보 조회를 시작합니다.")
    
        self.total_cnt = len(result_list)
        self.current_cnt = 0  # 프로그레스바 카운트 초기화
    
        # 상세 조회용 기본 헤더
        detail_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        }
    
        for rs in result_list:
            if self._stop_event.is_set() or not self.running:
                self.log_signal_func("⛔ 중지 감지 (상세수집) → 중단")
                break
    
            domain = rs.get("storeDomain")

            # 도메인이 있는 경우에만 상세 API 호출
            if domain:
                profile_url = f"https://store.kakao.com/a/brandstore/{domain}/profile"
                detail_headers["referer"] = f"https://store.kakao.com/{domain}/profile"
                detail_headers["x-shopping-referrer"] = f"https://store.kakao.com/{domain}"
                params = {"_": int(time.time() * 1000)}

                try:
                    profile_res = self.api_client.get(profile_url, headers=detail_headers, params=params)

                    # API 응답에서 store_info 추출 (없거나 에러 시 빈 딕셔너리)
                    store_info = {}
                    if profile_res and profile_res.get("result"):
                        store_info = profile_res.get("data", {}).get("store", {})

                    # 💡 요청하신 형태의 obj 딕셔너리 생성
                    obj = {
                        '상품명': rs.get('productName', ''),
                        '사업자번호': store_info.get('businessRegistrationNumber', ''),
                        '메일 주소': store_info.get('mainEmail', ''),
                        '구분': rs.get('categoryType', '')
                    }

                    # 완성된 obj를 DB에 인서트
                    self.insert_detail_row(obj)

                    # 로그 출력용
                    biz_num = obj['사업자번호'] or "없음"
                    email = obj['메일 주소'] or "없음"
                    self.log_signal_func(f"[{self.current_cnt + 1}/{self.total_cnt}] ✅ [사업자: {biz_num} | 메일: {email} | 상품: {obj['상품명']}]")

                except Exception as e:
                    self.log_signal_func(f"[{self.current_cnt + 1}/{self.total_cnt}] 💥 상세 조회 예외 발생: {e}")

            # 카운트 증가
            self.current_cnt += 1

            # 💡 100개 단위이거나, 마지막 항목일 때만 프로그레스바 업데이트
            if self.current_cnt % 100 == 0 or self.current_cnt == self.total_cnt:
                pro_value = int((self.current_cnt / self.total_cnt) * 1000000) if self.total_cnt > 0 else 0
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value

            # API 차단 방지를 위한 딜레이
            time.sleep(0.3)


    def get_sections(self) -> List[Dict[str, Any]]:
        return [r for r in (self.setting_detail or []) if r.get("row_type") == "section"]

    def get_items(self, parent_id: Any) -> List[Dict[str, Any]]:
        rows = self.setting_detail or []
        return [r for r in rows if r.get("row_type") == "item" and r.get("parent_id") == parent_id]




    # =========================================================
    # DB / Excel 공통 모듈 파트
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)
        db_path = self.get_runtime_db_path()

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        if not self.insert_hist_start():
            return False

        return True

    def insert_hist_start(self) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id, table_name, site_name, worker_name, user_id,
                    start_at, status, total_count, success_count, fail_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        params = (
            self.job_id, self.detail_table_name, self.site_name, self.worker_name,
            getattr(self.user, "user_id", None) if self.user else None,
            now, "RUNNING", 0, 0, 0, now, now,
        )

        if not self.sqlite_driver.execute(query, params):
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None
        return True

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not sqlite_driver or not self.hist_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        query = """
                UPDATE worker_job_hist
                SET end_at = ?, status = ?, total_count = ?, success_count = ?, fail_count = ?,
                    error_message = ?, updated_at = ?
                WHERE hist_id = ?
                """
        params = (
            now, self.hist_status, self.detail_success_count + self.detail_fail_count,
            self.detail_success_count, self.detail_fail_count, self.hist_error_message, now, self.hist_id,
        )
        return sqlite_driver.execute(query, params)

    def insert_detail_row(self, rs: Dict[str, Any]) -> bool:
        if not self.sqlite_driver or not self.db_columns:
            self.detail_fail_count += 1
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        db_rs = self.map_out_to_db(rs)

        base_columns = ["hist_id", "site_name", "worker_name", "table_name", "job_id", "user_id", "row_status"]
        all_columns = base_columns + self.db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(all_columns)

        query = f"INSERT INTO {self.detail_table_name} ({column_text}) VALUES ({placeholders})"
        params = (
            self.hist_id, self.site_name, self.worker_name, self.detail_table_name, self.job_id,
            getattr(self.user, "user_id", None) if self.user else None, "SUCCESS",
            *[db_rs.get(col, "") for col in self.db_columns], now, now,
        )

        ok = self.sqlite_driver.execute(query, params)
        if ok:
            self.detail_success_count += 1
        else:
            self.detail_fail_count += 1
        return ok

    def get_runtime_config_path(self) -> str:
        candidates = [
            os.path.join(self.get_resource_root(), "runtime", "customers", self.worker_name, "config.json"),
            os.path.join(self.get_project_root(), "runtime", "customers", self.worker_name, "config.json"),
        ]
        for path in candidates:
            if os.path.exists(path): return path
        return candidates[0]

    def load_runtime_config_columns(self) -> bool:
        config_path = self.get_runtime_config_path()
        if not os.path.exists(config_path): return False

        with open(config_path, "r", encoding="utf-8") as f:
            self.config_data = json.load(f)

        columns = self.config_data.get("columns") or []
        self.column_defs = [c for c in columns if str(c.get("code")).strip() and str(c.get("value")).strip()]
        self.db_columns = [str(c.get("code")).strip() for c in self.column_defs]
        self.excel_columns = [str(c.get("value")).strip() for c in self.column_defs if bool(c.get("checked", False))]
        self.code_value_map = {str(c.get("code")).strip(): str(c.get("value")).strip() for c in self.column_defs}
        self.columns = self.excel_columns
        return True

    def map_out_to_db(self, out: Dict[str, Any]) -> Dict[str, Any]:
        return {code: str(out.get(value) or "") for code, value in self.code_value_map.items()}

    def db_rows_to_kor_rows(self, row_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for row in row_list or []:
            out = {}
            for col in self.column_defs:
                if not bool(col.get("checked", False)): continue
                code, value = str(col.get("code")).strip(), str(col.get("value")).strip()
                out[value] = row.get(code, "")
            result.append(out)
        return result

    def export_detail_to_excel(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not self.excel_driver or not sqlite_driver or not self.hist_id or not self.db_columns:
            return False

        select_text = ",\n                    ".join(self.db_columns)
        query = f"SELECT {select_text} FROM {self.detail_table_name} WHERE hist_id = ? ORDER BY detail_id"

        row_list = sqlite_driver.fetchall(query, (self.hist_id,))
        if not row_list:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        excel_row_list = self.db_rows_to_kor_rows([dict(row) for row in row_list])
        excel_filename = f"{self.site_name}_{self.job_id}.xlsx"

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=excel_filename,
            row_list=excel_row_list,
            columns=self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def finalize_db_and_excel(self) -> None:
        temp_sqlite_driver = None
        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            if temp_sqlite_driver.connect(self.get_runtime_db_path()):
                self.update_hist_end(temp_sqlite_driver)
                if self.auto_save_yn:
                    self.export_detail_to_excel(temp_sqlite_driver)
        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")
        finally:
            if temp_sqlite_driver: temp_sqlite_driver.close()

    # =========================================================
    # 종료 / 정리
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        try:
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
        except: pass
        finally:
            self.sqlite_driver = None

        self.finalize_db_and_excel()

        try:
            if self.file_driver: self.file_driver.close()
            if self.excel_driver: self.excel_driver.close()
            if self.api_client: self.api_client.close()
        except: pass

        self.file_driver, self.excel_driver, self.api_client = None, None, None
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()

        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        time.sleep(1)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()