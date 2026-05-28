import requests
import pandas as pd
import time

def main():
    # API 엔드포인트
    search_url = "https://wapi.bibf.net/api/v1/search/simple/exhibitor"
    info_url = "https://wapi.bibf.net/api/v1/exhibitor/info"

    # 요청 헤더 (이전 요청에서 파악한 최신 헤더 적용)
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
        "priority": "u=1, i",
        "referer": "https://www.bibf.net/",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "version": "100001"
    }

    # 사용자 세션 및 인증 쿠키 적용
    cookies = {
        "Hm_lpvt_e23d4ac494167c713a7147f5af01d850": "1779964666",
        "Hm_lvt_e23d4ac494167c713a7147f5af01d850": "1779963907",
        "HMACCOUNT": "E38541DC594A52D1",
        "JSESSIONID": "5FFD69032B4F977293BE6711AAB9247A"
    }

    page_no = 1
    page_size = 30
    exhibitor_ids = []
    previous_ids = []

    print("1. 전시업체 ID 수집 시작...")

    # [Step 1] ID 리스트 수집 반복문
    while True:
        # form-urlencoded 형식에 맞게 payload 작성
        payload = {
            "pageNo": page_no,
            "pageSize": page_size,
            "filterRegion": "",
            "filterParentExhibitor": ""
        }

        try:
            # json=payload 대신 data=payload 사용 (content-type 설정과 맞춤), cookies 파라미터 추가
            response = requests.post(f"{search_url}?_t={time.time()}", data=payload, headers=headers, cookies=cookies)
            response.raise_for_status()
            data = response.json()

            # 응답 코드가 정상이 아니거나 데이터가 없으면 중단
            if data.get("code") != 0 or not data.get("data") or not data["data"].get("documents"):
                print(f"서버 응답 오류 혹은 데이터 없음. (페이지 {page_no}) 응답 메시지: {data.get('message')}")
                break

            documents = data["data"]["documents"]

            # id만 추출
            current_ids = [doc.get("id") for doc in documents if doc.get("id")]

            # 데이터가 비어있거나, 이전 데이터(배열)와 완전히 동일하면 중단
            if not current_ids or current_ids == previous_ids:
                print(f"{page_no}페이지에서 데이터가 없거나 이전 페이지와 동일합니다. ID 수집 중단.")
                break

            exhibitor_ids.extend(current_ids)
            previous_ids = current_ids

            print(f"{page_no}페이지 완료 (현재 누적 ID: {len(exhibitor_ids)}개)")

            page_no += 1
            time.sleep(0.5)  # 서버 부하 및 차단 방지

        except Exception as e:
            print(f"ID 수집 중 에러 발생 (페이지 {page_no}): {e}")
            break

    # 순서를 유지하며 중복 ID 제거
    exhibitor_ids = list(dict.fromkeys(exhibitor_ids))
    print(f"\n총 {len(exhibitor_ids)}개의 고유 전시업체 ID 수집 완료.")
    print("--------------------------------------------------")

    if not exhibitor_ids:
        print("수집된 ID가 없어 프로그램을 종료합니다.")
        return

    print("2. 상세 정보 수집 시작...")

    all_exhibitor_data = []

    # [Step 2] 배열을 돌면서 상세 정보 수집
    for i, ex_id in enumerate(exhibitor_ids):
        params = {
            "sourceId": ex_id,
            "_t": time.time()
        }

        try:
            # 상세 정보 요청에도 쿠키와 헤더 포함
            response = requests.get(info_url, params=params, headers=headers, cookies=cookies)
            response.raise_for_status()
            info_data = response.json()

            if info_data.get("code") == 0 and info_data.get("data"):
                detail = info_data["data"]

                # 요청하신 추가 컬럼 매핑
                detail["Type of Business"] = detail.get("industryText", "")
                detail["Country/Region"] = detail.get("country", "")
                detail["Publication category"] = detail.get("publishText", "")
                detail["Website"] = detail.get("website", "")
                detail["Titles"] = detail.get("contentCount", "")
                detail["Contact Person"] = detail.get("contactPerson", "")
                detail["Email"] = detail.get("email", "")

                # Booth Number (stands가 배열로 오므로 문자열로 변환)
                stands = detail.get("stands", [])
                if isinstance(stands, list):
                    detail["Booth Number"] = ", ".join(stands)
                else:
                    detail["Booth Number"] = stands

                all_exhibitor_data.append(detail)

            # 진행 상황 출력 (10개마다 출력하여 너무 많은 로그가 쌓이지 않도록 조절)
            if (i + 1) % 10 == 0 or (i + 1) == len(exhibitor_ids):
                print(f"상세 정보 수집 진행 중... ({i + 1}/{len(exhibitor_ids)})")

            time.sleep(0.5)  # 서버 부하 방지용 딜레이

        except Exception as e:
            print(f"상세 정보 수집 중 에러 발생 (ID {ex_id}): {e}")
            continue

    print("--------------------------------------------------")
    print("3. 엑셀 파일 생성 중...")

    # [Step 3] 모은 데이터를 엑셀로 추출
    if all_exhibitor_data:
        df = pd.DataFrame(all_exhibitor_data)

        # 요청하신 컬럼을 맨 앞으로 오도록 재배치
        requested_cols = [
            "Type of Business", "Country/Region", "Publication category",
            "Website", "Titles", "Contact Person", "Email", "Booth Number"
        ]

        # 원래 있는 데이터(나머지 컬럼들)도 유실되지 않게 뒤에 배치
        other_cols = [col for col in df.columns if col not in requested_cols]
        df = df[requested_cols + other_cols]

        excel_filename = "bibf_exhibitors_full_data.xlsx"

        # 엑셀 파일로 저장
        with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Exhibitors')

        print(f"완료! 모든 데이터가 '{excel_filename}' 파일에 저장되었습니다.")
    else:
        print("수집된 상세 데이터가 없어서 엑셀 파일을 생성하지 못했습니다.")

if __name__ == "__main__":
    main()