import os
import json
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- [설정 구간] ---
JSON_FILE = "coco_reviews_1775743996.json"
# 실제 로컬 저장 베이스 경로
SAVE_BASE_PATH = "data/item/review"
# 브라우저에서 복사한 최신 쿠키
COOKIE_STR = 'al=KR; _fwb=153Fgpdb68AF6wtU0X73tQL.1774768427504; _fbp=fb.1.1774768429368.806216781255867927; __fs_imweb=%7B%22deviceId%22%3A%22mnbfcju9-0430ae7c4b36b520ae04b4544cb4be37-454gbpp%22%2C%22useSubDomain%22%3A%22Y%22%7D; FB_EXTERNAL_ID=u202410216715ffa21a17f20260409882fc8765d717; _clck=1r1oz16%5E2%5Eg52%5E0%5E2279; IMWEB_REFRESH_TOKEN=aca453e2-e571-4348-8453-84973102bde3; IMWEBVSSID=8f0iic6e7uoa0168v57padorkm5g5791cvj9st7af7p00pjb0v5812970i8n4vnnvbkq14q2h0tqeupko5iclebj9orit8jjgpivg00; ISDID=69d79344636a9; ilc=%2BptAWpJ8GLxIVCY4yyewr0sI3mA2nt6gsm4mOiTKFXA%3D; _imweb_login_state=Y; _dd_s=aid=a4e0643f-4dfa-4b70-ad58-a8b3d777aa9d&rum=2&id=090e1d54-79c0-4615-bc55-dd67bba97bc4&created=1775739387350&expire=1775740666071; mp_a4939111ea54962dbf95fe89a992eab3_mixpanel=%7B%22distinct_id%22%3A%22%22%2C%22%24device_id%22%3A%22920327e0-74a9-4609-90f6-77825e72978e%22%2C%22from_imweb_office%22%3Afalse%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fbackpg%2Flogin.cm%3Fback_url%3DaHR0cHM6Ly9jb2NvLWxhYmVsLmNvbS9hZG1pbg%253D%253D%22%2C%22%24initial_referring_domain%22%3A%22coco-label.com%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%7D; _rp_c_27f200f1d1c7ceb32be5ade900359469ad35f66c=1; _clsk=1v5lde%5E1775748215094%5E3%5E1%5Eq.clarity.ms%2Fcollect; alarm_cnt_member=2898; __bs_imweb=%7B%22deviceId%22%3A%22019d387118fb7a158d09c8b1123c61b0%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202410211a92d560f8f0e%22%2C%22unitCode%22%3A%22u202410216715ffa21a17f%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019d72d78ba67707834ee3b321a566fb%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3NDgyMzYsImV4cCI6MTc3NTc0ODgzNn0.2MCDvZXnbudLNt4TCkQmaO1rAUx4Mw235BcyiTl343M%22%2C%22referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2F459%22%2C%22initialReferrer%22%3A%22%40direct%22%2C%22initialReferrerDomain%22%3A%22%40direct%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-04-09T15%3A25%3A01.542Z%22%2C%22commonSessionId%22%3A%22sc_019d72d78ba97fd5961905190db5fa8e%22%2C%22commonSessionUpdatedAt%22%3A%222026-04-09T15%3A23%3A57.951Z%22%2C%22customSessionId%22%3A%22cs_019d72d78bac7c309e96e4bffdb68b56%22%2C%22customSessionUpdatedAt%22%3A%222026-04-09T15%3A23%3A57.952Z%22%2C%22browser_session_id%22%3A%22019d72d78ba67707834ee3b321a566fb%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3NDgyMzYsImV4cCI6MTc3NTc0ODgzNn0.2MCDvZXnbudLNt4TCkQmaO1rAUx4Mw235BcyiTl343M%22%2C%22initial_referrer%22%3A%22%40direct%22%2C%22initial_referrer_domain%22%3A%22%40direct%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-04-09T15%3A25%3A01.542Z%22%2C%22common_session_id%22%3A%22sc_019d72d78ba97fd5961905190db5fa8e%22%2C%22common_session_updated_at%22%3A%222026-04-09T15%3A23%3A57.951Z%22%2C%22custom_session_id%22%3A%22cs_019d72d78bac7c309e96e4bffdb68b56%22%2C%22custom_session_updated_at%22%3A%222026-04-09T15%3A23%3A57.952Z%22%7D'

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": COOKIE_STR,
    "Referer": "https://coco-label.com/admin/shopping/review/"
}

