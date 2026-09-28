"""Careple 상담/평가 CSV 이관 + 첨부 원본 다운로드 (Python 표준 라이브러리만 사용).

1. 아래 COOKIE에 최신 로그인 쿠키 전체를 입력하고 기존 이관 폴더에서 실행하세요.
2. 회원/선생님/프로그램/스케줄 매핑 CSV와 상담 CSV 컬럼/ID 생성 규칙은 그대로입니다.
3. 파일: output/consult/files/<Careple 상담ID>/<fileId>/<원본파일명>
4. 연결표: consult_files.csv / 실패: consult_files_failed.csv
   목록 보완 조회 오류: consult_file_list_errors.json
5. 다시 실행하면 크기·SHA256·원본 변경일이 일치하는 완료 파일은 건너뜁니다.
   임의의 URL이 아닌 /files/{fileId}?tuid=현재쿠키값 으로 다운로드합니다.

첨부파일 연결표는 확인/후속 이관용입니다. 별도 첨부 테이블에 자동 INSERT하지 않습니다.
실행 전 기존 output 폴더를 백업하세요. 기존 동작과 같이 CSV 결과 파일은 재생성됩니다.
"""

import csv
import hashlib
import json
import random
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

# 여기만 입력/확인하면 됩니다.
COOKIE = ""  # 브라우저에서 복사한 최신 Cookie 전체를 입력하세요. tuid도 여기서 추출합니다.
COMPANY_ID = "COMPANY000001"
START_YM = "2024-07"
END_YM = "2027-06"  # 스케줄 이관 범위와 반드시 같게 유지
CONSULT_ID_LAST_NO = 0
DETAIL_WORKERS = 6  # 4~8 사이 권장

# False면 기존 목록 캐시를 재사용합니다.
# 오늘 추가/수정된 상담·평가를 반영하려면 해당 월의 monthly/2026_09.json만 삭제하면 됩니다.
REFRESH_MONTHLY_LIST = False
# 상세는 내용 수정이 있을 수 있어 기본값을 True로 둡니다.
REFRESH_DETAIL = True

# 기존 상담 CSV/ID 생성은 유지하고 첨부파일 다운로드만 추가합니다.
DOWNLOAD_FILES = True
REFRESH_FILE_LIST = True
FILE_PAGE_SIZE = 20
FILE_TIMEOUT = 120
FILE_REQUEST_DELAY = 0.2  # 파일은 순차 다운로드합니다.

BASE_URL = "https://www.careplecenter.com"
LIST_URL = BASE_URL + "/pcareple/v1/counsels/.datatables"
DETAIL_URL = BASE_URL + "/pcareple/v1/counsels/"
FILE_LIST_URL = BASE_URL + "/pcareple/v1/counsels"
FILE_URL = BASE_URL + "/pcareple/v1/files/"

MEMBER_DIR = Path("output/member")
TEACHER_DIR = Path("output/teacher")
PROGRAM_DIR = Path("output/program")
SCHEDULE_DIR = Path("output/schedule")
OUTPUT_DIR = Path("output/consult")
CHECKPOINT_DIR = OUTPUT_DIR / "_checkpoint"

