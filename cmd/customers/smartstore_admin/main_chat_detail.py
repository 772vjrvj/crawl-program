# -*- coding: utf-8 -*-
import csv
import time
from datetime import datetime

import requests
from openpyxl import Workbook

COOKIE = '''NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; NACT=1; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; ttdevice=pc; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5kaFBCd9UEqqGTilAXfxVzMV8xBsCW5L28ALksD7+L/wI="; NID_SES=AAAB5k9ycwcWKpwgjNDg4ltfbGfx26HPMe07ClZkTiBuRvfwMPWIEonQMdVFjjRXz0Jz/vmsu4pKWi1QDiahQf2oGH66jiWAG7g0OTKCa4tc6nMdoDBYwEqzn45F7/WonrAImY+j9L8IBsCo0xr/aXLqaKh2wB6NIKhjpYDZ2dFrZR9Waicq1TA1ncX/69LA4Fgcxjc1ybljMKMPiVpnd0BLGwLTvWUd6ipvcmMk6o/Bja5StOYriaGP59kp8xehhLyjdvYedAIfauVUVCpi0D+rm1hJ7Hqmw9dHUQZhx+u5IBc0Rmw6UHafE4ZuM90wPAYxgthnSbc0yqVXv33oynXpO2ZK4WfPm56cGPNyV5mlJIpqMCJ1ZiCeGiWnBj4PtqN5zLPPz3gvzmFBQRoJu/KMylDgmsBu78Fk6/LPqssOkDQYAsDXCPk5DVyJ0i7me3Og3sfXELM/S7kCDgbDgW0Qb74faiOUUITyCjTfh6G8XeX86bkCd4dYUsxCjpM+nwYb7Gaf0VA3ODaqYxF/oRK/nLRXOyFSYxjAyVGP77qpX1rXyHcl7rjkYWfRLM2Ow36epy2EwjTCbhuHM88g8RSqJ+a98UWNIu716RyzvNskd6wP9MCNlbLfBbpBK72R6D+dsdtYnhOEc4apNvfSyAO/gpU=; SRT30=1773416725; SRT5=1773416725; BUC=2yR1gHVaaI15EQSxAaaMmfZhLavAKqXn9wHRCBOtmys='''
PARTNER_ID = "w4zlu6"

INPUT_CSV = "smartstore_chat_list.csv"
OUTPUT_CSV = "smartstore_chat_messages.csv"
OUTPUT_XLSX = "smartstore_chat_messages.xlsx"

BASE_URL = "https://talk.sell.smartstore.naver.com"
READ_API_URL = BASE_URL + f"/chatapi/ct/partner/{PARTNER_ID}/chat/{{chat_url}}/read"

session = requests.Session()
session.headers.update({
    "accept": "application/json, text/plain, */*",
    "origin": "https://talk.sell.smartstore.naver.com",
    "referer": "https://talk.sell.smartstore.naver.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "cookie": COOKIE,
})


def format_date(ms: str | int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def read_chat_list() -> list[dict]:
    with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def request_chat_read(chat_url: str, min_id: str = "", max_id: str = "") -> list[dict]:
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


def crawl_all_messages(chat_url: str) -> list[dict]:
    msg_map = {}

    first_list = request_chat_read(chat_url)
    if not first_list:
        return []

    for msg in first_list:
        msg_map[msg["id"]] = msg

    ids = sorted(int(msg["id"]) for msg in first_list)
    first_id = str(ids[0])
    last_id = str(ids[-1])
    print(f"  첫 페이지: {len(first_list)}건 / id {first_id} ~ {last_id}")

    while int(first_id) > 1:
        time.sleep(0.5)
        old_list = request_chat_read(chat_url, min_id=first_id)

        if not old_list:
            print(f"  이전 페이지 없음 / 현재 시작 id={first_id}")
            break

        for msg in old_list:
            msg_map[msg["id"]] = msg

        ids = sorted(int(msg["id"]) for msg in old_list)
        old_min_id = str(ids[0])
        old_max_id = str(ids[-1])

        print(f"  이전 페이지: {len(old_list)}건 / id {old_min_id} ~ {old_max_id}")

        if old_min_id == first_id:
            break

        first_id = old_min_id

    messages = list(msg_map.values())
    messages.sort(key=lambda x: int(x["id"]))
    return messages


def get_text(msg: dict) -> str:
    return msg.get("textContent", {}).get("text", "").replace("\r\n", "\n").strip()


def build_message_rows(parent: dict, messages: list[dict]) -> list[dict]:
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
            "no": parent["no"],
            "name": parent["name"],
            "chatUrl": parent["chatUrl"],
            "chatId": parent["chatId"],
            "parent_text": parent["text"],
            "parent_date": parent["date"],
            "parent_date_text": parent["date_text"],
        }
        rows.append(row)
        print(f"    메시지 저장: id={row['id']} / {row['sender']} / {row['text'][:30]}")

    return rows


def save_csv(rows: list[dict]) -> None:
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


def save_excel(rows: list[dict]) -> None:
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
        ws.append([row[field] for field in fields])

    wb.save(OUTPUT_XLSX)


def main() -> None:
    parents = read_chat_list()
    all_rows = []

    for i, parent in enumerate(parents, 1):
        print(f"[{i}/{len(parents)}] {parent['name']} / {parent['chatUrl']} 시작")

        messages = crawl_all_messages(parent["chatUrl"])
        print(f"  전체 메시지 수: {len(messages)}")

        rows = build_message_rows(parent, messages)
        print(f"  저장 대상 메시지 수: {len(rows)}")

        all_rows.extend(rows)
        time.sleep(0.7)

    save_csv(all_rows)
    save_excel(all_rows)
    print(f"완료: {OUTPUT_CSV}, {OUTPUT_XLSX} / 총 {len(all_rows)}건")


if __name__ == "__main__":
    main()