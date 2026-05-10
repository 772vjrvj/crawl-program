import json
import random
import re
import time
import urllib3
import requests
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# SSL 인증서 경고 메시지 숨기기 (프록시 사용 시 필수)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 1. 수집된 세션 정보 및 브라이트 데이터 설정
# =========================================================
# 직접 추출하신 정보를 여기에 넣습니다.
COOKIE = "elevisor_for_j2ee_uid=4pb5v04ahv19w; JSESSIONID=Q1aT7EcjyLyOQaiN8yRSs5plMoZ7LSLK15utvBnodmZbZ1JwTGHmy5Fd5XyV2Ifa.amV1c19kb21haW4veGNvd2FzMDFfSVBPMDE=; GPKISecureWebSession=qhBg91Jipp2Bn0IRMwxo; callPage=5659260513687476"
CALL_PAGE = "5659260513687476"

# 브라이트 데이터 정보
BRD_USER = "brd-customer-hl_7b5686a6-zone-foodsafetykorea-country-kr"
BRD_PASS = "5iw55h83jmjv"
# 연결 안정성을 위해 22225 포트 사용
BRD_PROXY_URL = f"http://{BRD_USER}:{BRD_PASS}@brd.superproxy.io:22225"

PROXIES = {
    "http": BRD_PROXY_URL,
    "https": BRD_PROXY_URL
}

# =========================================================
# 파일 및 수집 설정
# =========================================================
BASE_URL = "https://www.foodsafetykorea.go.kr"
DETAIL_URL = f"{BASE_URL}/potalPopup/fooddanger/bsnInfoDetail.do"

INPUT_JSON = "foodsafety_bsn_list.json"
OUTPUT_JSON = "foodsafety_bsn_detail.json"
FAILED_JSON = "foodsafety_bsn_detail_failed.json"

MAX_COUNT = None
SKIP_DONE = True
SHUFFLE_REQUEST_ORDER = False

# 딜레이 설정
MIN_DELAY_SEC = 1.0
MAX_DELAY_SEC = 3.0
LONG_SLEEP_EVERY = 50
LONG_SLEEP_MIN_SEC = 10
LONG_SLEEP_MAX_SEC = 20
VERY_LONG_SLEEP_EVERY = 100
VERY_LONG_SLEEP_MIN_SEC = 180
VERY_LONG_SLEEP_MAX_SEC = 300

MAX_RETRY = 3
SAVE_DEBUG_HTML = True
DEBUG_HTML_DIR = "debug_detail_html"

# =========================================================
# 공통 유틸리티
# =========================================================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{now()}] {msg}")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save_json(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def random_sleep():
    sec = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
    log(f"대기 {sec:.2f}초")
    time.sleep(sec)

def long_sleep_if_needed(done_count):
    if done_count > 0:
        if done_count % VERY_LONG_SLEEP_EVERY == 0:
            sec = random.uniform(VERY_LONG_SLEEP_MIN_SEC, VERY_LONG_SLEEP_MAX_SEC)
            log(f"매우 긴 휴식(IP차단 방지) {sec:.2f}초 / 처리건수={done_count}")
            time.sleep(sec)
        elif done_count % LONG_SLEEP_EVERY == 0:
            sec = random.uniform(LONG_SLEEP_MIN_SEC, LONG_SLEEP_MAX_SEC)
            log(f"긴 휴식 {sec:.2f}초 / 처리건수={done_count}")
            time.sleep(sec)

def save_debug_html(row_no, html):
    if not SAVE_DEBUG_HTML: return
    debug_dir = Path(DEBUG_HTML_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)
    file_path = debug_dir / f"debug_detail_{row_no}.html"
    file_path.write_text(html, encoding="utf-8")

# =========================================================
# 데이터 요청 및 파싱
# =========================================================
def make_headers():
    headers = {
        "accept": "text/html, */*; q=0.01",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "connection": "keep-alive",
        "referer": f"{BASE_URL}/portal/specialinfo/searchInfoCompany.do?menu_grp=MENU_NEW04&menu_no=2813",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": COOKIE
    }
    return headers

