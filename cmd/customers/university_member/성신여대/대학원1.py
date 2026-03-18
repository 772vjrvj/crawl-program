# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook

# =========================
# 설정
# =========================
URLS = [
    ("유아교육전공", "https://www.sungshin.ac.kr/gess/14973/subview.do"),
    ("미술교육전공", "https://www.sungshin.ac.kr/gess/14974/subview.do"),
    ("음악교육전공", "https://www.sungshin.ac.kr/gess/14975/subview.do"),
]

BASE_URL = "https://www.sungshin.ac.kr"
OUTPUT_CSV = "sungshin_professors.csv"
OUTPUT_XLSX = "sungshin_professors.xlsx"
MAX_WORKERS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.sungshin.ac.kr/"
}


# =========================
# 공통 유틸
# =========================
def clean_text(v: str) -> str:
    if not v:
        return ""
    return re.sub(r"\s+", " ", v).strip()


def make_absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return urljoin(BASE_URL, url)


# =========================
# 교수 파싱
# =========================
def parse_professors(html: str, major: str, page_url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    results = []

    sections = soup.select(".section_professor_info")

    for sec in sections:
        data = {
            "전공": major,
            "이름": "",
            "연구분야": "",
            "담당과목": "",
            "연구실": "",
            "전화번호": "",
            "이메일": "",
            "홈페이지": "",
            "URL": page_url,
        }

        table = sec.select_one("table")
        if not table:
            continue

        for tr in table.select("tr"):
            th = clean_text(tr.select_one("th").get_text() if tr.select_one("th") else "")
            td = clean_text(tr.select_one("td").get_text() if tr.select_one("td") else "")

            if not th:
                continue

            if "성명" in th:
                data["이름"] = td
            elif "연구분야" in th:
                data["연구분야"] = td
            elif "담당과목" in th:
                data["담당과목"] = td
            elif "연구실" in th:
                data["연구실"] = td
            elif "전화번호" in th:
                data["전화번호"] = td
            elif "이메일" in th:
                data["이메일"] = td
            elif "홈페이지" in th:
                a = tr.select_one("a")
                data["홈페이지"] = make_absolute(a["href"]) if a else td

        results.append(data)

    return results


# =========================
# 요청 처리
# =========================
def fetch(idx: int, major: str, url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()

        data = parse_professors(res.text, major, url)

        return idx, data

    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return idx, []


# =========================
# CSV 저장
# =========================
def save_csv(rows: List[Dict]):
    if not rows:
        return

    keys = rows[0].keys()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


# =========================
# XLSX 저장
# =========================
def save_xlsx(rows: List[Dict]):
    if not rows:
        return

    wb = Workbook()
    ws = wb.active

    keys = list(rows[0].keys())
    ws.append(keys)

    for r in rows:
        ws.append([r.get(k, "") for k in keys])

    wb.save(OUTPUT_XLSX)


# =========================
# 메인
# =========================
def main():
    all_results = [None] * len(URLS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []

        for idx, (major, url) in enumerate(URLS):
            futures.append(executor.submit(fetch, idx, major, url))

        for f in as_completed(futures):
            idx, data = f.result()
            all_results[idx] = data

    # 순서 유지 flatten
    final_rows = []
    for item in all_results:
        if item:
            final_rows.extend(item)

    # 저장
    save_csv(final_rows)
    save_xlsx(final_rows)

    print(f"완료: {len(final_rows)}건 저장")


if __name__ == "__main__":
    main()