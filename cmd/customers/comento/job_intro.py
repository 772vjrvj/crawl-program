import json
import requests


# =========================
# 수정할 값
# =========================
PAGE = 302
PER_PAGE = 10
JOB_GROUP = "all"
COOKIE_STRING = ""  # 브라우저에서 복사한 cookie 문자열 넣기


# =========================
# 고정값
# =========================
URL = "https://comento.kr/api/job-wiki/index"

params = {
    "page": PAGE,
    "perPage": PER_PAGE,
    "jobGroup": JOB_GROUP,
}

headers = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "baggage": "sentry-environment=production,sentry-release=ElySQ7EtANxbMVRTJ0cnV,sentry-public_key=97365f23b2d9992b6367167cf3fd8914,sentry-trace_id=cf4c330acbbb4fdd8a4db968d8f00a86,sentry-sample_rate=0.1,sentry-sampled=false",
    "cache-control": "no-cache",
    "cookie": COOKIE_STRING,
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://comento.kr/job-wiki",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sentry-trace": "cf4c330acbbb4fdd8a4db968d8f00a86-a1782936f02c5687-0",
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

        with open("comento_job_wiki.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("저장 완료: comento_job_wiki.json")

    except requests.exceptions.RequestException as e:
        print("요청 실패:", e)
        if getattr(e, "response", None) is not None:
            print("응답 본문:", e.response.text)
    except ValueError as e:
        print("JSON 파싱 실패:", e)
        print("응답 본문:", response.text)


if __name__ == "__main__":
    main()