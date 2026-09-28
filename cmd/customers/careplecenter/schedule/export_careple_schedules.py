import csv
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = "_ga=GA1.2.1541479523.1786462213; SCOUTER=z585fum1bc95et; _gid=GA1.2.1705722455.1789353979; orgNm=%EC%84%9C%EC%9A%B8%EC%84%B1%EB%AA%A8%EC%9D%98%EC%9B%90%EC%95%84%EB%8F%99%EB%B0%9C%EB%8B%AC%ED%81%B4%EB%A6%AC%EB%8B%89%20; empId=172523906005189656; empNm=%EB%B0%95%EB%B3%91%EC%A4%80; tuid=tuid178956214865944220; loginId=rapport1; posn=%EB%8C%80%ED%91%9C%EB%8B%98; managerYn=Y; masterYn=N; _ga_592EQKNPJ5=GS2.2.s1789562143$o69$g1$t1789569069$j60$l0$h0"
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2027-06"
DETAIL_WORKERS = 6  # 4~8 사이

BASE_URL = "https://www.careplecenter.com"
CALENDAR_URL = BASE_URL + "/pcareple/v1/schedules/.fullcalendar/events/sim?reqtype=fc"
CLASS_URL = BASE_URL + "/pcareple/v1/classes/"
COUNSEL_URL = BASE_URL + "/pcareple/v1/counsels/"
ETC_URL = BASE_URL + "/pcareple/v1/schedules/"
MONTHLY_PLAN_URL = BASE_URL + "/pcareple/v1/monthlyplans/"

MEMBER_DIR = Path("output/member")
TEACHER_DIR = Path("output/teacher")
PROGRAM_DIR = Path("output/program")
OUTPUT_DIR = Path("output/schedule")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"

SCHEDULE_HEADERS = [
    "SCHEDULE_ID", "SCHEDULE_GROUP_ID", "COMPANY_ID", "PROGRAM_ID", "MEMBER_ID", "TEACHER_ID",
    "MEMO", "SCHEDULE_CLASS_CD", "SCHEDULE_TYPE_CD", "SCHEDULE_STATUS_CD", "START_DT", "END_DT",
    "ALL_DAY_YN", "PLACE", "QUICK_INPUT_TEXT", "COUNSEL_INPUT_TYPE_CD", "PRICE", "CENTER_SHARE_YN",
    "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID",
    "MEMBER_PROGRAM_ID", "REPEAT_TEMPLATE_YN",
]
MEMBER_PROGRAM_HEADERS = [
    "MEMBER_PROGRAM_ID", "COMPANY_ID", "MEMBER_ID", "PROGRAM_ID", "EMP_ID", "PROGRAM_PRICE_ID",
    "TOTAL_COUNT", "USED_COUNT", "REMAIN_COUNT", "UNIT_PRICE", "TOTAL_AMOUNT", "DISCOUNT_AMOUNT",
    "PAY_AMOUNT", "START_DT", "END_DT", "STATUS_CD", "MEMO", "USE_YN", "DELETE_YN", "CREATE_DT",
    "UPDATE_DT", "DISCOUNT_MEMO",
]
MONTHLY_SERVICE_HEADERS = [
    "MONTHLY_SERVICE_ID", "COMPANY_ID", "MEMBER_PROGRAM_ID", "SERVICE_YM", "CARRYOVER_SESSION_COUNT",
    "PROGRAM_PRICE_ID", "UNIT_SERVICE_PRICE", "DISCOUNT_AMOUNT", "OUT_OF_POCKET_AMOUNT", "MEMO",
    "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID",
]
SERVICE_POLICY_HEADERS = [
    "SERVICE_POLICY_ID", "COMPANY_ID", "MEMBER_PROGRAM_ID", "EFFECTIVE_FROM_YM", "PROGRAM_PRICE_ID",
    "UNIT_SERVICE_PRICE", "DISCOUNT_AMOUNT", "OUT_OF_POCKET_AMOUNT", "MEMO", "USE_YN", "DELETE_YN",
    "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID",
]
SCHEDULE_MAP_HEADERS = [
    "CAREPLE_EVENT_ID", "CAREPLE_DETAIL_ID", "SCHEDULE_ID", "SCHEDULE_TYPE_CD", "MEMBER_PROGRAM_ID",
]
MEMBER_PROGRAM_MAP_HEADERS = [
    "CAREPLE_MONTH_SRVPL_ID", "MEMBER_PROGRAM_ID", "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID",
]
UNMATCHED_HEADERS = ["SOURCE_TYPE", "CAREPLE_ID", "SOURCE_VALUE", "FIELD", "MESSAGE"]


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


