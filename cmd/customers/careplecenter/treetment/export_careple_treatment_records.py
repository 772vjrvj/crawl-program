"""Careple 재활 회기기록 이관 + 첨부 원본 다운로드 (추가 pip 설치 불필요).

사용 방법
  1. 기존 output 폴더를 백업하고 아래 COOKIE에 최신 로그인 쿠키 전체를 입력합니다.
  2. 기존 회원/선생님/프로그램/스케줄 매핑 CSV가 있는 작업 폴더에서 실행합니다.
  3. 첨부 저장 위치: output/treatment_record/files/<Careple 회기ID>/<fileId>/<원본파일명>
  4. 연결표: treatment_record_files.csv / 실패 목록: treatment_record_files_failed.csv
  5. 목록 조회 시점 이후 추가된 첨부도 받으려면 REFRESH_MONTHLY_LIST = True로 바꿉니다.

기존 CSV 컬럼·회기기록 생성 조건·ID 생성 방식은 유지합니다.
내용 없는 회기/필수 매핑 누락으로 기록이 제외되어도 그 회기의 첨부는 다운로드합니다.
그 경우 연결표의 TREATMENT_RECORD_ID는 공란이며 SCHEDULE_ID는 가능한 경우 기록합니다.
완료 파일의 크기·SHA256·원본 변경일이 일치하면 다시 다운로드하지 않습니다.

기존 동작과 같이 CSV 결과는 다시 생성됩니다. 원본 데이터/조회 순서가 바뀌면 순번형
ID도 달라질 수 있으므로 이미 적재한 DB에 CSV를 무조건 재적재하지 마세요.
첨부파일은 로컬에 저장하며 별도 첨부 테이블에 자동 INSERT하지는 않습니다.
"""

import csv
import hashlib
import json
import random
import re
import tempfile
import time
from datetime import datetime, timedelta
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = ""  # 최신 Cookie 전체를 입력하세요. 다운로드용 tuid도 여기서 자동 추출합니다.
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2027-06"  # 스케줄 이관 범위와 같게 유지
TREATMENT_RECORD_ID_LAST_NO = 0

# False면 이전 목록 캐시를 사용합니다.
# 특정 월만 최신 조회하려면 output/treatment_record/_checkpoint/monthly/2026_09.json만 삭제합니다.
REFRESH_MONTHLY_LIST = False
# 이전 캐시에 fileList가 없는 경우에는 자동으로 해당 월을 다시 조회합니다.
# 캐시 생성 뒤 추가/변경된 첨부까지 반영하려면 위 값을 True로 바꾸세요.

DOWNLOAD_FILES = True
FILE_TIMEOUT = 120
FILE_REQUEST_DELAY = 0.2  # 첨부는 순차 다운로드합니다.

BASE_URL = "https://www.careplecenter.com"
LIST_URL = BASE_URL + "/pcareple/v1/classes"
FILE_URL = BASE_URL + "/pcareple/v1/files/"

MEMBER_DIR = Path("output/member")
TEACHER_DIR = Path("output/teacher")
PROGRAM_DIR = Path("output/program")
SCHEDULE_DIR = Path("output/schedule")
OUTPUT_DIR = Path("output/treatment_record")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"

