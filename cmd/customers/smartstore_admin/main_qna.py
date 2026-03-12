import json
import time

import pandas as pd
import requests


URL = "https://sell.smartstore.naver.com/api/v3/contents/comments/pages"

COOKIE = """NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; nid_inf=1108943888; NID_AUT=5AGU4vGOG1BucmYTV/Ot0kxZfrlkbyeReiDUVFr+LTpxwFeGz7Ek3LnsOFlNBSx7; CBI_SES=BPH3JArZy1dvOpOm4G/0jcfKJ1F8TkTLbWp3n8Yj8LHsmEojJSWnouuyfhrN4fqx83LdlXPWVsI0rjEtNv8bZMV+PrTC+rLp8sBIR19aH8q+HhUlG9QBT60rgKTds1J74m2k0uzirqHEeDK/AzVz65dTZP0pdxMuWwQEK9W2zsOKLUyX7iBaleky1kAYOjGEk/tbrOCyF1wdL4LFmM6PBA1gu761+3Fmr/KY5zE6pM4b1q6fdMYesRH1t3Tl0V+nYBhKW82h/eAgY2nYqocwVSVDrdoQ+me/iJiZ7XRUYoAOgcMHT8xyqe+8yU7ujTAlck2SAuIEzJcnEVTdtSNTckse73xZHOBxZIMKF/dABuZvoZVm/iGnPbLqtnhtmxngMwsS14v7mKrFFJAyrTRsM681QFuqHxijZbzjJmaKsf7a/+/VNdzvyRohH8HV9cIM; NSI=2lK46D8m8rIQNLZPpu9G85CRbLY4pdrvqmRjXLdF; NACT=1; SRT30=1773342502; NID_SES=AAAB8Hyygcie9hVv9+KX10SGQcPoLzofZizxefUqagGmXf52nL1BWXWcdU8OcYKNmosGF3bvQfSDbBxr8UjUrnCEXJPGhiKq5a+E6LIQXQrTx6wYY+VpDQH7dJIOZrQVcIg9xUZiQgpevLFURfwxvYe34DhnjYQ2SYIc/T7p0KqNVXmscittvHB+3vLfWZN3LiiLMRG01HkI4zvWfCYgg8UjVy7ErlDlcQbe0WDEUUFo2QC/9b49Rmc2kAJFDd+ARUq2pr6FvJBuliEmtWcMdDanlBVAZTWv6wqdagojaPeSoGgqJDtXzvu7DaHToIBhSY5U9ik0lxat/wGED8QCyoV407eyJ9NcpGGIIml/kfZycNgB+8g5rTwzZm8QTjM9xDrORl+1WQsLcV0tJOUKkIb9EVAdlppSYD6wHqR7Z3Eunm3jwO2f00EZOKISsSG3XRgngcfXlaKvvheWcb32BkcExFaq9YKlIIGxoFYtPDUE4yZWQFa86znuomUwAF9g+lczwjbAvKthuwI84Fhchdx6M9y54spwDYy+OjFvXVUFJ2D8fNIbUQgOZTjsVHeTWh8UbmDrzWiy1ZtbrsyLUlPOmKzqLLwHny8izta4sYo+HlVMDPTOIdGXQ2kcHgefYROlrupLgD7JYdRniW1ik4iaYRs=; cto_bundle=rfg_7F9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGalNQMjhnTXZEWVRQTTJHdFY0SEZibHRBSHI1VEwxVTV1UTF5ZzNIa1JBMk9MJTJCNWdVeE5TVXlwTGszUFBQYmlwcTIlMkJYcnV5S21DUUhVRFZLZjhZeVBldGJHN0cwWkRJUWt2WnNtd3Z6JTJCQ2JR; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5kP2M3DdMU8tsDp3AKjvaVpjfk1Q7Sx+bbHQJYWeHFd+0="; SRT5=1773344868; BUC=1xZxTND0-5vjHbNqEDlA7_sBtTqBXCfTTWv4gse0mbk="""

START_DATE = "2024-03-13T00:00:00.000+09:00"
END_DATE = "2026-03-13T23:59:59.999+09:00"

START_PAGE = 0
SIZE = 300
TOTAL_COUNT = 366
RANGE = 5

CSV_FILE = "smartstore_qna.csv"
XLSX_FILE = "smartstore_qna.xlsx"

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
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
    "x-current-state": "https://sell.smartstore.naver.com/#/comment/",
    "x-current-statename": "main.contents.comment",
    "x-to-statename": "main.contents.comment",
    "cookie": COOKIE,
}


def build_params(start_date: str, end_date: str, page: int, size: int, total_count: int) -> dict:
    return {
        "commentType": "",
        "endDate": end_date,
        "keyword": "",
        "page": page,
        "range": RANGE,
        "searchKeywordType": "PRODUCT_NAME",
        "sellerAnswer": "",
        "size": size,
        "startDate": start_date,
        "totalCount": total_count,
    }


def fetch_page(
        session: requests.Session,
        start_date: str,
        end_date: str,
        page: int,
        size: int,
        total_count: int,
) -> list[dict]:
    params = build_params(start_date, end_date, page, size, total_count)
    resp = session.get(URL, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    contents = data.get("contents", [])

    rows = []
    for item in contents:
        rows.append({
            "id": item.get("id"),
            "regDate": item.get("regDate"),
            "modDate": item.get("modDate"),
            "replyCount": item.get("replyCount"),
            "commentContent": item.get("commentContent"),
            "productName": item.get("productName"),
            "channelProductNo": item.get("channelProductNo"),
        })
    return rows


def collect_all(
        start_date: str,
        end_date: str,
        start_page: int,
        size: int,
        total_count: int,
) -> list[dict]:
    all_rows = []
    page = start_page

    with requests.Session() as session:
        while True:
            print(f"page={page} 요청중...")
            rows = fetch_page(session, start_date, end_date, page, size, total_count)

            if not rows:
                print(f"page={page} rows 비어있음 -> 중지")
                break

            print(f"page={page} 수집건수={len(rows)}")
            all_rows.extend(rows)
            page += 1
            time.sleep(2)

    return all_rows


def save_files(rows: list[dict], csv_file: str, xlsx_file: str) -> None:
    columns = [
        "id",
        "regDate",
        "modDate",
        "replyCount",
        "commentContent",
        "productName",
        "channelProductNo",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_file, index=False)


def main() -> None:
    all_rows = collect_all(
        start_date=START_DATE,
        end_date=END_DATE,
        start_page=START_PAGE,
        size=SIZE,
        total_count=TOTAL_COUNT,
    )

    print(f"총 수집건수: {len(all_rows)}")
    print(json.dumps(all_rows, ensure_ascii=False, indent=2))

    save_files(all_rows, CSV_FILE, XLSX_FILE)
    print(f"CSV 저장 완료: {CSV_FILE}")
    print(f"XLSX 저장 완료: {XLSX_FILE}")


if __name__ == "__main__":
    main()