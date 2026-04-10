from selenium import webdriver
from bs4 import BeautifulSoup
import re
import time
import json

# 1. 드라이버 실행
driver = webdriver.Chrome()

# 2. 초기 접속 (로그인을 위해)
driver.get("https://coco-label.com/admin/shopping/review/")

print("-" * 50)
print("1. 브라우저에서 로그인을 완료하세요.")
print("2. 크롤링을 시작할 검색 결과 페이지까지 이동하세요.")
print("3. 준비가 되면 이 곳(터미널)에서 'Enter'를 누르세요.")
print("-" * 50)
input("준비 완료 시 엔터 클릭...")

# 현재 접속된 URL 분석하여 베이스 URL 생성
current_url = driver.current_url
if 'page=' in current_url:
    base_url = re.sub(r'page=\d+', 'page=', current_url)
else:
    connector = '&' if '?' in current_url else '?'
    base_url = f"{current_url}{connector}page="

# 시작 페이지 번호 추출
try:
    page_match = re.search(r'page=(\d+)', current_url)
    current_page = int(page_match.group(1)) if page_match else 1
except:
    current_page = 1

all_reviews = []
last_page_review_ids = []

while True:
    target_url = f"{base_url}{current_page}"
    print(f"\n[페이지 접속] {target_url}")
    driver.get(target_url)
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    container = soup.find('ul', class_='list-comments check')

    if not container:
        print(f"[알림] {current_page}페이지 컨테이너 없음. 종료.")
        break

    items = container.find_all('li', recursive=False)
    if not items:
        break

    current_page_data = []
    current_page_review_ids = []

    # --- 여기서부터 항목별 실시간 로그 출력 ---
    for idx, item in enumerate(items, 1):
        try:
            # 리뷰 번호 추출
            review_id = ""
            review_detail_div = item.find('div', onclick=re.compile(r'viewAdminReviewDetail'))
            if review_detail_div:
                id_match = re.search(r"viewAdminReviewDetail\('(\d+)'", review_detail_div['onclick'])
                if id_match:
                    review_id = id_match.group(1)

            current_page_review_ids.append(review_id)

            # 상품 정보
            prod_link = item.find('a', href=re.compile(r'idx=\d+'))
            prod_name = prod_link.find('span').get_text(strip=True) if prod_link else "상품명 없음"
            prod_num = ""
            if prod_link:
                num_match = re.search(r'idx=(\d+)', prod_link['href'])
                prod_num = num_match.group(1) if num_match else ""

            # 주문확인 유무
            check_status = "주문확인" if item.find('a', string=re.compile("주문확인")) else ""

            # 작성자 성함
            author = ""
            author_tag = item.find('a', onclick=re.compile(r'openShopWriterInfo')) or item.find('a', class_='text-gray')
            if author_tag:
                author = author_tag.get_text(strip=True)

            # 로그 출력 (작성자 | 상품명)
            print(f"  ({idx}/{len(items)}) [ID:{review_id}] {author} | {prod_name[:20]}... | {check_status}")

            current_page_data.append({
                "현재 페이지": current_page,
                "리뷰 번호": review_id,
                "상품번호": prod_num,
                "성함": author,
                "상품명": prod_name,
                "확인": check_status
            })

        except Exception as e:
            print(f"  [에러] {idx}번째 파싱 실패: {e}")
            continue

    # 중복 검사 (마지막 페이지 무한 반복 방지)
    if current_page_review_ids == last_page_review_ids:
        print(f"\n[중단] {current_page}페이지 내용이 이전과 동일하여 수집을 종료합니다.")
        break

    all_reviews.extend(current_page_data)
    last_page_review_ids = current_page_review_ids

    print(f"-> {current_page}페이지 완료 (현재 누적: {len(all_reviews)}개)")
    current_page += 1

# 결과 저장
if all_reviews:
    file_name = f"coco_reviews_{int(time.time())}.json"
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(all_reviews, f, ensure_ascii=False, indent=4)
    print(f"\n최종 수집 완료: {len(all_reviews)}개 저장됨.")

driver.quit()