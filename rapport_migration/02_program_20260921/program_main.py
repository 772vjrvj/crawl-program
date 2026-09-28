"""
Careple 프로그램 데이터 -> Rapport Codi PROGRAM 관련 SQL 변환기

실행 방법
    python program_main.py

입력 파일
    ./rapport_migration/program_raw.json

생성 파일
    ./rapport_migration/01_program_insert.sql
    ./rapport_migration/02_program_price_insert.sql
    ./rapport_migration/03_program_teacher_insert.sql
    ./rapport_migration/program_id_map.json
    ./rapport_migration/program_export_summary.json

실행 순서
    1. 선생님 변환 SQL(TEACHER)을 먼저 DB에 실행합니다.
    2. 이 프로그램이 만든 01, 02, 03 SQL을 번호 순서로 실행합니다.

중요
    - pgmId와 empId는 긴 숫자처럼 보여도 절대 숫자로 바꾸지 않습니다.
    - PROGRAM_TEACHER는 TEACHER.USER_ID = 원본 empId가 실제로 있는 경우에만 INSERT됩니다.
    - Excel로 SQL/JSON 파일을 열어 저장하지 마세요.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


# -----------------------------------------------------------------------------
# 고정값 및 ID 생성 규칙
# -----------------------------------------------------------------------------
COMPANY_ID = "COMPANY000001"

# PROGRAM_ID는 신규 채번하지 않고, 원본 pgmId를 그대로 사용합니다.
PROGRAM_PRICE_ID_PREFIX = "PROGRAM_PRICE"
PROGRAM_TEACHER_ID_PREFIX = "PROGRAM_TEACHER"

PROGRAM_PRICE_ID_START = 1
PROGRAM_TEACHER_ID_START = 1


PROGRAM_COLUMNS = [
    "PROGRAM_ID", "PROGRAM_NM", "PROGRAM_DIV_CD", "PROGRAM_TYPE_CD",
    "PROGRAM_CLS_DIV_CD", "PROGRAM_PL_DIV_CD", "PROGRAM_STOP_YN",
    "DURATION_MIN", "MAX_STUDENT_CNT", "DESCRIPTION", "USE_YN",
    "DELETE_YN", "CREATE_DT", "UPDATE_DT", "DEFAULT_SESSION_CNT",
    "COMPANY_ID",
]

PROGRAM_PRICE_COLUMNS = [
    "PROGRAM_PRICE_ID", "PROGRAM_ID", "PRICE", "DEFAULT_YN", "USE_YN",
    "DELETE_YN", "CREATE_DT", "UPDATE_DT", "COMPANY_ID",
]

PROGRAM_TEACHER_COLUMNS = [
    "PROGRAM_TEACHER_ID", "PROGRAM_ID", "TEACHER_ID", "USE_YN",
    "DELETE_YN", "CREATE_DT", "UPDATE_DT", "COMPANY_ID",
]


def text(value: Any) -> str:
    """None은 빈 문자열로, 나머지는 문자열 그대로 반환합니다."""
    if value is None:
        return ""
    return str(value).strip()


def format_datetime(value: Any) -> str:
    """yyyy-MM-dd HH:mm 또는 yyyy-MM-dd HH:mm:ss 값을 DB 일시 형식으로 맞춥니다."""
    raw = text(value)
    if not raw:
        return ""

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return raw


def sql_literal(value: Any) -> str:
    """MariaDB SQL 문자열 값으로 변환합니다. 빈 값은 NULL로 출력합니다."""
    value_text = text(value)
    if not value_text:
        return "NULL"

    # 작은따옴표와 역슬래시가 SQL 문자열을 깨지 않도록 처리합니다.
    escaped = value_text.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def make_id(prefix: str, sequence: int) -> str:
    """예: make_id('PROGRAM_PRICE', 1) -> PROGRAM_PRICE00000001"""
    return f"{prefix}{sequence:08d}"


def parse_list(value: Any) -> List[Any]:
    """JSON 배열 또는 이미 변환된 배열을 항상 list로 반환합니다."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def get_program_rows(document: Any) -> List[Dict[str, Any]]:
    """원본이 배열이거나 API 응답(data.data) 전체인 경우를 모두 지원합니다."""
    if isinstance(document, list):
        return [row for row in document if isinstance(row, dict)]

    if isinstance(document, dict):
        data = document.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [row for row in data["data"] if isinstance(row, dict)]
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]

    raise ValueError("program_raw.json의 최상위 구조는 배열 또는 data.data 배열이어야 합니다.")


def get_source_teacher_ids(row: Dict[str, Any]) -> List[str]:
    """pgmPicList 또는 pgmPic에서 원본 empId 목록을 중복 없이 읽습니다."""
    result: List[str] = []
    seen: set[str] = set()

    # API가 pgmPicList를 주면 이름까지 확인된 객체 목록이므로 우선 사용합니다.
    teacher_list = row.get("pgmPicList")
    if isinstance(teacher_list, list):
        candidates = [item.get("empId") for item in teacher_list if isinstance(item, dict)]
    else:
        candidates = parse_list(row.get("pgmPic"))

    for candidate in candidates:
        emp_id = text(candidate)
        if emp_id and emp_id not in seen:
            seen.add(emp_id)
            result.append(emp_id)
    return result


