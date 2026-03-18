# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


START_URL = "https://gse.hufs.ac.kr/gse/7725/subview.do"
BASE_URL = "https://gse.hufs.ac.kr"
OUTPUT_CSV = "hufs_gse_professors.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": START_URL,
}


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def absolute_url(href: str, base_url: str = BASE_URL) -> str:
    href = clean_text(href)
    if not href:
        return ""
    return urljoin(base_url, href)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_tab_links(start_soup: BeautifulSoup, current_url: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    tab_ul = start_soup.select_one("ul.tab_k2wiz_GNB._wizOdr.ul_3")
    if not tab_ul:
        raise RuntimeError("탭 메뉴 ul.tab_k2wiz_GNB._wizOdr.ul_3 를 찾지 못했습니다.")

    seen = set()

    for li in tab_ul.select("li"):
        a = li.select_one("a[href]")
        if not a:
            continue

        name = clean_text(a.get_text(" ", strip=True))
        href = clean_text(a.get("href"))
        url = absolute_url(href, current_url)

        if not url or url in seen:
            continue

        seen.add(url)
        results.append({
            "tab_name": name,
            "tab_url": url,
        })

    return results


def parse_prof_item(li: Tag, tab_name: str, page_url: str) -> Dict[str, str]:
    row = {
        "소속": tab_name,
        "이름": "",
        "이메일": "",
        "전공분야": "",
        "참고URL": page_url,
    }

    strong = li.select_one(".artclTitle strong")
    if strong:
        raw_name = clean_text(strong.get_text(" ", strip=True))
        raw_name = re.sub(r"\[[^\]]*\]", "", raw_name).strip()
        row["이름"] = raw_name

    for dl in li.select("dl"):
        dt = clean_text(dl.select_one("dt").get_text(" ", strip=True) if dl.select_one("dt") else "")
        dd = clean_text(dl.select_one("dd").get_text(" ", strip=True) if dl.select_one("dd") else "")

        if not dt:
            continue

        if "이메일" in dt:
            row["이메일"] = dd
        elif "전공분야" in dt:
            row["전공분야"] = dd

    # 상세 링크가 있으면 참고URL을 상세보기 링크로 교체
    detail_a = li.select_one("a._prFlLinkView[href]")
    if detail_a:
        detail_href = clean_text(detail_a.get("href"))
        detail_url = absolute_url(detail_href, page_url)
        if detail_url:
            row["참고URL"] = detail_url

    return row


def extract_professors_from_page(
        session: requests.Session,
        tab_name: str,
        page_url: str,
) -> List[Dict[str, str]]:
    print(f"[INFO] 탭 수집 시작: {tab_name} / {page_url}")
    soup = get_soup(session, page_url)

    prof_list = soup.select_one("ul._wizOdr._prFlList")
    if not prof_list:
        print(f"[WARN] 교수 목록 없음: {tab_name} / {page_url}")
        return []

    rows: List[Dict[str, str]] = []
    for li in prof_list.select("li._prFlLi"):
        row = parse_prof_item(li, tab_name, page_url)

        # 이름/이메일/전공분야 중 하나라도 있으면 저장
        if row["이름"] or row["이메일"] or row["전공분야"]:
            rows.append(row)

    print(f"[INFO] 탭 수집 완료: {tab_name} / {len(rows)}건")
    return rows


def save_csv(rows: List[Dict[str, str]], filepath: str) -> None:
    fieldnames = ["소속", "이름", "이메일", "전공분야", "참고URL"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    session = make_session()

    print(f"[INFO] 시작 페이지 접속: {START_URL}")
    start_soup = get_soup(session, START_URL)

    tab_links = extract_tab_links(start_soup, START_URL)
    print(f"[INFO] 탭 개수: {len(tab_links)}")

    all_rows: List[Dict[str, str]] = []

    for idx, item in enumerate(tab_links, start=1):
        tab_name = item["tab_name"]
        tab_url = item["tab_url"]

        print(f"[{idx}/{len(tab_links)}] 처리 중: {tab_name}")
        try:
            rows = extract_professors_from_page(session, tab_name, tab_url)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[ERROR] 탭 처리 실패: {tab_name} / {tab_url} / {e}")

        time.sleep(0.2)

    # 중복 제거
    unique_rows: List[Dict[str, str]] = []
    seen = set()

    for row in all_rows:
        key = (
            clean_text(row.get("소속")),
            clean_text(row.get("이름")),
            clean_text(row.get("이메일")),
            clean_text(row.get("전공분야")),
            clean_text(row.get("참고URL")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    save_csv(unique_rows, OUTPUT_CSV)
    print(f"[DONE] CSV 저장 완료: {OUTPUT_CSV} / 총 {len(unique_rows)}건")


if __name__ == "__main__":
    main()