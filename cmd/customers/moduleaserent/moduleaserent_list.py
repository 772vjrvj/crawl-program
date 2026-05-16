import requests
from bs4 import BeautifulSoup
import json
import time
from concurrent.futures import ThreadPoolExecutor

# 공통 설정
BASE_URL = "https://moduleaserent.com/"
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'cache-control': 'no-cache',
    'connection': 'keep-alive',
    'cookie': 'PHPSESSID=burhjno7f49i6oq1v5d2c425q0; page_count=10',
    'host': 'moduleaserent.com',
    'pragma': 'no-cache',
    'referer': 'https://moduleaserent.com/index.html?p_cate=1',
    'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
}

def fetch_category_data(cate_info):
    cate_id, cate_name = cate_info
    category_results = []
    page = 1
    prev_page_data = []

    print(f">>> [{cate_name}] 크롤링 쓰레드 시작")

    while True:
        params = {
            'page': page,
            'p_cate': cate_id,
            'p_cate2': '',
            'p_carnm': ''
        }

        try:
            # 로그: 현재 시도 중인 페이지 출력
            print(f"    [{cate_name}] {page}페이지 요청 중...")

            response = requests.get(f"{BASE_URL}index.html", headers=HEADERS, params=params, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            items = soup.select('li.grid-item')

            # 페이지에 데이터가 아예 없는 경우
            if not items:
                print(f" [!] [{cate_name}] {page}페이지에 데이터가 없어 종료합니다.")
                break

            current_page_data = []
            for item in items:
                name_tag = item.select_one('h3')
                product_name = name_tag.get_text(strip=True) if name_tag else "상품명 없음"

                link_tag = item.select_one('div.container.padding-15px-bottom a')
                full_url = BASE_URL + link_tag['href'] if link_tag and 'href' in link_tag.attrs else ""

                current_page_data.append({
                    "url": full_url,
                    "상품명": product_name,
                    "종류": cate_name
                })

            # 로그: 페이지 수집 완료 및 상품 수 출력
            print(f"    [*] [{cate_name}] {page}페이지 수집 완료: {len(current_page_data)}개 상품")

            # 종료 조건: 이전 페이지 데이터와 현재 페이지 데이터가 같으면 루프 탈출
            if current_page_data == prev_page_data:
                print(f" [!] [{cate_name}] {page}페이지가 이전 페이지와 중복되어 종료합니다.")
                break

            category_results.extend(current_page_data)
            prev_page_data = current_page_data
            page += 1

            # 멀티쓰레드 환경에서 사이트 부하를 줄이기 위한 미세 지연
            time.sleep(0.3)

        except Exception as e:
            print(f" [X] [{cate_name}] {page}페이지 에러 발생: {e}")
            break

    print(f" <<< [{cate_name}] 모든 수집 완료 (누적: {len(category_results)}건)")
    return category_results

def main():
    start_time = time.time()
    print("=" * 50)
    print(" 멀티쓰레드 크롤링을 시작합니다. (Threads: 8)")
    print("=" * 50)

    categories = [
        ("1", "국산차"),
        ("2", "수입차"),
        ("3", "배달 오토바이")
    ]

    total_data = []

    # 8개의 쓰레드 사용
    with ThreadPoolExecutor(max_workers=8) as executor:
        # 각 카테고리 작업을 병렬로 실행
        results = list(executor.map(fetch_category_data, categories))

        for res in results:
            total_data.extend(res)

    # JSON 저장
    with open('product_results_multi.json', 'w', encoding='utf-8') as f:
        json.dump(total_data, f, ensure_ascii=False, indent=4)

    end_time = time.time()
    print("=" * 50)
    print(f" 최종 결과 저장 완료: 'product_results_multi.json'")
    print(f" 총 수집 상품 수: {len(total_data)}개")
    print(f" 전체 소요 시간: {end_time - start_time:.2f}초")
    print("=" * 50)

if __name__ == "__main__":
    main()