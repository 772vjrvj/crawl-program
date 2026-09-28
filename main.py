import json
from pathlib import Path

import pymysql


# =========================
# DB 접속 정보 수정
# =========================
DB_CONFIG = {
    "host": "modukidscenter.cafe24.com",
    "port": 3306,
    "user": "modukidscenter",
    "password": "kidscenter12!",
    "database": "modukidscenter",
    "charset": "utf8mb4",
    "autocommit": False,
}

BASE_DIR = Path(__file__).resolve().parent
JSON_FILE = BASE_DIR / "last_mig" / "SCHEDULE_MASTER_updated.json"


COLUMNS = [
    "SCHEDULE_ID",
    "SCHEDULE_GROUP_ID",
    "COMPANY_ID",
    "PROGRAM_ID",
    "MEMBER_ID",
    "TEACHER_ID",
    "MEMO",
    "SCHEDULE_CLASS_CD",
    "SCHEDULE_TYPE_CD",
    "SCHEDULE_STATUS_CD",
    "START_DT",
    "END_DT",
    "ALL_DAY_YN",
    "PLACE",
    "QUICK_INPUT_TEXT",
    "COUNSEL_INPUT_TYPE_CD",
    "PRICE",
    "CENTER_SHARE_YN",
    "COMPLETE_DT",
    "USE_YN",
    "DELETE_YN",
    "CREATE_DT",
    "UPDATE_DT",
    "UPDATE_USER_ID",
    "MEMBER_PROGRAM_ID",
    "REPEAT_TEMPLATE_YN",
]

COLUMN_SQL = ", ".join(f"`{column}`" for column in COLUMNS)
PLACEHOLDERS = ", ".join(["%s"] * len(COLUMNS))

INSERT_SQL = f"""
INSERT INTO `SCHEDULE_MASTER` (
    {COLUMN_SQL}
) VALUES (
    {PLACEHOLDERS}
)
"""


def main():
    if not JSON_FILE.exists():
        raise FileNotFoundError(f"JSON 파일이 없습니다: {JSON_FILE}")

    with JSON_FILE.open("r", encoding="utf-8-sig") as file:
        rows = json.load(file)

    print(f"JSON 데이터: {len(rows)}건")

    connection = pymysql.connect(**DB_CONFIG)

    success_count = 0
    fail_count = 0

    try:
        with connection.cursor() as cursor:
            for index, row in enumerate(rows, start=1):
                try:
                    company_id = row.get("COMPANY_ID")

                    if not company_id:
                        print(f"[{index}] COMPANY_ID 누락")
                        fail_count += 1
                        continue

                    values = [
                        row.get(column)
                        for column in COLUMNS
                    ]

                    cursor.execute(INSERT_SQL, values)
                    success_count += 1

                    if index % 500 == 0:
                        connection.commit()
                        print(f"[진행상황] {index}/{len(rows)}건 처리")

                except Exception as error:
                    connection.rollback()
                    fail_count += 1

                    print(
                        f"[실패] {index}번째 데이터 "
                        f"SCHEDULE_ID={row.get('SCHEDULE_ID')}"
                    )
                    print(f"       사유: {error}")

            connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    print()
    print("===== 마이그레이션 완료 =====")
    print(f"전체 데이터: {len(rows)}건")
    print(f"성공: {success_count}건")
    print(f"실패: {fail_count}건")


if __name__ == "__main__":
    main()