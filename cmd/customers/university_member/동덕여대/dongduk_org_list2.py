# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


PAGE_URL = "https://www.dongduk.ac.kr/www/contents/kor-org.do?gotoMenuNo=kor-org#none"
BASE_URL = "https://www.dongduk.ac.kr"


def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_grad_links(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.org_graduate")
    if not article:
        return []

    result: List[Dict[str, str]] = []

    # h4 다음에 오는 dl 들을 순회하면서 dd 안의 p/a 수집
    for h4 in article.select("h4"):
        title = clean_text(h4.get_text())
        if not title:
            continue

        # 여기서는 사용자 요청대로 구분1을 고정 "대학원"으로 사용
        category1 = "대학원"

        node = h4.find_next_sibling()
        while node:
            if isinstance(node, Tag) and node.name == "h4":
                break

            if isinstance(node, Tag) and node.name == "dl":
                dd = node.find("dd")
                if dd:
                    for p in dd.find_all("p", recursive=False):
                        name = clean_text(p.get_text())
                        if not name:
                            continue

                        a = p.find("a")
                        href = ""
                        if a and a.get("href"):
                            href = clean_text(a["href"])
                            if href and href != "#none":
                                href = urljoin(BASE_URL, href)
                            else:
                                href = ""

                        result.append({
                            "구분1": category1,
                            "구분2": name,
                            "URL": href,
                        })

            node = node.find_next_sibling()

    return result


if __name__ == "__main__":
    html = fetch_html(PAGE_URL)
    rows = parse_grad_links(html)

    for row in rows:
        print(row)