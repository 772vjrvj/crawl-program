from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Optional


class RunFileLogger:
    def __init__(
            self,
            site: str,
            logs_dir: str = "logs",
            retention_days: int = 30,
            encoding: str = "utf-8",
    ) -> None:
        self.site = self._sanitize_site(site)
        self.logs_dir = Path(logs_dir)
        self.retention_days = retention_days
        self.encoding = encoding

        self._lock = Lock()
        self._file: Optional[Any] = None
        self._file_path: Optional[Path] = None

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._delete_old_logs()
        self._open_new_file()

    def _sanitize_site(self, site: str) -> str:
        value = (site or "APP").strip()
        value = re.sub(r"[^\w\-]", "_", value)
        return value or "APP"

    def _open_new_file(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.site}_{ts}.log"
        self._file_path = self.logs_dir / filename

        # line buffering
        self._file = open(self._file_path, mode="a", encoding=self.encoding, buffering=1)

    def _delete_old_logs(self) -> None:
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        for path in self.logs_dir.glob("*.log"):
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
                if modified_at < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                # 로그 삭제 실패는 전체 프로그램에 영향 주지 않도록 무시
                pass

    def log(self, message: Any) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"

        with self._lock:
            if self._file is not None:
                try:
                    self._file.write(line + "\n")
                    self._file.flush()
                except Exception:
                    pass

        return line

    def get_file_path(self) -> Optional[str]:
        return str(self._file_path) if self._file_path else None

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass
                finally:
                    self._file = None