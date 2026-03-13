import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests


INPUT_CSV = "smartstore_qna.csv"
OUTPUT_CSV = "smartstore_qna_replies.csv"
OUTPUT_XLSX = "smartstore_qna_replies.xlsx"
MAX_WORKERS = 6

COOKIE = """NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; cto_bundle=PP7e9l9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGamRoOUljcVJXYmdpZUlMd2pZM0glMkI3a0lBc0IwUXFlYXV5bll1RERVeFYlMkJTa29pQlh4TlpJSCUyQms4dlVlb3hyRnBkTFZLZmRHM09BeHhEVlN3RWQlMkJOc2tucEdpTzZJNFo4Z0R2bExCYTNndW4; nid_inf=1114662082; NID_AUT=eWfKDXfxjNP0QeBSSWooOdSK8Oge1zEmloU+8ADX/rIMukDbYtkqmJpaFK5ojErK; page_uid=jkdA5lqps2y0BMWCuJo-366763; CBI_SES=6YmLVKT+AnMWKmZ6wWvlmQtgPfflEPlCrmmg8tpa1dMS3bQx7QgxNxaVBWtSwxgy2IjN5okTKbd3gfWDPN3rviNyIlWzgdOKF8cb5Q9pI2k8bIEnMRhZM/K++yL6M5qLvfbbRBdTeMXHbhR6Ahg9TnGx6O9lvCNrMz/42ueWuLyHypK5Ac1J0TwvrcgVb3GaYxzN9eQbeATT9v0lpyJ67uHZgjSEdqvVyyqk6CVyHcFYtA22Q/v2TVMRtYWRN6LBAQ48H2g/TVjcDifCPjfmViExp/0pMINfmegkOI5r0NNguC/rzRZpvpWMzqZrDTC4/o6EhPbVbs9fR3heDygQ5eYih7j26eq1cVsNNpW8+Caz4n4b/4g+Twhlrw/mXkhZmm87BjKnCFvxw1xj+2WLWdStu8gnjFrpW8FMZrVL/8K+X62yO4MtFvKcJQVOfJ+q; NSI=E3kTGUMGr3KiA5sk67DT8nbJ61v47hAefJJEOzPh; NACT=1; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5kLpbaesATR7cYxM2lVsLPwugT8hriDVmwh3R25YyPw5g="; NID_SES=AAAB446NyG/Y3UYEcSFa8597GZIBjdnxtgEYWm1cKc/WDA4W8LRhac1salxUq6OTlfP2eectO4rRgsOCRFIz3DENz8kEHJqFSiOJ7Bp1jfOHytTtfxKDrmoD1fdnhQOCfV/31gXgobiuTKB267Z0/6kqbephwGkrd71EQNmK6+2Ebg2M8KpQyS+XwkBJnko0sWSZO+28T0Ibc4Gp2qvUNhRSNsVyEoLJmn2kKsCpdXXnMsY7y402td/o0MD6HwsMRc3SjFSG6jXyZOUqIiJZhShtHqFv7ZKEoWY8sRArr4AoQPRN3UB8a6q8Z/fI1kyuTnD5Wy6q2Cv0glQ0XUocCWGxwv32nqcgy/zQpqUSA+TL7BlJZVMQ8ipofdr3q3HKg4poaPF+N4F8g9v6C4X/4PJ2s+aZHNtGnrjCoFqseF56EW5oLHizvNXdSug9RMJvJHKALf753A2U12Lv/Lk2qa9HLGtYmWuV4AB9wbEpEZYPDXIe+2G4ivDsVx0RHJ5gQvyQIuFepxZi0BkaP48BhgT3FOwXYJgJjcFUcwNf0f0WjGt94OGfJrSosYMyeu/vUWdQwxdjILW0qcoDNCitDCq73O5iUY/XLDlRbMA98XYZ+2iCzAe7Ep58JcgWJHzeFN0OfDl9S2aT0fmSVkSswLOwep0=; SRT30=1773420567; SRT5=1773420567; BUC=I2gDZJP3YA5qRMIzGThWxaB4kXISxKnNnBItoAtmNEA="""
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


def fetch_replies(qna_id: str) -> str:
    time.sleep(random.uniform(0.5, 1.3))

    url = f"https://sell.smartstore.naver.com/api/v3/contents/comments/{qna_id}/replies"

    with requests.Session() as session:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    texts = []
    for item in data:
        text = str(item.get("commentContent", "")).strip()
        if text:
            texts.append(text)

    return "\n".join(texts)


def process_row(index: int, row: dict) -> tuple[int, dict]:
    qna_id = str(row.get("id", "")).strip()
    row["qna"] = row.get("commentContent", "")

    if not qna_id:
        row["replies"] = ""
        return index, row

    try:
        replies = fetch_replies(qna_id)
        row["replies"] = replies
        print(f"[{index}] id={qna_id} 성공 / replies 길이={len(replies)}")
    except Exception as e:
        row["replies"] = ""
        print(f"[{index}] id={qna_id} 실패: {e}")

    return index, row


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    rows = df.to_dict(orient="records")

    results = [None] * len(rows)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process_row, idx, row.copy())
            for idx, row in enumerate(rows)
        ]

        for future in as_completed(futures):
            idx, row = future.result()
            results[idx] = row

    out_df = pd.DataFrame(results)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    out_df.to_excel(OUTPUT_XLSX, index=False)

    print(f"CSV 저장 완료: {OUTPUT_CSV}")
    print(f"XLSX 저장 완료: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()