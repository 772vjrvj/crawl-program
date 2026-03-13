# -*- coding: utf-8 -*-
import csv
import time
from datetime import datetime, timedelta

import requests
from openpyxl import Workbook

COOKIE = '''NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; ttdevice=pc; NACT=1; SRT30=1773426682; SRT5=1773427872; NID_SES=AAAB4/LCTrnnrSTH6E6acME2gn5LvKALTujnlB1seblR2XbKY/stX1G1QYLP2HUQoHZqUo3PjiGjdQPxd+oYL4Pgg3pm/+EtA7Qh3nuQG7NvZMcKAvsViYAceiwlfGHik+UjJypFPW9tqq7jhEhwvA0iUkmm75tBDgUrRGm9P7cdcFDGdL6cK9PJpcukk5MlGYaf9KUl+3JOcVq+kXHr+l1xlaX7lYxYwG3Qx6xDSNGoFl442AhgvitzLhV+2qVoQq7lwNCIC7yPFBczD3b3lTqVatHnlVVtXhSuAqyF6XbDb0wYiHFMh4azO3fgIxa2JZzs4PCD0L3RppE1A34tah9KP6GeL7BacqmJnXxYwLgHvVpoOxDrANLlgU5HdR3npz0QZeq4XcFLtM8b5TcF2nAsNWBfeTrK/wy4MrmRNOYEVcfB8XAvjJ00e6KjN6a1jmhGtwPyAZm9EfrtsSl5jl5QGxAPEoUmL5Be+32D3/BWnFJV9oF8bi8HjaSNcw5MtL7KFa5/KOcvGrYKmyYVlizFdYytQic2A1zJlGcv74isIwMsxxM0H5DlkdGI6NdGs+vHGzJ7zirq3MXFub4gu5P7Qgqfsd+YEgv8ykyLJV1NTBvciaMoq1B8NNg6qgDOlI3mrRaFj5vJr2CGaTpDHzNWXE0=; BUC=amYB1AV61_gYNYXBnjXBh2huVXOZ2m-ZOwE0EvqAg00=; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5kgojQG7q5DBI4+irNEsWDGhmyp1N2DuX9CCrCLPoDE3c="'''  # <- 여기에 직접 넣으세요
PARTNER_ID = "w4zlu6"

START_DATE = "20260314"
END_DATE = "20260301"

OUT_CSV = "smartstore_chat_list.csv"
OUT_XLSX = "smartstore_chat_list.xlsx"

URL = f"https://talk.sell.smartstore.naver.com/chatapi/ct/partner/{PARTNER_ID}/list"

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


def format_date(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def iter_dates_desc(start_ymd: str, end_ymd: str):
    current = datetime.strptime(start_ymd, "%Y%m%d")
    end = datetime.strptime(end_ymd, "%Y%m%d")

    while current >= end:
        yield current.strftime("%Y%m%d")
        current -= timedelta(days=1)


def request_page(from_date: str, min_no: str | None = None) -> dict:
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


def crawl_chat_list_by_date(from_date: str, seen_no: set[str]) -> list[dict]:
    rows = []
    min_no = None
    page = 0

    while True:
        page += 1
        data = request_page(from_date, min_no)
        ret = data.get("htReturnValue", {})
        chat_list = ret.get("chatList", [])

        if not chat_list:
            break

        for item in chat_list:
            no = str(item.get("no", "")).strip()
            if not no or no in seen_no:
                continue

            seen_no.add(no)

            row = {
                "req_from_date": from_date,
                "no": no,
                "name": item.get("name", ""),
                "chatUrl": item.get("chatUrl", ""),
                "text": item.get("text", ""),
                "date": item.get("date", ""),
                "date_text": format_date(item.get("date", 0)),
                "chatId": item.get("chatId", ""),
            }
            rows.append(row)

            print(
                f"[{from_date}][{len(seen_no)}] "
                f"{row['name']} / {row['date_text']} / {row['text']}"
            )

        if not ret.get("hasNextPage"):
            break

        min_no = str(chat_list[-1].get("no", "")).strip()
        if not min_no:
            break

        time.sleep(1)

    return rows


def crawl_chat_list() -> list[dict]:
    all_rows = []
    seen_no = set()

    for from_date in iter_dates_desc(START_DATE, END_DATE):
        print(f"\n===== 수집 시작: {from_date} =====")
        rows = crawl_chat_list_by_date(from_date, seen_no)
        all_rows.extend(rows)
        print(f"===== 수집 완료: {from_date} / 신규 {len(rows)}건 =====\n")
        time.sleep(1)

    return all_rows


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