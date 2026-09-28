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
MAP_HEADERS = ["CAREPLE_MUID", "MESSAGE_BALANCE_HISTORY_ID", "TRANSACTION_TYPE_CD", "AMOUNT", "CREATE_DT"]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def as_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


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


def request_json(payload):
    tuid = next((x.split("=", 1)[1].strip() for x in COOKIE.split(";") if x.strip().startswith("tuid=")), "")
    headers = {
        "Accept": "*/*", "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.careplecenter.com/index.html", "Origin": "https://www.careplecenter.com",
        "Cookie": COOKIE, "tuid": tuid,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    error_last = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with urlopen(Request(API_URL, data=body, headers=headers, method="PUT"), timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            error_last = error
            if attempt < RETRY_COUNT:
                wait_seconds = min(30, attempt * 3)
                print(f"요청 실패 {attempt}/{RETRY_COUNT}: {error} / {wait_seconds}초 후 재시도")
                time.sleep(wait_seconds)
    raise RuntimeError(f"CareplePay 결제 이력 조회 실패: {error_last}")


def page_info(response):
    groups = ((response.get("data") or {}).get("resp") or [])
    if not groups:
        return 0, []
    return as_int(groups[0].get("totalPage")), groups[0].get("list") or []


def add_row(rows, maps, sequence, source, transaction_type, amount, before_balance, after_balance, create_dt, memo_suffix):
    if amount <= 0:
        return sequence
    muid = str(source.get("muid") or source.get("merchantUid") or "").strip()
    history_id = f"MBHPAY{sequence:08d}"
    rows.append({
        "MESSAGE_BALANCE_HISTORY_ID": history_id, "COMPANY_ID": COMPANY_ID,
        "TRANSACTION_TYPE_CD": transaction_type, "SEND_TYPE_CD": "",
        "AMOUNT": amount, "BEFORE_BALANCE": before_balance, "AFTER_BALANCE": after_balance,
        "TARGET_TYPE_CD": "CAREPLEPAY_PAYMENT", "TARGET_ID": muid,
        "MEMO": f"CareplePay {transaction_type} / sourceMuid={muid} {memo_suffix}".strip(), "CREATE_DT": create_dt,
    })
    maps.append({
        "CAREPLE_MUID": muid, "MESSAGE_BALANCE_HISTORY_ID": history_id,
        "TRANSACTION_TYPE_CD": transaction_type, "AMOUNT": amount, "CREATE_DT": create_dt,
    })
    return sequence + 1


def main():
    if not COOKIE.strip():
        raise ValueError("COOKIE에 최신 Careple 로그인 쿠키를 넣어주세요.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_items, page, max_page = [], 1, None
    while max_page is None or page <= max_page:
        payload = {
            "page": page, "limit": PAGE_SIZE, "orgIdList": None, "paymethodList": ["card", "account"],
            "statusList": ["paid", "cancelled", "failed", "paying", "refund"], "listTypeList": ["pay", "cancel"],
            "willRefundList": [], "userIdList": None, "muIdList": None, "startTime": START_TIME, "endTime": END_TIME,
        }
        response = request_json(payload)
        page_total, page_items = page_info(response)
        if max_page is None:
            max_page = page_total
        raw_items.extend(page_items)
        print(f"[{now_text()}] 충전/환불 {page}/{max_page} / {len(page_items)}건")
        if not page_items or page >= max_page:
            break
        page += 1

    unique = {}
    for wrapped in raw_items:
        item = wrapped.get("paymentAnnotationResp") or wrapped
        key = str(item.get("merchantUid") or wrapped.get("muid") or "").strip()
        if key:
            unique[key] = wrapped

    rows, maps, sequence = [], [], 1
    for wrapped in unique.values():
        source = wrapped.get("paymentAnnotationResp") or wrapped
        status = str(source.get("status") or "").lower()
        paid_amount = as_int(source.get("amount"))
        usable = as_int(source.get("usableAmt"))
        cancel_amount = as_int(source.get("cancelAmount"))
        refund_amount = as_int(source.get("refundAmount"))
        refund_total = max(cancel_amount, refund_amount)

        # 정상 결제는 충전. 환불/취소가 있는 건은 별도 REFUND 행까지 만든다.
        if status == "paid" or paid_amount > 0:
            # 결제 직후 잔액은 usableAmt + 이미 환불된 금액일 수 있으므로 원본 잔액을 우선 보존한다.
            after = usable + refund_total
            before = max(0, after - paid_amount)
            sequence = add_row(rows, maps, sequence, source, "CHARGE", paid_amount, before, after,
                               normalize_dt(source.get("paidAtStr") or source.get("regDtime")), f"status={status}")
        if refund_total > 0 or status in ("cancelled", "refund"):
            # 환불 뒤 usableAmt가 최종 잔액으로 제공되므로 직전 잔액을 역산한다.
            after = usable
            before = max(0, after - refund_total)
            sequence = add_row(rows, maps, sequence, source, "REFUND", refund_total, before, after,
                               normalize_dt(source.get("refundAtStr") or source.get("modDtime")), f"status={status}")

        # 응답에 포함되는 세부 취소 이력도 원본에는 보존한다. 중복잔액 행은 만들지 않는다.

    with open(OUTPUT_DIR / "message_balance_payment_asis_raw.json", "w", encoding="utf-8") as file:
        json.dump(list(unique.values()), file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_balance_payment_tobe_all.json", "w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_balance_history_charge_refund.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader(); writer.writerows(rows)
    with open(OUTPUT_DIR / "message_payment_id_map.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=MAP_HEADERS)
        writer.writeheader(); writer.writerows(maps)
    with open(OUTPUT_DIR / "message_balance_payment_summary.json", "w", encoding="utf-8") as file:
        json.dump({"source_count": len(unique), "db_count": len(rows)}, file, ensure_ascii=False, indent=2)
    print(f"완료: 충전/환불 잔액 {len(rows)}건 / {(OUTPUT_DIR / 'message_balance_history_charge_refund.csv').resolve()}")


if __name__ == "__main__":
    main()