TREATMENT_HEADERS = [
    "TREATMENT_RECORD_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID", "PROGRAM_ID",
    "TREATMENT_STATUS_CD", "COUNSEL_CONTENT", "RECORD_CONTENT", "SPECIAL_NOTE", "PARENT_COMMENT",
    "NEXT_PLAN", "MEMO", "TREATMENT_DT", "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT",
]
TREATMENT_MAP_HEADERS = [
    "CAREPLE_CLASS_ID", "TREATMENT_RECORD_ID", "SCHEDULE_ID",
    "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID",
]
UNMATCHED_HEADERS = ["CAREPLE_CLASS_ID", "FIELD", "SOURCE_VALUE", "MESSAGE"]
ORIGIN_HEADERS = [
    "회기ID", "이용자", "프로그램", "담당선생님", "일시", "상태", "상담내용",
    "기록내용", "특이사항", "보호자전달", "다음계획", "메모",
]
FILE_HEADERS = [
    "CAREPLE_CLASS_ID", "TREATMENT_RECORD_ID", "SCHEDULE_ID", "CAREPLE_FILE_ID",
    "ORIGINAL_FILE_NAME", "SAVED_FILE_NAME", "MIME_TYPE", "SOURCE_SIZE_KB",
    "SOURCE_LAST_MOD_DT", "LOCAL_PATH", "STATUS", "BYTES", "SHA256", "ERROR",
]


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


def later_date_time(*items):
    dates = [date_time(item) for item in items if value(item)]
    return max(dates) if dates else ""


def month_range(start_ym, end_ym):
    year, month = map(int, start_ym.split("-"))
    end_year, end_month = map(int, end_ym.split("-"))
    while (year, month) <= (end_year, end_month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def last_day(year, month):
    if month == 12:
        return "31"
    return (datetime(year, month + 1, 1) - timedelta(days=1)).strftime("%d")


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def checkpoint_path(kind, name):
    safe = "".join(char if char.isalnum() else "_" for char in str(name))
    path = CHECKPOINT_DIR / kind / f"{safe}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def request_retry(request_once, label):
    waits = (5, 15, 30, 60, 120, 300)
    for attempt in range(len(waits) + 1):
        try:
            return request_once()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, HTTPError) and error.code in (401, 403):
                raise  # 로그인/권한 실패는 반복 요청하지 않습니다.
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


def csv_mapping(rows, source_column, target_column):
    result = {}
    for row in rows:
        source, target = value(row.get(source_column)), value(row.get(target_column))
        if not source or not target:
            continue
        previous = result.get(source)
        if previous and previous != target:
            raise ValueError(f"매핑 CSV 원본 ID 중복: {source}")
        result[source] = target
    return result


def load_maps():
    paths = [
        (MEMBER_DIR / "member_id_map.csv", "MEMBER"),
        (TEACHER_DIR / "employee_id_map.csv", "TEACHER"),
        (PROGRAM_DIR / "program_id_map.csv", "PROGRAM"),
        (SCHEDULE_DIR / "schedule_id_map.csv", "SCHEDULE"),
    ]
    for path, name in paths:
        if not path.exists():
            raise FileNotFoundError(f"{path} 파일이 없습니다. {name} 이관을 먼저 실행하세요.")

    member_rows = read_csv(MEMBER_DIR / "member_id_map.csv")
    teacher_rows = read_csv(TEACHER_DIR / "employee_id_map.csv")
    program_rows = read_csv(PROGRAM_DIR / "program_id_map.csv")
    schedule_rows = read_csv(SCHEDULE_DIR / "schedule_id_map.csv")

    schedule_by_class_id = {}
    for row in schedule_rows:
        if value(row.get("SCHEDULE_TYPE_CD")) != "CLS":
            continue
        schedule_id = value(row.get("SCHEDULE_ID"))
        for class_id in (value(row.get("CAREPLE_EVENT_ID")), value(row.get("CAREPLE_DETAIL_ID"))):
            if not class_id or not schedule_id:
                continue
            previous = schedule_by_class_id.get(class_id)
            if previous and previous != schedule_id:
                raise ValueError(f"회기 원본 일정 ID가 둘 이상 매핑됩니다: {class_id}")
            schedule_by_class_id[class_id] = schedule_id

    return {
        "member": csv_mapping(member_rows, "CAREPLE_VIS_ID", "MEMBER_ID"),
        "teacher": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "TEACHER_ID"),
        "program": csv_mapping(program_rows, "CAREPLE_PROGRAM_ID", "PROGRAM_ID"),
        "schedule": schedule_by_class_id,
    }


