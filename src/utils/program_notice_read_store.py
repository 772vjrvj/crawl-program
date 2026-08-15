# src/utils/program_notice_read_store.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol


class NoticeLike(Protocol):
    notice_id: str


class ProgramNoticeReadStore:
    """
    프로그램별 runtime 폴더의 notice_read.json으로 읽음 상태를 관리한다.

    예:
        runtime/customers/naver_land_real_estate_detail/notice_read.json

    config.json과 사용자 설정은 건드리지 않는다.
    """

    FILE_NAME = "notice_read.json"

    def __init__(self, site: str, project_root: Path | None = None) -> None:
        self.site = (site or "").strip()
        self.project_root = Path(project_root) if project_root else Path.cwd()

        # 기존 runtime/customers/<site>/config.json 구조와 동일하게 사용한다.
        self.customer_dir = (
                self.project_root
                / "runtime"
                / "customers"
                / self.site.lower()
        )
        self.file_path = self.customer_dir / self.FILE_NAME

    def _load(self) -> dict[str, str]:
        if not self.file_path.exists():
            return {}

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            # 읽음 캐시가 깨졌더라도 프로그램 실행 자체에는 영향을 주지 않는다.
            return {}

        if not isinstance(data, dict):
            return {}

        result: dict[str, str] = {}
        for key, value in data.items():
            notice_id = str(key or "").strip()
            if not notice_id:
                continue
            result[notice_id] = str(value or "")

        return result

    def _save(self, data: dict[str, str]) -> None:
        self.customer_dir.mkdir(parents=True, exist_ok=True)

        # 중간에 프로그램이 종료돼도 기존 파일이 최대한 보존되도록 임시 파일 후 교체한다.
        temp_path = self.file_path.with_suffix(".json.tmp")

        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temp_path.replace(self.file_path)

    def is_read(self, notice_id: str) -> bool:
        notice_key = (notice_id or "").strip()
        if not notice_key:
            return False

        return notice_key in self._load()

    def mark_read(self, notice_id: str) -> None:
        notice_key = (notice_id or "").strip()
        if not notice_key:
            return

        data = self._load()

        # 이미 읽은 공지는 최초 읽은 시각을 유지한다.
        if notice_key in data:
            return

        data[notice_key] = datetime.now().isoformat(timespec="seconds")
        self._save(data)

    def get_unread_count(self, notices: Iterable[NoticeLike]) -> int:
        read_map = self._load()

        return sum(
            1
            for notice in notices
            if (notice.notice_id or "").strip()
            and notice.notice_id not in read_map
        )

    def get_unread_ids(self, notices: Iterable[NoticeLike]) -> set[str]:
        read_map = self._load()

        return {
            notice.notice_id
            for notice in notices
            if (notice.notice_id or "").strip()
               and notice.notice_id not in read_map
        }
