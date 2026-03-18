# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


LIST_URL = "https://biz.hufs.ac.kr/biz/7986/subview.do"
BASE_URL = "https://biz.hufs.ac.kr"
OUTPUT_CSV = "hufs_biz_professors.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": LIST_URL,
}


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def find_detail_url_in_li(li: Tag, list_url: str) -> str:
    # 1순위: 자세히보기 링크
    for a in li.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        href = clean_text(a.get("href"))
        if text == "자세히보기" and href:
            return urljoin(list_url, href)

    # 2순위: target=_blank 링크
    for a in li.find_all("a", href=True):
        href = clean_text(a.get("href"))
        target = clean_text(a.get("target"))
        if target == "_blank" and href:
            return urljoin(list_url, href)

    # 3순위: artclView.do 포함 링크
    for a in li.find_all("a", href=True):
        href = clean_text(a.get("href"))
        if "artclView.do" in href:
            return urljoin(list_url, href)

    return ""


def extract_detail_links(list_url: str, session: requests.Session) -> List[str]:
    soup = get_soup(list_url, session)

    links: List[str] = []
    seen = set()

    ul = soup.select_one("ul._wizOdr._prFlList")
    if not ul:
        print("[경고] 목록 영역을 찾지 못했습니다: ul._wizOdr._prFlList")
        return links

    for li in ul.find_all("li", class_=re.compile(r"\b_prFlLi\b")):
        detail_url = find_detail_url_in_li(li, list_url)
        if not detail_url:
            continue

        if detail_url in seen:
            continue

        seen.add(detail_url)
        links.append(detail_url)

    return links


def find_email(values: List[str]) -> str:
    email_pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for value in values:
        m = email_pattern.search(value)
        if m:
            return m.group(0)
    return ""


def extract_name(root: Tag) -> str:
    node = root.select_one(".artclTitle strong")
    if node:
        return clean_text(node.get_text(" ", strip=True))
    return ""


def extract_major(dd_values: List[str]) -> str:
    """
    상세 예시:
    [0] 마케팅/교수
    [1] 미국 시라큐스대 경영대학 계량마케팅 전공 Ph.D
    [2] 02-2173-3019
    [3] Kahn, Hyungsik
    [4] hkahn@hufs.ac.kr
    [5] 사이버관 C726호

    전공은 첫 번째 항목에서 '/' 앞부분 사용
    """
    if not dd_values:
        return ""

    first = clean_text(dd_values[0])
    if "/" in first:
        return clean_text(first.split("/")[0])

    return first


def parse_detail_page(detail_url: str, session: requests.Session) -> Dict[str, str]:
    soup = get_soup(detail_url, session)

    root = soup.select_one("div._prFlList._prFlView")
    if not root:
        print(f"[경고] 상세 루트를 찾지 못했습니다: {detail_url}")
        return {
            "이름": "",
            "이메일": "",
            "전공": "",
            "참고URL": detail_url,
        }

    name = extract_name(root)

    dd_values: List[str] = []
    for dd in root.select("div.artclInfo dl dd"):
        text = clean_text(dd.get_text(" ", strip=True))
        if text:
            dd_values.append(text)

    email = find_email(dd_values)
    major = extract_major(dd_values)

    return {
        "이름": name,
        "이메일": email,
        "전공": major,
        "참고URL": detail_url,
    }


def save_csv(rows: List[Dict[str, str]], output_csv: str) -> None:
    fieldnames = ["이름", "이메일", "전공", "참고URL"]

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    session = requests.Session()

    print(f"[목록 페이지] {LIST_URL}")
    detail_links = extract_detail_links(LIST_URL, session)
    print(f"[상세 링크 수집] {len(detail_links)}건")

    if detail_links:
        print("[상세 링크 예시]")
        for i, url in enumerate(detail_links[:5], start=1):
            print(f"  {i}. {url}")

    results: List[Dict[str, str]] = []

    for idx, detail_url in enumerate(detail_links, start=1):
        try:
            row = parse_detail_page(detail_url, session)
            results.append(row)
            print(
                f"[{idx}/{len(detail_links)}] 완료 | "
                f"이름={row['이름']} | 이메일={row['이메일']} | 전공={row['전공']}"
            )
        except Exception as e:
            print(f"[{idx}/{len(detail_links)}] 실패 | URL={detail_url} | 오류={e}")
            results.append({
                "이름": "",
                "이메일": "",
                "전공": "",
                "참고URL": detail_url,
            })

    save_csv(results, OUTPUT_CSV)
    print(f"[저장 완료] {OUTPUT_CSV}")


if __name__ == "__main__":
    main()