def fetch_month_list(year, month):
    ym = f"{year:04d}_{month:02d}"
    path = checkpoint_path("monthly", ym)
    if not REFRESH_MONTHLY_LIST:
        cached = read_json(path)
        if cached is not None:
            if (not DOWNLOAD_FILES or all(isinstance(row, dict) and "fileList" in row
                                          for row in cached.get("data") or [])):
                return cached
            print(f"[캐시 보완] {year:04d}-{month:02d}: fileList가 없어 목록을 다시 조회합니다.")

    rows, pages, page_token = [], [], ""
    seen_tokens = set()
    while True:
        params = {
            "searchSd": f"{year:04d}-{month:02d}-01",
            "searchEd": f"{year:04d}-{month:02d}-{last_day(year, month)}",
            "searchVisDiv": "VIS_ID", "searchVisKeyword": "",
            "searchEmpDiv": "EMP_ID", "searchEmpKeyword": "",
            "searchPgmDiv": "PGM_CAT", "searchPgmKeyword": "",
            "searchStatDivCds": "R D C S F ",
            "orderColumn": "clsDate", "orderDir": "asc", "maxLength": "100",
            "pageToken": page_token, "randid": str(random.random()),
        }
        response = get_json(LIST_URL, params)
        body = response.get("data") if isinstance(response, dict) else None
        if (not isinstance(body, dict) or not isinstance(body.get("data"), list)
                or any(not isinstance(row, dict) or not value(row.get("clsId")) for row in body["data"])):
            write_json(checkpoint_path("list_errors", ym), response)
            raise ValueError("회기 목록 응답이 예상한 data.data 배열이 아닙니다. 쿠키/응답을 확인하세요.")
        if response.get("resultCode", 20000) != 20000:
            raise ValueError("회기 목록 API가 실패 상태를 반환했습니다. 쿠키/응답을 확인하세요.")
        if "nextPageToken" not in body:
            write_json(checkpoint_path("list_errors", ym), response)
            raise ValueError("목록 응답에 nextPageToken이 없습니다. 누락 방지를 위해 중단합니다.")
        page_rows = body["data"]
        pages.append(response)
        rows.extend(page_rows)
        page_token = value(body.get("nextPageToken"))
        if not page_token:
            break
        if page_token in seen_tokens or not page_rows:
            raise ValueError("회기 목록의 페이지 토큰이 반복되거나 빈 페이지에 다음 토큰이 있습니다.")
        seen_tokens.add(page_token)

    result = {"year": year, "month": month, "pages": pages, "data": rows}
    write_json(path, result)
    return result


def has_treatment_record(source):
    """내용이 없는 일정에는 빈 회기기록을 만들지 않는다. objCont는 원본 JSON에만 남긴다."""
    record = source.get("clsRecord") or {}
    fields = (
        record.get("conslCont"), source.get("cmtCont"), source.get("subjCont"),
        source.get("assmCont"), source.get("planCont"),
        (source.get("reinfTgtClsInfoMap") or {}).get("memo"),
    )
    return any(value(item) for item in fields)


def validate(rows):
    required = ("TREATMENT_RECORD_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID")
    for line_no, row in enumerate(rows, start=2):
        missing = [column for column in required if not value(row.get(column))]
        if missing:
            raise ValueError(f"TREATMENT_RECORD_MASTER CSV {line_no}행 NOT NULL 값 누락: {', '.join(missing)}")


class FileAuthenticationError(RuntimeError):
    pass


class SameOriginRedirect(HTTPRedirectHandler):
    """Cookie/tuid를 다른 사이트로 전달하지 않는다."""

    def redirect_request(self, request, fp, code, message, headers, new_url):
        target, origin = urlsplit(new_url), urlsplit(BASE_URL)
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            raise FileAuthenticationError("외부 사이트로 이동하는 응답입니다. 로그인 상태를 확인하세요.")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def file_error_text(error):
    """실패 로그에 다운로드 URL의 세션 토큰을 남기지 않는다."""
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, IncompleteRead):
        return "첨부파일 다운로드가 중간에 끊겼습니다. 다시 실행하세요."
    text = str(error)
    token = HEADERS.get("tuid", "")
    if token:
        text = text.replace(token, "<redacted>")
    return re.sub(r"(?i)(tuid=)[^&\s]+", r"\1<redacted>", text)


