import random
import time

import pandas as pd
import requests


INPUT_CSV = "smartstore_qna.csv"
OUTPUT_CSV = "smartstore_qna_replies.csv"
OUTPUT_XLSX = "smartstore_qna_replies.xlsx"

COOKIE = """NAC=sTKYB8Q0oCuv; NNB=5JW4LAIBW6PGS; ASID=da9384ec0000019c9a7d0e5500000022; _fwb=45c3P102KEBT3izE67lKPr.1772118416325; _fbp=fb.1.1772118417182.532189996571638526; nstore_session=LKnBxxh1L2ipiCmyd3Difk2R; nstore_pagesession=jj5IAlqW5bXVpssLsGC-225598; nid_inf=1108943888; NID_AUT=5AGU4vGOG1BucmYTV/Ot0kxZfrlkbyeReiDUVFr+LTpxwFeGz7Ek3LnsOFlNBSx7; CBI_SES=BPH3JArZy1dvOpOm4G/0jcfKJ1F8TkTLbWp3n8Yj8LHsmEojJSWnouuyfhrN4fqx83LdlXPWVsI0rjEtNv8bZMV+PrTC+rLp8sBIR19aH8q+HhUlG9QBT60rgKTds1J74m2k0uzirqHEeDK/AzVz65dTZP0pdxMuWwQEK9W2zsOKLUyX7iBaleky1kAYOjGEk/tbrOCyF1wdL4LFmM6PBA1gu761+3Fmr/KY5zE6pM4b1q6fdMYesRH1t3Tl0V+nYBhKW82h/eAgY2nYqocwVSVDrdoQ+me/iJiZ7XRUYoAOgcMHT8xyqe+8yU7ujTAlck2SAuIEzJcnEVTdtSNTckse73xZHOBxZIMKF/dABuZvoZVm/iGnPbLqtnhtmxngMwsS14v7mKrFFJAyrTRsM681QFuqHxijZbzjJmaKsf7a/+/VNdzvyRohH8HV9cIM; NSI=2lK46D8m8rIQNLZPpu9G85CRbLY4pdrvqmRjXLdF; NACT=1; SRT30=1773342502; NID_SES=AAAB8Hyygcie9hVv9+KX10SGQcPoLzofZizxefUqagGmXf52nL1BWXWcdU8OcYKNmosGF3bvQfSDbBxr8UjUrnCEXJPGhiKq5a+E6LIQXQrTx6wYY+VpDQH7dJIOZrQVcIg9xUZiQgpevLFURfwxvYe34DhnjYQ2SYIc/T7p0KqNVXmscittvHB+3vLfWZN3LiiLMRG01HkI4zvWfCYgg8UjVy7ErlDlcQbe0WDEUUFo2QC/9b49Rmc2kAJFDd+ARUq2pr6FvJBuliEmtWcMdDanlBVAZTWv6wqdagojaPeSoGgqJDtXzvu7DaHToIBhSY5U9ik0lxat/wGED8QCyoV407eyJ9NcpGGIIml/kfZycNgB+8g5rTwzZm8QTjM9xDrORl+1WQsLcV0tJOUKkIb9EVAdlppSYD6wHqR7Z3Eunm3jwO2f00EZOKISsSG3XRgngcfXlaKvvheWcb32BkcExFaq9YKlIIGxoFYtPDUE4yZWQFa86znuomUwAF9g+lczwjbAvKthuwI84Fhchdx6M9y54spwDYy+OjFvXVUFJ2D8fNIbUQgOZTjsVHeTWh8UbmDrzWiy1ZtbrsyLUlPOmKzqLLwHny8izta4sYo+HlVMDPTOIdGXQ2kcHgefYROlrupLgD7JYdRniW1ik4iaYRs=; cto_bundle=rfg_7F9qSmJKeGVhNVY3S3J3bHVUcHNlJTJGalNQMjhnTXZEWVRQTTJHdFY0SEZibHRBSHI1VEwxVTV1UTF5ZzNIa1JBMk9MJTJCNWdVeE5TVXlwTGszUFBQYmlwcTIlMkJYcnV5S21DUUhVRFZLZjhZeVBldGJHN0cwWkRJUWt2WnNtd3Z6JTJCQ2JR; BUC=1xZxTND0-5vjHbNqEDlA7_sBtTqBXCfTTWv4gse0mbk=; CBI_CHK="r5V0mf9uRUZHZ/vmLGy3ez7f4/k4aqWXL5o03eN68fqLRkfANj2mMKLuHew5Nt7kk+Us2vGKYu/1dgfESwLJyiS3ngXtYbQAOCAoOTU+nJ9PUJKwsH10WfMnZEJJRU5k8D+NiQrRcqCAjrXPGG+sOJLd6Sgen5e2FxIbrHmusbg="""

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


def fetch_replies(session: requests.Session, qna_id: str) -> str:
    url = f"https://sell.smartstore.naver.com/api/v3/contents/comments/{qna_id}/replies"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    texts = []

    for item in data:
        text = item.get("commentContent", "")
        if text:
            texts.append(str(text).strip())

    return "\n".join(texts)


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    rows = df.to_dict(orient="records")

    with requests.Session() as session:
        for idx, row in enumerate(rows, 1):
            qna_id = row.get("id", "").strip()

            if not qna_id:
                row["replies"] = ""
                row["qna"] = row.get("commentContent", "")
                continue

            print(f"[{idx}/{len(rows)}] id={qna_id} 요청중...")

            try:
                replies = fetch_replies(session, qna_id)
                row["replies"] = replies
                row["qna"] = row.get("commentContent", "")
                print(f"[{idx}/{len(rows)}] replies 길이={len(replies)}")
            except Exception as e:
                row["replies"] = ""
                row["qna"] = row.get("commentContent", "")
                print(f"[{idx}/{len(rows)}] 실패: {e}")

            sleep_sec = random.uniform(1.0, 3.0)
            time.sleep(sleep_sec)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    out_df.to_excel(OUTPUT_XLSX, index=False)

    print(f"CSV 저장 완료: {OUTPUT_CSV}")
    print(f"XLSX 저장 완료: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()