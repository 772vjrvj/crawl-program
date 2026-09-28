"""
Careple 회원 상세 데이터 -> Rapport Codi 회원 관련 SQL 변환기

실행 방법
    python member_main.py

입력 파일
    ./rapport_migration/member_detail_raw.json

생성 파일 (번호 순서대로 실행)
    01_member_user_insert.sql
    02_member_insert.sql
    03_member_phone_insert.sql
    04_member_school_insert.sql
    05_member_status_insert.sql

추가 확인 파일
    member_id_map.json               # 원본 visId -> 신규 MEMBER_ID 매핑
    member_export_summary.json       # 생성 건수, 제외 건수 확인

중요 규칙
    - USER_ID는 원본 visId를 문자열 그대로 사용합니다.
    - MEMBER_ID만 MEMBER00000001부터 새로 채번합니다.
    - 첫 번째 보호자 연락처를 USER 로그인 ID/대표 전화번호로 사용합니다.
    - 보호자 연락처, 학교, 상태 이력은 원본 목록 전체를 별도 테이블로 옮깁니다.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


# -----------------------------------------------------------------------------
# 고정값 및 ID 규칙
# -----------------------------------------------------------------------------
COMPANY_ID = "COMPANY000001"
UPDATE_USER_ID = "172584498380071948"

LOGIN_PASSWORD = "$2a$10$3wtruf9CvYd6WnHdXVJeJuDg1XNBtNEYEglTi1a9EZxBIIoi9lplW"
TEST_PASSWORD = "1234"
DEFAULT_CALENDAR_COLOR = "#3B82F6"

MEMBER_ID_PREFIX = "MEMBER"
MEMBER_PHONE_ID_PREFIX = "MEMBER_P"
MEMBER_SCHOOL_ID_PREFIX = "MEMBER_S"
MEMBER_STATUS_ID_PREFIX = "MEMBER_ST"

MEMBER_ID_START = 1
MEMBER_PHONE_ID_START = 1
MEMBER_SCHOOL_ID_START = 1
MEMBER_STATUS_ID_START = 1


# 테이블 DDL의 컬럼 순서와 동일하게 작성합니다.
USER_COLUMNS = [
    "USER_ID", "COMPANY_ID", "LOGIN_ID", "LOGIN_PW", "TEST_PASSWORD",
    "USER_NM", "BIRTH_DATE", "EMAIL", "ADDR", "CALENDAR_COLOR", "PHONE",
    "WORK_PHONE", "DEPARTMENT_NM", "POSITION_NM", "LOGIN_FAIL_CNT",
    "ACCOUNT_LOCK_YN", "PASSWORD_UPDATE_DT", "PASSWORD_INIT_YN", "USE_YN",
    "DELETE_YN", "LAST_LOGIN_DT", "CREATE_DT", "UPDATE_DT", "LEADER_USER_ID",
    "LEADER_USER_NAME", "EMP_STATUS_CD", "PROFILE_FILE_ID", "SIGNATURE_FILE_ID",
    "STAMP_FILE_ID", "USER_TYPE_CD",
]

MEMBER_COLUMNS = [
    "MEMBER_ID", "MEMBER_NO", "MEMBER_NM", "GENDER_CD", "BIRTH_DT",
    "DISABILITY_TYPE_CD", "DISABILITY_GRADE_CD", "EMAIL", "ADDRESS",
    "INITIAL_CONSULT_DT", "FIRST_VISIT_DT", "INFLOW_PATH_CD", "INFLOW_MEMO",
    "MEMO", "PHOTO_FILE_ID", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
    "COMPANY_ID", "USER_ID", "UPDATE_USER_ID", "APP_USE_YN",
    "APP_LAST_ACCESS_DT", "KAKAO_RECEIVE_YN",
]

MEMBER_PHONE_COLUMNS = [
    "MEMBER_PHONE_ID", "MEMBER_ID", "RELATION_CD", "GUARDIAN_NM", "PHONE_NO",
    "RECEIVE_YN", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]

MEMBER_SCHOOL_COLUMNS = [
    "MEMBER_SCHOOL_ID", "MEMBER_ID", "SCHOOL_NM", "USE_YN", "DELETE_YN",
    "CREATE_DT", "UPDATE_DT",
]

MEMBER_STATUS_COLUMNS = [
    "MEMBER_STATUS_ID", "MEMBER_ID", "STATUS_CD", "STATUS_DT", "USE_YN",
    "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]


def text(value: Any) -> str:
    """None은 빈 문자열로, 나머지는 문자열 그대로 반환합니다."""
    if value is None:
        return ""
    return str(value).strip()


def format_datetime(value: Any) -> str:
    """원본 일시를 yyyy-MM-dd HH:mm:ss 형식으로 통일합니다."""
    raw = text(value)
    if not raw:
        return ""

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed.strftime("%Y-%m-%d" if pattern == "%Y-%m-%d" else "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return raw


def sql_literal(value: Any) -> str:
    """MariaDB INSERT에 사용할 문자열을 만듭니다. 빈 값은 NULL입니다."""
    value_text = text(value)
    if not value_text:
        return "NULL"
    escaped = value_text.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def make_id(prefix: str, sequence: int) -> str:
    """예: MEMBER_P + 1 -> MEMBER_P00000001"""
    return f"{prefix}{sequence:08d}"


def extract_phone(value: Any) -> str:
    """'(모) 010-1234-5678' 같은 값에서 전화번호 표기만 추출합니다.

    하이픈이 있는 원본 표기를 우선 보존합니다. 번호를 찾지 못한 경우 원본 문자열을
    그대로 반환해 데이터가 조용히 사라지는 일을 막습니다.
    """
    raw = text(value)
    if not raw:
        return ""
    match = re.search(r"0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}", raw)
    return match.group(0).replace(" ", "-") if match else raw


def clean_phone(value: Any) -> str:
    """로그인 ID용으로 전화번호에서 숫자만 남깁니다."""
    return re.sub(r"\D", "", extract_phone(value))


def make_unique_login_id(phone: str, source_member_id: str, used_ids: set[str]) -> str:
    """전화번호 중복 시 01, 02를 붙여 유일한 로그인 ID를 만듭니다."""
    base = clean_phone(phone) or source_member_id
    if base not in used_ids:
        used_ids.add(base)
        return base

    suffix = 1
    while True:
        candidate = f"{base}{suffix:02d}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        suffix += 1


def get_member_rows(document: Any) -> List[Dict[str, Any]]:
    """member_detail_raw.json의 {visId: {data: {...}}} 구조를 평탄화합니다."""
    if not isinstance(document, dict):
        raise ValueError("member_detail_raw.json의 최상위 구조는 객체여야 합니다.")

    rows: List[Dict[str, Any]] = []
    for source_member_id, response in document.items():
        if not isinstance(response, dict) or not isinstance(response.get("data"), dict):
            continue
        row = dict(response["data"])
        # 내부 visId가 비어 있더라도 파일의 키가 원본 회원 ID이므로 보완합니다.
        row["visId"] = text(row.get("visId")) or text(source_member_id)
        rows.append(row)
    return rows


def get_contacts(row: Dict[str, Any]) -> List[Dict[str, str]]:
    """보호자 연락처 목록을 안전한 문자열 객체 목록으로 반환합니다."""
    contacts = row.get("visCtcList")
    result: List[Dict[str, str]] = []
    if isinstance(contacts, list):
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            phone = extract_phone(contact.get("ctc"))
            if phone:
                result.append({
                    "relation_cd": text(contact.get("ctcTypeCd")),
                    "phone": phone,
                })
    return result


def to_member_status_cd(source_status_cd: Any) -> str:
    """케어플 회원 상태를 Rapport Codi 상태 코드로 변환합니다.

    W(대기) -> WAIT, E(등록) -> ACTIVE, C(종결) -> LEAVE
    """
    source_code = text(source_status_cd).upper()
    status_map = {
        "W": "WAIT",
        "E": "ACTIVE",
        "C": "LEAVE",
        "WAIT": "WAIT",
        "ACTIVE": "ACTIVE",
        "LEAVE": "LEAVE",
    }
    return status_map.get(source_code, source_code)


def write_batch_insert_sql(
    path: Path,
    table_name: str,
    columns: List[str],
    rows: Iterable[Dict[str, str]],
    batch_size: int = 500,
) -> int:
    """최대 500건씩 묶은 MariaDB 다중 INSERT SQL 파일을 생성합니다."""
    row_list = list(rows)
    quoted_columns = ", ".join(f"`{column}`" for column in columns)

    with path.open("w", encoding="utf-8", newline="\n") as sql_file:
        sql_file.write("-- Generated by member_main.py. Do not edit with Excel.\n")
        sql_file.write("SET NAMES utf8mb4;\nSTART TRANSACTION;\n\n")

        for start_index in range(0, len(row_list), batch_size):
            batch = row_list[start_index:start_index + batch_size]
            sql_file.write(f"INSERT INTO `{table_name}` ({quoted_columns}) VALUES\n")
            lines = []
            for row in batch:
                values = ", ".join(sql_literal(row.get(column)) for column in columns)
                lines.append(f"({values})")
            sql_file.write(",\n".join(lines))
            sql_file.write(";\n\n")

        sql_file.write("COMMIT;\n")
    return len(row_list)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    migration_dir = base_dir / "rapport_migration"
    source_path = migration_dir / "member_detail_raw.json"

    output_paths = {
        "user": migration_dir / "01_member_user_insert.sql",
        "member": migration_dir / "02_member_insert.sql",
        "phone": migration_dir / "03_member_phone_insert.sql",
        "school": migration_dir / "04_member_school_insert.sql",
        "status": migration_dir / "05_member_status_insert.sql",
        "map": migration_dir / "member_id_map.json",
        "summary": migration_dir / "member_export_summary.json",
    }

    if not source_path.exists():
        print(f"입력 파일이 없습니다: {source_path}", file=sys.stderr)
        sys.exit(1)

    with source_path.open("r", encoding="utf-8-sig") as source_file:
        source_rows = get_member_rows(json.load(source_file))

    user_rows: List[Dict[str, str]] = []
    member_rows: List[Dict[str, str]] = []
    phone_rows: List[Dict[str, str]] = []
    school_rows: List[Dict[str, str]] = []
    status_rows: List[Dict[str, str]] = []
    member_id_map: List[Dict[str, str]] = []
    warnings: List[str] = []
    used_source_ids: set[str] = set()
    used_login_ids: set[str] = set()

    for row_number, source in enumerate(source_rows, start=1):
        source_member_id = text(source.get("visId"))
        if not source_member_id:
            warnings.append(f"{row_number}번째 회원: visId가 없어 제외했습니다.")
            continue
        if source_member_id in used_source_ids:
            warnings.append(f"{row_number}번째 회원: 중복 visId({source_member_id})라서 제외했습니다.")
            continue
        used_source_ids.add(source_member_id)

        member_id = make_id(MEMBER_ID_PREFIX, MEMBER_ID_START + len(member_rows))
        # 상세 응답의 regDtime은 현재 전체 회원에서 비어 있습니다.
        # visRegDtime(회원 등록일)을 우선 사용해 USER.CREATE_DT NOT NULL을 보장합니다.
        create_dt = (
            format_datetime(source.get("visRegDtime"))
            or format_datetime(source.get("regDtime"))
            or format_datetime(source.get("lastModDtime"))
        )
        update_dt = format_datetime(source.get("lastModDtime"))
        is_deleted = text(source.get("delYn")).upper() == "Y"
        use_yn = "N" if is_deleted else "Y"
        delete_yn = "Y" if is_deleted else "N"

        contacts = get_contacts(source)
        # 상세 목록의 첫 번째 보호자 연락처가 회원의 대표 연락처/로그인 기준입니다.
        primary_phone = contacts[0]["phone"] if contacts else extract_phone(source.get("mobiNum"))
        login_id = make_unique_login_id(primary_phone, source_member_id, used_login_ids)

        user_rows.append({
            "USER_ID": source_member_id,
            "COMPANY_ID": COMPANY_ID,
            "LOGIN_ID": login_id,
            "LOGIN_PW": LOGIN_PASSWORD,
            "TEST_PASSWORD": TEST_PASSWORD,
            "USER_NM": text(source.get("visNm")),
            "BIRTH_DATE": text(source.get("bdt")),
            "EMAIL": text(source.get("email")),
            "ADDR": text(source.get("addr")),
            "CALENDAR_COLOR": DEFAULT_CALENDAR_COLOR,
            "PHONE": primary_phone,
            "WORK_PHONE": extract_phone(source.get("phoneNum")),
            "DEPARTMENT_NM": "",
            "POSITION_NM": "",
            "LOGIN_FAIL_CNT": "0",
            "ACCOUNT_LOCK_YN": "N",
            "PASSWORD_UPDATE_DT": "",
            "PASSWORD_INIT_YN": "Y",
            "USE_YN": use_yn,
            "DELETE_YN": delete_yn,
            "LAST_LOGIN_DT": "",
            "CREATE_DT": create_dt,
            "UPDATE_DT": update_dt,
            "LEADER_USER_ID": "",
            "LEADER_USER_NAME": "",
            "EMP_STATUS_CD": "WORK",
            "PROFILE_FILE_ID": "",
            "SIGNATURE_FILE_ID": "",
            "STAMP_FILE_ID": "",
            "USER_TYPE_CD": "MEMBER",
        })

        member_rows.append({
            "MEMBER_ID": member_id,
            "MEMBER_NO": text(source.get("regNum")),
            "MEMBER_NM": text(source.get("visNm")),
            "GENDER_CD": text(source.get("genDivCd")),
            "BIRTH_DT": text(source.get("bdt")),
            "DISABILITY_TYPE_CD": text(source.get("disDivCd")),
            "DISABILITY_GRADE_CD": text(source.get("disGrDivCd")),
            "EMAIL": text(source.get("email")),
            "ADDRESS": text(source.get("addr")),
            "INITIAL_CONSULT_DT": format_datetime(source.get("frtMeetDate")),
            "FIRST_VISIT_DT": format_datetime(source.get("frtVisitDate")),
            "INFLOW_PATH_CD": text(source.get("visitPathDivCd")),
            "INFLOW_MEMO": text(source.get("visitPathNote")),
            "MEMO": text(source.get("memo")),
            "PHOTO_FILE_ID": text(source.get("imgFileId")),
            "USE_YN": use_yn,
            "DELETE_YN": delete_yn,
            "CREATE_DT": create_dt,
            "UPDATE_DT": update_dt,
            "COMPANY_ID": COMPANY_ID,
            "USER_ID": source_member_id,
            "UPDATE_USER_ID": UPDATE_USER_ID,
            # AS-IS에는 앱 사용 이력이 없으므로 앱 미사용, 카카오 수신은 허용으로 초기화합니다.
            "APP_USE_YN": "N",
            "APP_LAST_ACCESS_DT": "",
            "KAKAO_RECEIVE_YN": "Y",
        })
        member_id_map.append({
            "SOURCE_MEMBER_ID": source_member_id,
            "MEMBER_ID": member_id,
            "MEMBER_NM": text(source.get("visNm")),
        })

        # 보호자 연락처는 원본에 있는 모든 항목을 MEMBER_PHONE으로 생성합니다.
        for contact in contacts:
            phone_rows.append({
                "MEMBER_PHONE_ID": make_id(MEMBER_PHONE_ID_PREFIX, MEMBER_PHONE_ID_START + len(phone_rows)),
                "MEMBER_ID": member_id,
                "RELATION_CD": contact["relation_cd"],
                "GUARDIAN_NM": "",  # 원본 visCtcList에는 보호자 이름 필드가 없습니다.
                "PHONE_NO": contact["phone"],
                "RECEIVE_YN": "Y",
                "USE_YN": use_yn,
                "DELETE_YN": delete_yn,
                "CREATE_DT": create_dt,
                "UPDATE_DT": update_dt,
            })

        # 학교 정보는 schoolInfoList의 schoolName을 그대로 사용합니다.
        schools = source.get("schoolInfoList")
        if isinstance(schools, list):
            for school in schools:
                if not isinstance(school, dict) or not text(school.get("schoolName")):
                    continue
                school_rows.append({
                    "MEMBER_SCHOOL_ID": make_id(MEMBER_SCHOOL_ID_PREFIX, MEMBER_SCHOOL_ID_START + len(school_rows)),
                    "MEMBER_ID": member_id,
                    "SCHOOL_NM": text(school.get("schoolName")),
                    "USE_YN": use_yn,
                    "DELETE_YN": delete_yn,
                    "CREATE_DT": create_dt,
                    "UPDATE_DT": update_dt,
                })

        # 상태 이력은 statusList의 status/date를 보존합니다.
        statuses = source.get("statusList")
        if isinstance(statuses, list):
            for status in statuses:
                if not isinstance(status, dict) or not text(status.get("status")):
                    continue
                status_rows.append({
                    "MEMBER_STATUS_ID": make_id(MEMBER_STATUS_ID_PREFIX, MEMBER_STATUS_ID_START + len(status_rows)),
                    "MEMBER_ID": member_id,
                    "STATUS_CD": to_member_status_cd(status.get("status")),
                    "STATUS_DT": format_datetime(status.get("date")),
                    "USE_YN": use_yn,
                    "DELETE_YN": delete_yn,
                    "CREATE_DT": create_dt,
                    "UPDATE_DT": update_dt,
                })

    user_count = write_batch_insert_sql(output_paths["user"], "USER", USER_COLUMNS, user_rows)
    member_count = write_batch_insert_sql(output_paths["member"], "MEMBER", MEMBER_COLUMNS, member_rows)
    phone_count = write_batch_insert_sql(output_paths["phone"], "MEMBER_PHONE", MEMBER_PHONE_COLUMNS, phone_rows)
    school_count = write_batch_insert_sql(output_paths["school"], "MEMBER_SCHOOL", MEMBER_SCHOOL_COLUMNS, school_rows)
    status_count = write_batch_insert_sql(output_paths["status"], "MEMBER_STATUS", MEMBER_STATUS_COLUMNS, status_rows)

    with output_paths["map"].open("w", encoding="utf-8") as map_file:
        json.dump(member_id_map, map_file, ensure_ascii=False, indent=2)

    summary = {
        "input_member_count": len(source_rows),
        "user_count": user_count,
        "member_count": member_count,
        "member_phone_count": phone_count,
        "member_school_count": school_count,
        "member_status_count": status_count,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    with output_paths["summary"].open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, ensure_ascii=False, indent=2)

    print(f"완료: USER {user_count}건, MEMBER {member_count}건")
    print(f"MEMBER_PHONE {phone_count}건, MEMBER_SCHOOL {school_count}건, MEMBER_STATUS {status_count}건")
    print("실행 순서: 01 -> 02 -> 03 -> 04 -> 05")


if __name__ == "__main__":
    main()
