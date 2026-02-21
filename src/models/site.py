# src/models/site.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Site:
    label: Optional[str] = None
    key: Optional[str] = None
    color: Optional[str] = None
    enabled: bool = True

    # 지금 네 UI 흐름상 setting/columns는 "그대로 들고 다니기"만 하면 됨
    setting: Any = None
    setting_detail: Any = None
    columns: Any = None
    region: Any = None

    popup: bool = False
    sites: bool = False

    def is_enabled(self) -> bool:
        return self.enabled

    # === 신규 ===
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Site":
        return cls(
            label=d.get("label"),
            key=d.get("key"),
            color=d.get("color"),
            enabled=bool(d.get("enabled", True)),
            setting=d.get("setting"),
            setting_detail=d.get("setting_detail"),
            columns=d.get("columns"),
            region=d.get("region"),
            popup=bool(d.get("popup", False)),
            sites=bool(d.get("sites", False)),
        )