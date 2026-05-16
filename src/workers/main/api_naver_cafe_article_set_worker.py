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


class ApiNaverCafeArticleSetWorker(BaseApiWorker):

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.setting: Any = setting

        self.site_name: str = "네이버 카페 게시글"
        self.worker_name: str = "naver_cafe_article"

        self.running: bool = True
        self.before_pro_value: float = 0.0

        # UI 셋팅값
        self.url: str = ""
        self.fr_date: str = ""
        self.to_date: str = ""
        self.detail_yn: bool = False
        self.auto_save_yn: bool = False

        self.cafe_id: str = ""
        self.menu_id: str = ""

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
        self.detail_table_name: str = "naver_cafe_article"
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
            self.url = str(self.get_setting_value(self.setting, "url") or "").strip()
            self.fr_date = str(self.get_setting_value(self.setting, "fr_date") or "").replace("-", "").strip()
            self.to_date = str(self.get_setting_value(self.setting, "to_date") or "").replace("-", "").strip()
            self.detail_yn = bool(self.get_setting_value(self.setting, "detail_yn"))
            self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))

            self.log_signal_func(f"기간 : {self.fr_date} ~ {self.to_date}")
            self.log_signal_func(f"상세보기 여부 : {self.detail_yn}")
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
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

    def main(self) -> bool:
        try:
            self.log_signal_func("크롤링 시작")

            # URL 파싱 (cafeId, menuId 추출)
            # https://m.cafe.naver.com/ca-fe/web/cafes/28669646/menus/26
            m = re.search(r"cafes/(\d+)/menus/(\d+)", self.url)
            if not m:
                self.log_signal_func("❌ URL에서 cafeId와 menuId를 추출할 수 없습니다.")
                self.finish_job("FAIL", "URL 형식 오류")
                return False

            self.cafe_id = m.group(1)
            self.menu_id = m.group(2)

            page = 1
            is_finished = False

            while self.running and not self._stop_event.is_set() and not is_finished:
                # time.sleep(1)

                # 1. 목록 조회
                list_url = (f"https://apis.naver.com/cafe-web/cafe2/ArticleListV3dot1.json?"
                            f"search.clubid={self.cafe_id}&search.queryType=lastArticle&"
                            f"search.menuid={self.menu_id}&search.page={page}&search.perPage=50")

                headers = {
                    "accept": "application/json, text/plain, */*",
                    "referer": self.url,
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
                }

                res_json = self.api_client.get(list_url, headers=headers)
                if not res_json:
                    self.log_signal_func("❌ API 응답이 없습니다. 중단합니다.")
                    break

                result = res_json.get("message", {}).get("result", {})
                article_list = result.get("articleList", [])
                has_next = result.get("hasNext", False)

                if not article_list:
                    break

                self.log_signal_func(f"[{page} 페이지] 탐색 중...")

                for item in article_list:
                    if not self.running or self._stop_event.is_set():
                        break

                    # 날짜 변환
                    ts = item.get("writeDateTimestamp", 0)
                    if ts == 0:
                        continue

                    dt = datetime.fromtimestamp(ts / 1000.0)
                    write_date = dt.strftime("%Y%m%d")
                    write_date_time = dt.strftime("%Y.%m.%d %H:%M:%S")

                    # 날짜 비교 로직
                    if write_date > self.to_date:
                        continue # 지정 기간보다 미래 글이면 스킵 (보통 상단 고정 공지사항 등)

                    if write_date < self.fr_date:
                        # 지정 기간보다 과거로 넘어가면 전체 반복문 종료
                        is_finished = True
                        break

                    # 데이터 맵핑
                    article_id = str(item.get("articleId", ""))
                    rs: Dict[str, Any] = {
                        "글번호": article_id,
                        "카페ID": str(item.get("cafeId", "")),
                        "메뉴ID": str(item.get("menuId", "")),
                        "메뉴명": item.get("menuName", ""),
                        "제목": item.get("subject", ""),
                        "작성자": item.get("writerNickname", ""),
                        "타임스탬프": str(ts),
                        "작성일(YMD)": write_date,
                        "작성일시": write_date_time,
                        "조회수": str(item.get("readCount", "0")),
                        "댓글수": str(item.get("commentCount", "0")),
                        "좋아요수": str(item.get("likeItCount", "0")),
                        "본문내용": ""
                    }

                    # 2. 상세보기 조회 (detail_yn 옵션 켜져있을 경우)
                    if self.detail_yn and article_id:
                        # time.sleep(1) # API 부하 방지
                        detail_url = f"https://article.cafe.naver.com/gw/v4/cafes/{self.cafe_id}/articles/{article_id}?fromList=true&menuId={self.menu_id}"
                        try:
                            detail_json = self.api_client.get(detail_url, headers=headers)
                            content_html = detail_json.get("result", {}).get("article", {}).get("contentHtml", "")

                            if content_html:
                                # BeautifulSoup으로 html 태그 걷어내고 텍스트만 추출
                                soup = BeautifulSoup(content_html, "html.parser")
                                clean_text = soup.get_text(separator="\n", strip=True)
                                rs["본문내용"] = clean_text
                        except Exception as e:
                            self.log_signal_func(f"⚠️ 게시글 {article_id} 상세보기 실패: {e}")

                    # DB 적재
                    self.insert_detail_row(rs)
                
                page += 1
                self.log_signal_func(f"[{page} 페이지] 완료")
                
                if not has_next:
                    is_finished = True

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