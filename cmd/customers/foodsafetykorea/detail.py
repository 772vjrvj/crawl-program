
import json
import random
import re
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# =========================================================
# 설정
# =========================================================
BASE_URL = "https://www.foodsafetykorea.go.kr"

DETAIL_URL = (
    "https://www.foodsafetykorea.go.kr"
    "/potalPopup/fooddanger/bsnInfoDetail.do"
)

INPUT_JSON = "foodsafety_bsn_list.json"
OUTPUT_JSON = "foodsafety_bsn_detail.json"
FAILED_JSON = "foodsafety_bsn_detail_failed.json"

# 상세 요청 Network에서 잡은 callPage 직접 입력
CALL_PAGE = "5409756199133579"

# 쿠키 없어도 되면 빈 값 유지
# 필요하면 브라우저 Network에서 cookie 전체 복사해서 넣기
COOKIE = "elevisor_for_j2ee_uid=f5at4pm3cf3rg; JSESSIONID=NW91b1CoAaD9At73fnEaELiYVCaW01lNaUUkK6on2BFX2WvGtBUtySe1nPev7Yer.amV1c19kb21haW4veGNvd2FzMDJfSVBPMDE=; GPKISecureWebSession=w8ksi4DjqP6T530MxXBh; notShowModalPopupYn=Y; callPage=5409756199133579"

# 테스트할 때는 5, 10 정도
# 전체 수집은 None
MAX_COUNT = None

# 이미 상세가 들어간 row는 건너뜀
SKIP_DONE = True

# 요청 순서 섞기
# 결과 JSON 순서는 원본 순서 유지
SHUFFLE_REQUEST_ORDER = False

# =========================================================
# IP 차단 방지를 위한 딜레이 설정 (강화됨)
# =========================================================
# 기본 요청 간 랜덤 대기 (기존보다 길게 설정)
MIN_DELAY_SEC = 3.5
MAX_DELAY_SEC = 7.5

# 몇 건마다 긴 휴식
LONG_SLEEP_EVERY = 20
LONG_SLEEP_MIN_SEC = 30
LONG_SLEEP_MAX_SEC = 60

# 차단 방지를 위해 100건 정도마다 매우 긴 휴식 추가 (사람인 것처럼 위장)
VERY_LONG_SLEEP_EVERY = 100
VERY_LONG_SLEEP_MIN_SEC = 180  # 3분
VERY_LONG_SLEEP_MAX_SEC = 300  # 5분

# 재시도
MAX_RETRY = 3

# 디버그 HTML 저장 여부
SAVE_DEBUG_HTML = True
DEBUG_HTML_DIR = "debug_detail_html"


# =========================================================
# 로그 / 파일
# =========================================================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{now()}] {msg}")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def random_sleep():
    sec = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
    log(f"대기 {sec:.2f}초")
    time.sleep(sec)


def long_sleep_if_needed(done_count):
    if done_count > 0:
        # 100건 단위 매우 긴 휴식을 먼저 체크
        if done_count % VERY_LONG_SLEEP_EVERY == 0:
            sec = random.uniform(VERY_LONG_SLEEP_MIN_SEC, VERY_LONG_SLEEP_MAX_SEC)
            log(f"매우 긴 휴식(IP차단 방지) {sec:.2f}초 / 처리건수={done_count}")
            time.sleep(sec)
        # 20건 단위 긴 휴식 체크
        elif done_count % LONG_SLEEP_EVERY == 0:
            sec = random.uniform(LONG_SLEEP_MIN_SEC, LONG_SLEEP_MAX_SEC)
            log(f"긴 휴식 {sec:.2f}초 / 처리건수={done_count}")
            time.sleep(sec)


def save_debug_html(row_no, html):
    if not SAVE_DEBUG_HTML:
        return

    debug_dir = Path(DEBUG_HTML_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)

    file_path = debug_dir / f"debug_detail_{row_no}.html"
    file_path.write_text(html, encoding="utf-8")

    log(f"[디버그HTML저장] {file_path}")


