# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


START_URL = "https://gsit.hufs.ac.kr/gsit/7361/subview.do"
OUTPUT_CSV = "통번역대학원.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": "https://gsit.hufs.ac.kr/",
}


def clean_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_tab_links(html: str, base_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: List[Dict[str, str]] = []

    for a_tag in soup.select("ul.tab_k2wiz_GNB._wizOdr.ul_3 a[href]"):
        href = clean_text(a_tag.get("href", ""))
        if not href:
            continue

        dept_name = clean_text(a_tag.get_text(" ", strip=True))
        dept_url = urljoin(base_url, href)

        result.append({
            "학과명": dept_name,
            "학과URL": dept_url,
        })

    # 중복 제거
    seen = set()
    unique_result = []
    for item in result:
        key = item["학과URL"]
        if key in seen:
            continue
        seen.add(key)
        unique_result.append(item)

    return unique_result


def parse_professors(html: str, dept_name: str, dept_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: List[Dict[str, str]] = []

    ul = soup.select_one("ul._wizOdr._prFlList")
    if not ul:
        return result

    for li in ul.select("li._prFlLi"):
        a_tag = li.select_one("a._prFlLinkView")
        detail_url = ""
        if a_tag and a_tag.get("href"):
            detail_url = urljoin(dept_url, clean_text(a_tag.get("href", "")))

        name = ""
        title = ""
        email = ""

        name_tag = li.select_one(".artclTitle strong")
        if name_tag:
            name = clean_text(name_tag.get_text(" ", strip=True))

        for dl in li.select("dl"):
            dt_tag = dl.select_one("dt")
            dd_tag = dl.select_one("dd")

            dt = clean_text(dt_tag.get_text(" ", strip=True) if dt_tag else "")
            dd = clean_text(dd_tag.get_text(" ", strip=True) if dd_tag else "")

            if dt == "직위(직급)":
                title = dd
            elif dt == "이메일":
                email = dd

        if not name and not email:
            continue

        result.append({
            "학과명": dept_name,
            "학과URL": dept_url,
            "이름": name,
            "직위": title,
            "이메일": email,
            "상세URL": detail_url,
        })

    return result


def save_csv(rows: List[Dict[str, str]], path: str) -> None:
    fieldnames = ["학과명", "학과URL", "이름", "직위", "이메일", "상세URL"]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    all_rows: List[Dict[str, str]] = []

    with requests.Session() as session:
        start_html = fetch_html(session, START_URL)
        dept_list = parse_tab_links(start_html, START_URL)

        print(f"[INFO] 학과 탭 수집 완료: {len(dept_list)}개")

        for idx, dept in enumerate(dept_list, start=1):
            dept_name = dept["학과명"]
            dept_url = dept["학과URL"]

            try:
                print(f"[{idx}/{len(dept_list)}] 처리중: {dept_name} - {dept_url}")
                dept_html = fetch_html(session, dept_url)
                rows = parse_professors(dept_html, dept_name, dept_url)
                print(f"    -> 교수 수집: {len(rows)}건")
                all_rows.extend(rows)
            except Exception as e:
                print(f"    -> 실패: {dept_name} / {dept_url} / {e}")

    save_csv(all_rows, OUTPUT_CSV)
    print(f"[완료] CSV 저장: {OUTPUT_CSV} / 총 {len(all_rows)}건")


if __name__ == "__main__":
    main()