import csv
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = ""
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2026-09"
WORKERS = 6  # 4~8 사이

# DB를 비운 기준. 기존 수납 데이터를 유지하는 경우 마지막 번호만 수정하세요.
PAYMENT_ID_LAST_NO = 0
PAYMENT_DETAIL_ID_LAST_NO = 0
PAYMENT_CARRYOVER_ID_LAST_NO = 0

BASE_URL = "https://www.careplecenter.com"
PAYMENT_URL = BASE_URL + "/pcareple/v1/payment/all/{year}/{month:02d}"

MEMBER_MAP_PATH = Path("output/member/member_id_map.csv")
MEMBER_PROGRAM_MAP_PATH = Path("output/schedule/member_program_id_map.csv")
MONTHLY_SERVICE_PATH = Path("output/schedule/member_program_monthly_service_db.csv")
OUTPUT_DIR = Path("output/payment")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"
EMPTY_FILE = CHECKPOINT_DIR / "empty_keys.txt"

PAYMENT_MASTER_HEADERS = [
    "PAYMENT_ID", "COMPANY_ID", "MEMBER_ID", "PAYMENT_TARGET_TYPE_CD", "PAYMENT_TARGET_ID",
    "MEMBER_PROGRAM_ID", "PAYMENT_TYPE_CD", "PAYMENT_STATUS_CD", "TOTAL_AMOUNT", "PAID_AMOUNT",
    "REMAIN_AMOUNT", "CARRYOVER_USE_AMOUNT", "CARRYOVER_CREATE_AMOUNT", "PAYMENT_DT", "MEMO",
    "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "REF_PAYMENT_ID", "TARGET_YEAR_MONTH",
]
PAYMENT_DETAIL_HEADERS = [
    "PAYMENT_DETAIL_ID", "PAYMENT_ID", "PAYMENT_METHOD_CD", "PAY_AMOUNT", "APPROVAL_NO",
    "MEMO", "CREATE_DT", "UPDATE_DT", "USE_YN", "DELETE_YN",
]
PAYMENT_CARRYOVER_HEADERS = [
    "PAYMENT_CARRYOVER_ID", "COMPANY_ID", "MEMBER_ID", "MEMBER_PROGRAM_ID", "PAYMENT_ID",
    "FROM_YEAR_MONTH", "TO_YEAR_MONTH", "CARRYOVER_AMOUNT", "USED_AMOUNT", "REMAIN_AMOUNT",
    "STATUS_CD", "USED_DT", "MEMO", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
PAYMENT_MAP_HEADERS = [
    "CAREPLE_PM_ID", "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID", "SERVICE_YM",
    "PAYMENT_ID", "MEMBER_ID", "MEMBER_PROGRAM_ID",
]
UNMATCHED_HEADERS = ["CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID", "SERVICE_YM", "FIELD", "MESSAGE"]


def value(item):
    return str(item or "").strip()


def amount(item):
    try:
        return int(float(value(item).replace(",", "") or "0"))
    except ValueError:
        return 0


def date_time(item):
    text = value(item).replace("T", " ").replace("Z", "")
    if not text:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(f"날짜 형식을 확인하세요: {item}")


def payment_datetime(dtime):
    text = value(dtime)
    try:
        return datetime.strptime(text, "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return date_time(text)


def month_range(start_ym, end_ym):
    year, month = map(int, start_ym.split("-"))
    end_year, end_month = map(int, end_ym.split("-"))
    while (year, month) <= (end_year, end_month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def previous_ym(ym):
    year, month = map(int, ym.split("-"))
    year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return f"{year:04d}-{month:02d}"


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def checkpoint_path(vis_id, ym):
    path = CHECKPOINT_DIR / "nonempty" / f"{vis_id}_{ym.replace('-', '')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def request_retry(request_once, label):
    waits = (5, 15, 30, 60, 120, 300)
    for attempt in range(len(waits) + 1):
        try:
            return request_once()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            if attempt == len(waits):
                raise
            print(f"요청 실패 {attempt + 1}/{len(waits) + 1}: {label} / {error}")
            print(f"{waits[attempt]}초 후 재시도합니다.")
            time.sleep(waits[attempt])


def get_json(url, params):
    def request_once():
        request = Request(url + "?" + urlencode(params), headers=HEADERS)
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    return request_retry(request_once, url)


def read_member_map():
    if not MEMBER_MAP_PATH.exists():
        raise FileNotFoundError(f"{MEMBER_MAP_PATH} 파일이 없습니다. MEMBER 이관을 먼저 실행하세요.")
    result = {}
    for row in read_csv(MEMBER_MAP_PATH):
        vis_id, member_id = value(row.get("CAREPLE_VIS_ID")), value(row.get("MEMBER_ID"))
        if vis_id and member_id:
            result[vis_id] = member_id
    return result


def read_member_program_map():
    if not MEMBER_PROGRAM_MAP_PATH.exists() or not MONTHLY_SERVICE_PATH.exists():
        raise FileNotFoundError("output/schedule의 MEMBER_PROGRAM 이관 CSV를 먼저 생성하세요.")

    source_by_mp = {}
    for row in read_csv(MEMBER_PROGRAM_MAP_PATH):
        mp_id = value(row.get("MEMBER_PROGRAM_ID"))
        source = value(row.get("CAREPLE_VIS_ID")), value(row.get("CAREPLE_PROGRAM_ID")), value(row.get("CAREPLE_EMP_ID"))
        if mp_id and all(source):
            source_by_mp[mp_id] = source

    result = {}
    for row in read_csv(MONTHLY_SERVICE_PATH):
        mp_id, ym = value(row.get("MEMBER_PROGRAM_ID")), value(row.get("SERVICE_YM"))
        source = source_by_mp.get(mp_id)
        if not source or not ym:
            continue
        key = source + (ym,)
        if key in result and result[key] != mp_id:
            raise ValueError(f"같은 이용자/프로그램/선생님/월에 MEMBER_PROGRAM이 2개입니다: {key}")
        result[key] = mp_id
    return result


def nonempty_response(response):
    return bool((response.get("data") or {}).get("programs") or [])


def fetch_payment(vis_id, ym):
    path = checkpoint_path(vis_id, ym)
    cached = read_json(path)
    if cached is not None:
        return vis_id, ym, cached
    year, month = map(int, ym.split("-"))
    response = get_json(
        PAYMENT_URL.format(year=year, month=month),
        {"visId": vis_id, "_randid": int(time.time() * 1000) + random.randint(0, 999)},
    )
    if nonempty_response(response):
        write_json(path, response)
        return vis_id, ym, response
    return vis_id, ym, None


def payment_methods(detail):
    common = detail.get("rcvCommon") or {}
    voucher = detail.get("rcvVoucher") or {}
    methods = [
        ("CARD", amount(common.get("card")), ""),
        ("CASH", amount(common.get("cash")), ""),
        ("BANK_TRANSFER", amount(common.get("bankTransfer")), ""),
        ("VOUCHER", amount(voucher.get("voucher")), value(voucher.get("approveInfo"))),
        ("CARRYOVER", amount(detail.get("fromTransferedSum")), ""),
    ]
    known = sum(pay_amount for _, pay_amount, _ in methods)
    received = amount(detail.get("rcvSum")) + amount(detail.get("fromTransferedSum"))
    if received > known:
        methods.append(("OTHER", received - known, ""))
    return [(method, pay_amount, approval) for method, pay_amount, approval in methods if pay_amount]


def pick(source, *keys):
    for key in keys:
        if value(source.get(key)):
            return value(source.get(key))
    return ""


def carryover_rows(detail, payment_id, member_id, member_program_id, ym, create_dt, update_dt, start_no):
    rows = []
    transfers = detail.get("fromTransfered") or []
    if not isinstance(transfers, list):
        transfers = []

    # 원본 API에 개별 이월 정보가 있으면 그 값 그대로 사용한다.
    for transfer in transfers:
        used_amount = amount(pick(transfer, "use", "useAmt", "used", "usedAmount", "amount", "sum"))
        carryover_amount = amount(pick(transfer, "total", "totalAmount", "originAmount", "amount", "sum")) or used_amount
        remain_amount = amount(pick(transfer, "remain", "remainAmount", "balance"))
        from_ym = pick(transfer, "fromYearMonth", "fromYm", "yearMonth")
        if not from_ym:
            from_year, from_month = pick(transfer, "fromYearId", "yearId"), pick(transfer, "fromMonthId", "monthId")
            from_ym = f"{from_year}-{from_month.zfill(2)}" if from_year and from_month else previous_ym(ym)
        rows.append({
            "PAYMENT_CARRYOVER_ID": f"PAYMENT_CARRYOVER{start_no + len(rows) + 1:08d}",
            "COMPANY_ID": COMPANY_ID, "MEMBER_ID": member_id, "MEMBER_PROGRAM_ID": member_program_id,
            "PAYMENT_ID": payment_id, "FROM_YEAR_MONTH": from_ym, "TO_YEAR_MONTH": ym,
            "CARRYOVER_AMOUNT": str(carryover_amount), "USED_AMOUNT": str(used_amount), "REMAIN_AMOUNT": str(remain_amount),
            "STATUS_CD": "USED", "USED_DT": create_dt, "MEMO": value(detail.get("memo")),
            "USE_YN": "Y", "DELETE_YN": "N", "CREATE_DT": create_dt, "UPDATE_DT": update_dt,
        })

    # AS-IS가 합계만 주는 경우도 이월 사용 금액이 사라지지 않도록 전월 이월 1건으로 보존한다.
    if not rows and amount(detail.get("fromTransferedSum")):
        used_amount = amount(detail.get("fromTransferedSum"))
        rows.append({
            "PAYMENT_CARRYOVER_ID": f"PAYMENT_CARRYOVER{start_no + 1:08d}",
            "COMPANY_ID": COMPANY_ID, "MEMBER_ID": member_id, "MEMBER_PROGRAM_ID": member_program_id,
            "PAYMENT_ID": payment_id, "FROM_YEAR_MONTH": previous_ym(ym), "TO_YEAR_MONTH": ym,
            "CARRYOVER_AMOUNT": str(used_amount), "USED_AMOUNT": str(used_amount), "REMAIN_AMOUNT": "0",
            "STATUS_CD": "USED", "USED_DT": create_dt, "MEMO": value(detail.get("memo")),
            "USE_YN": "Y", "DELETE_YN": "N", "CREATE_DT": create_dt, "UPDATE_DT": update_dt,
        })
    return rows


def main():
    if not COOKIE.strip():
        raise ValueError("맨 위 COOKIE 변수에 최신 쿠키를 넣으세요.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "payment_export.log"
    log_path.write_text("", encoding="utf-8")

    def log(message):
        text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(text)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(text + "\n")

    global HEADERS
    tuid = next((part.split("=", 1)[1].strip() for part in COOKIE.split(";") if part.strip().startswith("tuid=")), "")
    HEADERS = {"Accept": "*/*", "Referer": BASE_URL + "/index.html", "X-Requested-With": "XMLHttpRequest", "Cookie": COOKIE, "tuid": tuid}
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    member_map = read_member_map()
    member_program_map = read_member_program_map()
    log(f"매핑 로드: 이용자 {len(member_map)}, 회원프로그램 월매핑 {len(member_program_map)}")

    empty_keys = set()
    if EMPTY_FILE.exists():
        empty_keys = {line.strip() for line in EMPTY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()}
    tasks = [(vis_id, f"{year:04d}-{month:02d}") for vis_id in member_map for year, month in month_range(START_YM, END_YM)]
    tasks = [(vis_id, ym) for vis_id, ym in tasks if f"{vis_id}|{ym}" not in empty_keys]
    log(f"수납 조회 대상 {len(tasks)}건 (빈 응답 재조회 제외 {len(empty_keys)}건)")

    raw_asis, new_empty = {}, set()
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(fetch_payment, vis_id, ym) for vis_id, ym in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            vis_id, ym, response = future.result()
            if response is None:
                new_empty.add(f"{vis_id}|{ym}")
            else:
                raw_asis[f"{vis_id}_{ym}"] = response
            if index % 50 == 0 or index == len(futures):
                log(f"수납 조회 {index}/{len(futures)} (동시작업 {WORKERS})")
    if new_empty:
        EMPTY_FILE.write_text("\n".join(sorted(empty_keys | new_empty)) + "\n", encoding="utf-8")

    master_rows, detail_rows, carryover_rows_all, map_rows, unmatched = [], [], [], [], []
    payment_no, detail_no, carryover_no = PAYMENT_ID_LAST_NO, PAYMENT_DETAIL_ID_LAST_NO, PAYMENT_CARRYOVER_ID_LAST_NO
    for response in raw_asis.values():
        for program in (response.get("data") or {}).get("programs") or []:
            vis_id = value((program.get("vis") or {}).get("visId"))
            pgm_id = value((program.get("pgm") or {}).get("pgmId"))
            emp_id = value((program.get("emp") or {}).get("empId"))
            ym = f"{value(program.get('yearId'))}-{value(program.get('monthId')).zfill(2)}"
            member_id = member_map.get(vis_id, "")
            member_program_id = member_program_map.get((vis_id, pgm_id, emp_id, ym), "")
            if not member_id:
                unmatched.append([vis_id, pgm_id, emp_id, ym, "MEMBER_ID", "이용자 매핑 없음"])
            if not member_program_id:
                unmatched.append([vis_id, pgm_id, emp_id, ym, "MEMBER_PROGRAM_ID", "회원프로그램 월매핑 없음"])

            for source in ((program.get("payment") or {}).get("details") or []):
                payment_no += 1
                payment_id = f"PAYMENT{payment_no:08d}"
                payment_dt = payment_datetime(source.get("dtime")) or migration_dt
                update_dt = date_time(source.get("lastModDtime")) or payment_dt
                received = amount(source.get("rcvSum")) + amount(source.get("fromTransferedSum"))
                refund = amount(source.get("refund"))
                paid_amount = max(received - refund, 0)
                total_amount = amount(source.get("total"))
                carryover_use = amount(source.get("fromTransferedSum"))
                carryover_create = amount(source.get("transferTo"))
                master_rows.append({
                    "PAYMENT_ID": payment_id, "COMPANY_ID": COMPANY_ID, "MEMBER_ID": member_id,
                    "PAYMENT_TARGET_TYPE_CD": "MEMBER_PROGRAM", "PAYMENT_TARGET_ID": member_program_id,
                    "MEMBER_PROGRAM_ID": member_program_id, "PAYMENT_TYPE_CD": value(source.get("typeCd")),
                    "PAYMENT_STATUS_CD": value(source.get("statusCd")), "TOTAL_AMOUNT": str(total_amount),
                    "PAID_AMOUNT": str(paid_amount), "REMAIN_AMOUNT": str(max(total_amount - paid_amount, 0)),
                    "CARRYOVER_USE_AMOUNT": str(carryover_use), "CARRYOVER_CREATE_AMOUNT": str(carryover_create),
                    "PAYMENT_DT": payment_dt, "MEMO": value(source.get("memo")), "USE_YN": "Y", "DELETE_YN": "N",
                    "CREATE_DT": payment_dt, "UPDATE_DT": update_dt, "REF_PAYMENT_ID": "",
                    # 수납 조회/회원프로그램 서비스 대상 월 (YYYY-MM)
                    "TARGET_YEAR_MONTH": ym,
                })
                map_rows.append({
                    "CAREPLE_PM_ID": value(source.get("pmId")), "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id,
                    "CAREPLE_EMP_ID": emp_id, "SERVICE_YM": ym, "PAYMENT_ID": payment_id,
                    "MEMBER_ID": member_id, "MEMBER_PROGRAM_ID": member_program_id,
                })
                for method, pay_amount, approval in payment_methods(source):
                    detail_no += 1
                    detail_rows.append({
                        "PAYMENT_DETAIL_ID": f"PAYMENT_DETAIL{detail_no:08d}", "PAYMENT_ID": payment_id,
                        "PAYMENT_METHOD_CD": method, "PAY_AMOUNT": str(pay_amount), "APPROVAL_NO": approval,
                        "MEMO": value(source.get("memo")), "CREATE_DT": payment_dt, "UPDATE_DT": update_dt,
                        "USE_YN": "Y", "DELETE_YN": "N",
                    })
                rows = carryover_rows(source, payment_id, member_id, member_program_id, ym, payment_dt, update_dt, carryover_no)
                carryover_rows_all.extend(rows)
                carryover_no += len(rows)

    tobe_json = {"payment_master": master_rows, "payment_detail": detail_rows, "payment_carryover": carryover_rows_all, "unmatched": [dict(zip(UNMATCHED_HEADERS, row)) for row in unmatched]}
    write_csv(OUTPUT_DIR / "payment_master_db.csv", PAYMENT_MASTER_HEADERS, master_rows)
    write_csv(OUTPUT_DIR / "payment_detail_db.csv", PAYMENT_DETAIL_HEADERS, detail_rows)
    write_csv(OUTPUT_DIR / "payment_carryover_db.csv", PAYMENT_CARRYOVER_HEADERS, carryover_rows_all)
    write_csv(OUTPUT_DIR / "payment_id_map.csv", PAYMENT_MAP_HEADERS, map_rows)
    write_csv(OUTPUT_DIR / "payment_unmatched_map.csv", UNMATCHED_HEADERS, tobe_json["unmatched"])
    write_json(OUTPUT_DIR / "payment_asis_raw.json", raw_asis)
    write_json(OUTPUT_DIR / "payment_tobe_all.json", tobe_json)
    summary = {"nonempty_response_count": len(raw_asis), "payment_master_count": len(master_rows), "payment_detail_count": len(detail_rows), "payment_carryover_count": len(carryover_rows_all), "unmatched_count": len(unmatched)}
    write_json(OUTPUT_DIR / "payment_export_summary.json", summary)
    log("이관 완료: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
