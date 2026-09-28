import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

# 최신 브라우저 쿠키만 넣어 실행하세요.
COOKIE = "_ga=GA1.2.1541479523.1786462213; SCOUTER=z585fum1bc95et; _gid=GA1.2.1705722455.1789353979; orgNm=%EC%84%9C%EC%9A%B8%EC%84%B1%EB%AA%A8%EC%9D%98%EC%9B%90%EC%95%84%EB%8F%99%EB%B0%9C%EB%8B%AC%ED%81%B4%EB%A6%AC%EB%8B%89%20; empId=172523906005189656; empNm=%EB%B0%95%EB%B3%91%EC%A4%80; loginId=rapport1; posn=%EB%8C%80%ED%91%9C%EB%8B%98; managerYn=Y; masterYn=N; tuid=tuid178964425989068310; _ga_592EQKNPJ5=GS2.2.s1789644262$o72$g1$t1789644262$j60$l0$h0"
COMPANY_ID = "COMPANY000001"
START_TIME = "2024-07-01 00:00:00"
END_TIME = "2026-09-17 23:59:59"
PAGE_SIZE = 100
DETAIL_WORKERS = 6
RETRY_COUNT = 7

# AS-IS 상세 응답에 실제 템플릿 식별자가 없으므로, 기존 공통 일정안내 템플릿을 사용한다.
KAKAO_TEMPLATE_ID = "KAKAO_TEMPLATE00000001"

LIST_URL = "https://www.careplecenter.com/pcareple/v1/message/visMsgList"
DETAIL_URL = "https://www.careplecenter.com/pcareple/v1/message/{msg_id}/detail"
OUTPUT_DIR = Path("output") / "message"
MEMBER_MAP_PATH = Path("output") / "member" / "member_id_map.csv"
USE_MAP_PATH = OUTPUT_DIR / "message_use_id_map.csv"

