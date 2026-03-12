# -*- coding: utf-8 -*-
import time
import random
from datetime import datetime
from urllib.parse import quote
import requests
import pandas as pd

# =========================
# 설정
# =========================
KEYWORDS = [
    "경기", "제주도", "서울", "인천", "대구", "대전", "충남", "경남",
    "부산", "전북", "울산", "광주", "강원", "경북", "전남", "충북", "세종"
]

CATEGORY_MAP = {
    1: "모텔",
    2: "호텔·리조트",
    3: "펜션",
    15: "홈&빌라",
    5: "캠핑",
    18: "게하·한옥",
}

CHECK_IN = "2026-05-11"
CHECK_OUT = "2026-05-12"
LIMIT = 1000

BASE = "https://www.yeogi.com"
API_PATH = "/api/gateway/web-product-api/places/search"


# =========================
# 유틸
# =========================
def build_referer(keyword_kr: str, category: int, page: int) -> str:
    return (
        f"{BASE}/domestic-accommodations"
        f"?sortType=RECOMMEND"
        f"&keyword={quote(keyword_kr)}"
        f"&personal=2"
        f"&checkIn={CHECK_IN}&checkOut={CHECK_OUT}"
        f"&category={category}"
        f"&page={page}"
    )


def build_api_url(keyword_kr: str, category: int, page: int) -> str:
    return (
        f"{BASE}{API_PATH}"
        f"?category={category}"
        f"&sortType=RECOMMEND"
        f"&keyword={quote(keyword_kr)}"
        f"&page={page}"
        f"&personal=2"
        f"&checkIn={CHECK_IN}&checkOut={CHECK_OUT}"
        f"&limit={LIMIT}"
    )


def base_headers(referer: str) -> dict:
    # "필요한 것만" 위주로 최소 구성
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
        "referer": referer,

        # yeogi에서 자주 쓰는 커스텀 헤더
        "x-api-max-version": "2.0.0",
        "x-channel": "YEOGI",
        "x-device-id": "WEB",
        "x-device-platform": "NEW_WEB",

        # 사용자가 준 priority
        "priority": "u=1, i",
    }


def safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return cur


def request_json(session: requests.Session, url: str, headers: dict, max_retry: int = 5) -> dict:
    last_err = None
    for attempt in range(1, max_retry + 1):
        try:
            r = session.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.json()

            # 흔한 제한/오류 대응
            if r.status_code in (429, 500, 502, 503, 504):
                sleep_s = min(8, 1.2 * attempt) + random.random()
                time.sleep(sleep_s)
                continue

            r.raise_for_status()

        except Exception as e:
            last_err = e
            sleep_s = min(8, 1.2 * attempt) + random.random()
            time.sleep(sleep_s)

    raise RuntimeError(f"Request failed: {url} / last_err={str(last_err)}")


# =========================
# 크롤러
# =========================
def warmup(session: requests.Session):
    # 쿠키/세션 세팅용 워밍업 (필수 아닐 수 있으나 안전빵)
    url = f"{BASE}/domestic-accommodations"
    headers = {
        "user-agent": base_headers(url)["user-agent"],
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        session.get(url, headers=headers, timeout=20)
    except Exception:
        pass


def crawl_all() -> pd.DataFrame:
    session = requests.Session()
    warmup(session)

    out_rows = []
    total_cnt = 0          # 전체 누적 개수
    req_cnt = 0            # === 신규 === API 요청 횟수

    for kw in KEYWORDS:
        for cat, cat_kr in CATEGORY_MAP.items():
            page = 1
            seen_ids = set()

            print(f"\n[START] keyword='{kw}' | category='{cat_kr}'")

            while True:
                req_cnt += 1  # === 신규 ===

                referer = build_referer(kw, cat, page)
                url = build_api_url(kw, cat, page)
                headers = base_headers(referer)

                print(f"[REQ #{req_cnt}] keyword='{kw}' | category='{cat_kr}' | page={page}")

                data = request_json(session, url, headers)
                body = safe_get(data, "body", default={}) or {}
                items = safe_get(body, "items", default=[]) or []

                if not items:
                    print(f"[END PAGE] keyword='{kw}' | category='{cat_kr}' | page={page} -> items=0 (종료)")
                    break

                added_this_page = 0
                for it in items:
                    meta = safe_get(it, "meta", default={}) or {}
                    braze = safe_get(it, "braze", default={}) or {}

                    place_id = safe_get(meta, "id", default=None)
                    name = safe_get(meta, "name", default=None)

                    # 무한루프 방지: 같은 데이터만 반복되면 컷
                    if place_id is not None and place_id in seen_ids:
                        continue
                    if place_id is not None:
                        seen_ids.add(place_id)

                    region = safe_get(braze, "region", default=None)
                    city = safe_get(braze, "city", default=None)

                    out_rows.append({
                        "keyword": kw,
                        "category": cat_kr,
                        "id": place_id,
                        "name": name,
                        "region": region,
                        "city": city,
                    })
                    added_this_page += 1

                total_cnt += added_this_page

                print(
                    f"[PAGE DONE] keyword='{kw}' | category='{cat_kr}' | "
                    f"page={page} | added={added_this_page} | total={total_cnt}"
                )

                # 페이지당 추가가 0이면(전부 중복) 종료
                if added_this_page == 0:
                    print(f"[STOP] keyword='{kw}' | category='{cat_kr}' | page={page} -> added=0 (중복만 발생)")
                    break

                time.sleep(0.25 + random.random() * 0.25)
                page += 1

            print(f"[FINISH] keyword='{kw}' | category='{cat_kr}' | 누적={total_cnt}")

    df = pd.DataFrame(out_rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["keyword", "category", "id"], keep="first").reset_index(drop=True)
    return df


def main():
    df = crawl_all()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"yeogi_places_{ts}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] rows={len(df)} saved => {out_path}")


if __name__ == "__main__":
    main()
