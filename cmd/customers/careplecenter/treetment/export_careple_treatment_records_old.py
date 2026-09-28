import csv
import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = ""
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2027-06"  # 스케줄 이관 범위와 같게 유지
TREATMENT_RECORD_ID_LAST_NO = 0

# False면 이전 목록 캐시를 사용합니다.
# 특정 월만 최신 조회하려면 output/treatment_record/_checkpoint/monthly/2026_09.json만 삭제합니다.
REFRESH_MONTHLY_LIST = False

BASE_URL = "https://www.careplecenter.com"
LIST_URL = BASE_URL + "/pcareple/v1/classes"

MEMBER_DIR = Path("output/member")
TEACHER_DIR = Path("output/teacher")
PROGRAM_DIR = Path("output/program")
SCHEDULE_DIR = Path("output/schedule")
OUTPUT_DIR = Path("output/treatment_record")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"

TREATMENT_HEADERS = [
    "TREATMENT_RECORD_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID", "PROGRAM_ID",
    "TREATMENT_STATUS_CD", "COUNSEL_CONTENT", "RECORD_CONTENT", "SPECIAL_NOTE", "PARENT_COMMENT",
    "NEXT_PLAN", "MEMO", "TREATMENT_DT", "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
TREATMENT_MAP_HEADERS = [
    "CAREPLE_CLASS_ID", "TREATMENT_RECORD_ID", "SCHEDULE_ID",
    "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID",
]
UNMATCHED_HEADERS = ["CAREPLE_CLASS_ID", "FIELD", "SOURCE_VALUE", "MESSAGE"]
ORIGIN_HEADERS = [
    "회기ID", "이용자", "프로그램", "담당선생님", "일시", "상태", "상담내용",
    "기록내용", "특이사항", "보호자전달", "다음계획", "메모",
]


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
    dates = [date_time(item) for item in items if value(item)]
    return max(dates) if dates else ""


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


def checkpoint_path(kind, name):
    safe = "".join(char if char.isalnum() else "_" for char in str(name))
    path = CHECKPOINT_DIR / kind / f"{safe}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path, data):
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
    paths = [
        (MEMBER_DIR / "member_id_map.csv", "MEMBER"),
        (TEACHER_DIR / "employee_id_map.csv", "TEACHER"),
        (PROGRAM_DIR / "program_id_map.csv", "PROGRAM"),
        (SCHEDULE_DIR / "schedule_id_map.csv", "SCHEDULE"),
    ]
    for path, name in paths:
        if not path.exists():
            raise FileNotFoundError(f"{path} 파일이 없습니다. {name} 이관을 먼저 실행하세요.")

    member_rows = read_csv(MEMBER_DIR / "member_id_map.csv")
    teacher_rows = read_csv(TEACHER_DIR / "employee_id_map.csv")
    program_rows = read_csv(PROGRAM_DIR / "program_id_map.csv")
    schedule_rows = read_csv(SCHEDULE_DIR / "schedule_id_map.csv")

    schedule_by_class_id = {}
    for row in schedule_rows:
        if value(row.get("SCHEDULE_TYPE_CD")) != "CLS":
            continue
        schedule_id = value(row.get("SCHEDULE_ID"))
        for class_id in (value(row.get("CAREPLE_EVENT_ID")), value(row.get("CAREPLE_DETAIL_ID"))):
            if not class_id or not schedule_id:
                continue
            previous = schedule_by_class_id.get(class_id)
            if previous and previous != schedule_id:
                raise ValueError(f"회기 원본 일정 ID가 둘 이상 매핑됩니다: {class_id}")
            schedule_by_class_id[class_id] = schedule_id

    return {
        "member": csv_mapping(member_rows, "CAREPLE_VIS_ID", "MEMBER_ID"),
        "teacher": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "TEACHER_ID"),
        "program": csv_mapping(program_rows, "CAREPLE_PROGRAM_ID", "PROGRAM_ID"),
        "schedule": schedule_by_class_id,
    }