SMS_HEADERS = [
    "SMS_SEND_HISTORY_ID", "COMPANY_ID", "SEND_TYPE_CD", "TARGET_TYPE_CD", "TARGET_ID", "RECEIVER_NM",
    "RECEIVER_PHONE", "MESSAGE", "SEND_PRICE", "SEND_STATUS_CD", "ALIGO_MID", "RESULT_CODE",
    "RESULT_MESSAGE", "SEND_DT", "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
KAKAO_HEADERS = [
    "KAKAO_SEND_HISTORY_ID", "COMPANY_ID", "KAKAO_TEMPLATE_ID", "TARGET_TYPE_CD", "TARGET_ID", "RECEIVER_NM",
    "RECEIVER_PHONE", "MESSAGE", "SEND_PRICE", "SEND_STATUS_CD", "ALIGO_MID", "RESULT_CODE",
    "RESULT_MESSAGE", "SEND_DT", "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
MAP_HEADERS = [
    "CAREPLE_MSG_ID", "CAREPLE_VIS_ID", "MEMBER_ID", "RECEIVER_PHONE", "SEND_TYPE_CD", "LOCAL_HISTORY_ID", "SEND_DT", "SEND_PRICE",
]
UNMATCHED_HEADERS = ["TYPE", "CAREPLE_MSG_ID", "CAREPLE_VIS_ID", "RECEIVER_PHONE", "DETAIL"]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_dt(value):
    value = str(value or "").strip().replace("T", " ").replace("Z", "")
    if not value:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return value


def parse_dt(value):
    text = normalize_dt(value)
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def phone(value):
    return "".join(character for character in str(value or "") if character.isdigit())


def option_to_type(value):
    option = str(value or "").strip().lower()
    if option == "alimtalk":
        return "KAKAO"
    if option == "lms":
        return "LMS"
    if option == "sms":
        return "SMS"
    return ""


def status_to_cd(value):
    value = str(value or "").strip().lower()
    if value in ("success", "sent", "complete", "completed"):
        return "SUCCESS"
    if value in ("wait", "waiting", "processing", "pending"):
        return "WAIT"
    return "FAIL"


def request_json(url, method, payload=None):
    tuid = next((x.split("=", 1)[1].strip() for x in COOKIE.split(";") if x.strip().startswith("tuid=")), "")
    headers = {
        "Accept": "*/*", "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.careplecenter.com/index.html",
        "Origin": "https://www.careplecenter.com", "Cookie": COOKIE, "tuid": tuid,
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < RETRY_COUNT:
                wait_seconds = min(30, attempt * 3)
                print(f"요청 실패 {attempt}/{RETRY_COUNT}: {url} / {wait_seconds}초 후 재시도")
                time.sleep(wait_seconds)
    raise RuntimeError(f"API 호출 실패: {url} / {last_error}")


def load_member_map():
    if not MEMBER_MAP_PATH.exists():
        raise FileNotFoundError(f"이용자 매핑 파일이 없습니다: {MEMBER_MAP_PATH.resolve()}")
    result = {}
    with open(MEMBER_MAP_PATH, encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            source_id = str(row.get("CAREPLE_VIS_ID") or row.get("VIS_ID") or row.get("ASIS_VIS_ID") or "").strip()
            member_id = str(row.get("MEMBER_ID") or "").strip()
            if source_id and member_id:
                result[source_id] = member_id
    if not result:
        raise ValueError(f"{MEMBER_MAP_PATH.name}에서 CAREPLE_VIS_ID/MEMBER_ID 매핑을 찾지 못했습니다.")
    return result


def load_use_candidates():
    if not USE_MAP_PATH.exists():
        print("사용잔액 매핑 파일이 없어 발송가격은 0으로 생성합니다. 먼저 export_careple_message_balance_use.py를 실행하면 가격을 연결합니다.")
        return []
    rows = []
    with open(USE_MAP_PATH, encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            dt = parse_dt(row.get("USED_DT"))
            if dt:
                rows.append({"id": row.get("CAREPLE_USE_ID", ""), "type": row.get("SEND_TYPE_CD", ""),
                             "amount": int(float(row.get("AMOUNT") or 0)), "dt": dt, "used": False})
    return rows


def find_send_price(candidates, send_type, sent_at):
    # Careple use API에는 msgId가 없으므로 동일 유형 중 가장 가까운 미사용 거래만 연결한다.
    # 5분 밖의 거래는 추정하지 않고 0으로 남긴다.
    when = parse_dt(sent_at)
    if when is None:
        return 0, ""
    matched, distance = None, None
    for candidate in candidates:
        if candidate["used"] or candidate["type"] != send_type:
            continue
        seconds = abs((candidate["dt"] - when).total_seconds())
        if seconds <= 300 and (distance is None or seconds < distance):
            matched, distance = candidate, seconds
    if matched is None:
        return 0, ""
    matched["used"] = True
    return matched["amount"], matched["id"]


def list_messages():
    all_rows, page, total_page = [], 1, None
    msg_types = [
        "VIS_SCHED_ADD", "VIS_SCHED_UPDATE", "VIS_SCHED_DELETE", "VIS_SCHED_REPEAT_ADD", "VIS_SCHED_REPEAT_UPDATE",
        "VIS_SCHED_REPEAT_DELETE", "VIS_SCHED_STAT_CHANGE", "VIS_SCHED_CLS_AUTO_DONE", "VIS_SCHED_CONS_AUTO_DONE",
        "VIS_SCHED_DAILY", "VIS_SCHED_NEXT_DAILY_1", "VIS_SCHED_NEXT_DAILY_2", "VIS_POST_ADD",
    ]
    while total_page is None or page <= total_page:
        payload = {
            "page": page, "limit": PAGE_SIZE, "empIdList": None, "visIdList": None, "msgTypeList": msg_types,
            "msgSendOptionList": ["SEND", "RE_SEND", "STORE", "SEND_AF_STORE"],
            "msgRcvOptionList": ["careple", "alimTalk", "lms", "sms"], "msgResultOptionList": [],
            "startTime": START_TIME, "endTime": END_TIME,
        }
        response = request_json(LIST_URL, "PUT", payload)
        data = response.get("data") or {}
        if total_page is None:
            total_page = int(data.get("totalPage") or 0)
        page_rows = data.get("list") or []
        all_rows.extend(page_rows)
        print(f"[{now_text()}] 메시지 목록 {page}/{total_page} / {len(page_rows)}건")
        if not page_rows or page >= total_page:
            break
        page += 1
    return all_rows


def main():
    if not COOKIE.strip():
        raise ValueError("COOKIE에 최신 Careple 로그인 쿠키를 넣어주세요.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    member_map = load_member_map()
    use_candidates = load_use_candidates()
    list_rows = list_messages()
    unique_list = {str(row.get("msgId") or "").strip(): row for row in list_rows if str(row.get("msgId") or "").strip()}

    def fetch_detail(item):
        msg_id, summary = item
        org_id = ((summary.get("orgInfo") or {}).get("id") or "")
        response = request_json(DETAIL_URL.format(msg_id=msg_id), "PUT", {"orgId": org_id})
        return msg_id, response.get("data") or {}

    details, failures, completed = {}, [], 0
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(fetch_detail, item): item[0] for item in unique_list.items()}
        for future in as_completed(futures):
            msg_id = futures[future]
            try:
                result_id, data = future.result()
                details[result_id] = data
            except Exception as error:
                failures.append({"TYPE": "DETAIL_ERROR", "CAREPLE_MSG_ID": msg_id, "CAREPLE_VIS_ID": "", "RECEIVER_PHONE": "", "DETAIL": str(error)})
            completed += 1
            if completed % 25 == 0 or completed == len(unique_list):
                print(f"[{now_text()}] 메시지 상세 {completed}/{len(unique_list)} (동시작업 {DETAIL_WORKERS})")

    sms_rows, kakao_rows, map_rows, unmatched = [], [], [], failures[:]
    sms_seq, kakao_seq = 1, 1
    tobe_rows = []
    for msg_id, summary in unique_list.items():
        detail = details.get(msg_id)
        if not detail:
            continue
        sent_dt = normalize_dt(summary.get("sendTime"))
        contents = {str(item.get("msgRcvOption") or "").lower(): item for item in (detail.get("msgContentList") or [])}
        for visitor in detail.get("visInfoList") or []:
            vis_id = str(visitor.get("visId") or "").strip()
            member_id = member_map.get(vis_id, "")
            if not member_id:
                unmatched.append({"TYPE": "MEMBER", "CAREPLE_MSG_ID": msg_id, "CAREPLE_VIS_ID": vis_id, "RECEIVER_PHONE": "", "DETAIL": "member_id_map.csv 미매핑"})
                continue
            for receiver in visitor.get("receiverInfoList") or []:
                receiver_option = str(receiver.get("msgRcvOption") or "").lower()
                type_cd = option_to_type(receiver_option)
                receiver_phone = phone(receiver.get("telNum"))
                if not type_cd:
                    unmatched.append({"TYPE": "UNSUPPORTED_CHANNEL", "CAREPLE_MSG_ID": msg_id, "CAREPLE_VIS_ID": vis_id,
                                      "RECEIVER_PHONE": receiver_phone, "DETAIL": receiver_option})
                    continue
                content_item = contents.get(receiver_option) or next(iter(contents.values()), {})
                message = str(content_item.get("content") or "")
                if not receiver_phone or not message:
                    unmatched.append({"TYPE": "REQUIRED_VALUE", "CAREPLE_MSG_ID": msg_id, "CAREPLE_VIS_ID": vis_id,
                                      "RECEIVER_PHONE": receiver_phone, "DETAIL": "수신번호 또는 본문 없음"})
                    continue
                send_price, use_id = find_send_price(use_candidates, type_cd, sent_dt)
                status_cd = status_to_cd(receiver.get("status"))
                common = {
                    "COMPANY_ID": COMPANY_ID, "TARGET_TYPE_CD": "MEMBER", "TARGET_ID": member_id,
                    "RECEIVER_NM": receiver.get("name") or "", "RECEIVER_PHONE": receiver_phone, "MESSAGE": message,
                    "SEND_PRICE": send_price, "SEND_STATUS_CD": status_cd, "ALIGO_MID": "",
                    "RESULT_CODE": receiver.get("status") or "", "RESULT_MESSAGE": receiver.get("desc") or "",
                    "SEND_DT": sent_dt, "COMPLETE_DT": sent_dt if status_cd == "SUCCESS" else "",
                    "USE_YN": "Y", "DELETE_YN": "N", "CREATE_DT": sent_dt, "UPDATE_DT": sent_dt,
                }
                if type_cd == "KAKAO":
                    history_id = f"KAKAO{ kakao_seq:08d}"
                    kakao_seq += 1
                    row = {"KAKAO_SEND_HISTORY_ID": history_id, "KAKAO_TEMPLATE_ID": KAKAO_TEMPLATE_ID, **common}
                    kakao_rows.append(row)
                else:
                    history_id = f"SMSH{sms_seq:08d}"
                    sms_seq += 1
                    row = {"SMS_SEND_HISTORY_ID": history_id, "SEND_TYPE_CD": type_cd, **common}
                    sms_rows.append(row)
                tobe_rows.append({"carepleMsgId": msg_id, "carepleUseId": use_id, "history": row})
                map_rows.append({
                    "CAREPLE_MSG_ID": msg_id, "CAREPLE_VIS_ID": vis_id, "MEMBER_ID": member_id,
                    "RECEIVER_PHONE": receiver_phone, "SEND_TYPE_CD": type_cd, "LOCAL_HISTORY_ID": history_id,
                    "SEND_DT": sent_dt, "SEND_PRICE": send_price,
                })

    with open(OUTPUT_DIR / "message_asis_list_raw.json", "w", encoding="utf-8") as file:
        json.dump(list(unique_list.values()), file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_asis_detail_raw.json", "w", encoding="utf-8") as file:
        json.dump(details, file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "message_tobe_all.json", "w", encoding="utf-8") as file:
        json.dump(tobe_rows, file, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "sms_send_history.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=SMS_HEADERS)
        writer.writeheader(); writer.writerows(sms_rows)
    with open(OUTPUT_DIR / "kakao_send_history.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=KAKAO_HEADERS)
        writer.writeheader(); writer.writerows(kakao_rows)
    with open(OUTPUT_DIR / "message_id_map.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=MAP_HEADERS)
        writer.writeheader(); writer.writerows(map_rows)
    with open(OUTPUT_DIR / "message_unmatched_map.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=UNMATCHED_HEADERS)
        writer.writeheader(); writer.writerows(unmatched)
    with open(OUTPUT_DIR / "message_export_summary.json", "w", encoding="utf-8") as file:
        json.dump({"source_message_count": len(unique_list), "detail_count": len(details), "sms_count": len(sms_rows),
                   "kakao_count": len(kakao_rows), "unmatched_count": len(unmatched)}, file, ensure_ascii=False, indent=2)
    print(f"완료: SMS/LMS {len(sms_rows)}건, 카카오 {len(kakao_rows)}건, 미매핑 {len(unmatched)}건")


if __name__ == "__main__":
    main()
