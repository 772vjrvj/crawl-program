# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = "https://gsai.hanyang.ac.kr"
START_URL = "https://gsai.hanyang.ac.kr/front/graduateSchool/prof/professor"

MAJOR_NAME = "인공지능융합대학원"
OUT_FILE = "인공지능융합대학원_교수목록.xlsx"


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def make_driver():
    options = Options()

    # 화면 띄우기 싫으면 아래 주석 해제
    # options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")

    # === 신규 === 이미지/css/font 차단해서 속도 개선
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver


def wait_page(driver):
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    time.sleep(0.8)


def get_tab_links(driver):
    print("[탭] 교수 탭 링크 수집 시작")

    driver.get(START_URL)
    wait_page(driver)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    result = []

    # 상단 탭 링크
    for a in soup.select(".page-tab a, ul.count-6 a"):
        name = clean_text(a.get_text(" ", strip=True))
        href = a.get("href")

        if not name or not href:
            continue

        full_url = urljoin(BASE_URL, href)

        result.append({
            "tab_name": name,
            "url": full_url
        })

    # 중복 제거
    final = []
    seen = set()

    for row in result:
        key = row["url"]
        if key in seen:
            continue
        seen.add(key)
        final.append(row)

    print("[탭] 수집 링크 수:", len(final))

    for row in final:
        print(" -", row["tab_name"], row["url"])

    return final


def parse_professor_list(html, tab_name, page_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    items = soup.select(".professor_list .list")

    for item in items:
        h4 = item.select_one(".desc h4")
        if not h4:
            continue

        span = h4.select_one("span")

        position = ""
        if span:
            position = clean_text(span.get_text(" ", strip=True))
            span.extract()

        name = clean_text(h4.get_text(" ", strip=True))
        name = re.sub(r"\s+", " ", name).strip()

        # 빈 껍데기 방지
        if not name:
            continue

        info = {}

        for li in item.select(".desc ul li"):
            b = li.select_one("b")
            if not b:
                continue

            key = clean_text(b.get_text(" ", strip=True))
            b.extract()
            val = clean_text(li.get_text(" ", strip=True))

            info[key] = val

        email = ""
        mail_a = item.select_one('a[href^="mailto:"]')
        if mail_a:
            email = mail_a.get("href", "").replace("mailto:", "").strip()

        if not email:
            email = info.get("이메일", "")

        homepage = ""
        home_a = item.select_one("a.homepage_btn")
        if home_a:
            homepage = clean_text(home_a.get("href"))

        affiliation = info.get("소속", "")
        role = info.get("보직", "")
        research = info.get("연구분야", "")

        work_parts = []
        if role:
            work_parts.append(role)
        if research:
            work_parts.append(research)

        rows.append({
            "대분류": MAJOR_NAME,
            "중분류": tab_name,
            "소분류": tab_name,
            "직위": position,
            "업무": " / ".join(work_parts),
            "이름": name,
            "이메일": email,
            "URL": homepage,
            "소속": affiliation,
            "원본URL": page_url,
        })

    return rows


def collect_all(driver, tabs):
    all_rows = []

    for idx, tab in enumerate(tabs, start=1):
        tab_name = tab["tab_name"]
        url = tab["url"]

        print("[진행]", idx, "/", len(tabs), tab_name)
        print("      ", url)

        try:
            driver.get(url)
            wait_page(driver)

            rows = parse_professor_list(driver.page_source, tab_name, url)

            print("       수집:", len(rows), "명")

            # 교수 목록이 없으면 확인용 빈 row
            if len(rows) == 0:
                rows.append({
                    "대분류": MAJOR_NAME,
                    "중분류": tab_name,
                    "소분류": tab_name,
                    "직위": "",
                    "업무": "교수 목록 없음",
                    "이름": "",
                    "이메일": "",
                    "URL": "",
                    "소속": "",
                    "원본URL": url,
                })

            all_rows.extend(rows)

        except Exception as e:
            print("       오류:", e)

            all_rows.append({
                "대분류": MAJOR_NAME,
                "중분류": tab_name,
                "소분류": tab_name,
                "직위": "",
                "업무": "수집 실패: " + str(e),
                "이름": "",
                "이메일": "",
                "URL": "",
                "소속": "",
                "원본URL": url,
            })

    return all_rows


def save_excel(rows):
    df = pd.DataFrame(rows)

    columns = [
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "소속",
        "원본URL",
    ]

    df = df[columns]
    df.to_excel(OUT_FILE, index=False)

    print("[완료] 저장:", OUT_FILE)
    print("[완료] 전체 건수:", len(df))


def main():
    driver = make_driver()

    try:
        tabs = get_tab_links(driver)
        rows = collect_all(driver, tabs)
        save_excel(rows)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()