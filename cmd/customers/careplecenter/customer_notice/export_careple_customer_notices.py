import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 최신 브라우저 쿠키만 넣어 실행하세요.
COOKIE = "_ga=GA1.2.1541479523.1786462213; SCOUTER=z585fum1bc95et; _gid=GA1.2.1705722455.1789353979; orgNm=%EC%84%9C%EC%9A%B8%EC%84%B1%EB%AA%A8%EC%9D%98%EC%9B%90%EC%95%84%EB%8F%99%EB%B0%9C%EB%8B%AC%ED%81%B4%EB%A6%AC%EB%8B%89%20; empId=172523906005189656; empNm=%EB%B0%95%EB%B3%91%EC%A4%80; loginId=rapport1; posn=%EB%8C%80%ED%91%9C%EB%8B%98; managerYn=Y; masterYn=N; tuid=tuid178972617157580966; sysNtc_sched_172523906005189656_178935060004325211=N; _gat=1; _ga_592EQKNPJ5=GS2.2.s1789735094$o77$g1$t1789736974$j56$l0$h0"
COMPANY_ID = "COMPANY000001"

# DB를 비운 뒤 적재하면 0으로 두면 됩니다. 기존 데이터가 있으면 마지막 번호로 수정하세요.
CUSTOMER_NOTICE_LAST_NO = 0
CUSTOMER_NOTICE_MEMBER_LAST_NO = 0
PAGE_SIZE = 50
DETAIL_WORKERS = 6
RETRY_COUNT = 7

LIST_URL = "https://www.careplecenter.com/pcareple/v1/boards/visnotice/.datatables"
DETAIL_URL = "https://www.careplecenter.com/pcareple/v1/boards/visnotice/posts/{post_id}"
OUTPUT_DIR = Path("output") / "customer_notice"
MEMBER_MAP_PATH = Path("output") / "member" / "member_id_map.csv"
TEACHER_MAP_PATH = Path("output") / "teacher" / "employee_id_map.csv"

