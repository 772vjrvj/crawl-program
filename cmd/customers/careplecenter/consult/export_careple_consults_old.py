import csv
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = ""
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2027-06"  # 스케줄 이관 범위와 반드시 같게 유지
CONSULT_ID_LAST_NO = 0
DETAIL_WORKERS = 6  # 4~8 사이 권장

# False면 기존 목록 캐시를 재사용합니다.
# 오늘 추가/수정된 상담·평가를 반영하려면 해당 월의 monthly/2026_09.json만 삭제하면 됩니다.
REFRESH_MONTHLY_LIST = False
# 상세는 내용 수정이 있을 수 있어 기본값을 True로 둡니다.
REFRESH_DETAIL = True

BASE_URL = "https://www.careplecenter.com"
LIST_URL = BASE_URL + "/pcareple/v1/counsels/.datatables"
DETAIL_URL = BASE_URL + "/pcareple/v1/counsels/"

MEMBER_DIR = Path("output/member")
TEACHER_DIR = Path("output/teacher")
PROGRAM_DIR = Path("output/program")
SCHEDULE_DIR = Path("output/schedule")
OUTPUT_DIR = Path("output/consult")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"

CONSULT_HEADERS = [
    "CONSULT_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID", "PROGRAM_ID",
    "CONSULT_TYPE_CD", "CONSULT_STATUS_CD", "TITLE", "COUNSEL_CONTENT", "MEMO", "CONSULT_DT",
    "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID",
]
CONSULT_MAP_HEADERS = ["CAREPLE_CONSULT_ID", "CONSULT_ID", "SCHEDULE_ID", "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID"]
UNMATCHED_HEADERS = ["CAREPLE_CONSULT_ID", "FIELD", "SOURCE_VALUE", "MESSAGE"]
ORIGIN_HEADERS = ["상담평가ID", "이용자", "프로그램", "담당선생님", "일시", "상태", "내용", "메모"]


def value(item):
    return str(item or "").strip()


def date_time(item):
    text = value(item).replace("T", " ").replace("Z", "")
    if not text:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(f"날짜 형식을 확인하세요: {item}")


def later_date_time(*items):
    values = [date_time(item) for item in items if value(item)]
    return max(values) if values else ""


def month_range(start_ym, end_ym):
    year, month = map(int, start_ym.split("-"))
    end_year, end_month = map(int, end_ym.split("-"))
    while (year, month) <= (end_year, end_month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def last_day(year, month):
    if month == 12:
        return "31"
    return (datetime(year, month + 1, 1) - timedelta(days=1)).strftime("%d")


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def validate(rows):
    required = ("CONSULT_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID")
    for index, row in enumerate(rows, start=2):
        missing = [key for key in required if not value(row.get(key))]
        if missing:
            raise ValueError(f"CONSULT_MASTER CSV {index}행 NOT NULL 값 누락: {', '.join(missing)}")


def checkpoint_path(kind, name):
    safe = "".join(char if char.isalnum() else "_" for char in str(name))
    path = CHECKPOINT_DIR / kind / f"{safe}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_checkpoint(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_checkpoint(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def request_retry(request_once, label):
    waits = (5, 15, 30, 60, 120, 300)
    for attempt in range(len(waits) + 1):
        try:
            return request_once()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            if attempt == len(waits):
                raise
            print(f"요청 실패 {attempt + 1}/{len(waits) + 1}: {label} / {error}")
            print(f"{waits[attempt]}초 후 재시도합니다.")
            time.sleep(waits[attempt])


def get_json(url, params=None):
    def request_once():
        query = urlencode(params or {})
        request = Request(f"{url}?{query}" if query else url, headers=HEADERS)
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    return request_retry(request_once, url)


def csv_mapping(rows, source_column, target_column):
    result = {}
    for row in rows:
        source, target = value(row.get(source_column)), value(row.get(target_column))
        if not source or not target:
            continue
        previous = result.get(source)
        if previous and previous != target:
            raise ValueError(f"매핑 CSV 원본 ID 중복: {source}")
        result[source] = target
    return result


def load_maps():
    required_files = [
        (MEMBER_DIR / "member_id_map.csv", "MEMBER"),
        (TEACHER_DIR / "employee_id_map.csv", "TEACHER"),
        (PROGRAM_DIR / "program_id_map.csv", "PROGRAM"),
        (SCHEDULE_DIR / "schedule_id_map.csv", "SCHEDULE"),
    ]
    for path, name in required_files:
        if not path.exists():
            raise FileNotFoundError(f"{path} 파일이 없습니다. {name} 이관을 먼저 실행하세요.")

    member_rows = read_csv(MEMBER_DIR / "member_id_map.csv")
    teacher_rows = read_csv(TEACHER_DIR / "employee_id_map.csv")
    program_rows = read_csv(PROGRAM_DIR / "program_id_map.csv")
    schedule_rows = read_csv(SCHEDULE_DIR / "schedule_id_map.csv")

    schedule_by_careple_id = {}
    for row in schedule_rows:
        if value(row.get("SCHEDULE_TYPE_CD")) != "CSL":
            continue
        schedule_id = value(row.get("SCHEDULE_ID"))
        for source_id in (value(row.get("CAREPLE_EVENT_ID")), value(row.get("CAREPLE_DETAIL_ID"))):
            if not source_id or not schedule_id:
                continue
            previous = schedule_by_careple_id.get(source_id)
            if previous and previous != schedule_id:
                raise ValueError(f"상담 원본 일정 ID가 둘 이상 매핑됩니다: {source_id}")
            schedule_by_careple_id[source_id] = schedule_id

    # 상세 응답에는 최종수정자의 ID가 없고 이름만 있는 경우가 있어, 이름 매핑은 보조로만 사용합니다.
    teacher_name_user = {}
    for row in teacher_rows:
        user_id = value(row.get("USER_ID"))
        for key in ("CAREPLE_EMP_NM", "EMP_NM", "TEACHER_NM"):
            name = value(row.get(key))
            if name and user_id:
                teacher_name_user[name] = user_id

    return {
        "member": csv_mapping(member_rows, "CAREPLE_VIS_ID", "MEMBER_ID"),
        "teacher": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "TEACHER_ID"),
        "teacher_user": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "USER_ID"),
        "teacher_name_user": teacher_name_user,
        "program": csv_mapping(program_rows, "CAREPLE_PROGRAM_ID", "PROGRAM_ID"),
        "schedule": schedule_by_careple_id,
    }


