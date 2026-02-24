# launcher/core/notice_store.py
from __future__ import annotations  # === 신규 ===

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class NoticeAck:
    notice_id: str
    hide_until_epoch: int


def _now_epoch() -> int:
    return int(time.time())


def load_ack_map(path: Path) -> Dict[str, int]:
    """
    return: {notice_id: hide_until_epoch}
    """
    if not path.exists():
        return {}

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return {}
        out: Dict[str, int] = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.strip() and isinstance(v, int):
                out[k.strip()] = v
        return out
    except Exception:
        return {}


def save_ack_map(path: Path, m: Dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def is_hidden(path: Path, notice_id: str) -> bool:
    m = load_ack_map(path)
    until = m.get((notice_id or "").strip())
    if until is None:
        return False
    return until > _now_epoch()


def hide_for_day(path: Path, notice_id: str, seconds: int = 60 * 60 * 24) -> None:
    """
    기본: 24시간 숨김
    """
    nid = (notice_id or "").strip()
    if not nid:
        return

    m = load_ack_map(path)
    m[nid] = _now_epoch() + int(seconds)
    save_ack_map(path, m)