def process_single_review(review_info):
    """리뷰 하나에 대한 상세 호출, 이미지 다운로드, 매핑 수행"""
    rev_id = review_info.get("리뷰 번호")
    prod_id = review_info.get("상품번호")
    author = review_info.get("성함", "알 수 없음")
    orig_prod_name = review_info.get("상품명", "상품명 없음")
    is_confirm_val = "1" if review_info.get("확인") == "주문확인" else ""

    if not rev_id or not prod_id:
        return None

    try:
        url = "https://coco-label.com/admin/ajax/shop/admin_review_detail_view.cm"
        payload = {"idx": rev_id, "review_page": "1"}

        resp = requests.post(url, headers=HEADERS, data=payload, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "rev_id": rev_id, "author": author}

        res_json = resp.json()
        html = res_json.get("html", "")
        if not html:
            return {"error": "No HTML Content", "rev_id": rev_id, "author": author}

        soup = BeautifulSoup(html, 'html.parser')
        review_body = soup.find('div', class_='_review_body')

        # 이미지 처리 (이미지가 있을 때만 폴더 생성)
        img_tags = review_body.find_all('img') if review_body else []
        img_html_list = []
        folder_name = f"{prod_id}_{rev_id}"

        if img_tags:
            valid_imgs = [img.get('src') for img in img_tags if img.get('src')]
            if valid_imgs:
                # 1. 실제 로컬 저장 경로는 data/item/review/폴더명
                folder_path = os.path.join(SAVE_BASE_PATH, folder_name)
                os.makedirs(folder_path, exist_ok=True)

                for i, src_url in enumerate(valid_imgs, 1):
                    if src_url.startswith('/'): src_url = "https://coco-label.com" + src_url

                    new_file_name = f"{prod_id}_{rev_id}_{i:02d}.jpg"
                    save_path = os.path.join(folder_path, new_file_name)

                    try:
                        img_data = requests.get(src_url, timeout=10).content
                        with open(save_path, 'wb') as f:
                            f.write(img_data)

                        # 2. HTML 태그에는 data/item 제외하고 review/폴더명/파일명만 넣기
                        img_html_list.append(f'<img src="review/{folder_name}/{new_file_name}">')
                    except:
                        pass

        # 본문 텍스트 추출 (이미지 제거 후)
        if review_body:
            temp_body = BeautifulSoup(str(review_body), 'html.parser')
            for im in temp_body.find_all('img'):
                im.decompose()
            content_text = temp_body.get_text(separator="\n", strip=True)
        else:
            content_text = ""

        star_point = len(soup.select('.star-point .text-danger'))
        time_tag = soup.find('span', class_='write-summary', string=re.compile(r'\d{4}-\d{2}-\d{2}'))
        is_time = time_tag.get_text(strip=True) if time_tag else ""

        mapped = {
            "is_id": "",
            "it_id": prod_id,
            "mb_id": "",
            "is_name": author,
            "is_password": "",
            "is_score": star_point,
            "is_subject": orig_prod_name,
            "is_content": f"{content_text}\n<div>{''.join(img_html_list)}</div>",
            "is_time": is_time,
            "is_ip": "",
            "is_confirm": is_confirm_val,
            "is_reply_subject": "",
            "is_reply_content": "",
            "is_reply_name": ""
        }
        return mapped

    except Exception as e:
        return {"error": str(e), "rev_id": rev_id, "author": author}

def main():
    if not os.path.exists(JSON_FILE):
        print(f"❌ 파일을 찾을 수 없습니다: {JSON_FILE}")
        return

    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        review_list = json.load(f)

    total_count = len(review_list)
    completed_count = 0

    print(f"🚀 총 {total_count}개 리뷰 데이터 처리를 시작합니다.")
    print(f"📂 로컬 저장: {SAVE_BASE_PATH}")
    print(f"🔗 태그 경로: review/폴더명/파일명")
    print("="*75)

    final_results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_review = {executor.submit(process_single_review, rev): rev for rev in review_list}

        for future in as_completed(future_to_review):
            completed_count += 1
            result = future.result()
            progress = f"[{completed_count}/{total_count}]"

            if result and "error" not in result:
                final_results.append(result)
                print(f"{progress} ✅ 성공 | ID: {result['it_id']}_{future_to_review[future]['리뷰 번호']}")
                print(f"      작성자: {result['is_name']} | 이미지: {result['is_content'].count('<img')}장")
            else:
                err_msg = result.get('error') if result else "Unknown error"
                print(f"{progress} ❌ 실패 | ID: {result.get('rev_id') if result else '??'} | 사유: {err_msg}")

            print("-" * 75)

    if final_results:
        timestamp = int(time.time())
        excel_name = f"final_reviews_{timestamp}.xlsx"
        pd.DataFrame(final_results).to_excel(excel_name, index=False)
        print(f"\n🎉 작업 완료! 엑셀 파일: {excel_name}")
    else:
        print("⚠️ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    main()