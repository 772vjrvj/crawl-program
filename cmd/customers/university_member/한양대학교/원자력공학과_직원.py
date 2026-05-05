# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://hypa.hanyang.ac.kr"
START_URL = "https://hypa.hanyang.ac.kr/front/major/major-notice"

MAX_PAGE = 30

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

SKIP_EMAILS = [
    "leegn@hanyang.ac.kr",
    "kss007@hanyang.ac.kr",
    "koo4667@hanyang.ac.kr",
    "tykim1004@hanyang.ac.kr",
    "coramdeo@hanyang.ac.kr",
    "seokeun@hanyang.ac.kr",
    "ohseongsoo@hanyang.ac.kr",
    "donwe@hanyang.ac.kr",
    "hyewonk@hanyang.ac.kr",
]


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(session, url):
    res = session.get(url, timeout=20)
    res.raise_for_status()
    res.encoding = res.apparent_encoding
    return res.text


def make_list_url(page_no):
    if page_no == 1:
        return START_URL
    return START_URL + "?page=%s" % page_no


def get_list_links(session, page_no):
    url = make_list_url(page_no)
    print("[목록]", page_no, url)

    html = get_html(session, url)
    soup = BeautifulSoup(html, "html.parser")

    links = []
    seen = set()

    selectors = [
        ".board-default-list a[href*='notice-view?id=']",
        ".board-default-list a[href*='/view?id=']",
    ]

    for selector in selectors:
        for a in soup.select(selector):
            href = a.get("href")
            title_el = a.select_one(".subject")
            title = clean_text(title_el.get_text()) if title_el else clean_text(a.get_text())

            if not href:
                continue

            detail_url = urljoin(BASE_URL, href)

            if detail_url in seen:
                continue

            seen.add(detail_url)

            links.append({
                "title": title,
                "url": detail_url,
            })

    print("[상세 링크]", len(links), "개")
    return links


def find_email_from_detail(session, item):
    title = item["title"]
    url = item["url"]

    print("  [상세]", title)

    html = get_html(session, url)
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(".content")

    if content:
        text = content.get_text(" ", strip=True)
    else:
        text = soup.get_text(" ", strip=True)

    found = re.findall(EMAIL_RE, text)

    for email in found:
        email = email.strip().strip(".,;:()[]{}<>")
        email_lower = email.lower()

        if "@hanyang" not in email_lower:
            continue

        if email_lower in SKIP_EMAILS:
            print("    [제외]", email)
            continue

        return {
            "email": email,
            "title": title,
            "url": url,
        }

    return None


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    seen_detail_url = set()

    for page_no in range(1, MAX_PAGE + 1):
        links = get_list_links(session, page_no)

        if not links:
            print("[종료] 목록 없음")
            break

        for item in links:
            if item["url"] in seen_detail_url:
                continue

            seen_detail_url.add(item["url"])

            row = find_email_from_detail(session, item)

            if row:
                print()
                print("===== 발견 후 중지 =====")
                print("이메일:", row["email"])
                print("제목:", row["title"])
                print("URL:", row["url"])
                return

        time.sleep(0.3)

    print()
    print("===== 최종 결과 =====")
    print("제외 이메일 외에 @hanyang 이메일을 찾지 못했습니다.")


if __name__ == "__main__":
    main()