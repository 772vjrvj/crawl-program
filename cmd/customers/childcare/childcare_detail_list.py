import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup


# =========================
# 설정
# =========================
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "resources" / "customers" / "childcare"
OUTPUT_FILE = INPUT_DIR / "childcare_nursery_merged.xlsx"

DETAIL_URL = (
    "https://info.childcare.go.kr/info_html5/pnis/search/preview/"
    "SummaryInfoSlPu.jsp?flag=YJ&STCODE_POP={stcode}"
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
REQUEST_SLEEP_SEC = 0.2


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
def parse_detail_names_from_html(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".table_childcare")
    if not table:
        return "", ""

    rep_name = ""
    director_name = ""

    for tr in table.select("tbody tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue

        label = th.get_text(" ", strip=True)
        value = td.get_text(" ", strip=True)

        if label == "대표자명":
            rep_name = value
        elif label == "원장명":
            director_name = value

    return rep_name, director_name


def fetch_detail_names(session: requests.Session, stcode: str) -> Tuple[str, str]:
    if not stcode:
        return "", ""

    url = build_detail_url(stcode)

    try:
        res = session.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return parse_detail_names_from_html(res.text)
    except Exception as e:
        print(f"[WARN] stcode={stcode} 상세 조회 실패: {e}")
        return "", ""


# =========================
# 파일 처리
# =========================
def load_json_file(file_path: Path) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def collect_json_files(input_dir: Path) -> List[Path]:
    return sorted(input_dir.glob("childcare_nursery_*.json"))


def process_json_file(session: requests.Session, file_path: Path) -> List[Dict[str, Any]]:
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

    rows: List[Dict[str, Any]] = []

    for idx, item in enumerate(data_list, start=1):
        if not isinstance(item, dict):
            continue

        row = build_korean_row(item)
        stcode = row.get("코드", "")

        rep_name_detail, director_name_detail = fetch_detail_names(session, stcode)

        if rep_name_detail:
            row["대표자명"] = rep_name_detail

        if director_name_detail:
            row["원장(시설장)명"] = director_name_detail

        rows.append(row)

        if idx % 100 == 0:
            print(f"[INFO] {file_path.name} 처리중... {idx}건")

        time.sleep(REQUEST_SLEEP_SEC)

    print(f"[INFO] 파일 처리 완료: {file_path.name} / 총 {len(rows)}건")
    return rows


def save_to_excel(rows: List[Dict[str, Any]], output_file: Path) -> None:
    if not rows:
        print("[WARN] 저장할 데이터가 없습니다.")
        return

    df = pd.DataFrame(rows)

    # 주소 관련 컬럼을 한쪽으로 모으고,
    # 원본 시군구문자열은 시도/시군구 바로 뒤,
    # stcode는 코드로 변경
    ordered_columns = [
        "사이트 이름",
        "상세 URL",
        "시도",
        "시군구",
        "원본 시군구문자열",
        "코드",
        "시설명",
        "유형",
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

    all_rows: List[Dict[str, Any]] = []

    with requests.Session() as session:
        for file_path in json_files:
            rows = process_json_file(session, file_path)
            all_rows.extend(rows)

    save_to_excel(all_rows, OUTPUT_FILE)
    print("[INFO] 전체 작업 완료")


if __name__ == "__main__":
    main()