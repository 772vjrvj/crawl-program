import json
import re
import time
import urllib3
import requests
import sys
from pathlib import Path
from bs4 import BeautifulSoup

# SSL 인증서 경고 메시지 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 1. 고정 설정 (세션 및 프록시)
# =========================================================
COOKIE = "elevisor_for_j2ee_uid=4pb5v04ahv19w; JSESSIONID=Q1aT7EcjyLyOQaiN8yRSs5plMoZ7LSLK15utvBnodmZbZ1JwTGHmy5Fd5XyV2Ifa.amV1c19kb21haW4veGNvd2FzMDFfSVBPMDE=; GPKISecureWebSession=qhBg91Jipp2Bn0IRMwxo; callPage=5659260513687476"
CALL_PAGE = "5659260513687476"

BRD_USER = "brd-customer-hl_7b5686a6-zone-foodsafetykorea-country-kr"
BRD_PASS = "5iw55h83jmjv"
BRD_PROXY_URL = f"http://{BRD_USER}:{BRD_PASS}@brd.superproxy.io:22225"

PROXIES = {"http": BRD_PROXY_URL, "https": BRD_PROXY_URL}
BASE_URL = "https://www.foodsafetykorea.go.kr"
DETAIL_URL = f"{BASE_URL}/potalPopup/fooddanger/bsnInfoDetail.do"

INPUT_JSON = "foodsafety_bsn_list.json"
RAWDATA_DIR = Path("rawdata")
RAWDATA_DIR.mkdir(exist_ok=True)

# =========================================================
# 유틸리티 및 통신
# =========================================================
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save_json(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def make_headers():
    return {
        "accept": "text/html, */*; q=0.01",
        "referer": f"{BASE_URL}/portal/specialinfo/searchInfoCompany.do?menu_grp=MENU_NEW04&menu_no=2813",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": COOKIE
    }

def clean_text(value):
    if value is None: return ""
    text = value.get_text(" ", strip=True) if hasattr(value, "get_text") else str(value)
    return re.sub(r"\s+", " ", text).strip()

# =========================================================
# 파싱 로직
# =========================================================
def parse_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")

    def get_table(cap):
        for t in soup.find_all("table"):
            if t.find("caption") and cap in clean_text(t.find("caption")): return t
        return None

    def parse_info(table):
        res = {}
        if not table: return res
        for tr in table.find_all("tr"):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            for th, td in zip(ths, tds):
                res[clean_text(th)] = clean_text(td)
        return res

    def parse_list(table, is_prod=False):
        res = []
        if not table: return res
        headers = [clean_text(th) for th in table.find_all("th")]
        for tr in table.find("tbody").find_all("tr"):
            tds = tr.find_all("td")
            if not tds or "데이터가 없습니다" in clean_text(tds[0]): continue
            row = {headers[i]: clean_text(tds[i]) for i in range(len(tds)) if i < len(headers)}
            if is_prod:
                a = tr.find("a")
                if a:
                    m = re.search(r"'([^']+)'", a.get("onclick", ""))
                    if m: row["제품상세키"] = m.group(1)
            res.append(row)
        return res

    haccp_table = get_table("HACCP 인증 정보")
    haccp_data = parse_list(haccp_table)

    return {
        "인허가 정보": parse_info(get_table("인허가 정보")),
        "HACCP 인증 정보": haccp_data,
        "인허가 변경사항정보": parse_list(get_table("인허가 변경사항정보")),
        "행정처분 정보": parse_list(get_table("행정처분 정보")),
        "제조품목 정보": parse_list(get_table("제조품목 정보"), True),
        "HACCP 인증 여부": "Y" if haccp_data else "N",
    }

# =========================================================
# 메인 실행부
# =========================================================
def main():
    print("="*50)
    print(" [식품안전나라 상세수집기 - 범위 지정 모드]")
    print("="*50)

    try:
        start_no = int(input("시작 번호 (예: 2500): "))
        end_no = int(input("끝 번호 (예: 3000): "))
    except ValueError:
        print("숫자만 입력 가능합니다.")
        return

    output_file = RAWDATA_DIR / f"detail_{start_no}_{end_no}.json"

    # 데이터 로드
    all_list = read_json(INPUT_JSON)
    # 입력받은 '번호' 키 값 기준으로 필터링
    targets = [item for item in all_list if start_no <= int(item['번호']) <= end_no]

    if not targets:
        print(f"해당 범위({start_no}~{end_no})에 해당하는 데이터가 없습니다.")
        return

    print(f"▶ 수집 대상: {len(targets)} 건")
    print(f"▶ 저장 경로: {output_file}")
    print("="*50)

    session = requests.Session()
    collected_data = []

    for i, item in enumerate(targets, 1):
        row_no = item['번호']
        company = item['업체명']
        key = item['상세키']

        try:
            log(f"[{i}/{len(targets)}] 번호:{row_no} | {company} 요청 중...")

            res = session.get(
                DETAIL_URL,
                headers=make_headers(),
                params={"bsnLcnsLedgNo": key, "callPage": CALL_PAGE},
                proxies=PROXIES,
                verify=False,
                timeout=30
            )

            if res.status_code == 200:
                detail = parse_detail_html(res.text)
                # 원본 데이터에 상세 정보 병합
                full_item = {**item, **detail}
                collected_data.append(full_item)

                # 매 건수마다 저장 (비정상 종료 대비)
                save_json(collected_data, output_file)
            else:
                log(f"   [오류] HTTP {res.status_code}")

        except Exception as e:
            log(f"   [실패] {e}")

    print("\n" + "="*50)
    print(f" 작업 완료: {len(collected_data)} 건 수집됨")
    print(f" 파일 저장됨: {output_file}")
    print("="*50)
    input("엔터를 누르면 종료됩니다...")

if __name__ == "__main__":
    main()