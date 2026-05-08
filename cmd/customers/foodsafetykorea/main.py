import json
import time
import random
from pathlib import Path
from datetime import datetime

import requests


# ==============================
# 기본 설정
# ==============================
BASE_URL = "https://www.foodsafetykorea.go.kr"

SEARCH_PAGE_URL = (
    "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoCompany.do"
    "?menu_grp=MENU_NEW04&menu_no=2813"
)

AJAX_URL = f"{BASE_URL}/ajax/portal/specialinfo/searchBsnList.do"

OUTPUT_FILE = "foodsafety_bsn_list.json"

PAGE_SIZE = 50

CALL_PAGE = "4183411263476406"

# 테스트할 때는 1 또는 2
# 전체 수집할 때는 None
MAX_PAGES_PER_REGION = None

# 너무 빠르게 요청하지 않도록 대기
REQUEST_DELAY_SEC = 0.3
REGION_DELAY_SEC = 0.5

# 필요하면 브라우저 개발자도구에서 복사한 cookie 전체를 넣기
# 예: "JSESSIONID=...; callPage=..."
COOKIE = "elevisor_for_j2ee_uid=a8jvrkducruks; GPKISecureWebSession=IPcii49IaDiFnoCsjCqk; JSESSIONID=vPXpEt6wj8leI9vKBIz1Z5aMMPIRcoq8FRmM0JJqa7DAonvctWi1KCfz1jhhdWHH.amV1c19kb21haW4veGNvd2FzMDJfSVBPMDE=; callPage=4183411263476406"


# ==============================
# 지역 코드
# ==============================
SIDO_LIST = [
    {"지역": "서울특별시", "code": "11"},
    {"지역": "부산광역시", "code": "26"},
    {"지역": "대구광역시", "code": "27"},
    {"지역": "인천광역시", "code": "28"},
    {"지역": "광주광역시", "code": "29"},
    {"지역": "대전광역시", "code": "30"},
    {"지역": "울산광역시", "code": "31"},
    {"지역": "세종특별자치시", "code": "3611"},
    {"지역": "경기도", "code": "41"},
    {"지역": "강원특별자치도", "code": "51"},
    {"지역": "충청북도", "code": "43"},
    {"지역": "충청남도", "code": "44"},
    {"지역": "전북특별자치도", "code": "52"},
    {"지역": "전라남도", "code": "46"},
    {"지역": "경상북도", "code": "47"},
    {"지역": "경상남도", "code": "48"},
    {"지역": "제주특별자치도", "code": "50"},
]


# ==============================
# 로그
# ==============================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    print(f"[{now()}] {message}")


def make_region_log(region_idx, total_regions, region_name, region_code):
    return f"[지역 {region_idx:02d}/{total_regions}] {region_name}(code={region_code})"


def save_json(data, file_path):
    Path(file_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_headers(call_page):
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "connection": "keep-alive",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.foodsafetykorea.go.kr",
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
        "x-requested-with": "XMLHttpRequest",
    }

    if COOKIE:
        headers["cookie"] = COOKIE

    return headers


def make_payload(sido_code, page_num, page_size, call_page):
    copy_url = (
        "https://www.foodsafetykorea.go.kr:443"
        "/portal/specialinfo/searchInfoCompany.do"
        "?menu_grp=MENU_NEW04&menu_no=2813"
    )

    # 같은 key가 여러 번 들어가므로 dict가 아니라 list tuple 사용
    return [
        ("menu_no", "2813"),
        ("menu_grp", "MENU_NEW04"),
        ("menuNm", ""),
        ("copyUrl", copy_url),
        ("mberId", ""),
        ("mberNo", ""),
        ("favorListCnt", ""),

        ("menu_grp", "MENU_NEW04"),
        ("menu_no", "2813"),

        ("s_mode", "1"),
        ("s_opt", "food"),
        ("s_sido_cd", sido_code),
        ("s_bsn_nm", ""),
        ("s_lcns_no", ""),
        ("s_opt1", "N"),
        ("s_opt2", "Y"),
        ("s_opt3", "N"),
        ("s_opt4", ""),
        ("s_keyword", ""),
        ("s_opt5", "N"),
        ("s_opt5_sdt", ""),
        ("s_opt5_edt", ""),
        ("s_opt6", "1"),
        ("s_opt7", "N"),
        ("s_induty_cd", "106,402,107,108,117,109,111,112,113,122,110,114,115,116,123"),
        ("s_order_by", "reg_dt"),
        ("s_list_cnt", str(page_size)),
        ("s_page_num", str(page_num)),
        ("s_food_truck_yn", ""),
        ("s_na_yn", ""),
        ("s_halal_yn", ""),
        ("s_prsdnt_nm", ""),
        ("s_dsp_reason", ""),
        ("s_induty_cd_dsp", ""),
        ("s_tx_id", "1"),
        ("callPage", call_page),

        ("chk_sido", sido_code),
        ("bsn_nm", ""),
        ("lcns_no", ""),
        ("site_addr", ""),
        ("opt6_1", "1"),

        # 원본 payload에 chk_sido가 한 번 더 있음
        ("chk_sido", sido_code),
        ("upjongOne", "all"),
        ("opt6_2", "1"),
        ("bsn_nm", ""),
        ("lcns_no", ""),
        ("prsdnt_nm", ""),
    ]


