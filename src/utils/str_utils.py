# ./src/utils/str_utils.py
from __future__ import annotations

import re
from typing import Optional, List
from urllib.parse import urlparse, parse_qs


NBSP_RE = re.compile(r"[\u00a0\u200b]")  # NBSP, zero-width space


def split_comma_keywords(keyword_str: Optional[str]) -> List[str]:
    """
    콤마로 구분된 키워드 문자열을 리스트로 변환
    None 안전 처리
    """
    if not keyword_str:
        return []
    return [k.strip() for k in keyword_str.split(",") if k.strip()]


def extract_numbers(text: Optional[str]) -> List[int]:
    """
    문자열에서 모든 숫자(연속된 숫자 덩어리)를 리스트로 반환
    예: "in total 352 albums and 12 tracks" → [352, 12]
    """
    if not text:
        return []
    return [int(num) for num in re.findall(r"\d+", text)]


def get_query_params(url: str, name: str) -> Optional[str]:
    """
    URL에서 특정 query param 값 1개 반환
    없으면 None
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    values = query_params.get(name)
    if not values:
        return None
    return values[0]


def str_norm(s: Optional[str]) -> str:
    """
    NBSP/zero-width 제거 후 strip
    특수공백을 일반 스페이스로 변환
    """
    if not s:
        return ""
    return NBSP_RE.sub(" ", s).strip()


def str_clean(s: Optional[str]) -> str:
    """
    NBSP 제거 후 strip
    """
    if not s:
        return ""
    return s.replace("\u00a0", " ").strip()


def to_str(v: object, default: str = "") -> str:
    """
    None/빈문자열이면 default 반환
    """
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default