import csv
import json
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = "_ga=GA1.2.1541479523.1786462213; SCOUTER=z585fum1bc95et; _gid=GA1.2.1705722455.1789353979; orgNm=%EC%84%9C%EC%9A%B8%EC%84%B1%EB%AA%A8%EC%9D%98%EC%9B%90%EC%95%84%EB%8F%99%EB%B0%9C%EB%8B%AC%ED%81%B4%EB%A6%AC%EB%8B%89%20; empId=172523906005189656; empNm=%EB%B0%95%EB%B3%91%EC%A4%80; tuid=tuid178947511313331054; loginId=rapport1; posn=%EB%8C%80%ED%91%9C%EB%8B%98; managerYn=Y; masterYn=N; sysNtc_sched_172523906005189656_178935060004325211=N; _gat=1; _ga_592EQKNPJ5=GS2.2.s1789480067$o65$g1$t1789485043$j43$l0$h0"
COMPANY_ID = "COMPANY000001"

# DB를 비운 기준입니다. 0이면 ID가 1부터 생성됩니다.
PROGRAM_ID_LAST_NO = 0
PROGRAM_PRICE_ID_LAST_NO = 0
PROGRAM_TEACHER_ID_LAST_NO = 0

PROGRAM_URL = "https://www.careplecenter.com/pcareple/v1/programs/status/A"
TEACHER_OUTPUT_DIR = Path("output") / "teacher"
OUTPUT_DIR = Path("output") / "program"

ORIGIN_HEADERS = [
    "구분", "프로그램유형", "프로그램", "방식", "장소", "담당선생님", "가격", "기본가격", "사용여부", "등록일시", "수정일시",
]
PROGRAM_HEADERS = [
    "PROGRAM_ID", "PROGRAM_NM", "PROGRAM_DIV_CD", "PROGRAM_TYPE_CD", "PROGRAM_CLS_DIV_CD",
    "PROGRAM_PL_DIV_CD", "PROGRAM_STOP_YN", "DURATION_MIN", "MAX_STUDENT_CNT", "DESCRIPTION",
    "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "DEFAULT_SESSION_CNT", "COMPANY_ID",
]
PRICE_HEADERS = [
    "PROGRAM_PRICE_ID", "PROGRAM_ID", "PRICE", "DEFAULT_YN", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "COMPANY_ID",
]
PROGRAM_TEACHER_HEADERS = [
    "PROGRAM_TEACHER_ID", "PROGRAM_ID", "TEACHER_ID", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "COMPANY_ID",
]
PROGRAM_MAP_HEADERS = ["CAREPLE_PROGRAM_ID", "PROGRAM_ID", "PROGRAM_NM"]

# AS-IS 분류가 비어 있는 상담/기타 프로그램의 TO-BE 유형 보정값
TYPE_FALLBACK = {"C": "09", "E": "99"}


def text(value):
    return str(value or "").strip()


def date_time(value):
    value = text(value).replace("T", " ").replace("Z", "")
    if not value:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(f"날짜 형식을 확인하세요: {value}")


def request_json(url, params):
    request_url = f"{url}?{urlencode(params)}"
    request = Request(request_url, headers=HEADERS)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def csv_rows(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def validate_not_null(rows, required_columns, table_name):
    for row_no, row in enumerate(rows, start=2):
        missing = [column for column in required_columns if not text(row.get(column))]
        if missing:
            raise ValueError(f"{table_name} CSV {row_no}행 NOT NULL 값 누락: {', '.join(missing)}")


def teacher_id_map():
    """선생님 이관 결과를 단일 기준으로 사용한다. 직원 API 순서는 절대 사용하지 않는다."""
    path = TEACHER_OUTPUT_DIR / "employee_id_map.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} 파일이 없습니다. TEACHER 이관을 먼저 실행하세요.")

    mapping = {}
    for row in csv_rows(path):
        employee_id = text(row.get("CAREPLE_EMP_ID"))
        teacher_id = text(row.get("TEACHER_ID"))
        if not employee_id or not teacher_id:
            raise ValueError("employee_id_map.csv의 CAREPLE_EMP_ID 또는 TEACHER_ID가 비어 있습니다.")
        if employee_id in mapping:
            raise ValueError(f"employee_id_map.csv에 Careple 직원 ID가 중복되었습니다: {employee_id}")
        mapping[employee_id] = teacher_id
    return mapping


