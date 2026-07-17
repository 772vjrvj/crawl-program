from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CurrentState:
    """
    현재 설치된 프로그램 정보
    """

    program_id: str
    version: str
    server_url: str
    launcher_key: str


def version_to_dirname(version: str) -> str:
    """
    버전 문자열을 버전 폴더명으로 변환한다.

    예:
    1.0.2 -> v1_0_2
    v1.0.2 -> v1_0_2
    """
    value = version.strip()

    if not value:
        raise ValueError("version is empty")

    value = value.replace(".", "_")

    if not value.startswith("v"):
        value = "v" + value

    return value


def read_current_state(
        current_json_path: Path,
) -> CurrentState:
    """
    current.json을 읽어 CurrentState로 반환한다.
    """

    if not current_json_path.exists():
        raise FileNotFoundError(
            f"current.json not found: {current_json_path}"
        )

    try:
        text = current_json_path.read_text(
            encoding="utf-8"
        )

        obj = json.loads(text)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"current.json invalid json: {str(error)}"
        ) from error

    except OSError as error:
        raise OSError(
            f"current.json read failed: {str(error)}"
        ) from error

    if not isinstance(obj, dict):
        raise ValueError(
            "current.json invalid: root must be object"
        )

    program_id = obj.get("program_id")
    version = obj.get("version")
    server_url = obj.get("server_url")
    launcher_key = obj.get("launcher_key")

    if (
            not isinstance(program_id, str)
            or not program_id.strip()
    ):
        raise ValueError(
            'current.json invalid: '
            '"program_id" is required (string)'
        )

    if (
            not isinstance(version, str)
            or not version.strip()
    ):
        raise ValueError(
            'current.json invalid: '
            '"version" is required (string)'
        )

    if (
            not isinstance(server_url, str)
            or not server_url.strip()
    ):
        raise ValueError(
            'current.json invalid: '
            '"server_url" is required (string)'
        )

    if (
            not isinstance(launcher_key, str)
            or not launcher_key.strip()
    ):
        raise ValueError(
            'current.json invalid: '
            '"launcher_key" is required (string)'
        )

    return CurrentState(
        program_id=program_id.strip(),
        version=version.strip(),
        server_url=server_url.strip(),
        launcher_key=launcher_key.strip(),
    )


def write_current_state(
        current_json_path: Path,
        state: CurrentState,
) -> None:
    """
    current.json을 임시 파일에 먼저 작성한 뒤
    원본 파일로 교체하여 안전하게 저장한다.
    """

    obj = {
        "program_id": state.program_id,
        "version": state.version,
        "server_url": state.server_url,
        "launcher_key": state.launcher_key,
    }

    current_json_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = current_json_path.with_suffix(
        ".tmp"
    )

    try:
        temp_path.write_text(
            json.dumps(
                obj,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temp_path.replace(current_json_path)

    except OSError as error:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

        raise OSError(
            f"current.json write failed: {str(error)}"
        ) from error