CONSULT_HEADERS = [
    "CONSULT_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID", "PROGRAM_ID",
    "CONSULT_TYPE_CD", "CONSULT_STATUS_CD", "TITLE", "COUNSEL_CONTENT", "MEMO", "CONSULT_DT",
    "COMPLETE_DT", "USE_YN", "DELETE_YN", "CREATE_DT", "UPDATE_DT", "UPDATE_USER_ID",
]
CONSULT_MAP_HEADERS = ["CAREPLE_CONSULT_ID", "CONSULT_ID", "SCHEDULE_ID", "CAREPLE_VIS_ID", "CAREPLE_PROGRAM_ID", "CAREPLE_EMP_ID"]
UNMATCHED_HEADERS = ["CAREPLE_CONSULT_ID", "FIELD", "SOURCE_VALUE", "MESSAGE"]
ORIGIN_HEADERS = ["상담평가ID", "이용자", "프로그램", "담당선생님", "일시", "상태", "내용", "메모"]
FILE_HEADERS = [
    "CAREPLE_CONSULT_ID", "CONSULT_ID", "SCHEDULE_ID", "CAREPLE_FILE_ID",
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
    values = [date_time(item) for item in items if value(item)]
    return max(values) if values else ""


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


def validate(rows):
    required = ("CONSULT_ID", "SCHEDULE_ID", "COMPANY_ID", "MEMBER_ID", "TEACHER_ID")
    for index, row in enumerate(rows, start=2):
        missing = [key for key in required if not value(row.get(key))]
        if missing:
            raise ValueError(f"CONSULT_MASTER CSV {index}행 NOT NULL 값 누락: {', '.join(missing)}")


def checkpoint_path(kind, name):
    safe = "".join(char if char.isalnum() else "_" for char in str(name))
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
            # 로그인/권한 실패를 반복 호출하지 않습니다.
            if isinstance(error, HTTPError) and error.code in (401, 403):
                raise
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
    required_files = [
        (MEMBER_DIR / "member_id_map.csv", "MEMBER"),
        (TEACHER_DIR / "employee_id_map.csv", "TEACHER"),
        (PROGRAM_DIR / "program_id_map.csv", "PROGRAM"),
        (SCHEDULE_DIR / "schedule_id_map.csv", "SCHEDULE"),
    ]
    for path, name in required_files:
        if not path.exists():
            raise FileNotFoundError(f"{path} 파일이 없습니다. {name} 이관을 먼저 실행하세요.")

    member_rows = read_csv(MEMBER_DIR / "member_id_map.csv")
    teacher_rows = read_csv(TEACHER_DIR / "employee_id_map.csv")
    program_rows = read_csv(PROGRAM_DIR / "program_id_map.csv")
    schedule_rows = read_csv(SCHEDULE_DIR / "schedule_id_map.csv")

    schedule_by_careple_id = {}
    for row in schedule_rows:
        if value(row.get("SCHEDULE_TYPE_CD")) != "CSL":
            continue
        schedule_id = value(row.get("SCHEDULE_ID"))
        for source_id in (value(row.get("CAREPLE_EVENT_ID")), value(row.get("CAREPLE_DETAIL_ID"))):
            if not source_id or not schedule_id:
                continue
            previous = schedule_by_careple_id.get(source_id)
            if previous and previous != schedule_id:
                raise ValueError(f"상담 원본 일정 ID가 둘 이상 매핑됩니다: {source_id}")
            schedule_by_careple_id[source_id] = schedule_id

    # 상세 응답에는 최종수정자의 ID가 없고 이름만 있는 경우가 있어, 이름 매핑은 보조로만 사용합니다.
    teacher_name_user = {}
    for row in teacher_rows:
        user_id = value(row.get("USER_ID"))
        for key in ("CAREPLE_EMP_NM", "EMP_NM", "TEACHER_NM"):
            name = value(row.get(key))
            if name and user_id:
                teacher_name_user[name] = user_id

    return {
        "member": csv_mapping(member_rows, "CAREPLE_VIS_ID", "MEMBER_ID"),
        "teacher": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "TEACHER_ID"),
        "teacher_user": csv_mapping(teacher_rows, "CAREPLE_EMP_ID", "USER_ID"),
        "teacher_name_user": teacher_name_user,
        "program": csv_mapping(program_rows, "CAREPLE_PROGRAM_ID", "PROGRAM_ID"),
        "schedule": schedule_by_careple_id,
    }


def fetch_month_list(year, month):
    ym = f"{year:04d}_{month:02d}"
    path = checkpoint_path("monthly", ym)
    if not REFRESH_MONTHLY_LIST:
        cached = read_checkpoint(path)
        if cached is not None:
            return cached

    all_rows, pages, start, draw = [], [], 0, 1
    while True:
        params = {
            "searchSd": f"{year:04d}-{month:02d}-01",
            "searchEd": f"{year:04d}-{month:02d}-{last_day(year, month)}",
            "searchVisDiv": "VIS_ID", "searchVisKeyword": "",
            "searchEmpDiv": "EMP_ID", "searchEmpKeyword": "",
            "searchPgmDiv": "PGM_DIV", "searchPgmKeyword": "",
            "searchStatDivCds": "R D C ", "saveTypeSet": "N", "dt": "",
            "extReq.fullyUseVisCtc": "true", "draw": str(draw), "start": str(start), "length": "100",
            "orderColumn": "conslDate", "orderDir": "asc", "randid": str(random.random()),
        }
        response = get_json(LIST_URL, params)
        page_data = response.get("data") or {}
        rows = page_data.get("data") or []
        pages.append(response)
        all_rows.extend(rows)
        total = int(value(page_data.get("recordsFiltered")) or len(all_rows))
        if not rows or len(all_rows) >= total:
            break
        start += len(rows)
        draw += 1

    result = {"year": year, "month": month, "pages": pages, "data": all_rows}
    write_checkpoint(path, result)
    return result