def fetch_detail_html(session, detail_key, row_no, company_name):
    params = {"bsnLcnsLedgNo": detail_key, "callPage": CALL_PAGE}

    for retry in range(1, MAX_RETRY + 1):
        try:
            log(f"[상세요청] 번호={row_no} 업체명={company_name} retry={retry}/{MAX_RETRY}")

            res = session.get(
                DETAIL_URL,
                headers=make_headers(),
                params=params,
                proxies=PROXIES, # 프록시 적용
                verify=False,    # 인증서 무시 필수
                timeout=40
            )

            if res.status_code != 200:
                log(f"[상세오류] status={res.status_code}")
                res.raise_for_status()

            html = res.content.decode("utf-8", errors="ignore")
            save_debug_html(row_no, html)
            return html

        except Exception as e:
            log(f"[상세실패] 번호={row_no} error={e}")
            if retry >= MAX_RETRY: raise
            time.sleep(random.uniform(5, 10) * retry)
    return ""

def clean_text(value):
    if value is None: return ""
    text = value.get_text(" ", strip=True) if hasattr(value, "get_text") else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*-\s*", "-", text)

def find_table_by_caption(soup, caption_name):
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption and caption_name in clean_text(caption):
            return table
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
        if any(str(v).strip() for v in row.values()):
            result.append(row)
    return result

def parse_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")
    return {
        "인허가 정보": parse_info_table(find_table_by_caption(soup, "인허가 정보")),
        "HACCP 인증 정보": parse_list_table(find_table_by_caption(soup, "HACCP 인증 정보"), "HACCP 인증 정보"),
        "인허가 변경사항정보": parse_list_table(find_table_by_caption(soup, "인허가 변경사항정보"), "인허가 변경사항정보"),
        "행정처분 정보": parse_list_table(find_table_by_caption(soup, "행정처분 정보"), "행정처분 정보"),
        "제조품목 정보": parse_list_table(find_table_by_caption(soup, "제조품목 정보"), "제조품목 정보"),
        "HACCP 인증 여부": "Y" if find_table_by_caption(soup, "HACCP 인증 정보") and parse_list_table(find_table_by_caption(soup, "HACCP 인증 정보"), "HACCP 인증 정보") else "N",
    }

# =========================================================
# 메인 로직
# =========================================================
def has_detail(row):
    permit_info = row.get("인허가 정보")
    return bool(permit_info and isinstance(permit_info, dict) and permit_info.get("업체명"))

def collect_detail():
    output_path = Path(OUTPUT_JSON)
    data = read_json(OUTPUT_JSON) if output_path.exists() else read_json(INPUT_JSON)
    results = deepcopy(data)
    failed = []

    targets = [i for i, r in enumerate(results) if r.get("상세키") and not (SKIP_DONE and has_detail(r))]
    if SHUFFLE_REQUEST_ORDER: random.shuffle(targets)
    if MAX_COUNT: targets = targets[:MAX_COUNT]

    log("=" * 60)
    log(f"수집 시작 - 대상 건수: {len(targets)}")
    log("=" * 60)

    session = requests.Session()
    done_count = 0

    for order_no, idx in enumerate(targets, start=1):
        row = results[idx]
        try:
            html = fetch_detail_html(session, row['상세키'], row['번호'], row['업체명'])
            detail_data = parse_detail_html(html)

            row.update(detail_data)
            results[idx] = row
            done_count += 1

            save_json(results, OUTPUT_JSON)
            log(f"[저장완료] {order_no}/{len(targets)} - {row['업체명']}")

        except Exception as e:
            log(f"[최종실패] {row['업체명']} - {e}")
            failed.append({"번호": row['번호'], "업체명": row['업체명'], "error": str(e)})
            save_json(failed, FAILED_JSON)

        random_sleep()
        long_sleep_if_needed(done_count)

    log("=" * 60)
    log(f"수집 종료 - 성공: {done_count}, 실패: {len(failed)}")
    log("=" * 60)

if __name__ == "__main__":
    collect_detail()