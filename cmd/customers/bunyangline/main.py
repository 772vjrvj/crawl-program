import time
import requests
import pandas as pd

# 1. 지역 코드 및 명칭 매핑
REGIONS = {
    "1": "서울", "2": "경기남부", "16": "경기북부", "3": "인천",
    "10": "부산", "14": "울산", "11": "대구", "6": "경상도",
    "13": "대전", "15": "세종", "4": "충청도", "12": "광주",
    "5": "전라도", "7": "강원도", "8": "제주도"
}

# 2. 광고/공고 타입 매핑 (ENG -> KOR)
TYPE_MAPPING = {
    "uniques": "유니크",
    "superiors": "슈페리어",
    "allTopsPremium": "프리미엄",
    "allTopsBasic": "전국탑",
    "localTops": "지역탑",
    "imageUps": "이미지업",
    "lineAds": "라인광고",
    "recruits": "채용공고",
    "partnerBanners": "파트너 배너",
    "supportersBanners": "서포터즈 배너"
}

# 원본 헤더 설정 (Fiddler 추출 원본 그대로 유지)
base_headers = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "content-type": "application/x-www-form-urlencoded",
    "cookie": "PHPSESSID=0n6egeqg9t2rr4v9pkn4tjcpjl; MF_CLIENT_SESSION=MF1779071027-6a0a7833664b7; cartSession=7c5651b9091c291085fea366184b6758; _ga=GA1.1.456761267.1779071030; _ga_PS8XKWW70Y=GS2.1.s1779096599$o2$g1$t1779099130$j60$l0$h0",
    "host": "www.bunyangline.com",
    "origin": "https://www.bunyangline.com",
    "pragma": "no-cache",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}

def main():
    # 최종 데이터를 담을 리스트
    all_extracted_data = []

    total_count = len(REGIONS)
    current_count = 0

    print("=== 크롤링 시작 (단일 쓰레드 순차 안정 모드) ===")
    print("-" * 60)

    # 전국 지역 순회 (1개씩 차례대로 진행)
    for region_id, region_name in REGIONS.items():
        current_count += 1
        url = f"https://www.bunyangline.com/recruit/list/{region_id}"

        print(f"\n=== [{current_count}/{total_count}] {region_name} 크롤링 시작 ===")

        # 헤더의 Referer 수정
        headers = base_headers.copy()
        headers["referer"] = url

        # 페이징 및 커서 초기화
        current_page = 1
        total_page = 1
        html_last_date_title = ""
        region_scraped_count = 0  # 해당 지역에서 몇 건 수집했는지 체크용

        while current_page <= total_page:
            print(f" -> {region_name} - {current_page}/{total_page} 페이지 요청 중... (Cursor: {html_last_date_title})", flush=True)

            # POST 페이로드 구성
            payload = {
                "page": current_page,
                "html": "Y",
                "htmlLastDateTitle": html_last_date_title
            }

            try:
                response = requests.post(url, headers=headers, data=payload, timeout=10)

                if response.status_code != 200:
                    print(f" [오류] {response.status_code} 상태 코드가 반환되었습니다. 건너뜁니다.", flush=True)
                    break

                res_json = response.json()
                extra = res_json.get("extra", {})

                # 1. 데이터 추출 (각 광고 타입별 순회)
                for eng_type, kor_type in TYPE_MAPPING.items():
                    items = extra.get(eng_type, [])

                    # 데이터가 리스트 형태로 존재하는 경우에만 파싱
                    if isinstance(items, list):
                        for item in items:
                            extracted_item = {
                                "user_id": item.get("user_id"),
                                "charge_name": item.get("charge_name"),
                                "charge_mphone": item.get("charge_mphone"),
                                "created_at": item.get("created_at"),
                                "type_eng": eng_type,
                                "type_kor": kor_type,
                                "local": region_name
                            }
                            all_extracted_data.append(extracted_item)
                            region_scraped_count += 1

                # 2. 다음 페이지 처리를 위한 페이징 정보 갱신 (커서 방식 반영)
                pagination = extra.get("pagination", {})
                total_page = int(pagination.get("totalPage", 1))
                html_last_date_title = extra.get("htmlLastDateTitle", "")

                # 페이지 증가
                current_page += 1

                # 과도한 요청 방지를 위한 딜레이
                # time.sleep(0.5)

            except Exception as e:
                print(f" [에러 발생]: {e}", flush=True)
                break

        print(f"[{current_count}/{total_count}] 완료: {region_name} (이번 회차 수집: {region_scraped_count}건)", flush=True)
        print("-" * 40)

    print("\n" + "=" * 60)
    print("=== 모든 지역 크롤링 완료 ===")
    print(f"총 수집된 전체 데이터 수: {len(all_extracted_data)}건")

    # 3. 데이터 저장 (Pandas 활용)
    if all_extracted_data:
        df = pd.DataFrame(all_extracted_data)

        # 컬럼 순서 고정
        columns_order = ["user_id", "charge_name", "charge_mphone", "created_at", "type_eng", "type_kor", "local"]
        df = df[columns_order]

        # 엑셀 파일로 저장
        output_filename = "bunyang_recruit_data.xlsx"
        df.to_excel(output_filename, index=False)
        print(f"성공적으로 '{output_filename}' 파일에 저장되었습니다.", flush=True)
    else:
        print("수집된 데이터가 없어 파일 저장을 진행하지 않습니다.", flush=True)

if __name__ == "__main__":
    main()