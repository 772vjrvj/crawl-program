import json
import html
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import requests


URL = "https://comm-api.game.naver.com/nng_main/v1/community/lounge/ZZZ/feed"
DETAIL_URL_FORMAT = "https://game.naver.com/lounge/ZZZ/board/detail/{feed_id}"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "deviceid": "c0aa9cfd-253c-4a37-988e-67721c3b06c0",
    "front-client-platform-type": "PC",
    "front-client-product-type": "web",
    "if-modified-since": "Mon, 26 Jul 1997 05:00:00 GMT",
    "origin": "https://game.naver.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://game.naver.com/lounge/ZZZ/board/4?page=1&order=new",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "cookie": "NAC=sTKYB8Q0oCuv; NNB=EZJOVEYWNS7GS; ASID=dc5ec4bf0000019d0fd8bc0d0000001b; _fbp=fb.1.1774087357518.703983604281386815; _ga=GA1.1.971879580.1774198458; _ga_E6ST2DMJ6E=GS2.1.s1774201536$o2$g0$t1774201536$j60$l0$h0; _ga_SPWZFHV5W9=GS2.1.s1774689327$o2$g0$t1774689329$j58$l0$h0; nstore_session=A0g9EWbemr5sVnsMXSeu+kKc; nstore_pagesession=jO6fsdqW7WJR7ssd4BN-162223; cto_bundle=iW-snl9sMTBEM05POXRxWkxoWHU0VUhBdHIyemNnJTJGUjJ1QUduYlFFZWxORHpUJTJCaW1pOEdFdXZLWk8xNTBodXhLQk5HQSUyQll2SiUyQmR1OHU1SkhwTXFiJTJGenkzU2d6aVE4TWFpTWFYNWNKUzhTUSUyQkZQaTFibWVMSE1GMDFRaHJHUWwlMkJXNllH; ba.uuid=c0aa9cfd-253c-4a37-988e-67721c3b06c0; loungesRecentlyVisited=ZZZ; recentKeyword=%5B%5D; recentKeywordInLounge=%5B%5D; NACT=1; SRT30=1775903193; SRT5=1775903193; BUC=22pQ7JYDg45Vx7yOaYmMyV28jsQ7cs-MTSI_15EulBM=; nid_inf=1268989421; NID_AUT=kbxlX5ShAt4SPViQJClfX+dSL/HB0fzvWsxBq3ARja2PikByHtLlP5eI5Fh/LGzq; lastSeenQuestPopupTime=1775903213685; NID_SES=AAABqebaKLFLDGd2f2v9I++bpKAdHYX/msxk6aBiL5V7uyUK1TTjWcuvaVEH870/+2eaQb21q0clUrszusJCl+sXKAXuJ1oQbtgZk6zMvAcUK3N2s6dcORNOhZJCXHp00KdxrXSCWVCC+wX0HpAqZOYdLGNv5v772o/Bsy/jrf7rZqFi5V3pPlN98pJzAWHBxPLqX0vXlYxnI7ffxAPCPRBn7z33pZLWVSESh6VUVG0SOo3CgIO5mwB7kbjdr0rSLULuvGvHQkQxFYpHt0Edj5cNSmxxo9/6p2dGZ4OfyGD5rJHOZNqb3I6u2oDo3WHJ/y/SWj2Yqm94tTRm0RTNTgl6pI+wCxPF+Wvu5MfGW8oDodrZ18c0bPwigZvGSrwRPq2LRfMGcO92oaf0Fvc+/qeLiAHSHV5M5ojC8fOm/sTzYwm7HUffcLJ/+IE7XdIrePEI/gLYEM+t73Us0hnTPv4rPOSy9WsHtTGelNYQ+pgLp8/805Y3rHi3WDrRE2F/Zch9fVxQEfC3pPgIcpcbt/9m8W07xqFuEVNdTh4zboVGy7s7enqR3armYDvvdToH6bVqEQ==",
}

BOARD_ID = 4
LIMIT = 25
START_OFFSET = 0
STOP_DATE = datetime(2024, 7, 4, 0, 0, 0)
OUTPUT_FILE = "naver_game_lounge_board_4.xlsx"


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def parse_feed_datetime(date_str: str):
    date_str = str(date_str or "").strip()
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%Y%m%d%H%M%S")
    except Exception:
        return None


