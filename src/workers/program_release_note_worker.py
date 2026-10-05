# src/workers/program_release_note_worker.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ProgramReleaseNote:
    """프로그램 정보 > 릴리즈 노트에서 사용하는 1건."""

    release_id: int | None
    program_id: str
    version: str
    title: str
    content: str
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ProgramReleaseNoteResult:
    ok: bool
    message: str
    release_notes: list[ProgramReleaseNote]


def _pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in obj and obj.get(key) is not None:
            return obj.get(key)
    return default


def _to_release_note(row: dict[str, Any]) -> ProgramReleaseNote:
    raw_id = _pick(row, "id", default=None)

    try:
        release_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        release_id = None

    version = str(
        _pick(row, "version", default="") or ""
    ).strip()

    title = str(
        _pick(
            row,
            "releaseTitle",
            "release_title",
            default="",
        ) or ""
    ).strip()

    content = str(
        _pick(
            row,
            "releaseNote",
            "release_note",
            default="",
        ) or ""
    )

    # 제목이 비어 있으면 버전으로 자연스럽게 표시한다.
    if not title:
        title = f"버전 {version}" if version else "릴리즈 노트"

    return ProgramReleaseNote(
        release_id=release_id,
        program_id=str(
            _pick(row, "programId", "program_id", default="") or ""
        ).strip(),
        version=version,
        title=title,
        content=content,
        created_at=str(
            _pick(row, "createdAt", "created_at", default="") or ""
        ).strip(),
        updated_at=str(
            _pick(row, "updatedAt", "updated_at", default="") or ""
        ).strip(),
    )


def fetch_program_release_notes(
        server_base_url: str,
        program_id: str,
        timeout_sec: int = 7,
) -> ProgramReleaseNoteResult:
    """
    서버 릴리즈 노트 API 호출.

    GET
    /launcher/api/v1/programs/{programId}/release-notes
    """
    base = (server_base_url or "").rstrip("/")
    pid = (program_id or "").strip()

    if not base:
        return ProgramReleaseNoteResult(
            ok=False,
            message="server_url is empty",
            release_notes=[],
        )

    if not pid:
        return ProgramReleaseNoteResult(
            ok=False,
            message="program_id is empty",
            release_notes=[],
        )

    url = f"{base}/launcher/api/v1/programs/{pid}/release-notes"

    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=timeout_sec,
        )
    except Exception as error:
        return ProgramReleaseNoteResult(
            ok=False,
            message=f"request failed: {str(error)}",
            release_notes=[],
        )

    if response.status_code != 200:
        return ProgramReleaseNoteResult(
            ok=False,
            message=(
                f"bad status: {response.status_code} / "
                f"{response.text[:200]}"
            ),
            release_notes=[],
        )

    try:
        obj = response.json()
    except Exception as error:
        return ProgramReleaseNoteResult(
            ok=False,
            message=f"json parse failed: {str(error)}",
            release_notes=[],
        )

    # 현재 서버 API는 List<LauncherReleaseDto>를 그대로 반환한다.
    if not isinstance(obj, list):
        return ProgramReleaseNoteResult(
            ok=False,
            message="invalid response: root is not list",
            release_notes=[],
        )

    release_notes = [
        _to_release_note(row)
        for row in obj
        if isinstance(row, dict)
    ]

    return ProgramReleaseNoteResult(
        ok=True,
        message="ok",
        release_notes=release_notes,
    )


class ProgramReleaseNoteWorker(QThread):
    """릴리즈 노트 탭 최초 진입 시 비동기로 조회한다."""

    sig_done = Signal(object)  # ProgramReleaseNoteResult

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
            result = fetch_program_release_notes(
                server_base_url=self.server_url,
                program_id=self.program_id,
            )
        except Exception as error:
            result = ProgramReleaseNoteResult(
                ok=False,
                message=f"unexpected error: {str(error)}",
                release_notes=[],
            )

        self.sig_done.emit(result)