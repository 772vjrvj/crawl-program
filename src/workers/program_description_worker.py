# src/workers/program_description_worker.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ProgramDescription:
    """프로그램 정보 > 프로그램 설명에서 사용하는 데이터."""

    program_id: str
    description: str
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ProgramDescriptionResult:
    ok: bool
    message: str
    data: Optional[ProgramDescription]


def _pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in obj and obj.get(key) is not None:
            return obj.get(key)
    return default


def fetch_program_description(
        server_base_url: str,
        program_id: str,
        timeout_sec: int = 7,
) -> ProgramDescriptionResult:
    """
    서버 프로그램 설명 API 호출.

    GET
    /launcher/api/v1/programs/{programId}/description
    """
    base = (server_base_url or "").rstrip("/")
    pid = (program_id or "").strip()

    if not base:
        return ProgramDescriptionResult(
            ok=False,
            message="server_url is empty",
            data=None,
        )

    if not pid:
        return ProgramDescriptionResult(
            ok=False,
            message="program_id is empty",
            data=None,
        )

    url = f"{base}/launcher/api/v1/programs/{pid}/description"

    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=timeout_sec,
        )
    except Exception as error:
        return ProgramDescriptionResult(
            ok=False,
            message=f"request failed: {str(error)}",
            data=None,
        )

    # 등록된 설명이 없는 정상 상태
    if response.status_code == 204:
        return ProgramDescriptionResult(
            ok=True,
            message="no content",
            data=None,
        )

    if response.status_code != 200:
        return ProgramDescriptionResult(
            ok=False,
            message=(
                f"bad status: {response.status_code} / "
                f"{response.text[:200]}"
            ),
            data=None,
        )

    try:
        obj = response.json()
    except Exception as error:
        return ProgramDescriptionResult(
            ok=False,
            message=f"json parse failed: {str(error)}",
            data=None,
        )

    if not isinstance(obj, dict):
        return ProgramDescriptionResult(
            ok=False,
            message="invalid response: root is not object",
            data=None,
        )

    enabled_raw = _pick(obj, "enabled", default=True)
    enabled = (
        enabled_raw is True
        or str(enabled_raw).strip().upper() in {"Y", "TRUE", "1"}
    )

    data = ProgramDescription(
        program_id=str(
            _pick(obj, "programId", "program_id", default="") or ""
        ).strip(),
        description=str(
            _pick(obj, "description", default="") or ""
        ),
        enabled=enabled,
        created_at=str(
            _pick(obj, "createdAt", "created_at", default="") or ""
        ).strip(),
        updated_at=str(
            _pick(obj, "updatedAt", "updated_at", default="") or ""
        ).strip(),
    )

    return ProgramDescriptionResult(
        ok=True,
        message="ok",
        data=data,
    )


class ProgramDescriptionWorker(QThread):
    """프로그램 설명 API를 UI 스레드 밖에서 호출한다."""

    sig_done = Signal(object)  # ProgramDescriptionResult

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
            result = fetch_program_description(
                server_base_url=self.server_url,
                program_id=self.program_id,
            )
        except Exception as error:
            result = ProgramDescriptionResult(
                ok=False,
                message=f"unexpected error: {str(error)}",
                data=None,
            )

        self.sig_done.emit(result)
