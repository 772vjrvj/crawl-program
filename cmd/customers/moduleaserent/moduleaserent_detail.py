import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import time
import threading
import re

# 전역 설정 및 데이터 보관소
BASE_URL = "https://moduleaserent.com/"
AJAX_URL = "https://moduleaserent.com/ajax/car.price.ajax.php"

progress_counter = 0
collected_data_dict = {}  # 번호를 키로 데이터를 모으는 전역 딕셔너리
counter_lock = threading.Lock()

HEADERS = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'cookie': 'PHPSESSID=burhjno7f49i6oq1v5d2c425q0; page_count=10',
    'origin': 'https://moduleaserent.com',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest'
}

def safe_int_format(value):
    try:
        if value is None or str(value).strip() in ["", "None", "0"]:
            return "0"
        num = int(str(value).replace(',', '').split('.')[0])
        return format(num, ',')
    except (ValueError, TypeError):
        return "0"

def get_detail_info(args):
    global progress_counter, collected_data_dict
    item, total_count = args
    results = []
    detail_url = item['url']

    try:
        res = requests.get(detail_url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # [1. 디폴트 정보 파싱] AJAX 실패 시 로그에 표시할 기본 정보
        try:
            d_type = soup.select_one('input[name="po_type"]:checked')['value'] if soup.select_one('input[name="po_type"]:checked') else "렌트"
            d_month = soup.select_one('input[name="po_months"]:checked')['value'] if soup.select_one('input[name="po_months"]:checked') else "36"
            d_ptype_node = soup.select_one('input[name="po_ptype"]:checked')
            d_ptype_label = soup.find('label', {'for': d_ptype_node['id']}).get_text(strip=True) if d_ptype_node else "선납금30%"
            d_mprice = safe_int_format(soup.select_one('#months_price').get_text(strip=True)) if soup.select_one('#months_price') else "0"
            d_tprice = safe_int_format(soup.select_one('#total_price').get_text(strip=True)) if soup.select_one('#total_price') else "0"

            default_key = f"{d_type}|{d_month}개월|{d_ptype_label}"
        except:
            default_key, d_mprice, d_tprice = None, "0", "0"

        # [2. po_parts 및 기본 정보 추출]
        title_spans = soup.select('div.text-extra-large30 span')
        po_parts = title_spans[2].get_text(strip=True) if len(title_spans) >= 3 else ""
        if not po_parts:
            h3_tag = soup.select_one('h3')
            po_parts = re.sub(r'^20\d{2}년형\s+', '', " ".join(h3_tag.get_text(separator=' ', strip=True).split())) if h3_tag else ""

        po_pidx = parse_qs(urlparse(detail_url).query).get('ItemCode', [''])[0]
        full_product_name = " ".join([span.get_text(strip=True) for span in title_spans]) if title_spans else item.get('상품명', '')

        # [3. 옵션 루프 및 AJAX 요청]
        types = [("렌트", "렌트"), ("리스", "리스")]
        months = ["36", "48", "60"]
        ptypes = [("A", "선납금30%"), ("B", "보증금30%"), ("C", "0%")]

        current_headers = HEADERS.copy()
        current_headers['referer'] = detail_url
        log_messages = []
        ajax_success_count = 0

        for t_val, t_name in types:
            for m_val in months:
                for p_val, p_name in ptypes:
                    current_key = f"{t_name}|{m_val}개월|{p_name}"

                    payload = {
                        'po_pidx': po_pidx, 'po_parts': po_parts,
                        'allSelectedValues[0][po_type]': t_val,
                        'allSelectedValues[1][po_months]': m_val,
                        'allSelectedValues[2][po_ptype]': p_val
                    }

                    m_formatted, t_formatted, is_ajax_ok = "0", "0", False
                    try:
                        ajax_res = requests.post(AJAX_URL, headers=current_headers, data=payload, timeout=7)
                        data = ajax_res.json()
                        if data.get('rst') == 'success' and data.get('mprice') and str(data.get('mprice')) != "0":
                            m_formatted = safe_int_format(data.get('mprice'))
                            t_formatted = safe_int_format(data.get('tprice'))
                            is_ajax_ok = True
                            ajax_success_count += 1
                    except: pass

                    # 로그 및 데이터 결정
                    if is_ajax_ok:
                        log_messages.append(f"      ✅ [성공] [{current_key}] -> {m_formatted}원")
                        results.append({
                            "상품[렌트/리스]": t_name, "상품명": full_product_name, "개월수": m_val + "개월",
                            "초기비용": p_name, "월 가격": m_formatted + "원", "총 가격": t_formatted + "원",
                            "특이사항": "", "종류": item['종류'], "URL": detail_url
                        })
                    elif current_key == default_key:
                        # AJAX는 실패했지만 화면 디폴트값인 경우
                        log_messages.append(f"      ✅ [성공(디폴트)] [{current_key}] -> {d_mprice}원")
                        results.append({
                            "상품[렌트/리스]": t_name, "상품명": full_product_name, "개월수": m_val + "개월",
                            "초기비용": p_name, "월 가격": d_mprice + "원", "총 가격": d_tprice + "원",
                            "특이사항": "디폴트값", "종류": item['종류'], "URL": detail_url
                        })
                    else:
                        log_messages.append(f"      ❌ [실패] [{current_key}] -> 0원")

        # [4. 결과 로그 출력 및 전역 변수 저장]
        with counter_lock:
            progress_counter += 1
            # 전역 딕셔너리에 작업물 저장 (번호를 키로 사용)
            collected_data_dict[progress_counter] = results

            print(f"[*] 처리완료: {progress_counter:4d}/{total_count} | 수집: {len(results):2d}건")
            print(f"    - 파츠명: [{po_parts}]")
            print(f"    - URL  : {detail_url}")
            for msg in log_messages: print(msg)
            print("-" * 85)

        return results

    except Exception as e:
        with counter_lock:
            progress_counter += 1
            print(f" [!] 에러: {detail_url} -> {e}")
        return []

def main():
    try:
        with open('product_results_multi.json', 'r', encoding='utf-8') as f:
            base_items = json.load(f)
    except: return

    total_count = len(base_items)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = list(executor.map(get_detail_info, [(it, total_count) for it in base_items]))
        final_results = [item for sublist in futures for item in sublist]

    if final_results:
        # 최종 결과 저장
        pd.DataFrame(final_results).to_excel('final_car_data_detail.xlsx', index=False)
        print(f"\n[종료] 총 {len(final_results)}건 수집 완료. 전역 변수에 {len(collected_data_dict)}개 상품군 저장됨.")

if __name__ == "__main__":
    main()