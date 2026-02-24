# launcher/core/api.py
from __future__ import annotations  # === 신규 ===

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


@dataclass(frozen=True)
class LatestInfo:
    program_id: str
    latest_version: str
    asset_url: Optional[str] = None
    asset_sha256: Optional[str] = None
    asset_size: Optional[int] = None


@dataclass(frozen=True)
class NoticeInfo:
    notice_id: str
    level: str          # CRITICAL | IMPORTANT | INFO
    force: bool
    title: str
    content: str


def fetch_latest(server_base_url: str, program_id: str, timeout_sec: int = 10) -> Tuple[bool, str, Optional[LatestInfo]]:
    """
    서버에서 최신 버전 정보 조회 (1단계 테스트용)
    """
    base = server_base_url.rstrip("/")
    url = f"{base}/launcher/api/v1/programs/{program_id}/latest"
    headers = {"Accept": "application/json"}

    try:
        res = requests.get(url, headers=headers, timeout=timeout_sec)
    except Exception as e:
        return False, f"request failed: {str(e)}", None

    if res.status_code != 200:
        # 너무 길면 콘솔 지저분해지니 앞부분만
        return False, f"bad status: {res.status_code} / {res.text[:200]}", None

    try:
        obj: Dict[str, Any] = res.json()
    except Exception as e:
        return False, f"json parse failed: {str(e)}", None

    pid = obj.get("program_id")
    latest = obj.get("latest_version")

    if not isinstance(pid, str) or not pid.strip():
        return False, 'invalid response: "program_id"', None
    if not isinstance(latest, str) or not latest.strip():
        return False, 'invalid response: "latest_version"', None

    asset = obj.get("asset") or {}
    asset_url = asset.get("url")
    asset_sha256 = asset.get("sha256")
    asset_size = asset.get("size")

    info = LatestInfo(
        program_id=pid.strip(),
        latest_version=latest.strip(),
        asset_url=asset_url.strip() if isinstance(asset_url, str) and asset_url.strip() else None,
        asset_sha256=asset_sha256.strip() if isinstance(asset_sha256, str) and asset_sha256.strip() else None,
        asset_size=int(asset_size) if isinstance(asset_size, int) else None,
    )
    return True, "ok", info


def fetch_latest_notice(server_base_url: str, program_id: str, timeout_sec: int = 5) -> Tuple[bool, str, Optional[NoticeInfo]]:
    """
    공지 최신 1건만 조회(런처용)
    """
    base = server_base_url.rstrip("/")
    url = f"{base}/launcher/api/v1/programs/{program_id}/notices/latest"
    headers = {"Accept": "application/json"}

    try:
        res = requests.get(url, headers=headers, timeout=timeout_sec)
    except Exception as e:
        return False, f"request failed: {str(e)}", None

    if res.status_code == 204:
        return True, "no notice", None

    if res.status_code != 200:
        return False, f"bad status: {res.status_code} / {res.text[:200]}", None

    try:
        obj: Dict[str, Any] = res.json()
    except Exception as e:
        return False, f"json parse failed: {str(e)}", None

    n = obj.get("notice") or obj  # 서버가 notice 래핑을 안 할 수도 있어서 대응
    if not isinstance(n, dict):
        return False, "invalid response: notice is not object", None

    nid = n.get("id")
    level = (n.get("level") or "INFO")
    force = bool(n.get("force") is True)
    title = n.get("title") or ""
    content = n.get("content") or ""

    if not isinstance(nid, str) or not nid.strip():
        return False, 'invalid response: "id"', None
    if not isinstance(level, str) or not level.strip():
        level = "INFO"
    if not isinstance(title, str):
        title = str(title)
    if not isinstance(content, str):
        content = str(content)

    info = NoticeInfo(
        notice_id=nid.strip(),
        level=level.strip().upper(),
        force=force,
        title=title.strip(),
        content=content.strip(),
    )
    return True, "ok", info