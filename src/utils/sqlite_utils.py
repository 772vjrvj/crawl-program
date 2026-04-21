from __future__ import annotations

import os
import sys
import sqlite3
from typing import Optional, Callable, Any, Sequence


class SqliteUtils:
    def __init__(self, log_func: Optional[Callable[[str], None]] = None):
        self.log_func = log_func
        self.conn: Optional[sqlite3.Connection] = None

    def _log(self, msg: str) -> None:
        if self.log_func:
            try:
                self.log_func(msg)
            except Exception:
                pass

    def _get_base_dirs(self) -> list[str]:
        dirs = []

        cwd = os.getcwd()
        if cwd:
            dirs.append(cwd)

        this_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(this_file_dir, "..", ".."))
        if project_root:
            dirs.append(project_root)

        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            if exe_dir:
                dirs.append(exe_dir)
                dirs.append(os.path.join(exe_dir, "_internal"))

        result = []
        seen = set()

        for path in dirs:
            path = os.path.abspath(path)
            if path not in seen:
                seen.add(path)
                result.append(path)

        return result

    def resolve_path(self, relative_path: str) -> Optional[str]:
        try:
            relative_path = str(relative_path or "").strip()
            if not relative_path:
                return None

            if os.path.isabs(relative_path):
                return relative_path if os.path.exists(relative_path) else None

            for base_dir in self._get_base_dirs():
                full_path = os.path.join(base_dir, relative_path)
                if os.path.exists(full_path):
                    return full_path

            return None

        except Exception:
            return None

    def connect(self, db_path: str, readonly: bool = False) -> bool:
        try:
            self.close()

            db_path = str(db_path or "").strip()
            if not db_path:
                self._log("❌ [DB] db_path 비어있음")
                return False

            parent_dir = os.path.dirname(db_path)
            if parent_dir and not readonly:
                os.makedirs(parent_dir, exist_ok=True)

            if readonly:
                uri = f"file:{db_path}?mode=ro"
                self.conn = sqlite3.connect(uri, uri=True, timeout=30)
            else:
                self.conn = sqlite3.connect(db_path, timeout=30)

            self.conn.row_factory = sqlite3.Row

            if not readonly:
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA synchronous=NORMAL")
                self.conn.execute("PRAGMA busy_timeout = 30000")
            else:
                self.conn.execute("PRAGMA busy_timeout = 30000")

            if readonly:
                self._log(f"✅ [DB] 읽기 연결 완료: {db_path}")
            else:
                self._log(f"✅ [DB] 연결 완료: {db_path}")

            return True

        except Exception as e:
            self._log(f"❌ [DB] 연결 실패: {e}")
            self.conn = None
            return False

    def execute_script(self, sql_text: str) -> bool:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return False

            sql_text = str(sql_text or "").strip()
            if not sql_text:
                self._log("❌ [DB] SQL 비어있음")
                return False

            self.conn.executescript(sql_text)
            self.conn.commit()
            self._log("✅ [DB] SQL 실행 완료")
            return True

        except Exception as e:
            try:
                if self.conn:
                    self.conn.rollback()
            except Exception:
                pass

            self._log(f"❌ [DB] SQL 실행 실패: {e}")
            return False

    def execute_script_file(self, relative_path: str) -> bool:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return False

            full_path = self.resolve_path(relative_path)
            if not full_path:
                self._log(f"❌ [DB] 스키마 파일 못찾음: {relative_path}")
                return False

            with open(full_path, "r", encoding="utf-8") as f:
                sql_text = f.read()

            self._log(f"✅ [DB] 스키마 파일 확인: {full_path}")
            return self.execute_script(sql_text)

        except Exception as e:
            self._log(f"❌ [DB] 스키마 파일 실행 실패: {e}")
            return False

    def execute_script_files(self, relative_paths: Sequence[str]) -> bool:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return False

            paths = [str(x).strip() for x in relative_paths if str(x).strip()]
            if not paths:
                self._log("❌ [DB] 스키마 파일 목록 비어있음")
                return False

            for relative_path in paths:
                if not self.execute_script_file(relative_path):
                    return False

            self._log("✅ [DB] 전체 스키마 실행 완료")
            return True

        except Exception as e:
            self._log(f"❌ [DB] 스키마 파일들 실행 실패: {e}")
            return False

    def execute(self, query: str, params: Sequence[Any] = ()) -> bool:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return False

            self.conn.execute(query, params)
            self.conn.commit()
            return True

        except Exception as e:
            try:
                if self.conn:
                    self.conn.rollback()
            except Exception:
                pass

            self._log(f"❌ [DB] execute 실패: {e}")
            return False

    def fetchall(self, query: str, params: Sequence[Any] = ()) -> list[dict]:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return []

            cur = self.conn.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self._log(f"❌ [DB] fetchall 실패: {e}")
            return []

    def fetchone(self, query: str, params: Sequence[Any] = ()) -> Optional[dict]:
        try:
            if not self.conn:
                self._log("❌ [DB] conn 없음")
                return None

            cur = self.conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

        except Exception as e:
            self._log(f"❌ [DB] fetchone 실패: {e}")
            return None

    def close(self) -> None:
        try:
            if self.conn:
                self.conn.close()
                self._log("✅ [DB] 해제")
        except Exception:
            pass
        finally:
            self.conn = None