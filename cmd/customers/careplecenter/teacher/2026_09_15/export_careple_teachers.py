import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

# 여기만 채우거나 필요하면 번호만 수정하면 됩니다.
COOKIE = "_ga=GA1.2.1541479523.1786462213; SCOUTER=z585fum1bc95et; _gid=GA1.2.1705722455.1789353979; orgNm=%EC%84%9C%EC%9A%B8%EC%84%B1%EB%AA%A8%EC%9D%98%EC%9B%90%EC%95%84%EB%8F%99%EB%B0%9C%EB%8B%AC%ED%81%B4%EB%A6%AC%EB%8B%89%20; empId=172523906005189656; empNm=%EB%B0%95%EB%B3%91%EC%A4%80; tuid=tuid178947511313331054; loginId=rapport1; posn=%EB%8C%80%ED%91%9C%EB%8B%98; managerYn=Y; masterYn=N; sysNtc_sched_172523906005189656_178935060004325211=N; _gat=1; _ga_592EQKNPJ5=GS2.2.s1789480067$o65$g1$t1789485043$j43$l0$h0"
COMPANY_ID = "COMPANY000001"
ROLE_CD = "ROLE_TEACHER"

# DB를 비운 기준입니다. 0이면 TEACHER_ID / 사번이 1부터 생성됩니다.
# USER_ID는 output/member/member_user_db.csv의 마지막 USER_ID 다음 번호부터 자동 생성됩니다.
TEACHER_ID_LAST_NO = 0
USER_ID_LAST_NO = None  # 숫자를 직접 넣으면 member CSV 대신 그 번호 다음부터 생성
EMPLOYEE_NO_LAST_NO = 0

DEFAULT_LOGIN_PW = "$2a$10$3wtruf9CvYd6WnHdXVJeJuDg1XNBtNEYEglTi1a9EZxBIIoi9lplW"  # 1234
TEST_PASSWORD = "1234"

URL = "https://www.careplecenter.com/pcareple/v1/employees/status?searchStatDivCds=all"
MEMBER_OUTPUT_DIR = Path("output") / "member"
OUTPUT_DIR = Path("output") / "teacher"

ORIGIN_HEADERS = [
    "캘린더색상", "이름", "직급(호칭)", "생년월일", "휴대전화번호",
    "업무용전화번호", "로그인계정", "계정상태", "최종로그인일시",
]
TEACHER_HEADERS = [
    "TEACHER_ID", "USER_ID", "COMPANY_ID", "TEACHER_NM", "BIRTH_DATE",
    "POSITION_NM", "EMPLOYEE_NO", "PHONE", "WORK_PHONE", "EMAIL", "ADDR",
    "ROLE_CD", "CALENDAR_COLOR", "EMP_STATUS_CD", "MEMBER_ACCESS_TYPE",
    "RECORD_NOTICE_YN", "SCHEDULE_NOTICE_YN", "CREATE_DT", "UPDATE_DT", "DELETE_YN",
]
MEMBER_HEADERS = [
    "MEMBER_ID", "MEMBER_NO", "MEMBER_NM", "GENDER_CD", "BIRTH_DT", "DISABILITY_TYPE_CD",
    "DISABILITY_GRADE_CD", "EMAIL", "ADDRESS", "INITIAL_CONSULT_DT", "FIRST_VISIT_DT",
    "INFLOW_PATH_CD", "INFLOW_MEMO", "MEMO", "PHOTO_FILE_ID", "USE_YN", "DELETE_YN",
    "CREATE_DT", "UPDATE_DT", "COMPANY_ID", "USER_ID", "UPDATE_USER_ID",
]
USER_HEADERS = [
    "USER_ID", "COMPANY_ID", "LOGIN_ID", "LOGIN_PW", "TEST_PASSWORD", "USER_NM",
    "EMAIL", "PHONE", "DEPARTMENT_NM", "POSITION_NM", "LOGIN_FAIL_CNT",
    "ACCOUNT_LOCK_YN", "PASSWORD_UPDATE_DT", "PASSWORD_INIT_YN", "USE_YN",
    "DELETE_YN", "LAST_LOGIN_DT", "CREATE_DT", "UPDATE_DT", "BIRTH_DATE", "ADDR",
    "CALENDAR_COLOR", "WORK_PHONE", "LEADER_USER_ID", "LEADER_USER_NAME",
    "EMP_STATUS_CD", "PROFILE_FILE_ID", "SIGNATURE_FILE_ID", "STAMP_FILE_ID", "USER_TYPE_CD",
]
EMPLOYEE_MAP_HEADERS = [
    "CAREPLE_EMP_ID", "TEACHER_ID", "USER_ID", "LOGIN_ID", "EMPLOYEE_NM",
]
MEMBER_LINK_HEADERS = [
    "MEMBER_ID", "CAREPLE_LAST_MOD_EMP_ID", "UPDATE_USER_ID", "LINK_STATUS",
]
USER_NOT_NULL_COLUMNS = [
    "USER_ID", "LOGIN_ID", "LOGIN_PW", "USER_NM", "USE_YN", "DELETE_YN", "CREATE_DT",
]


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