def safe_file_name(name, fallback):
    # 한글/공백/괄호/확장자는 유지한다. Windows에서 저장할 수 없는 문자만 바꾼다.
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or fallback)).rstrip(" .")
    if not name or name in (".", ".."):
        name = fallback
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I):
        name = "_" + name
    return name


def safe_id(item):
    text = value(item)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise ValueError("첨부 경로에 사용할 원본 ID가 비어 있거나 올바르지 않습니다.")
    return text


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(class_id, item):
    file_id = safe_id(item.get("fileId"))
    class_id = safe_id(class_id)
    name = safe_file_name(item.get("name"), file_id)
    target = OUTPUT_DIR / "files" / class_id / file_id / name
    checkpoint = checkpoint_path("files", f"{class_id}_{file_id}")
    source_version = {key: item.get(key) for key in ("name", "lastModDtime", "size")}
    cached = read_json(checkpoint)
    if (isinstance(cached, dict) and target.is_file()
            and cached.get("source_version") == source_version
            and cached.get("bytes") == target.stat().st_size
            and cached.get("sha256") == file_sha256(target)):
        return {"STATUS": "EXISTS", "LOCAL_PATH": str(target.resolve()),
                "SAVED_FILE_NAME": name, "BYTES": cached["bytes"], "SHA256": cached["sha256"]}

    tuid = HEADERS.get("tuid", "")
    if not tuid:
        raise FileAuthenticationError("COOKIE에 tuid가 없습니다. 최신 로그인 쿠키를 입력하세요.")
    # HTML의 /pcareple/v1/files/{fileId}?tuid=... 와 동일한 주소를 사용한다.
    url = FILE_URL + file_id + "?" + urlencode({"tuid": tuid})
    headers = dict(HEADERS, Accept="*/*", **{"Accept-Encoding": "identity"})
    target.parent.mkdir(parents=True, exist_ok=True)

    def request_once():
        part = None
        try:
            opener = build_opener(SameOriginRedirect())
            with opener.open(Request(url, headers=headers), timeout=FILE_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise ValueError(f"첨부 응답 상태가 200이 아닙니다: {response.getcode()}")
                content_type = response.headers.get("Content-Type", "").lower()
                expected_type = value(item.get("type")).lower()
                first = response.read(8192)
                sniff = first.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
                looks_html = "text/html" in content_type or sniff.startswith((b"<!doctype html", b"<html"))
                looks_json = "json" in content_type or sniff.startswith((b"{", b"["))
                if looks_html and expected_type != "text/html" and target.suffix.lower() not in (".html", ".htm"):
                    raise FileAuthenticationError("파일 대신 HTML 응답을 받았습니다. 로그인 쿠키/다운로드 권한을 확인하세요.")
                if looks_json and "json" not in expected_type and target.suffix.lower() != ".json":
                    raise ValueError("파일 대신 JSON 응답을 받았습니다. 세션 또는 파일 접근 권한을 확인하세요.")
                digest, byte_count = hashlib.sha256(), 0
                with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".download_", suffix=".part", delete=False) as file:
                    part = Path(file.name)
                    chunk = first
                    while chunk:
                        file.write(chunk)
                        digest.update(chunk)
                        byte_count += len(chunk)
                        chunk = response.read(1024 * 1024)
                if not byte_count:
                    raise ValueError("빈 첨부파일 응답입니다.")
                length = response.headers.get("Content-Length")
                if length is not None and byte_count != int(length):
                    raise ConnectionError("첨부파일 다운로드가 중간에 끊겼습니다.")
                # source.size는 예: 279.5(kB)인 표시값. 바이트 수로 변환해 비교하지 않는다.
                part.replace(target)
                write_json(checkpoint, {
                    "source_version": source_version, "bytes": byte_count, "sha256": digest.hexdigest(),
                })
                return {"STATUS": "DOWNLOADED", "LOCAL_PATH": str(target.resolve()),
                        "SAVED_FILE_NAME": name, "BYTES": byte_count, "SHA256": digest.hexdigest()}
        except HTTPError as error:
            if error.code in (401, 403):
                raise FileAuthenticationError(f"HTTP {error.code}: 최신 쿠키/첨부 다운로드 권한을 확인하세요.") from None
            if error.code == 404:
                raise ValueError("HTTP 404: 첨부파일을 찾을 수 없습니다.") from None
            raise
        except IncompleteRead:
            raise ConnectionError("첨부파일 다운로드가 중간에 끊겼습니다.") from None
        finally:
            if part is not None and part.exists():
                part.unlink()  # 이번 시도에서 만든 미완성 임시 파일만 정리한다.

    return request_retry(request_once, f"첨부 fileId={file_id}")


