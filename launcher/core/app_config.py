from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SupportConfig:
    site_url: str
    qna_url: str


def load_support_config(data_dir: Path) -> Optional[SupportConfig]:
    cfg_path = data_dir / "app.json"

    if not cfg_path.exists():
        return None

    try:
        obj = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    support = obj.get("support")
    if not isinstance(support, dict):
        return None

    site_url = support.get("site_url")
    qna_url = support.get("qna_url")

    if not isinstance(site_url, str) or not site_url.strip():
        return None
    if not isinstance(qna_url, str) or not qna_url.strip():
        return None

    return SupportConfig(
        site_url=site_url.strip(),
        qna_url=qna_url.strip(),
    )