# =========================================================
# 요청 헤더
# =========================================================
def make_headers():
    headers = {
        "accept": "text/html, */*; q=0.01",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "connection": "keep-alive",
        "pragma": "no-cache",
        "referer": (
            "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoCompany.do"
            "?menu_grp=MENU_NEW04&menu_no=2813"
        ),
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "x-fancybox": "true",
        "x-requested-with": "XMLHttpRequest",
    }

    if COOKIE:
        headers["cookie"] = COOKIE

    return headers


def check_headers(headers):
    """
    header에 한글 placeholder 같은 게 들어가면 requests가 latin-1 인코딩 오류를 냄.
    요청 전에 미리 확인.
    """
    for key, value in headers.items():
        try:
            key.encode("latin-1")
            value.encode("latin-1")
        except Exception as e:
            log("[헤더 인코딩 오류]")
            log(f"key={key}")
            log(f"value={value}")
            log(f"error={e}")
            raise


# =========================================================
# 상세 요청
# =========================================================
def fetch_detail_html(session, detail_key, row_no, company_name):
    params = {
        "bsnLcnsLedgNo": detail_key,
        "callPage": CALL_PAGE,
    }

    for retry in range(1, MAX_RETRY + 1):
        try:
            log(
                f"[상세요청] 번호={row_no} 업체명={company_name} "
                f"상세키={detail_key} retry={retry}/{MAX_RETRY}"
            )

            headers = make_headers()
            check_headers(headers)

            res = session.get(
                DETAIL_URL,
                headers=headers,
                params=params,
                timeout=30,
            )

            log(
                f"[상세응답] 번호={row_no} status={res.status_code} "
                f"size={len(res.content)} url={res.url}"
            )

            if res.status_code != 200:
                text_preview = res.content.decode("utf-8", errors="ignore")[:700]
                log(f"[상세오류본문] {text_preview}")
                res.raise_for_status()

            # 중요: res.text 대신 직접 UTF-8 디코딩
            html = res.content.decode("utf-8", errors="ignore")

            log(f"[HTML확인] 인허가 정보 포함={'인허가 정보' in html}")
            log(f"[HTML확인] HACCP 인증 정보 포함={'HACCP 인증 정보' in html}")
            log(f"[HTML확인] 제조품목 정보 포함={'제조품목 정보' in html}")
            log(f"[HTML앞부분] {html[:200].replace(chr(10), ' ')}")

            save_debug_html(row_no, html)

            return html

        except Exception as e:
            log(f"[상세실패] 번호={row_no} retry={retry} error={e}")

            if retry >= MAX_RETRY:
                raise

            wait_sec = random.uniform(3, 8) * retry
            log(f"[재시도대기] {wait_sec:.2f}초")
            time.sleep(wait_sec)

    return ""


# =========================================================
# HTML 파싱
# =========================================================
def clean_text(value):
    if value is None:
        return ""

    if hasattr(value, "get_text"):
        text = value.get_text(" ", strip=True)
    else:
        text = str(value)

    text = re.sub(r"\s+", " ", text).strip()

    # 2026 -03 -18 -> 2026-03-18
    text = re.sub(r"\s*-\s*", "-", text)

    return text


def find_table_by_caption(soup, caption_name):
    """
    caption 텍스트 기준으로 table 찾기
    """
    for table in soup.find_all("table"):
        caption = table.find("caption")

        if not caption:
            continue

        caption_text = clean_text(caption)

        if caption_name in caption_text:
            return table

    return None


def parse_info_table(table):
    """
    인허가 정보 전용
    th, td, th, td 형태를 dict로 변환
    """
    result = {}

    if not table:
        return result

    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])

        key = ""

        for cell in cells:
            tag_name = cell.name.lower()
            text = clean_text(cell)

            if not text:
                continue

            if tag_name == "th":
                key = text

            elif tag_name == "td" and key:
                result[key] = text
                key = ""

    return result


