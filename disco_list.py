import json
import time
from datetime import datetime, timedelta, timezone

import requests


URL = "https://www.disco.re/detail/get_area_timeline/"
COOKIE = "sessionid=ncu0fpo2s6r705jufutswl30nn7tttyv; _gcl_au=1.1.776080952.1790653419; _ga=GA1.1.591524989.1790653419; _fwb=50xtjvqrGTQtz5gTcSMPVK.1790653419235; _fbp=fb.1.1790653421402.847631576992532249; _ga_G2RYCVJW11=GS2.1.s1791299442$o6$g1$t1791299443$j59$l0$h0"
LAST_PAGE = 10  # 0~10페이지: 최대 11번 조회
OUTPUT_FILE = "disco_list.json"

PAYLOAD = {
    "pnu": "1168010600",
    "address": "서울특별시 강남구 대치동",
    "sigungu_address": "서울특별시 강남구",
    "offset": 0,
    "center_lat": 37.493238997572995,
    "center_lng": 127.05669236808124,
    "prev_pnu": "1168010600",
    "prev_address": "서울특별시 강남구 대치동",
    "prev_offset": 0,
    "prev_center_lat": 37.493238997572995,
    "prev_center_lng": 127.05669236808124,
    "std_time": "",  # 조회 시작 시 한국 시간으로 설정
    "curation_refresh": "true",
    "category": "sale",
    "ignore_filter": "false",
    "sale_filter1": "",
    "sale_filter2": "",
    "fromBanner": "false",
    "limit": 15,
    "_": 0,  # 요청마다 현재 밀리초로 설정
}


def fetch_list(payload):
    params = payload.copy()
    if not params["std_time"]:
        params["std_time"] = datetime.now(
            timezone(timedelta(hours=9))
        ).strftime("%Y.%m.%d %H:%M:%S")
    items = []

    with requests.Session() as session:
        session.headers.update({
            "Accept": "*/*",
            "Referer": "https://www.disco.re/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/154.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": COOKIE,
        })

        for page in range(LAST_PAGE + 1):
            params["_"] = int(time.time() * 1000)
            response = session.get(URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()  # \\uXXXX 형태의 한글도 자동으로 디코딩

            if data.get("result") != "success":
                raise RuntimeError(f"{page}페이지 목록 조회 실패")

            page_items = data["context"]
            if not isinstance(page_items, list):
                raise ValueError("context가 JSON 배열이 아닙니다.")

            items.extend(page_items)
            print(f"[페이지 {page}] offset={params['offset']}, "
                  f"조회={len(page_items)}건, 누적={len(items)}건")

            if data.get("isend") or not page_items or page == LAST_PAGE:
                break

            next_offset = int(data["offset"])
            if next_offset <= int(params["offset"]):
                raise RuntimeError("다음 offset이 증가하지 않습니다.")

            params["prev_offset"] = params["offset"]
            params["offset"] = next_offset
            params["std_time"] = data.get("std_time") or params["std_time"]
            params["ignore_filter"] = (
                "true" if data.get("ignore_filter_next_time") else "false"
            )
            time.sleep(0.5)

    return items


if __name__ == "__main__":
    result = fetch_list(PAYLOAD)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"저장 완료: {OUTPUT_FILE} ({len(result)}건)")
