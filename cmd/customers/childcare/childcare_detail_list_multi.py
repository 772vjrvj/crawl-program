import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


# =========================
# 설정
# =========================
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "resources" / "customers" / "childcare"

# OUTPUT_FILE = INPUT_DIR / "childcare_nursery_merged.xlsx"

OUTPUT_FILE = INPUT_DIR / "childcare_nursery_merged.csv"

DETAIL_URL = (
    "https://info.childcare.go.kr/info_html5/pnis/search/preview/"
    "SummaryInfoSlPu.jsp?flag=YJ&STCODE_POP={stcode}"
)

BASIS_PRESENT_URL = (
    "https://info.childcare.go.kr/info_html5/pnis/search/preview/"
    "BasisPresentConditionSlPu.jsp?flag=GH&STCODE_POP={stcode}&CRNAMETITLE={cr_name}&loginFlag="
)

SITE_NAME = "아이사랑"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": "https://info.childcare.go.kr/",
}

REQUEST_TIMEOUT = 15
REQUEST_SLEEP_SEC = 0.05

# 너무 크게 잡으면 차단될 수 있음
MAX_WORKERS = 8

# 쓰레드별 Session 보관
_thread_local = local()


# =========================
# 공통 함수
# =========================
def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def split_region(stsmrycn: str) -> Tuple[str, str]:
    text = safe_str(stsmrycn)
    if not text:
        return "", ""

    parts = text.split()
    sido = parts[0] if len(parts) >= 1 else ""
    sigungu = " ".join(parts[1:]) if len(parts) >= 2 else ""
    return sido, sigungu


def normalize_phone(value: Any) -> str:
    return safe_str(value)


def normalize_home_as_email(value: Any) -> str:
    return safe_str(value)


def map_vehicle_operating(row: Dict[str, Any]) -> str:
    return "운영" if safe_str(row.get("crcargb")).upper() == "Y" else "미 운영"


def build_detail_url(stcode: str) -> str:
    return DETAIL_URL.format(stcode=stcode)


def build_basis_present_url(stcode: str, facility_name: str) -> str:
    return BASIS_PRESENT_URL.format(
        stcode=quote(safe_str(stcode), safe=""),
        cr_name=quote(safe_str(facility_name), safe=""),
    )


def get_thread_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        _thread_local.session = session
    return session


def build_korean_row(item: Dict[str, Any]) -> Dict[str, Any]:
    stcode = safe_str(item.get("stcode"))
    sido, sigungu = split_region(item.get("stsmrycn"))

    return {
        "사이트 이름": SITE_NAME,
        "상세 URL": build_detail_url(stcode),
        "시도": sido,
        "시군구": sigungu,
        "원본 시군구문자열": safe_str(item.get("stsmrycn")),
        "코드": stcode,
        "시설명": safe_str(item.get("crrepre")) or safe_str(item.get("crname")),
        "유형": safe_str(item.get("crtypenm")),
        "설립유형": "",
        "건물소유형태": "",
        "평가인증 연월": "",
        "주소": safe_str(item.get("craddr")),
        "전화번호": normalize_phone(item.get("tel_no")),
        "핸드폰번호": "",
        "이메일주소": normalize_home_as_email(item.get("crhome")),
        "정원": safe_str(item.get("crcapat")),
        "현원": safe_str(item.get("crchcnt")),
        "차량운행": map_vehicle_operating(item),
        "대표자명": safe_str(item.get("crrepname")),
        "원장(시설장)명": "",
        "대기인원": "",
        "대기여부": safe_str(item.get("etnrtrynnm")),
    }


# =========================
# 상세페이지 파싱
# =========================
def extract_label_value_map_from_rows(rows: List[Tag]) -> Dict[str, str]:
    result: Dict[str, str] = {}

    for tr in rows:
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue

        i = 0
        while i < len(cells) - 1:
            left = cells[i]
            right = cells[i + 1]

            if left.name == "th" and right.name == "td":
                label = left.get_text(" ", strip=True)
                value = right.get_text(" ", strip=True)
                if label and value and label not in result:
                    result[label] = value
                i += 2
            else:
                i += 1

    return result