def format_datetime(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def extract_text_from_contents(contents_str: str) -> str:
    if not contents_str:
        return ""

    try:
        contents_obj = json.loads(contents_str)
    except Exception:
        return ""

    lines = []

    document = contents_obj.get("document", {})
    components = document.get("components", [])

    for comp in components:
        if comp.get("@ctype") != "text":
            continue

        value_list = comp.get("value", [])
        for value_item in value_list:
            nodes = value_item.get("nodes", [])
            text_parts = []

            for node in nodes:
                if node.get("@ctype") == "textNode":
                    text = str(node.get("value", "") or "").strip()
                    if text:
                        text_parts.append(html.unescape(text))

            line = "".join(text_parts).strip()
            if line:
                lines.append(line)

    return "\n".join(lines)


def build_params(offset: int) -> Dict[str, Any]:
    return {
        "boardId": BOARD_ID,
        "buffFilteringYN": "N",
        "limit": LIMIT,
        "offset": offset,
        "order": "NEW",
    }


def request_page(offset: int) -> List[Dict[str, Any]]:
    params = build_params(offset)

    resp = requests.get(
        URL,
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("content", {}).get("feeds", [])


def collect_all_feeds() -> List[Dict[str, Any]]:
    results = []
    offset = START_OFFSET

    log("수집 시작")
    log(
        f"조건: boardId={BOARD_ID}, limit={LIMIT}, start_offset={START_OFFSET}, "
        f"기준일={STOP_DATE.strftime('%Y-%m-%d')}"
    )

    while True:
        page_no = offset + 1

        log("-" * 100)
        log(f"요청 중... page={page_no}, offset={offset}, limit={LIMIT}")

        try:
            feeds = request_page(offset)
        except Exception as e:
            log(f"요청 실패: {e}")
            break

        feed_count = len(feeds)
        log(f"응답 수신 완료: page={page_no}, offset={offset}, 수신건수={feed_count}")

        if feed_count == 0:
            log("응답 건수가 0건이라 수집 종료")
            break

        page_saved_count = 0
        should_stop = False

        for idx, item in enumerate(feeds, start=1):
            feed = item.get("feed", {})

            updated_date_raw = str(feed.get("updatedDate", "") or "").strip()
            created_date_raw = str(feed.get("createdDate", "") or "").strip()
            date_raw = updated_date_raw if updated_date_raw else created_date_raw
            date_dt = parse_feed_datetime(date_raw)

            feed_id = feed.get("feedId", "")

            if not date_dt:
                log(f"날짜 파싱 실패 -> page={page_no}, item={idx}, feedId={feed_id}")
                continue

            if date_dt < STOP_DATE:
                log(
                    f"중단 기준 도달 -> page={page_no}, item={idx}, feedId={feed_id}, "
                    f"게시날짜={format_datetime(date_dt)}"
                )
                should_stop = True
                break

            title = html.unescape(str(feed.get("title", "") or "")).strip()
            body = extract_text_from_contents(feed.get("contents", ""))
            detail_url = DETAIL_URL_FORMAT.format(feed_id=feed_id)

            row = {
                "게시판 ID": BOARD_ID,
                "페이지": page_no,
                "게시 날짜": format_datetime(date_dt),
                "게시글 제목": title,
                "게시글 본문": body,
                "URL": detail_url,
            }
            results.append(row)
            page_saved_count += 1

            log(
                f"저장 완료 -> page={page_no}, item={idx}, feedId={feed_id}, "
                f"게시날짜={row['게시 날짜']}, 제목={title[:40]}"
            )

        log(
            f"페이지 처리 완료 -> page={page_no}, offset={offset}, "
            f"페이지저장건수={page_saved_count}, 누적저장건수={len(results)}"
        )

        if should_stop:
            log("기준일 이전 데이터가 확인되어 전체 수집 종료")
            break

        offset += 1

    log("-" * 100)
    log(f"최종 수집 완료: 총 {len(results)}건")
    return results


def save_to_excel(rows: List[Dict[str, Any]], file_path: str) -> None:
    df = pd.DataFrame(
        rows,
        columns=[
            "게시판 ID",
            "페이지",
            "게시 날짜",
            "게시글 제목",
            "게시글 본문",
            "URL",
        ],
    )
    df.to_excel(file_path, index=False)
    log(f"엑셀 저장 완료: {file_path}")


def main() -> None:
    rows = collect_all_feeds()

    if not rows:
        log("저장할 데이터가 없습니다.")
        return

    save_to_excel(rows, OUTPUT_FILE)
    log("전체 작업 종료")


if __name__ == "__main__":
    main()