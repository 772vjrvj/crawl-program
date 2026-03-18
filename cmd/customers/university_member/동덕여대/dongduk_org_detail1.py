# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from openpyxl import Workbook


BASE_URL = "https://www.dongduk.ac.kr"
INPUT_CSV = "dongduk_univ_org.csv"
OUTPUT_CSV = "dongduk_univ_org_detail.csv"
OUTPUT_XLSX = "dongduk_univ_org_detail.xlsx"
MAX_WORKERS = 10


# =========================
# 공통
# =========================
def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def make_absolute_url(href: str, base_url: str = BASE_URL) -> str:
    href = clean_text(href)
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base_url, href)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "Referer": BASE_URL,
        }
    )
    return session


def fetch_html(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def is_honorary_professor(name: str, raw_text: str = "") -> bool:
    name = clean_text(name)
    raw_text = clean_text(raw_text)

    if "명예교수" in name:
        return True
    if raw_text and "명예교수" in raw_text:
        return True
    return False


# =========================
# URL 변환
# =========================
def convert_to_detail_url(url: str) -> str:
    """
    예:
    https://www.dongduk.ac.kr/www/contents/liberal01-01.do?gotoMenuNo=liberal01-01
    -> https://www.dongduk.ac.kr/www/contents/liberal01-05.do?gotoMenuNo=liberal01-05

    https://www.dongduk.ac.kr/www/contents/socialnature07-01.do?gotoMenuNo=socialnature07
    -> https://www.dongduk.ac.kr/www/contents/socialnature07-05.do?gotoMenuNo=socialnature07-05
    """
    url = clean_text(url)
    if not url:
        return ""

    parsed = urlparse(url)
    path = parsed.path
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)

    # path 의 -01.do -> -05.do
    path = re.sub(r"-01\.do$", "-05.do", path)

    # gotoMenuNo 도 같이 보정
    new_query_pairs = []
    for k, v in query_pairs:
        if k == "gotoMenuNo":
            if re.search(r"-01$", v):
                v = re.sub(r"-01$", "-05", v)
            else:
                v = f"{v}-05"
        new_query_pairs.append((k, v))

    new_query = urlencode(new_query_pairs, doseq=True)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path if path == "" else path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


