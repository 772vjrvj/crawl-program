import json
import requests


# =========================
# 수정할 값
# =========================
PAGE = 99
PER_PAGE = 10
JOB = ""  # 예: "developer" / 비우면 전체
COOKIE_STRING = """_fwb=34QSR09a9Uk8ZK2NEQ1HA7.1773201199848; _hackle_hid=7bff8520-b439-446a-ac0d-10f12a5cada4; _hackle_mkt_V944yZFr=%7B%7D; _gcl_au=1.1.254692046.1773201201; _fbp=fb.1.1773201200922.993427587245645599; _fcOM={"k":"747430fabc328dfc-3767257719cdb053c3c6a19","i":"220.94.196.191.39962","r":1773201200942}; _ga=GA1.1.1464015753.1773201201; _clck=wrltiu%5E2%5Eg49%5E0%5E2261; LOGIN_SOCIAL_TYPE_KEY=kakao; XSRF-TOKEN=eyJpdiI6IjExbHpFTCtHSTZ3bllMa2EybHhqMlE9PSIsInZhbHVlIjoiSXU4bndrSUJtdm5xQ2JFUUg3NDVFUzJMaXM2S2RRWnFxOG1xVDdnQk5PT0ZDWEJsNWJWR1lRQm1rS2IvMGl0clB4Yi9nU1FOZFRhY1IwSHNPaTJxRUw4aEdVekswQ2hPU0xnN2dNbnllZktQSTFDT0FRd1Y1M1RPVlh5UUExKzkiLCJtYWMiOiJlODdjZDJiN2JiMzM1OGUzMjEwN2ZlZmM2ZTg5ZDYyZmQ4OWYyNmYwZDczYTgyODQ0YWFjN2VjYmMwMzUxNDlkIiwidGFnIjoiIn0%3D; remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d=eyJpdiI6IkFvWmNSYUt2dGxHak0wTDV4TFpPZ1E9PSIsInZhbHVlIjoiY1FQS1NWTVRpclZab0hFSDFpTDQzZUo0R1ZRQlQyaUFLalJzS2hrZHArQ25XeG81a3dRbG84K0dGdWdZNW5weERUd0lGTGdsdmUxekowcmdIVTBtdVZkZ1VKWWZEcWNIbHhMZWpyUFlhTmlyMVd4bU1rNnVZU0swVTFqbnF2VXBoU1lwZWFpVTlnNVJZdzB5UC9CSkhrSTJHNlVMZ2oxV01FYjVuZ1NJMFJKZ3EzR3lFS0VpeW9NNTFWd2E4MWVmZGNVWFd3NHBxTnROeWg2Z1FlbHpGT1hqVXFxNWUySzljRzA1R0p4SE51ST0iLCJtYWMiOiJlMTM3OTFiNTM0ZDY4NzYzOTgwMzg1NThjMTM4ZGMwZTlhZjIxZjA0ODg1YTM4YzJmMDExYmU1YWY4MTA5MTlhIiwidGFnIjoiIn0%3D; couser=eyJpdiI6Ingra1JVVjJobVlrYk1EbDd6c1Zyb2c9PSIsInZhbHVlIjoiNXVUWFpIVElrQjZPb2hWTkUwdUR1b2FkNmwvSll4VTk2ZDVpUUZPd3VSWE95ckRWelc4ZHRSWHIyTE1BT0JESFpxRUkrSjZnbVZjMWhuTDJCZEx6R2c9PSIsIm1hYyI6IjAxYjcwZjc1MTVkZmZmNTQ0ZTRjYzY4YWFhZTQwZmUyNzFiYmFhMmE2ZDI1NzEyYTI1MDliZjZjMjYwZGY0NTkiLCJ0YWciOiIifQ%3D%3D; comento-access-token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczovL2NvbWVudG8ua3IvbG9naW4va2FrYW8vY2FsbGJhY2siLCJpYXQiOjE3NzMyMDEyMzQsImV4cCI6MTc3MzIwNDgzNCwibmJmIjoxNzczMjAxMjM0LCJqdGkiOiJnc3A0eXJlSVRyUTNVd1ZWIiwic3ViIjoiMjIxNzE1OSIsInBydiI6IjI2ZDMwMjhlMTliMTU2OWNiOThmZjg1MjQwMzM2MzllZDhlNzk2ZjAifQ.wUrNp0X4h17Ztg9jNms3_r4XVDcPFdfEC5NFgLrdCvI; comento-refresh-token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczovL2NvbWVudG8ua3IvbG9naW4va2FrYW8vY2FsbGJhY2siLCJpYXQiOjE3NzMyMDEyMzQsImV4cCI6MTc3MzIwNDgzNCwibmJmIjoxNzczMjAxMjM0LCJqdGkiOiJnc3A0eXJlSVRyUTNVd1ZWIiwic3ViIjoiMjIxNzE1OSIsInBydiI6IjI2ZDMwMjhlMTliMTU2OWNiOThmZjg1MjQwMzM2MzllZDhlNzk2ZjAifQ.wUrNp0X4h17Ztg9jNms3_r4XVDcPFdfEC5NFgLrdCvI; ab.storage.deviceId.fbb7aafd-61dc-46b3-9ca2-30d28e7105d5=g%3A4afebbb1-03f8-c32a-f28e-c58c5f384752%7Ce%3Aundefined%7Cc%3A1773201200858%7Cl%3A1773201239710; ab.storage.userId.fbb7aafd-61dc-46b3-9ca2-30d28e7105d5=g%3A2217159%7Ce%3Aundefined%7Cc%3A1773201239706%7Cl%3A1773201239710; of.cookiesSupported=true; _hackle_did_V944yZFr69DcMD8twgPk2KrG9R2w2yZf=7bff8520-b439-446a-ac0d-10f12a5cada4; _hackle_session_id_69DcMD8twgPk2KrG9R2w2yZf=1773201240137.515cd8d1; ofs=%7B%22v%22%3A%22x7jecuaw8n7beloyqka6k%22%2C%22s%22%3A%22na%22%2C%22t%22%3A1773201240652%7D; of.firstVisit=%7B%22u%22%3A%22https%3A%2F%2Fcomento.kr%2Fjob-questions%22%2C%22r%22%3A%22https%3A%2F%2Fkauth.kakao.com%2F%22%2C%22t%22%3A1773201240653%7D; of.lastPageviews=%5B%7B%22u%22%3A%22https%3A%2F%2Fcomento.kr%2Fjob-questions%22%2C%22r%22%3A%22https%3A%2F%2Fkauth.kakao.com%2F%22%2C%22t%22%3A1773201240653%7D%5D; of.humanVerified=true; of.humanVerified.event=%22mousemove%22; wcs_bt=s_397071b78da7:1773201358; ab.storage.sessionId.fbb7aafd-61dc-46b3-9ca2-30d28e7105d5=g%3A954920a1-69d6-4214-a222-b2a3965ecebc%7Ce%3A1773203158789%7Cc%3A1773201239708%7Cl%3A1773201358789; mp_322ce6a55eade32fabe82c4fdd8bd32e_mixpanel=%7B%22distinct_id%22%3A2217159%2C%22%24device_id%22%3A%22a8228af8-28d6-467f-8bf4-cb6000ca91e4%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fkauth.kakao.com%2F%22%2C%22%24initial_referring_domain%22%3A%22kauth.kakao.com%22%2C%22%24user_id%22%3A2217159%7D; _ga_XFSX9Z4LJS=GS2.1.s1773201200$o1$g1$t1773202056$j60$l0$h0; comento_new_session=eyJpdiI6IkRvNm5UV29oSW16Ung3ZVRmbEYvWXc9PSIsInZhbHVlIjoicnV4RWNnS0pLRHBHa2E5OXd4UFBXWC96bVU5VWkwSFp0c2hzUG05bTRmYlJhZDY2NjI1RDF5ZTI0ZDMrV1daRzlvc2wrS0dFOGhDMkd0WW5WeUU0Si9tR21QMnowME84ZG5kZEVXWlUya3R2cmdHWjJXdlI2ZWIyMjAxVzFBd1QiLCJtYWMiOiI0M2M0ZDVkMWEzNzc2ZjFiMjRlYmZhOWIyYjUwNTFlNDcxNmZhZmY4ZWNhZjlmODkwNjExYzRjMjJmYTFkZWUxIiwidGFnIjoiIn0%3D; _clsk=g4cje4%5E1773202059486%5E12%5E1%5Eq.clarity.ms%2Fcollect; _hackle_last_event_ts_69DcMD8twgPk2KrG9R2w2yZf=1773202061992; _dd_s=rum=2&id=f0422a06-e73b-490c-8c57-ea72cd2c2883&created=1773201200233&expire=1773202964036&logs=1"""  # 여기에 브라우저에서 복사한 cookie 문자열 넣기


