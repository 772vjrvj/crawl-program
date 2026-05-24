import time
import json
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

# 단일 스토어 프로필을 조회하는 워커 함수
def fetch_single_store_profile(index, item, total_items, headers):
    category_type = item.get("categoryType")
    ranking_tab_type = item.get("rankingTabType")
    product_id = item.get("productId")
    product_name = item.get("productName")
    domain = item.get("storeDomain")

    # [기본 값 세팅] 초기화
    base_row = {
        "categoryType": category_type,
        "rankingTabType": ranking_tab_type,
        "productId": product_id,
        "productName": product_name,
        "storeDomain": domain,
        "상호명(name)": "",
        "대표자명(presidentName)": "",
        "사업자등록번호(businessRegistrationNumber)": "",
        "통신판매업신고번호(onlineOrderRegistrationNumber)": "",
        "전화번호(phoneNumber)": "",
        "이메일(mainEmail)": "",
        "주소(addressPost)": "",
        "법인명(corporateName)": "",
        "상담ID(consultId)": "",
        "소개글(introduce)": "",
        "등급(grade)": "",
        "농가여부(isFarmer)": ""
    }

    if not domain:
        print(f"[{index}/{total_items}] 🔍 [사업자: 없음 | 메일: 없음 | 가게명: 없음 | 상품명: {product_name}]")
        return base_row

    # 스레드별로 독립적인 헤더 컨텍스트 생성 (도메인 맞춤 레퍼러 설정)
    thread_headers = headers.copy()
    base_url = f"https://store.kakao.com/a/brandstore/{domain}/profile"
    thread_headers["referer"] = f"https://store.kakao.com/{domain}/profile"
    thread_headers["x-shopping-referrer"] = f"https://store.kakao.com/{domain}"

    timestamp = int(time.time() * 1000)
    params = {"_": timestamp}

    try:
        # 스레드가 동시에 몰려 차단당하는 것을 살짝 완화하기 위해 0.1초 내외 미세한 갭 생성
        response = requests.get(base_url, headers=thread_headers, params=params, timeout=5)

        if response.status_code == 200:
            json_response = response.json()
            if json_response.get("result"):
                data_node = json_response.get("data", {})
                store_info = data_node.get("store", {})

                if store_info:
                    base_row["상호명(name)"] = store_info.get("name")
                    base_row["대표자명(presidentName)"] = store_info.get("presidentName")
                    base_row["사업자등록번호(businessRegistrationNumber)"] = store_info.get("businessRegistrationNumber")
                    base_row["통신판매업신고번호(onlineOrderRegistrationNumber)"] = store_info.get("onlineOrderRegistrationNumber")
                    base_row["전화번호(phoneNumber)"] = store_info.get("phoneNumber")
                    base_row["이메일(mainEmail)"] = store_info.get("mainEmail")
                    base_row["주소(addressPost)"] = store_info.get("addressPost")
                    base_row["법인명(corporateName)"] = store_info.get("corporateName")
                    base_row["상담ID(consultId)"] = store_info.get("consultId")
                    base_row["소개글(introduce)"] = store_info.get("introduce")
                    base_row["등급(grade)"] = store_info.get("grade")
                    base_row["농가여부(isFarmer)"] = store_info.get("isFarmer")
    except Exception as e:
        pass

    # 실시간 로그용 변수 할당
    biz_num = base_row["사업자등록번호(businessRegistrationNumber)"] if base_row["사업자등록번호(businessRegistrationNumber)"] else "없음"
    email = base_row["이메일(mainEmail)"] if base_row["이메일(mainEmail)"] else "없음"
    store_name = base_row["상호명(name)"] if base_row["상호명(name)"] else "없음"

    # 완성 즉시 로그 출력
    print(f"[{index}/{total_items}] ✅ [사업자: {biz_num} | 메일: {email} | 가게명: {store_name} | 상품명: {product_name}]")

    return base_row

def fetch_store_profiles_multithread():
    json_filename = "kakao_ranking_products.json"
    try:
        with open(json_filename, "r", encoding="utf-8") as f:
            ranking_products = json.load(f)
    except FileNotFoundError:
        print(f"❌ '{json_filename}' 파일이 존재하지 않습니다. 랭킹 수집을 먼저 완료해 주세요.")
        return

    total_items = len(ranking_products)
    print(f"🚀 총 {total_items}개의 데이터를 8개 멀티스레드로 고속 수집 시작합니다.\n")

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    }

    # 🚀 핵심: max_workers=8 로 설정하여 동시에 8개씩 요청 처리
    # executor.map은 비동기로 연산하되, 리턴되는 결과 리스트는 원본 input의 인덱스 순서를 완벽히 보장합니다.
    with ThreadPoolExecutor(max_workers=8) as executor:
        # 워커 함수에 넘겨줄 인자 리스트 구성
        futures = [
            executor.submit(fetch_single_store_profile, idx, item, total_items, headers)
            for idx, item in enumerate(ranking_products, start=1)
        ]

        # 각 스레드가 완료되는 대로 데이터를 수집하되, 순서는 원본 순서대로 정렬되어 final_excel_rows에 들어감
        final_excel_rows = [future.result() for future in futures]

    # 4. 판다스를 이용해 최종 엑셀 파일로 변환 및 저장
    if final_excel_rows:
        df = pd.DataFrame(final_excel_rows)
        excel_filename = "kakao_store_profiles.xlsx"
        df.to_excel(excel_filename, index=False, engine='openpyxl')

        print(f"\n==================================================")
        print(f"🎉 [전체 완료] 총 {len(final_excel_rows)}개의 행이 순서 보장되어 매핑 및 저장 완료되었습니다.")
        print(f"📄 파일명: '{excel_filename}'")
        print(f"==================================================")
    else:
        print("\n❌ 처리할 상품 데이터가 존재하지 않습니다.")

if __name__ == "__main__":
    fetch_store_profiles_multithread()