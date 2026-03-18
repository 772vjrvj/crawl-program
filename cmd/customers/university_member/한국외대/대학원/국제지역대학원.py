# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


START_URL = "https://gsias.hufs.ac.kr/gsias/7177/subview.do"
OUTPUT_CSV = "hufs_gsias_professors.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
}


def clean_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


# =========================
# 탭 URL 수집
# =========================
def parse_tab_links(html: str, base_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    result = []
    for a in soup.select("ul.tab_k2wiz_GNB._wizOdr.ul_3 a[href]"):
        href = clean_text(a.get("href", ""))
        if not href:
            continue

        dept_name = clean_text(a.get_text(" ", strip=True))
        dept_url = urljoin(base_url, href)

        result.append({
            "학과명": dept_name,
            "학과URL": dept_url
        })

    # 중복 제거
    seen = set()
    unique = []
    for x in result:
        if x["학과URL"] in seen:
            continue
        seen.add(x["학과URL"])
        unique.append(x)

    return unique


# =========================
# 교수 파싱 (영문 구조 대응)
# =========================
def parse_professors(html: str, dept_name: str, dept_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    result = []

    ul = soup.select_one("ul._wizOdr._prFlList")
    if not ul:
        return result

    for li in ul.select("li._prFlLi"):
        name = ""
        position = ""
        email = ""
        tel = ""

        # 이름
        name_tag = li.select_one(".artclTitle strong")
        if name_tag:
            name = clean_text(name_tag.get_text())

        # 상세 URL
        a_tag = li.select_one("a._prFlLinkView")
        detail_url = urljoin(dept_url, a_tag.get("href")) if a_tag else ""

        # dl 파싱
        for dl in li.select("dl"):
            dt = clean_text(dl.select_one("dt").get_text() if dl.select_one("dt") else "")
            dd = clean_text(dl.select_one("dd").get_text() if dl.select_one("dd") else "")

            if dt in ["Position", "직위(직급)"]:
                position = dd
            elif dt in ["E-mail", "이메일"]:
                email = dd
            elif dt in ["Tel.", "전화번호"]:
                tel = dd

        result.append({
            "학과명": dept_name,
            "학과URL": dept_url,
            "이름": name,
            "직위": position,
            "이메일": email,
            "전화번호": tel,
            "상세URL": detail_url
        })

    return result


# =========================
# CSV 저장
# =========================
def save_csv(rows: List[Dict[str, str]]):
    fieldnames = ["학과명", "학과URL", "이름", "직위", "이메일", "전화번호", "상세URL"]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# =========================
# 메인
# =========================
def main():
    all_rows = []

    with requests.Session() as session:
        start_html = fetch_html(session, START_URL)
        dept_list = parse_tab_links(start_html, START_URL)

        print(f"[탭 개수] {len(dept_list)}")

        for i, dept in enumerate(dept_list, 1):
            print(f"[{i}/{len(dept_list)}] {dept['학과명']}")

            try:
                html = fetch_html(session, dept["학과URL"])
                rows = parse_professors(html, dept["학과명"], dept["학과URL"])
                print(f"  -> {len(rows)}명")
                all_rows.extend(rows)
            except Exception as e:
                print("  -> 실패:", e)

    save_csv(all_rows)
    print("완료")


if __name__ == "__main__":
    main()