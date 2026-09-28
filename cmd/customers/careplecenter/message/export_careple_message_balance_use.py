import csv
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

# 최신 브라우저 쿠키만 넣어 실행하세요.
COOKIE = ""
COMPANY_ID = "COMPANY000001"
START_TIME = "2024-07-01 00:00:00"
END_TIME = "2026-09-17 23:59:59"
PAGE_SIZE = 100
RETRY_COUNT = 7

API_URL = "https://www.careplecenter.com/pcareple/v1/careplepay/payments"
OUTPUT_DIR = Path("output") / "message"

HEADERS = [
    "MESSAGE_BALANCE_HISTORY_ID", "COMPANY_ID", "TRANSACTION_TYPE_CD", "SEND_TYPE_CD",
    "AMOUNT", "BEFORE_BALANCE", "AFTER_BALANCE", "TARGET_TYPE_CD", "TARGET_ID", "MEMO", "CREATE_DT",
]
MAP_HEADERS = [
    "CAREPLE_USE_ID", "MESSAGE_BALANCE_HISTORY_ID", "SEND_TYPE_CD", "AMOUNT", "USED_DT", "AFTER_BALANCE",
]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_dt(value):
    value = str(value or "").strip().replace("T", " ").replace("Z", "")
    if not value:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return value


def as_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def send_type(name):
    name = str(name or "").strip().lower()
    if name in ("alimtalk", "al imtalk", "kakao"):
        return "KAKAO"
    if name == "lms":
        return "LMS"
    if name == "sms":
        return "SMS"
    return (name or "UNKNOWN").upper()


def request_json(payload):
    tuid = next((x.split("=", 1)[1].strip() for x in COOKIE.split(";") if x.strip().startswith("tuid=")), "")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "*/*", "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.careplecenter.com/index.html", "Origin": "https://www.careplecenter.com",
        "Cookie": COOKIE, "tuid": tuid,
    }
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            request = Request(API_URL, data=body, headers=headers, method="PUT")
            with urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt == RETRY_COUNT:
                break
            wait_seconds = min(30, attempt * 3)
            print(f"요청 실패 {attempt}/{RETRY_COUNT}: {error} / {wait_seconds}초 후 재시도")
            time.sleep(wait_seconds)
    raise RuntimeError(f"CareplePay 사용 이력 조회 실패: {last_error}")


def response_list(response):
    # Careple 응답: data.resp[0].list
    groups = ((response.get("data") or {}).get("resp") or [])
    return (groups[0].get("list") or []) if groups else []


def total_page(response):
    groups = ((response.get("data") or {}).get("resp") or [])
    return as_int(groups[0].get("totalPage")) if groups else 0


def main():
    if not COOKIE.strip():
        raise ValueError("COOKIE에 최신 Careple 로그인 쿠키를 넣어주세요.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_items = []
    page = 1
    max_page = None

    while max_page is None or page <= max_page:
        payload = {
            "page": page, "limit": PAGE_SIZE, "orgIdList": None, "paymethodList": None,
            "statusList": None, "listTypeList": ["use"], "willRefundList": [],
            "userIdList": None, "muIdList": None, "startTime": START_TIME, "endTime": END_TIME,
        }
        response = request_json(payload)
        if max_page is None:
            max_page = total_page(response)
        page_items = response_list(response)
        raw_items.extend(page_items)
        print(f"[{now_text()}] 사용잔액 {page}/{max_page} / {len(page_items)}건")
        if not page_items or page >= max_page:
            break
        page += 1

    # useId 기준 중복 제거
    unique = {}
    for item in raw_items:
        source_id = str(item.get("useId") or "").strip()
        if source_id:
            unique[source_id] = item

    db_rows, map_rows = [], []
    for index, item in enumerate(unique.values(), start=1):
        source_id = str(item.get("useId") or "").strip()
        history_id = f"MBHUSE{index:08d}"
        amount = as_int(item.get("usedAmt"))
        after_balance = as_int(item.get("usableAmt"))
        # USE 거래는 '사용 후 잔액 + 사용금액'으로 직전 잔액을 역산한다.
        before_balance = after_balance + amount
        type_cd = send_type(item.get("name"))
        used_dt = normalize_dt(item.get("regTime") or item.get("modTime"))
        memo = f"CareplePay USE / sourceUseId={source_id} / sourceName={item.get('name') or ''}"
        db_rows.append({
            "MESSAGE_BALANCE_HISTORY_ID": history_id, "COMPANY_ID": COMPANY_ID,
            "TRANSACTION_TYPE_CD": "USE", "SEND_TYPE_CD": type_cd,
            "AMOUNT": amount, "BEFORE_BALANCE": before_balance, "AFTER_BALANCE": after_balance,
            "TARGET_TYPE_CD": "CAREPLEPAY_USE", "TARGET_ID": source_id, "MEMO": memo, "CREATE_DT": used_dt,
        })
        map_rows.append({
            "CAREPLE_USE_ID": source_id, "MESSAGE_BALANCE_HISTORY_ID": history_id,
            "SEND_TYPE_CD": type_cd, "AMOUNT": amount, "USED_DT": used_dt, "AFTER_BALANCE": after_balance,
        })

    with open(OUTPUT_DIR / "message_balance_use_asis_raw.json", "w", encoding="utf-8") as file:
        json.dump(list(unique.values()), file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_balance_use_tobe_all.json", "w", encoding="utf-8") as file:
        json.dump(db_rows, file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_balance_history_use.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader(); writer.writerows(db_rows)
    with open(OUTPUT_DIR / "message_use_id_map.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=MAP_HEADERS)
        writer.writeheader(); writer.writerows(map_rows)
    with open(OUTPUT_DIR / "message_balance_use_summary.json", "w", encoding="utf-8") as file:
        json.dump({"source_count": len(unique), "db_count": len(db_rows)}, file, ensure_ascii=False, indent=2)
    print(f"완료: 사용잔액 {len(db_rows)}건 / {(OUTPUT_DIR / 'message_balance_history_use.csv').resolve()}")


if __name__ == "__main__":
    main()