def get_table_headers(table):
    headers = []

    if not table:
        return headers

    thead = table.find("thead")

    if not thead:
        return headers

    for th in thead.find_all("th"):
        text = clean_text(th)

        if text:
            headers.append(text)

    return headers


def extract_onclick_id(tag):
    if not tag:
        return ""

    onclick = tag.get("onclick", "")

    match = re.search(r"fn_movePrdDetail\('([^']+)'\)", onclick)

    if match:
        return match.group(1)

    match = re.search(r"'([^']+)'", onclick)

    if match:
        return match.group(1)

    return ""


def parse_list_table(table, caption_name):
    """
    HACCP 인증 정보
    인허가 변경사항정보
    행정처분 정보
    제조품목 정보

    thead th 기준으로 tbody td 매핑
    """
    result = []

    if not table:
        return result

    headers = get_table_headers(table)

    if not headers:
        return result

    tbody = table.find("tbody")

    if not tbody:
        return result

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")

        if not tds:
            continue

        row = {}

        for idx, header in enumerate(headers):
            if idx < len(tds):
                row[header] = clean_text(tds[idx])
            else:
                row[header] = ""

        # 제조품목 정보는 제품상세키 추가
        if caption_name == "제조품목 정보":
            a_tag = tr.find("a")
            product_detail_key = extract_onclick_id(a_tag)

            if product_detail_key:
                row["제품상세키"] = product_detail_key

        # 빈 row 제거
        if any(str(v).strip() for v in row.values()):
            result.append(row)

    return result


def parse_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")

    permit_table = find_table_by_caption(soup, "인허가 정보")
    haccp_table = find_table_by_caption(soup, "HACCP 인증 정보")
    change_table = find_table_by_caption(soup, "인허가 변경사항정보")
    admin_table = find_table_by_caption(soup, "행정처분 정보")
    product_table = find_table_by_caption(soup, "제조품목 정보")

    log(f"[테이블확인] 인허가 정보 table={permit_table is not None}")
    log(f"[테이블확인] HACCP 인증 정보 table={haccp_table is not None}")
    log(f"[테이블확인] 인허가 변경사항정보 table={change_table is not None}")
    log(f"[테이블확인] 행정처분 정보 table={admin_table is not None}")
    log(f"[테이블확인] 제조품목 정보 table={product_table is not None}")

    permit_info = parse_info_table(permit_table)
    haccp_list = parse_list_table(haccp_table, "HACCP 인증 정보")
    change_list = parse_list_table(change_table, "인허가 변경사항정보")
    admin_list = parse_list_table(admin_table, "행정처분 정보")
    product_list = parse_list_table(product_table, "제조품목 정보")

    return {
        "인허가 정보": permit_info,
        "HACCP 인증 정보": haccp_list,
        "인허가 변경사항정보": change_list,
        "행정처분 정보": admin_list,
        "제조품목 정보": product_list,
        "HACCP 인증 여부": "Y" if haccp_list else "N",
    }


def has_detail(row):
    """
    기존에는 아무 상세 데이터나 하나라도 있으면 True를 반환했으나,
    요청하신 대로 '인허가 정보' 내에 '업체명'이 정상 수집되었는지를 기준으로 판단합니다.
    """
    permit_info = row.get("인허가 정보")

    if permit_info and isinstance(permit_info, dict) and permit_info.get("업체명"):
        return True

    return False


# =========================================================
# 대상 생성
# =========================================================
def build_targets(data):
    targets = []

    for idx, row in enumerate(data):
        detail_key = row.get("상세키", "")

        if not detail_key:
            continue

        if SKIP_DONE and has_detail(row):
            continue

        targets.append(idx)

    if SHUFFLE_REQUEST_ORDER:
        random.shuffle(targets)

    if MAX_COUNT:
        targets = targets[:MAX_COUNT]

    return targets


def load_start_data():
    """
    OUTPUT_JSON이 있으면 이어서 진행 가능하게 OUTPUT_JSON 우선 사용.
    없으면 INPUT_JSON 사용.
    """
    output_path = Path(OUTPUT_JSON)

    if output_path.exists():
        log(f"[로드] 기존 결과 파일에서 이어서 진행: {OUTPUT_JSON}")
        return read_json(OUTPUT_JSON)

    log(f"[로드] 원본 목록 파일 사용: {INPUT_JSON}")
    return read_json(INPUT_JSON)


