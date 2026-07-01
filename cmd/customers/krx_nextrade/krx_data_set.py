# krx_data_set.py
import csv
import os
import time
from datetime import datetime, timedelta

import requests

# 로그인 후 쿠키만 바꿔서 데이터 업데이트 하면됨


# ==============================
# 설정
# ==============================
YEAR = 2026

START_DATE = f"{YEAR}0306"
END_DATE = f"{YEAR}0306"
OUTPUT_FILE = f"krx_{YEAR}.csv"

SLEEP_SEC = 0.1          # 요청 간 대기
SAVE_INTERVAL = 100      # 100일마다 중간 저장


# ==============================
# 공통
# ==============================
def date_range(start_yyyymmdd, end_yyyymmdd):
    start_date = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end_date = datetime.strptime(end_yyyymmdd, "%Y%m%d")

    current = start_date
    while current <= end_date:
        yield current.strftime("%Y%m%d")
        current += timedelta(days=1)


def normalize_value(value):
    if isinstance(value, str):
        return value.strip()
    return value


def fetch_day(session, trd_dd):
    url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
        "locale": "ko_KR",
        "mktId": "ALL",
        "trdDd": trd_dd,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "cookie": "__smVisitorID=sI3CKS9DmaP; lang=ko_KR; JSESSIONID=Cq8ZtMuSWfI7a7kmlwPsYbneWVl6eoLiTOMRgDHsN1ln5GFYt8cMs3WUQeRLBOzA.bWRjX2RvbWFpbi9tZGNvd2FwMi1tZGNhcHAxMQ==; npPfsHost=127.0.0.1; npPfsPort=14440; mdc.client_session=true",
        "origin": "https://data.krx.co.kr",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest"
    }

    response = session.post(url, data=payload, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    rows = data.get("OutBlock_1", [])

    result = []
    for row in rows:
        item = {}
        for k, v in row.items():
            item[k] = normalize_value(v)

        item["trdDd"] = trd_dd
        result.append(item)

    return result


def append_csv(rows, filename, fieldnames):
    if not rows:
        return

    file_exists = os.path.exists(filename)
    write_header = (not file_exists) or os.path.getsize(filename) == 0

    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")

        if write_header:
            writer.writeheader()

        writer.writerows(rows)


def main():
    session = requests.Session()

    all_buffer = []
    fieldnames = None

    total_days = 0
    total_rows = 0
    success_days = 0
    fail_days = 0

    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print("기존 파일 삭제:", OUTPUT_FILE)

    for trd_dd in date_range(START_DATE, END_DATE):
        total_days += 1
        print(f"[{total_days}] 요청: {trd_dd}")

        try:
            rows = fetch_day(session, trd_dd)
            print(f"    수신: {len(rows)}건")

            if rows:
                if fieldnames is None:
                    fieldnames = list(rows[0].keys())

                all_buffer.extend(rows)
                total_rows += len(rows)

            success_days += 1

        except Exception as e:
            fail_days += 1
            print(f"    실패: {trd_dd} / {e}")

        if total_days % SAVE_INTERVAL == 0 and all_buffer:
            append_csv(all_buffer, OUTPUT_FILE, fieldnames)
            print(f"    중간 저장 완료: {len(all_buffer)}건 -> {OUTPUT_FILE}")
            all_buffer = []

        time.sleep(SLEEP_SEC)

    if all_buffer and fieldnames:
        append_csv(all_buffer, OUTPUT_FILE, fieldnames)
        print(f"최종 저장 완료: {len(all_buffer)}건 -> {OUTPUT_FILE}")

    print("\n=== 완료 ===")
    print("전체 요청 일수:", total_days)
    print("성공 일수:", success_days)
    print("실패 일수:", fail_days)
    print("총 저장 건수:", total_rows)
    print("출력 파일:", OUTPUT_FILE)


if __name__ == "__main__":
    main()