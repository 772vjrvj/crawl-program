"""Careple 일정 JSON -> Rapport Codi SQL 변환.

입력 폴더(기본 rapport_migration)
  schedule_class_raw.json, schedule_counsel_raw.json,
  schedule_etc_raw.json, schedule_monthlyplan_raw.json

ID 규칙: SCHEDULE_ID와 PROGRAM_ID는 AS-IS ID 그대로 사용한다.
MEMBER_PROGRAM_ID만 AS-IS에 없으므로 MP00000001부터 생성한다.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

COMPANY_ID = "COMPANY000001"
INPUT_FILES = {
    "CLS": "schedule_class_raw.json",
    "CSL": "schedule_counsel_raw.json",
    "ETC": "schedule_etc_raw.json",
    "PLAN": "schedule_monthlyplan_raw.json",
}
# 기존 수집 파이썬과 동일하게 실행 위치 아래 output/schedule에 결과물을 만든다.
DEFAULT_INPUT_DIR = Path("rapport_migration")
DEFAULT_OUTPUT_DIR = Path("output/schedule")


def value(item: Any) -> str | None:
    """AS-IS ID가 숫자로 바뀌지 않도록 항상 문자열로만 다룬다."""
    if item is None:
        return None
    result = str(item).strip()
    return result or None


def sql(item: Any) -> str:
    item = value(item)
    if item is None:
        return "NULL"
    return "'" + item.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_number(item: Any) -> str:
    item = value(item)
    if item is None:
        return "NULL"
    item = item.replace(",", "")
    return item if re.fullmatch(r"-?\d+", item) else "NULL"


def to_int(item: Any) -> int:
    """금액/회기 수가 빈 값 또는 소수 문자열이어도 변환 전체가 중단되지 않게 한다."""
    item = value(item)
    if item is None:
        return 0
    try:
        return int(float(item.replace(",", "")))
    except ValueError:
        return 0


def dt(item: Any) -> str | None:
    item = value(item)
    if item is None:
        return None
    item = item.replace("T", " ").replace("Z", "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", item):
        return item + ":00"
    return item


def date_time(day: Any, clock: Any) -> str | None:
    day, clock = value(day), value(clock)
    return dt(f"{day} {clock}") if day and clock else None


def month_no(year: Any, month: Any, day: Any = None) -> int | None:
    year, month = value(year), value(month)
    if year and month and year.isdigit() and month.isdigit():
        return int(year) * 12 + int(month)
    day = value(day)
    if day and re.match(r"^\d{4}-\d{2}", day):
        return int(day[:4]) * 12 + int(day[5:7])
    return None


def load_map(path: Path) -> OrderedDict[str, dict[str, Any]]:
    """{AS-IS ID: {data: 실제상세데이터}} JSON을 읽는다."""
    with path.open("r", encoding="utf-8-sig") as file:
        source = json.load(file, object_pairs_hook=OrderedDict)
    if not isinstance(source, dict):
        raise ValueError(f"{path.name}: 최상위 값은 JSON 객체여야 합니다.")
    return OrderedDict(
        (str(raw_id), response["data"])
        for raw_id, response in source.items()
        if isinstance(response, dict) and isinstance(response.get("data"), dict)
    )


def raw_schedule_id(kind: str, raw_id: str, data: dict[str, Any]) -> str:
    field = {"CLS": "clsId", "CSL": "conslId", "ETC": "schedId"}[kind]
    return value(data.get(field)) or raw_id


def member_program_key(kind: str, data: dict[str, Any]) -> tuple[str, str, str] | None:
    """MP 구분 기준: 이용자 + 프로그램 + 담당선생님."""
    member = value(data.get("visId"))
    program = value(data.get("pgmId"))
    teacher = value(data.get("clsMgrEmpId" if kind == "CLS" else "conslEmpId")) or ""
    return (member, program, teacher) if member and program else None


def schedule_source(kind: str, schedule_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """CLS/CSL 일정도 MP 생성을 위한 원본 월 데이터로 포함한다."""
    key = member_program_key(kind, data)
    day = value(data.get("clsDate" if kind == "CLS" else "conslDate"))
    ym = month_no(None, None, day)
    if key is None or ym is None:
        return None
    price_map = data.get("pgmInfoMap" if kind == "CLS" else "priceInfoMap") or {}
    return {
        "key": key, "month": ym, "day": day, "schedule": (kind, schedule_id), "plan_id": None,
        "plan": None, "price": price_map.get("pgmPrice"), "create_dt": dt(data.get("regDtime")),
        "update_dt": dt(data.get("lastModDtime")),
    }


def plan_source(raw_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    member, program = value(data.get("visId")), value(data.get("pgmId"))
    teacher = value(data.get("srvPicId")) or ""
    ym = month_no(data.get("srvYear"), data.get("srvMonth"))
    if not member or not program or ym is None:
        return None
    return {
        "key": (member, program, teacher), "month": ym, "day": None, "schedule": None,
        "plan_id": value(data.get("monthSrvplId")) or raw_id, "plan": data,
        "price": (data.get("pgmInfoMap") or {}).get("pgmPrice"),
        "create_dt": dt(data.get("regDtime")), "update_dt": dt(data.get("lastModDtime")),
    }


def price(plan_source_item: dict[str, Any], name: str, default: str = "0") -> str:
    info = (plan_source_item.get("plan") or {}).get("priceInfoMap") or {}
    return value(info.get(name)) or default


def make_member_programs(
        class_data: OrderedDict[str, dict[str, Any]],
        counsel_data: OrderedDict[str, dict[str, Any]],
        plan_data: OrderedDict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], str]]:
    """연속 월 단위로 MP를 만들고 (유형, AS-IS 일정ID) -> MP ID 맵을 만든다."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for kind, data_map in (("CLS", class_data), ("CSL", counsel_data)):
        for raw_id, data in data_map.items():
            schedule_id = raw_schedule_id(kind, raw_id, data)
            item = schedule_source(kind, schedule_id, data)
            if item:
                grouped[item["key"]].append(item)
    for raw_id, data in plan_data.items():
        item = plan_source(raw_id, data)
        if item:
            grouped[item["key"]].append(item)

    records: list[dict[str, Any]] = []
    schedule_to_mp: dict[tuple[str, str], str] = {}

    for key in sorted(grouped):
        by_month: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in grouped[key]:
            by_month[item["month"]].append(item)

        # 중간 월이 비어야만 재등록으로 보고 다음 MP를 만든다.
        episodes: list[list[dict[str, Any]]] = []
        episode: list[dict[str, Any]] = []
        previous_month: int | None = None
        for ym in sorted(by_month):
            if previous_month is not None and ym - previous_month > 1:
                episodes.append(episode)
                episode = []
            episode.extend(by_month[ym])
            previous_month = ym
        if episode:
            episodes.append(episode)

        for episode in episodes:
            mp_id = f"MP{len(records) + 1:08d}"
            member_user_id, program_id, teacher_user_id = key
            plans = [item for item in episode if item["plan"] is not None]
            dates = [item["day"] for item in episode if item["day"]]
            classes = [cls for item in plans for cls in ((item["plan"].get("clsList") or []))]
            dates.extend(value(cls.get("clsDate")) for cls in classes if value(cls.get("clsDate")))
            first, last = (plans[0], plans[-1]) if plans else (episode[0], episode[-1])
            paid = sum(to_int(price(item, "payClsTime")) for item in plans)
            used = sum(1 for cls in classes if value(cls.get("clsStatDivCd")) == "D")
            memo = next((price(item, "memo", "") for item in plans if price(item, "memo", "")), None)
            records.append({
                "id": mp_id, "member_user_id": member_user_id, "program_id": program_id,
                "teacher_user_id": teacher_user_id or None,
                "program_price_id": value((first["plan"] or {}).get("pgmPriceId")),
                "total_count": str(paid), "used_count": str(used), "remain_count": str(max(paid - used, 0)),
                "unit_price": price(first, "totalPgmPrice", value(first.get("price")) or "0"),
                "total_amount": str(sum(to_int(price(item, "totalPayPgmPrice")) for item in plans)),
                "discount_amount": str(sum(to_int(price(item, "discountPrice")) for item in plans)),
                "pay_amount": str(sum(to_int(price(item, "totalPayPgmPrice")) for item in plans)),
                "start_dt": min(dates) if dates else None, "end_dt": max(dates) if dates else None,
                "status": "ACTIVE", "memo": memo, "create_dt": first["create_dt"], "update_dt": last["update_dt"],
            })
            for item in episode:
                if item["schedule"]:
                    schedule_to_mp[item["schedule"]] = mp_id
    return records, schedule_to_mp