def fetch_detail(consl_id):
    path = checkpoint_path("detail", consl_id)
    if not REFRESH_DETAIL:
        cached = read_checkpoint(path)
        if cached is not None:
            return cached
    response = get_json(DETAIL_URL + consl_id, {"randid": random.random()})
    write_checkpoint(path, response)
    return response


def resolve_update_user(detail, mapping):
    reg_emp_id = value(detail.get("regEmpId"))
    user_id = mapping["teacher_user"].get(reg_emp_id, "")
    if user_id:
        return user_id

    # 응답의 `contLastModEmp`/`lastModEmp`는 "이름 / 직급" 형식이다.
    for raw_name in (detail.get("contLastModEmp"), detail.get("lastModEmp"), detail.get("regEmp")):
        name = value(raw_name).split(" / ", 1)[0]
        if mapping["teacher_name_user"].get(name):
            return mapping["teacher_name_user"][name]
    return ""


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


def attachment_page(response):
    """목록의 행과 다음 토큰을 분리한다. 토큰을 행 ID로 임의 생성하지 않는다."""
    if not isinstance(response, dict):
        raise ValueError("첨부 목록 응답이 JSON 객체가 아닙니다.")
    payload = response.get("data")
    meta = [response]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        meta.insert(0, payload)
        rows = next((payload[key] for key in ("data", "list", "items", "rows")
                     if isinstance(payload.get(key), list)), None)
    else:
        rows = None
    if rows is None or any(not isinstance(row, dict) for row in rows):
        raise ValueError("첨부 목록의 행 구조를 확인할 수 없습니다. _checkpoint/file_pages 응답을 확인하세요.")

    for item in list(meta):
        for key in ("pagination", "paging"):
            if isinstance(item.get(key), dict):
                meta.append(item[key])
    token = next((value(item.get(key)) for key in ("nextPageToken", "nextToken", "pageToken")
                  for item in meta if value(item.get(key))), "")
    total = next((int(item[key]) for item in meta
                  for key in ("recordsFiltered", "totalCount", "recordsTotal")
                  if value(item.get(key)).isdigit()), None)
    has_more = next((str(item[key]).lower() in ("true", "1", "y") for item in meta
                     for key in ("hasNext", "hasMore") if item.get(key) is not None), None)
    return rows, token, total, has_more


def fetch_file_month(year, month):
    """fileList가 기존 목록/상세에 없을 때만 새 /counsels 목록을 보완 조회한다."""
    ym = f"{year:04d}_{month:02d}"
    path = checkpoint_path("monthly_files_v1", ym)
    if not REFRESH_FILE_LIST:
        cached = read_checkpoint(path)
        if isinstance(cached, dict) and cached.get("complete") is True:
            return cached["data"]

    all_rows, seen_ids, seen_tokens = [], set(), set()
    page_token = ""
    for page_number in range(1, 10001):
        response = get_json(FILE_LIST_URL, {
            "searchSd": f"{year:04d}-{month:02d}-01",
            "searchEd": f"{year:04d}-{month:02d}-{last_day(year, month)}",
            "searchVisDiv": "VIS_ID", "searchVisKeyword": "",
            "searchEmpDiv": "EMP_ID", "searchEmpKeyword": "",
            "searchPgmDiv": "PGM_DIV", "searchPgmKeyword": "",
            "searchStatDivCds": "R D C ",
            "orderColumn": "conslDate", "orderDir": "asc",
            "maxLength": str(FILE_PAGE_SIZE), "pageToken": page_token,
            "randid": str(random.random()),
        })
        # 응답 규격이 다를 때 확인할 수 있도록 원문을 보관한다. 요청 쿠키는 저장하지 않는다.
        write_checkpoint(checkpoint_path("file_pages", f"{ym}_{page_number}"), response)
        rows, next_token, total, has_more = attachment_page(response)
        previous_count = len(all_rows)
        for row in rows:
            consl_id = value(row.get("conslId"))
            if not consl_id:
                raise ValueError("첨부 목록에 conslId가 없는 행이 있습니다.")
            if consl_id not in seen_ids:
                seen_ids.add(consl_id)
                all_rows.append(row)
        print(f"[첨부 목록] {year:04d}-{month:02d} page={page_number}, 누적={len(all_rows)}건")
        if total is not None and len(all_rows) >= total:
            break
        if has_more is False:
            if total is not None and len(all_rows) < total:
                raise ValueError("첨부 목록의 전체 건수와 종료 표시가 일치하지 않습니다.")
            break
        if rows and len(all_rows) == previous_count:
            raise ValueError("첨부 목록의 같은 페이지가 반복됩니다.")
        if next_token:
            if next_token == page_token or next_token in seen_tokens:
                raise ValueError("첨부 목록의 pageToken이 반복됩니다.")
            seen_tokens.add(next_token)
            page_token = next_token
            continue
        if has_more is True or (total is not None and len(all_rows) < total):
            raise ValueError("첨부 목록에 다음 페이지가 있지만 토큰이 없습니다. 전체 JSON 응답을 확인하세요.")
        if len(rows) < FILE_PAGE_SIZE:
            break
        raise ValueError("첨부 목록이 20건 이상인데 다음 토큰/종료 정보가 없습니다. 누락 방지를 위해 완료 처리하지 않습니다.")
    else:
        raise ValueError("첨부 목록 페이지 수가 안전 한도를 초과했습니다.")
    write_checkpoint(path, {"complete": True, "data": all_rows})
    return all_rows


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


