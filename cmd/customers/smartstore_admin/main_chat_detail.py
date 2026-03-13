# -*- coding: utf-8 -*-
import csv
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from openpyxl import Workbook

COOKIE = '''NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; ttdevice=pc; NACT=1; NID_SES=AAAB4/LCTrnnrSTH6E6acME2gn5LvKALTujnlB1seblR2XbKY/stX1G1QYLP2HUQoHZqUo3PjiGjdQPxd+oYL4Pgg3pm/+EtA7Qh3nuQG7NvZMcKAvsViYAceiwlfGHik+UjJypFPW9tqq7jhEhwvA0iUkmm75tBDgUrRGm9P7cdcFDGdL6cK9PJpcukk5MlGYaf9KUl+3JOcVq+kXHr+l1xlaX7lYxYwG3Qx6xDSNGoFl442AhgvitzLhV+2qVoQq7lwNCIC7yPFBczD3b3lTqVatHnlVVtXhSuAqyF6XbDb0wYiHFMh4azO3fgIxa2JZzs4PCD0L3RppE1A34tah9KP6GeL7BacqmJnXxYwLgHvVpoOxDrANLlgU5HdR3npz0QZeq4XcFLtM8b5TcF2nAsNWBfeTrK/wy4MrmRNOYEVcfB8XAvjJ00e6KjN6a1jmhGtwPyAZm9EfrtsSl5jl5QGxAPEoUmL5Be+32D3/BWnFJV9oF8bi8HjaSNcw5MtL7KFa5/KOcvGrYKmyYVlizFdYytQic2A1zJlGcv74isIwMsxxM0H5DlkdGI6NdGs+vHGzJ7zirq3MXFub4gu5P7Qgqfsd+YEgv8ykyLJV1NTBvciaMoq1B8NNg6qgDOlI3mrRaFj5vJr2CGaTpDHzNWXE0=; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5k2cA+28rrLhl28X9McFIL0rRG3oj3ROhCS4Sgm1A4dug="; BUC=20DoHiOywDSoK47KudPdfkqjPsotJ0n42kxGDumNeuM='''
PARTNER_ID = "w4zlu6"

INPUT_CSV = "smartstore_chat_list.csv"
OUTPUT_CSV = "smartstore_chat_messages.csv"
OUTPUT_XLSX = "smartstore_chat_messages.xlsx"

MAX_WORKERS = 6

BASE_URL = "https://talk.sell.smartstore.naver.com"
READ_API_URL = BASE_URL + f"/chatapi/ct/partner/{PARTNER_ID}/chat/{{chat_url}}/read"


def create_session():
    session = requests.Session()
    session.headers.update({
        "accept": "application/json, text/plain, */*",
        "origin": "https://talk.sell.smartstore.naver.com",
        "referer": "https://talk.sell.smartstore.naver.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": COOKIE,
    })
    return session


def format_date(ms):
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def read_chat_list():
    with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def request_chat_read(session, chat_url, min_id="", max_id=""):
    url = READ_API_URL.format(chat_url=chat_url)
    payload = {"updateRead": "true"}

    if min_id:
        payload["min"] = min_id
    if max_id:
        payload["max"] = max_id

    res = session.post(
        url,
        files={k: (None, str(v)) for k, v in payload.items()},
        timeout=(10, 30),
        headers={
            "x-orig-referer": f"https://talk.sell.smartstore.naver.com/ct/partner/{PARTNER_ID}/chat/{chat_url}/read"
        },
    )
    res.raise_for_status()
    return res.json()["htReturnValue"]["messageList"]


def crawl_all_messages(session, chat_url):
    msg_map = {}

    time.sleep(random.uniform(0.2, 0.8))

    first_list = request_chat_read(session, chat_url)
    if not first_list:
        return []

    for msg in first_list:
        msg_map[str(msg["id"])] = msg

    ids = sorted(int(msg["id"]) for msg in first_list)
    first_id = str(ids[0])
    last_id = str(ids[-1])
    print(f"  첫 페이지: {len(first_list)}건 / id {first_id} ~ {last_id}")

    while True:
        old_list = request_chat_read(session, chat_url, min_id=first_id)

        if not old_list:
            print(f"  이전 페이지 없음 / 현재 시작 id={first_id}")
            break

        for msg in old_list:
            msg_map[str(msg["id"])] = msg

        ids = sorted(int(msg["id"]) for msg in old_list)
        old_min_id = str(ids[0])
        old_max_id = str(ids[-1])

        print(f"  이전 페이지: {len(old_list)}건 / id {old_min_id} ~ {old_max_id}")

        if old_min_id == first_id:
            break

        first_id = old_min_id
        time.sleep(random.uniform(0.5, 1.1))

    messages = list(msg_map.values())
    messages.sort(key=lambda x: int(x["id"]))
    return messages


def get_text(msg):
    return msg.get("textContent", {}).get("text", "").replace("\r\n", "\n").strip()


def build_message_rows(parent, messages):
    rows = []

    for msg in messages:
        text = get_text(msg)
        if not text:
            continue

        row = {
            "id": msg.get("id", ""),
            "sender": msg.get("sender", ""),
            "type": "대답" if msg.get("sender") == "partner" else "질문",
            "text": text,
            "date": msg.get("date", ""),
            "date_text": format_date(msg.get("date", "")),
            "no": parent.get("no", ""),
            "name": parent.get("name", ""),
            "chatUrl": parent.get("chatUrl", ""),
            "chatId": parent.get("chatId", ""),
            "parent_text": parent.get("text", ""),
            "parent_date": parent.get("date", ""),
            "parent_date_text": parent.get("date_text", ""),
        }
        rows.append(row)

    return rows


def crawl_one_parent(idx, total, parent):
    session = create_session()
    chat_url = parent["chatUrl"]

    print(f"[{idx}/{total}] {parent['name']} / {chat_url} 시작")

    messages = crawl_all_messages(session, chat_url)
    print(f"[{idx}/{total}] {parent['name']} / 전체 메시지 수: {len(messages)}")

    rows = build_message_rows(parent, messages)
    print(f"[{idx}/{total}] {parent['name']} / 저장 대상 메시지 수: {len(rows)}")

    return rows


def dedupe_rows(rows):
    seen = set()
    result = []

    for row in sorted(rows, key=lambda x: (str(x.get("chatUrl", "")), int(x.get("id", 0)))):
        key = (row.get("chatUrl", ""), row.get("id", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)

    return result


def save_csv(rows):
    fields = [
        "id",
        "sender",
        "type",
        "text",
        "date",
        "date_text",
        "no",
        "name",
        "chatUrl",
        "chatId",
        "parent_text",
        "parent_date",
        "parent_date_text",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_excel(rows):
    fields = [
        "id",
        "sender",
        "type",
        "text",
        "date",
        "date_text",
        "no",
        "name",
        "chatUrl",
        "chatId",
        "parent_text",
        "parent_date",
        "parent_date_text",
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "chat_messages"
    ws.append(fields)

    for row in rows:
        ws.append([row.get(field, "") for field in fields])

    wb.save(OUTPUT_XLSX)


def main():
    parents = read_chat_list()
    all_rows = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(crawl_one_parent, i, len(parents), parent)
            for i, parent in enumerate(parents, 1)
        ]

        for future in as_completed(futures):
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                print(f"[에러] {e}")

    all_rows = dedupe_rows(all_rows)

    save_csv(all_rows)
    save_excel(all_rows)
    print(f"완료: {OUTPUT_CSV}, {OUTPUT_XLSX} / 총 {len(all_rows)}건")


if __name__ == "__main__":
    main()