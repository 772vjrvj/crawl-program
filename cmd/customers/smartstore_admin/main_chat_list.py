# -*- coding: utf-8 -*-
import csv
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests
from openpyxl import Workbook

COOKIE = ""  # 여기에 직접 넣으세요
PARTNER_ID = "w4zlu6"

START_DATE = "20260314"
END_DATE = "20260301"
MAX_WORKERS = 6

OUT_CSV = "smartstore_chat_list.csv"
OUT_XLSX = "smartstore_chat_list.xlsx"

URL = f"https://talk.sell.smartstore.naver.com/chatapi/ct/partner/{PARTNER_ID}/list"


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "accept": "application/json, text/plain, */*",
        "origin": "https://talk.sell.smartstore.naver.com",
        "referer": "https://talk.sell.smartstore.naver.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-orig-referer": f"https://talk.sell.smartstore.naver.com/chat/ct/{PARTNER_ID}?device=pc",
        "x-requested-with": "XMLHttpRequest",
        "cookie": COOKIE,
    })
    return session


def format_date(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def iter_dates_desc(start_ymd: str, end_ymd: str):
    current = datetime.strptime(start_ymd, "%Y%m%d")
    end = datetime.strptime(end_ymd, "%Y%m%d")

    while current >= end:
        yield current.strftime("%Y%m%d")
        current -= timedelta(days=1)


def request_page(session: requests.Session, from_date: str, min_no: str | None = None) -> dict:
    data = {
        "fromDate": (None, from_date),
        "order": (None, "lstDesc"),
        "filter": (None, "all"),
    }
    if min_no:
        data["min"] = (None, min_no)

    res = session.post(URL, files=data, timeout=(10, 30))
    res.raise_for_status()
    return res.json()


def crawl_chat_list_by_date(from_date: str) -> list[dict]:
    session = create_session()
    rows = []
    min_no = None
    page = 0

    time.sleep(random.uniform(0.2, 0.8))

    while True:
        page += 1
        data = request_page(session, from_date, min_no)
        ret = data.get("htReturnValue", {})
        chat_list = ret.get("chatList", [])

        if not chat_list:
            break

        for item in chat_list:
            row = {
                "req_from_date": from_date,
                "no": str(item.get("no", "")).strip(),
                "name": item.get("name", ""),
                "chatUrl": item.get("chatUrl", ""),
                "text": item.get("text", ""),
                "date": item.get("date", ""),
                "date_text": format_date(item.get("date", 0)),
                "chatId": item.get("chatId", ""),
            }
            rows.append(row)

            print(
                f"[{from_date}][page:{page}] "
                f"{row['name']} / {row['date_text']} / {row['text']}"
            )

        if not ret.get("hasNextPage"):
            break

        min_no = str(chat_list[-1].get("no", "")).strip()
        if not min_no:
            break

        time.sleep(random.uniform(0.7, 1.4))

    print(f"===== 날짜 완료: {from_date} / 수집 {len(rows)}건 =====")
    return rows


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    result = []

    rows.sort(key=lambda x: (str(x.get("date", "")), str(x.get("no", ""))), reverse=True)

    for row in rows:
        no = row.get("no", "")
        if not no or no in seen:
            continue
        seen.add(no)
        result.append(row)

    return result


def crawl_chat_list() -> list[dict]:
    all_rows = []
    dates = list(iter_dates_desc(START_DATE, END_DATE))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(crawl_chat_list_by_date, from_date): from_date
            for from_date in dates
        }

        for future in as_completed(future_map):
            from_date = future_map[future]
            try:
                rows = future.result()
                all_rows.extend(rows)
                print(f"[완료] {from_date} / {len(rows)}건")
            except Exception as e:
                print(f"[에러] {from_date} / {e}")

    return dedupe_rows(all_rows)


def save_csv(rows: list[dict]) -> None:
    fields = ["req_from_date", "no", "name", "chatUrl", "text", "date", "date_text", "chatId"]

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_excel(rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "chat_list"

    fields = ["req_from_date", "no", "name", "chatUrl", "text", "date", "date_text", "chatId"]
    ws.append(fields)

    for row in rows:
        ws.append([row[field] for field in fields])

    wb.save(OUT_XLSX)


if __name__ == "__main__":
    rows = crawl_chat_list()
    save_csv(rows)
    save_excel(rows)
    print(f"저장 완료: {len(rows)}건 / {OUT_CSV}, {OUT_XLSX}")