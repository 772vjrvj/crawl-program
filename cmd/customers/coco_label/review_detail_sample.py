import requests
import json
from bs4 import BeautifulSoup

# 1. 설정 정보
# 실제 브라우저에서 복사한 전체 쿠키 문자열을 아래에 넣으세요.
COOKIE_STR = f"""al=KR; _fwb=153Fgpdb68AF6wtU0X73tQL.1774768427504; _fbp=fb.1.1774768429368.806216781255867927; __fs_imweb=%7B%22deviceId%22%3A%22mnbfcju9-0430ae7c4b36b520ae04b4544cb4be37-454gbpp%22%2C%22useSubDomain%22%3A%22Y%22%7D; FB_EXTERNAL_ID=u202410216715ffa21a17f20260409882fc8765d717; SITE_STAT_SID=2026040969d71f16c45242.55477841; _clck=1r1oz16%5E2%5Eg52%5E0%5E2279; IMWEB_REFRESH_TOKEN=aca453e2-e571-4348-8453-84973102bde3; IMWEBVSSID=8f0iic6e7uoa0168v57padorkm5g5791cvj9st7af7p00pjb0v5812970i8n4vnnvbkq14q2h0tqeupko5iclebj9orit8jjgpivg00; ISDID=69d79344636a9; ilc=%2BptAWpJ8GLxIVCY4yyewr0sI3mA2nt6gsm4mOiTKFXA%3D; _imweb_login_state=Y; SITE_SHOP_PROD_VIEW_SID_m20250520321529559de2f_s2025042494f157a278922=2026040969d7946a8ef428.99158791; SITE_SHOP_PROD_VIEW_SID_m20250520321529559de2f_s20241126dc640ab30f1c8=2026040969d7946fda9f48.13150095; SITE_SHOP_PROD_VIEW_SID_m20250520321529559de2f_s202411264e9ba557d95d4=2026040969d7a13e585474.63435079; _dd_s=aid=a4e0643f-4dfa-4b70-ad58-a8b3d777aa9d&rum=2&id=090e1d54-79c0-4615-bc55-dd67bba97bc4&created=1775739387350&expire=1775740666071; mp_a4939111ea54962dbf95fe89a992eab3_mixpanel=%7B%22distinct_id%22%3A%22%22%2C%22%24device_id%22%3A%22920327e0-74a9-4609-90f6-77825e72978e%22%2C%22from_imweb_office%22%3Afalse%2C%22%24initial_referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fbackpg%2Flogin.cm%3Fback_url%3DaHR0cHM6Ly9jb2NvLWxhYmVsLmNvbS9hZG1pbg%253D%253D%22%2C%22%24initial_referring_domain%22%3A%22coco-label.com%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%7D; _clsk=1v5lde%5E1775746210614%5E1%5E1%5Eq.clarity.ms%2Fcollect; __bs_imweb=%7B%22deviceId%22%3A%22019d387118fb7a158d09c8b1123c61b0%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202410211a92d560f8f0e%22%2C%22unitCode%22%3A%22u202410216715ffa21a17f%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019d72b9b8d8748aba40446777acbe57%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3NDYyNjQsImV4cCI6MTc3NTc0Njg2NH0.q5zbOQhTDn7EeD-jLOqXOZ_mWcYpWI8rAPLk-yVnQ3c%22%2C%22referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fadmin%2Fshopping%2Freview%2F%3Fq%3DJTdCJTIyZGF0YSUyMjolN0IlMjJyZXZpZXdfY29tbWVudCUyMjolMjIlMjIsJTIycmV2aWV3X3JhdGluZyUyMjolMjIlMjIsJTIycmV2aWV3X3R5cGUlMjI6JTIyJTIyLCUyMm9yZGVyX3R5cGUlMjI6JTIyJTIyLCUyMnN0YXJ0X3RpbWUlMjI6JTIyJTIyLCUyMmVuZF90aW1lJTIyOiUyMiUyMiwlMjJyZXZpZXdfbGV2ZWwlMjI6JTIyJTIyLCUyMnJldmlld19uaWNrJTIyOiUyMiUyMiwlMjJyZXZpZXdfcHJvZF9udW0lMjI6JTIyJTIyLCUyMnJldmlld19wcm9kX25hbWUlMjI6JTIyJTIyLCUyMmJyYW5kJTIyOiUyMiUyMiwlMjJrZXl3b3JkJTIyOiUyMiUyMiwlMjJwYWdlc2l6ZSUyMjolMjIxMDAlMjIlN0QsJTIydHlwZSUyMjolMjJzZWFyY2glMjIlN0Q%253D%26page%3D1%22%2C%22initialReferrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fadmin%2Fshopping%2Freview%2F%3Fq%3DJTdCJTIyZGF0YSUyMjolN0IlMjJyZXZpZXdfY29tbWVudCUyMjolMjIlMjIsJTIycmV2aWV3X3JhdGluZyUyMjolMjIlMjIsJTIycmV2aWV3X3R5cGUlMjI6JTIyJTIyLCUyMm9yZGVyX3R5cGUlMjI6JTIyJTIyLCUyMnN0YXJ0X3RpbWUlMjI6JTIyJTIyLCUyMmVuZF90aW1lJTIyOiUyMiUyMiwlMjJyZXZpZXdfbGV2ZWwlMjI6JTIyJTIyLCUyMnJldmlld19uaWNrJTIyOiUyMiUyMiwlMjJyZXZpZXdfcHJvZF9udW0lMjI6JTIyJTIyLCUyMnJldmlld19wcm9kX25hbWUlMjI6JTIyJTIyLCUyMmJyYW5kJTIyOiUyMiUyMiwlMjJrZXl3b3JkJTIyOiUyMiUyMiwlMjJwYWdlc2l6ZSUyMjolMjIxMDAlMjIlN0QsJTIydHlwZSUyMjolMjJzZWFyY2glMjIlN0Q%253D%26page%3D1%22%2C%22initialReferrerDomain%22%3A%22coco-label.com%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-04-09T14%3A51%3A07.362Z%22%2C%22commonSessionId%22%3A%22sc_019d72b9b8db758db352a6e908f85e44%22%2C%22commonSessionUpdatedAt%22%3A%222026-04-09T14%3A51%3A07.363Z%22%2C%22customSessionId%22%3A%22cs_019d72b9b8dc7f36b2a8965c2e7391f1%22%2C%22customSessionUpdatedAt%22%3A%222026-04-09T14%3A51%3A07.364Z%22%2C%22browser_session_id%22%3A%22019d72b9b8d8748aba40446777acbe57%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNTA1MjAzMjE1Mjk1NTlkZTJmIiwic2l0ZUNvZGUiOiJTMjAyNDEwMjExYTkyZDU2MGY4ZjBlIiwidW5pdENvZGUiOiJ1MjAyNDEwMjE2NzE1ZmZhMjFhMTdmIiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzU3NDYyNjQsImV4cCI6MTc3NTc0Njg2NH0.q5zbOQhTDn7EeD-jLOqXOZ_mWcYpWI8rAPLk-yVnQ3c%22%2C%22initial_referrer%22%3A%22https%3A%2F%2Fcoco-label.com%2Fadmin%2Fshopping%2Freview%2F%3Fq%3DJTdCJTIyZGF0YSUyMjolN0IlMjJyZXZpZXdfY29tbWVudCUyMjolMjIlMjIsJTIycmV2aWV3X3JhdGluZyUyMjolMjIlMjIsJTIycmV2aWV3X3R5cGUlMjI6JTIyJTIyLCUyMm9yZGVyX3R5cGUlMjI6JTIyJTIyLCUyMnN0YXJ0X3RpbWUlMjI6JTIyJTIyLCUyMmVuZF90aW1lJTIyOiUyMiUyMiwlMjJyZXZpZXdfbGV2ZWwlMjI6JTIyJTIyLCUyMnJldmlld19uaWNrJTIyOiUyMiUyMiwlMjJyZXZpZXdfcHJvZF9udW0lMjI6JTIyJTIyLCUyMnJldmlld19wcm9kX25hbWUlMjI6JTIyJTIyLCUyMmJyYW5kJTIyOiUyMiUyMiwlMjJrZXl3b3JkJTIyOiUyMiUyMiwlMjJwYWdlc2l6ZSUyMjolMjIxMDAlMjIlN0QsJTIydHlwZSUyMjolMjJzZWFyY2glMjIlN0Q%253D%26page%3D1%22%2C%22initial_referrer_domain%22%3A%22coco-label.com%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-04-09T14%3A51%3A07.362Z%22%2C%22common_session_id%22%3A%22sc_019d72b9b8db758db352a6e908f85e44%22%2C%22common_session_updated_at%22%3A%222026-04-09T14%3A51%3A07.355Z%22%2C%22custom_session_id%22%3A%22cs_019d72b9b8dc7f36b2a8965c2e7391f1%22%2C%22custom_session_updated_at%22%3A%222026-04-09T14%3A51%3A07.356Z%22%7D; SITE_SHOP_PROD_VIEW_SID_m20250520321529559de2f_s20241126c0eb3979bd4a5=2026040969d7bcdad2cff7.74622611; IMWEB_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJob3N0IjoiY29jby1sYWJlbC5jb20iLCJzaXRlQ29kZSI6IlMyMDI0MTAyMTFhOTJkNTYwZjhmMGUiLCJ1bml0Q29kZSI6InUyMDI0MTAyMTY3MTVmZmEyMWExN2YiLCJtZW1iZXJDb2RlIjoibTIwMjUwNTIwMzIxNTI5NTU5ZGUyZiIsInJvbGUiOiJvd25lciIsImlhdCI6MTc3NTc0NjI2NiwiZXhwIjoxNzc1NzQ2NTY2LCJpc3MiOiJpbXdlYi1jb3JlLWF1dGgtc2l0ZSJ9.LZc5plID8QS1kVjFy046QxPhJgyEpF85JHQE-avdKbk; alarm_cnt_member=2898; _rp_c_27f200f1d1c7ceb32be5ade900359469ad35f66c=1"""

