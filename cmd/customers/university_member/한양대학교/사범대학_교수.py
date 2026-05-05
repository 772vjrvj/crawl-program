# -*- coding: utf-8 -*-

import re
from datetime import datetime
from urllib.parse import urljoin

import requests
import pandas as pd
from bs4 import BeautifulSoup


BASE_URL = "https://education.hanyang.ac.kr"
START_URL = "https://education.hanyang.ac.kr/front/undergraduate/education/dean"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

DEPT_LIST = [
    {
        "name": "교육학과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/education/dean",
    },
    {
        "name": "교육공학과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/engineering/dean",
    },
    {
        "name": "국어교육과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/language/dean",
    },
    {
        "name": "영어교육과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/English/dean",
    },
    {
        "name": "수학교육과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/math/class",
    },
    {
        "name": "응용미술교육과",
        "dean_url": "https://education.hanyang.ac.kr/front/undergraduate/art/dean",
    },
]


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(session, url):
    print("[요청]", url)

    res = session.get(url, timeout=20)
    res.raise_for_status()
    res.encoding = res.apparent_encoding

    return res.text


def find_professor_url(session, dean_url):
    """
    학과 페이지에서 page-tab 안의 '교수소개' 링크를 찾아 교수소개 URL 반환
    """
    html = get_html(session, dean_url)
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.select(".page-tab a"):
        text = clean_text(a.get_text())
        href = a.get("href")

        if "교수소개" in text and href:
            return urljoin(BASE_URL, href)

    # page-tab 파싱 실패 시 URL 규칙으로 보조 처리
    if dean_url.endswith("/dean"):
        return dean_url.replace("/dean", "/professor")

    if dean_url.endswith("/class"):
        return dean_url.replace("/class", "/professor")

    return ""


def extract_professors(html, dept_name, page_url):
    soup = BeautifulSoup(html, "html.parser")

    rows = []

    # 일반 교수 카드 + special 명예교수 카드 모두 포함
    items = soup.select(".module-professor-class li")

    for item in items:
        name_el = item.select_one("p.subject strong")
        if not name_el:
            continue

        name = clean_text(name_el.get_text())

        email = ""

        mail_a = item.select_one("a[href^='mailto:']")
        if mail_a:
            email = mail_a.get("href", "").replace("mailto:", "").strip()

        if not email:
            text = item.get_text(" ", strip=True)
            found = re.findall(EMAIL_RE, text)
            if found:
                email = found[0].strip()

        rows.append({
            "구분": "대학",
            "대분류": "사범대학",
            "중분류": dept_name,
            "소분류": dept_name,
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": page_url,
        })

    return rows


def main():
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })

    all_rows = []

    for dept in DEPT_LIST:
        dept_name = dept["name"]
        dean_url = dept["dean_url"]

        print()
        print("[학과]", dept_name)

        prof_url = find_professor_url(session, dean_url)

        if not prof_url:
            print("[실패] 교수소개 URL 없음:", dept_name)
            continue

        html = get_html(session, prof_url)
        rows = extract_professors(html, dept_name, prof_url)

        print("[수집]", dept_name, len(rows), "명")

        all_rows.extend(rows)

    df = pd.DataFrame(all_rows, columns=[
        "구분", "대분류", "중분류", "소분류",
        "직위", "업무", "이름", "이메일", "URL"
    ])

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_name = "한양대_사범대학_교수_이메일_%s.xlsx" % now

    df.to_excel(excel_name, index=False)

    print()
    print("===== 엑셀 붙여넣기용 =====")
    print(df.to_csv(sep="\t", index=False))

    print("[완료]", excel_name)


if __name__ == "__main__":
    main()