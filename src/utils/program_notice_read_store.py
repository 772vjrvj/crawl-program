# src/utils/program_notice_read_store.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol


class NoticeLike(Protocol):
    notice_id: str
    start_at: str
    end_at: str


class ProgramNoticeReadStore:
    """
    프로그램별 runtime 폴더의 notice_read.json으로 읽음 상태를 관리한다.

    NEW 조건:
        START_AT이 없거나 START_AT <= 현재시간
        AND
        END_AT이 없거나 END_AT >= 현재시간
        AND
        notice_read.json에 NOTICE_ID가 없음
    """

    FILE_NAME = "notice_read.json"

    def __init__(
            self,
            site: str,
            project_root: Path | None = None,
    ) -> None:
        self.site = (site or "").strip()
        self.project_root = Path(project_root) if project_root else Path.cwd()

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
            return {}

        if not isinstance(data, dict):
            return {}

        result: dict[str, str] = {}

        for key, value in data.items():
            notice_id = str(key or "").strip()

            if notice_id:
                result[notice_id] = str(value or "")

        return result

    def _save(self, data: dict[str, str]) -> None:
        self.customer_dir.mkdir(parents=True, exist_ok=True)

        temp_path = self.file_path.with_suffix(".json.tmp")

        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temp_path.replace(self.file_path)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        """
        아래 형식을 처리한다.
        2026-08-16 00:00:00
        2026-08-16T00:00:00
        2026-08-16T00:00:00+09:00
        2026-08-16T00:00:00Z
        """
        text = str(value or "").strip()

        if not text:
            return None

        normalized = text

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _normalize_compare_pair(
            left: datetime,
            right: datetime,
    ) -> tuple[datetime, datetime]:
        """aware/naive datetime 비교 오류를 방지한다."""
        left_aware = left.tzinfo is not None
        right_aware = right.tzinfo is not None

        if left_aware and right_aware:
            return (
                left.astimezone(timezone.utc),
                right.astimezone(timezone.utc),
            )

        if not left_aware and not right_aware:
            return left, right

        return (
            left.replace(tzinfo=None),
            right.replace(tzinfo=None),
        )

    def is_active_notice(
            self,
            notice: NoticeLike,
            now: datetime | None = None,
    ) -> bool:
        """
        현재 시간이 공지 START_AT ~ END_AT 범위 안인지 확인한다.

        START_AT 없음 = 즉시 노출
        END_AT 없음   = 종료 없음
        """
        current = now or datetime.now()

        start_at = self._parse_datetime(
            getattr(notice, "start_at", "")
        )
        end_at = self._parse_datetime(
            getattr(notice, "end_at", "")
        )

        if start_at is not None:
            compare_start, compare_now = self._normalize_compare_pair(
                start_at,
                current,
            )

            if compare_start > compare_now:
                return False

        if end_at is not None:
            compare_end, compare_now = self._normalize_compare_pair(
                end_at,
                current,
            )

            if compare_end < compare_now:
                return False

        return True

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

        if notice_key in data:
            return

        data[notice_key] = datetime.now().isoformat(timespec="seconds")
        self._save(data)

    def is_new(
            self,
            notice: NoticeLike,
            now: datetime | None = None,
    ) -> bool:
        """현재 유효기간 안 + 미읽음인 공지만 NEW."""
        notice_id = str(
            getattr(notice, "notice_id", "") or ""
        ).strip()

        if not notice_id:
            return False

        if not self.is_active_notice(notice, now=now):
            return False

        return not self.is_read(notice_id)

    def get_unread_count(
            self,
            notices: Iterable[NoticeLike],
    ) -> int:
        """메인 버튼 빨간 숫자용 현재 유효한 미읽음 공지 개수."""
        read_map = self._load()
        current = datetime.now()
        count = 0

        for notice in notices:
            notice_id = str(
                getattr(notice, "notice_id", "") or ""
            ).strip()

            if not notice_id:
                continue

            if notice_id in read_map:
                continue

            if not self.is_active_notice(notice, now=current):
                continue

            count += 1

        return count

    def get_unread_ids(
            self,
            notices: Iterable[NoticeLike],
    ) -> set[str]:
        """공지 카드 NEW 표시용 현재 유효한 미읽음 NOTICE_ID 집합."""
        read_map = self._load()
        current = datetime.now()
        result: set[str] = set()

        for notice in notices:
            notice_id = str(
                getattr(notice, "notice_id", "") or ""
            ).strip()

            if not notice_id:
                continue

            if notice_id in read_map:
                continue

            if not self.is_active_notice(notice, now=current):
                continue

            result.add(notice_id)

        return result
