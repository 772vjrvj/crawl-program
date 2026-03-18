# -*- coding: utf-8 -*-
"""
동덕여대 조직도에서
구분1, 구분2, 구분3, URL 을 추출하여 CSV 저장

규칙
- article.org_collage 2개 중 display:none 제외
- ul.orz1 안의 li 순회
- 각 li 내부 ul.orz_blue 안의 li들을 모두 순회
- 구분1: "대학" 고정
- 구분2: 상위 대학명
- 구분3: 하위 전공/학과명
- URL: href가 절대주소면 그대로, 상대주소면 https://www.dongduk.ac.kr 붙임
"""

from __future__ import annotations

import csv
import re
from typing import List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.dongduk.ac.kr"
TARGET_URL = "https://www.dongduk.ac.kr/www/contents/kor-org.do?gotoMenuNo=kor-org"
OUTPUT_CSV = "dongduk_univ_org.csv"


def is_hidden_article(article: Tag) -> bool:
    """
    article 태그의 style 속성에 display:none 이 있으면 숨김으로 판단
    """
    style = (article.get("style") or "").strip().lower()
    style = re.sub(r"\s+", "", style)
    return "display:none" in style


def make_absolute_url(href: str) -> str:
    """
    href가 절대주소면 그대로 사용,
    상대주소면 BASE_URL 기준으로 절대주소 생성
    """
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(BASE_URL, href)


def get_visible_org_articles(soup: BeautifulSoup) -> List[Tag]:
    """
    article.org_collage 중 display:none 아닌 것만 반환
    """
    articles = soup.select("article.org_collage")
    visible_articles = []

    for article in articles:
        if not is_hidden_article(article):
            visible_articles.append(article)

    return visible_articles


def extract_rows_from_article(article: Tag) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    # article > ul.orz1 > li
    for top_li in article.select("ul.orz1 > li"):
        # 여기 p는 "대학" 같은 고정 분류
        top_name = top_li.select_one(":scope > p")
        category1 = top_name.get_text(" ", strip=True) if top_name else "대학"

        # 실제 대학 목록은 ul.orz_blue > li
        for college_li in top_li.select(":scope > ul.orz_blue > li"):
            # 구분2
            college_a = college_li.select_one(":scope > p > a")
            if not college_a:
                continue

            category2 = college_a.get_text(" ", strip=True)
            if not category2:
                continue

            # 구분3
            for major_a in college_li.select("ul.orz_gray a"):
                category3 = major_a.get_text(" ", strip=True)
                href = (major_a.get("href") or "").strip()

                if not category3:
                    continue

                rows.append(
                    {
                        "구분1": category1,
                        "구분2": category2,
                        "구분3": category3,
                        "URL": make_absolute_url(href),
                    }
                )

    return rows

def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def deduplicate_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    중복 제거
    """
    seen = set()
    result = []

    for row in rows:
        key = (row["구분1"], row["구분2"], row["구분3"], row["URL"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)

    return result


def save_csv(rows: List[Dict[str, str]], filepath: str) -> None:
    fieldnames = ["구분1", "구분2", "구분3", "URL"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    html = fetch_html(TARGET_URL)
    soup = BeautifulSoup(html, "html.parser")

    visible_articles = get_visible_org_articles(soup)

    all_rows: List[Dict[str, str]] = []
    for article in visible_articles:
        rows = extract_rows_from_article(article)
        all_rows.extend(rows)

    all_rows = deduplicate_rows(all_rows)

    save_csv(all_rows, OUTPUT_CSV)

    print(f"완료: {OUTPUT_CSV}")
    print(f"총 {len(all_rows)}건 저장")


if __name__ == "__main__":
    main()