def export_files(classes_by_id, treatment_map_rows, mapping):
    """CSV 적재 대상 여부와 무관하게 조회된 모든 회기의 첨부파일을 수집한다."""
    record_by_class = {row["CAREPLE_CLASS_ID"]: row for row in treatment_map_rows}
    jobs, list_errors = [], []
    for class_id, source in classes_by_id.items():
        if "fileList" not in source:
            list_errors.append({"CAREPLE_CLASS_ID": class_id, "ERROR": "fileList 없음. 최신 목록을 다시 조회하세요."})
            continue
        raw_files = source.get("fileList") or []
        if not isinstance(raw_files, list) or any(not isinstance(item, dict) for item in raw_files):
            list_errors.append({"CAREPLE_CLASS_ID": class_id, "ERROR": "fileList가 파일 객체 배열이 아닙니다."})
            continue
        files = {}
        for index, item in enumerate(raw_files):
            key = value(item.get("fileId")) or f"missing_id_{index}"
            files[key] = item
        jobs.extend((class_id, item) for item in files.values())

    results, auth_error = [], ""
    for number, (class_id, item) in enumerate(jobs, 1):
        mapped = record_by_class.get(class_id, {})
        result = {
            "CAREPLE_CLASS_ID": class_id,
            "TREATMENT_RECORD_ID": mapped.get("TREATMENT_RECORD_ID", ""),
            "SCHEDULE_ID": mapped.get("SCHEDULE_ID") or mapping["schedule"].get(class_id, ""),
            "CAREPLE_FILE_ID": value(item.get("fileId")),
            "ORIGINAL_FILE_NAME": item.get("name") or "",
            "MIME_TYPE": item.get("type") or "", "SOURCE_SIZE_KB": item.get("size") or "",
            "SOURCE_LAST_MOD_DT": item.get("lastModDtime") or "", "ERROR": "",
        }
        try:
            if auth_error:
                result.update(STATUS="SKIPPED_AUTH", ERROR=auth_error)
            else:
                result.update(download_file(class_id, item))
        except FileAuthenticationError as error:
            auth_error = file_error_text(error)
            result.update(STATUS="FAILED", ERROR=auth_error)
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
            result.update(STATUS="FAILED", ERROR=file_error_text(error))
        results.append(result)
        print(f"[첨부 {number}/{len(jobs)}] {result['STATUS']} / fileId={result['CAREPLE_FILE_ID']} / {result['ORIGINAL_FILE_NAME']}" +
              (f" / {result['ERROR']}" if result["ERROR"] else ""))
        write_csv(OUTPUT_DIR / "treatment_record_files.csv", FILE_HEADERS, results)
        if not auth_error and result["STATUS"] != "EXISTS":
            time.sleep(FILE_REQUEST_DELAY)

    write_csv(OUTPUT_DIR / "treatment_record_files.csv", FILE_HEADERS, results)
    failed = [row for row in results if row["STATUS"] not in ("DOWNLOADED", "EXISTS")]
    write_csv(OUTPUT_DIR / "treatment_record_files_failed.csv", FILE_HEADERS, failed)
    write_json(OUTPUT_DIR / "treatment_record_file_list_errors.json", list_errors)
    return {
        "file_count": len(jobs),
        "file_downloaded_count": sum(row["STATUS"] == "DOWNLOADED" for row in results),
        "file_existing_count": sum(row["STATUS"] == "EXISTS" for row in results),
        "file_failed_count": len(failed), "file_list_error_count": len(list_errors),
        "files_complete": not failed and not list_errors,
    }