# ==============================
# 목록 row 한글 매핑
# ==============================
def map_row(row, region_name, region_code, no):
    haccp_yn = row.get("HACCP_YN", "") or "N"

    return {
        "번호": no,
        "지역": region_name,
        "지역코드": region_code,

        "인허가번호": row.get("LCNS_NO", ""),
        "업체명": row.get("BSSH_NM", ""),
        "업종": row.get("INDUTY_CD_NM", ""),
        "대표자": row.get("PRSDNT_NM", ""),
        "소재지": row.get("SITE_ADDR", ""),
        "인허가기관": row.get("INSTT_CD_NM", ""),
        "영업상태": row.get("CLSBIZ_DVS_CD_NM", ""),
        "비고": "",

        # 상세 페이지 호출에 필요
        "상세키": row.get("BSN_LCNS_LEDG_NO", ""),

        # 목록 응답 기준
        # 나중에 상세 수집 추가하면 HACCP 인증 정보 배열 존재 여부로 다시 갱신 가능
        "HACCP 인증 여부": haccp_yn,

        # 나중에 상세 수집 붙일 자리
        "인허가 정보": {},
        "HACCP 인증 정보": [],
        "제조품목 정보": [],

        # 원본 확인용
        "원본": row,
    }


# ==============================
# 목록 페이지 요청
# ==============================
def fetch_list_page(session, sido_code, page_num, page_size, call_page, region_log):
    url = f"{AJAX_URL}?callPage={call_page}"

    log(f"{region_log} [page={page_num}] 요청 시작")
    log(f"{region_log} [page={page_num}] URL={url}")
    log(f"{region_log} [page={page_num}] sido_code={sido_code}")
    log(f"{region_log} [page={page_num}] page_size={page_size}")
    log(f"{region_log} [page={page_num}] callPage={call_page}")

    try:
        res = session.post(
            url,
            headers=make_headers(call_page),
            data=make_payload(sido_code, page_num, page_size, call_page),
            timeout=30,
        )

        log(f"{region_log} [page={page_num}] 응답 status={res.status_code}")
        log(f"{region_log} [page={page_num}] 응답 앞부분={res.text[:500]}")

        if res.status_code != 200:
            log(f"{region_log} [page={page_num}] 응답 미리보기={res.text[:1000]}")
            res.raise_for_status()

        try:
            data = res.json()
        except Exception as e:
            log(f"{region_log} [page={page_num}] JSON 변환 실패")
            log(f"{region_log} [page={page_num}] 응답 미리보기={res.text[:1500]}")
            raise e

        rows = data.get("bsnList", [])

        log(f"{region_log} [page={page_num}] s_tx_id={data.get('s_tx_id', '')}")
        log(f"{region_log} [page={page_num}] bsnList count={len(rows)}")

        if rows:
            first_name = rows[0].get("BSSH_NM", "")
            first_lcns = rows[0].get("LCNS_NO", "")
            last_name = rows[-1].get("BSSH_NM", "")
            last_lcns = rows[-1].get("LCNS_NO", "")

            log(f"{region_log} [page={page_num}] 첫 업체={first_name} / 인허가번호={first_lcns}")
            log(f"{region_log} [page={page_num}] 마지막 업체={last_name} / 인허가번호={last_lcns}")

        return rows

    except requests.exceptions.Timeout:
        log(f"{region_log} [page={page_num}] 요청 타임아웃")
        raise

    except requests.exceptions.RequestException as e:
        log(f"{region_log} [page={page_num}] 요청 오류={e}")
        raise

    except Exception as e:
        log(f"{region_log} [page={page_num}] 처리 오류={e}")
        raise


