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
MEMBER_ID_LAST_NO = 0
MEMBER_PHONE_ID_LAST_NO = 0
MEMBER_SCHOOL_ID_LAST_NO = 0
MEMBER_STATUS_ID_LAST_NO = 0
USER_ID_LAST_NO = 0

DEFAULT_LOGIN_PW = "$2a$10$3wtruf9CvYd6WnHdXVJeJuDg1XNBtNEYEglTi1a9EZxBIIoi9lplW"  # 1234
TEST_PASSWORD = "1234"
MEMBER_CALENDAR_COLOR = "#3B82F6"

# MEMBER를 먼저 적재하므로 아직 없는 선생님 USER_ID는 연결하지 않습니다.
# 원본 직원 ID는 member_id_map.csv에 보관하며, 선생님 이관 후 그 파일로 연결합니다.
DEFAULT_UPDATE_USER_ID = ""

LIST_URL = "https://www.careplecenter.com/pcareple/v2/visitors/.datatables"
DETAIL_URL = "https://www.careplecenter.com/pcareple/v2/visitors/{vis_id}"
PAGE_SIZE = 100
OUTPUT_DIR = Path("output") / "member"

ORIGIN_HEADERS = [
    "이름", "성별", "생년월일", "회원번호", "휴대전화번호", "전화번호", "주소", "이메일",
    "장애유형", "장애등급", "초기상담일", "최초방문일", "상태", "유입경로", "유입메모", "메모", "최종수정일시",
]
MEMBER_HEADERS = [
    "MEMBER_ID", "MEMBER_NO", "MEMBER_NM", "GENDER_CD", "BIRTH_DT", "DISABILITY_TYPE_CD",
    "DISABILITY_GRADE_CD", "EMAIL", "ADDRESS", "INITIAL_CONSULT_DT", "FIRST_VISIT_DT",
    "INFLOW_PATH_CD", "INFLOW_MEMO", "MEMO", "PHOTO_FILE_ID", "USE_YN", "DELETE_YN",
    "CREATE_DT", "UPDATE_DT", "COMPANY_ID", "USER_ID", "UPDATE_USER_ID",
]
PHONE_HEADERS = [
    "MEMBER_PHONE_ID", "MEMBER_ID", "RELATION_CD", "GUARDIAN_NM", "PHONE_NO", "RECEIVE_YN",
    "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
SCHOOL_HEADERS = [
    "MEMBER_SCHOOL_ID", "MEMBER_ID", "SCHOOL_NM", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
STATUS_HEADERS = [
    "MEMBER_STATUS_ID", "MEMBER_ID", "STATUS_CD", "STATUS_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
USER_HEADERS = [
    "USER_ID", "COMPANY_ID", "LOGIN_ID", "LOGIN_PW", "TEST_PASSWORD", "USER_NM", "EMAIL", "PHONE",
    "DEPARTMENT_NM", "POSITION_NM", "LOGIN_FAIL_CNT", "ACCOUNT_LOCK_YN", "PASSWORD_UPDATE_DT",
    "PASSWORD_INIT_YN", "USE_YN", "DELETE_YN", "LAST_LOGIN_DT", "CREATE_DT", "UPDATE_DT", "BIRTH_DATE",
    "ADDR", "CALENDAR_COLOR", "WORK_PHONE", "LEADER_USER_ID", "LEADER_USER_NAME", "EMP_STATUS_CD",
    "PROFILE_FILE_ID", "SIGNATURE_FILE_ID", "STAMP_FILE_ID", "USER_TYPE_CD",
]
MAP_HEADERS = [
    "CAREPLE_VIS_ID", "MEMBER_ID", "USER_ID", "LOGIN_ID", "LAST_MOD_EMP_ID", "UPDATE_USER_ID",
]

DISABILITY_MAP = {
    "미응답": "NONE", "지적장애": "INTELLECTUAL", "자폐성장애": "AUTISM", "언어장애": "LANGUAGE",
    "발달장애": "DEVELOPMENT", "지체장애": "PHYSICAL", "뇌병변장애": "BRAIN_LESION",
    "시각장애": "VISUAL", "청각장애": "HEARING", "정신장애": "MENTAL", "신장장애": "KIDNEY",
    "심장장애": "HEART", "호흡기장애": "RESPIRATORY",
}
STATUS_MAP = {"W": "WAIT", "E": "ACTIVE", "C": "LEAVE"}
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


def date_only(value):
    value = date_time(value)
    return value[:10] if value else ""


def inflow_code(name):
    name = text(name)
    if "검색" in name or "네이버" in name:
        return "INTERNET"
    if "지인" in name or "병원" in name or "의뢰" in name:
        return "REFERRAL"
    if "홍보" in name:
        return "PROMOTION"
    return "OTHER" if name else ""


def request_json(url, params=None):
    query = urlencode(params or [], doseq=True)
    request_url = f"{url}?{query}" if query else url
    request = Request(request_url, headers=HEADERS)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def contact_list(detail):
    contacts = detail.get("visCtcList") or []
    if contacts:
        return contacts
    mobile = text(detail.get("mobiNum"))
    phone = "".join(char for char in mobile if char.isdigit())
    relation = "M" if "(모)" in mobile else "F" if "(부)" in mobile else ""
    return [{"ctcTypeCd": relation, "ctc": phone}] if phone else []


def school_name(school):
    if isinstance(school, str):
        return school
    return text(school.get("schoolNm") or school.get("schoolName") or school.get("nm"))


def preferred_guardian_phone(contacts):
    """엄마(M) -> 아빠(F) -> 첫 연락처 순으로 로그인용 보호자 연락처를 고른다."""
    for relation in ("M", "F"):
        for contact in contacts:
            if text(contact.get("ctcTypeCd")) == relation and text(contact.get("ctc")):
                return text(contact.get("ctc"))
    return text((contacts[0] if contacts else {}).get("ctc"))


def phone_login_id(phone, used_login_ids, member_no):
    """010-1234-5678 -> 01012345678, 중복이면 01 / 02를 붙인다."""
    base_id = "".join(char for char in phone if char.isdigit())
    if not base_id:
        base_id = f"no_phone{member_no:04d}"
    count = used_login_ids.get(base_id, 0)
    used_login_ids[base_id] = count + 1
    return base_id if count == 0 else f"{base_id}{count:02d}"


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def validate_not_null(headers, rows, required_columns, table_name):
    """CSV를 쓰기 전에 DB NOT NULL 컬럼이 비어 있지 않은지 확인한다."""
    indexes = {name: headers.index(name) for name in required_columns}
    for row_no, row in enumerate(rows, start=2):  # 헤더 다음 첫 데이터 행은 2행
        missing = [name for name, index in indexes.items() if not text(row[index])]
        if missing:
            raise ValueError(f"{table_name} CSV {row_no}행 NOT NULL 값 누락: {', '.join(missing)}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "member_export.log"

    def log(message):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")

    log_path.write_text("", encoding="utf-8")
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("MEMBER 이관 시작")
    log(f"결과 경로: {OUTPUT_DIR.resolve()}")
    log("ID 시작값: MEMBER/USER/MEMBER_PHONE/MEMBER_SCHOOL/MEMBER_STATUS = 1")

    # 쿠키의 tuid도 헤더에 같이 전달
    global HEADERS
    tuid = next((x.split("=", 1)[1].strip() for x in COOKIE.split(";") if x.strip().startswith("tuid=")), "")
    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Referer": "https://www.careplecenter.com/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE,
        "tuid": tuid,
    }

    page_responses = []
    list_rows = []
    start = 0
    page = 1
    while True:
        log(f"목록 조회 {page}페이지 시작: start={start}")
        params = [
            ("dt", ""), ("searchVisDiv", "ALL"), ("searchVisKeyword", ""),
            ("searchStatCdList[0]", "W"), ("searchStatCdList[1]", "E"), ("searchStatCdList[2]", "C"),
            ("draw", "1"), ("start", str(start)), ("length", str(PAGE_SIZE)),
            ("orderColumn", "8"), ("orderDir", "desc"), ("randid", str(random.random())),
        ]
        response = request_json(LIST_URL, params)
        page_responses.append(response)
        rows = (response.get("data") or {}).get("data") or []
        log(f"목록 조회 {page}페이지 완료: {len(rows)}건")
        if not rows:
            break
        list_rows.extend(rows)
        start += len(rows)
        page += 1

    detail_responses = {}
    unique_vis_ids = []
    for row in list_rows:
        vis_id = text(row.get("visId"))
        if vis_id and vis_id not in detail_responses:
            unique_vis_ids.append(vis_id)
            detail_responses[vis_id] = None

    total = len(unique_vis_ids)
    log(f"목록 {len(list_rows)}건, 상세 대상 {total}건")
    for index, vis_id in enumerate(unique_vis_ids, start=1):
        log(f"상세 조회 {index}/{total}: visId={vis_id}")
        detail_responses[vis_id] = request_json(
            DETAIL_URL.format(vis_id=vis_id), [("randid", str(random.random()))]
        )

    # 파일명은 고정합니다. 실행할 때마다 같은 파일을 새 결과로 교체합니다.
    paths = {
        "origin": OUTPUT_DIR / "member_origin.csv",
        "member": OUTPUT_DIR / "member_db.csv",
        "phone": OUTPUT_DIR / "member_phone_db.csv",
        "school": OUTPUT_DIR / "member_school_db.csv",
        "status": OUTPUT_DIR / "member_status_db.csv",
        "user": OUTPUT_DIR / "member_user_db.csv",
        "map": OUTPUT_DIR / "member_id_map.csv",
        "list_raw": OUTPUT_DIR / "member_list_raw.json",
        "detail_raw": OUTPUT_DIR / "member_detail_raw.json",
        "summary": OUTPUT_DIR / "member_export_summary.json",
    }
    paths["list_raw"].write_text(
        json.dumps({"pages": page_responses, "data": list_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["detail_raw"].write_text(
        json.dumps(detail_responses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("목록/상세 원본 JSON 저장 완료")

    origin_rows, member_rows, phone_rows = [], [], []
    school_rows, status_rows, user_rows, map_rows = [], [], [], []
    phone_seq = MEMBER_PHONE_ID_LAST_NO
    school_seq = MEMBER_SCHOOL_ID_LAST_NO
    status_seq = MEMBER_STATUS_ID_LAST_NO
    used_login_ids = {}

    for index, list_row in enumerate(list_rows, start=1):
        vis_id = text(list_row.get("visId"))
        detail = (detail_responses[vis_id].get("data") or {})
        member_no = MEMBER_ID_LAST_NO + index
        member_id = f"MEMBER{member_no:08d}"
        user_id = f"USER{USER_ID_LAST_NO + index:08d}"
        delete_yn = "Y" if text(detail.get("delYn")) == "Y" else "N"
        use_yn = "N" if delete_yn == "Y" else "Y"
        create_dt = date_time(
            detail.get("visRegDtime") or list_row.get("visRegDtime") or detail.get("lastModDtime")
        ) or migration_dt
        update_dt = date_time(detail.get("lastModDtime"))
        contacts = contact_list(detail)
        guardian_phone = preferred_guardian_phone(contacts)
        login_id = phone_login_id(guardian_phone, used_login_ids, member_no)
        disability = DISABILITY_MAP.get(text(detail.get("disDivNm")), text(detail.get("disDivCd")))
        initial_dt = date_only(detail.get("frtMeetDate") or detail.get("scheduledFrtMeetDate"))
        update_user_id = DEFAULT_UPDATE_USER_ID

        log(f"변환 {index}/{len(list_rows)}: {vis_id} -> {member_id}, {user_id}")
        origin_rows.append([
            detail.get("visNm", ""), detail.get("genDivNm", ""), detail.get("bdt", ""),
            detail.get("regNum", ""), detail.get("mobiNum", ""), detail.get("phoneNum", ""),
            detail.get("addr", ""), detail.get("email", ""), detail.get("disDivNm", ""),
            detail.get("disGrDivNm", ""), initial_dt, date_only(detail.get("frtVisitDate")),
            ", ".join(text(x.get("statusNm")) for x in detail.get("statusList") or []),
            detail.get("visitPathDivNm", ""), detail.get("visitPathNote", ""), detail.get("memo", ""), update_dt,
        ])
        member_rows.append([
            member_id, detail.get("regNum", ""), detail.get("visNm", ""), detail.get("genDivCd", ""),
            detail.get("bdt", ""), disability, detail.get("disGrDivNm") or detail.get("disGrDivCd") or "",
            detail.get("email", ""), detail.get("addr", ""), initial_dt, date_only(detail.get("frtVisitDate")),
            inflow_code(detail.get("visitPathDivNm")), detail.get("visitPathNote", ""), detail.get("memo", ""), "",
            use_yn, delete_yn, create_dt, update_dt, COMPANY_ID, user_id, update_user_id,
                                               ])
        user_rows.append([
            user_id, COMPANY_ID, login_id, DEFAULT_LOGIN_PW, TEST_PASSWORD, detail.get("visNm", ""),
            detail.get("email", ""), guardian_phone, "", "", "0", "N", create_dt, "Y", use_yn, delete_yn,
            "", create_dt, update_dt, detail.get("bdt", ""), detail.get("addr", ""), MEMBER_CALENDAR_COLOR,
            "", "", "", "WORK", "", "", "", "MEMBER",
        ])
        map_rows.append([
            vis_id, member_id, user_id, login_id, text(detail.get("lastModEmpId")), update_user_id,
        ])

        for contact in contacts:
            phone_seq += 1
            phone_rows.append([
                f"MEMBER_P{phone_seq:08d}", member_id, contact.get("ctcTypeCd", ""),
                contact.get("guardianNm", ""), contact.get("ctc", ""), "Y", use_yn, delete_yn, create_dt, update_dt,
            ])
        for school in detail.get("schoolInfoList") or []:
            name = school_name(school)
            if name:
                school_seq += 1
                school_rows.append([
                    f"MEMBER_S{school_seq:08d}", member_id, name, use_yn, delete_yn, create_dt, update_dt,
                ])
        statuses = detail.get("statusList") or [{"status": "W", "date": date_only(create_dt)}]
        for status in statuses:
            status_seq += 1
            source_status = text(status.get("status"))
            status_rows.append([
                f"MEMBER_ST{status_seq:08d}", member_id, STATUS_MAP.get(source_status, source_status),
                date_only(status.get("date") or create_dt), use_yn, delete_yn, create_dt, update_dt,
            ])

    validate_not_null(MEMBER_HEADERS, member_rows, ["MEMBER_ID", "MEMBER_NM"], "MEMBER")
    validate_not_null(USER_HEADERS, user_rows, USER_NOT_NULL_COLUMNS, "USER(MEMBER)")
    validate_not_null(PHONE_HEADERS, phone_rows, ["MEMBER_PHONE_ID", "MEMBER_ID"], "MEMBER_PHONE")
    validate_not_null(SCHOOL_HEADERS, school_rows, ["MEMBER_SCHOOL_ID", "MEMBER_ID"], "MEMBER_SCHOOL")
    validate_not_null(STATUS_HEADERS, status_rows, ["MEMBER_STATUS_ID", "MEMBER_ID"], "MEMBER_STATUS")

    write_csv(paths["origin"], ORIGIN_HEADERS, origin_rows)
    write_csv(paths["member"], MEMBER_HEADERS, member_rows)
    write_csv(paths["phone"], PHONE_HEADERS, phone_rows)
    write_csv(paths["school"], SCHOOL_HEADERS, school_rows)
    write_csv(paths["status"], STATUS_HEADERS, status_rows)
    write_csv(paths["user"], USER_HEADERS, user_rows)
    write_csv(paths["map"], MAP_HEADERS, map_rows)

    summary = {
        "member_count": len(member_rows),
        "user_count": len(user_rows),
        "phone_count": len(phone_rows),
        "school_count": len(school_rows),
        "status_count": len(status_rows),
        "member_id_range": [member_rows[0][0], member_rows[-1][0]] if member_rows else [],
        "user_id_range": [user_rows[0][0], user_rows[-1][0]] if user_rows else [],
        "note": "MEMBER.UPDATE_USER_ID는 선생님 이관 전에는 비워둡니다. 원본 lastModEmpId는 member_id_map.csv에 보관됩니다.",
    }
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log(
        "CSV 저장 완료: "
        f"MEMBER {len(member_rows)} / USER {len(user_rows)} / "
        f"PHONE {len(phone_rows)} / SCHOOL {len(school_rows)} / STATUS {len(status_rows)}"
    )
    log("MEMBER 이관 완료")
    for name, path in paths.items():
        log(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()
