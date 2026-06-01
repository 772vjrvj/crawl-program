import requests
import pandas as pd
import time
import re
import logging
import urllib3
import random
import os     # 🌟 추가: 파일 존재 여부 확인용
import json   # 🌟 추가: JSON 중간 저장 및 불러오기용

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

ILLEGAL_CHARACTERS_RE = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]')

def clean_text(val):
    if isinstance(val, str):
        return ILLEGAL_CHARACTERS_RE.sub('', val)
    return val

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "deviceid": "",
    "i18n": "en",
    "origin": "https://www.bibf.net",
    "platform": "pc",
    "pragma": "no-cache",
    "referer": "https://www.bibf.net/",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "token": "6a1d54b9f64a843e716258ea", # 🚨 필수: 요청 권한 토큰 (만료 시 갱신 필요)
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "version": "100001",
}

# 🚨 [주의] 잦은 재시작 시 쿠키가 만료될 수 있으니 주기적으로 확인하세요.
cookies = {
    "Hm_lpvt_e23d4ac494167c713a7147f5af01d850": "1780307149",
    "Hm_lvt_e23d4ac494167c713a7147f5af01d850": "1780132615,1780298791",
    "HMACCOUNT": "A7EDB3E51F603BF3",
    "HMACCOUNT_BFESS": "A7EDB3E51F603BF3"
}

info_url = "https://wapi.bibf.net/api/v1/exhibitor/info"
JSON_FILENAME = "bibf_exhibitors.json"  # 중간 저장 파일명 고정

def fetch_detail(ex_id):
    """1개씩 순차적으로 실행될 상세 정보 수집 함수 (최대 3회 재시도)"""
    params = {"sourceId": ex_id, "_t": time.time()}
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = requests.get(info_url, params=params, headers=headers, cookies=cookies, timeout=10, verify=False)

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
                    logging.warning(f"[API 응답 데이터 없음] ID {ex_id} - 서버 메시지: {info_data.get('msg', '알 수 없음')}")
            else:
                logging.warning(f"[서버 차단 의심] Status Code: {response.status_code} - 응답 내용: {response.text[:150]}")

        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"[상세 데이터 수집 실패] ID {ex_id} 오류 발생: {e} - {attempt + 1}/{max_retries - 1}회 재시도 중...")
                time.sleep(2)
            else:
                logging.error(f"❌ [상세 데이터 수집 최종 실패] ID {ex_id} 오류 발생 (3회 모두 실패): {e}")

    return None

def main():
    search_url = "https://wapi.bibf.net/api/v1/search/simple/exhibitor"

    page_no = 1
    page_size = 5000
    exhibitor_ids = []
    previous_ids = []

    TARGET_COUNT = 5000

    logging.info("==================================================")
    logging.info(f"🚀 [STEP 1] 전시업체 목록(ID) 수집 시작 (page_size={page_size})")
    logging.info("==================================================")

    while len(exhibitor_ids) < TARGET_COUNT:
        payload = {"pageNo": page_no, "pageSize": page_size, "filterRegion": "", "filterParentExhibitor": ""}
        try:
            response = requests.post(f"{search_url}?_t={time.time()}", data=payload, headers=headers, cookies=cookies, timeout=10, verify=False)

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
            time.sleep(1)

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
    logging.info(f"🚀 [STEP 2] 상세 정보 수집 (이어하기 및 자동저장 적용)")
    logging.info("==================================================")

    all_exhibitor_data = []

    # 🌟 수정: 기존에 저장된 JSON 파일이 있다면 읽어오기 (이어하기 로직)
    if os.path.exists(JSON_FILENAME):
        try:
            with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
                all_exhibitor_data = json.load(f)
            logging.info(f"🔄 [이어하기] 기존 데이터 발견! {len(all_exhibitor_data)}건의 데이터를 불러왔습니다.")
        except json.JSONDecodeError:
            logging.warning("⚠️ 기존 JSON 파일이 손상되었습니다. 덮어쓰고 새로 시작합니다.")
            all_exhibitor_data = []

    # 이미 수집된 ID 리스트 추출
    processed_ids = set(item.get("ID") for item in all_exhibitor_data if item.get("ID"))

    # 중복을 제외하고 앞으로 수집해야 할 ID만 필터링
    remaining_ids = [ex_id for ex_id in exhibitor_ids if ex_id not in processed_ids]

    total_count = len(remaining_ids)

    if total_count == 0:
        logging.info("✅ 모든 ID의 수집이 이미 완료되어 있습니다.")
    else:
        logging.info(f"🚀 총 {len(exhibitor_ids)}개 중 남은 {total_count}개 수집을 시작(재개)합니다...")

    # 남은 데이터만 순차적으로 수집
    for i, ex_id in enumerate(remaining_ids):
        res = fetch_detail(ex_id)
        progress_percent = ((i + 1) / total_count) * 100

        if res:
            all_exhibitor_data.append(res)
            logging.info(f"⚡ [진행률] {i + 1}/{total_count} ({progress_percent:.2f}%) - 완료: {res.get('name', '이름 없음')} (ID: {ex_id}) (NAME: {res.get('name', '이름 없음')}) (EMAIL: {res.get('Email', 'EMAIL 없음')})")
        else:
            logging.warning(f"⚠️ [진행률] {i + 1}/{total_count} ({progress_percent:.2f}%) - 수집 실패 ID: {ex_id}")

        # 🌟 수정: 10건마다 JSON 파일에 현재까지의 모든 데이터를 중간 덮어쓰기 저장
        if (i + 1) % 10 == 0:
            with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(all_exhibitor_data, f, ensure_ascii=False, indent=4)
            logging.info(f"💾 [중간 저장] {len(all_exhibitor_data)}건 누적 저장 완료.")

        sleep_time = random.uniform(1.5, 3.5)
        time.sleep(sleep_time)

    # 🌟 추가: 루프 종료 직후, 10건 단위로 안 떨어지는 나머지 데이터 최종 반영을 위해 1회 더 저장
    if total_count > 0:
        with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(all_exhibitor_data, f, ensure_ascii=False, indent=4)

    logging.info(f"✅ [STEP 2 완료] 총 {len(all_exhibitor_data)}개의 상세 데이터 확보 성공!\n")

    logging.info("==================================================")
    logging.info("🚀 [STEP 3] 최종 엑셀(XLSX) 및 CSV 생성 중...")
    logging.info("==================================================")

    # 🌟 수정: 마지막에 한 번만 엑셀, CSV로 데이터 가공 및 저장
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

        logging.info("🎉 [전체 작업 완료] 모든 파일 (JSON, CSV, XLSX) 저장 성공!")
    else:
        logging.error("❌ 저장할 상세 데이터가 없습니다.")

if __name__ == "__main__":
    main()