import json
import os
import re
import time
import threading
from collections import defaultdict
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverCafeCountOnlySetWorker(BaseApiWorker):

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.setting: Any = setting

        self.base_main_url: str = "https://cafe.naver.com/"
        self.site_name: str = "네이버 카페 조회수"

        self.running: bool = True
        self.before_pro_value: float = 0.0

        # 병렬 처리 설정
        self.max_workers: int = 5
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()

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
        self.worker_name: str = "naver_cafe_ctt_cnt_only"
        self.detail_table_name: str = "naver_cafe_ctt_cnt_only"
        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0
        self.auto_save_yn: bool = False

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

            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))
            self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")

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
        self.log_signal_func("드라이버 세팅 ========================================")
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)

    def _extract_inputs(self) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for row in self.excel_data_list:
            lower_map = {k.lower(): k for k in row.keys()}
            url_key = lower_map.get("url")
            file_key = lower_map.get("file")

            url_val = str(row[url_key]).strip() if (url_key and row.get(url_key)) else ""
            if not url_val:
                continue
            file_val = str(row[file_key]).strip() if (file_key and row.get(file_key)) else "__unknown__"
            pairs.append((url_val, file_val))
        return pairs

    def main(self) -> bool:
        try:
            self.log_signal_func("크롤링 시작")

            url_file_pairs = self._extract_inputs()
            total = len(url_file_pairs)
            if total == 0:
                self.log_signal_func("처리할 URL이 없습니다.")
                self.finish_job("SUCCESS")
                return True

            self._executor = ThreadPoolExecutor(max_workers=min(self.max_workers, total))
            futures = {}

            for url, file_tag in url_file_pairs:
                if not self.running or self._stop_event.is_set():
                    break
                fut = self._executor.submit(self._fetch_once, url, file_tag)
                futures[fut] = (url, file_tag)

            done_count = 0
            for fut in as_completed(futures):
                url, file_tag = futures[fut]
                if not self.running or self._stop_event.is_set():
                    break

                try:
                    obj = fut.result()
                except Exception as e:
                    obj = {"URL": url, "조회수": f"요청 실패: {e}", "파일명": file_tag}

                with self._lock:
                    # 메인 스레드에서 DB INSERT (SQLite Threading Issue 방지)
                    self.insert_detail_row(obj)
                    done_count += 1
                    self.log_signal_func(f"전체 ({done_count}/{total}) : {url}")

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

    def _fetch_once(self, url: str, file_tag: str) -> Dict[str, Any]:
        """
        한 URL에 대해 API 호출 1회만 수행
        리턴값은 config.json 의 'value'(한글)에 맞춘 Dict
        """
        if not self.running or self._stop_event.is_set():
            return {"URL": url, "조회수": "중단됨", "파일명": file_tag}

        api_client = APIClient(use_cache=False)

        m = re.search(r"cafe\.naver\.com/([^/]+)/(\d+)", url)
        if not m:
            return {"URL": url, "조회수": "URL 형식 오류", "파일명": file_tag}
        cafe_id, article_id = m.group(1), m.group(2)

        api_url = f"https://article.cafe.naver.com/gw/v3/cafes/{cafe_id}/articles/{article_id}?useCafeId=false"
        headers = {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            ),
            "referer": f"https://m.cafe.naver.com/ca-fe/web/cafes/{cafe_id}/articles/{article_id}?useCafeId=false&tc",
        }

        try:
            json_data = api_client.get(api_url, headers=headers)
            count = json_data.get("result", {}).get("article", {}).get("readCount")
            if count is None:
                return {"URL": url, "조회수": "글이 삭제되었습니다", "파일명": file_tag}
            return {"URL": url, "조회수": str(count), "파일명": file_tag}
        except Exception as e:
            return {"URL": url, "조회수": "글이 삭제되었습니다", "파일명": file_tag}


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

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

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
        """기존 방식대로 파일명(file_tag) 기준으로 그룹화하여 각각 별개의 엑셀 파일로 저장하도록 오버라이딩"""
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not self.excel_driver or not sqlite_driver or not self.hist_id or not self.db_columns:
            return False

        select_text = ",\n                    ".join(self.db_columns)
        query = f"SELECT {select_text} FROM {self.detail_table_name} WHERE hist_id = ? ORDER BY detail_id"

        row_list = sqlite_driver.fetchall(query, (self.hist_id,))
        if not row_list:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        # file_tag별로 그룹핑
        grouped = defaultdict(list)
        for row in row_list:
            grouped[str(dict(row).get("file_tag", "__unknown__"))].append(dict(row))

        ts = time.strftime("%Y%m%d_%H%M%S")

        # '파일명' 컬럼은 결과 엑셀에서 생략
        final_excel_columns = [col for col in self.columns if col != "파일명"]

        for file_tag, rows in grouped.items():
            excel_row_list = self.db_rows_to_kor_rows(rows)

            # 최종 엑셀에서는 '파일명' 필드 제거
            for r in excel_row_list:
                r.pop("파일명", None)

            safe_file_tag = re.sub(r"[^\w\.-]+", "_", file_tag)
            excel_filename = f"{self.site_name}__{safe_file_tag}__{ts}.xlsx"

            self.excel_driver.save_db_rows_to_excel(
                excel_filename=excel_filename,
                row_list=excel_row_list,
                columns=final_excel_columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )
        return True

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
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None
        except: pass

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
        except: pass

        self.file_driver, self.excel_driver = None, None
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