# -*- coding: utf-8 -*-
import os
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


# =========================
# 설정
# =========================
INPUT_CSV = "yeogi_places_20260312_204547.csv"
OUT_PREFIX = "yeogi_place_contract"

# === 신규 === 원본 CSV + API 결과 컬럼 한글 매핑
OUTPUT_COLUMN_MAP = {
    # 원본 CSV 컬럼
    "id": "아이디",
    "keyword": "키워드",
    "category": "카테고리",
    "region": "시도",
    "city": "시군구",
    "name": "이름",
    "companyName": "상호",
    "ownerName": "대표자명",
    "licenseNumber": "사업자번호",
    "roadNameAddress": "주소",
    "email": "이메일",
    "tel": "전화번호",
    "mailOrderRegNo": "통신판매업 신고번호",
}

BASE = "https://www.yeogi.com"
URL_TPL = BASE + "/api/gateway/web-product-api/places/{id}/metas/contract"

MAX_WORKERS = 16
TIMEOUT_SEC = 10
MAX_RETRY = 4
SLEEP_BETWEEN_RETRY_BASE = 0.6


# =========================
# 헤더
# =========================
def build_headers() -> Dict[str, str]:
    return {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
        # 필요 시 최신 쿠키로 갱신
        "cookie": "__cf_bm=px11zByBo8IcaRNlNOQ777Qre6XxHnYGkXvshuqWZb8-1765938523-1.0.1.1-HIPIo9eVf_ASwOV100y5zj0Y0UV2yNRvg6nwFb52.zOw8av8bUm4CNs7QVMUwW9kInD5uvu7EOwhNV1K2zGyzJBrFgTpZtrF_IGyJdCq5vI",
    }


# =========================
# 로깅
# =========================
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# =========================
# 요청 + 재시도
# =========================
def fetch_contract(place_id: int, headers: Dict[str, str]) -> Dict[str, Any]:
    """
    성공: {"id":..., ...body fields...}
    실패: {"id":..., "_error": "...", "_status": ..., "_url": ...}
    """
    url = URL_TPL.format(id=place_id)
    last_err: Optional[str] = None
    last_status: Optional[int] = None

    session = requests.Session()

    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = session.get(url, headers=headers, timeout=TIMEOUT_SEC)
            last_status = res.status_code

            if res.status_code == 200:
                data = res.json()
                body = data.get("body", {}) or {}

                out = {"id": place_id}
                if isinstance(body, dict):
                    out.update(body)
                else:
                    out["body_raw"] = str(body)
                return out

            if res.status_code in (403, 429, 500, 502, 503, 504):
                last_err = f"HTTP {res.status_code}"
                sleep_s = (SLEEP_BETWEEN_RETRY_BASE * attempt) + random.random() * 0.3
                time.sleep(sleep_s)
                continue

            return {
                "id": place_id,
                "_error": f"HTTP {res.status_code}",
                "_status": res.status_code,
                "_url": url,
            }

        except Exception as e:
            last_err = str(e)
            sleep_s = (SLEEP_BETWEEN_RETRY_BASE * attempt) + random.random() * 0.3
            time.sleep(sleep_s)

    return {
        "id": place_id,
        "_error": last_err or "unknown error",
        "_status": last_status,
        "_url": url,
    }


# =========================
# 메인
# =========================
def main():
    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없음: {INPUT_CSV}")

    src_df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")

    required_cols = ["keyword", "category", "id", "name", "region", "city"]
    missing_cols = [c for c in required_cols if c not in src_df.columns]
    if missing_cols:
        raise ValueError(f"입력 CSV에 필요한 컬럼이 없습니다: {missing_cols}")

    # =========================
    # 원본 데이터 정리
    # =========================
    work_df = src_df.copy()

    # id 숫자 변환
    work_df["id"] = pd.to_numeric(work_df["id"], errors="coerce")
    work_df = work_df[work_df["id"].notna()].copy()
    work_df["id"] = work_df["id"].astype(int)

    total_rows = len(work_df)
    ids = work_df["id"].drop_duplicates().tolist()
    total_unique_ids = len(ids)

    log(f"입력 행 로드 완료: total_rows={total_rows}, total_unique_ids={total_unique_ids}")

    headers = build_headers()
    results: List[Dict[str, Any]] = []

    ok = 0
    fail = 0

    # =========================
    # id 기준 API 호출
    # =========================
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_map = {ex.submit(fetch_contract, pid, headers): pid for pid in ids}

        done_cnt = 0
        for fut in as_completed(future_map):
            pid = future_map[fut]
            done_cnt += 1

            try:
                row = fut.result()
            except Exception as e:
                row = {
                    "id": pid,
                    "_error": str(e),
                    "_status": None,
                    "_url": URL_TPL.format(id=pid),
                }

            results.append(row)

            if "_error" in row:
                fail += 1
                log(f"[{done_cnt}/{total_unique_ids}] FAIL id={pid} err={row.get('_error')}")
            else:
                ok += 1
                log(f"[{done_cnt}/{total_unique_ids}] OK   id={pid} companyName={row.get('companyName')}")

    # API 결과 df
    api_df = pd.DataFrame(results)

    # =========================
    # 원본 CSV + API 결과 merge
    # =========================
    out_df = work_df.merge(api_df, on="id", how="left")

    # =========================
    # 컬럼 순서 정리
    # =========================
    preferred_front = [
        # 원본 CSV
        "id",
        "keyword",
        "category",
        "region",
        "city",
        "name",        # API 결과
        "companyName",
        "ownerName",
        "licenseNumber",
        "roadNameAddress",
        "email",
        "tel",
        "mailOrderRegNo",
    ]

    cols = list(out_df.columns)
    front = [c for c in preferred_front if c in cols]
    tail = [c for c in ["_error", "_status", "_url"] if c in cols]
    middle = [c for c in cols if c not in set(front + tail)]
    out_df = out_df[front + middle + tail]

    # =========================
    # 한글 컬럼명 변경
    # =========================
    out_df = out_df.rename(columns=OUTPUT_COLUMN_MAP)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUT_PREFIX}_{ts}.xlsx"

    out_df.to_excel(out_path, index=False)

    log(f"완료: ok={ok}, fail={fail}, total_rows={len(out_df)}, saved={out_path}")


if __name__ == "__main__":
    main()