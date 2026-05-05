# -*- coding: utf-8 -*-

import re
import time
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


START_URL = "https://biz.hanyang.ac.kr/70_"
BASE_URL = "https://biz.hanyang.ac.kr"

TARGET_TABS = [
    "경영전략/벤처",
    "경영정보",
    "글로벌경영",
    "마케팅",
    "OSM",
    "재무금융",
    "조직인사",
    "회계",
    "교육전담",
    "겸임교수",
    "특임/특훈/대우",
    "명예교수",
]

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def make_driver():
    options = Options()

    # 브라우저 안 보고 돌릴 때 사용
    # options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    return driver


def get_professor_menu_urls(driver):
    """
    교수진소개 하위 메뉴에서
    경영전략/벤처, 경영정보, 글로벌경영 ... 명예교수 URL 수집
    """
    driver.get(START_URL)

    WebDriverWait(driver, 15).until(
        lambda d: len(d.find_elements("css selector", "a.dropdown-item")) > 0
    )

    soup = BeautifulSoup(driver.page_source, "html.parser")

    menu_map = {}

    for a in soup.select("a.dropdown-item"):
        name = clean_text(a.get_text())
        href = a.get("href")

        if name in TARGET_TABS and href:
            menu_map[name] = urljoin(BASE_URL, href)

    # 혹시 좌측 메뉴 파싱 실패할 때 대비
    default_map = {
        "경영전략/벤처": "https://biz.hanyang.ac.kr/70_",
        "경영정보": "https://biz.hanyang.ac.kr/-27",
        "글로벌경영": "https://biz.hanyang.ac.kr/-29",
        "마케팅": "https://biz.hanyang.ac.kr/-30",
        "OSM": "https://biz.hanyang.ac.kr/-32",
        "재무금융": "https://biz.hanyang.ac.kr/-33",
        "조직인사": "https://biz.hanyang.ac.kr/-34",
        "회계": "https://biz.hanyang.ac.kr/-35",
        "교육전담": "https://biz.hanyang.ac.kr/-36",
        "겸임교수": "https://biz.hanyang.ac.kr/-12",
        "특임/특훈/대우": "https://biz.hanyang.ac.kr/81_",
        "명예교수": "https://biz.hanyang.ac.kr/-39",
    }

    for tab_name in TARGET_TABS:
        if tab_name not in menu_map:
            menu_map[tab_name] = default_map[tab_name]

    return menu_map


def extract_professors_from_page(driver, tab_name, url):
    """
    각 교수 페이지에서 이름 / 이메일 추출
    """
    print("[접속]", tab_name, url)

    driver.get(url)

    WebDriverWait(driver, 15).until(
        lambda d: len(d.find_elements("css selector", "body")) > 0
    )

    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    rows = []

    cards = soup.select(".hyu-fragment-component-profile")

    for card in cards:
        name_el = card.select_one(".hyu-profile-info-title-name")
        name = clean_text(name_el.get_text()) if name_el else ""

        email = ""

        mail_a = card.select_one("a[href^='mailto:']")
        if mail_a:
            email = mail_a.get("href", "").replace("mailto:", "").strip()

        if not email:
            text = card.get_text(" ", strip=True)
            found = re.findall(EMAIL_RE, text)
            if found:
                email = found[0].strip()

        if not name and not email:
            continue

        rows.append({
            "구분": "대학",
            "대분류": "경영대학",
            "중분류": "경영학부",
            "소분류": tab_name,
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": url,
        })

    # 일부 페이지가 다른 카드 구조일 때 보조 파싱
    if not rows:
        for item in soup.select("li"):
            text = item.get_text(" ", strip=True)
            found = re.findall(EMAIL_RE, text)

            if not found:
                continue

            email = found[0].strip()

            name = ""
            name_el = item.select_one("strong")
            if name_el:
                name = clean_text(name_el.get_text())

            if not name:
                continue

            rows.append({
                "구분": "대학",
                "대분류": "경영대학",
                "중분류": "경영학부",
                "소분류": tab_name,
                "직위": "교수",
                "업무": "교육.연구",
                "이름": name,
                "이메일": email,
                "URL": url,
            })

    print("[수집]", tab_name, len(rows), "명")
    return rows


def main():
    driver = make_driver()

    try:
        all_rows = []

        menu_map = get_professor_menu_urls(driver)

        print("[메뉴 수]", len(menu_map))

        for tab_name in TARGET_TABS:
            url = menu_map.get(tab_name)

            if not url:
                print("[스킵] URL 없음:", tab_name)
                continue

            rows = extract_professors_from_page(driver, tab_name, url)
            all_rows.extend(rows)

        # 이메일 기준 중복 제거
        result = []
        seen = set()

        for row in all_rows:
            key = row["이메일"].lower()

            if key and key in seen:
                continue

            if key:
                seen.add(key)

            result.append(row)

        df = pd.DataFrame(result, columns=[
            "구분", "대분류", "중분류", "소분류",
            "직위", "업무", "이름", "이메일", "URL"
        ])

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_name = "한양대_경영대학_교수_이메일_%s.xlsx" % now

        df.to_excel(excel_name, index=False)

        print()
        print("===== 엑셀 붙여넣기용 =====")
        print(df.to_csv(sep="\t", index=False))

        print("[완료]", excel_name)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()