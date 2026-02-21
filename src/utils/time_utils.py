# ./src/utils/time_utils.py
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional, Union

from src.utils.str_utils import str_clean


SEOUL_TZ = ZoneInfo("Asia/Seoul")


def get_current_yyyymmddhhmmss() -> str:
    """현재 날짜/시간을 'yyyymmddhhmmss'로 반환 (Asia/Seoul 기준)"""
    now = datetime.now(SEOUL_TZ)
    return now.strftime("%Y%m%d%H%M%S")


def parse_timestamp(ymd_hms_text: Optional[str]) -> int:
    """'YYYY/MM/DD \\nHH:MM:SS' -> epoch seconds (Asia/Seoul 기준)"""
    t = str_clean(ymd_hms_text).replace("\n", " ").replace("  ", " ")
    parts = t.split()
    if len(parts) < 2:
        return 0

    ymd, hms = parts[0], parts[1]
    try:
        dt_naive = datetime.strptime(f"{ymd} {hms}", "%Y/%m/%d %H:%M:%S")
        dt = dt_naive.replace(tzinfo=SEOUL_TZ)  # ✅ 타임존 고정
        return int(dt.timestamp())
    except Exception:
        return 0


def format_real_date(ts: int) -> str:
    """epoch seconds -> 'YYYY-MM-DD HH:MM:SS' (Asia/Seoul)"""
    if ts <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ts, SEOUL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def parse_yy_mm_dd(d: Optional[str]) -> str:
    """'25.08.25' → '2025-08-25'"""
    s = (d or "").strip()
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%y.%m.%d").strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_date_yyyy_mm_dd(s: Optional[str]) -> Optional[date]:
    """'YYYY-MM-DD' -> date 또는 None"""
    t = (s or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d").date()
    except Exception:
        return None


def parse_finish_dt(dt_str: Optional[str]) -> str:
    """'2025-08-31 23:59:00.0' → '2025-08-31'"""
    t = (dt_str or "").strip()
    if not t:
        return ""
    try:
        return datetime.strptime(t.split()[0], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_datetime_yyyy_mm_dd_hhmmss(s: Optional[str]) -> Optional[datetime]:
    """'2025-11-11 00:00:00' → datetime(naive) 또는 None"""
    t = (s or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def parse_datetime_to_yyyymmdd(s: Optional[str]) -> str:
    """
    '2025-11-11' → '20251111'
    '2025-11-11 00:00:00' → '20251111'
    """
    t = (s or "").strip()
    if not t:
        return ""

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
        except Exception:
            return ""

    return ""


def format_yyyymmdd_to_yyyy_mm_dd(s: Optional[str]) -> str:
    """'20251123' → '2025-11-23'"""
    t = (s or "").strip()
    if not t:
        return ""
    try:
        return datetime.strptime(t, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return ""


def ms_to_yyyy_mm_dd(ms: Union[int, str, None]) -> str:
    """milliseconds -> 'YYYY-MM-DD' (Asia/Seoul)"""
    if ms is None:
        return ""
    try:
        v = int(ms)
        return datetime.fromtimestamp(v / 1000, SEOUL_TZ).strftime("%Y-%m-%d")
    except Exception:
        return ""