NOTICE_HEADERS = [
    "CUSTOMER_NOTICE_ID", "COMPANY_ID", "TITLE", "CONTENT", "NOTICE_TYPE_CD", "RESERVE_YN", "RESERVE_DT",
    "SEND_STATUS_CD", "SEND_DT", "END_DT", "WRITER_ID", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
NOTICE_MEMBER_HEADERS = [
    "CUSTOMER_NOTICE_MEMBER_ID", "CUSTOMER_NOTICE_ID", "MEMBER_ID", "COMPANY_ID", "READ_YN", "READ_DT",
    "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
NOTICE_MAP_HEADERS = ["CAREPLE_POST_ID", "CUSTOMER_NOTICE_ID", "CAREPLE_REG_EMP_ID", "WRITER_ID"]
NOTICE_MEMBER_MAP_HEADERS = ["CAREPLE_POST_ID", "CAREPLE_VIS_ID", "CUSTOMER_NOTICE_MEMBER_ID", "MEMBER_ID"]
UNMATCHED_HEADERS = ["TYPE", "CAREPLE_POST_ID", "CAREPLE_SOURCE_ID", "DETAIL"]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_dt(value):
    value = str(value or "").strip().replace("T", " ").replace("Z", "")
    if not value:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return value


def parse_dt(value):
    try:
        return datetime.strptime(normalize_dt(value), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def request_json(url):
    tuid = next((item.split("=", 1)[1].strip() for item in COOKIE.split(";") if item.strip().startswith("tuid=")), "")
    headers = {
        "Accept": "*/*", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.careplecenter.com/index.html",
        "Cookie": COOKIE, "tuid": tuid,
    }
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with urlopen(Request(url, headers=headers, method="GET"), timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < RETRY_COUNT:
                wait_seconds = min(30, attempt * 3)
                print(f"요청 실패 {attempt}/{RETRY_COUNT}: {url} / {wait_seconds}초 후 재시도")
                time.sleep(wait_seconds)
    raise RuntimeError(f"API 호출 실패: {url} / {last_error}")


def load_map(path, source_keys, target_key, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} 매핑 파일이 없습니다: {path.resolve()}")
    result = {}
    with open(path, encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            source = next((str(row.get(key) or "").strip() for key in source_keys if str(row.get(key) or "").strip()), "")
            target = str(row.get(target_key) or "").strip()
            if source and target:
                result[source] = target
    if not result:
        raise ValueError(f"{path.name}에서 {description} 매핑을 찾지 못했습니다.")
    return result


def fetch_list():
    rows, start, total = [], 0, None
    draw = 1
    while total is None or start < total:
        query = {
            "dt": "", "searchKeyword": "", "searchStatDivCds": "ALL", "searchTargetDivCds": "ALL SELECTED",
            "searchDeleted": "N", "draw": draw, "start": start, "length": PAGE_SIZE, "orderDir": "none", "randid": time.time(),
        }
        response = request_json(f"{LIST_URL}?{urlencode(query)}")
        data = response.get("data") or {}
        if total is None:
            total = int(data.get("recordsFiltered") or data.get("recordsTotal") or 0)
        page_rows = data.get("data") or []
        rows.extend(page_rows)
        print(f"[{now_text()}] 고객공지 목록 {len(rows)}/{total}")
        if not page_rows:
            break
        start += len(page_rows)
        draw += 1
    return rows


def main():
    if not COOKIE.strip():
        raise ValueError("COOKIE에 최신 Careple 로그인 쿠키를 넣어주세요.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    member_map = load_map(MEMBER_MAP_PATH, ("CAREPLE_VIS_ID", "VIS_ID", "ASIS_VIS_ID"), "MEMBER_ID", "이용자")
    writer_map = load_map(TEACHER_MAP_PATH, ("CAREPLE_EMP_ID", "EMP_ID", "ASIS_EMP_ID"), "USER_ID", "작성자")

    list_rows = fetch_list()
    unique_list = {str(row.get("postId") or "").strip(): row for row in list_rows if str(row.get("postId") or "").strip()}

    def fetch_detail(post_id):
        url = f"{DETAIL_URL.format(post_id=post_id)}?{urlencode({'randid': time.time()})}"
        return post_id, (request_json(url).get("data") or {})

    details, unmatched, complete = {}, [], 0
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(fetch_detail, post_id): post_id for post_id in unique_list}
        for future in as_completed(futures):
            post_id = futures[future]
            try:
                key, detail = future.result()
                details[key] = detail
            except Exception as error:
                unmatched.append({"TYPE": "DETAIL_ERROR", "CAREPLE_POST_ID": post_id, "CAREPLE_SOURCE_ID": "", "DETAIL": str(error)})
            complete += 1
            if complete % 25 == 0 or complete == len(unique_list):
                print(f"[{now_text()}] 고객공지 상세 {complete}/{len(unique_list)} (동시작업 {DETAIL_WORKERS})")

    notice_rows, member_rows, notice_map_rows, member_map_rows, tobe_rows = [], [], [], [], []
    notice_no, notice_member_no = CUSTOMER_NOTICE_LAST_NO, CUSTOMER_NOTICE_MEMBER_LAST_NO
    for post_id, list_row in unique_list.items():
        source = details.get(post_id)
        if not source:
            continue
        notice_no += 1
        notice_id = f"NOTICE{notice_no:08d}"
        created_dt = normalize_dt(source.get("regDtime") or list_row.get("regDtime"))
        send_dt = normalize_dt(source.get("postSendDtime") or list_row.get("postSendDtime"))
        end_dt = normalize_dt(source.get("postEd") or list_row.get("postEd"))
        writer_emp_id = str(source.get("regEmpId") or list_row.get("regEmpId") or "").strip()
        writer_id = writer_map.get(writer_emp_id, "")
        if writer_emp_id and not writer_id:
            unmatched.append({"TYPE": "WRITER", "CAREPLE_POST_ID": post_id, "CAREPLE_SOURCE_ID": writer_emp_id, "DETAIL": "employee_id_map.csv 미매핑"})

        targets = [target for target in (source.get("targetList") or list_row.get("targetList") or []) if target.get("tgtTypeDivCd") == "VIS"]
        notice_type = source.get("postDivCd") or ("SELECTED" if targets else "ALL")
        # 발송예약 상태는 원본에 미래 예약 여부가 별도 없으므로 실제 발송일이 있으면 SENT, 없으면 NOT_SENT로 보존한다.
        reserve_yn = "N"
        if send_dt and created_dt and parse_dt(send_dt) and parse_dt(created_dt) and parse_dt(send_dt) > parse_dt(created_dt):
            reserve_yn = "Y"
        send_status = "SENT" if str(source.get("postSendYn") or "").upper() == "Y" else "NOT_SENT"
        deleted = "Y" if str(source.get("delYn") or "N").upper() == "Y" else "N"
        notice = {
            "CUSTOMER_NOTICE_ID": notice_id, "COMPANY_ID": COMPANY_ID, "TITLE": source.get("postTit") or list_row.get("postTit") or "",
            "CONTENT": source.get("postCont") or "", "NOTICE_TYPE_CD": notice_type, "RESERVE_YN": reserve_yn,
            "RESERVE_DT": send_dt if reserve_yn == "Y" else "", "SEND_STATUS_CD": send_status, "SEND_DT": send_dt,
            "END_DT": end_dt, "WRITER_ID": writer_id, "USE_YN": "Y", "DELETE_YN": deleted,
            "CREATE_DT": created_dt, "UPDATE_DT": normalize_dt(source.get("postSendDtime") or created_dt),
        }
        notice_rows.append(notice)
        notice_map_rows.append({"CAREPLE_POST_ID": post_id, "CUSTOMER_NOTICE_ID": notice_id, "CAREPLE_REG_EMP_ID": writer_emp_id, "WRITER_ID": writer_id})

        mapped_members = []
        for target in targets:
            vis_id = str(target.get("tgtId") or "").strip()
            member_id = member_map.get(vis_id, "")
            if not member_id:
                unmatched.append({"TYPE": "MEMBER", "CAREPLE_POST_ID": post_id, "CAREPLE_SOURCE_ID": vis_id, "DETAIL": "member_id_map.csv 미매핑"})
                continue
            notice_member_no += 1
            notice_member_id = f"NOTICE_M{notice_member_no:08d}"
            member_row = {
                "CUSTOMER_NOTICE_MEMBER_ID": notice_member_id, "CUSTOMER_NOTICE_ID": notice_id, "MEMBER_ID": member_id,
                "COMPANY_ID": COMPANY_ID, "READ_YN": "N", "READ_DT": "", "USE_YN": "Y", "DELETE_YN": deleted,
                "CREATE_DT": created_dt, "UPDATE_DT": "",
            }
            member_rows.append(member_row)
            member_map_rows.append({"CAREPLE_POST_ID": post_id, "CAREPLE_VIS_ID": vis_id, "CUSTOMER_NOTICE_MEMBER_ID": notice_member_id, "MEMBER_ID": member_id})
            mapped_members.append(member_row)
        if not targets:
            unmatched.append({"TYPE": "ALL_TARGET_NOTICE", "CAREPLE_POST_ID": post_id, "CAREPLE_SOURCE_ID": "", "DETAIL": "원본 대상목록 없음 - NOTICE_TYPE_CD=ALL, 회원별 행 미생성"})
        tobe_rows.append({"careplePostId": post_id, "notice": notice, "members": mapped_members})

    with open(OUTPUT_DIR / "customer_notice_asis_list_raw.json", "w", encoding="utf-8") as file:
        json.dump(list(unique_list.values()), file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "customer_notice_asis_detail_raw.json", "w", encoding="utf-8") as file:
        json.dump(details, file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "customer_notice_tobe_all.json", "w", encoding="utf-8") as file:
        json.dump(tobe_rows, file, ensure_ascii=False, indent=2)
    for path, headers, rows in (
            (OUTPUT_DIR / "customer_notice_master.csv", NOTICE_HEADERS, notice_rows),
            (OUTPUT_DIR / "customer_notice_member.csv", NOTICE_MEMBER_HEADERS, member_rows),
            (OUTPUT_DIR / "customer_notice_id_map.csv", NOTICE_MAP_HEADERS, notice_map_rows),
            (OUTPUT_DIR / "customer_notice_member_id_map.csv", NOTICE_MEMBER_MAP_HEADERS, member_map_rows),
            (OUTPUT_DIR / "customer_notice_unmatched_map.csv", UNMATCHED_HEADERS, unmatched),
    ):
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader(); writer.writerows(rows)
    with open(OUTPUT_DIR / "customer_notice_export_summary.json", "w", encoding="utf-8") as file:
        json.dump({"source_notice_count": len(unique_list), "detail_count": len(details), "notice_count": len(notice_rows),
                   "notice_member_count": len(member_rows), "unmatched_count": len(unmatched)}, file, ensure_ascii=False, indent=2)
    print(f"완료: 고객공지 {len(notice_rows)}건, 대상회원 {len(member_rows)}건, 미매핑 {len(unmatched)}건")


if __name__ == "__main__":
    main()