def csv_rows(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def validate_not_null(headers, rows, required_columns, table_name):
    """CSV를 쓰기 전에 DB NOT NULL 컬럼이 비어 있지 않은지 확인한다."""
    for row_no, row in enumerate(rows, start=2):
        missing = [column for column in required_columns if not text(row.get(column))]
        if missing:
            raise ValueError(f"{table_name} CSV {row_no}행 NOT NULL 값 누락: {', '.join(missing)}")


def last_id_number(value, prefix):
    value = text(value)
    if not value.startswith(prefix):
        raise ValueError(f"ID 형식을 확인하세요: {value}")
    return int(value[len(prefix):])


def member_user_info():
    """MEMBER USER의 마지막 번호와 로그인 ID를 읽어 USER 충돌을 막는다."""
    member_user_path = MEMBER_OUTPUT_DIR / "member_user_db.csv"
    if not member_user_path.exists():
        raise FileNotFoundError(
            f"{member_user_path} 파일이 없습니다. MEMBER 이관을 먼저 실행하세요."
        )

    rows = csv_rows(member_user_path)
    user_last_no = max(
        (last_id_number(row["USER_ID"], "USER") for row in rows if text(row.get("USER_ID"))),
        default=0,
    )
    login_ids = {text(row.get("LOGIN_ID")) for row in rows if text(row.get("LOGIN_ID"))}
    return user_last_no, login_ids


def phone_login_id(phone, used_login_ids, teacher_no):
    """휴대전화번호에서 '-' 제거. 이미 있으면 01, 02를 붙여 전체 USER에서 유일하게 만든다."""
    base_id = "".join(char for char in text(phone) if char.isdigit())
    if not base_id:
        base_id = f"no_phone{teacher_no:04d}"

    candidate = base_id
    suffix = 1
    while candidate in used_login_ids:
        candidate = f"{base_id}{suffix:02d}"
        suffix += 1

    used_login_ids.add(candidate)
    return candidate


def source_employee_id(employee):
    employee_id = text(employee.get("empId") or employee.get("employeeId") or employee.get("id"))
    if not employee_id:
        raise ValueError(f"Careple 직원 ID(empId)가 없습니다: {employee.get('empNm', '')}")
    return employee_id


def update_member_links(employee_user_map, log):
    """MEMBER 원본 직원 ID를 방금 생성한 선생님 USER_ID로 연결한다."""
    member_path = MEMBER_OUTPUT_DIR / "member_db.csv"
    member_map_path = MEMBER_OUTPUT_DIR / "member_id_map.csv"
    member_link_path = MEMBER_OUTPUT_DIR / "member_update_user_link.csv"

    if not member_path.exists() or not member_map_path.exists():
        raise FileNotFoundError(
            "output/member/member_db.csv 또는 member_id_map.csv가 없습니다. MEMBER 이관을 먼저 실행하세요."
        )

    member_rows = csv_rows(member_path)
    map_rows = csv_rows(member_map_path)
    map_by_member_id = {text(row.get("MEMBER_ID")): row for row in map_rows}
    link_rows = []
    linked_count = 0
    unmatched_count = 0

    for member in member_rows:
        member_id = text(member.get("MEMBER_ID"))
        source = map_by_member_id.get(member_id)
        source_emp_id = text((source or {}).get("LAST_MOD_EMP_ID"))

        if not source_emp_id:
            update_user_id = ""
            link_status = "NO_SOURCE_EMPLOYEE"
        elif source_emp_id not in employee_user_map:
            update_user_id = ""
            link_status = "EMPLOYEE_NOT_FOUND"
            unmatched_count += 1
        else:
            update_user_id = employee_user_map[source_emp_id]
            link_status = "LINKED"
            linked_count += 1

        member["UPDATE_USER_ID"] = update_user_id
        if source is not None:
            source["UPDATE_USER_ID"] = update_user_id
        link_rows.append({
            "MEMBER_ID": member_id,
            "CAREPLE_LAST_MOD_EMP_ID": source_emp_id,
            "UPDATE_USER_ID": update_user_id,
            "LINK_STATUS": link_status,
        })

    write_csv(member_path, MEMBER_HEADERS, member_rows)
    write_csv(member_map_path, [
        "CAREPLE_VIS_ID", "MEMBER_ID", "USER_ID", "LOGIN_ID", "LAST_MOD_EMP_ID", "UPDATE_USER_ID",
    ], map_rows)
    write_csv(member_link_path, MEMBER_LINK_HEADERS, link_rows)
    log(f"MEMBER UPDATE_USER_ID 연결 완료: 연결 {linked_count}건 / 미매칭 {unmatched_count}건")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "teacher_export.log"

    def log(message):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")

    log_path.write_text("", encoding="utf-8")
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("TEACHER 이관 시작")

    member_user_last_no, used_login_ids = member_user_info()
    user_id_last_no = member_user_last_no if USER_ID_LAST_NO is None else USER_ID_LAST_NO
    log(f"MEMBER USER 마지막 번호: {member_user_last_no}")
    log(f"TEACHER USER 시작 번호: {user_id_last_no + 1}")

    tuid = next((x.split("=", 1)[1].strip() for x in COOKIE.split(";") if x.strip().startswith("tuid=")), "")
    headers = {
        "Accept": "*/*",
        "Referer": "https://www.careplecenter.com/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE,
        "tuid": tuid,
    }
    with urlopen(Request(URL, headers=headers), timeout=30) as response:
        employees = (json.loads(response.read().decode("utf-8")).get("data") or {}).get("data") or []
    log(f"Careple 직원 목록 조회 완료: {len(employees)}건")

    paths = {
        "origin": OUTPUT_DIR / "teacher_origin.csv",
        "teacher": OUTPUT_DIR / "teacher_db.csv",
        "user": OUTPUT_DIR / "teacher_user_db.csv",
        "map": OUTPUT_DIR / "employee_id_map.csv",
        "raw": OUTPUT_DIR / "teacher_raw.json",
        "summary": OUTPUT_DIR / "teacher_export_summary.json",
    }
    paths["raw"].write_text(json.dumps(employees, ensure_ascii=False, indent=2), encoding="utf-8")

    origin_rows, teacher_rows, user_rows, employee_map_rows = [], [], [], []
    employee_user_map = {}

    for index, employee in enumerate(employees, start=1):
        careple_emp_id = source_employee_id(employee)
        if careple_emp_id in employee_user_map:
            raise ValueError(f"Careple 직원 ID가 중복되었습니다: {careple_emp_id}")

        teacher_no = TEACHER_ID_LAST_NO + index
        teacher_id = f"TEACHER{teacher_no:08d}"
        user_id = f"USER{user_id_last_no + index:08d}"
        employee_number = f"{EMPLOYEE_NO_LAST_NO + index:04d}"
        color = (employee.get("color") or {}).get("manager", "")
        status = "WORK" if text(employee.get("empStatDivCd")) == "A" else "LEAVE"
        use_yn = "Y" if status == "WORK" else "N"
        phone = text(employee.get("empCtc"))
        login_id = phone_login_id(phone, used_login_ids, teacher_no)
        create_dt = date_time(employee.get("regDtime") or employee.get("lastModDtime")) or migration_dt
        update_dt = date_time(employee.get("lastModDtime"))
        last_login_dt = date_time(employee.get("lastLoginDtime"))

        log(f"변환 {index}/{len(employees)}: {careple_emp_id} -> {teacher_id}, {user_id}")
        origin_rows.append({
            "캘린더색상": color, "이름": employee.get("empNm", ""), "직급(호칭)": employee.get("posn", ""),
            "생년월일": employee.get("bdt", ""), "휴대전화번호": phone, "업무용전화번호": employee.get("empOrgCtc", ""),
            "로그인계정": employee.get("loginId", ""), "계정상태": employee.get("empStatDivNm", ""),
            "최종로그인일시": last_login_dt,
        })
        teacher_rows.append({
            "TEACHER_ID": teacher_id, "USER_ID": user_id, "COMPANY_ID": COMPANY_ID,
            "TEACHER_NM": employee.get("empNm", ""), "BIRTH_DATE": employee.get("bdt", ""),
            "POSITION_NM": employee.get("posn", ""), "EMPLOYEE_NO": employee_number, "PHONE": phone,
            "WORK_PHONE": employee.get("empOrgCtc", ""), "EMAIL": employee.get("email", ""),
            "ADDR": employee.get("addr", ""), "ROLE_CD": ROLE_CD, "CALENDAR_COLOR": color,
            "EMP_STATUS_CD": status, "MEMBER_ACCESS_TYPE": "SELECTED", "RECORD_NOTICE_YN": "Y",
            "SCHEDULE_NOTICE_YN": "Y", "CREATE_DT": create_dt, "UPDATE_DT": update_dt, "DELETE_YN": "N",
        })
        user_rows.append({
            "USER_ID": user_id, "COMPANY_ID": COMPANY_ID, "LOGIN_ID": login_id,
            "LOGIN_PW": DEFAULT_LOGIN_PW, "TEST_PASSWORD": TEST_PASSWORD, "USER_NM": employee.get("empNm", ""),
            "EMAIL": employee.get("email", ""), "PHONE": phone, "DEPARTMENT_NM": employee.get("deptNm", ""),
            "POSITION_NM": employee.get("posn", ""), "LOGIN_FAIL_CNT": "0", "ACCOUNT_LOCK_YN": "N",
            "PASSWORD_UPDATE_DT": create_dt, "PASSWORD_INIT_YN": "Y", "USE_YN": use_yn, "DELETE_YN": "N",
            "LAST_LOGIN_DT": last_login_dt, "CREATE_DT": create_dt, "UPDATE_DT": update_dt,
            "BIRTH_DATE": employee.get("bdt", ""), "ADDR": employee.get("addr", ""),
            "CALENDAR_COLOR": color, "WORK_PHONE": employee.get("empOrgCtc", ""), "LEADER_USER_ID": "",
            "LEADER_USER_NAME": "", "EMP_STATUS_CD": status, "PROFILE_FILE_ID": "", "SIGNATURE_FILE_ID": "",
            "STAMP_FILE_ID": "", "USER_TYPE_CD": "TEACHER",
        })
        employee_map_rows.append({
            "CAREPLE_EMP_ID": careple_emp_id, "TEACHER_ID": teacher_id, "USER_ID": user_id,
            "LOGIN_ID": login_id, "EMPLOYEE_NM": employee.get("empNm", ""),
        })
        employee_user_map[careple_emp_id] = user_id

    validate_not_null(
        TEACHER_HEADERS,
        teacher_rows,
        ["TEACHER_ID", "USER_ID", "COMPANY_ID", "TEACHER_NM", "CREATE_DT"],
        "TEACHER",
    )
    validate_not_null(USER_HEADERS, user_rows, USER_NOT_NULL_COLUMNS, "USER(TEACHER)")

    write_csv(paths["origin"], ORIGIN_HEADERS, origin_rows)
    write_csv(paths["teacher"], TEACHER_HEADERS, teacher_rows)
    write_csv(paths["user"], USER_HEADERS, user_rows)
    write_csv(paths["map"], EMPLOYEE_MAP_HEADERS, employee_map_rows)

    update_member_links(employee_user_map, log)
    summary = {
        "teacher_count": len(teacher_rows),
        "teacher_id_range": [teacher_rows[0]["TEACHER_ID"], teacher_rows[-1]["TEACHER_ID"]] if teacher_rows else [],
        "user_id_range": [user_rows[0]["USER_ID"], user_rows[-1]["USER_ID"]] if user_rows else [],
        "member_user_last_no": member_user_last_no,
        "note": "employee_id_map.csv는 프로그램 담당 선생님 연결에도 사용합니다.",
    }
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"TEACHER CSV 저장 완료: {len(teacher_rows)}건")
    for name, path in paths.items():
        log(f"{name}: {path.resolve()}")
    log("TEACHER 이관 완료")


if __name__ == "__main__":
    main()