def member_program_sql(row: dict[str, Any]) -> str:
    columns = [
        "MEMBER_PROGRAM_ID", "COMPANY_ID", "MEMBER_ID", "PROGRAM_ID", "EMP_ID", "PROGRAM_PRICE_ID",
        "TOTAL_COUNT", "USED_COUNT", "REMAIN_COUNT", "UNIT_PRICE", "TOTAL_AMOUNT", "DISCOUNT_AMOUNT",
        "PAY_AMOUNT", "START_DT", "END_DT", "STATUS_CD", "MEMO", "USE_YN", "DELETE_YN",
        "CREATE_DT", "UPDATE_DT", "DISCOUNT_MEMO",
    ]
    values = [
        sql(row["id"]), sql(COMPANY_ID), "M.`MEMBER_ID`", sql(row["program_id"]), "T.`TEACHER_ID`",
        sql(row["program_price_id"]), sql(row["total_count"]), sql(row["used_count"]), sql(row["remain_count"]),
        sql(row["unit_price"]), sql(row["total_amount"]), sql(row["discount_amount"]), sql(row["pay_amount"]),
        sql(row["start_dt"]), sql(row["end_dt"]), sql(row["status"]), sql(row["memo"]), "'Y'", "'N'",
        sql(row["create_dt"]), sql(row["update_dt"]), "NULL",
    ]
    return (
            f"INSERT INTO `MEMBER_PROGRAM` ({', '.join(f'`{name}`' for name in columns)})\nSELECT\n    "
            + ",\n    ".join(values)
            + "\nFROM `USER` MU\n"
              "INNER JOIN `MEMBER` M ON M.`USER_ID` = MU.`USER_ID`"
            + f" AND M.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(M.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `USER` TU ON TU.`USER_ID` = " + sql(row["teacher_user_id"])
            + f" AND TU.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(TU.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `TEACHER` T ON T.`USER_ID` = TU.`USER_ID`"
            + f" AND T.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(T.`DELETE_YN`, 'N') = 'N'\n"
              "WHERE MU.`USER_ID` = " + sql(row["member_user_id"])
            + f" AND MU.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(MU.`DELETE_YN`, 'N') = 'N';\n"
    )


