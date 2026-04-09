# -*- coding: utf-8 -*-
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import requests


BASE_DIR = Path.cwd() / "excel"
API_URL = "https://coco-label.com/ajax/oms/OMS_get_product.cm"
MAX_WORKERS = 8

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "authority": "coco-label.com",
    "method": "GET",
    "path": "/ajax/oms/OMS_get_products.cm",
    "priority": "u=1, i",
    "scheme": "https",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
}


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_one(row_idx: int, idx: str, referer: str) -> tuple[int, str, str]:
    headers = dict(HEADERS)
    headers["referer"] = referer

    params = {"prod_idx": idx}

    log(f"[요청] row={row_idx + 1} idx={idx} referer={referer}")

    res = requests.get(API_URL, headers=headers, params=params, timeout=20)
    res.raise_for_status()

    data = res.json()
    simple_text = str(((data.get("data") or {}).get("simple_content_plain")) or "").strip()

    return row_idx, idx, simple_text


def process_excel_file(file_path: Path) -> None:
    log("=" * 100)
    log(f"[엑셀 시작] {file_path}")

    df = pd.read_excel(file_path, dtype=str)

    if "상품코드" not in df.columns or "URL" not in df.columns:
        log(f"[스킵] 필수 컬럼 없음: {file_path.name}")
        return

    if "기본설명" not in df.columns:
        df["기본설명"] = ""

    if "상품옵션1" not in df.columns:
        df["상품옵션1"] = ""

    jobs: list[tuple[int, str, str]] = []
    for i, row in df.iterrows():
        idx = str(row.get("상품코드") or "").strip()
        referer = str(row.get("URL") or "").strip()

        if not idx or not referer:
            log(f"[스킵] row={i + 1} 상품코드 또는 URL 없음")
            continue

        jobs.append((i, idx, referer))

    log(f"[엑셀 정보] 전체행={len(df)} 요청대상={len(jobs)}")

    success_count = 0
    empty_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(fetch_one, row_idx, idx, referer)
            for row_idx, idx, referer in jobs
        ]

        done_count = 0

        for future in as_completed(futures):
            done_count += 1

            try:
                row_idx, idx, simple_text = future.result()

                if simple_text:
                    df.at[row_idx, "기본설명"] = simple_text

                    if is_empty(df.at[row_idx, "상품옵션1"]):
                        df.at[row_idx, "상품옵션1"] = f"옵션1|{simple_text}"
                        log(f"[옵션입력] row={row_idx + 1} idx={idx} 상품옵션1=옵션1|{simple_text}")
                    else:
                        log(f"[옵션유지] row={row_idx + 1} idx={idx} 상품옵션1 기존값 유지")

                    success_count += 1
                    log(
                        f"[성공] {done_count}/{len(jobs)} "
                        f"row={row_idx + 1} idx={idx} 기본설명={simple_text}"
                    )
                else:
                    empty_count += 1
                    log(
                        f"[빈값] {done_count}/{len(jobs)} "
                        f"row={row_idx + 1} idx={idx} simple_content_plain 없음"
                    )

            except Exception as e:
                fail_count += 1
                log(f"[실패] {done_count}/{len(jobs)} {e}")

    new_file = file_path.with_name(f"{file_path.stem}_new{file_path.suffix}")
    df.to_excel(new_file, index=False)

    log(
        f"[엑셀 완료] {file_path.name} "
        f"성공={success_count} 빈값={empty_count} 실패={fail_count} 저장={new_file.name}"
    )


def main() -> None:
    log(f"[시작] BASE_DIR={BASE_DIR}")

    if not BASE_DIR.exists():
        log(f"[종료] excel 폴더가 없습니다: {BASE_DIR}")
        return

    excel_exts = {".xlsx", ".xls"}
    folder_count = 0
    file_count = 0

    for folder in sorted(BASE_DIR.iterdir()):
        if not folder.is_dir():
            continue

        folder_count += 1
        log("")
        log(f"[폴더 시작] {folder.name}")

        for file_path in sorted(folder.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in excel_exts:
                continue
            if file_path.stem.endswith("_new"):
                log(f"[스킵] 이미 생성된 파일 제외: {file_path.name}")
                continue

            file_count += 1
            process_excel_file(file_path)

        log(f"[폴더 완료] {folder.name}")

    log("")
    log(f"[전체 완료] 폴더수={folder_count} 파일수={file_count}")


if __name__ == "__main__":
    main()