def fetch_month_list(year, month):
    ym = f"{year:04d}_{month:02d}"
    path = checkpoint_path("monthly", ym)
    if not REFRESH_MONTHLY_LIST:
        cached = read_json(path)
        if cached is not None:
            return cached

    rows, pages, page_token = [], [], ""
    while True:
        params = {
            "searchSd": f"{year:04d}-{month:02d}-01",
            "searchEd": f"{year:04d}-{month:02d}-{last_day(year, month)}",
            "searchVisDiv": "VIS_ID", "searchVisKeyword": "",
            "searchEmpDiv": "EMP_ID", "searchEmpKeyword": "",
            "searchPgmDiv": "PGM_CAT", "searchPgmKeyword": "",
            "searchStatDivCds": "R D C S F ",
            "orderColumn": "clsDate", "orderDir": "asc", "maxLength": "100",
            "pageToken": page_token, "randid": str(random.random()),
        }
        response = get_json(LIST_URL, params)
        body = response.get("data") or {}
        page_rows = body.get("data") or []
        pages.append(response)
        rows.extend(page_rows)
        page_token = value(body.get("nextPageToken"))
        if not page_token:
            break

    result = {"year": year, "month": month, "pages": pages, "data": rows}
    write_json(path, result)
    return result


def has_treatment_record(source):
    """내용이 없는 일정에는 빈 회기기록을 만들지 않는다. objCont는 원본 JSON에만 남긴다."""
    record = source.get("clsRecord") or {}
    fields = (
        record.get("conslCont"), source.get("cmtCont"), source.get("subjCont"),
        source.get("assmCont"), source.get("planCont"),
        (source.get("reinfTgtClsInfoMap") or {}).get("memo"),
    )
    return any(value(item) for item in fields)


