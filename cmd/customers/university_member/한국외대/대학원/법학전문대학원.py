# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URLS = [
    "https://law.hufs.ac.kr/law/7448/subview.do?enc=Zm5jdDF8QEB8JTJGcHJvZmwlMkZsYXclMkYzNzQlMkZhcnRjbExpc3QuZG8lM0ZwYWdlJTNEMSUyNnNyY2hDb2x1bW4lM0QlMjZzcmNoV3JkJTNEJTI2",
    "https://law.hufs.ac.kr/law/7448/subview.do?enc=Zm5jdDF8QEB8JTJGcHJvZmwlMkZsYXclMkYzNzQlMkZhcnRjbExpc3QuZG8lM0ZwYWdlJTNEMiUyNnNyY2hDb2x1bW4lM0QlMjZzcmNoV3JkJTNEJTI2",
]

OUTPUT_CSV = "hufs_law_professors.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": "https://law.hufs.ac.kr/",
}


def clean_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_professor_list(html: str, page_url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: List[Dict[str, str]] = []

    ul = soup.select_one("ul._wizOdr._prFlList")
    if not ul:
        return result

    for li in ul.select("li._prFlLi"):
        a_tag = li.select_one("a._prFlLinkView")
        detail_url = ""
        if a_tag and a_tag.get("href"):
            detail_url = urljoin(page_url, a_tag.get("href", "").strip())

        name = ""
        title_tag = li.select_one(".artclTitle strong")
        if title_tag:
            name = clean_text(title_tag.get_text(" ", strip=True))

        item = {
            "이름": name,
            "직위": "",
            "이메일": "",
            "연구실": "",
            "담당과목": "",
            "전화번호": "",
            "참고URL": detail_url if detail_url else page_url,
        }

        for dl in li.select("dl"):
            dt_tag = dl.select_one("dt")
            dd_tag = dl.select_one("dd")

            dt = clean_text(dt_tag.get_text(" ", strip=True) if dt_tag else "")
            dd = clean_text(dd_tag.get_text(" ", strip=True) if dd_tag else "")

            if dt == "직위(직급)":
                item["직위"] = dd
            elif dt == "이메일":
                item["이메일"] = dd
            elif dt == "연구실":
                item["연구실"] = dd
            elif dt == "담당과목":
                item["담당과목"] = dd
            elif dt == "전화번호":
                item["전화번호"] = dd

        result.append(item)

    return result


def save_csv(rows: List[Dict[str, str]], path: str) -> None:
    fieldnames = ["이름", "직위", "이메일", "연구실", "담당과목", "전화번호", "참고URL"]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    all_rows: List[Dict[str, str]] = []

    with requests.Session() as session:
        for url in URLS:
            html = fetch_html(session, url)
            rows = parse_professor_list(html, url)
            all_rows.extend(rows)

    save_csv(all_rows, OUTPUT_CSV)
    print(f"완료: {OUTPUT_CSV} / 총 {len(all_rows)}건")


if __name__ == "__main__":
    main()