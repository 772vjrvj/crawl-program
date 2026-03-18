# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.sungshin.ac.kr"


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


def find_dept_menu_ul(soup: BeautifulSoup) -> Optional[Tag]:
    """
    class 속성에 _wizOdr 와 ul_3 이 모두 포함된 ul 태그를 찾는다.
    예:
      <ul class="top_k2wiz_GNB_ul_11620 _wizOdr ul_3">
    """
    for ul in soup.find_all("ul"):
        classes = ul.get("class", [])
        if "_wizOdr" in classes and "ul_3" in classes:
            return ul
    return None


def parse_department_links(page_url: str, html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    menu_ul = find_dept_menu_ul(soup)

    if not menu_ul:
        return []

    rows: List[Dict[str, str]] = []

    for li in menu_ul.find_all("li", recursive=False):
        a_tag = li.find("a", href=True)
        if not a_tag:
            continue

        dept_name = clean_text(a_tag.get_text(" ", strip=True))
        detail_url = make_absolute_url(a_tag["href"], page_url)

        if not dept_name or not detail_url:
            continue

        rows.append({
            "구분3": dept_name,
            "DETAIL_URL": detail_url,
        })

    return rows


def expand_detail_url_list(detail_url_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    입력:
        [
            {"구분1": "대학", "구분2": "자연과학대학", "구분3": "", "URL": "..."},
            ...
        ]

    출력:
        [
            {"구분1": "대학", "구분2": "자연과학대학", "구분3": "수학과(수정)", "URL": "...", "DETAIL_URL": "..."},
            {"구분1": "대학", "구분2": "자연과학대학", "구분3": "통계학과(수정)", "URL": "...", "DETAIL_URL": "..."},
            ...
        ]
    """
    session = create_session()
    result: List[Dict[str, str]] = []

    for item in detail_url_list:
        page_url = clean_text(item.get("URL", ""))

        if not page_url:
            continue

        try:
            resp = session.get(page_url, timeout=20)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"[ERROR] 요청 실패: {page_url} / {e}")
            continue

        dept_rows = parse_department_links(page_url, resp.text)

        if not dept_rows:
            print(f"[WARN] 학과 메뉴 없음: {page_url}")
            continue

        for dept in dept_rows:
            new_item = dict(item)
            new_item["구분3"] = dept["구분3"]
            new_item["DETAIL_URL"] = dept["DETAIL_URL"]
            result.append(new_item)

        print(f"[OK] {item.get('구분2', '')}: {len(dept_rows)}건")

    return result


if __name__ == "__main__":
    # detail_url_list 는 사용자가 직접 넣는다고 했으니 예시만 최소로 둠
    detail_url_list = [
        {
            "구분1": "대학",
            "구분2": "인문융합예술대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/humanity/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "사회과학대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/social/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "법과대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/lawdean/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "자연과학대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/natscience/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "공과대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/eng/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "IT융합대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/itc/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "간호대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/nursing/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "생활산업대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/lifeindustry/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "사범대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/teacher/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "미술대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/midae/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "음악대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/music/index.do",
        },
        {
            "구분1": "대학",
            "구분2": "창의융합대학",
            "구분3": "",
            "URL": "https://www.sungshin.ac.kr/generaledu/index.do",
        },
    ]

    expanded_list = expand_detail_url_list(detail_url_list)

    for row in expanded_list:
        print(row)