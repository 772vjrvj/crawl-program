from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from src.utils.sqlite_utils import SqliteUtils


class WorkerDbRepository:
    """
    Worker 공통 SQLite Repository.

    역할
    - SQLite 연결 및 스키마 초기화
    - worker_job_hist 작업 시작/종료 처리
    - Worker별 detail 데이터 단건/다건 저장
    - config.json columns[].code 기준 detail 조회
    - config.json columns[].value 기준 엑셀 데이터 변환

    detail INSERT 컬럼 구성
    1. 모든 detail 테이블의 공통 컬럼
    2. config.json에 정의된 Worker별 동적 컬럼
    3. created_at, updated_at

    Worker는 수집 결과를 config.json의 columns[].code 기준 dict로 전달한다.

    예:
        {
            "id": "123",
            "name": "상호명"
        }
    """

    # 모든 Worker의 detail 테이블에 공통으로 존재하는 컬럼
    # Worker마다 달라지는 수집 컬럼은 config.json에서 동적으로 가져온다.
    DETAIL_COMMON_COLUMNS = [
        "hist_id",
        "site_name",
        "worker_name",
        "table_name",
        "job_id",
        "user_id",
        "row_status",
        "row_error_message",
        "row_start_at",
        "row_end_at",
    ]

    def __init__(
            self,
            *,
            db_path: str,
            site_name: str,
            worker_name: str,
            detail_table_name: str,
            column_defs: Sequence[Dict[str, Any]],
            user_id: Optional[Any] = None,
            hist_table_name: str = "worker_job_hist",
            log_func: Optional[Callable[[str], None]] = None,
            detail_log_fields: Sequence[str] = (),
    ) -> None:
        # DB 및 테이블 정보
        self.db_path = db_path
        self.hist_table_name = hist_table_name
        self.detail_table_name = detail_table_name

        # 현재 Worker 정보
        self.site_name = site_name
        self.worker_name = worker_name
        self.user_id = user_id

        # 로그 설정
        self.log_func = log_func
        self.detail_log_fields = tuple(detail_log_fields)

        # config.json에 정의된 Worker별 동적 컬럼
        columns = list(column_defs)

        # detail 테이블에 저장할 실제 DB 컬럼명
        self.db_columns = [
            column["code"]
            for column in columns
        ]

        # 엑셀 출력 대상으로 선택된 컬럼 정의
        self.checked_column_defs = [
            column
            for column in columns
            if column.get("checked", False)
        ]

        # 엑셀 조회에 사용할 DB 컬럼명
        self.checked_codes = [
            column["code"]
            for column in self.checked_column_defs
        ]

        # 엑셀 헤더에 표시할 컬럼명
        self.excel_columns = [
            column["value"]
            for column in self.checked_column_defs
        ]

        # SQLite 공통 유틸
        self.sqlite = SqliteUtils(self._log)

        # 현재 작업 이력 정보
        self.hist_id: Optional[int] = None
        self.job_id: Optional[str] = None

        # 현재 작업 결과
        self.status = "RUNNING"
        self.error_message: Optional[str] = None
        self.success_count = 0
        self.fail_count = 0

        # stop, cleanup, destroy에서 종료 처리가 중복되는 것을 방지한다.
        self._job_finished = False

    # =========================================================
    # DB 연결 및 초기화
    # =========================================================
    @property
    def is_connected(self) -> bool:
        """SQLite 연결 여부를 반환한다."""
        return self.sqlite.conn is not None

    def initialize(
            self,
            schema_files: Sequence[str],
            *,
            start_job: bool = True,
    ) -> bool:
        """DB 연결, 스키마 실행, 작업 시작을 순서대로 처리한다."""
        if not self.connect():
            return False

        if not self.sqlite.execute_script_files(schema_files):
            self._log("❌ [DB] 스키마 초기화 실패")
            return False

        self._log("✅ [DB] 스키마 초기화 완료")

        if start_job:
            return self.start_job()

        return True

    def connect(self) -> bool:
        """SQLite에 연결한다. 이미 연결된 경우 기존 연결을 사용한다."""
        if self.is_connected:
            return True

        self._log(f"[DB] 실제 경로 = {self.db_path}")
        return self.sqlite.connect(self.db_path)

    def close(self) -> None:
        """SQLite 연결을 닫는다."""
        self.sqlite.close()

    # =========================================================
    # config 컬럼 확인
    # =========================================================
    def is_column_checked(self, code: str) -> bool:
        """특정 컬럼이 엑셀 출력 대상으로 선택되었는지 확인한다."""
        return code in self.checked_codes

    def are_any_columns_checked(self, codes: Iterable[str]) -> bool:
        """전달한 컬럼 중 하나라도 엑셀 출력 대상인지 확인한다."""
        return any(code in self.checked_codes for code in codes)

    # =========================================================
    # 작업 이력
    # =========================================================
    def reset_job_state(self) -> None:
        """새 작업 시작 전에 이전 작업 상태를 초기화한다."""
        self.hist_id = None
        self.job_id = None
        self.status = "RUNNING"
        self.error_message = None
        self.success_count = 0
        self.fail_count = 0
        self._job_finished = False

    def set_job_result(
            self,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        """작업 종료 전에 최종 상태와 대표 오류 메시지를 설정한다."""
        self.status = status
        self.error_message = error_message

    def start_job(self, job_id: Optional[str] = None) -> bool:
        """worker_job_hist에 RUNNING 상태의 작업 이력을 생성한다."""
        if not self.connect():
            self._log("❌ [DB] 연결 없음 - hist 시작 실패")
            return False

        self.reset_job_state()

        now = self._now()

        # 외부에서 job_id를 전달하면 그대로 사용한다.
        # 전달하지 않으면 시간 + UUID 일부를 조합해 충돌 가능성을 최소화한다.
        self.job_id = (
                job_id
                or f"{datetime.now():%Y%m%d%H%M%S%f}_{uuid4().hex[:8]}"
        )

        query = f"""
            INSERT INTO {self._quote(self.hist_table_name)} (
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
            self.user_id,
            now,
            "RUNNING",
            0,
            0,
            0,
            now,
            now,
        )

        if not self.sqlite.execute(query, params):
            self._log("❌ [DB] hist 시작 row 저장 실패")
            return False

        # 방금 INSERT된 hist PK를 가져온다.
        row = self.sqlite.fetchone(
            "SELECT last_insert_rowid() AS hist_id"
        )

        if not row or row.get("hist_id") is None:
            self._log("❌ [DB] hist_id 조회 실패")
            return False

        self.hist_id = int(row["hist_id"])

        self._log(
            f"✅ [DB] hist 시작 row 저장 완료 | "
            f"hist_id={self.hist_id} | "
            f"job_id={self.job_id}"
        )

        return True

    def finish_job(
            self,
            status: Optional[str] = None,
            error_message: Optional[str] = None,
    ) -> bool:
        """현재 작업의 최종 상태와 저장 건수를 hist 테이블에 반영한다."""
        # finish_job에서 상태를 직접 전달한 경우 최종 결과를 먼저 설정한다.
        if status is not None:
            self.set_job_result(status, error_message)
        elif error_message is not None:
            self.error_message = error_message

        # cleanup, stop, destroy에서 여러 번 호출되어도 한 번만 UPDATE한다.
        if self._job_finished:
            return True

        if self.hist_id is None:
            self._log("⚠️ [DB] hist_id 없음 - 종료 update 스킵")
            return False

        if not self.connect():
            self._log("❌ [DB] 연결 없음 - hist 종료 실패")
            return False

        now = self._now()

        query = f"""
            UPDATE {self._quote(self.hist_table_name)}
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
            self.status,
            self.success_count + self.fail_count,
            self.success_count,
            self.fail_count,
            self.error_message,
            now,
            self.hist_id,
        )

        if not self.sqlite.execute(query, params):
            self._log(
                f"❌ [DB] hist 종료 row 수정 실패 | "
                f"hist_id={self.hist_id}"
            )
            return False

        self._job_finished = True

        self._log(
            f"✅ [DB] hist 종료 row 수정 완료 | "
            f"hist_id={self.hist_id} | "
            f"status={self.status}"
        )

        return True

    # =========================================================
    # detail 저장
    # =========================================================
    def insert_detail(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        """
        수집 결과 한 건을 Worker별 detail 테이블에 저장한다.

        기존 Worker는 insert_detail(row)만 호출해도 된다.
        행 단위 상태 관리가 필요한 Worker만 row_* 값을 추가로 전달한다.
        """
        if not isinstance(row, dict):
            self.fail_count += 1
            self._log("❌ [DB] detail row가 dict가 아님")
            return False

        if not self._can_save_detail():
            self.fail_count += 1
            return False

        query = self._build_detail_insert_query()
        params = self._build_detail_params(
            row=row,
            row_status=row_status,
            row_error_message=row_error_message,
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

        success = self.sqlite.execute(query, params)

        if success:
            self.success_count += 1
        else:
            self.fail_count += 1

        self._log_detail_result(success, row)

        return success

    def insert_details(
            self,
            rows: Sequence[Dict[str, Any]],
            *,
            row_status: str = "SUCCESS",
    ) -> bool:
        """수집 결과 여러 건을 하나의 트랜잭션으로 저장한다."""
        row_list = list(rows)

        if not row_list:
            self._log("⚠️ [DB] 저장할 detail 데이터 없음")
            return False

        # 잘못된 행을 조용히 제외하지 않고 전체 실패로 처리한다.
        if not all(isinstance(row, dict) for row in row_list):
            self.fail_count += len(row_list)
            self._log("❌ [DB] detail 목록에 dict가 아닌 데이터가 있음")
            return False

        if not self._can_save_detail():
            self.fail_count += len(row_list)
            return False

        query = self._build_detail_insert_query()
        params_list = [
            self._build_detail_params(
                row=row,
                row_status=row_status,
            )
            for row in row_list
        ]

        try:
            if self.sqlite.conn is None:
                raise RuntimeError("SQLite connection이 없습니다.")

            self.sqlite.conn.executemany(query, params_list)
            self.sqlite.conn.commit()

            self.success_count += len(row_list)

            self._log(
                f"✅ [DB] detail bulk 저장 완료 | "
                f"hist_id={self.hist_id} | "
                f"count={len(row_list)}"
            )

            return True

        except Exception as e:
            if self.sqlite.conn is not None:
                self.sqlite.conn.rollback()

            self.fail_count += len(row_list)

            self._log(
                f"❌ [DB] detail bulk 저장 실패 | "
                f"hist_id={self.hist_id} | "
                f"count={len(row_list)} | "
                f"error={e}"
            )

            return False

    def _can_save_detail(self) -> bool:
        """detail 저장에 필요한 DB 연결과 작업 정보가 있는지 확인한다."""
        if not self.is_connected:
            self._log("❌ [DB] 연결 없음 - detail 저장 실패")
            return False

        if self.hist_id is None or not self.job_id:
            self._log(
                "❌ [DB] hist_id 또는 job_id 없음 - "
                "detail 저장 실패"
            )
            return False

        return True

    def _build_detail_insert_query(self) -> str:
        """
        detail INSERT SQL을 생성한다.

        최종 컬럼 순서
        - detail 공통 컬럼
        - config.json columns[].code
        - created_at, updated_at
        """
        columns = [
            *self.DETAIL_COMMON_COLUMNS,
            *self.db_columns,
            "created_at",
            "updated_at",
        ]

        column_text = ",\n                ".join(
            self._quote(column)
            for column in columns
        )

        placeholders = ", ".join(
            "?"
            for _ in columns
        )

        return f"""
            INSERT INTO {self._quote(self.detail_table_name)} (
                {column_text}
            ) VALUES ({placeholders})
        """

    def _build_detail_params(
            self,
            *,
            row: Dict[str, Any],
            row_status: str,
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> Tuple[Any, ...]:
        """detail INSERT SQL의 컬럼 순서에 맞는 파라미터를 생성한다."""
        now = self._now()

        return (
            self.hist_id,
            self.site_name,
            self.worker_name,
            self.detail_table_name,
            self.job_id,
            self.user_id,
            row_status,
            row_error_message,
            row_start_at,
            row_end_at,
            *[
                self._to_db_value(row.get(column, ""))
                for column in self.db_columns
            ],
            now,
            now,
        )

    # =========================================================
    # detail 조회 및 엑셀 변환
    # =========================================================
    def fetch_detail_rows(
            self,
            *,
            checked_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """현재 작업에서 저장한 Worker별 데이터 컬럼을 조회한다."""
        if self.hist_id is None:
            self._log("❌ [DB] hist_id 없음 - detail 조회 실패")
            return []

        if not self.connect():
            self._log("❌ [DB] 연결 없음 - detail 조회 실패")
            return []

        columns = (
            self.checked_codes
            if checked_only
            else self.db_columns
        )

        if not columns:
            self._log("⚠️ [DB] 조회할 config 컬럼 없음")
            return []

        column_text = ",\n                ".join(
            self._quote(column)
            for column in columns
        )

        query = f"""
            SELECT
                {column_text}
            FROM {self._quote(self.detail_table_name)}
            WHERE hist_id = ?
            ORDER BY detail_id
        """

        return self.sqlite.fetchall(
            query,
            (self.hist_id,),
        )

    def to_excel_rows(
            self,
            rows: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """DB 컬럼명(code)을 엑셀 컬럼명(value)으로 변환한다."""
        return [
            {
                column["value"]: row.get(
                    column["code"],
                    "",
                )
                for column in self.checked_column_defs
            }
            for row in rows
        ]

    def get_excel_data(
            self,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """엑셀 헤더와 행 데이터를 함께 반환한다."""
        rows = self.fetch_detail_rows(
            checked_only=True
        )

        return (
            list(self.excel_columns),
            self.to_excel_rows(rows),
        )

    # =========================================================
    # 공통 내부 함수
    # =========================================================
    @staticmethod
    def _quote(name: str) -> str:
        """테이블명과 컬럼명을 SQLite 식별자로 감싼다."""
        return f'"{name}"'

    @staticmethod
    def _to_db_value(value: Any) -> Any:
        """SQLite가 직접 저장하지 못하는 dict와 list를 JSON 문자열로 바꾼다."""
        if isinstance(value, (dict, list)):
            return json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )

        return value

    @staticmethod
    def _now() -> str:
        """현재 시간을 밀리초까지 포함한 DB 저장용 문자열로 반환한다."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _log_detail_result(
            self,
            success: bool,
            row: Dict[str, Any],
    ) -> None:
        """detail 단건 저장 결과와 대표 필드 값을 한 줄로 출력한다."""
        icon = "✅" if success else "❌"
        result = "완료" if success else "실패"

        fields = [
            f"{field}={row.get(field, '')}"
            for field in self.detail_log_fields
        ]

        field_text = (
            f" | {' | '.join(fields)}"
            if fields
            else ""
        )

        self._log(
            f"{icon} [DB] detail 저장 {result} | "
            f"hist_id={self.hist_id}"
            f"{field_text}"
        )

    def _log(self, message: str) -> None:
        """외부 로그 함수가 설정된 경우에만 메시지를 전달한다."""
        if self.log_func is None:
            return

        try:
            self.log_func(message)
        except Exception:
            # 로그 실패가 DB 작업 실패로 이어지지 않게 한다.
            pass
