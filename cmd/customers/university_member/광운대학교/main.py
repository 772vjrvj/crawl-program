# -*- coding: utf-8 -*-

import time
import re
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


START_URL = "https://www.kw.ac.kr/ko/univ/glance.jsp"
IACF_URL = "https://iacf.kw.ac.kr/sub01/sub04.php"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

COLUMNS = [
    "분류", "대분류", "중분류", "소분류",
    "직위", "업무", "이름", "이메일",
    "URL", "교수URL"
]


def clean(text):
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def get_text(tag):
    if not tag:
        return ""
    return clean(tag.get_text(" ", strip=True))


def get_href(a, base_url=START_URL):
    if not a:
        return ""
    return urljoin(base_url, a.get("href", ""))


def get_email(text):
    emails = re.findall(EMAIL_RE, text or "")
    if emails:
        return emails[0].strip()
    return ""


def make_driver():
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=options)


def get_soup(driver, url):
    driver.get(url)
    time.sleep(0.7)
    return BeautifulSoup(driver.page_source, "html.parser")


def make_row(base, sub_name, position, work, name, email, prof_url=""):
    return {
        "분류": base.get("분류", ""),
        "대분류": base.get("대분류", ""),
        "중분류": base.get("중분류", ""),
        "소분류": sub_name,
        "직위": position,
        "업무": work,
        "이름": name,
        "이메일": email,
        "URL": base.get("URL", ""),
        "교수URL": prof_url
    }


def collect_menu(driver):
    soup = get_soup(driver, START_URL)

    rows = []
    lnb = soup.select_one("ul.lnb-list")

    for cate_li in lnb.find_all("li", recursive=False):
        cate_a = cate_li.find("a", recursive=False)
        cate_name = get_text(cate_a)

        cate_ul = cate_li.find("ul", recursive=False)
        if not cate_ul:
            continue

        for big_li in cate_ul.find_all("li", recursive=False):
            big_a = big_li.find("a", recursive=False)
            big_name = get_text(big_a)

            if big_name == "한눈에 보는 대학":
                continue

            mid_ul = big_li.find("ul", recursive=False)

            if mid_ul:
                for mid_li in mid_ul.find_all("li", recursive=False):
                    mid_a = mid_li.find("a", recursive=False)
                    mid_name = get_text(mid_a)
                    is_intro = "N"

                    if mid_name == "한눈에 보는 대학":
                        continue

                    if mid_name == "소개":
                        mid_name = big_name
                        is_intro = "Y"

                    rows.append({
                        "분류": cate_name,
                        "대분류": big_name,
                        "중분류": mid_name,
                        "URL": get_href(mid_a),
                        "소개여부": is_intro
                    })
            else:
                rows.append({
                    "분류": cate_name,
                    "대분류": big_name,
                    "중분류": big_name,
                    "URL": get_href(big_a),
                    "소개여부": "N"
                })

    return rows


def collect_intro_staff(soup, base):
    rows = []
    target_table = None

    for section in soup.select("section.h3_contents-block"):
        h3_text = get_text(section.find("h3"))
        if "담당직원" in h3_text:
            target_table = section.select_one("table")
            break

    if not target_table:
        return [make_row(base, "행정", "", "", "", "")]

    for tr in target_table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        name = get_text(tds[0])
        position = get_text(tds[1])
        work = get_text(tds[2])
        email = get_email(get_text(tds[5]))

        rows.append(make_row(base, "행정", position, work, name, email))

    if not rows:
        rows.append(make_row(base, "행정", "", "", "", ""))

    return rows


def collect_admin_email(soup, base):
    email = ""

    email_box = soup.select_one("span.ico-circle.email")
    if email_box:
        email = get_email(get_text(email_box))

    if not email:
        mail_a = soup.select_one("a[href^='mailto:']")
        if mail_a:
            email = get_email(mail_a.get("href", "") + " " + get_text(mail_a))

    return [make_row(base, "행정", "", "행정", "", email)]


