# ./src/utils/number_utils.py
from __future__ import annotations  # === 신규 ===

from math import floor
import re
from typing import Optional, Tuple, Union


Number = Union[int, float]


def divide_and_truncate(param1: Number, param2: Number, digits: int = 4) -> float:
    """
    나누기 후 소수점 digits 자리까지 '버림'(truncate)
    - digits 기본값: 4 (기존 코드 동작 유지)
    """
    if param2 == 0:
        return 0.0

    scale = 10 ** int(digits)
    result = float(param1) / float(param2)
    return floor(result * scale) / scale


def divide_and_truncate_per(param1: Number, param2: Number, digits: int = 4) -> float:
    """
    (param1/param2) * 100 값을 소수점 digits 자리까지 '버림'
    - digits 기본값: 4 (기존 코드 동작 유지)
    """
    if param2 == 0:
        return 0.0

    return divide_and_truncate(param1, param2, digits=digits) * 100.0


def calculate_divmod(total_cnt: int, divisor: int = 30) -> Tuple[int, int]:
    quotient = total_cnt // divisor
    remainder = total_cnt % divisor
    return quotient, remainder


def to_int_digits(s: Optional[str]) -> int:
    """'1,234원' -> 1234"""
    if not s:
        return 0
    nums = re.findall(r"\d+", s)
    return int("".join(nums)) if nums else 0


def to_int(v: object, default: int = 0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(str(v).replace(",", ""))
    except Exception:
        return default


def to_float(v: object, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(",", ""))
    except Exception:
        return default