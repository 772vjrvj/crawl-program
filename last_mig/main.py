import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ============================================================
# 경로 설정
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
LAST_MIG_DIR = BASE_DIR / "last_mig"

MASTER_FILE = LAST_MIG_DIR / "SCHEDULE_MASTER.json"
MEMBER_FILE = LAST_MIG_DIR / "MEMBER.json"
TEACHER_FILE = LAST_MIG_DIR / "TEACHER.json"
PROGRAM_FILE = LAST_MIG_DIR / "PROGRAM.json"
PROGRAM_PRICE_FILE = LAST_MIG_DIR / "PROGRAM_PRICE.json"
CLASS_RAW_FILE = LAST_MIG_DIR / "schedule_class_raw.json"
COUNSEL_RAW_FILE = LAST_MIG_DIR / "schedule_counsel_raw.json"

OUTPUT_FILE = LAST_MIG_DIR / "SCHEDULE_MASTER_updated.json"
LOG_FILE = LAST_MIG_DIR / "migration.log"
FOUND_LOG_FILE = LAST_MIG_DIR / "migration_found.log"
NOT_FOUND_LOG_FILE = LAST_MIG_DIR / "migration_not_found.log"
SUMMARY_LOG_FILE = LAST_MIG_DIR / "migration_summary.log"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_log(message, log_file=None, print_console=True):
    line = f"[{now_text()}] {message}"

    if print_console:
        print(line)

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")

    if log_file is not None:
        with log_file.open("a", encoding="utf-8") as file:
            file.write(line + "\n")


def load_json(file_path):
    if not file_path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {file_path}")

    with file_path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(file_path, value):
    temp_file = file_path.with_suffix(file_path.suffix + ".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")

    temp_file.replace(file_path)


