import requests
import json
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ==================================================
# 기본 설정
# ==================================================
API_URL = "https://nol.yanolja.com/api/v2/list/local-accommodation/v3/search"

_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def create_options():
    return {
        "checkInDate": "2026-08-31",
        "checkOutDate": "2026-09-01",
        "capacityAdults": 2,
        "childrenAges": [],
        "filters": [],
        "sort": "RECOMMEND",
        "maxPages": 500,
        "sleepSec": 0.2,
        "logIdsLimit": 0,          # 0이면 전체 출력, 예: 30이면 앞 30개만
        "logIdsJoiner": ",",       # id 출력 구분자
        "maxWorkers": 8,           # === 신규 === 멀티 쓰레드 개수
    }


# ==================================================
# 카테고리 / 지역 정의
# ==================================================
def build_categories():
    return [
        {
            "topCategory": "호텔/리조트",
            "pageName": "HOTEL",
            "searchType": "hotel",
            "regions": [
                {"name": "서울", "code": 900582},
                {"name": "부산", "code": 900583},
                {"name": "제주", "code": 900584},
                {"name": "경기", "code": 900585},
                {"name": "인천", "code": 900586},
                {"name": "강원", "code": 900587},
                {"name": "경상", "code": 900588},
                {"name": "전라", "code": 900589},
                {"name": "충청", "code": 900590},
            ],
        },
        {
            "topCategory": "펜션/풀빌라",
            "pageName": "PENSION",
            "searchType": "pension",
            "regions": [
                {"name": "가평", "code": 910252},
                {"name": "강원", "code": 900592},
                {"name": "경기", "code": 900591},
                {"name": "인천", "code": 900594},
                {"name": "충남", "code": 900595},
                {"name": "충북", "code": 900596},
                {"name": "경북", "code": 900598},
                {"name": "경남", "code": 910224},
                {"name": "전남", "code": 900599},
                {"name": "전북", "code": 900600},
                {"name": "제주", "code": 900593},
                {"name": "부산", "code": 900272},
                {"name": "울산", "code": 900575},
                {"name": "서울", "code": 900270},
            ],
        },
    ]


# ==================================================
# HTTP / Payload
# ==================================================
def build_headers(referer):
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://nol.yanolja.com",
        "platform": "Web",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }


def build_payload(page, pageName, searchType, region, opt):
    # 제외: locationTime, locationType, longitude, latitude (payload에 아예 안 넣음)
    return {
        "page": page,
        "sort": opt["sort"],
        "pageName": pageName,
        "searchType": searchType,
        "region": region,
        "filters": opt["filters"],
        "checkInDate": opt["checkInDate"],
        "checkOutDate": opt["checkOutDate"],
        "capacityAdults": opt["capacityAdults"],
        "childrenAges": opt["childrenAges"],
    }


# ==================================================
# API 호출
# ==================================================
def post_search(session, headers, payload):
    res = session.post(
        API_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=30
    )
    res.raise_for_status()
    return res.json()


# ==================================================
# 응답 파싱
# ==================================================
def parse_items(resp):
    rows = []

    for it in resp.get("items") or []:
        data = it.get("data") or {}

        pid = data.get("id")
        title = data.get("title")
        location = data.get("locationDetails") or []

        if not pid or not title:
            continue

        rows.append({
            "id": str(pid),
            "title": title,
            "locationDetails": location
        })

    return rows


def page_signature(rows):
    sig = []
    for r in rows:
        sig.append(
            r["id"]
            + "|"
            + r["title"]
            + "|"
            + json.dumps(r["locationDetails"], ensure_ascii=False)
        )
    return tuple(sig)


# ==================================================
# 로그
# ==================================================
def log_request_result(category, region, page, page_rows, region_total, opt, reason):
    ids = []
    for r in page_rows:
        ids.append(r.get("id", ""))

    limit = opt.get("logIdsLimit", 0) or 0
    joiner = opt.get("logIdsJoiner", ",")

    if limit > 0 and len(ids) > limit:
        shown = ids[:limit]
        ids_text = joiner.join(shown) + joiner + "...(+" + str(len(ids) - limit) + ")"
    else:
        ids_text = joiner.join(ids)

    safe_print(
        "[REQ DONE] topCategory={}".format(category["topCategory"])
        + " | region={}(#{})".format(region["name"], region["code"])
        + " | page={}".format(page)
        + " | success={}".format(len(page_rows))
        + " | region_total={}".format(region_total)
        + " | reason={}".format(reason)
    )
    safe_print("  ids: " + ids_text)


# ==================================================
# region 단위 수집 (page는 순차)
# ==================================================
def fetch_region(session, category, region, opt):
    referer = (
        "https://nol.yanolja.com/local/list"
        "?type={}&region={}&shortcut={}"
    ).format(category["searchType"], region["code"], category["searchType"])

    headers = build_headers(referer)

    page = 1
    prev_sig = None
    collected = []

    while page <= opt["maxPages"]:
        payload = build_payload(
            page,
            category["pageName"],
            category["searchType"],
            region["code"],
            opt
        )

        resp = post_search(session, headers, payload)
        page_items = parse_items(resp)

        # === 로그: 요청 1번 끝 ===
        if not page_items:
            log_request_result(category, region, page, page_items, len(collected), opt, "STOP: empty items")
            break

        sig = page_signature(page_items)
        if sig == prev_sig:
            log_request_result(category, region, page, page_items, len(collected), opt, "STOP: same as prev page")
            break

        for r in page_items:
            collected.append({
                "topCategory": category["topCategory"],
                "pageName": category["pageName"],
                "searchType": category["searchType"],
                "regionCode": str(region["code"]),
                "regionName": region["name"],
                "id": r["id"],
                "title": r["title"],
                "locationDetails_json": json.dumps(r["locationDetails"], ensure_ascii=False)
            })

        log_request_result(category, region, page, page_items, len(collected), opt, "OK")

        prev_sig = sig
        page += 1
        time.sleep(opt["sleepSec"])

    return collected


# ==================================================
# 멀티스레드 래퍼
# - 스레드마다 Session을 따로 쓰는게 안전함
# ==================================================
def fetch_region_threadsafe(category, region, opt):
    with requests.Session() as session:
        return fetch_region(session, category, region, opt)


# ==================================================
# 전체 수집 (region을 8개 스레드로 병렬)
# ==================================================
def scrape_all(categories, opt):
    rows = []
    futures = []

    max_workers = opt.get("maxWorkers", 8) or 8

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for cat in categories:
            for region in cat["regions"]:
                futures.append(ex.submit(fetch_region_threadsafe, cat, region, opt))

        for fut in as_completed(futures):
            try:
                part = fut.result()
                if part:
                    rows.extend(part)
            except Exception as e:
                safe_print("[ERROR] worker failed: " + str(e))

    return rows


# ==================================================
# CSV 저장
# ==================================================
def write_csv(rows, path):
    if not rows:
        return

    fields = list(rows[0].keys())

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ==================================================
# main
# ==================================================
def main():
    categories = build_categories()
    options = create_options()

    rows = scrape_all(categories, options)
    write_csv(rows, "yanolja_local_accommodation.csv")

    safe_print("수집 완료: " + str(len(rows)))


if __name__ == "__main__":
    main()