def to_schedule_row(kind: str, schedule_id: str, data: dict[str, Any], mp_id: str | None) -> dict[str, Any] | None:
    if kind == "CLS":
        member, program, teacher = value(data.get("visId")), value(data.get("pgmId")), value(data.get("clsMgrEmpId"))
        start, end = date_time(data.get("clsDate"), data.get("clsSt")), date_time(data.get("clsDate"), data.get("clsEt"))
        status = value(data.get("clsStatDivCd")) or "R"
        memo, quick, price = value((data.get("reinfTgtClsInfoMap") or {}).get("memo")), None, (data.get("pgmInfoMap") or {}).get("pgmPrice")
        create, update, updater, place = dt(data.get("regDtime")), dt(data.get("lastModDtime")), value(data.get("regEmpId")), value(data.get("pl"))
    elif kind == "CSL":
        member, program, teacher = value(data.get("visId")), value(data.get("pgmId")), value(data.get("conslEmpId"))
        start, end = date_time(data.get("conslDate"), data.get("conslSt")), date_time(data.get("conslDate"), data.get("conslEt"))
        status = value(data.get("taskStatDivCd")) or "R"
        memo, quick, price = value(data.get("conslCont")), value(data.get("reqRsn")), (data.get("priceInfoMap") or {}).get("pgmPrice")
        create, update, updater, place = dt(data.get("regDtime")), dt(data.get("lastModDtime")), value(data.get("regEmpId")), None
    else:
        member, program, teacher = None, None, value(data.get("schedOwnEmpId"))
        start, end = date_time(data.get("schedSd"), data.get("schedSt")), date_time(data.get("schedEd"), data.get("schedEt"))
        status, memo, quick, price, create, update, updater, place = "R", value(data.get("schedNm")), None, None, None, None, None, value(data.get("pl"))
    if start is None or end is None:
        return None
    return {
        "id": schedule_id, "kind": kind, "member": member, "program": program, "teacher": teacher, "mp_id": mp_id,
        "memo": memo, "status": status, "start": start, "end": end, "quick": quick, "price": price,
        "create": create, "update": update, "updater": updater, "place": place,
    }


