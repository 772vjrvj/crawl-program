# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


INPUT_CSV = "prof_url_list.csv"
OUTPUT_CSV = "professor_detail_result.csv"
BASE_URL = "https://www.sungshin.ac.kr"
MAX_WORKERS = 16


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
    return urljoin(base_url, href)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    return session


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def get_text(tag: Optional[Tag]) -> str:
    if not tag:
        return ""
    return clean_text(tag.get_text(" ", strip=True))


# =========================
# CSV
# =========================
def read_csv_rows(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            item = {k: clean_text(v) for k, v in row.items()}
            item["__src_index"] = str(idx)
            rows.append(item)
    return rows


def save_csv(rows: List[Dict[str, str]], path: str) -> None:
    if not rows:
        print("[WARN] 저장할 데이터가 없습니다.")
        return

    fieldnames: List[str] = []
    seen = set()

    for row in rows:
        for key in row.keys():
            if key.startswith("__"):
                continue
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            out = {k: v for k, v in row.items() if not k.startswith("__")}
            writer.writerow(out)

    print(f"[OK] CSV 저장 완료: {path}")


# =========================
# HTML 파싱
# =========================
def get_builder_root(soup: BeautifulSoup) -> Tag:
    contents = soup.find(id="contentsEditHtml")
    if contents:
        builder = contents.find(id="_contentBuilder")
        if builder:
            return builder
        return contents
    return soup


def table_to_map(table: Tag) -> Dict[str, str]:
    info: Dict[str, str] = {}

    for tr in table.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue

        key = get_text(th)
        value = get_text(td)

        if key:
            info[key] = value

    return info


def extract_phone_and_email(contact_td: Optional[Tag]) -> Tuple[str, str]:
    phone = ""
    email = ""

    if not contact_td:
        return phone, email

    tel_a = contact_td.find("a", href=lambda x: x and x.startswith("tel:"))
    if tel_a:
        phone = get_text(tel_a)

    if not phone:
        m = re.search(r"(\d{2,4}-\d{3,4}-\d{4})", get_text(contact_td))
        if m:
            phone = clean_text(m.group(1))

    mail_a = contact_td.find("a", href=lambda x: x and x.startswith("mailto:"))
    if mail_a:
        email = get_text(mail_a)

    if not email:
        m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", get_text(contact_td))
        if m:
            email = clean_text(m.group(0))

    return phone, email


def parse_one_professor_section(section: Tag, page_url: str) -> Dict[str, str]:
    info_table = section.find("table", class_="table01") or section.find("table")
    if not info_table:
        return {
            "성명": "",
            "연구분야": "",
            "소속": "",
            "연구실": "",
            "전화번호": "",
            "이메일": "",
            "교수상세URL": page_url,
            "error": "교수 정보 테이블 없음",
        }

    info_map = table_to_map(info_table)

    contact_td = None
    for tr in info_table.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue

        if get_text(th) == "연락처":
            contact_td = td
            break

    phone, email = extract_phone_and_email(contact_td)

    return {
        "성명": clean_text(info_map.get("성명", "")),
        "연구분야": clean_text(info_map.get("연구분야", "")),
        "소속": clean_text(info_map.get("소속", "")),
        "연구실": clean_text(info_map.get("연구실", "")),
        "전화번호": clean_text(phone),
        "이메일": clean_text(email),
        "교수상세URL": page_url,
        "error": "",
    }


def parse_professor_list_page(html: str, page_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    root = get_builder_root(soup)

    professor_area = root.find("div", class_="professor_area")
    if not professor_area:
        return [{
            "성명": "",
            "연구분야": "",
            "소속": "",
            "연구실": "",
            "전화번호": "",
            "이메일": "",
            "교수상세URL": page_url,
            "error": "professor_area 없음",
        }]

    sections = professor_area.find_all("div", class_="section_professor_info")
    if not sections:
        return [{
            "성명": "",
            "연구분야": "",
            "소속": "",
            "연구실": "",
            "전화번호": "",
            "이메일": "",
            "교수상세URL": page_url,
            "error": "section_professor_info 없음",
        }]

    rows: List[Dict[str, str]] = []
    for section in sections:
        parsed = parse_one_professor_section(section, page_url)
        rows.append(parsed)

    return rows


# =========================
# 단건 처리
# =========================
def fetch_one_professor_page(src_row: Dict[str, str]) -> Tuple[int, List[Dict[str, str]]]:
    src_index = int(src_row["__src_index"])
    professor_url = clean_text(src_row.get("PROFESSOR_URL", ""))

    if not professor_url:
        row = dict(src_row)
        row["__prof_index"] = "0"
        row["성명"] = ""
        row["연구분야"] = ""
        row["소속"] = ""
        row["연구실"] = ""
        row["전화번호"] = ""
        row["교수이메일"] = ""
        row["교수상세URL"] = ""
        row["error"] = "PROFESSOR_URL 없음"
        return src_index, [row]

    session = create_session()

    try:
        resp = session.get(professor_url, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        row = dict(src_row)
        row["__prof_index"] = "0"
        row["성명"] = ""
        row["연구분야"] = ""
        row["소속"] = ""
        row["연구실"] = ""
        row["전화번호"] = ""
        row["교수이메일"] = ""
        row["교수상세URL"] = professor_url
        row["error"] = f"요청 실패: {e}"
        return src_index, [row]

    parsed_rows = parse_professor_list_page(resp.text, professor_url)

    result_rows: List[Dict[str, str]] = []

    for prof_index, parsed in enumerate(parsed_rows):
        row = dict(src_row)
        row["__prof_index"] = str(prof_index)

        row["성명"] = parsed.get("성명", "")
        row["연구분야"] = parsed.get("연구분야", "")
        row["소속"] = parsed.get("소속", "")
        row["연구실"] = parsed.get("연구실", "")
        row["전화번호"] = parsed.get("전화번호", "")
        row["교수이메일"] = parsed.get("이메일", "")
        row["교수상세URL"] = parsed.get("교수상세URL", professor_url)
        row["error"] = parsed.get("error", "")

        result_rows.append(row)

    return src_index, result_rows


# =========================
# 전체 처리
# =========================
def build_professor_rows(input_rows: List[Dict[str, str]], max_workers: int = MAX_WORKERS) -> List[Dict[str, str]]:
    temp_results: List[Tuple[int, List[Dict[str, str]]]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_one_professor_page, row): row
            for row in input_rows
        }

        total = len(future_map)
        done_count = 0

        for future in as_completed(future_map):
            done_count += 1
            src_row = future_map[future]

            try:
                src_index, rows = future.result()
                temp_results.append((src_index, rows))

                ok_count = len([r for r in rows if r.get("성명")])
                print(
                    f"[{done_count}/{total}] "
                    f"{clean_text(src_row.get('구분2', ''))} / {clean_text(src_row.get('구분3', ''))} | "
                    f"교수수={ok_count}"
                )
            except Exception as e:
                src_index = int(src_row["__src_index"])
                fail_row = dict(src_row)
                fail_row["__prof_index"] = "0"
                fail_row["성명"] = ""
                fail_row["연구분야"] = ""
                fail_row["소속"] = ""
                fail_row["연구실"] = ""
                fail_row["전화번호"] = ""
                fail_row["교수이메일"] = ""
                fail_row["교수상세URL"] = clean_text(src_row.get("PROFESSOR_URL", ""))
                fail_row["error"] = f"예외: {e}"
                temp_results.append((src_index, [fail_row]))

                print(
                    f"[{done_count}/{total}] "
                    f"{clean_text(src_row.get('구분2', ''))} / {clean_text(src_row.get('구분3', ''))} | "
                    f"ERROR={e}"
                )

    temp_results.sort(key=lambda x: x[0])

    result_rows: List[Dict[str, str]] = []
    for _, rows in temp_results:
        rows.sort(key=lambda x: int(x.get("__prof_index", "0")))
        result_rows.extend(rows)

    return result_rows


# =========================
# 실행
# =========================
def main() -> None:
    input_rows = read_csv_rows(INPUT_CSV)
    print(f"[START] 입력 행 수: {len(input_rows)}")

    result_rows = build_professor_rows(input_rows, max_workers=MAX_WORKERS)
    print(f"[INFO] 최종 결과 수: {len(result_rows)}")

    save_csv(result_rows, OUTPUT_CSV)


if __name__ == "__main__":
    main()