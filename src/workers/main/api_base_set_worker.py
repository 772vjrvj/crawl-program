# src/workers/main/api_base_set_worker.py
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.repositories.worker_db_repository import WorkerDbRepository
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiBaseSetWorker(BaseApiWorker):
    """
    신규 Worker 작성용 기본 샘플.

    복사 후 아래 항목만 Worker에 맞게 변경한다.
    - 클래스명
    - site_name
    - worker_name
    - detail_table_name
    - init()의 설정값
    - main()의 비즈니스 로직

    수집 결과 dict의 key는 config.json의 columns[].code를 사용한다.
    DB 연결, 작업 이력, 건수 집계, detail 저장 및 엑셀 변환은
    WorkerDbRepository가 담당한다.
    """

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        if setting is not None:
            self.setting = setting

        self._stop_event = threading.Event()

        # 복사 후 필수 변경
        self.site_name: str = "샘플 사이트"
        self.worker_name: str = "sample_worker"
        self.detail_table_name: str = "sample_worker"

        # detail 저장 로그에 표시할 대표 컬럼
        # 예: ("id", "name")
        self.detail_log_fields: Tuple[str, ...] = ()

        # 실행 상태
        self.running: bool = True
        self.before_pro_value: float = 0.0
        self.init_flag: bool = False
        self._cleaned_up: bool = False

        # UI 설정값
        self.detail_yn: bool = False
        self.auto_save_yn: bool = False
        self.folder_path: str = ""
        self.out_dir: str = "output"

        # 드라이버
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        # DB Repository
        self.db_repository: Optional[WorkerDbRepository] = None

        # checked=true인 엑셀 한글 컬럼명
        self.columns: List[str] = []

    # =========================================================
    # 초기화
    # =========================================================
    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화가 완료되었습니다.")
                return True

            self.folder_path = str(
                self.get_setting_value(self.setting, "folder_path") or ""
            ).strip()
            self.auto_save_yn = bool(
                self.get_setting_value(self.setting, "auto_save_yn")
            )

            self.log_signal_func(f"저장경로 : {self.folder_path}")
            self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")

            # Worker별 설정값은 이 위치에서 추가한다.
            # self.keyword = str(
            #     self.get_setting_value(self.setting, "keyword") or ""
            # ).strip()

            self.driver_set()

            if not self.db_set():
                return False

            self.init_flag = True
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(
            use_cache=False,
            log_func=self.log_signal_func,
        )

    # =========================================================
    # 비즈니스 로직
    # =========================================================
    def main(self) -> bool:
        try:
            self.log_signal_func("작업 시작")

            # =================================================
            # Worker별 비즈니스 로직 작성 영역
            # =================================================
            # 성공 저장 예시
            # row_start_at = self._now_db()
            # result = {
            #     "id": "123",          # config columns[].code
            #     "name": "샘플 데이터",
            # }
            # self.insert_detail_row(
            #     result,
            #     row_status="SUCCESS",
            #     row_start_at=row_start_at,
            #     row_end_at=self._now_db(),
            # )
            #
            # 실패 행 저장 예시
            # self.insert_detail_row(
            #     {"id": "123", "name": ""},
            #     row_status="FAIL",
            #     row_error_message="상세 조회 실패",
            #     row_start_at=row_start_at,
            #     row_end_at=self._now_db(),
            # )

            if self.db_repository and self.db_repository.status == "RUNNING":
                if self.running:
                    self.finish_job("SUCCESS")
                else:
                    self.finish_job("STOP", "사용자 중단")

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            error_message = str(e)
            self.log_signal_func(f"❌ 전체 실행 중 예외 발생: {error_message}")
            self.finish_job("FAIL", error_message)
            return False

    # =========================================================
    # DB Repository
    # =========================================================
    def db_set(self) -> bool:
        config_data = self.read_runtime_customer_config(
            customer_name=self.worker_name
        )
        column_defs = config_data.get("columns") or []

        if not isinstance(column_defs, list) or not column_defs:
            self.log_signal_func(
                "❌ [config] columns가 없거나 형식이 올바르지 않습니다."
            )
            return False

        try:
            user = getattr(self, "user", None)
            user_id = getattr(user, "user_id", user)

            self.db_repository = WorkerDbRepository(
                db_path=self.get_runtime_db_path(),
                site_name=self.site_name,
                worker_name=self.worker_name,
                detail_table_name=self.detail_table_name,
                column_defs=column_defs,
                user_id=user_id,
                log_func=self.log_signal_func,
                detail_log_fields=self.detail_log_fields,
            )
        except Exception as e:
            self.log_signal_func(f"❌ [DB] Repository 생성 실패: {e}")
            return False

        schema_files = [
            os.path.join(
                "resources", "customers", "common", "db", "schema_hist.sql"
            ),
            os.path.join(
                "resources",
                "customers",
                self.worker_name,
                "db",
                "schema_detail.sql",
            ),
        ]

        if not self.db_repository.initialize(schema_files, start_job=True):
            return False

        self.columns = list(self.db_repository.excel_columns)

        self.log_signal_func(
            f"✅ [config] DB 컬럼 수={len(self.db_repository.db_columns)} / "
            f"엑셀 컬럼 수={len(self.db_repository.excel_columns)}"
        )
        return True

    def finish_job(
            self,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
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

    def insert_detail_rows(
            self,
            rows: Sequence[Dict[str, Any]],
            *,
            row_status: str = "SUCCESS",
    ) -> bool:
        if not self.db_repository:
            self.log_signal_func(
                "❌ [DB] Repository 없음 - detail 일괄 저장 실패"
            )
            return False

        return self.db_repository.insert_details(rows, row_status=row_status)

    @staticmethod
    def _now_db() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # =========================================================
    # Excel / 작업 마감
    # =========================================================
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

        job_id = self.db_repository.job_id or datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        excel_filename = f"{self.site_name}_{job_id}.xlsx"

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
                self.log_signal_func(
                    "ℹ️ [엑셀] 자동 저장 미사용(auto_save_yn=False)"
                )

        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")

    # =========================================================
    # 종료 / 정리
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        # Repository 연결 종료 전에 hist 마감 및 엑셀 저장
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
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()

        if self.db_repository and self.db_repository.status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        time.sleep(1)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.cleanup()
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()