def find_professor_url(soup, base_url):
    for a in soup.select("nav.tab.tab-inc a"):
        if "교수진" in get_text(a):
            return urljoin(base_url, a.get("href", ""))

    for a in soup.select("nav.tab a"):
        if "교수진" in get_text(a):
            return urljoin(base_url, a.get("href", ""))

    return ""


def collect_professors(driver, professor_url, base):
    rows = []

    if not professor_url:
        return rows

    soup = get_soup(driver, professor_url)
    table = soup.select_one("table#departmentProfessor")

    if not table:
        return rows

    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        name = get_text(tds[1])
        email = get_email(get_text(tds[4]))

        rows.append(make_row(
            base=base,
            sub_name=base["중분류"],
            position="교수",
            work="교육·연구",
            name=name,
            email=email,
            prof_url=professor_url
        ))

    return rows


def collect_iacf(driver):
    print("[3] 산학협력단 수집 시작")

    soup = get_soup(driver, IACF_URL)
    rows = []

    for box in soup.select("div.write_it.popup_write_it"):
        table = box.select_one("table")
        if not table:
            continue

        for tr in table.select("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 6:
                continue

            dept = get_text(tds[0])
            position = get_text(tds[1]).replace("(", " (").replace(")", ")")
            name = get_text(tds[2])
            work = get_text(tds[3])
            email = get_email(get_text(tds[5]))

            base = {
                "분류": "산학협력단",
                "대분류": "산학협력단",
                "중분류": dept,
                "URL": IACF_URL
            }

            rows.append(make_row(base, "행정", position, work, name, email, ""))

    print("[3] 산학협력단 수집 완료:", len(rows), "건")
    return rows


def save_excel(rows):
    now = datetime.now().strftime("%Y%m%d%H%M%S")

    original_file = "광운대학교_이메일_전체원본_" + now + ".xlsx"
    clean_file = "광운대학교_이메일_정리본_" + now + ".xlsx"

    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_excel(original_file, index=False, sheet_name="전체원본")

    clean_df = df.copy()
    clean_df["이메일"] = clean_df["이메일"].fillna("").astype(str).str.strip()
    clean_df = clean_df[clean_df["이메일"] != ""]
    clean_df["_email_key"] = clean_df["이메일"].str.lower()
    clean_df = clean_df.drop_duplicates("_email_key", keep="first")
    clean_df = clean_df.drop(columns=["_email_key"])
    clean_df.to_excel(clean_file, index=False, sheet_name="정리본")

    print("[엑셀] 전체 원본 저장 완료:", original_file)
    print("[엑셀] 정리본 저장 완료:", clean_file)


def main():
    driver = make_driver()

    print("[1] 학과 목록 수집 시작")
    menu_rows = collect_menu(driver)
    print("[1] 학과 목록 수집 완료:", len(menu_rows), "건")

    result_rows = []

    for i, row in enumerate(menu_rows, start=1):
        print(f"[2] {i}/{len(menu_rows)} 처리중 - {row['분류']} > {row['대분류']} > {row['중분류']}")

        soup = get_soup(driver, row["URL"])

        if row["소개여부"] == "Y":
            staff_rows = collect_intro_staff(soup, row)
            result_rows.extend(staff_rows)
            print("    - 소개 담당직원:", len(staff_rows), "건")
        else:
            admin_rows = collect_admin_email(soup, row)
            result_rows.extend(admin_rows)

            professor_url = find_professor_url(soup, row["URL"])
            professor_rows = collect_professors(driver, professor_url, row)
            result_rows.extend(professor_rows)

            print("    - 행정 이메일:", admin_rows[0]["이메일"])
            print("    - 교수URL:", professor_url)
            print("    - 교수:", len(professor_rows), "건")

    result_rows.extend(collect_iacf(driver))

    driver.quit()

    print("[4] 전체 수집 결과:", len(result_rows), "건")
    save_excel(result_rows)


main()
