import time
import json
import requests

def fetch_ranking_data():
    base_url = "https://store.kakao.com/a/f-s/ranking/product-sale-ranking"

    categories = [
        "BEAUTY", "FASHION", "FOOD", "SPORT",
        "LIFE", "ELECTRONIC", "INTERIOR", "CHILD"
    ]

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://store.kakao.com/home/best?__ld__=&oldRef=https:%2F%2Fwww.google.com%2F&tab=contProduct&groupId=6&period=HOURLY",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-shopping-referrer": "https://store.kakao.com/home/best?__ld__=&oldRef=https:%2F%2Fwww.google.com%2F&tab=contProduct&groupId=4&period=HOURLY",
        "x-shopping-tab-id": "e9449e8384498f7f6c8b8a",
        "cookie": "_kadu=rieSDBhKCyjpOJzVvoqCn0dLpChb_1778803663; _pmt=9NKhfGMwcq; __T_=1; __T_SECURE=1; _kau=4ca2a71e38fabebaf5b403dbe46f5c4e01a4a077116768499cff4a4dafea510bc7e004cc91e426b6ada983c6661313397919c1cf4a21ffeac3ce61f70efec0ef50e71aea5ee93e5aaf91f9d70b9256b2d8499311910315bb76a5a4f209781f296bad9bc43319201d093d9ff4ab0e040dcb903eac5aa8a3dc67de633638313738343035363634383537313437373036333332333632383232373838dc2306875196e9c6c5de4f3a93ebfc4b; _kawlt=dTp25-rHUkN4myqzaJp5y5ZtB5i9brz9foiIh1SSHQ7vKI8ENvaBXlbjbwMgrdS3_F_CtxDqFY8mluRtOwFGKDrGmYM2DZ7zOgoySWzBQzmHzCTRH8qMnn-Pi5La01Sq; _kawltea=1779259080; _karmt=AyR_hFrSiRWmFb4sEKLbCAFX3qzfte_YJ5XZF9Jlb9fTwbt-5DiBqNCu7NLpUOjR; _karmtea=1779269880; _kahai=fb568bc443058027b719a49ec3b108ae34b410a02832a33b4cf4724f2a7bbe74; _kc_ua_si_=9c66c7d4dd7cbca027e02776e2baf1c0e8d6ac4a624ccb72b43d9bd154a8dcf894a99db26e314ee3aed97066e285ac4a6419e3f9e1902; _T_ANO=AhK6wz1u+KYzMGTfF5R3YnMyWjvQ1QiH39PwpvoUQ3Lkv08/2+XrItII0sPLvy62kiXVQTCLVdNrj2tB5+z9ZpNYOBwS5/FR8s/7IifDe6t3z2HHg2YpnuY7ZxPFnw75BzVCs5kVgUfGB4GjZito43Ihyc2V00hLOe+s1N9G6CkOQP9ViKTCj6JPXHQULM4c6548Je4idnIC3OC1gxbwFgVvYFcabQNYaLgVI/uwN+ukh1rSo7lNamPceUCGbQMPVgl95DGTtKD399HcHxRnui5uqL0zR2n21/VmhWnIRoFfeZuHkx2RVNYqluQEgMd8WzybMtwq8L9rHTgrBKa3WQ=="
    }

    result_data = []

    for category in categories:
        page = 0
        previous_page_id_list = []

        print(f"\n==================================================")
        print(f">> [{category}] 카테고리 수집 시작 (최대 100개 제한)")
        print(f"==================================================")

        while True:
            # size=20 기준 page=5가 되는 순간 101개째 요청이므로 루프를 즉시 종료합니다.
            if page >= 5:
                print(f"  -> ⏹️ [목표 달성] 100개 수집을 완료하여 카테고리를 전환합니다.")
                break

            timestamp = int(time.time() * 1000)

            params = {
                "page": page,
                "rankingTabType": "contProduct",
                "categoryType": category,
                "periodType": "HOURLY",
                "size": 20,
                "displayPlaceType": "RANKING_TAB",
                "_": timestamp
            }

            try:
                response = requests.get(base_url, headers=headers, params=params)

                if response.status_code != 200:
                    print(f"[{category} | P.{page}] ❌ 에러 발생 (HTTP 상태 코드: {response.status_code})")
                    break

                json_response = response.json()

                if not json_response.get("result"):
                    print(f"[{category} | P.{page}] ⚠️ API 응답 'result'가 false입니다.")
                    break

                data_node = json_response.get("data", {})
                products = data_node.get("products", [])
                is_last = data_node.get("last", False)
                current_count = len(products)

                print(f"[{category} | P.{page}] 응답 상품 수: {current_count}개 | last 여부: {is_last}")

                # 1. 데이터가 완전히 없는 경우 종료
                if current_count == 0:
                    print(f"  -> ⏹️ [종료] 상품 데이터가 없습니다.")
                    break

                # 현재 페이지 상품 고유 ID 추출
                current_page_id_list = [prod.get("productId") for prod in products if prod.get("productId")]

                # 2. 직전 데이터랑 완전히 동일할 경우 종료 (100개 미만에서 끝나는 카테고리 대비 방어 코드)
                if current_page_id_list == previous_page_id_list:
                    print(f"  -> ⏹️ [종료] 데이터가 직전 페이지와 중복됩니다.")
                    break

                previous_page_id_list = current_page_id_list

                # 가공 후 결과 저장
                for prod in products:
                    parsed_item = {
                        "categoryType": category,
                        "rankingTabType": "contProduct",
                        "productId": prod.get("productId"),
                        "productName": prod.get("productName"),
                        "storeDomain": prod.get("storeDomain")  # storeDomain 항목 추가 수집
                    }
                    result_data.append(parsed_item)

                # 3. API가 마지막 페이지라고 주는 경우 종료
                if is_last is True:
                    print(f"  -> ⏹️ [종료] API 응답에서 last=true 임을 확인했습니다.")
                    break

                page += 1
                time.sleep(0.4)

            except Exception as e:
                print(f"[{category} | P.{page}] 💥 예외 오류 발생: {e}")
                break

    output_filename = "kakao_ranking_products.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=4)

    print(f"\n==================================================")
    print(f"🎉 [전체 완료] 총 {len(result_data)}개의 데이터가 '{output_filename}'에 저장되었습니다.")
    print(f"==================================================")

if __name__ == "__main__":
    fetch_ranking_data()