# =========================================================
# 메인 처리
# =========================================================
def collect_detail():
    data = load_start_data()
    results = deepcopy(data)
    failed = []

    session = requests.Session()
    targets = build_targets(results)

    log("=" * 80)
    log("상세 수집 시작")
    log(f"입력 파일={INPUT_JSON}")
    log(f"출력 파일={OUTPUT_JSON}")
    log(f"전체 row 수={len(results)}")
    log(f"상세 수집 대상 수={len(targets)}")
    log(f"CALL_PAGE={CALL_PAGE}")
    log(f"COOKIE 사용 여부={bool(COOKIE)}")
    log(f"SHUFFLE_REQUEST_ORDER={SHUFFLE_REQUEST_ORDER}")
    log(f"MAX_COUNT={MAX_COUNT}")
    log(f"SAVE_DEBUG_HTML={SAVE_DEBUG_HTML}")
    log("=" * 80)

    done_count = 0

    for order_no, idx in enumerate(targets, start=1):
        row = results[idx]

        row_no = row.get("번호", "")
        region = row.get("지역", "")
        company_name = row.get("업체명", "")
        detail_key = row.get("상세키", "")

        log("")
        log(
            f"[진행] {order_no}/{len(targets)} "
            f"json_index={idx} 번호={row_no} 지역={region} 업체명={company_name}"
        )

        try:
            html = fetch_detail_html(
                session=session,
                detail_key=detail_key,
                row_no=row_no,
                company_name=company_name,
            )

            detail_data = parse_detail_html(html)

            log(
                f"[파싱결과] "
                f"인허가정보={len(detail_data['인허가 정보'])} "
                f"HACCP={len(detail_data['HACCP 인증 정보'])} "
                f"변경사항={len(detail_data['인허가 변경사항정보'])} "
                f"행정처분={len(detail_data['행정처분 정보'])} "
                f"제조품목={len(detail_data['제조품목 정보'])}"
            )

            row["인허가 정보"] = detail_data["인허가 정보"]
            row["HACCP 인증 정보"] = detail_data["HACCP 인증 정보"]
            row["인허가 변경사항정보"] = detail_data["인허가 변경사항정보"]
            row["행정처분 정보"] = detail_data["행정처분 정보"]
            row["제조품목 정보"] = detail_data["제조품목 정보"]
            row["HACCP 인증 여부"] = detail_data["HACCP 인증 여부"]

            results[idx] = row
            done_count += 1

            log(
                f"[저장대상확인] 번호={row_no} "
                f"인허가정보={bool(row['인허가 정보'])} "
                f"HACCP건수={len(row['HACCP 인증 정보'])} "
                f"제조품목건수={len(row['제조품목 정보'])}"
            )

            save_json(results, OUTPUT_JSON)
            save_json(failed, FAILED_JSON)

            log(f"[중간저장] {OUTPUT_JSON}")

        except Exception as e:
            log(f"[실패] 번호={row_no} 업체명={company_name} error={e}")

            failed.append({
                "json_index": idx,
                "번호": row_no,
                "지역": region,
                "업체명": company_name,
                "상세키": detail_key,
                "error": str(e),
            })

            save_json(results, OUTPUT_JSON)
            save_json(failed, FAILED_JSON)

        random_sleep()
        long_sleep_if_needed(done_count)

    save_json(results, OUTPUT_JSON)
    save_json(failed, FAILED_JSON)

    log("")
    log("=" * 80)
    log("상세 수집 종료")
    log(f"성공 처리 수={done_count}")
    log(f"실패 수={len(failed)}")
    log(f"결과 파일={OUTPUT_JSON}")
    log(f"실패 파일={FAILED_JSON}")
    log("=" * 80)


def main():
    collect_detail()


if __name__ == "__main__":
    main()
