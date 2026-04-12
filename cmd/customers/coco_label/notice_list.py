import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

import requests


BASE_URL = "https://coco-label.com/admin/ajax/contents/v2/api.cm"

COMMON_PARAMS = {
    "site_code": "S202410211a92d560f8f0e",
    "unit_code": "u202410216715ffa21a17f",
    "endpoint": "posts",
    "type": "post",
    "board_code": "b202410229a3f4f7779060",
    "keyword": "",
    "status": "",
    "page_size": 20,
}

OUTPUT_JSON = "coco_posts.json"
MAX_WORKERS = 8

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-length": "0",
    "cookie": "al=KR; _fwb=153Fgpdb68AF6wtU0X73tQL.1774768427504; _fbp=fb.1.1774768429368.806216781255867927; __fs_imweb=%7B%22deviceId%22%3A%22mnbfcju9-0430ae7c4b36b520ae04b4544cb4be37-454gbpp%22%2C%22useSubDomain%22%3A%22Y%22%7D; _dd_s=aid=a4e0643f-4dfa-4b70-ad58-a8b3d777aa9d&rum=2&id=090e1d54-79c0-4615-bc55-dd67bba97bc4&created=1775739387350&expire=1775740666071; __bs_imweb=%7B%22deviceId%22%3A%22019d387118fb7a158d09c8b1123c61b0%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202410211a92d560f8f0e%22%2C%22unitCode%22%3A%22u202410216715ffa21a17f%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019d7525774f7118a76f1c7fd0aa4ebe%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3ODY5MjAsImV4cCI6MTc3NTc4NzUyMH0.G47myWFkCyQnlgSss_fi2Gko4aIuCnJc5aUCW4dN4hM%22%2C%22referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2F%22%2C%22initialReferrer%22%3A%22%40direct%22%2C%22initialReferrerDomain%22%3A%22%40direct%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-04-10T02%3A08%3A51.347Z%22%2C%22commonSessionId%22%3A%22sc_019d752577517bb1a5f8a1048f282778%22%2C%22commonSessionUpdatedAt%22%3A%222026-04-10T02%3A08%3A41.061Z%22%2C%22customSessionId%22%3A%22cs_019d7525775276e291c8906215a43ad9%22%2C%22customSessionUpdatedAt%22%3A%222026-04-10T02%3A08%3A41.062Z%22%2C%22browser_session_id%22%3A%22019d7525774f7118a76f1c7fd0aa4ebe%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3ODY5MjAsImV4cCI6MTc3NTc4NzUyMH0.G47myWFkCyQnlgSss_fi2Gko4aIuCnJc5aUCW4dN4hM%22%2C%22initial_referrer%22%3A%22%40direct%22%2C%22initial_referrer_domain%22%3A%22%40direct%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-04-10T02%3A08%3A51.347Z%22%2C%22common_session_id%22%3A%22sc_019d752577517bb1a5f8a1048f282778%22%2C%22common_session_updated_at%22%3A%222026-04-10T02%3A08%3A41.061Z%22%2C%22custom_session_id%22%3A%22cs_019d7525775276e291c8906215a43ad9%22%2C%22custom_session_updated_at%22%3A%222026-04-10T02%3A08%3A41.062Z%22%7D; IMWEBVSSID=2372eadpe4lfn41nsnkc597oggcda7hvh96sgpu09vnjuvmsqge9k4ths3kkvv23i9ipfd3jhgp00p75brvn8jfkgiamjb63ctktv00; ISDID=69db984ebf2cf; ilc=%2BptAWpJ8GLxIVCY4yyewr0sI3mA2nt6gsm4mOiTKFXA%3D; ial=c81c5d84a43a12e659a0fa45c685e65ed4820ef001221e91c6eec9061d71f124; _clck=1r1oz16%5E2%5Eg55%5E0%5E2279; IMWEB_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJob3N0IjoiY29jby1sYWJlbC5jb20iLCJzaXRlQ29kZSI6IlMyMDI0MTAyMTFhOTJkNTYwZjhmMGUiLCJ1bml0Q29kZSI6InUyMDI0MTAyMTY3MTVmZmEyMWExN2YiLCJtZW1iZXJDb2RlIjoibTIwMjUwNTIwMzIxNTI5NTU5ZGUyZiIsInJvbGUiOiJvd25lciIsImlhdCI6MTc3NTk5OTA3OSwiZXhwIjoxNzc1OTk5Mzc5LCJpc3MiOiJpbXdlYi1jb3JlLWF1dGgtc2l0ZSJ9.iHMotFypZwDv_fT9t8eCHiqhtqlXS7szLMxWQTSOhxg; IMWEB_REFRESH_TOKEN=8298d8c4-2f70-436e-9d46-2b1821abe5d5; mp_a4939111ea54962dbf95fe89a992eab3_mixpanel=%7B%22distinct_id%22%3A%22%22%2C%22%24device_id%22%3A%22920327e0-74a9-4609-90f6-77825e72978e%22%2C%22from_imweb_office%22%3Afalse%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fbackpg%2Flogin.cm%3Fback_url%3DaHR0cHM6Ly9jb2NvLWxhYmVsLmNvbS9hZG1pbg%253D%253D%22%2C%22%24initial_referring_domain%22%3A%22coco-label.com%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%7D; _clsk=1f0pg02%5E1775999317168%5E15%5E1%5Eq.clarity.ms%2Fcollect",
    "origin": "https://coco-label.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://coco-label.com/_/site-content/",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}


def build_url(page: int) -> str:
    params = COMMON_PARAMS.copy()
    params["page"] = page
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_page(page: int) -> tuple[int, list[dict]]:
    url = build_url(page)

    with requests.Session() as session:
        response = session.post(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        res_json = response.json()
        posts = res_json.get("data", {}).get("posts", [])

        parsed = []
        for item in posts:
            post = item.get("post", {})
            parsed.append({
                "code": post.get("code", ""),
                "subject": post.get("subject", ""),
                "wtime": post.get("wtime", ""),
                "board_code": post.get("board_code", ""),
                "site_code": post.get("site_code", ""),
                "unit_code": post.get("unit_code", ""),
            })

        return page, parsed


def fetch_page_batch(start_page: int, batch_size: int) -> dict[int, list[dict]]:
    page_data = {}

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        future_map = {
            executor.submit(fetch_page, page): page
            for page in range(start_page, start_page + batch_size)
        }

        for future in as_completed(future_map):
            page = future_map[future]
            try:
                result_page, items = future.result()
                page_data[result_page] = items
            except Exception as e:
                print(f"[에러] page={page} {e}")
                page_data[page] = []

    return page_data


def main():
    all_items = []
    prev_page_items = None
    start_page = 1
    stop = False

    while not stop:
        end_page = start_page + MAX_WORKERS - 1
        print(f"[배치요청] {start_page} ~ {end_page}")

        batch_data = fetch_page_batch(start_page, MAX_WORKERS)

        for page in range(start_page, end_page + 1):
            items = batch_data.get(page, [])

            page_count = len(items)
            print(f"[완료] page={page} 수집={page_count} 누적예정={len(all_items) + page_count}")

            if not items:
                print(f"[종료] page={page} 데이터 없음 / 누적={len(all_items)}")
                stop = True
                break

            if prev_page_items is not None and items == prev_page_items:
                print(f"[종료] page={page} 직전 페이지와 동일 / 누적={len(all_items)}")
                stop = True
                break

            all_items.extend(items)
            prev_page_items = items

        start_page += MAX_WORKERS

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=4)

    print(f"[저장완료] {OUTPUT_JSON} / 총 {len(all_items)}건")


if __name__ == "__main__":
    main()