def event_time(event, field):
    text = value(event.get(field))
    if not text:
        return ""
    if text.endswith("Z"):
        # Careple FullCalendar 응답의 Z 시간은 화면에 표시되는 현지 시간값이다.
        # UTC로 변환해 9시간을 더하면 일정 시간이 잘못된다.
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")
    return date_time(text)


def month_range(start_ym, end_ym):
    year, month = map(int, start_ym.split("-"))
    end_year, end_month = map(int, end_ym.split("-"))
    while (year, month) <= (end_year, end_month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def month_number(ym):
    year, month = map(int, ym.split("-"))
    return year * 12 + month


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def validate(rows, required_columns, table):
    for row_no, row in enumerate(rows, start=2):
        missing = [column for column in required_columns if not value(row.get(column))]
        if missing:
            raise ValueError(f"{table} CSV {row_no}행 NOT NULL 값 누락: {', '.join(missing)}")


def checkpoint_path(kind, source_id):
    safe = "".join(char if char.isalnum() else "_" for char in str(source_id))
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


def post_json(url, body):
    def request_once():
        headers = dict(HEADERS)
        headers["Content-Type"] = "application/json"
        headers["Origin"] = BASE_URL
        request = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    return request_retry(request_once, url)


def cached_api(kind, source_id, url):
    path = checkpoint_path(kind, source_id)
    cached = read_checkpoint(path)
    if cached is not None:
        return cached
    response = get_json(url, {"randid": random.random()})
    write_checkpoint(path, response)
    return response


def csv_mapping(rows, source_column, target_column):
    result = {}
    for row in rows:
        source, target = value(row.get(source_column)), value(row.get(target_column))
        if source and target:
            if source in result and result[source] != target:
                raise ValueError(f"매핑 CSV 원본 ID 중복: {source}")
            result[source] = target
    return result


def load_maps():
    files = [
        (MEMBER_DIR / "member_id_map.csv", "MEMBER"),
        (TEACHER_DIR / "employee_id_map.csv", "TEACHER"),
        (PROGRAM_DIR / "program_id_map.csv", "PROGRAM"),
    ]
    for path, name in files:
        if not path.exists():
            raise FileNotFoundError(f"{path} 파일이 없습니다. {name} 이관을 먼저 실행하세요.")
    member_rows, teacher_rows, program_rows = (read_csv(path) for path, _ in files)
    return {
        "member": csv_mapping(member_rows, "CAREPLE_VIS_ID", "MEMBER_ID"),
        "teacher": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "TEACHER_ID"),
        "teacher_user": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "USER_ID"),
        "program": csv_mapping(program_rows, "CAREPLE_PROGRAM_ID", "PROGRAM_ID"),
        "employee_ids": [value(row.get("CAREPLE_EMP_ID")) for row in teacher_rows if value(row.get("CAREPLE_EMP_ID"))],
    }