def price_list(program):
    prices = program.get("pgmPriceList") or []
    if not prices:
        try:
            prices = json.loads(program.get("pgmPrice") or "[]")
        except json.JSONDecodeError:
            prices = []
    return [text(price).replace(",", "") for price in prices]


def teacher_names(program):
    return ", ".join(text(teacher.get("empNm")) for teacher in program.get("pgmPicList") or [])


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "program_export.log"

    def log(message):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")

    log_path.write_text("", encoding="utf-8")
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("PROGRAM 이관 시작")

    teacher_map = teacher_id_map()
    log(f"선생님 매핑 로드 완료: {len(teacher_map)}건")

    global HEADERS
    tuid = next((item.split("=", 1)[1].strip() for item in COOKIE.split(";") if item.strip().startswith("tuid=")), "")
    HEADERS = {
        "Accept": "*/*",
        "Referer": "https://www.careplecenter.com/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE,
        "tuid": tuid,
    }
    program_response = request_json(PROGRAM_URL, [("randid", str(random.random()))])
    programs = (program_response.get("data") or {}).get("data") or []
    log(f"Careple 프로그램 목록 조회 완료: {len(programs)}건")

    paths = {
        "origin": OUTPUT_DIR / "program_origin.csv",
        "program": OUTPUT_DIR / "program_db.csv",
        "price": OUTPUT_DIR / "program_price_db.csv",
        "teacher": OUTPUT_DIR / "program_teacher_db.csv",
        "map": OUTPUT_DIR / "program_id_map.csv",
        "raw": OUTPUT_DIR / "program_raw.json",
        "summary": OUTPUT_DIR / "program_export_summary.json",
    }
    paths["raw"].write_text(json.dumps(program_response, ensure_ascii=False, indent=2), encoding="utf-8")

    origin_rows, program_rows, price_rows = [], [], []
    program_teacher_rows, program_map_rows = [], []
    price_no = PROGRAM_PRICE_ID_LAST_NO
    program_teacher_no = PROGRAM_TEACHER_ID_LAST_NO

    for index, program in enumerate(programs, start=1):
        program_id = f"PROGRAM{PROGRAM_ID_LAST_NO + index:08d}"
        careple_program_id = text(program.get("pgmId") or program.get("programId"))
        create_dt = date_time(program.get("regDtime") or program.get("lastModDtime")) or migration_dt
        update_dt = date_time(program.get("lastModDtime"))
        prices = price_list(program)
        default_price = text(program.get("pgmDefaultPrice")).replace(",", "")
        program_div = text(program.get("pgmDivCd"))
        program_type = text(program.get("pgmCatDivCd")) or TYPE_FALLBACK.get(program_div, "")
        program_name = text(program.get("pgmNm"))
        log(f"변환 {index}/{len(programs)}: {careple_program_id or program_name} -> {program_id}")

        origin_rows.append({
            "구분": program.get("pgmDivNm", ""), "프로그램유형": program.get("pgmCatDivNm", ""),
            "프로그램": program_name, "방식": program.get("pgmClsDivNm", ""), "장소": program.get("pgmPlDivNm", ""),
            "담당선생님": teacher_names(program), "가격": " | ".join(prices), "기본가격": default_price,
            "사용여부": "중단" if text(program.get("pgmStopYn")) == "Y" else "정상",
            "등록일시": create_dt, "수정일시": update_dt,
        })
        program_rows.append({
            "PROGRAM_ID": program_id, "PROGRAM_NM": program_name, "PROGRAM_DIV_CD": program_div,
            "PROGRAM_TYPE_CD": program_type, "PROGRAM_CLS_DIV_CD": text(program.get("pgmClsDivCd")) or "01",
            "PROGRAM_PL_DIV_CD": text(program.get("pgmPlDivCd")) or "01",
            "PROGRAM_STOP_YN": text(program.get("pgmStopYn")) or "N", "DURATION_MIN": text(program.get("pgmPer")),
            "MAX_STUDENT_CNT": "", "DESCRIPTION": program.get("pgmDesc", ""), "USE_YN": "Y", "DELETE_YN": "N",
            "CREATE_DT": create_dt, "UPDATE_DT": update_dt, "DEFAULT_SESSION_CNT": "1", "COMPANY_ID": COMPANY_ID,
        })
        program_map_rows.append({
            "CAREPLE_PROGRAM_ID": careple_program_id, "PROGRAM_ID": program_id, "PROGRAM_NM": program_name,
        })

        for price in prices:
            price_no += 1
            price_rows.append({
                "PROGRAM_PRICE_ID": f"PROGRAM_P{price_no:08d}", "PROGRAM_ID": program_id, "PRICE": price,
                "DEFAULT_YN": "Y" if price == default_price else "N", "USE_YN": "Y", "DELETE_YN": "N",
                "CREATE_DT": create_dt, "UPDATE_DT": update_dt, "COMPANY_ID": COMPANY_ID,
            })

        for teacher in program.get("pgmPicList") or []:
            employee_id = text(teacher.get("empId"))
            teacher_id = teacher_map.get(employee_id)
            if not teacher_id:
                raise ValueError(
                    f"선생님 매핑 실패: {teacher.get('empNm', '')} / Careple empId={employee_id}"
                )
            program_teacher_no += 1
            program_teacher_rows.append({
                "PROGRAM_TEACHER_ID": f"PROGRAM_T{program_teacher_no:08d}", "PROGRAM_ID": program_id,
                "TEACHER_ID": teacher_id, "USE_YN": "Y", "DELETE_YN": "N",
                "CREATE_DT": create_dt, "UPDATE_DT": update_dt, "COMPANY_ID": COMPANY_ID,
            })

    validate_not_null(
        program_rows,
        ["PROGRAM_ID", "PROGRAM_NM", "PROGRAM_STOP_YN", "USE_YN", "DELETE_YN", "CREATE_DT"],
        "PROGRAM",
    )
    validate_not_null(
        price_rows,
        ["PROGRAM_PRICE_ID", "PROGRAM_ID", "PRICE", "DEFAULT_YN", "USE_YN", "DELETE_YN", "CREATE_DT"],
        "PROGRAM_PRICE",
    )
    validate_not_null(
        program_teacher_rows,
        ["PROGRAM_TEACHER_ID", "PROGRAM_ID", "TEACHER_ID", "USE_YN", "DELETE_YN", "CREATE_DT"],
        "PROGRAM_TEACHER",
    )

    write_csv(paths["origin"], ORIGIN_HEADERS, origin_rows)
    write_csv(paths["program"], PROGRAM_HEADERS, program_rows)
    write_csv(paths["price"], PRICE_HEADERS, price_rows)
    write_csv(paths["teacher"], PROGRAM_TEACHER_HEADERS, program_teacher_rows)
    write_csv(paths["map"], PROGRAM_MAP_HEADERS, program_map_rows)
    summary = {
        "program_count": len(program_rows), "price_count": len(price_rows),
        "program_teacher_count": len(program_teacher_rows),
        "teacher_map_count": len(teacher_map),
    }
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"CSV 저장 완료: PROGRAM {len(program_rows)} / PRICE {len(price_rows)} / PROGRAM_TEACHER {len(program_teacher_rows)}")
    for name, path in paths.items():
        log(f"{name}: {path.resolve()}")
    log("PROGRAM 이관 완료")


if __name__ == "__main__":
    main()