def parse_summary_detail_from_html(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".table_childcare")
    if not table:
        return {
            "대표자명": "",
            "원장명": "",
            "설립유형": "",
            "평가인증 연월": "",
        }

    tbody_rows = table.select("tbody > tr")
    data_map = extract_label_value_map_from_rows(tbody_rows)

    return {
        "대표자명": safe_str(data_map.get("대표자명")),
        "원장명": safe_str(data_map.get("원장명")),
        "설립유형": safe_str(data_map.get("설립유형")),
        "평가인증 연월": safe_str(data_map.get("평가인증 연월")),
    }


def parse_basis_present_from_html(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    x_scroll = soup.select_one(".x-scroll")
    if not x_scroll:
        return {
            "설립유형": "",
            "건물소유형태": "",
        }

    tbody = x_scroll.select_one("tbody")
    if not tbody:
        return {
            "설립유형": "",
            "건물소유형태": "",
        }

    rows = tbody.find_all("tr", recursive=False)
    data_map = extract_label_value_map_from_rows(rows)

    return {
        "설립유형": safe_str(data_map.get("설립유형")),
        "건물소유형태": safe_str(data_map.get("건물소유형태")),
    }


def fetch_summary_detail(stcode: str) -> Dict[str, str]:
    if not stcode:
        return {
            "대표자명": "",
            "원장명": "",
            "설립유형": "",
            "평가인증 연월": "",
        }

    url = build_detail_url(stcode)
    session = get_thread_session()

    try:
        time.sleep(REQUEST_SLEEP_SEC)
        res = session.get(url, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return parse_summary_detail_from_html(res.text)
    except Exception as e:
        print(f"[WARN] stcode={stcode} 요약 상세 조회 실패: {e}")
        return {
            "대표자명": "",
            "원장명": "",
            "설립유형": "",
            "평가인증 연월": "",
        }


def fetch_basis_present_detail(stcode: str, facility_name: str) -> Dict[str, str]:
    if not stcode:
        return {
            "설립유형": "",
            "건물소유형태": "",
        }

    url = build_basis_present_url(stcode, facility_name)
    session = get_thread_session()

    try:
        time.sleep(REQUEST_SLEEP_SEC)
        res = session.get(url, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return parse_basis_present_from_html(res.text)
    except Exception as e:
        print(f"[WARN] stcode={stcode} 기본현황 상세 조회 실패: {e}")
        return {
            "설립유형": "",
            "건물소유형태": "",
        }


def enrich_row_with_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    stcode = safe_str(row.get("코드"))
    facility_name = safe_str(row.get("시설명"))

    summary_detail = fetch_summary_detail(stcode)
    basis_detail = fetch_basis_present_detail(stcode, facility_name)

    rep_name = safe_str(summary_detail.get("대표자명"))
    director_name = safe_str(summary_detail.get("원장명"))
    setup_type_summary = safe_str(summary_detail.get("설립유형"))
    eval_month = safe_str(summary_detail.get("평가인증 연월"))

    setup_type_basis = safe_str(basis_detail.get("설립유형"))
    building_ownership = safe_str(basis_detail.get("건물소유형태"))

    if rep_name:
        row["대표자명"] = rep_name

    if director_name:
        row["원장(시설장)명"] = director_name

    row["설립유형"] = setup_type_summary or setup_type_basis
    row["건물소유형태"] = building_ownership
    row["평가인증 연월"] = eval_month

    return row


# =========================
# 파일 처리
# =========================
def load_json_file(file_path: Path) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def collect_json_files(input_dir: Path) -> List[Path]:
    return sorted(input_dir.glob("childcare_nursery_*.json"))


def process_json_file(file_path: Path) -> List[Dict[str, Any]]:
    print(f"[INFO] 파일 처리 시작: {file_path.name}")

    try:
        payload = load_json_file(file_path)
    except Exception as e:
        print(f"[ERROR] JSON 로드 실패: {file_path.name} / {e}")
        return []

    data_list = payload.get("data_list")
    if not isinstance(data_list, list):
        print(f"[WARN] data_list 없음 또는 리스트 아님: {file_path.name}")
        return []

    base_rows: List[Dict[str, Any]] = []
    for item in data_list:
        if isinstance(item, dict):
            base_rows.append(build_korean_row(item))

    print(f"[INFO] {file_path.name} 기본 변환 완료 / {len(base_rows)}건")

    rows: List[Dict[str, Any]] = [None] * len(base_rows)  # type: ignore

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(enrich_row_with_detail, row): idx
            for idx, row in enumerate(base_rows)
        }

        done_count = 0
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                rows[idx] = future.result()
            except Exception as e:
                print(f"[WARN] 상세 병렬 처리 실패 idx={idx}: {e}")
                rows[idx] = base_rows[idx]

            done_count += 1
            if done_count % 100 == 0:
                print(f"[INFO] {file_path.name} 상세조회 진행중... {done_count}/{len(base_rows)}")

    final_rows = [row for row in rows if row]
    print(f"[INFO] 파일 처리 완료: {file_path.name} / 총 {len(final_rows)}건")
    return final_rows


# 기존 save_to_excel 함수 대신 이걸로 교체
def save_to_csv(rows: List[Dict[str, Any]], output_file: Path) -> None:
    if not rows:
        print("[WARN] 저장할 데이터가 없습니다.")
        return

    df = pd.DataFrame(rows)

    ordered_columns = [
        "사이트 이름",
        "상세 URL",
        "시도",
        "시군구",
        "원본 시군구문자열",
        "코드",
        "시설명",
        "유형",
        "설립유형",
        "건물소유형태",
        "평가인증 연월",
        "주소",
        "전화번호",
        "핸드폰번호",
        "이메일주소",
        "정원",
        "현원",
        "차량운행",
        "대표자명",
        "원장(시설장)명",
        "대기인원",
        "대기여부",
    ]

    for col in ordered_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[ordered_columns]
    df = df.sort_values(by=["시도", "시군구", "시설명"], ascending=[True, True, True])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print(f"[INFO] CSV 저장 완료: {output_file}")


def save_to_excel(rows: List[Dict[str, Any]], output_file: Path) -> None:
    if not rows:
        print("[WARN] 저장할 데이터가 없습니다.")
        return

    df = pd.DataFrame(rows)

    ordered_columns = [
        "사이트 이름",
        "상세 URL",
        "시도",
        "시군구",
        "원본 시군구문자열",
        "코드",
        "시설명",
        "유형",
        "설립유형",
        "건물소유형태",
        "평가인증 연월",
        "주소",
        "전화번호",
        "핸드폰번호",
        "이메일주소",
        "정원",
        "현원",
        "차량운행",
        "대표자명",
        "원장(시설장)명",
        "대기인원",
        "대기여부",
    ]

    for col in ordered_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[ordered_columns]
    df = df.sort_values(by=["시도", "시군구", "시설명"], ascending=[True, True, True])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_file, index=False)

    print(f"[INFO] 엑셀 저장 완료: {output_file}")


def main() -> None:
    json_files = collect_json_files(INPUT_DIR)

    if not json_files:
        print(f"[WARN] 대상 JSON 파일이 없습니다: {INPUT_DIR}")
        return

    print(f"[INFO] 대상 파일 수: {len(json_files)}")
    print(f"[INFO] 상세조회 멀티쓰레드 수: {MAX_WORKERS}")

    all_rows: List[Dict[str, Any]] = []

    for file_path in json_files:
        rows = process_json_file(file_path)
        all_rows.extend(rows)

    # save_to_excel(all_rows, OUTPUT_FILE)
    save_to_csv(all_rows, OUTPUT_FILE)
    print("[INFO] 전체 작업 완료")


if __name__ == "__main__":
    main()