# ==============================
# 전체 수집
# ==============================
def collect_all():
    session = requests.Session()

    results = []
    no = 1
    total_regions = len(SIDO_LIST)

    list_call_page = CALL_PAGE

    log("=" * 80)
    log("수집 시작")
    log(f"저장 파일={OUTPUT_FILE}")
    log(f"지역 수={total_regions}")
    log(f"페이지당 수집 건수={PAGE_SIZE}")
    log(f"MAX_PAGES_PER_REGION={MAX_PAGES_PER_REGION}")
    log(f"목록 callPage={list_call_page}")
    log("=" * 80)

    for region_idx, sido in enumerate(SIDO_LIST, start=1):
        region_name = sido["지역"]
        region_code = sido["code"]

        page_num = 1
        region_total = 0
        call_page = list_call_page

        region_log = make_region_log(
            region_idx=region_idx,
            total_regions=total_regions,
            region_name=region_name,
            region_code=region_code,
        )

        log("")
        log("-" * 80)
        log(f"{region_log} 시작")
        log(f"{region_log} callPage={call_page}")
        log("-" * 80)

        while True:
            if MAX_PAGES_PER_REGION and page_num > MAX_PAGES_PER_REGION:
                log(f"{region_log} [page={page_num}] MAX_PAGES_PER_REGION 도달로 지역 종료")
                break

            try:
                rows = fetch_list_page(
                    session=session,
                    sido_code=region_code,
                    page_num=page_num,
                    page_size=PAGE_SIZE,
                    call_page=call_page,
                    region_log=region_log,
                )

            except Exception as e:
                log(f"{region_log} [page={page_num}] 실패로 해당 지역 종료")
                log(f"{region_log} [page={page_num}] 오류 내용={e}")
                break

            if not rows:
                log(f"{region_log} [page={page_num}] 데이터 없음")
                log(f"{region_log} 종료 / 지역 수집={region_total}건 / 전체 누적={len(results)}건")
                break

            before_total = len(results)

            for row in rows:
                mapped = map_row(
                    row=row,
                    region_name=region_name,
                    region_code=region_code,
                    no=no,
                )
                results.append(mapped)
                no += 1

            region_total += len(rows)
            after_total = len(results)

            log(
                f"{region_log} [page={page_num}] 저장 완료 "
                f"/ 현재 페이지={len(rows)}건 "
                f"/ 지역 누적={region_total}건 "
                f"/ 전체 누적={after_total}건 "
                f"/ 증가={after_total - before_total}건"
            )

            save_json(results, OUTPUT_FILE)
            log(f"{region_log} [page={page_num}] 중간 저장 완료: {OUTPUT_FILE}")

            if len(rows) < PAGE_SIZE:
                log(
                    f"{region_log} [page={page_num}] 마지막 페이지 판단 "
                    f"/ 현재 페이지 건수 {len(rows)} < PAGE_SIZE {PAGE_SIZE}"
                )
                log(f"{region_log} 종료 / 지역 수집={region_total}건 / 전체 누적={len(results)}건")
                break

            page_num += 1
            time.sleep(REQUEST_DELAY_SEC)

        save_json(results, OUTPUT_FILE)
        log(f"{region_log} 지역 최종 저장 완료: {OUTPUT_FILE}")

        time.sleep(REGION_DELAY_SEC)

    log("")
    log("=" * 80)
    log(f"전체 수집 종료 / 총 {len(results)}건")
    log(f"최종 저장 파일={OUTPUT_FILE}")
    log("=" * 80)

    return results


# ==============================
# 실행
# ==============================
def main():
    results = collect_all()
    save_json(results, OUTPUT_FILE)

    print()
    print("=" * 80)
    print(f"[완료] 총 {len(results)}건 저장")
    print(f"[파일] {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    main()