def schedule_sql(row: dict[str, Any]) -> str:
    columns = [
        "SCHEDULE_ID", "SCHEDULE_GROUP_ID", "COMPANY_ID", "PROGRAM_ID", "MEMBER_ID", "TEACHER_ID", "MEMO",
        "SCHEDULE_CLASS_CD", "SCHEDULE_TYPE_CD", "SCHEDULE_STATUS_CD", "START_DT", "END_DT", "ALL_DAY_YN",
        "PLACE", "QUICK_INPUT_TEXT", "COUNSEL_INPUT_TYPE_CD", "PRICE", "CENTER_SHARE_YN", "COMPLETE_DT",
        "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID", "MEMBER_PROGRAM_ID", "REPEAT_TEMPLATE_YN",
    ]
    values = [
        sql(row["id"]), "NULL", sql(COMPANY_ID), sql(row["program"]), "M.`MEMBER_ID`", "T.`TEACHER_ID`", sql(row["memo"]),
        "'NORMAL'", sql(row["kind"]), sql(row["status"]), sql(row["start"]), sql(row["end"]), "'N'", sql(row["place"]),
        sql(row["quick"]), "NULL", sql_number(row["price"]), "'N'", sql(row["end"] if row["status"] == "D" else None),
        "'Y'", "'N'", sql(row["create"]), sql(row["update"]), sql(row["updater"]), "MP.`MEMBER_PROGRAM_ID`", "'N'",
    ]
    return (
            f"INSERT INTO `SCHEDULE_MASTER` ({', '.join(f'`{name}`' for name in columns)})\nSELECT\n    "
            + ",\n    ".join(values)
            + "\nFROM DUAL\n"
              "LEFT JOIN `USER` MU ON MU.`USER_ID` = " + sql(row["member"])
            + f" AND MU.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(MU.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `MEMBER` M ON M.`USER_ID` = MU.`USER_ID`"
            + f" AND M.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(M.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `USER` TU ON TU.`USER_ID` = " + sql(row["teacher"])
            + f" AND TU.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(TU.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `TEACHER` T ON T.`USER_ID` = TU.`USER_ID`"
            + f" AND T.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(T.`DELETE_YN`, 'N') = 'N'\n"
              "LEFT JOIN `MEMBER_PROGRAM` MP ON MP.`MEMBER_PROGRAM_ID` = " + sql(row["mp_id"])
            + f" AND MP.`COMPANY_ID` = {sql(COMPANY_ID)} AND COALESCE(MP.`DELETE_YN`, 'N') = 'N';\n"
    )


def write_sql(path: Path, statements: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("-- Generated by schedule_main.py. Do not open with Excel.\nSET NAMES utf8mb4;\nSTART TRANSACTION;\n\n")
        for statement in statements:
            file.write(statement + "\n")
        file.write("COMMIT;\n")


def run(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "schedule_export.log"
    log_path.write_text("", encoding="utf-8")

    def log(message: str) -> None:
        message = f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(message)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(message + "\n")

    raw: dict[str, OrderedDict[str, dict[str, Any]]] = {}
    for kind, file_name in INPUT_FILES.items():
        input_path = input_dir / file_name
        if not input_path.exists():
            raise FileNotFoundError(f"입력 파일이 없습니다: {input_path}")
        raw[kind] = load_map(input_path)
        log(f"입력 로드: {file_name} / {len(raw[kind]):,}건")

    mp_rows, schedule_to_mp = make_member_programs(raw["CLS"], raw["CSL"], raw["PLAN"])
    log(f"MEMBER_PROGRAM 생성 대상: {len(mp_rows):,}건")
    schedule_rows: list[dict[str, Any]] = []
    schedule_id_map: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for kind in ("CLS", "CSL", "ETC"):
        for raw_id, data in raw[kind].items():
            schedule_id = raw_schedule_id(kind, raw_id, data)
            if schedule_id in seen_ids:
                raise ValueError(f"AS-IS SCHEDULE_ID 중복: {schedule_id}")
            seen_ids.add(schedule_id)
            row = to_schedule_row(kind, schedule_id, data, schedule_to_mp.get((kind, schedule_id)))
            if row is None:
                skipped.append({"schedule_type_cd": kind, "source_schedule_id": schedule_id})
                continue
            schedule_rows.append(row)
            schedule_id_map.append({
                "source_schedule_id": schedule_id, "schedule_id": schedule_id,
                "schedule_type_cd": kind, "member_program_id": row["mp_id"],
            })

    write_sql(output_dir / "01_member_program_insert.sql", [member_program_sql(row) for row in mp_rows])
    write_sql(output_dir / "02_schedule_master_insert.sql", [schedule_sql(row) for row in schedule_rows])
    (output_dir / "schedule_id_map.json").write_text(json.dumps(schedule_id_map, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "company_id": COMPANY_ID, "member_program_count": len(mp_rows), "schedule_count": len(schedule_rows),
        "schedule_count_by_type": {kind: sum(1 for row in schedule_rows if row["kind"] == kind) for kind in ("CLS", "CSL", "ETC")},
        "skipped_missing_start_or_end_datetime": skipped,
    }
    (output_dir / "schedule_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("완료: " + json.dumps(summary, ensure_ascii=False))
    log(f"결과 폴더: {output_dir.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Careple schedule JSON -> SQL")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    run(arguments.input_dir, arguments.output_dir)
