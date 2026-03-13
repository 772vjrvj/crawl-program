from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests


URL = "https://sell.smartstore.naver.com/api/v3/contents/reviews/search"

COOKIE = '''NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; NACT=1; NID_SES=AAAB446NyG/Y3UYEcSFa8597GZIBjdnxtgEYWm1cKc/WDA4W8LRhac1salxUq6OTlfP2eectO4rRgsOCRFIz3DENz8kEHJqFSiOJ7Bp1jfOHytTtfxKDrmoD1fdnhQOCfV/31gXgobiuTKB267Z0/6kqbephwGkrd71EQNmK6+2Ebg2M8KpQyS+XwkBJnko0sWSZO+28T0Ibc4Gp2qvUNhRSNsVyEoLJmn2kKsCpdXXnMsY7y402td/o0MD6HwsMRc3SjFSG6jXyZOUqIiJZhShtHqFv7ZKEoWY8sRArr4AoQPRN3UB8a6q8Z/fI1kyuTnD5Wy6q2Cv0glQ0XUocCWGxwv32nqcgy/zQpqUSA+TL7BlJZVMQ8ipofdr3q3HKg4poaPF+N4F8g9v6C4X/4PJ2s+aZHNtGnrjCoFqseF56EW5oLHizvNXdSug9RMJvJHKALf753A2U12Lv/Lk2qa9HLGtYmWuV4AB9wbEpEZYPDXIe+2G4ivDsVx0RHJ5gQvyQIuFepxZi0BkaP48BhgT3FOwXYJgJjcFUcwNf0f0WjGt94OGfJrSosYMyeu/vUWdQwxdjILW0qcoDNCitDCq73O5iUY/XLDlRbMA98XYZ+2iCzAe7Ep58JcgWJHzeFN0OfDl9S2aT0fmSVkSswLOwep0=; SRT30=1773426682; BUC=D0UIj06f2W2KzLWIz6a6um3jy-tBuhPjgUSX1iQsnSQ=; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5k8rpWVJPGk5dv3HWGVNjNcL4cYoo2fKIblkABD2KJ/HU="'''

START_DATE = "2020-09-01"   # 조회 시작일
FINAL_TO_DATE = None        # None이면 오늘까지, 직접 넣으려면 "2026-03-12"

SIZE = 500
MAX_WORKERS = 6

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://sell.smartstore.naver.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://sell.smartstore.naver.com/",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "x-current-state": "https://sell.smartstore.naver.com/#/review/search",
    "x-current-statename": "main.contents.review.search",
    "x-to-statename": "main.contents.review.search",
    "cookie": COOKIE,
}


def to_api_from_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00.000+09:00")


def to_api_to_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT23:59:59.999+09:00")


def parse_ymd(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def add_one_year_minus_one_day(dt: datetime) -> datetime:
    try:
        return dt.replace(year=dt.year + 1) - timedelta(days=1)
    except ValueError:
        # 2월 29일 같은 케이스 보정
        return dt.replace(month=2, day=28, year=dt.year + 1) - timedelta(days=1)


def build_payload(from_date: str, to_date: str, page: int, size: int) -> dict:
    return {
        "benefitKindTypeStringList": [],
        "contentsStatusTypes": [],
        "fromDate": from_date,
        "page": page,
        "reviewContentClassTypes": [],
        "reviewScores": [],
        "reviewSearchSortType": "REVIEW_CREATE_DATE_DESC",
        "reviewTypes": [],
        "searchKeyword": "",
        "searchKeywordType": "IDS",
        "size": size,
        "sort": [],
        "storeTypes": [],
        "toDate": to_date,
        "useSelectedDate": False,
    }


def fetch_page(from_date: str, to_date: str, page: int, size: int) -> tuple[int, list[dict]]:
    payload = build_payload(from_date, to_date, page, size)

    with requests.Session() as session:
        resp = session.post(URL, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        contents = data.get("contents", [])

        rows = []
        for item in contents:
            rows.append({
                "reviewContent": item.get("reviewContent", ""),
                "reviewScore": item.get("reviewScore", ""),
                "productName": item.get("productName", ""),
                "productNo": item.get("productNo", ""),
                "id": item.get("id", ""),
                "createDate": item.get("createDate", ""),
            })

        return page, rows


def fetch_year_range(from_date: str, to_date: str, size: int, max_workers: int) -> list[dict]:
    all_rows = []
    next_page = 0
    stop = False

    while not stop:
        batch_pages = list(range(next_page, next_page + max_workers))
        page_results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_page, from_date, to_date, page, size): page
                for page in batch_pages
            }

            for future in as_completed(futures):
                page = futures[future]
                try:
                    result_page, rows = future.result()
                    page_results[result_page] = rows
                    print(f"{from_date} ~ {to_date} / page={result_page} / 수집건수={len(rows)}")
                except Exception as e:
                    page_results[page] = []
                    print(f"{from_date} ~ {to_date} / page={page} 실패: {e}")

        for page in batch_pages:
            rows = page_results.get(page, [])
            if not rows:
                stop = True
                break
            all_rows.extend(rows)

        next_page += max_workers

    return all_rows


def build_date_ranges(start_date_str: str, final_to_date_str: str | None) -> list[tuple[str, str]]:
    start_dt = parse_ymd(start_date_str)

    if final_to_date_str:
        final_dt = parse_ymd(final_to_date_str)
    else:
        final_dt = datetime.now()

    ranges = []
    current_start = start_dt

    while current_start <= final_dt:
        current_end = add_one_year_minus_one_day(current_start)
        if current_end > final_dt:
            current_end = final_dt

        ranges.append((
            to_api_from_date(current_start),
            to_api_to_date(current_end),
        ))

        current_start = current_end + timedelta(days=1)

    return ranges


def save_files(rows: list[dict], csv_path: str, xlsx_path: str) -> None:
    columns = ["reviewContent", "reviewScore", "productName", "productNo", "id", "createDate"]
    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)


def main() -> None:
    date_ranges = build_date_ranges(START_DATE, FINAL_TO_DATE)
    all_rows = []

    for idx, (from_date, to_date) in enumerate(date_ranges, 1):
        print(f"[{idx}/{len(date_ranges)}] 구간 조회 시작: {from_date} ~ {to_date}")
        rows = fetch_year_range(from_date, to_date, SIZE, MAX_WORKERS)
        print(f"[{idx}/{len(date_ranges)}] 구간 조회 완료: {len(rows)}건")
        all_rows.extend(rows)

    save_files(all_rows, "smartstore_reviews.csv", "smartstore_reviews.xlsx")
    print(f"완료: 총 {len(all_rows)}건 저장")


if __name__ == "__main__":
    main()