def validate(rows):
    required = ("TREATMENT_RECORD_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID")
    for line_no, row in enumerate(rows, start=2):
        missing = [column for column in required if not value(row.get(column))]
        if missing:
            raise ValueError(f"TREATMENT_RECORD_MASTER CSV {line_no}행 NOT NULL 값 누락: {', '.join(missing)}")


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

    monthly_raw, classes_by_id = [], {}
    for year, month in month_range(START_YM, END_YM):
        result = fetch_month_list(year, month)
        monthly_raw.append(result)
        for row in result.get("data") or []:
            class_id = value(row.get("clsId"))
            if class_id:
                classes_by_id[class_id] = row
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 목록 {year:04d}-{month:02d}: {len(result.get('data') or [])}건")

    treatment_rows, treatment_map_rows, unmatched, tobe_all = [], [], [], []
    for class_id, source in classes_by_id.items():
        if not has_treatment_record(source):
            tobe_all.append({"carepleClassId": class_id, "source": source, "excluded": True, "reason": "회기기록 내용 없음"})
            continue

        vis_id = value(source.get("visId"))
        emp_id = value(source.get("clsMgrEmpId"))
        pgm_id = value(source.get("pgmId"))
        member_id = mapping["member"].get(vis_id, "")
        teacher_id = mapping["teacher"].get(emp_id, "")
        program_id = mapping["program"].get(pgm_id, "")
        schedule_id = mapping["schedule"].get(class_id, "")
        for field, source_id, target in (
            ("SCHEDULE_ID", class_id, schedule_id),
            ("MEMBER_ID", vis_id, member_id),
            ("TEACHER_ID", emp_id, teacher_id),
            ("PROGRAM_ID", pgm_id, program_id),
        ):
            if not target:
                unmatched.append({"CAREPLE_CLASS_ID": class_id, "FIELD": field, "SOURCE_VALUE": source_id, "MESSAGE": "매핑 없음"})

        # PROGRAM_ID는 nullable이나, 추후 추적 가능하도록 매핑 실패 건은 파일에 남긴 채 적재한다.
        if not schedule_id or not member_id or not teacher_id:
            tobe_all.append({"carepleClassId": class_id, "source": source, "excluded": True, "reason": "NOT NULL 매핑 없음"})
            continue

        record = source.get("clsRecord") or {}
        status = value(source.get("clsStatDivCd")) or "R"
        treatment_dt = date_time(f"{value(source.get('clsDate'))} {value(source.get('clsSt'))}")
        complete_dt = later_date_time(source.get("soapLastModDtime"), source.get("lastModDtime")) if status == "D" else ""
        treatment_id = f"TREATMENT_RECORD{TREATMENT_RECORD_ID_LAST_NO + len(treatment_rows) + 1:08d}"
        row = {
            "TREATMENT_RECORD_ID": treatment_id,
            "SCHEDULE_ID": schedule_id,
            "COMPANY_ID": COMPANY_ID,
            "MEMBER_ID": member_id,
            "TEACHER_ID": teacher_id,
            "PROGRAM_ID": program_id,
            "TREATMENT_STATUS_CD": status,
            "COUNSEL_CONTENT": value(record.get("conslCont")),
            "RECORD_CONTENT": value(source.get("cmtCont")),
            "SPECIAL_NOTE": value(source.get("assmCont")),
            "PARENT_COMMENT": value(source.get("subjCont")),
            "NEXT_PLAN": value(source.get("planCont")),
            "MEMO": value((source.get("reinfTgtClsInfoMap") or {}).get("memo")),
            "TREATMENT_DT": treatment_dt,
            "COMPLETE_DT": complete_dt,
            "USE_YN": "Y",
            "DELETE_YN": "N",
            "CREATE_DT": date_time(source.get("regDtime")) or migration_dt,
            "UPDATE_DT": later_date_time(source.get("lastModDtime"), source.get("soapLastModDtime")),
        }
        treatment_rows.append(row)
        treatment_map_rows.append({
            "CAREPLE_CLASS_ID": class_id, "TREATMENT_RECORD_ID": treatment_id, "SCHEDULE_ID": schedule_id,
            "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id, "CAREPLE_EMP_ID": emp_id,
        })
        tobe_all.append({"carepleClassId": class_id, "source": source, "tobe": row, "excluded": False})

    validate(treatment_rows)
    origin_rows = []
    for class_id, source in classes_by_id.items():
        record = source.get("clsRecord") or {}
        origin_rows.append({
            "회기ID": class_id, "이용자": value(source.get("visNm")), "프로그램": value(source.get("pgmNm")),
            "담당선생님": value(source.get("clsMgrEmp")),
            "일시": date_time(f"{value(source.get('clsDate'))} {value(source.get('clsSt'))}"),
            "상태": value(source.get("clsStatDivNm")), "상담내용": value(record.get("conslCont")),
            "기록내용": value(source.get("cmtCont")), "특이사항": value(source.get("assmCont")),
            "보호자전달": value(source.get("subjCont")), "다음계획": value(source.get("planCont")),
            "메모": value((source.get("reinfTgtClsInfoMap") or {}).get("memo")),
        })

    write_csv(OUTPUT_DIR / "treatment_record_origin.csv", ORIGIN_HEADERS, origin_rows)
    write_csv(OUTPUT_DIR / "treatment_record_db.csv", TREATMENT_HEADERS, treatment_rows)
    write_csv(OUTPUT_DIR / "treatment_record_id_map.csv", TREATMENT_MAP_HEADERS, treatment_map_rows)
    write_csv(OUTPUT_DIR / "treatment_record_unmatched_map.csv", UNMATCHED_HEADERS, unmatched)
    (OUTPUT_DIR / "treatment_record_asis_raw.json").write_text(json.dumps(monthly_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "treatment_record_tobe_all.json").write_text(json.dumps(tobe_all, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "class_count": len(classes_by_id), "treatment_record_count": len(treatment_rows),
        "unmatched_count": len(unmatched), "start_ym": START_YM, "end_ym": END_YM,
    }
    (OUTPUT_DIR / "treatment_record_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("이관 완료: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