def normalize_date(value):
    """날짜 비교용. 날짜는 YYYY-MM-DD 형태로 맞춘다."""
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    # 2024-07-01 10:00:00, 2024-07-01T10:00:00 모두 처리
    match = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", text)
    if not match:
        return text

    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def normalize_time(value):
    """시간 비교용. 9:5, 09:5, 9:05를 모두 09:05로 맞춘다."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    match = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})(?::\s*(\d{1,2}))?", text)
    if not match:
        return text

    hour, minute, second = match.groups()
    result = f"{int(hour):02d}:{int(minute):02d}"

    # 비교는 HH:mm 기준이므로 초는 버린다.
    return result


def split_datetime(value):
    """SCHEDULE_MASTER의 START_DT/END_DT를 날짜와 시간으로 분리한다."""
    if value is None:
        return "", ""

    text = str(value).strip()
    if not text:
        return "", ""

    date_value = normalize_date(text)
    time_match = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})(?::\s*(\d{1,2}))?", text)
    time_value = normalize_time(time_match.group(0)) if time_match else ""

    return date_value, time_value


def normalize_price(value):
    """JSON 안의 가격은 숫자로 저장할 수 있으면 숫자로 변환한다."""
    if value is None or value == "":
        return value

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip().replace(",", "")

    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return value


def build_id_map(rows, id_key):
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue

        key = row.get(id_key)
        if key is not None and key != "":
            result[key] = row
    return result


def make_raw_records(raw_root, source_type, file_name):
    """raw JSON의 바깥쪽 ID를 보존하면서 data만 매칭용 레코드로 만든다."""
    records = []

    if not isinstance(raw_root, dict):
        return records

    for outer_id, wrapper in raw_root.items():
        if not isinstance(wrapper, dict):
            continue

        data = wrapper.get("data")
        if not isinstance(data, dict):
            continue

        records.append({
            "source_type": source_type,
            "file_name": file_name,
            "raw_id": outer_id,
            "result_code": wrapper.get("resultCode"),
            "data": data,
        })

    return records


def raw_match_values(record):
    data = record["data"]

    if record["source_type"] == "CLS":
        return {
            "start_date": normalize_date(data.get("clsDate")),
            "start_time": normalize_time(data.get("clsSt")),
            "end_date": normalize_date(data.get("clsDate")),
            "end_time": normalize_time(data.get("clsEt")),
            "member_name": data.get("visNm"),
            "teacher_text": data.get("clsMgrEmp"),
            "program_name": data.get("pgmNm"),
        }

    return {
        "start_date": normalize_date(data.get("conslDate")),
        "start_time": normalize_time(data.get("conslSt")),
        "end_date": normalize_date(data.get("conslDate")),
        "end_time": normalize_time(data.get("conslEt")),
        "member_name": data.get("visNm"),
        "teacher_text": data.get("conslEmp"),
        "program_name": data.get("pgmNm"),
    }


def make_raw_index(records):
    """날짜·시간·회원명으로 먼저 좁힌 뒤 선생님명을 검사한다."""
    index = defaultdict(list)

    for record in records:
        values = raw_match_values(record)
        record["match_values"] = values

        key = (
            values["start_date"],
            values["start_time"],
            values["end_date"],
            values["end_time"],
            values["member_name"],
        )
        index[key].append(record)

    return index


def get_schedule_type(schedule):
    return schedule.get("SCHEDULE_TYPE_CD")


def get_default_price(program_id, prices_by_program):
    prices = [
        row for row in prices_by_program.get(program_id, [])
        if row.get("DEFAULT_YN") == "Y"
    ]

    if not prices:
        return None, 0

    return normalize_price(prices[0].get("PRICE")), len(prices)


def get_counsel_price(raw_data):
    price_info = raw_data.get("priceInfoMap")
    if not isinstance(price_info, dict):
        return None

    price = price_info.get("pgmPrice")
    if price is None or price == "":
        return None

    return normalize_price(price)


def initialize_schedule_fields(schedule, members_by_id, teachers_by_id,
                               programs_by_id, prices_by_program, stats):
    """기본 매핑 및 C_* 필드를 만든다."""
    member_id = schedule.get("MEMBER_ID")
    teacher_id = schedule.get("TEACHER_ID")
    program_id = schedule.get("PROGRAM_ID")

    member = members_by_id.get(member_id)
    teacher = teachers_by_id.get(teacher_id)
    program = programs_by_id.get(program_id)

    member_name = member.get("MEMBER_NM") if member else ""
    teacher_name = teacher.get("TEACHER_NM") if teacher else ""
    program_name = program.get("PROGRAM_NM") if program else ""

    before_program_id = program_id or ""
    before_program_name = program_name or ""

    schedule["C_MEMBER_NM"] = member_name
    schedule["C_TEACHER_NM"] = teacher_name
    schedule["C_PROGRAM_NM"] = program_name
    schedule["C_START_DT"], schedule["C_START_TM"] = split_datetime(schedule.get("START_DT"))
    schedule["C_END_DT"], schedule["C_END_TM"] = split_datetime(schedule.get("END_DT"))
    schedule["C_BEFORE_PROGRAM_ID"] = before_program_id
    schedule["C_BEFORE_PROGRAM_NM"] = before_program_name
    schedule["C_AFTER_PROGRAM_ID"] = ""
    schedule["C_AFTER_PROGRAM_NM"] = ""
    schedule["C_SAME"] = "N"

    default_price, default_count = get_default_price(program_id, prices_by_program)
    if default_count > 1:
        write_log(
            f"[PRICE_MULTI] scheduleId={schedule.get('SCHEDULE_ID')} "
            f"programId={program_id} defaultPriceCount={default_count} "
            f"firstPrice={default_price}",
            NOT_FOUND_LOG_FILE,
        )

    if default_price is not None:
        schedule["PRICE"] = default_price
        stats["default_price_updated"] += 1
    else:
        stats["default_price_not_found"] += 1
        write_log(
            f"[DEFAULT_PRICE_NOT_FOUND] scheduleId={schedule.get('SCHEDULE_ID')} "
            f"programId={program_id}",
            NOT_FOUND_LOG_FILE,
        )

    if not member:
        stats["member_not_found"] += 1
    if not teacher:
        stats["teacher_not_found"] += 1
    if not program:
        stats["program_before_not_found"] += 1


def main():
    LAST_MIG_DIR.mkdir(parents=True, exist_ok=True)

    # 이전 실행 로그를 새로 만든다.
    for log_file in [LOG_FILE, FOUND_LOG_FILE, NOT_FOUND_LOG_FILE, SUMMARY_LOG_FILE]:
        log_file.write_text("", encoding="utf-8")

    write_log("========== 스케줄 프로그램 매핑 시작 ==========")
    write_log(f"실행 경로: {BASE_DIR}")
    write_log(f"입력 폴더: {LAST_MIG_DIR}")

    try:
        schedules = load_json(MASTER_FILE)
        members = load_json(MEMBER_FILE)
        teachers = load_json(TEACHER_FILE)
        programs = load_json(PROGRAM_FILE)
        program_prices = load_json(PROGRAM_PRICE_FILE)
        class_raw = load_json(CLASS_RAW_FILE)
        counsel_raw = load_json(COUNSEL_RAW_FILE)
    except Exception as error:
        write_log(f"[FATAL] JSON 파일 로드 실패: {error}", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    if not isinstance(schedules, list):
        write_log("[FATAL] SCHEDULE_MASTER.json 최상위 구조가 배열이 아닙니다.", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    if not isinstance(members, list):
        write_log("[FATAL] MEMBER.json 최상위 구조가 배열이 아닙니다.", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    if not isinstance(teachers, list):
        write_log("[FATAL] TEACHER.json 최상위 구조가 배열이 아닙니다.", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    if not isinstance(programs, list):
        write_log("[FATAL] PROGRAM.json 최상위 구조가 배열이 아닙니다.", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    if not isinstance(program_prices, list):
        write_log("[FATAL] PROGRAM_PRICE.json 최상위 구조가 배열이 아닙니다.", NOT_FOUND_LOG_FILE)
        sys.exit(1)

    members_by_id = build_id_map(members, "MEMBER_ID")
    teachers_by_id = build_id_map(teachers, "TEACHER_ID")
    programs_by_id = build_id_map(programs, "PROGRAM_ID")

    programs_by_name = defaultdict(list)
    for program in programs:
        if isinstance(program, dict) and program.get("PROGRAM_NM") is not None:
            # 프로그램명은 사용자가 요청한 대로 변형하지 않고 완전일치한다.
            programs_by_name[program.get("PROGRAM_NM")].append(program)

    prices_by_program = defaultdict(list)
    for price in program_prices:
        if not isinstance(price, dict):
            continue
        prices_by_program[price.get("PROGRAM_ID")].append(price)

    class_records = make_raw_records(class_raw, "CLS", CLASS_RAW_FILE.name)
    counsel_records = make_raw_records(counsel_raw, "CSL", COUNSEL_RAW_FILE.name)

    class_index = make_raw_index(class_records)
    counsel_index = make_raw_index(counsel_records)

    stats = defaultdict(int)
    stats["total"] = len(schedules)
    stats["class_target"] = 0
    stats["counsel_target"] = 0
    stats["etc_skipped"] = 0
    stats["other_type_skipped"] = 0
    stats["found"] = 0
    stats["not_found"] = 0
    stats["ambiguous_raw"] = 0
    stats["program_not_found"] = 0
    stats["program_ambiguous"] = 0
    stats["program_changed"] = 0
    stats["program_same"] = 0
    stats["counsel_price_updated"] = 0
    stats["default_price_updated"] = 0
    stats["default_price_not_found"] = 0
    stats["member_not_found"] = 0
    stats["teacher_not_found"] = 0
    stats["program_before_not_found"] = 0

    write_log(
        f"로드 완료: schedules={len(schedules)}, members={len(members)}, "
        f"teachers={len(teachers)}, programs={len(programs)}, "
        f"classRaw={len(class_records)}, counselRaw={len(counsel_records)}"
    )

    for index, schedule in enumerate(schedules, start=1):
        if not isinstance(schedule, dict):
            stats["not_found"] += 1
            write_log(
                f"[PROGRESS] {index}/{len(schedules)} "
                f"[INVALID] 스케줄 객체가 아닙니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        schedule_id = schedule.get("SCHEDULE_ID", "")
        schedule_type = get_schedule_type(schedule)

        initialize_schedule_fields(
            schedule,
            members_by_id,
            teachers_by_id,
            programs_by_id,
            prices_by_program,
            stats,
        )

        write_log(
            f"[PROGRESS] {index}/{len(schedules)} "
            f"scheduleId={schedule_id} type={schedule_type}"
        )

        if schedule_type == "ETC":
            stats["etc_skipped"] += 1
            write_log(
                f"[SKIP][ETC] scheduleId={schedule_id} 기타 일정은 매칭하지 않습니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        if schedule_type == "CLS":
            stats["class_target"] += 1
            raw_index = class_index
            raw_label = "CLASS"
        elif schedule_type == "CSL":
            stats["counsel_target"] += 1
            raw_index = counsel_index
            raw_label = "COUNSEL"
        else:
            stats["other_type_skipped"] += 1
            write_log(
                f"[SKIP][UNKNOWN_TYPE] scheduleId={schedule_id} "
                f"scheduleType={schedule_type}",
                NOT_FOUND_LOG_FILE,
            )
            continue

        key = (
            schedule.get("C_START_DT", ""),
            schedule.get("C_START_TM", ""),
            schedule.get("C_END_DT", ""),
            schedule.get("C_END_TM", ""),
            schedule.get("C_MEMBER_NM", ""),
        )

        candidates = raw_index.get(key, [])
        teacher_name = schedule.get("C_TEACHER_NM", "")

        teacher_candidates = []
        for candidate in candidates:
            values = candidate["match_values"]
            teacher_text = values.get("teacher_text")

            if (
                    teacher_name
                    and teacher_text
                    and teacher_name in str(teacher_text)
            ):
                teacher_candidates.append(candidate)

        if not teacher_candidates:
            stats["not_found"] += 1

            if candidates:
                reason = "날짜/시간/회원명은 일치하지만 선생님명이 일치하지 않음"
            else:
                reason = "날짜/시간/회원명에 맞는 raw 데이터 없음"

            write_log(
                f"[NOT_FOUND][{raw_label}] scheduleId={schedule_id} "
                f"date={schedule.get('C_START_DT')} "
                f"time={schedule.get('C_START_TM')}~{schedule.get('C_END_TM')} "
                f"member={schedule.get('C_MEMBER_NM')} "
                f"teacher={teacher_name} reason={reason}",
                NOT_FOUND_LOG_FILE,
            )
            continue

        if len(teacher_candidates) > 1:
            stats["ambiguous_raw"] += 1
            stats["not_found"] += 1

            raw_ids = ",".join(str(item["raw_id"]) for item in teacher_candidates)
            write_log(
                f"[AMBIGUOUS][{raw_label}] scheduleId={schedule_id} "
                f"matchedCount={len(teacher_candidates)} rawIds={raw_ids} "
                f"임의로 선택하지 않고 기존 프로그램을 유지합니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        matched = teacher_candidates[0]
        raw_data = matched["data"]
        raw_program_name = raw_match_values(matched).get("program_name")

        if raw_program_name is None or raw_program_name == "":
            stats["program_not_found"] += 1
            stats["not_found"] += 1
            write_log(
                f"[PROGRAM_NOT_FOUND][{raw_label}] scheduleId={schedule_id} "
                f"rawId={matched['raw_id']} rawProgramName이 비어 있습니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        matched_programs = programs_by_name.get(raw_program_name, [])

        if not matched_programs:
            stats["program_not_found"] += 1
            stats["not_found"] += 1
            write_log(
                f"[PROGRAM_NOT_FOUND][{raw_label}] scheduleId={schedule_id} "
                f"rawId={matched['raw_id']} rawProgramName={raw_program_name} "
                f"PROGRAM.json에 완전일치 프로그램이 없습니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        if len(matched_programs) > 1:
            stats["program_ambiguous"] += 1
            stats["not_found"] += 1
            matched_ids = ",".join(str(item.get("PROGRAM_ID")) for item in matched_programs)
            write_log(
                f"[PROGRAM_AMBIGUOUS][{raw_label}] scheduleId={schedule_id} "
                f"rawProgramName={raw_program_name} programIds={matched_ids} "
                f"임의로 선택하지 않고 기존 프로그램을 유지합니다.",
                NOT_FOUND_LOG_FILE,
            )
            continue

        new_program = matched_programs[0]
        new_program_id = new_program.get("PROGRAM_ID")
        old_program_id = schedule.get("C_BEFORE_PROGRAM_ID", "")
        old_program_name = schedule.get("C_BEFORE_PROGRAM_NM", "")

        schedule["PROGRAM_ID"] = new_program_id
        schedule["C_AFTER_PROGRAM_ID"] = new_program_id
        schedule["C_AFTER_PROGRAM_NM"] = raw_program_name
        schedule["C_SAME"] = "Y" if old_program_name == raw_program_name else "N"

        if schedule["C_SAME"] == "Y":
            stats["program_same"] += 1
        else:
            stats["program_changed"] += 1

        if schedule_type == "CSL":
            counsel_price = get_counsel_price(raw_data)
            if counsel_price is not None:
                schedule["PRICE"] = counsel_price
                stats["counsel_price_updated"] += 1

        stats["found"] += 1

        write_log(
            f"[FOUND][{raw_label}] scheduleId={schedule_id} rawId={matched['raw_id']} "
            f"member={schedule.get('C_MEMBER_NM')} "
            f"teacher={schedule.get('C_TEACHER_NM')} "
            f"date={schedule.get('C_START_DT')} "
            f"time={schedule.get('C_START_TM')}~{schedule.get('C_END_TM')} "
            f"oldProgramId={old_program_id} oldProgramName={old_program_name} "
            f"newProgramId={new_program_id} newProgramName={raw_program_name} "
            f"same={schedule.get('C_SAME')}",
            FOUND_LOG_FILE,
        )

    save_json(OUTPUT_FILE, schedules)

    summary_lines = [
        "========== 최종 결과 통계 ==========",
        f"전체 스케줄: {stats['total']}",
        f"CLASS 대상: {stats['class_target']}",
        f"COUNSEL 대상: {stats['counsel_target']}",
        f"ETC 제외: {stats['etc_skipped']}",
        f"알 수 없는 스케줄 타입 제외: {stats['other_type_skipped']}",
        f"매칭 성공: {stats['found']}",
        f"매칭 실패: {stats['not_found']}",
        f"raw 다건 매칭: {stats['ambiguous_raw']}",
        f"PROGRAM 미존재: {stats['program_not_found']}",
        f"PROGRAM명 다건 매칭: {stats['program_ambiguous']}",
        f"프로그램 변경: {stats['program_changed']}",
        f"프로그램 동일: {stats['program_same']}",
        f"기본 프로그램 가격 반영: {stats['default_price_updated']}",
        f"기본 프로그램 가격 없음: {stats['default_price_not_found']}",
        f"상담 가격 반영: {stats['counsel_price_updated']}",
        f"회원 ID 조회 실패: {stats['member_not_found']}",
        f"선생님 ID 조회 실패: {stats['teacher_not_found']}",
        f"기존 프로그램 ID 조회 실패: {stats['program_before_not_found']}",
        f"결과 파일: {OUTPUT_FILE}",
        f"전체 로그: {LOG_FILE}",
        f"성공 로그: {FOUND_LOG_FILE}",
        f"실패 로그: {NOT_FOUND_LOG_FILE}",
        "====================================",
    ]

    summary = "\n".join(summary_lines)
    with SUMMARY_LOG_FILE.open("w", encoding="utf-8") as file:
        file.write(f"[{now_text()}]\n{summary}\n")

    for line in summary_lines:
        write_log(line, print_console=True)

    write_log("========== 스케줄 프로그램 매핑 종료 ==========")


if __name__ == "__main__":
    main()