def build_member_programs(plan_details, mapping, migration_dt, unmatched):
    grouped = {}
    for plan_id, plan in plan_details.items():
        ym = f"{value(plan.get('srvYear'))}-{value(plan.get('srvMonth')).zfill(2)}"
        key = value(plan.get("visId")), value(plan.get("pgmId")), value(plan.get("srvPicId"))
        grouped.setdefault(key, []).append((ym, plan_id, plan))

    mp_rows, monthly_rows, policy_rows, mp_map_rows, plan_to_mp = [], [], [], [], {}
    mp_no = service_no = policy_no = 0
    for (vis_id, pgm_id, emp_id), plans in grouped.items():
        plans.sort(key=lambda item: item[0])
        episodes, current = [], []
        for plan in plans:
            if current and month_number(plan[0]) - month_number(current[-1][0]) > 1:
                episodes.append(current)
                current = []
            current.append(plan)
        if current:
            episodes.append(current)

        for episode in episodes:
            member_id = mapping["member"].get(vis_id, "")
            program_id = mapping["program"].get(pgm_id, "")
            teacher_id = mapping["teacher"].get(emp_id, "")
            for source, field, found in ((vis_id, "MEMBER_ID", member_id), (pgm_id, "PROGRAM_ID", program_id), (emp_id, "TEACHER_ID", teacher_id)):
                if not found:
                    unmatched.append(["MONTHLY_PLAN", episode[0][1], source, field, "매핑 없음"])
            if not member_id or not program_id:
                continue

            mp_no += 1
            mp_id = f"MP{mp_no:08d}"
            first_plan, last_plan = episode[0][2], episode[-1][2]
            first_info = first_plan.get("priceInfoMap") or {}
            classes = [item for _, _, plan in episode for item in (plan.get("clsList") or [])]
            dates = [value(item.get("clsDate")) for item in classes if value(item.get("clsDate"))]
            paid = sum(int(value((plan.get("priceInfoMap") or {}).get("payClsTime")) or 0) for _, _, plan in episode)
            used = sum(1 for item in classes if value(item.get("clsStatDivCd")) == "D")
            discount = sum(int(value((plan.get("priceInfoMap") or {}).get("discountPrice")) or 0) for _, _, plan in episode)
            pay = sum(int(value((plan.get("priceInfoMap") or {}).get("totalPayPgmPrice")) or 0) for _, _, plan in episode)
            memo = next((value((plan.get("priceInfoMap") or {}).get("memo")) for _, _, plan in episode if value((plan.get("priceInfoMap") or {}).get("memo"))), "")
            create_dt, update_dt = date_time(first_plan.get("regDtime")) or migration_dt, date_time(last_plan.get("lastModDtime"))
            mp_rows.append({
                "MEMBER_PROGRAM_ID": mp_id, "COMPANY_ID": COMPANY_ID, "MEMBER_ID": member_id, "PROGRAM_ID": program_id,
                "EMP_ID": teacher_id, "PROGRAM_PRICE_ID": value(first_plan.get("pgmPriceId")),
                "TOTAL_COUNT": str(paid), "USED_COUNT": str(used), "REMAIN_COUNT": str(max(paid - used, 0)),
                "UNIT_PRICE": value(first_info.get("totalPgmPrice")) or "0", "TOTAL_AMOUNT": str(pay),
                "DISCOUNT_AMOUNT": str(discount), "PAY_AMOUNT": str(pay),
                "START_DT": min(dates) if dates else episode[0][0] + "-01", "END_DT": max(dates) if dates else episode[-1][0] + "-01",
                "STATUS_CD": "ACTIVE", "MEMO": memo, "USE_YN": "Y", "DELETE_YN": "N",
                "CREATE_DT": create_dt, "UPDATE_DT": update_dt, "DISCOUNT_MEMO": memo,
            })
            last_policy = None
            for ym, plan_id, plan in episode:
                info = plan.get("priceInfoMap") or {}
                unit = value(info.get("totalPgmPrice")) or "0"
                discount_amount = value(info.get("discountPrice")) or "0"
                out_of_pocket = value(info.get("selfPayPrice")) or "0"
                policy = value(plan.get("pgmPriceId")), unit, discount_amount, out_of_pocket, value(info.get("memo"))
                update_user = mapping["teacher_user"].get(value(plan.get("srvPicId")), "")
                plan_to_mp[plan_id] = mp_id
                service_no += 1
                monthly_rows.append({
                    "MONTHLY_SERVICE_ID": f"MONTHLY_SERVICE{service_no:08d}", "COMPANY_ID": COMPANY_ID,
                    "MEMBER_PROGRAM_ID": mp_id, "SERVICE_YM": ym, "CARRYOVER_SESSION_COUNT": value(info.get("forwardedClsTime")) or "0",
                    "PROGRAM_PRICE_ID": policy[0], "UNIT_SERVICE_PRICE": unit, "DISCOUNT_AMOUNT": discount_amount,
                    "OUT_OF_POCKET_AMOUNT": out_of_pocket, "MEMO": policy[4], "USE_YN": "Y", "DELETE_YN": "N",
                    "CREATE_DT": date_time(plan.get("regDtime")) or migration_dt,
                    "UPDATE_DT": date_time(plan.get("lastModDtime")) or date_time(plan.get("regDtime")) or migration_dt,
                    "UPDATE_USER_ID": update_user,
                })
                mp_map_rows.append({"CAREPLE_MONTH_SRVPL_ID": plan_id, "MEMBER_PROGRAM_ID": mp_id, "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id, "CAREPLE_EMP_ID": emp_id})
                if policy != last_policy:
                    last_policy = policy
                    policy_no += 1
                    policy_rows.append({
                        "SERVICE_POLICY_ID": f"SERVICE_POLICY{policy_no:08d}", "COMPANY_ID": COMPANY_ID,
                        "MEMBER_PROGRAM_ID": mp_id, "EFFECTIVE_FROM_YM": ym, "PROGRAM_PRICE_ID": policy[0],
                        "UNIT_SERVICE_PRICE": unit, "DISCOUNT_AMOUNT": discount_amount, "OUT_OF_POCKET_AMOUNT": out_of_pocket,
                        "MEMO": policy[4], "USE_YN": "Y", "DELETE_YN": "N", "CREATE_DT": create_dt,
                        "UPDATE_DT": update_dt, "UPDATE_USER_ID": mapping["teacher_user"].get(emp_id, ""),
                    })
    return mp_rows, monthly_rows, policy_rows, plan_to_mp, mp_map_rows


def main():
    if not COOKIE.strip():
        raise ValueError("맨 위 COOKIE 변수에 최신 쿠키를 넣으세요.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 이전 그룹 방식 산출물이 남아 있으면 잘못 import하지 않도록 제거한다.
    for old_name in ("schedule_group_db.csv", "schedule_repeat_exception_db.csv", "schedule_group_id_map.csv"):
        old_path = OUTPUT_DIR / old_name
        if old_path.exists():
            old_path.unlink()
    log_path = OUTPUT_DIR / "schedule_export.log"
    log_path.write_text("", encoding="utf-8")

    def log(message):
        text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(text)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(text + "\n")

    global HEADERS
    tuid = next((part.split("=", 1)[1].strip() for part in COOKIE.split(";") if part.strip().startswith("tuid=")), "")
    HEADERS = {"Accept": "*/*", "Referer": BASE_URL + "/index.html", "X-Requested-With": "XMLHttpRequest", "Cookie": COOKIE, "tuid": tuid}
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mapping = load_maps()
    log(f"매핑 로드: 이용자 {len(mapping['member'])}, 선생님 {len(mapping['teacher'])}, 프로그램 {len(mapping['program'])}")

    raw_months, events = {}, {}
    for year, month in month_range(START_YM, END_YM):
        next_year, next_mon = next_month(year, month)
        ym = f"{year:04d}-{month:02d}"
        body = {
            "start": f"{ym}-01", "end": f"{next_year:04d}-{next_mon:02d}-01",
            "searchEmpId": mapping["employee_ids"], "searchVisId": [], "searchPgmId": [], "searchPgmDiv": [],
            "searchSchedDivCd": "CLS CSL ETC", "searchStatDivCd": "R D C S F ",
            "customTitleConfig": {"orderList": ["VIS", "PGM"]}, "searchVou": {"searchBy": "VOU_ID", "keyList": []},
        }
        path = checkpoint_path("monthly", ym)
        response = read_checkpoint(path)
        if response is None:
            response = post_json(CALENDAR_URL, body)
            write_checkpoint(path, response)
        else:
            log(f"{ym} 월간 목록 체크포인트 재사용")
        raw_months[ym] = response
        for event in response.get("data") or []:
            events[(value(event.get("tp")), value(event.get("id")), value(event.get("start")), value(event.get("end")))] = event
        log(f"{ym} 월간 일정 {len(response.get('data') or [])}건")

    event_list = sorted(events.values(), key=lambda event: (event_time(event, "start"), value(event.get("tp")), value(event.get("id"))))
    log(f"월 경계 중복 제거 후 일정 {len(event_list)}건")

    def detail_source(event):
        event_type, source_id = value(event.get("tp")), value(event.get("id"))
        if event_type == "CLS":
            return "classes", CLASS_URL + source_id
        if event_type == "CSL":
            return "counsels", COUNSEL_URL + source_id
        if event_type == "ETC":
            return "etc", ETC_URL + source_id
        return "", ""

    details, raw_classes, raw_counsels, raw_etc = {}, {}, {}, {}
    detail_events = [event for event in event_list if detail_source(event)[0]]
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(cached_api, detail_source(event)[0], value(event.get("id")), detail_source(event)[1]): event for event in detail_events}
        for index, future in enumerate(as_completed(futures), start=1):
            event = futures[future]
            event_type, source_id = value(event.get("tp")), value(event.get("id"))
            response = future.result()
            details[(event_type, source_id)] = response.get("data") or {}
            if event_type == "CLS":
                raw_classes[source_id] = response
            elif event_type == "CSL":
                raw_counsels[source_id] = response
            else:
                raw_etc[source_id] = response
            if index % 25 == 0 or index == len(futures):
                log(f"상세 조회 {index}/{len(futures)} (동시작업 {DETAIL_WORKERS})")

    plan_ids = sorted({value(detail.get("monthSrvplId")) for (event_type, _), detail in details.items() if event_type == "CLS" and value(detail.get("monthSrvplId"))})
    plan_details, raw_plans = {}, {}
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(cached_api, "monthlyplans", plan_id, MONTHLY_PLAN_URL + plan_id): plan_id for plan_id in plan_ids}
        for index, future in enumerate(as_completed(futures), start=1):
            plan_id = futures[future]
            response = future.result()
            plan_details[plan_id] = response.get("data") or {}
            raw_plans[plan_id] = response
            if index % 25 == 0 or index == len(futures):
                log(f"월서비스 상세 조회 {index}/{len(futures)} (동시작업 {DETAIL_WORKERS})")

    unmatched = []
    mp_rows, monthly_rows, policy_rows, plan_to_mp, mp_map_rows = build_member_programs(plan_details, mapping, migration_dt, unmatched)
    schedule_rows, schedule_map_rows = [], []

    for event in event_list:
        event_type, source_id = value(event.get("tp")), value(event.get("id"))
        detail = details.get((event_type, source_id), {})
        start_dt, end_dt = event_time(event, "start"), event_time(event, "end")
        status = value(event.get("sc")) or "R"
        member_id = program_id = teacher_id = member_program_id = update_user_id = ""
        memo, place, quick_text, price, complete_dt = value(event.get("mm")), "", "", "", ""
        all_day, input_type, detail_id = ("Y" if event.get("allDay") else "N"), "", ""

        if event_type == "CLS":
            vis_id, pgm_id = value(detail.get("visId")), value(detail.get("pgmId"))
            emp_id = value(event.get("ei")) or value(detail.get("clsMgrEmpId"))
            member_id, program_id, teacher_id = mapping["member"].get(vis_id, ""), mapping["program"].get(pgm_id, ""), mapping["teacher"].get(emp_id, "")
            member_program_id = plan_to_mp.get(value(detail.get("monthSrvplId")), "")
            update_user_id = mapping["teacher_user"].get(value(detail.get("regEmpId")), "")
            # 월 목록은 취소/변경된 회차의 최신 상태·일시·메모를 반환한다.
            # 상세 체크포인트는 과거 응답일 수 있으므로 월 목록을 우선한다.
            status = value(event.get("sc")) or value(detail.get("clsStatDivCd")) or "R"
            memo = value(event.get("mm")) or value(detail.get("memo")) or memo
            price = value((detail.get("pgmInfoMap") or {}).get("pgmPrice")) or "0"
            complete_dt = date_time(detail.get("lastModDtime")) if status == "D" else ""
            if not start_dt:
                start_dt = date_time(f"{detail.get('clsDate', '')} {detail.get('clsSt', '')}")
            if not end_dt:
                end_dt = date_time(f"{detail.get('clsDate', '')} {detail.get('clsEt', '')}")
            detail_id = value(detail.get("clsId"))
            fields = ((vis_id, "MEMBER_ID", member_id), (pgm_id, "PROGRAM_ID", program_id), (emp_id, "TEACHER_ID", teacher_id))
        elif event_type == "CSL":
            vis_id, pgm_id = value(detail.get("visId")), value(detail.get("pgmId"))
            emp_id = value(event.get("ei")) or value(detail.get("conslEmpId"))
            member_id, program_id, teacher_id = mapping["member"].get(vis_id, ""), mapping["program"].get(pgm_id, ""), mapping["teacher"].get(emp_id, "")
            update_user_id = mapping["teacher_user"].get(value(detail.get("regEmpId")), "")
            status = value(event.get("sc")) or value(detail.get("taskStatDivCd")) or "R"
            memo = value(event.get("mm")) or value(detail.get("conslCont")) or memo
            quick_text = value(detail.get("conslNm")) or value(detail.get("conslTgt"))
            price = value((detail.get("priceInfoMap") or {}).get("pgmPrice")) or "0"
            complete_dt = date_time(detail.get("contLastModDtime") or detail.get("lastModDtime")) if status == "D" else ""
            if not start_dt:
                start_dt = date_time(f"{detail.get('conslDate', '')} {detail.get('conslSt', '')}")
            if not end_dt:
                end_dt = date_time(f"{detail.get('conslDate', '')} {detail.get('conslEt', '')}")
            input_type, detail_id = "REGISTERED", value(detail.get("conslId"))
            fields = ((vis_id, "MEMBER_ID", member_id), (pgm_id, "PROGRAM_ID", program_id), (emp_id, "TEACHER_ID", teacher_id))
        elif event_type == "ETC":
            owner_id = value(event.get("ei")) or value(detail.get("schedOwnEmpId"))
            teacher_id, update_user_id = mapping["teacher"].get(owner_id, ""), mapping["teacher_user"].get(owner_id, "")
            memo, place = value(event.get("mm")) or value(detail.get("schedNm")) or memo, value(detail.get("pl"))
            all_day = "Y" if value(detail.get("schedWdayYn")) == "Y" else all_day
            # FullCalendar 종일 일정의 end는 다음 날 00:00:00인 미포함 경계값이다.
            # 기타 일정은 상세 API의 실제 종료일시(예: 당일 23:59)를 사용한다.
            start_dt = date_time(f"{detail.get('schedSd', '')} {detail.get('schedSt', '')}") or start_dt
            end_dt = date_time(f"{detail.get('schedEd', '')} {detail.get('schedEt', '')}") or end_dt
            detail_id, fields = value(detail.get("schedId")), ((owner_id, "TEACHER_ID", teacher_id),)
        else:
            fields = ()
            unmatched.append([event_type or "UNKNOWN", source_id, "", "DETAIL", "상세 API 미확인"])

        for source, field, found in fields:
            if not found:
                unmatched.append([event_type, source_id, source, field, "매핑 없음"])
        if not start_dt or not end_dt:
            unmatched.append([event_type or "UNKNOWN", source_id, "", "START_DT/END_DT", "일시가 없어 적재 제외"])
            continue

        schedule_id = f"SCHEDULE{len(schedule_rows) + 1:08d}"
        schedule_rows.append({
            "SCHEDULE_ID": schedule_id, "SCHEDULE_GROUP_ID": "", "COMPANY_ID": COMPANY_ID,
            "PROGRAM_ID": program_id, "MEMBER_ID": member_id, "TEACHER_ID": teacher_id, "MEMO": memo,
            "SCHEDULE_CLASS_CD": "VCHR" if value(detail.get("vouUseYn")) == "Y" else "NORMAL",
            "SCHEDULE_TYPE_CD": event_type or "ETC", "SCHEDULE_STATUS_CD": status, "START_DT": start_dt, "END_DT": end_dt,
            "ALL_DAY_YN": all_day, "PLACE": place, "QUICK_INPUT_TEXT": quick_text, "COUNSEL_INPUT_TYPE_CD": input_type,
            "PRICE": price, "CENTER_SHARE_YN": "N", "COMPLETE_DT": complete_dt, "USE_YN": "Y", "DELETE_YN": "N",
            "CREATE_DT": date_time(detail.get("regDtime")) or migration_dt, "UPDATE_DT": date_time(detail.get("lastModDtime")),
            "UPDATE_USER_ID": update_user_id, "MEMBER_PROGRAM_ID": member_program_id, "REPEAT_TEMPLATE_YN": "N",
        })
        schedule_map_rows.append({"CAREPLE_EVENT_ID": source_id, "CAREPLE_DETAIL_ID": detail_id, "SCHEDULE_ID": schedule_id, "SCHEDULE_TYPE_CD": event_type, "MEMBER_PROGRAM_ID": member_program_id})

    validate(schedule_rows, ["SCHEDULE_ID", "COMPANY_ID", "SCHEDULE_TYPE_CD", "START_DT", "END_DT"], "SCHEDULE_MASTER")
    validate(mp_rows, ["MEMBER_PROGRAM_ID", "COMPANY_ID", "MEMBER_ID", "PROGRAM_ID"], "MEMBER_PROGRAM")
    validate(monthly_rows, ["MONTHLY_SERVICE_ID", "COMPANY_ID", "MEMBER_PROGRAM_ID", "SERVICE_YM", "UNIT_SERVICE_PRICE", "DISCOUNT_AMOUNT", "OUT_OF_POCKET_AMOUNT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT"], "MEMBER_PROGRAM_MONTHLY_SERVICE")
    validate(policy_rows, ["SERVICE_POLICY_ID", "COMPANY_ID", "MEMBER_PROGRAM_ID", "EFFECTIVE_FROM_YM", "UNIT_SERVICE_PRICE", "DISCOUNT_AMOUNT", "OUT_OF_POCKET_AMOUNT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT"], "MEMBER_PROGRAM_MONTHLY_SERVICE_POLICY")

    origin_headers = ["일정ID", "유형", "제목", "시작", "종료", "상태", "메모"]
    origin_rows = [{"일정ID": value(e.get("id")), "유형": value(e.get("tp")), "제목": value(e.get("title")), "시작": event_time(e, "start"), "종료": event_time(e, "end"), "상태": value(e.get("sn")), "메모": value(e.get("mm"))} for e in event_list]
    write_csv(OUTPUT_DIR / "schedule_origin.csv", origin_headers, origin_rows)
    write_csv(OUTPUT_DIR / "schedule_db.csv", SCHEDULE_HEADERS, schedule_rows)
    write_csv(OUTPUT_DIR / "member_program_db.csv", MEMBER_PROGRAM_HEADERS, mp_rows)
    write_csv(OUTPUT_DIR / "member_program_monthly_service_db.csv", MONTHLY_SERVICE_HEADERS, monthly_rows)
    write_csv(OUTPUT_DIR / "member_program_monthly_service_policy_db.csv", SERVICE_POLICY_HEADERS, policy_rows)
    write_csv(OUTPUT_DIR / "schedule_id_map.csv", SCHEDULE_MAP_HEADERS, schedule_map_rows)
    write_csv(OUTPUT_DIR / "member_program_id_map.csv", MEMBER_PROGRAM_MAP_HEADERS, mp_map_rows)
    write_csv(OUTPUT_DIR / "schedule_unmatched_map.csv", UNMATCHED_HEADERS, [dict(zip(UNMATCHED_HEADERS, row)) for row in unmatched])
    for name, data in (("schedule_monthly_raw.json", raw_months), ("schedule_class_raw.json", raw_classes), ("schedule_counsel_raw.json", raw_counsels), ("schedule_etc_raw.json", raw_etc), ("schedule_monthlyplan_raw.json", raw_plans)):
        (OUTPUT_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"calendar_event_count": len(event_list), "schedule_count": len(schedule_rows), "member_program_count": len(mp_rows), "monthly_service_count": len(monthly_rows), "service_policy_count": len(policy_rows), "unmatched_count": len(unmatched)}
    (OUTPUT_DIR / "schedule_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("이관 완료: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