# =========================
# 고정값
# =========================
URL = "https://comento.kr/api/case-list/question-list"

params = {
    "page": PAGE,
    "perPage": PER_PAGE,
    "job": JOB,
}

headers = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "baggage": "sentry-environment=production,sentry-release=ElySQ7EtANxbMVRTJ0cnV,sentry-public_key=97365f23b2d9992b6367167cf3fd8914,sentry-trace_id=b32d929674294754a32e966f88b80187,sentry-sample_rate=0.1,sentry-sampled=true",
    "cache-control": "no-cache",
    "cookie": COOKIE_STRING,  # 여기에 쿠키 문자열 넣기
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://comento.kr/job-questions?feed=recent",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sentry-trace": "b32d929674294754a32e966f88b80187-99a412aa18fc034c-1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

# 쿠키를 직접 넣고 싶으면 여기서 추가
if COOKIE_STRING.strip():
    headers["cookie"] = COOKIE_STRING.strip()


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

        # 콘솔 출력
        print(json.dumps(data, ensure_ascii=False, indent=2))

        # 파일 저장
        with open("comento_question_list.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("저장 완료: comento_question_list.json")

    except requests.exceptions.RequestException as e:
        print("요청 실패:", e)
        if getattr(e, "response", None) is not None:
            print("응답 본문:", e.response.text)
    except ValueError as e:
        print("JSON 파싱 실패:", e)
        print("응답 본문:", response.text)


if __name__ == "__main__":
    main()