import json
import requests


# =========================
# 수정할 값
# =========================
KEYWORD = "생산직"
LIMIT = 12
SORT = "relevance"
PAGE = 4
CATEGORY = 0
CATEGORY_GROUP_ID = 0


# =========================
# 고정값
# =========================
URL = "https://comento.kr/api/v2/search/community"

params = {
    "keyword": KEYWORD,
    "limit": LIMIT,
    "sort": SORT,
    "page": PAGE,
    "category": CATEGORY,
    "category_group_id": CATEGORY_GROUP_ID,
}

headers = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "baggage": "sentry-environment=production,sentry-release=ElySQ7EtANxbMVRTJ0cnV,sentry-public_key=97365f23b2d9992b6367167cf3fd8914,sentry-trace_id=23791b68622c48de8ed025f901170441,sentry-sample_rate=0.1,sentry-sampled=false",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://comento.kr/search/community/%EC%83%9D%EC%82%B0%EC%A7%81?type=mentoring",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sentry-trace": "7c2aa16db1a5443a9f739dbf5ef3f548-babe98ee75a33348-0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


def main():
    try:
        response = requests.get(
            URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        print("요청 URL:", response.url)
        print("상태코드:", response.status_code)

        response.raise_for_status()

        data = response.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))

        with open("comento_search_community.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("저장 완료: comento_search_community.json")

    except requests.exceptions.RequestException as e:
        print("요청 실패:", e)
        if getattr(e, "response", None) is not None:
            print("응답 본문:", e.response.text)
    except ValueError as e:
        print("JSON 파싱 실패:", e)
        print("응답 본문:", response.text)


if __name__ == "__main__":
    main()