def download_file(consl_id, item):
    file_id = safe_id(item.get("fileId"))
    consl_id = safe_id(consl_id)
    name = safe_file_name(item.get("name"), file_id)
    target = OUTPUT_DIR / "files" / consl_id / file_id / name
    checkpoint = checkpoint_path("files", f"{consl_id}_{file_id}")
    source_version = {key: item.get(key) for key in ("name", "lastModDtime", "size")}
    cached = read_checkpoint(checkpoint)
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
                write_checkpoint(checkpoint, {
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


def export_files(monthly_raw, list_by_id, details, consult_map_rows):
    # 목록 캐시에 fileList가 없더라도 상세에 있으면 그것을 사용한다.
    sources = {key: [row, details[key].get("data") or {}] for key, row in list_by_id.items()}
    lookup_errors = []
    for month in monthly_raw:
        missing = [row for row in month.get("data") or []
                   if not any("fileList" in source for source in sources.get(value(row.get("conslId")), []))]
        if not missing:
            continue
        try:
            for row in fetch_file_month(month["year"], month["month"]):
                sources.setdefault(value(row.get("conslId")), []).append(row)
        except (HTTPError, URLError, TimeoutError, ConnectionError, ValueError) as error:
            message = file_error_text(error)
            lookup_errors.append({"year": month["year"], "month": month["month"], "error": message})
            print(f"[첨부 목록 실패] {month['year']}-{month['month']:02d}: {message}")
            if isinstance(error, HTTPError) and error.code in (401, 403):
                break

    jobs = []
    for consl_id, records in sources.items():
        if not any("fileList" in row for row in records):
            lookup_errors.append({"careple_consult_id": consl_id, "error": "목록/상세에서 fileList를 확인하지 못했습니다."})
        files = {}
        for row in records:
            file_list = row.get("fileList") or []
            if not isinstance(file_list, list) or any(not isinstance(item, dict) for item in file_list):
                lookup_errors.append({"careple_consult_id": consl_id, "error": "fileList 형식이 배열이 아닙니다."})
                continue
            for index, item in enumerate(file_list):
                file_id = value(item.get("fileId")) or f"missing_file_id_{index}"
                files[file_id] = item
        jobs.extend((consl_id, item) for item in files.values())

    by_id = {row["CAREPLE_CONSULT_ID"]: row for row in consult_map_rows}
    results, auth_error = [], ""
    for number, (consl_id, item) in enumerate(jobs, 1):
        mapped = by_id.get(consl_id, {})
        result = {
            "CAREPLE_CONSULT_ID": consl_id, "CONSULT_ID": mapped.get("CONSULT_ID", ""),
            "SCHEDULE_ID": mapped.get("SCHEDULE_ID", ""), "CAREPLE_FILE_ID": value(item.get("fileId")),
            "ORIGINAL_FILE_NAME": item.get("name") or "", "MIME_TYPE": item.get("type") or "",
            "SOURCE_SIZE_KB": item.get("size") or "", "SOURCE_LAST_MOD_DT": item.get("lastModDtime") or "",
            "ERROR": "",
        }
        try:
            if auth_error:
                result.update(STATUS="SKIPPED_AUTH", ERROR=auth_error)
            else:
                result.update(download_file(consl_id, item))
        except FileAuthenticationError as error:
            auth_error = file_error_text(error)
            result.update(STATUS="FAILED", ERROR=auth_error)
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
            result.update(STATUS="FAILED", ERROR=file_error_text(error))
        results.append(result)
        print(f"[첨부 {number}/{len(jobs)}] {result['STATUS']} / fileId={result['CAREPLE_FILE_ID']} / {result['ORIGINAL_FILE_NAME']}" +
              (f" / {result['ERROR']}" if result["ERROR"] else ""))
        # 매핑되지 않아 CONSULT_MASTER에서 제외된 상담의 파일도 보관한다.
        write_csv(OUTPUT_DIR / "consult_files.csv", FILE_HEADERS, results)
        if not auth_error and result["STATUS"] != "EXISTS":
            time.sleep(FILE_REQUEST_DELAY)

    write_csv(OUTPUT_DIR / "consult_files.csv", FILE_HEADERS, results)
    failed = [row for row in results if row["STATUS"] not in ("DOWNLOADED", "EXISTS")]
    write_csv(OUTPUT_DIR / "consult_files_failed.csv", FILE_HEADERS, failed)
    (OUTPUT_DIR / "consult_file_list_errors.json").write_text(json.dumps(lookup_errors, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "file_count": len(jobs),
        "file_downloaded_count": sum(row["STATUS"] == "DOWNLOADED" for row in results),
        "file_existing_count": sum(row["STATUS"] == "EXISTS" for row in results),
        "file_failed_count": len(failed), "file_list_error_count": len(lookup_errors),
        "files_complete": not failed and not lookup_errors,
    }


def main():
    if not COOKIE.strip():
        raise ValueError("상단 COOKIE에 최신 쿠키를 입력하세요.")

    global HEADERS
    tuid = next((item.split("=", 1)[1].strip() for item in COOKIE.split(";") if item.strip().startswith("tuid=")), "")
    if DOWNLOAD_FILES and not tuid:
        raise ValueError("첨부파일 다운로드에 필요한 tuid가 COOKIE에 없습니다. 최신 쿠키 전체를 입력하세요.")
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

    monthly_raw, list_by_id = [], {}
    for year, month in month_range(START_YM, END_YM):
        result = fetch_month_list(year, month)
        monthly_raw.append(result)
        for row in result.get("data") or []:
            consl_id = value(row.get("conslId"))
            if consl_id:
                list_by_id[consl_id] = row
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 목록 {year:04d}-{month:02d}: {len(result.get('data') or [])}건")

    consult_ids = list(list_by_id)
    details = {}
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(fetch_detail, consl_id): consl_id for consl_id in consult_ids}
        for number, future in enumerate(as_completed(futures), start=1):
            consl_id = futures[future]
            details[consl_id] = future.result()
            if number % 25 == 0 or number == len(consult_ids):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 상세 조회 {number}/{len(consult_ids)} (동시작업 {DETAIL_WORKERS})")

    consult_rows, consult_map_rows, unmatched, tobe_all = [], [], [], []
    for consl_id in consult_ids:
        source_list = list_by_id[consl_id]
        detail = (details[consl_id].get("data") or {})

        vis_id = value(detail.get("visId")) or value(source_list.get("visId"))
        emp_id = value(detail.get("conslEmpId")) or value(source_list.get("conslEmpId"))
        pgm_id = value(detail.get("pgmId")) or value(source_list.get("pgmId"))
        member_id = mapping["member"].get(vis_id, "")
        teacher_id = mapping["teacher"].get(emp_id, "")
        program_id = mapping["program"].get(pgm_id, "")
        schedule_id = mapping["schedule"].get(consl_id, "")

        for field, source, target in (
            ("SCHEDULE_ID", consl_id, schedule_id),
            ("MEMBER_ID", vis_id, member_id),
            ("TEACHER_ID", emp_id, teacher_id),
            ("PROGRAM_ID", pgm_id, program_id),
        ):
            if not target:
                unmatched.append({"CAREPLE_CONSULT_ID": consl_id, "FIELD": field, "SOURCE_VALUE": source, "MESSAGE": "매핑 없음"})

        source = {"list": source_list, "detail": detail}
        if not schedule_id or not member_id or not teacher_id:
            tobe_all.append({"carepleConsultId": consl_id, "source": source, "excluded": True, "reason": "NOT NULL 매핑 없음"})
            continue

        consult_id = f"CONSULT{CONSULT_ID_LAST_NO + len(consult_rows) + 1:08d}"
        status = value(detail.get("taskStatDivCd")) or value(source_list.get("taskStatDivCd")) or "R"
        consult_dt = date_time(f"{value(detail.get('conslDate')) or value(source_list.get('conslDate'))} {value(detail.get('conslSt')) or value(source_list.get('conslSt'))}")
        complete_dt = later_date_time(detail.get("contLastModDtime"), detail.get("lastModDtime")) if status == "D" else ""
        row = {
            "CONSULT_ID": consult_id,
            "SCHEDULE_ID": schedule_id,
            "COMPANY_ID": COMPANY_ID,
            "MEMBER_ID": member_id,
            "TEACHER_ID": teacher_id,
            "PROGRAM_ID": program_id,
            # AS-IS 프로그램 구분을 그대로 저장: C=상담, A=평가
            "CONSULT_TYPE_CD": value(detail.get("pgmDivCd")) or value(source_list.get("pgmDivCd")),
            "CONSULT_STATUS_CD": status,
            "TITLE": value(detail.get("conslNm")) or value(source_list.get("conslNm")) or value(detail.get("pgmNm")) or value(source_list.get("pgmNm")),
            "COUNSEL_CONTENT": value(detail.get("conslCont")),
            "MEMO": value(detail.get("reqRsn")),
            "CONSULT_DT": consult_dt,
            "COMPLETE_DT": complete_dt,
            "USE_YN": "Y",
            "DELETE_YN": "N",
            "CREATE_DT": date_time(detail.get("regDtime")) or migration_dt,
            "UPDATE_DT": later_date_time(detail.get("lastModDtime"), detail.get("contLastModDtime")),
            "UPDATE_USER_ID": resolve_update_user(detail, mapping),
        }
        consult_rows.append(row)
        consult_map_rows.append({
            "CAREPLE_CONSULT_ID": consl_id, "CONSULT_ID": consult_id, "SCHEDULE_ID": schedule_id,
            "CAREPLE_VIS_ID": vis_id, "CAREPLE_PROGRAM_ID": pgm_id, "CAREPLE_EMP_ID": emp_id,
        })
        tobe_all.append({"carepleConsultId": consl_id, "source": source, "tobe": row, "excluded": False})

    validate(consult_rows)
    origin_rows = []
    for consl_id in consult_ids:
        detail = (details[consl_id].get("data") or {})
        origin_rows.append({
            "상담평가ID": consl_id, "이용자": value(detail.get("visNm")), "프로그램": value(detail.get("pgmNm")),
            "담당선생님": value(detail.get("conslEmp")),
            "일시": date_time(f"{detail.get('conslDate', '')} {detail.get('conslSt', '')}"),
            "상태": value(detail.get("taskStatDivNm")), "내용": value(detail.get("conslCont")), "메모": value(detail.get("reqRsn")),
        })

    write_csv(OUTPUT_DIR / "consult_origin.csv", ORIGIN_HEADERS, origin_rows)
    write_csv(OUTPUT_DIR / "consult_db.csv", CONSULT_HEADERS, consult_rows)
    write_csv(OUTPUT_DIR / "consult_id_map.csv", CONSULT_MAP_HEADERS, consult_map_rows)
    write_csv(OUTPUT_DIR / "consult_unmatched_map.csv", UNMATCHED_HEADERS, unmatched)
    (OUTPUT_DIR / "consult_monthly_raw.json").write_text(json.dumps(monthly_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "consult_detail_raw.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "consult_tobe_all.json").write_text(json.dumps(tobe_all, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "list_count": len(consult_ids), "consult_count": len(consult_rows), "unmatched_count": len(unmatched),
        "start_ym": START_YM, "end_ym": END_YM,
    }
    if DOWNLOAD_FILES:
        summary.update(export_files(monthly_raw, list_by_id, details, consult_map_rows))
    else:
        summary["files_complete"] = False
        summary["file_download_disabled"] = True
    (OUTPUT_DIR / "consult_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CSV 이관 결과: " + json.dumps(summary, ensure_ascii=False))
    if DOWNLOAD_FILES and not summary["files_complete"]:
        print("주의: 첨부파일 처리가 미완료입니다. consult_files_failed.csv / consult_file_list_errors.json을 확인하세요.")


if __name__ == "__main__":
    main()