def get_prices(row: Dict[str, Any]) -> List[str]:
    """pgmPriceList 우선, 없으면 pgmPrice JSON 문자열에서 가격 목록을 가져옵니다."""
    source_prices = row.get("pgmPriceList")
    if not isinstance(source_prices, list):
        source_prices = parse_list(row.get("pgmPrice"))

    prices = []
    for price in source_prices:
        price_text = text(price)
        if price_text:
            prices.append(price_text)
    return prices


def write_batch_insert_sql(
        path: Path,
        table_name: str,
        columns: List[str],
        rows: Iterable[Dict[str, str]],
        batch_size: int = 500,
) -> int:
    """PROGRAM, PROGRAM_PRICE용 다중 VALUES INSERT SQL 파일을 만듭니다."""
    row_list = list(rows)
    quoted_columns = ", ".join(f"`{column}`" for column in columns)

    with path.open("w", encoding="utf-8", newline="\n") as sql_file:
        sql_file.write("-- Generated by program_main.py. Do not edit with Excel.\n")
        sql_file.write("SET NAMES utf8mb4;\nSTART TRANSACTION;\n\n")

        for start_index in range(0, len(row_list), batch_size):
            batch = row_list[start_index:start_index + batch_size]
            sql_file.write(f"INSERT INTO `{table_name}` ({quoted_columns}) VALUES\n")
            values = []
            for row in batch:
                values.append(
                    "(" + ", ".join(sql_literal(row.get(column)) for column in columns) + ")"
                )
            sql_file.write(",\n".join(values))
            sql_file.write(";\n\n")

        sql_file.write("COMMIT;\n")
    return len(row_list)


