# src/workers/program_notice_worker.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ProgramNotice:
    """메인 프로그램에서 사용하는 공지 1건."""

    notice_id: str
    program_id: str
    level: str
    force: bool
    title: str
    content: str

    # NEW 판단용
    start_at: str = ""
    end_at: str = ""

    # 화면 표시/정렬 보조용
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ProgramNoticeListResult:
    """공지 전체 조회 결과."""

    ok: bool
    message: str
    notices: list[ProgramNotice]
    total_elements: int = 0


def _pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """camelCase / snake_case 서버 응답을 모두 허용한다."""
    for key in keys:
        if key in obj and obj.get(key) is not None:
            return obj.get(key)
    return default


def _to_notice(row: dict[str, Any]) -> ProgramNotice:
    """서버 공지 DTO를 ProgramNotice로 변환한다."""
    force_raw = _pick(row, "force", "forceYn", "force_yn", default=False)

    return ProgramNotice(
        notice_id=str(
            _pick(row, "noticeId", "notice_id", "id", default="") or ""
        ).strip(),
        program_id=str(
            _pick(row, "programId", "program_id", default="") or ""
        ).strip(),
        level=str(
            _pick(row, "level", default="INFO") or "INFO"
        ).strip().upper(),
        force=(
            force_raw is True
            or str(force_raw).strip().upper() in {"Y", "TRUE", "1"}
        ),
        title=str(
            _pick(row, "title", default="") or ""
        ).strip(),
        content=str(
            _pick(row, "content", default="") or ""
        ),
        start_at=str(
            _pick(row, "startAt", "start_at", "START_AT", default="") or ""
        ).strip(),
        end_at=str(
            _pick(row, "endAt", "end_at", "END_AT", default="") or ""
        ).strip(),
        created_at=str(
            _pick(row, "createdAt", "created_at", "CREATED_AT", default="") or ""
        ).strip(),
        updated_at=str(
            _pick(row, "updatedAt", "updated_at", "UPDATED_AT", default="") or ""
        ).strip(),
    )


def fetch_program_notice_page(
        server_base_url: str,
        program_id: str,
        page: int,
        size: int = 100,
        timeout_sec: int = 7,
) -> tuple[bool, str, list[ProgramNotice], int, int]:
    """공지 목록 API에서 한 페이지를 조회한다."""

    base = (server_base_url or "").rstrip("/")
    pid = (program_id or "").strip()

    if not base:
        return False, "server_url is empty", [], 0, 0

    if not pid:
        return False, "program_id is empty", [], 0, 0

    url = f"{base}/launcher/api/v1/programs/{pid}/notices"

    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            params={
                "page": max(0, int(page)),
                "size": max(1, min(100, int(size))),
            },
            timeout=timeout_sec,
        )
    except Exception as error:
        return False, f"request failed: {str(error)}", [], 0, 0

    if response.status_code != 200:
        return (
            False,
            f"bad status: {response.status_code} / {response.text[:200]}",
            [],
            0,
            0,
        )

    try:
        obj = response.json()
    except Exception as error:
        return False, f"json parse failed: {str(error)}", [], 0, 0

    if not isinstance(obj, dict):
        return False, "invalid response: root is not object", [], 0, 0

    rows = _pick(obj, "data", "content", default=[])
    if not isinstance(rows, list):
        rows = []

    notices = [
        _to_notice(row)
        for row in rows
        if isinstance(row, dict)
    ]

    total_raw = _pick(
        obj,
        "totalElements",
        "total_elements",
        default=len(notices),
    )
    total_pages_raw = _pick(
        obj,
        "totalPages",
        "total_pages",
        default=1 if notices else 0,
    )

    try:
        total_elements = max(0, int(total_raw))
    except (TypeError, ValueError):
        total_elements = len(notices)

    try:
        total_pages = max(0, int(total_pages_raw))
    except (TypeError, ValueError):
        total_pages = 1 if notices else 0

    return True, "ok", notices, total_elements, total_pages


def fetch_all_program_notices(
        server_base_url: str,
        program_id: str,
        page_size: int = 100,
        timeout_sec: int = 7,
) -> ProgramNoticeListResult:
    """메인 화면에서 사용할 공지를 페이지 끝까지 전부 가져온다."""

    all_notices: list[ProgramNotice] = []
    page = 0
    total_elements = 0

    while True:
        (
            ok,
            message,
            notices,
            total_elements,
            total_pages,
        ) = fetch_program_notice_page(
            server_base_url=server_base_url,
            program_id=program_id,
            page=page,
            size=page_size,
            timeout_sec=timeout_sec,
        )

        if not ok:
            return ProgramNoticeListResult(
                ok=False,
                message=message,
                notices=[],
                total_elements=0,
            )

        all_notices.extend(notices)

        if total_pages <= 0 or page + 1 >= total_pages:
            break

        page += 1

    return ProgramNoticeListResult(
        ok=True,
        message="ok",
        notices=all_notices,
        total_elements=total_elements,
    )


class ProgramNoticeWorker(QThread):
    """메인 화면 시작 시 공지 전체를 비동기로 미리 조회한다."""

    sig_done = Signal(object)  # ProgramNoticeListResult

    def __init__(
            self,
            server_url: str,
            program_id: str,
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.server_url = server_url
        self.program_id = program_id

    def run(self) -> None:
        try:
            result = fetch_all_program_notices(
                server_base_url=self.server_url,
                program_id=self.program_id,
            )
        except Exception as error:
            result = ProgramNoticeListResult(
                ok=False,
                message=f"unexpected error: {str(error)}",
                notices=[],
                total_elements=0,
            )

        self.sig_done.emit(result)
