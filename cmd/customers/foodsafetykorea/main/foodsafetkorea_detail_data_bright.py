import json, re, time, threading, urllib3, requests
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# SSL 경고 무시 및 설정
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COOKIE = "elevisor_for_j2ee_uid=4pb5v04ahv19w; JSESSIONID=Q1aT7EcjyLyOQaiN8yRSs5plMoZ7LSLK15utvBnodmZbZ1JwTGHmy5Fd5XyV2Ifa.amV1c19kb21haW4veGNvd2FzMDFfSVBPMDE=; GPKISecureWebSession=qhBg91Jipp2Bn0IRMwxo; callPage=5659260513687476"
CALL_PAGE = "5659260513687476"
BRD_PROXY = {"http": "http://brd-customer-hl_7b5686a6-zone-foodsafetykorea-country-kr:5iw55h83jmjv@brd.superproxy.io:22225", "https": "http://brd-customer-hl_7b5686a6-zone-foodsafetykorea-country-kr:5iw55h83jmjv@brd.superproxy.io:22225"}
DETAIL_URL = "https://www.foodsafetykorea.go.kr/potalPopup/fooddanger/bsnInfoDetail.do"

INPUT_JSON = "foodsafety_bsn_detail.json"
OUTPUT_JSON = "out.json"

# 쓰레드 안전을 위한 변수
data_lock = threading.Lock()
collected_data = []
success_count = 0

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def clean_text(value):
    if value is None: return ""
    text = value.get_text(" ", strip=True) if hasattr(value, "get_text") else str(value)
    return re.sub(r"\s+", " ", text).strip()

def parse_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")
    def get_t(cap):
        for t in soup.find_all("table"):
            if t.find("caption") and cap in clean_text(t.find("caption")): return t
        return None
    def p_info(t):
        res = {}
        if t:
            for tr in t.find_all("tr"):
                ths, tds = tr.find_all("th"), tr.find_all("td")
                for h, d in zip(ths, tds): res[clean_text(h)] = clean_text(d)
        return res
    def p_list(t, is_p=False):
        res = []
        if not t or not t.find("tbody"): return res
        headers = [clean_text(th) for th in t.find_all("th")]
        for tr in t.find("tbody").find_all("tr"):
            tds = tr.find_all("td")
            if not tds or "데이터가 없습니다" in clean_text(tds[0]): continue
            row = {headers[i]: clean_text(tds[i]) for i in range(len(tds)) if i < len(headers)}
            if is_p:
                m = re.search(r"'([^']+)'", tr.find("a").get("onclick", "")) if tr.find("a") else None
                if m: row["제품상세키"] = m.group(1)
            res.append(row)
        return res

    h_list = p_list(get_t("HACCP 인증 정보"))
    return {
        "인허가 정보": p_info(get_t("인허가 정보")),
        "HACCP 인증 정보": h_list,
        "인허가 변경사항정보": p_list(get_t("인허가 변경사항정보")),
        "행정처분 정보": p_list(get_t("행정처분 정보")),
        "제조품목 정보": p_list(get_t("제조품목 정보"), True),
        "HACCP 인증 여부": "Y" if h_list else "N",
    }

def fetch_worker(session, item):
    global success_count
    headers = {
        "accept": "text/html, */*; q=0.01",
        "referer": "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoCompany.do?menu_grp=MENU_NEW04&menu_no=2813",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": COOKIE
    }
    try:
        res = session.get(DETAIL_URL, headers=headers, params={"bsnLcnsLedgNo": item['상세키'], "callPage": CALL_PAGE}, proxies=BRD_PROXY, verify=False, timeout=30)
        if res.status_code == 200:
            item.update(parse_detail_html(res.text))
            with data_lock:
                collected_data.append(item)
                success_count += 1
                log(f"[성공] {success_count}건 - {item.get('업체명')}")
                if success_count % 10 == 0:
                    Path(OUTPUT_JSON).write_text(json.dumps(collected_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    log(f" >>> 10건 단위 중간 저장 완료 ({success_count}건)")
    except Exception as e:
        log(f" [오류] {item.get('업체명')}: {e}")

def main():
    log("데이터 필터링 중...")
    all_data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    # '인허가 정보'가 없거나 비어있는 것만 수집
    targets = [i for i in all_data if not i.get("인허가 정보")]

    if not targets:
        log("수집할 대상이 없습니다.")
        return

    log(f"총 {len(targets)}건 수집 시작 (쓰레드 8개)")

    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_worker, session, item) for item in targets]
            for _ in as_completed(futures): pass

    Path(OUTPUT_JSON).write_text(json.dumps(collected_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"전체 작업 완료. 최종 {len(collected_data)}건 저장됨.")

if __name__ == "__main__":
    main()