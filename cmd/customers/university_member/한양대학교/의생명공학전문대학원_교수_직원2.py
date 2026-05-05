# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://bmse.hanyang.ac.kr"

PROF_URLS = [
    ("생체의공학과", "https://bmse.hanyang.ac.kr/sub/sub01_03.php?cat_no=3"),
    ("의생명과학과", "https://bmse.hanyang.ac.kr/sub/sub01_03.php?cat_no=4"),
    ("임상의과학과", "https://bmse.hanyang.ac.kr/sub/sub01_03.php?cat_no=5"),
    ("생명의료정보학과", "https://bmse.hanyang.ac.kr/sub/sub01_03.php?cat_no=6"),
]

STAFF_URL = "https://bmse.hanyang.ac.kr/sub/sub01_03_02.php"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": BASE_URL,
    }

    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    res.encoding = res.apparent_encoding
    return res.text


def parse_name(name_text):
    """
    예)
    장동표 (Jang, Dong Pyo) -> 장동표
    이제연  (Jeyeon Lee) -> 이제연
    """
    name_text = clean_text(name_text)
    name_text = re.sub(r"\(.*?\)", "", name_text)
    return clean_text(name_text)


def parse_member_list(html, group_name, person_type, page_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    members = soup.select(".member-list ul li")

    for li in members:
        position = clean_text(li.select_one(".name .position").get_text(" ", strip=True)) if li.select_one(".name .position") else ""
        name = parse_name(li.select_one(".name p").get_text(" ", strip=True)) if li.select_one(".name p") else ""

        info_text = clean_text(li.select_one(".info").get_text(" ", strip=True)) if li.select_one(".info") else ""
        email_match = EMAIL_RE.search(info_text)
        email = email_match.group(0) if email_match else ""

        detail_a = li.select_one(".btn-view a")
        detail_url = ""
        if detail_a and detail_a.get("href"):
            detail_url = urljoin(page_url, detail_a.get("href"))

        rows.append({
            "구분": person_type,
            "학과": group_name,
            "직위": person_type,
            "업무": position,
            "이름": name,
            "이메일": email,
            "URL": detail_url,
        })

    return rows


def collect_professors():
    all_rows = []

    print("[교수] 수집 시작")

    for idx, item in enumerate(PROF_URLS, start=1):
        group_name = item[0]
        url = item[1]

        print("[교수]", idx, "/", len(PROF_URLS), group_name, url)

        html = get_html(url)
        rows = parse_member_list(html, group_name, "교수", url)
        all_rows.extend(rows)

        print("  - 수집:", len(rows), "명")
        time.sleep(0.3)

    return all_rows


def collect_staff():
    all_rows = []

    print("[직원] 수집 시작")
    html = get_html(STAFF_URL)
    soup = BeautifulSoup(html, "html.parser")

    tab_links = soup.select(".sub-tab a")

    if tab_links:
        for idx, a in enumerate(tab_links, start=1):
            group_name = clean_text(a.get_text(" ", strip=True))
            url = urljoin(STAFF_URL, a.get("href"))

            print("[직원]", idx, "/", len(tab_links), group_name, url)

            html = get_html(url)
            rows = parse_member_list(html, group_name, "직원", url)
            all_rows.extend(rows)

            print("  - 수집:", len(rows), "명")
            time.sleep(0.3)
    else:
        print("[직원] 단일 페이지", STAFF_URL)
        rows = parse_member_list(html, "직원", "직원", STAFF_URL)
        all_rows.extend(rows)
        print("  - 수집:", len(rows), "명")

    return all_rows


def save_excel(rows):
    df = pd.DataFrame(rows)

    columns = ["구분", "학과", "직위", "업무", "이름", "이메일", "URL"]
    df = df.reindex(columns=columns)

    filename = "한양대_의생명공학전문대학원_교수_직원.xlsx"
    df.to_excel(filename, index=False)

    print("[완료] 저장:", filename)
    print("[완료] 총 수집:", len(df), "건")


def main():
    rows = []

    rows.extend(collect_professors())
    rows.extend(collect_staff())

    save_excel(rows)


if __name__ == "__main__":
    main()