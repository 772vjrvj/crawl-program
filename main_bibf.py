import requests
import pandas as pd
import time
import re
import logging

# 터미널에 시간과 함께 상세 로그를 찍기 위한 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# 엑셀/CSV 오류를 일으키는 불법 제어 문자 패턴 (제거용)
ILLEGAL_CHARACTERS_RE = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]')

def clean_text(val):
    if isinstance(val, str):
        return ILLEGAL_CHARACTERS_RE.sub('', val)
    return val

# [주의!] 브라우저에서 새로고침 후 최신 쿠키로 변경 필수!
headers = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "origin": "https://www.bibf.net",
    "referer": "https://www.bibf.net/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}

cookies = {
    "Hm_lpvt_e23d4ac494167c713a7147f5af01d850": "1779964666",
    "Hm_lvt_e23d4ac494167c713a7147f5af01d850": "1779963907",
    "HMACCOUNT": "E38541DC594A52D1",
    "JSESSIONID": "5FFD69032B4F977293BE6711AAB9247A" # 반드시 최신 쿠키로 갱신하세요!
}

info_url = "https://wapi.bibf.net/api/v1/exhibitor/info"

def fetch_detail(ex_id):
    """1개씩 순차적으로 실행될 상세 정보 수집 함수 (최대 3회 재시도)"""
    params = {"sourceId": ex_id, "_t": time.time()}
    max_retries = 3  # 최대 재시도 횟수

    for attempt in range(max_retries):
        try:
            response = requests.get(info_url, params=params, headers=headers, cookies=cookies, timeout=10)

            if response.status_code == 200:
                info_data = response.json()
                if info_data.get("code") == 0 and info_data.get("data"):
                    detail = info_data["data"]

                    for key, value in detail.items():
                        detail[key] = clean_text(value)

                    detail["ID"] = ex_id
                    detail["Type of Business"] = detail.get("industryText", "")
                    detail["Country/Region"] = detail.get("country", "")
                    detail["Publication category"] = detail.get("publishText", "")
                    detail["Website"] = detail.get("website", "")
                    detail["Titles"] = detail.get("contentCount", "")
                    detail["Contact Person"] = detail.get("contactPerson", "")
                    detail["Email"] = detail.get("email", "")

                    stands = detail.get("stands", [])
                    if isinstance(stands, list):
                        detail["Booth Number"] = ", ".join([clean_text(str(s)) for s in stands])
                    else:
                        detail["Booth Number"] = clean_text(str(stands))

                    return detail
            else:
                # 200이 아닌 응답 코드가 왔을 때도 재시도를 원한다면 여기서 예외를 발생시킬 수 있습니다.
                pass

        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"[상세 데이터 수집 실패] ID {ex_id} 오류 발생: {e} - {attempt + 1}/{max_retries - 1}회 재시도 중...")
                time.sleep(1)  # 재시도 전 1초 대기
            else:
                logging.error(f"❌ [상세 데이터 수집 최종 실패] ID {ex_id} 오류 발생 (3회 모두 실패): {e}")

    return None

def main():
    search_url = "https://wapi.bibf.net/api/v1/search/simple/exhibitor"

    page_no = 1
    page_size = 5000  # 한 번에 5000개 요청
    exhibitor_ids = []
    previous_ids = []

    TARGET_COUNT = 5000

    logging.info("==================================================")
    logging.info(f"🚀 [STEP 1] 전시업체 목록(ID) 수집 시작 (page_size={page_size})")
    logging.info("==================================================")

    while len(exhibitor_ids) < TARGET_COUNT:
        payload = {"pageNo": page_no, "pageSize": page_size, "filterRegion": "", "filterParentExhibitor": ""}
        try:
            logging.info(f"-> {page_no} 페이지 요청 중...")
            response = requests.post(f"{search_url}?_t={time.time()}", data=payload, headers=headers, cookies=cookies, timeout=10)

            if response.status_code != 200:
                logging.warning(f"서버 응답 오류 (Status Code: {response.status_code}). 반복을 종료합니다.")
                break

            data = response.json()
            if data.get("code") != 0 or not data.get("data") or not data["data"].get("documents"):
                break

            current_ids = [doc.get("id") for doc in data["data"]["documents"] if doc.get("id")]
            if not current_ids or current_ids == previous_ids:
                break

            exhibitor_ids.extend(current_ids)
            previous_ids = current_ids

            logging.info(f"   [완료] {len(current_ids)}개 ID 확보 완료 (현재 누적: {len(exhibitor_ids)}개)")
            page_no += 1
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"ID 수집 에러 (페이지 {page_no}): {e}")
            break

    exhibitor_ids = list(dict.fromkeys(exhibitor_ids))
    if len(exhibitor_ids) > TARGET_COUNT:
        exhibitor_ids = exhibitor_ids[:TARGET_COUNT]

    logging.info(f"✅ [STEP 1 완료] 총 {len(exhibitor_ids)}개 고유 ID 수집 완료.\n")

    if not exhibitor_ids:
        return

    logging.info("==================================================")
    logging.info(f"🚀 [STEP 2] {len(exhibitor_ids)}개 업체의 상세 정보 1개씩 순차 수집 시작...")
    logging.info("==================================================")

    all_exhibitor_data = []
    total_count = len(exhibitor_ids)

    # 1개씩 안전하게 수집
    for i, ex_id in enumerate(exhibitor_ids):
        res = fetch_detail(ex_id)
        if res:
            all_exhibitor_data.append(res)

        # [수정됨] 매 1건마다 무조건 로그 출력 + ID 포함
        progress_percent = ((i + 1) / total_count) * 100
        logging.info(f"⚡ [상세 진행률] {i + 1} / {total_count} 완료 ({progress_percent:.2f}%) - 완료된 ID: {ex_id}")
        logging.info(f"⚡ [상세 진행률] {i + 1} / {total_count} 완료 ({progress_percent:.2f}%) - 완료된 name: {res['name']}")

        # 서버 차단 방지 딜레이
        time.sleep(0.3)

    logging.info(f"✅ [STEP 2 완료] 총 {len(all_exhibitor_data)}개의 상세 데이터 확보 성공!\n")

    logging.info("==================================================")
    logging.info("🚀 [STEP 3] 데이터 파일 3종 생성 중...")
    logging.info("==================================================")

    if all_exhibitor_data:
        df = pd.DataFrame(all_exhibitor_data)

        requested_cols = [
            "ID", "Type of Business", "Country/Region", "Publication category",
            "Website", "Titles", "Contact Person", "Email", "Booth Number"
        ]
        other_cols = [col for col in df.columns if col not in requested_cols]
        df = df[requested_cols + other_cols]

        df.to_excel("bibf_exhibitors.xlsx", index=False, engine='openpyxl')
        df.to_csv("bibf_exhibitors.csv", index=False, encoding='utf-8-sig')
        df.to_json("bibf_exhibitors.json", force_ascii=False, orient='records', indent=4)

        logging.info("🎉 [전체 작업 완료] 파일 저장 성공!")
    else:
        logging.error("❌ 저장할 상세 데이터가 없습니다.")

if __name__ == "__main__":
    main()