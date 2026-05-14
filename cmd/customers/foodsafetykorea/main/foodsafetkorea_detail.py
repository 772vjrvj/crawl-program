import json, re, requests
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# 설정
DETAIL_URL = "https://www.foodsafetykorea.go.kr/potalPopup/fooddanger/bsnInfoDetail.do"
INPUT_JSON = "foodsafety_bsn_list.json"
OUTPUT_JSON = "out_json.json"
CALL_PAGE = "5409756199133579"
COOKIE = "elevisor_for_j2ee_uid=f5at4pm3cf3rg; JSESSIONID=NW91b1CoAaD9At73fnEaELiYVCaW01lNaUUkK6on2BFX2WvGtBUtySe1nPev7Yer.amV1c19kb21haW4veGNvd2FzMDJfSVBPMDE=; GPKISecureWebSession=w8ksi4DjqP6T530MxXBh; notShowModalPopupYn=Y; callPage=5409756199133579"

HEADERS = {
    "accept": "text/html, */*; q=0.01",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "pragma": "no-cache",
    "referer": "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoCompany.do?menu_grp=MENU_NEW04&menu_no=2813",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "x-fancybox": "true",
    "x-requested-with": "XMLHttpRequest",
    "cookie": COOKIE
}

def clean(val):
    if not val: return ""
    txt = val.get_text(" ", strip=True) if hasattr(val, "get_text") else str(val)
    return re.sub(r"\s+", " ", txt).strip()

def parse_tables(html):
    soup = BeautifulSoup(html, "html.parser")
    res = {}
    for table in soup.find_all("table"):
        cap = clean(table.find("caption"))
        if not cap: continue
        if "인허가 정보" in cap:
            info = {}
            cells = table.find_all(["th", "td"])
            for i in range(0, len(cells), 2):
                if i+1 < len(cells): info[clean(cells[i])] = clean(cells[i+1])
            res["인허가 정보"] = info
        else:
            headers = [clean(th) for th in table.find_all("th")]
            rows = []
            for tr in table.select("tbody tr"):
                tds = tr.find_all("td")
                if len(tds) < len(headers): continue
                row = {headers[i]: clean(tds[i]) for i in range(len(headers))}
                if "제조품목" in cap:
                    m = re.search(r"fn_movePrdDetail\('([^']+)'\)", str(tr))
                    if m: row["제품상세키"] = m.group(1)
                rows.append(row)
            res[cap] = rows
    return res

def fetch_worker(session, item):
    if not item.get("상세키") or (item.get("인허가 정보") and item["인허가 정보"].get("업체명")):
        return

    try:
        resp = session.get(DETAIL_URL, headers=HEADERS, params={"bsnLcnsLedgNo": item["상세키"], "callPage": CALL_PAGE}, timeout=10)
        if resp.status_code == 200:
            details = parse_tables(resp.content.decode("utf-8", errors="ignore"))
            item.update(details)
            item["HACCP 인증 여부"] = "Y" if details.get("HACCP 인증 정보") else "N"
            print(f"성공: {item.get('업체명')}")
    except Exception as e:
        print(f"오류 ({item.get('업체명')}): {e}")

def main():
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))

    # Session 객체는 쓰레드 세이프하므로 공유 가능
    with requests.Session() as s:
        # 쓰레드 8개로 작업 실행
        with ThreadPoolExecutor(max_workers=8) as executor:
            for item in data:
                executor.submit(fetch_worker, s, item)

    # 마지막에 한 번 저장
    Path(OUTPUT_JSON).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("수집 완료 및 저장 성공")

if __name__ == "__main__":
    main()