def main():
    if not COOKIE.strip():
        raise ValueError("상단 COOKIE에 최신 쿠키를 입력하세요.")

    global HEADERS
    tuid = next((item.split("=", 1)[1].strip() for item in COOKIE.split(";") if item.strip().startswith("tuid=")), "")
    if DOWNLOAD_FILES and not tuid:
        raise ValueError("COOKIE에 다운로드에 필요한 tuid가 없습니다. 최신 로그인 쿠키 전체를 입력하세요.")
    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": BASE_URL + "/index.html",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE,
        "tuid": tuid,
    }

    mapping = load_maps()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    migration_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    monthly_raw, classes_by_id = [], {}
    for year, month in month_range(START_YM, END_YM):
        result = fetch_month_list(year, month)
        monthly_raw.append(result)
        for row in result.get("data") or []:
            class_id = value(row.get("clsId"))
            if class_id:
                classes_by_id[class_id] = row
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 목록 {year:04d}-{month:02d}: {len(result.get('data') or [])}건")

    treatment_rows, treatment_map_rows, unmatched, tobe_all = [], [], [], []
    for class_id, source in classes_by_id.items():
        if not has_treatment_record(source):
            tobe_all.append({"carepleClassId": class_id, "source": source, "excluded": True, "reason": "회기기록 내용 없음"})
            continue

        vis_id = value(source.get("visId"))
        emp_id = value(source.get("clsMgrEmpId"))
        pgm_id = value(source.get("pgmId"))
        member_id = mapping["member"].get(vis_id, "")
        teacher_id = mapping["teacher"].get(emp_id, "")
        program_id = mapping["program"].get(pgm_id, "")
        schedule_id = mapping["schedule"].get(class_id, "")
        for field, source_id, target in (
            ("SCHEDULE_ID", class_id, schedule_id),
            ("MEMBER_ID", vis_id, member_id),
            ("TEACHER_ID", emp_id, teacher_id),
            ("PROGRAM_ID", pgm_id, program_id),
        ):
            if not target:
                unmatched.append({"CAREPLE_CLASS_ID": class_id, "FIELD": field, "SOURCE_VALUE": source_id, "MESSAGE": "매핑 없음"})

        # PROGRAM_ID는 nullable이나, 추후 추적 가능하도록 매핑 실패 건은 파일에 남긴 채 적재한다.
        if not schedule_id or not member_id or not teacher_id:
            tobe_all.append({"carepleClassId": class_id, "source": source, "excluded": True, "reason": "NOT NULL 매핑 없음"})
            continue

        record = source.get("clsRecord") or {}
        status = value(source.get("clsStatDivCd")) or "R"
        treatment_dt = date_time(f"{value(source.get('clsDate'))} {value(source.get('clsSt'))}")
        complete_dt = later_date_time(source.get("soapLastModDtime"), source.get("lastModDtime")) if status == "D" else ""
        treatment_id = f"TREATMENT_RECORD{TREATMENT_RECORD_ID_LAST_NO + len(treatment_rows) + 1:08d}"
        row = {
            "TREATMENT_RECORD_ID": treatment_id,
            "SCHEDULE_ID": schedule_id,
            "COMPANY_ID": COMPANY_ID,
            "MEMBER_ID": member_id,
            "TEACHER_ID": teacher_id,
            "PROGRAM_ID": program_id,
            "TREATMENT_STATUS_CD": status,
            "COUNSEL_CONTENT": value(record.get("conslCont")),
            "RECORD_CONTENT": value(source.get("cmtCont")),
            "SPECIAL_NOTE": value(source.get("assmCont")),
            "PARENT_COMMENT": value(source.get("subjCont")),
            "NEXT_PLAN": value(source.get("planCont")),
            "MEMO": value((source.get("reinfTgtClsInfoMap") or {}).get("memo")),
            "TREATMENT_DT": treatment_dt,
            "COMPLETE_DT": complete_dt,
            "USE_YN": "Y",
            "DELETE_YN": "N",
            "CREATE_DT": date_time(source.get("regDtime")) or migration_dt,
            "UPDATE_DT": later_date_time(source.get("lastModDtime"), source.get("soapLastModDtime")),
        }
        treatment_rows.append(row)
        treatment_map_rows.append({
            "CAREPLE_CLASS_ID": class_id, "TREATMENT_RECORD_ID": treatment_id, "SCHEDULE_ID": schedule_id,
            "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id, "CAREPLE_EMP_ID": emp_id,
        })
        tobe_all.append({"carepleClassId": class_id, "source": source, "tobe": row, "excluded": False})

    validate(treatment_rows)
    origin_rows = []
    for class_id, source in classes_by_id.items():
        record = source.get("clsRecord") or {}
        origin_rows.append({
            "회기ID": class_id, "이용자": value(source.get("visNm")), "프로그램": value(source.get("pgmNm")),
            "담당선생님": value(source.get("clsMgrEmp")),
            "일시": date_time(f"{value(source.get('clsDate'))} {value(source.get('clsSt'))}"),
            "상태": value(source.get("clsStatDivNm")), "상담내용": value(record.get("conslCont")),
            "기록내용": value(source.get("cmtCont")), "특이사항": value(source.get("assmCont")),
            "보호자전달": value(source.get("subjCont")), "다음계획": value(source.get("planCont")),
            "메모": value((source.get("reinfTgtClsInfoMap") or {}).get("memo")),
        })

    write_csv(OUTPUT_DIR / "treatment_record_origin.csv", ORIGIN_HEADERS, origin_rows)
    write_csv(OUTPUT_DIR / "treatment_record_db.csv", TREATMENT_HEADERS, treatment_rows)
    write_csv(OUTPUT_DIR / "treatment_record_id_map.csv", TREATMENT_MAP_HEADERS, treatment_map_rows)
    write_csv(OUTPUT_DIR / "treatment_record_unmatched_map.csv", UNMATCHED_HEADERS, unmatched)
    (OUTPUT_DIR / "treatment_record_asis_raw.json").write_text(json.dumps(monthly_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "treatment_record_tobe_all.json").write_text(json.dumps(tobe_all, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "class_count": len(classes_by_id), "treatment_record_count": len(treatment_rows),
        "unmatched_count": len(unmatched), "start_ym": START_YM, "end_ym": END_YM,
    }
    if DOWNLOAD_FILES:
        summary.update(export_files(classes_by_id, treatment_map_rows, mapping))
    else:
        summary.update(files_complete=False, file_download_disabled=True)
    (OUTPUT_DIR / "treatment_record_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CSV 이관 결과: " + json.dumps(summary, ensure_ascii=False))
    if DOWNLOAD_FILES and not summary["files_complete"]:
        print("주의: 첨부 처리가 미완료입니다. treatment_record_files_failed.csv / treatment_record_file_list_errors.json을 확인하세요.")


if __name__ == "__main__":
    main()
