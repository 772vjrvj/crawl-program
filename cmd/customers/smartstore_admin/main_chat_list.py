# -*- coding: utf-8 -*-
import csv
import time
from datetime import datetime

import requests
from openpyxl import Workbook

COOKIE = '''NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; NACT=1; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; ttdevice=pc; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5kaFBCd9UEqqGTilAXfxVzMV8xBsCW5L28ALksD7+L/wI="; NID_SES=AAAB5k9ycwcWKpwgjNDg4ltfbGfx26HPMe07ClZkTiBuRvfwMPWIEonQMdVFjjRXz0Jz/vmsu4pKWi1QDiahQf2oGH66jiWAG7g0OTKCa4tc6nMdoDBYwEqzn45F7/WonrAImY+j9L8IBsCo0xr/aXLqaKh2wB6NIKhjpYDZ2dFrZR9Waicq1TA1ncX/69LA4Fgcxjc1ybljMKMPiVpnd0BLGwLTvWUd6ipvcmMk6o/Bja5StOYriaGP59kp8xehhLyjdvYedAIfauVUVCpi0D+rm1hJ7Hqmw9dHUQZhx+u5IBc0Rmw6UHafE4ZuM90wPAYxgthnSbc0yqVXv33oynXpO2ZK4WfPm56cGPNyV5mlJIpqMCJ1ZiCeGiWnBj4PtqN5zLPPz3gvzmFBQRoJu/KMylDgmsBu78Fk6/LPqssOkDQYAsDXCPk5DVyJ0i7me3Og3sfXELM/S7kCDgbDgW0Qb74faiOUUITyCjTfh6G8XeX86bkCd4dYUsxCjpM+nwYb7Gaf0VA3ODaqYxF/oRK/nLRXOyFSYxjAyVGP77qpX1rXyHcl7rjkYWfRLM2Ow36epy2EwjTCbhuHM88g8RSqJ+a98UWNIu716RyzvNskd6wP9MCNlbLfBbpBK72R6D+dsdtYnhOEc4apNvfSyAO/gpU=; SRT30=1773416725; SRT5=1773416725; BUC=2yR1gHVaaI15EQSxAaaMmfZhLavAKqXn9wHRCBOtmys='''
PARTNER_ID = "w4zlu6"
FROM_DATE = "20260306"

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


def format_date(ms: str) -> str:
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def request_page(min_no: str | None = None) -> dict:
    data = {
        "fromDate": (None, FROM_DATE),
        "order": (None, "lstDesc"),
        "filter": (None, "all"),
    }
    if min_no:
        data["min"] = (None, min_no)

    res = session.post(URL, files=data, timeout=(10, 30))
    res.raise_for_status()
    return res.json()


def crawl_chat_list() -> list[dict]:
    rows = []
    min_no = None
    count = 0

    while True:
        ret = request_page(min_no)["htReturnValue"]
        chat_list = ret["chatList"]

        if not chat_list:
            break

        for item in chat_list:
            row = {
                "no": item["no"],
                "name": item["name"],
                "imageUrl": item["imageUrl"],
                "chatUrl": item["chatUrl"],
                "text": item["text"],
                "date": item["date"],
                "date_text": format_date(item["date"]),
                "chatId": item["chatId"],
            }
            rows.append(row)

            count += 1
            print(f"[{count}] {row['name']} / {row['date_text']} / {row['text']}")

        if not ret["hasNextPage"]:
            break

        min_no = chat_list[-1]["no"]
        time.sleep(1)

    return rows


def save_csv(rows: list[dict]) -> None:
    fields = ["no", "name", "imageUrl", "chatUrl", "text", "date", "date_text", "chatId"]

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_excel(rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "chat_list"

    fields = ["no", "name", "imageUrl", "chatUrl", "text", "date", "date_text", "chatId"]
    ws.append(fields)

    for row in rows:
        ws.append([row[field] for field in fields])

    wb.save(OUT_XLSX)


if __name__ == "__main__":
    rows = crawl_chat_list()
    save_csv(rows)
    save_excel(rows)
    print(f"저장 완료: {len(rows)}건 / {OUT_CSV}, {OUT_XLSX}")