# =========================
# 파싱
# =========================
def parse_topbox_admin_row(
        base_info: Dict[str, str],
        soup: BeautifulSoup,
        detail_url: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    top_box = soup.select_one("article.topBox")
    if not top_box:
        return rows

    email = ""
    tel = ""
    office = ""

    for li in top_box.select("aside ul li"):
        cls_list = li.get("class") or []
        cls_str = " ".join(cls_list)
        span = li.find("span")
        val = clean_text(span.get_text(" ", strip=True) if span else "")

        if "email" in cls_str:
            email = val
        elif "tel" in cls_str:
            tel = val
        elif "map" in cls_str:
            office = val

    rows.append(
        {
            "구분1": base_info.get("구분1", ""),
            "구분2": base_info.get("구분2", ""),
            "구분3": base_info.get("구분3", ""),
            "구분4": "행정",
            "이름": "",
            "이메일": email,
            "직위": "",
            "전화번호": tel,
            "연구실": office,
            "학력": "",
            "전공": "",
            "연구분야": "",
            "상세URL": detail_url,
            "원본URL": base_info.get("URL", ""),
        }
    )

    return rows


def parse_dl_map(container: Tag) -> Dict[str, str]:
    data: Dict[str, str] = {}

    for dl in container.find_all("dl", recursive=False):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue

        key = clean_text(dt.get_text(" ", strip=True))
        val = clean_text(dd.get_text(" ", strip=True))
        if key:
            data[key] = val

    return data


def extract_prof_iframe_url(soup: BeautifulSoup, detail_url: str) -> str:
    iframe = soup.select_one("iframe.iframe_process")
    if not iframe:
        return ""

    src = clean_text(iframe.get("src", ""))
    if not src:
        return ""

    return urljoin(detail_url, src)


def parse_professor_rows(
        base_info: Dict[str, str],
        soup: BeautifulSoup,
        detail_url: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for li in soup.select("ul.st_introduce_list > li"):
        info = li.select_one("div.int_info")
        if not info:
            continue

        dl_map = parse_dl_map(info)

        name = clean_text(dl_map.get("교수명", ""))
        email = clean_text(dl_map.get("이메일", ""))
        tel = clean_text(dl_map.get("전화번호", ""))
        room = clean_text(dl_map.get("연구실", ""))
        education = clean_text(dl_map.get("학력", ""))
        major = clean_text(dl_map.get("전공", ""))
        research = clean_text(dl_map.get("연구분야", ""))

        li_text = clean_text(li.get_text(" ", strip=True))

        # 명예교수 제외
        if is_honorary_professor(name, li_text):
            continue

        if not name and not email:
            continue

        rows.append(
            {
                "구분1": base_info.get("구분1", ""),
                "구분2": base_info.get("구분2", ""),
                "구분3": base_info.get("구분3", ""),
                "구분4": "교수",
                "이름": name,
                "이메일": email,
                "직위": "교수",
                "전화번호": tel,
                "연구실": room,
                "학력": education,
                "전공": major,
                "연구분야": research,
                "상세URL": detail_url,
                "원본URL": base_info.get("URL", ""),
            }
        )

    return rows


def parse_detail_page(
        session: requests.Session,
        base_info: Dict[str, str],
        detail_html: str,
        detail_url: str,
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(detail_html, "html.parser")
    rows: List[Dict[str, str]] = []

    # 행정
    rows.extend(parse_topbox_admin_row(base_info, soup, detail_url))

    # 교수 iframe
    iframe_url = extract_prof_iframe_url(soup, detail_url)
    if iframe_url:
        try:
            iframe_html = fetch_html(session, iframe_url)
            iframe_soup = BeautifulSoup(iframe_html, "html.parser")
            rows.extend(parse_professor_rows(base_info, iframe_soup, detail_url))
        except Exception as e:
            print(f"  !! 교수 iframe 조회 실패: {iframe_url} / {(e and str(e)) or ''}")

    return rows


# =========================
# CSV / XLSX
# =========================
def read_input_csv(filepath: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            rows.append(
                {
                    "__index__": idx,  # 요청 순서 보존용
                    "구분1": clean_text(row.get("구분1", "")),
                    "구분2": clean_text(row.get("구분2", "")),
                    "구분3": clean_text(row.get("구분3", "")),
                    "URL": clean_text(row.get("URL", "")),
                }
            )

    return rows


def write_output_csv(filepath: str, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "구분1",
        "구분2",
        "구분3",
        "구분4",
        "이름",
        "이메일",
        "직위",
        "전화번호",
        "연구실",
        "학력",
        "전공",
        "연구분야",
        "상세URL",
        "원본URL",
    ]

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_output_xlsx(filepath: str, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "구분1",
        "구분2",
        "구분3",
        "구분4",
        "이름",
        "이메일",
        "직위",
        "전화번호",
        "연구실",
        "학력",
        "전공",
        "연구분야",
        "상세URL",
        "원본URL",
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "dongduk"

    ws.append(fieldnames)

    for row in rows:
        ws.append([row.get(col, "") for col in fieldnames])

    wb.save(filepath)


def deduplicate_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []

    for row in rows:
        key = (
            row.get("__base_index__", 0),
            row.get("구분1", ""),
            row.get("구분2", ""),
            row.get("구분3", ""),
            row.get("구분4", ""),
            row.get("이름", ""),
            row.get("이메일", ""),
            row.get("직위", ""),
            row.get("상세URL", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)

    return result


# =========================
# 워커
# =========================
def process_one(base_info: Dict[str, str], total: int) -> Tuple[int, List[Dict[str, str]]]:
    idx = int(base_info.get("__index__", 0))
    original_url = clean_text(base_info.get("URL", ""))

    if not original_url:
        print(f"[{idx + 1}/{total}] URL 없음, 스킵")
        return idx, []

    if original_url.lower().startswith("javascript:"):
        print(f"[{idx + 1}/{total}] javascript URL 스킵: {original_url}")
        return idx, []

    detail_url = convert_to_detail_url(original_url)
    session = create_session()

    try:
        print(f"[{idx + 1}/{total}] 조회: {detail_url}")
        detail_html = fetch_html(session, detail_url)
        rows = parse_detail_page(session, base_info, detail_html, detail_url)

        # 입력 요청 순서 정렬 보존용
        for row in rows:
            row["__base_index__"] = idx

        print(f"[{idx + 1}/{total}] 완료: {len(rows)}건")
        return idx, rows

    except Exception as e:
        print(f"[{idx + 1}/{total}] 오류: {detail_url} / {(e and str(e)) or ''}")
        return idx, []


# =========================
# 메인
# =========================
def main() -> None:
    input_rows = read_input_csv(INPUT_CSV)
    total = len(input_rows)

    indexed_results: List[Tuple[int, List[Dict[str, str]]]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_one, row, total) for row in input_rows]

        for future in as_completed(futures):
            try:
                indexed_results.append(future.result())
            except Exception as e:
                print(f"멀티스레드 future 오류: {(e and str(e)) or ''}")

    # 요청한 순서대로 정렬
    indexed_results.sort(key=lambda x: x[0])

    final_rows: List[Dict[str, str]] = []
    for _, rows in indexed_results:
        final_rows.extend(rows)

    # 같은 요청 순서 안에서 중복 제거
    final_rows = deduplicate_rows(final_rows)

    # 최종 정렬:
    # 1) 요청 순서
    # 2) 같은 학과 내에서 행정 먼저, 교수 나중
    # 3) 교수는 이름순
    final_rows.sort(
        key=lambda row: (
            int(row.get("__base_index__", 0)),
            0 if row.get("구분4", "") == "행정" else 1,
            row.get("이름", ""),
            row.get("이메일", ""),
        )
    )

    # 내부 정렬용 컬럼 제거
    for row in final_rows:
        row.pop("__base_index__", None)

    write_output_csv(OUTPUT_CSV, final_rows)
    write_output_xlsx(OUTPUT_XLSX, final_rows)

    print()
    print(f"CSV 완료: {OUTPUT_CSV}")
    print(f"XLSX 완료: {OUTPUT_XLSX}")
    print(f"총 {len(final_rows)}건 저장")


if __name__ == "__main__":
    main()