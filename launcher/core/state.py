from __future__ import annotations  # === 신규 ===

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CurrentState:
    program_id: str
    version: str
    server_url: str  # === 신규 ===


def version_to_dirname(version: str) -> str:
    v = version.strip()
    if not v:
        raise ValueError("version is empty")
    v = v.replace(".", "_")
    if not v.startswith("v"):
        v = "v" + v
    return v


def read_current_state(current_json_path: Path) -> CurrentState:
    if not current_json_path.exists():
        raise FileNotFoundError(f"current.json not found: {current_json_path}")

    obj = json.loads(current_json_path.read_text(encoding="utf-8"))

    program_id = obj.get("program_id")
    version = obj.get("version")
    server_url = obj.get("server_url")  # === 신규 ===

    if not isinstance(program_id, str) or not program_id.strip():
        raise ValueError('current.json invalid: "program_id" is required (string)')
    if not isinstance(version, str) or not version.strip():
        raise ValueError('current.json invalid: "version" is required (string)')
    if not isinstance(server_url, str) or not server_url.strip():  # === 신규 ===
        raise ValueError('current.json invalid: "server_url" is required (string)')

    return CurrentState(
        program_id=program_id.strip(),
        version=version.strip(),
        server_url=server_url.strip(),  # === 신규 ===
    )

def write_current_state(current_json_path: Path, st: CurrentState) -> None:
    """
    current.json 원자적 저장
    """
    obj = {
        "version": st.version,
        "program_id": st.program_id,
        "server_url": st.server_url,
    }

    current_json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = current_json_path.with_suffix(".tmp")

    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(current_json_path)