target_idx = "118652630"  # 테스트용 리뷰 번호
url = "https://coco-label.com/admin/ajax/shop/admin_review_detail_view.cm"

# 2. 헤더 설정 (제공해주신 요청 정보 기반)
headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://coco-label.com",
    "Referer": "https://coco-label.com/admin/shopping/review/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": COOKIE_STR
}

# 3. POST 데이터 (Body)
payload = {
    "idx": target_idx,
    "review_page": "1"
}

try:
    # 4. 요청 보내기
    print(f"리뷰 ID {target_idx} 데이터 요청 중...")
    response = requests.post(url, headers=headers, data=payload)

    if response.status_code == 200:
        res_json = response.json()

        if "html" in res_json:
            # 5. HTML 추출 및 Prettify
            raw_html = res_json["html"]
            soup = BeautifulSoup(raw_html, 'html.parser')
            pretty_html = soup.prettify()

            print("\n" + "="*60)
            print(f"리뷰 ID [{target_idx}] 상세 응답 결과 (정렬됨)")
            print("="*60 + "\n")
            print(pretty_html)

            # 파일로 저장해서 확인하고 싶을 때
            with open(f"debug_review_{target_idx}.html", "w", encoding="utf-8") as f:
                f.write(pretty_html)
            print(f"\n[성공] 'debug_review_{target_idx}.html' 파일이 생성되었습니다.")

        else:
            print("[오류] 응답 JSON에 'html' 키가 없습니다.")
            print("응답 내용:", res_json)
    else:
        print(f"[오류] HTTP 상태 코드: {response.status_code}")
        print("서버 응답:", response.text)

except Exception as e:
    print(f"[예외 발생] {e}")