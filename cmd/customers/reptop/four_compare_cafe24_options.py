#!/usr/bin/env python3
"""
revelove.csv와 cafe24_options.csv를 상품명으로 매칭하여
기존 옵션(before옵션)과 신규 옵션(after옵션)을 나란히 저장한다.

같은 실행 폴더에 아래 파일을 둔 뒤 실행한다.
    - revelove.csv
    - cafe24_options.csv

실행:
    python compare_cafe24_options.py

결과:
    revelove_option_compare.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_BEFORE_FILE = "revelove.csv"
DEFAULT_AFTER_FILE = "cafe24_options.csv"
DEFAULT_OUTPUT_FILE = "revelove_option_compare.csv"

PRODUCT_NAME_COLUMN = "상품명"
OPTION_COLUMN = "옵션입력"
BEFORE_OPTION_COLUMN = "before옵션"
AFTER_OPTION_COLUMN = "after옵션"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="상품명으로 Cafe24 기존/신규 옵션을 비교합니다."
    )
    parser.add_argument("--before", default=DEFAULT_BEFORE_FILE)
    parser.add_argument("--after", default=DEFAULT_AFTER_FILE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE)
    return parser.parse_args()


def decode_csv(path: Path) -> Tuple[str, str]:
    raw = path.read_bytes()

    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise ValueError(f"CSV 인코딩을 확인할 수 없습니다: {path}")


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    text, encoding = decode_csv(path)
    reader = csv.DictReader(text.splitlines())

    if not reader.fieldnames:
        raise ValueError(f"CSV 헤더가 없습니다: {path}")

    fieldnames = list(reader.fieldnames)
    rows = [dict(row) for row in reader]
    print(f"읽기: {path} | {len(rows)}개 | {encoding}")
    return fieldnames, rows


def normalize_product_name(value: str) -> str:
    """앞뒤 공백과 연속 공백 차이만 제거하여 상품명을 매칭한다."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def validate_columns(path: Path, fieldnames: List[str]) -> None:
    required = {PRODUCT_NAME_COLUMN, OPTION_COLUMN}
    missing = required - set(fieldnames)

    if missing:
        raise ValueError(
            f"{path}에 필수 컬럼이 없습니다: {', '.join(sorted(missing))}"
        )


def build_after_option_map(rows: List[Dict[str, str]]) -> Tuple[Dict[str, str], int]:
    option_map: Dict[str, str] = {}
    duplicate_count = 0

    for row in rows:
        product_name = normalize_product_name(row.get(PRODUCT_NAME_COLUMN, ""))
        option_input = str(row.get(OPTION_COLUMN, "") or "").strip()

        if not product_name:
            continue

        if product_name in option_map:
            duplicate_count += 1
            # 동일 상품명이 여러 번 있으면 비어 있지 않은 옵션을 우선한다.
            if not option_map[product_name] and option_input:
                option_map[product_name] = option_input
            continue

        option_map[product_name] = option_input

    return option_map, duplicate_count


def merge_options(
    before_rows: List[Dict[str, str]],
    after_option_map: Dict[str, str],
) -> Tuple[List[Dict[str, str]], int, int]:
    result: List[Dict[str, str]] = []
    matched_count = 0
    unmatched_count = 0

    for source_row in before_rows:
        row = dict(source_row)
        product_name = normalize_product_name(row.get(PRODUCT_NAME_COLUMN, ""))

        row[BEFORE_OPTION_COLUMN] = str(row.get(OPTION_COLUMN, "") or "").strip()

        if product_name in after_option_map:
            row[AFTER_OPTION_COLUMN] = after_option_map[product_name]
            matched_count += 1
        else:
            row[AFTER_OPTION_COLUMN] = ""
            unmatched_count += 1

        result.append(row)

    return result, matched_count, unmatched_count


def write_csv(
    path: Path,
    original_fieldnames: List[str],
    rows: List[Dict[str, str]],
) -> None:
    # 재실행해도 비교 컬럼이 중복되지 않도록 기존 이름은 제거 후 맨 끝에 붙인다.
    fieldnames = [
        name
        for name in original_fieldnames
        if name not in {BEFORE_OPTION_COLUMN, AFTER_OPTION_COLUMN}
    ]
    fieldnames.extend([BEFORE_OPTION_COLUMN, AFTER_OPTION_COLUMN])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    before_path = Path(args.before)
    after_path = Path(args.after)
    output_path = Path(args.output)

    if not before_path.exists():
        raise FileNotFoundError(f"기존 옵션 파일이 없습니다: {before_path.resolve()}")
    if not after_path.exists():
        raise FileNotFoundError(f"신규 옵션 파일이 없습니다: {after_path.resolve()}")

    before_fieldnames, before_rows = read_csv(before_path)
    after_fieldnames, after_rows = read_csv(after_path)

    validate_columns(before_path, before_fieldnames)
    validate_columns(after_path, after_fieldnames)

    after_option_map, duplicate_count = build_after_option_map(after_rows)
    result_rows, matched_count, unmatched_count = merge_options(
        before_rows,
        after_option_map,
    )

    write_csv(output_path, before_fieldnames, result_rows)

    print()
    print(f"완료: {output_path.resolve()}")
    print(f"상품명 매칭: {matched_count}개")
    print(f"상품명 미매칭: {unmatched_count}개")
    print(f"신규 파일 중복 상품명: {duplicate_count}개")


if __name__ == "__main__":
    main()
