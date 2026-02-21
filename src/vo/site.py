# src/vo/site.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Site:
    """
    사이트 설정 VO.
    """
    label: Optional[str] = None
    key: Optional[str] = None
    color: Optional[str] = None

    enabled: bool = True

    setting: Optional[Dict[str, Any]] = None
    setting_detail: Optional[Dict[str, Any]] = None

    columns: Optional[List[str]] = None
    region: Any = None

    popup: bool = False
    sites: bool = False

    def is_enabled(self) -> bool:
        return self.enabled