def fetch_month_list(year, month):
    ym = f"{year:04d}_{month:02d}"
    path = checkpoint_path("monthly", ym)
    if not REFRESH_MONTHLY_LIST:
        cached = read_checkpoint(path)
        if cached is not None:
            return cached

    all_rows, pages, start, draw = [], [], 0, 1
    while True:
        params = {
            "searchSd": f"{year:04d}-{month:02d}-01",
            "searchEd": f"{year:04d}-{month:02d}-{last_day(year, month)}",
            "searchVisDiv": "VIS_ID", "searchVisKeyword": "",
            "searchEmpDiv": "EMP_ID", "searchEmpKeyword": "",
            "searchPgmDiv": "PGM_DIV", "searchPgmKeyword": "",
            "searchStatDivCds": "R D C ", "saveTypeSet": "N", "dt": "",
            "extReq.fullyUseVisCtc": "true", "draw": str(draw), "start": str(start), "length": "100",
            "orderColumn": "conslDate", "orderDir": "asc", "randid": str(random.random()),
        }
        response = get_json(LIST_URL, params)
        page_data = response.get("data") or {}
        rows = page_data.get("data") or []
        pages.append(response)
        all_rows.extend(rows)
        total = int(value(page_data.get("recordsFiltered")) or len(all_rows))
        if not rows or len(all_rows) >= total:
            break
        start += len(rows)
        draw += 1

    result = {"year": year, "month": month, "pages": pages, "data": all_rows}
    write_checkpoint(path, result)
    return result


def fetch_detail(consl_id):
    path = checkpoint_path("detail", consl_id)
    if not REFRESH_DETAIL:
        cached = read_checkpoint(path)
        if cached is not None:
            return cached
    response = get_json(DETAIL_URL + consl_id, {"randid": random.random()})
    write_checkpoint(path, response)
    return response


def resolve_update_user(detail, mapping):
    reg_emp_id = value(detail.get("regEmpId"))
    user_id = mapping["teacher_user"].get(reg_emp_id, "")
    if user_id:
        return user_id

    # 응답의 `contLastModEmp`/`lastModEmp`는 "이름 / 직급" 형식이다.
    for raw_name in (detail.get("contLastModEmp"), detail.get("lastModEmp"), detail.get("regEmp")):
        name = value(raw_name).split(" / ", 1)[0]
        if mapping["teacher_name_user"].get(name):
            return mapping["teacher_name_user"][name]
    return ""