def write_program_teacher_sql(path: Path, rows: List[Dict[str, str]]) -> int:
    """선생님이 실제 DB에 있을 때만 PROGRAM_TEACHER를 넣는 INSERT ... SELECT SQL을 만듭니다."""
    columns = ", ".join(f"`{column}`" for column in PROGRAM_TEACHER_COLUMNS)

    with path.open("w", encoding="utf-8", newline="\n") as sql_file:
        sql_file.write("-- Generated by program_main.py. Do not edit with Excel.\n")
        sql_file.write("-- TEACHER.USER_ID가 원본 empId와 일치할 때만 INSERT됩니다.\n")
        sql_file.write("SET NAMES utf8mb4;\nSTART TRANSACTION;\n\n")

        for row in rows:
            sql_file.write(f"INSERT INTO `PROGRAM_TEACHER` ({columns})\n")
            sql_file.write("SELECT\n")
            sql_file.write(
                "    " + ",\n    ".join([
                    sql_literal(row["PROGRAM_TEACHER_ID"]),
                    sql_literal(row["PROGRAM_ID"]),
                    "T.`TEACHER_ID`",
                    sql_literal(row["USE_YN"]),
                    sql_literal(row["DELETE_YN"]),
                    sql_literal(row["CREATE_DT"]),
                    sql_literal(row["UPDATE_DT"]),
                    sql_literal(row["COMPANY_ID"]),
                ]) + "\n"
            )
            sql_file.write("FROM `TEACHER` T\n")
            sql_file.write(
                f"WHERE T.`USER_ID` = {sql_literal(row['SOURCE_EMP_ID'])}\n"
                f"  AND T.`COMPANY_ID` = {sql_literal(COMPANY_ID)}\n"
                "  AND COALESCE(T.`DELETE_YN`, 'N') <> 'Y'\n"
                "LIMIT 1;\n\n"
            )

        sql_file.write("COMMIT;\n")
    return len(rows)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    migration_dir = base_dir / "rapport_migration"
    source_path = migration_dir / "program_raw.json"
    program_sql_path = migration_dir / "01_program_insert.sql"
    price_sql_path = migration_dir / "02_program_price_insert.sql"
    teacher_sql_path = migration_dir / "03_program_teacher_insert.sql"
    map_path = migration_dir / "program_id_map.json"
    summary_path = migration_dir / "program_export_summary.json"

    if not source_path.exists():
        print(f"입력 파일이 없습니다: {source_path}", file=sys.stderr)
        sys.exit(1)

    with source_path.open("r", encoding="utf-8-sig") as source_file:
        source_rows = get_program_rows(json.load(source_file))

    program_rows: List[Dict[str, str]] = []
    price_rows: List[Dict[str, str]] = []
    program_teacher_rows: List[Dict[str, str]] = []
    program_id_map: List[Dict[str, str]] = []
    warnings: List[str] = []
    used_source_program_ids: set[str] = set()

    for row_number, source in enumerate(source_rows, start=1):
        source_program_id = text(source.get("pgmId"))
        if not source_program_id:
            warnings.append(f"{row_number}번째 프로그램: pgmId가 없어 제외했습니다.")
            continue
        if source_program_id in used_source_program_ids:
            warnings.append(f"{row_number}번째 프로그램: 중복 pgmId({source_program_id})라서 제외했습니다.")
            continue
        used_source_program_ids.add(source_program_id)

        # PROGRAM_ID는 원본 키를 문자열 그대로 보존합니다.
        program_id = source_program_id
        stop_yn = text(source.get("pgmStopYn")) or "N"
        use_yn = "N" if stop_yn.upper() == "Y" else "Y"
        create_dt = format_datetime(source.get("regDtime"))
        update_dt = format_datetime(source.get("lastModDtime"))

        # pgmPer는 원본의 프로그램 회기/기간 값이므로 기본 회기수 컬럼으로 옮깁니다.
        program_rows.append({
            "PROGRAM_ID": program_id,
            "PROGRAM_NM": text(source.get("pgmNm")),
            "PROGRAM_DIV_CD": text(source.get("pgmDivCd")),
            "PROGRAM_TYPE_CD": text(source.get("pgmCatDivCd")),
            "PROGRAM_CLS_DIV_CD": text(source.get("pgmClsDivCd")),
            "PROGRAM_PL_DIV_CD": text(source.get("pgmPlDivCd")),
            "PROGRAM_STOP_YN": stop_yn,
            "DURATION_MIN": "",
            "MAX_STUDENT_CNT": "",
            "DESCRIPTION": text(source.get("pgmDesc")),
            "USE_YN": use_yn,
            "DELETE_YN": "N",
            "CREATE_DT": create_dt,
            "UPDATE_DT": update_dt,
            "DEFAULT_SESSION_CNT": text(source.get("pgmPer")),
            "COMPANY_ID": COMPANY_ID,
        })
        program_id_map.append({
            "SOURCE_PROGRAM_ID": source_program_id,
            "PROGRAM_ID": program_id,
            "PROGRAM_NM": text(source.get("pgmNm")),
        })

        # 가격 목록의 기본 가격과 일치하는 첫 번째 가격만 DEFAULT_YN=Y로 설정합니다.
        default_price = text(source.get("pgmDefaultPrice"))
        default_assigned = False
        for price in get_prices(source):
            is_default = price == default_price and not default_assigned
            if is_default:
                default_assigned = True
            price_rows.append({
                "PROGRAM_PRICE_ID": make_id(
                    PROGRAM_PRICE_ID_PREFIX,
                    PROGRAM_PRICE_ID_START + len(price_rows),
                    ),
                "PROGRAM_ID": program_id,
                "PRICE": price,
                "DEFAULT_YN": "Y" if is_default else "N",
                "USE_YN": use_yn,
                "DELETE_YN": "N",
                "CREATE_DT": create_dt,
                "UPDATE_DT": update_dt,
                "COMPANY_ID": COMPANY_ID,
            })

        # 원본 담당자 empId를 TEACHER.USER_ID에서 찾아서 있을 때만 INSERT하도록 만듭니다.
        for source_emp_id in get_source_teacher_ids(source):
            program_teacher_rows.append({
                "PROGRAM_TEACHER_ID": make_id(
                    PROGRAM_TEACHER_ID_PREFIX,
                    PROGRAM_TEACHER_ID_START + len(program_teacher_rows),
                    ),
                "PROGRAM_ID": program_id,
                "SOURCE_EMP_ID": source_emp_id,
                "USE_YN": use_yn,
                "DELETE_YN": "N",
                "CREATE_DT": create_dt,
                "UPDATE_DT": update_dt,
                "COMPANY_ID": COMPANY_ID,
            })

    program_count = write_batch_insert_sql(program_sql_path, "PROGRAM", PROGRAM_COLUMNS, program_rows)
    price_count = write_batch_insert_sql(price_sql_path, "PROGRAM_PRICE", PROGRAM_PRICE_COLUMNS, price_rows)
    program_teacher_count = write_program_teacher_sql(teacher_sql_path, program_teacher_rows)

    with map_path.open("w", encoding="utf-8") as map_file:
        json.dump(program_id_map, map_file, ensure_ascii=False, indent=2)

    summary = {
        "input_program_count": len(source_rows),
        "program_count": program_count,
        "program_price_count": price_count,
        "program_teacher_candidate_count": program_teacher_count,
        "warning_count": len(warnings),
        "warnings": warnings,
        "files": {
            "program_sql": str(program_sql_path),
            "program_price_sql": str(price_sql_path),
            "program_teacher_sql": str(teacher_sql_path),
            "program_id_map": str(map_path),
        },
    }
    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, ensure_ascii=False, indent=2)

    print(f"완료: PROGRAM {program_count}건, PROGRAM_PRICE {price_count}건")
    print(f"PROGRAM_TEACHER 후보: {program_teacher_count}건")
    print("실행 순서: 01_program_insert.sql -> 02_program_price_insert.sql -> 03_program_teacher_insert.sql")


if __name__ == "__main__":
    main()
