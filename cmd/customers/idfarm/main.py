import requests
import urllib3
from bs4 import BeautifulSoup
import pandas as pd

# SSL 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://idfarm.co.kr/ItemMarket/all/3?trx_type=SELL"

# 요청하신 헤더 정보 적용
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://idfarm.co.kr/ItemMarket/all/3?trx_type=BUY"
    # ※ 실제 사이트 조회를 위해 피들러에서 확인한 본인의 "Cookie": "..." 값을 여기에 꼭 추가해 주세요.
}

# verify=False 옵션을 추가하여 SSL 에러 우회
response = requests.get(url, headers=headers, verify=False)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')

    # --- 최상위 게임명 추출 ---
    game_title_elem = soup.select_one('h2.content__title span')
    game_name = game_title_elem.get_text(strip=True) if game_title_elem else "알 수 없음"

    # 아이템 목록 파싱
    items = soup.select('ul.market-item-row.trade_mode.desktop-item-list')
    excel_data_list = []

    for item in items:
        # 0. ID 및 URL
        item_id = item.get('data-item-id', '')
        item_url = f"https://idfarm.co.kr/ItemMarket/gameItem/{item_id}" if item_id else ""

        # 1. 계정 종류 (google, phone) 및 등급 배지(aria-label) 추출
        account_types = []
        logo_areas = item.select('.logo-area-wrap .logo-area')

        for logo in logo_areas:
            classes = logo.get('class', [])
            for c in classes:
                if c != 'logo-area':
                    account_types.append(c)

        # svg 태그의 aria-label(예: bronze) 찾아 추가하기
        svg_elem = item.select_one('.logo-area i svg')
        if svg_elem and svg_elem.get('aria-label'):
            account_types.append(svg_elem.get('aria-label'))

        # "미표기" 글자 사용 안 함. 값이 없으면 빈 문자열("") 처리
        account_type_str = ", ".join(account_types) if account_types else ""

        # 2. 제목
        title_elem = item.select_one('.item-content-wrapper .one-line-trunc')
        title = title_elem.get_text(strip=True) if title_elem else ""

        # 3. 메타정보 (서버, 직업, 거래유형)
        meta_info = item.select_one('.item-meta-info')
        server = ""
        job = ""
        trade_type = ""

        if meta_info:
            game_servers = meta_info.select('.game-server')
            if len(game_servers) >= 1:
                server = game_servers[0].get_text(strip=True)
            if len(game_servers) >= 2:
                trade_type = game_servers[1].get_text(strip=True)

            career_elem = meta_info.select_one('.career')
            if career_elem:
                job = career_elem.get_text(strip=True)

        # 4. 가격
        price_elem = item.select_one('.price-date-container .price--minimum.sale-price')
        price = price_elem.get_text(strip=True).replace('\xa0', '') if price_elem else ""

        # 5. 등록시간 (주석 처리됨)
        # date_elem = item.select_one('.uploaded-date')
        # upload_time = date_elem.get_text(strip=True) if date_elem else ""

        # 엑셀의 1줄(Row)이 될 딕셔너리 생성 (게임명 추가, 등록시간 제외)
        row_data = {
            "게임명": game_name,
            "게시글 ID": item_id,
            "계정종류": account_type_str,  # 구글/폰, 브론즈 등이 여기에 들어감
            "제목": title,
            "서버": server,
            "직업": job,
            "거래유형": trade_type,
            "가격": price,
            # "등록시간": upload_time,
            "URL": item_url
        }

        excel_data_list.append(row_data)

    # --- Pandas를 이용해 엑셀로 저장 ---
    df = pd.DataFrame(excel_data_list)
    file_name = "idfarm_items.xlsx"
    df.to_excel(file_name, index=False, engine='openpyxl')

    print(f"총 {len(excel_data_list)}개의 데이터가 '{file_name}' 파일로 성공적으로 저장되었습니다!")

else:
    print(f"요청 실패! 상태 코드: {response.status_code}")