def main():
    if not COOKIE.strip():
        raise ValueError("상단 COOKIE에 최신 쿠키를 입력하세요.")

    global HEADERS
    tuid = next((item.split("=", 1)[1].strip() for item in COOKIE.split(";") if item.strip().startswith("tuid=")), "")
    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": BASE_URL + "/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE,
        "tuid": tuid,
    }

    mapping = load_maps()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    monthly_raw, list_by_id = [], {}
    for year, month in month_range(START_YM, END_YM):
        result = fetch_month_list(year, month)
        monthly_raw.append(result)
        for row in result.get("data") or []:
            consl_id = value(row.get("conslId"))
            if consl_id:
                list_by_id[consl_id] = row
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 목록 {year:04d}-{month:02d}: {len(result.get('data') or [])}건")

    consult_ids = list(list_by_id)
    details = {}
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(fetch_detail, consl_id): consl_id for consl_id in consult_ids}
        for number, future in enumerate(as_completed(futures), start=1):
            consl_id = futures[future]
            details[consl_id] = future.result()
            if number % 25 == 0 or number == len(consult_ids):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 상세 조회 {number}/{len(consult_ids)} (동시작업 {DETAIL_WORKERS})")

    consult_rows, consult_map_rows, unmatched, tobe_all = [], [], [], []
    for consl_id in consult_ids:
        source_list = list_by_id[consl_id]
        detail = (details[consl_id].get("data") or {})

        vis_id = value(detail.get("visId")) or value(source_list.get("visId"))
        emp_id = value(detail.get("conslEmpId")) or value(source_list.get("conslEmpId"))
        pgm_id = value(detail.get("pgmId")) or value(source_list.get("pgmId"))
        member_id = mapping["member"].get(vis_id, "")
        teacher_id = mapping["teacher"].get(emp_id, "")
        program_id = mapping["program"].get(pgm_id, "")
        schedule_id = mapping["schedule"].get(consl_id, "")

        for field, source, target in (
            ("SCHEDULE_ID", consl_id, schedule_id),
            ("MEMBER_ID", vis_id, member_id),
            ("TEACHER_ID", emp_id, teacher_id),
            ("PROGRAM_ID", pgm_id, program_id),
        ):
            if not target:
                unmatched.append({"CAREPLE_CONSULT_ID": consl_id, "FIELD": field, "SOURCE_VALUE": source, "MESSAGE": "매핑 없음"})

        source = {"list": source_list, "detail": detail}
        if not schedule_id or not member_id or not teacher_id:
            tobe_all.append({"carepleConsultId": consl_id, "source": source, "excluded": True, "reason": "NOT NULL 매핑 없음"})
            continue

        consult_id = f"CONSULT{CONSULT_ID_LAST_NO + len(consult_rows) + 1:08d}"
        status = value(detail.get("taskStatDivCd")) or value(source_list.get("taskStatDivCd")) or "R"
        consult_dt = date_time(f"{value(detail.get('conslDate')) or value(source_list.get('conslDate'))} {value(detail.get('conslSt')) or value(source_list.get('conslSt'))}")
        complete_dt = later_date_time(detail.get("contLastModDtime"), detail.get("lastModDtime")) if status == "D" else ""
        row = {
            "CONSULT_ID": consult_id,
            "SCHEDULE_ID": schedule_id,
            "COMPANY_ID": COMPANY_ID,
            "MEMBER_ID": member_id,
            "TEACHER_ID": teacher_id,
            "PROGRAM_ID": program_id,
            # AS-IS 프로그램 구분을 그대로 저장: C=상담, A=평가
            "CONSULT_TYPE_CD": value(detail.get("pgmDivCd")) or value(source_list.get("pgmDivCd")),
            "CONSULT_STATUS_CD": status,
            "TITLE": value(detail.get("conslNm")) or value(source_list.get("conslNm")) or value(detail.get("pgmNm")) or value(source_list.get("pgmNm")),
            "COUNSEL_CONTENT": value(detail.get("conslCont")),
            "MEMO": value(detail.get("reqRsn")),
            "CONSULT_DT": consult_dt,
            "COMPLETE_DT": complete_dt,
            "USE_YN": "Y",
            "DELETE_YN": "N",
            "CREATE_DT": date_time(detail.get("regDtime")) or migration_dt,
            "UPDATE_DT": later_date_time(detail.get("lastModDtime"), detail.get("contLastModDtime")),
            "UPDATE_USER_ID": resolve_update_user(detail, mapping),
        }
        consult_rows.append(row)
        consult_map_rows.append({
            "CAREPLE_CONSULT_ID": consl_id, "CONSULT_ID": consult_id, "SCHEDULE_ID": schedule_id,
            "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id, "CAREPLE_EMP_ID": emp_id,
        })
        tobe_all.append({"carepleConsultId": consl_id, "source": source, "tobe": row, "excluded": False})

    validate(consult_rows)
    origin_rows = []
    for consl_id in consult_ids:
        detail = (details[consl_id].get("data") or {})
        origin_rows.append({
            "상담평가ID": consl_id, "이용자": value(detail.get("visNm")), "프로그램": value(detail.get("pgmNm")),
            "담당선생님": value(detail.get("conslEmp")),
            "일시": date_time(f"{detail.get('conslDate', '')} {detail.get('conslSt', '')}"),
            "상태": value(detail.get("taskStatDivNm")), "내용": value(detail.get("conslCont")), "메모": value(detail.get("reqRsn")),
        })

    write_csv(OUTPUT_DIR / "consult_origin.csv", ORIGIN_HEADERS, origin_rows)
    write_csv(OUTPUT_DIR / "consult_db.csv", CONSULT_HEADERS, consult_rows)
    write_csv(OUTPUT_DIR / "consult_id_map.csv", CONSULT_MAP_HEADERS, consult_map_rows)
    write_csv(OUTPUT_DIR / "consult_unmatched_map.csv", UNMATCHED_HEADERS, unmatched)
    (OUTPUT_DIR / "consult_monthly_raw.json").write_text(json.dumps(monthly_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "consult_detail_raw.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "consult_tobe_all.json").write_text(json.dumps(tobe_all, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "list_count": len(consult_ids), "consult_count": len(consult_rows), "unmatched_count": len(unmatched),
        "start_ym": START_YM, "end_ym": END_YM,
    }
    (OUTPUT_DIR / "consult_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("이관 완료: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
