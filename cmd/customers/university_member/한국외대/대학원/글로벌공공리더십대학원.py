# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from openpyxl import Workbook


START_URL = "https://gsps.hufs.ac.kr/gsps/7636/subview.do"
BASE_URL = "https://gsps.hufs.ac.kr"

OUTPUT_CSV = "hufs_gsps_professors.csv"
OUTPUT_XLSX = "hufs_gsps_professors.xlsx"

MAX_WORKERS = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": START_URL,
}


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


def normalize_name(raw_name: str) -> str:
    name = clean_text(raw_name)

    # 대괄호 제거: [의회행정학과 주임교수]
    name = re.sub(r"\[[^\]]*\]", "", name).strip()

    # 뒤쪽 "교수" 제거
    name = re.sub(r"\s*교수\s*$", "", name).strip()

    return name


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# =========================
# 탭 수집
# =========================
def extract_tab_links(session: requests.Session, start_url: str) -> List[Dict[str, str]]:
    soup = get_soup(session, start_url)

    tab_ul = soup.select_one("ul.tab_k2wiz_GNB._wizOdr.ul_3")
    if not tab_ul:
        raise RuntimeError("탭 목록 ul.tab_k2wiz_GNB._wizOdr.ul_3 를 찾지 못했습니다.")

    results: List[Dict[str, str]] = []
    seen = set()

    for idx, li in enumerate(tab_ul.select("li"), start=1):
        a = li.select_one("a[href]")
        if not a:
            continue

        tab_name = clean_text(a.get_text(" ", strip=True))
        href = clean_text(a.get("href"))
        tab_url = make_absolute_url(href, start_url)

        if not tab_url or tab_url in seen:
            continue
        seen.add(tab_url)

        results.append({
            "tab_index": idx,
            "학과": tab_name,
            "tab_url": tab_url,
        })

    return results


# =========================
# 교수 목록 파싱
# =========================
def parse_prof_li(li: Tag, department: str, page_url: str, tab_index: int, row_index: int) -> Dict[str, str]:
    row = {
        "정렬_tab_index": tab_index,
        "정렬_row_index": row_index,
        "학과": department,
        "이름": "",
        "이메일": "",
        "전공분야": "",
        "연구분야": "",
        "참고URL": page_url,
    }

    strong = li.select_one(".artclTitle strong")
    if strong:
        row["이름"] = normalize_name(strong.get_text(" ", strip=True))

    for dl in li.select("dl"):
        dt_el = dl.select_one("dt")
        dd_el = dl.select_one("dd")

        dt = clean_text(dt_el.get_text(" ", strip=True) if dt_el else "")
        dd = clean_text(dd_el.get_text(" ", strip=True) if dd_el else "")

        if not dt:
            continue

        if "이메일" in dt:
            row["이메일"] = dd
        elif "전공분야" in dt:
            row["전공분야"] = dd
        elif "연구분야" in dt:
            row["연구분야"] = dd

    detail_a = li.select_one("a._prFlLinkView[href]")
    if detail_a:
        detail_href = clean_text(detail_a.get("href"))
        detail_url = make_absolute_url(detail_href, page_url)
        if detail_url:
            row["참고URL"] = detail_url

    return row


def extract_professors_from_tab(tab_item: Dict[str, str]) -> List[Dict[str, str]]:
    tab_index = int(tab_item["tab_index"])
    department = tab_item["학과"]
    page_url = tab_item["tab_url"]

    session = make_session()

    print(f"[INFO] 처리 시작: {department} / {page_url}")
    soup = get_soup(session, page_url)

    prof_ul = soup.select_one("ul._wizOdr._prFlList")
    if not prof_ul:
        print(f"[WARN] 교수목록 없음: {department}")
        return []

    rows: List[Dict[str, str]] = []
    for row_index, li in enumerate(prof_ul.select("li._prFlLi"), start=1):
        row = parse_prof_li(
            li=li,
            department=department,
            page_url=page_url,
            tab_index=tab_index,
            row_index=row_index,
        )

        if row["이름"] or row["이메일"] or row["전공분야"] or row["연구분야"]:
            rows.append(row)

    print(f"[INFO] 처리 완료: {department} / {len(rows)}건")
    return rows


# =========================
# 저장
# =========================
def save_csv(rows: List[Dict[str, str]], filepath: str) -> None:
    fieldnames = ["학과", "이름", "이메일", "전공분야", "연구분야", "참고URL"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "학과": row.get("학과", ""),
                "이름": row.get("이름", ""),
                "이메일": row.get("이메일", ""),
                "전공분야": row.get("전공분야", ""),
                "연구분야": row.get("연구분야", ""),
                "참고URL": row.get("참고URL", ""),
            })


def save_xlsx(rows: List[Dict[str, str]], filepath: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "professors"

    headers = ["학과", "이름", "이메일", "전공분야", "연구분야", "참고URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("학과", ""),
            row.get("이름", ""),
            row.get("이메일", ""),
            row.get("전공분야", ""),
            row.get("연구분야", ""),
            row.get("참고URL", ""),
        ])

    wb.save(filepath)


# =========================
# 메인
# =========================
def main() -> None:
    session = make_session()

    print(f"[INFO] 시작 URL: {START_URL}")
    tab_items = extract_tab_links(session, START_URL)
    print(f"[INFO] 탭 개수: {len(tab_items)}")

    all_rows: List[Dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(extract_professors_from_tab, tab_item): tab_item
            for tab_item in tab_items
        }

        for future in as_completed(future_map):
            tab_item = future_map[future]
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                print(f"[ERROR] 실패: {tab_item.get('학과')} / {tab_item.get('tab_url')} / {e}")

    # 중복 제거
    deduped: List[Dict[str, str]] = []
    seen = set()

    for row in all_rows:
        key = (
            clean_text(row.get("학과")),
            clean_text(row.get("이름")),
            clean_text(row.get("이메일")),
            clean_text(row.get("전공분야")),
            clean_text(row.get("연구분야")),
            clean_text(row.get("참고URL")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    # 원래 탭 순서 + 페이지 내 순서 정렬
    deduped.sort(key=lambda x: (int(x["정렬_tab_index"]), int(x["정렬_row_index"])))

    save_csv(deduped, OUTPUT_CSV)
    save_xlsx(deduped, OUTPUT_XLSX)

    print(f"[DONE] CSV 저장 완료: {OUTPUT_CSV}")
    print(f"[DONE] XLSX 저장 완료: {OUTPUT_XLSX}")
    print(f"[DONE] 총 {len(deduped)}건")


if __name__ == "__main__":
    main()