import json
import random
import re
import time
import sys
import urllib3
import requests
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# SSL 인증서 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 기본 설정
# =========================================================
BASE_URL = "https://www.foodsafetykorea.go.kr"
DETAIL_URL = f"{BASE_URL}/potalPopup/fooddanger/bsnInfoDetail.do"
INPUT_JSON = "foodsafety_bsn_list.json"

# 글로벌 변수
COOKIE = ""
CALL_PAGE = ""
USE_RANDOM_SLEEP = True

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def save_json(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def clean_text(value):
    if value is None: return ""
    text = value.get_text(" ", strip=True) if hasattr(value, "get_text") else str(value)
    return re.sub(r"\s+", " ", text).strip()

def find_table_by_caption(soup, caption_name):
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption and caption_name in clean_text(caption): return table
    return None

def parse_info_table(table):
    result = {}
    if not table: return result
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        key = ""
        for cell in cells:
            text = clean_text(cell)
            if not text: continue
            if cell.name.lower() == "th": key = text
            elif cell.name.lower() == "td" and key:
                result[key] = text
                key = ""
    return result

def parse_list_table(table, caption_name):
    result = []
    if not table: return result
    headers = [clean_text(th) for th in table.find_all("th") if clean_text(th)]
    tbody = table.find("tbody")
    if not (headers and tbody): return result
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds: continue
        row = {header: clean_text(tds[idx]) if idx < len(tds) else "" for idx, header in enumerate(headers)}
        if caption_name == "제조품목 정보":
            a_tag = tr.find("a")
            if a_tag:
                match = re.search(r"'([^']+)'", a_tag.get("onclick", ""))
                if match: row["제품상세키"] = match.group(1)
        if any(str(v).strip() for v in row.values()): result.append(row)
    return result

def parse_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")
    return {
        "인허가 정보": parse_info_table(find_table_by_caption(soup, "인허가 정보")),
        "HACCP 인증 정보": parse_list_table(find_table_by_caption(soup, "HACCP 인증 정보"), "HACCP 인증 정보"),
        "인허가 변경사항정보": parse_list_table(find_table_by_caption(soup, "인허가 변경사항정보"), "인허가 변경사항정보"),
        "행정처분 정보": parse_list_table(find_table_by_caption(soup, "행정처분 정보"), "행정처분 정보"),
        "제조품목 정보": parse_list_table(find_table_by_caption(soup, "제조품목 정보"), "제조품목 정보"),
        "HACCP 인증 여부": "Y" if find_table_by_caption(soup, "HACCP 인증 정보") else "N",
    }

def fetch_detail_html(session, detail_key):
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "cookie": COOKIE,
        "referer": BASE_URL,
        "x-requested-with": "XMLHttpRequest"
    }
    params = {"bsnLcnsLedgNo": detail_key, "callPage": CALL_PAGE}
    res = session.get(DETAIL_URL, headers=headers, params=params, verify=False, timeout=20)
    return res.content.decode("utf-8", errors="ignore")

def main():
    global COOKIE, CALL_PAGE, USE_RANDOM_SLEEP

    print("="*60)
    print("   [식품안전나라 상세 수집기 - 게임방 Direct IP 버전]")
    print("="*60)

    # 1. 수집 필수 정보 입력
    COOKIE = input("1. 전체 COOKIE 입력: ").strip()
    CALL_PAGE = input("2. CALL_PAGE 값 입력: ").strip()

    # 랜덤 휴식 Y/N 입력 로직
    sleep_input = input("3. 랜덤 휴식(1.5초~3.5초)을 사용하시겠습니까? (Y/N, 기본Y): ").strip().upper()
    if sleep_input == "N":
        USE_RANDOM_SLEEP = False
        print(" > [경고] 휴식 없이 진행합니다. 차단 위험이 있습니다.")
    else:
        USE_RANDOM_SLEEP = True
        print(" > [설정] 랜덤 휴식을 활성화합니다.")

    # 2. 수집 범위 설정
    print("\n--- 수집 범위 설정 ---")
    start_idx = int(input("시작 인덱스 (0부터): ") or 0)
    end_idx = int(input("끝 인덱스 (예: 1000): ") or 7200)

    output_filename = f"detail_{start_idx}_{end_idx}.json"

    # 3. 실행
    if not Path(INPUT_JSON).exists():
        print(f"오류: {INPUT_JSON} 파일이 없습니다!"); input(); return

    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    targets = data[start_idx:end_idx]

    session = requests.Session()
    done_count = 0

    print(f"\n[알림] {output_filename} 수집 시작 (대상: {len(targets)}건)")

    try:
        for i, row in enumerate(targets):
            try:
                html = fetch_detail_html(session, row['상세키'])
                detail = parse_detail_html(html)
                row.update(detail)

                targets[i] = row
                done_count += 1

                # 5건마다 실시간 중간 저장
                if done_count % 5 == 0:
                    save_json(targets, output_filename)

                log(f"[{i+start_idx+1}/{len(data)}] {row['업체명']} 완료")

                # 휴식 여부에 따른 타임슬립
                if USE_RANDOM_SLEEP:
                    time.sleep(random.uniform(1.5, 3.5))

            except Exception as e:
                log(f"실패 ({row.get('업체명')}): {e}")
                continue

    except KeyboardInterrupt:
        print("\n중단됨. 현재까지 데이터 저장 중...")

    save_json(targets, output_filename)
    print(f"\n작업 완료! 파일명: {output_filename}")
    input("종료하려면 엔터를 누르세요...")

if __name__ == "__main__":
    main()