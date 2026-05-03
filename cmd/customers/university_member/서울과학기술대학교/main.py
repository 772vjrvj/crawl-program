# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException, TimeoutException


BASE_URL = "https://www.seoultech.ac.kr"
START_URL = "https://www.seoultech.ac.kr/intro/uvstat/orga"
OUTPUT_ORIGINAL_FILE = "seoultech_orga_final_original.xlsx"
OUTPUT_CLEAN_FILE = "seoultech_orga_final_clean.xlsx"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

PROFESSOR_KEYWORDS = [
    "교수소개",
    "교수 소개",
    "교수진소개",
    "교수진 소개",
    "교수진",
    "전담교수",
    "참여교수",
]

STAFF_KEYWORDS = [
    "교직원",
    "교직원소개",
    "교직원 소개",
    "직원소개",
]


# =========================
# 공통 유틸
# =========================

def clean_text(text):
    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def clean_professor_name(text):
    text = clean_text(text)
    text = text.replace("교수", "")
    text = text.replace("학과장", "")
    text = text.replace("전담", "")
    text = text.replace("참여", "")
    return clean_text(text)


def normalize_email_text(text):
    text = str(text)
    text = text.replace("＠", "@")
    text = re.sub(r"(?i)e\s*[-_ ]?\s*mail\s*[:：]?", " ", text)
    text = re.sub(r"(?i)\bemail\s*[:：]?", " ", text)
    text = re.sub(r"(?i)\bnull\b", " ", text)
    text = re.sub(r"\s*@\s*", "@", text)
    text = re.sub(r"\s*\.\s*", ".", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_first_email(text):
    text = normalize_email_text(text)
    emails = re.findall(EMAIL_RE, text)

    if emails:
        return emails[0]

    return ""


def get_text_before_br(a_tag):
    br = a_tag.find("br")

    if not br:
        return clean_text(a_tag.get_text(" ", strip=True))

    texts = []

    for item in a_tag.contents:
        if getattr(item, "name", None) == "br":
            break

        if hasattr(item, "get_text"):
            texts.append(item.get_text(" ", strip=True))
        else:
            texts.append(str(item))

    return clean_text(" ".join(texts))


def is_skip_url(url):
    if not url:
        return True

    lower_url = url.lower()

    if lower_url.startswith("javascript:"):
        return True

    if lower_url.startswith("mailto:"):
        return True

    if lower_url.startswith("tel:"):
        return True

    return False


def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    return res.text


def create_driver():
    options = Options()

    # 브라우저 화면 보고 싶으면 아래 한 줄만 주석 처리
    options.add_argument("--headless=new")

    options.page_load_strategy = "eager"

    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--blink-settings=imagesEnabled=false")

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(12)
    driver.set_script_timeout(12)

    return driver


def get_email_from_box(box):
    # 화면에 보이는 이메일 우선
    # 예: e-mail: goomj<a href="mailto:...">@seoultech.ac.kr</a>
    visible_text = box.get_text("", strip=True)
    email = get_first_email(visible_text)

    if email:
        return email

    visible_text = box.get_text(" ", strip=True)
    email = get_first_email(visible_text)

    if email:
        return email

    # 화면 텍스트에서 못 찾으면 mailto href 사용
    mail_a = box.select_one('a[href^="mailto:"]')

    if mail_a:
        href = mail_a.get("href", "").strip()
        email = href.replace("mailto:", "").strip()
        email = email.split("?")[0].strip()
        return email

    return ""


def get_staff_work_from_box(box):
    text = box.get_text("\n", strip=True)
    lines = text.split("\n")

    for line in lines:
        line = clean_text(line)

        if "담당업무" in line:
            line = line.replace("담당업무", "")
            line = line.replace(":", "")
            line = line.replace("：", "")
            return clean_text(line)

    return ""


# =========================
# 1차 / 2차 조직도 수집
# =========================

def collect_first_list():
    html = get_html(START_URL)
    soup = BeautifulSoup(html, "html.parser")

    rows = []

    for block in soup.select("li.v4, li.v5"):
        for box in block.select("ul.box"):
            for a_tag in box.select("a[href]"):
                name = get_text_before_br(a_tag)
                href = a_tag.get("href", "").strip()

                if not name or is_skip_url(href):
                    continue

                rows.append({
                    "대분류": name,
                    "중분류": "",
                    "소분류": "",
                    "URL": urljoin(BASE_URL, href),
                    "교수URL": "",
                    "교직원URL": "",
                })

    return rows


def collect_detail_list(row):
    try:
        html = get_html(row["URL"])
    except RequestException as e:
        print(f"  - 2차 접속 실패: {row['URL']}")
        print(f"  - 사유: {str(e)}")
        return [row]

    soup = BeautifulSoup(html, "html.parser")

    detail_rows = []

    # case 1: ul class="t15l bg mt10"
    for a_tag in soup.select("ul.t15l.bg.mt10 a[href]"):
        name = clean_text(a_tag.get_text(" ", strip=True))
        href = a_tag.get("href", "").strip()

        if not name or is_skip_url(href):
            continue

        detail_rows.append({
            "대분류": row["대분류"],
            "중분류": name,
            "소분류": name,
            "URL": urljoin(row["URL"], href),
            "교수URL": "",
            "교직원URL": "",
        })

    # case 2: div class="t15l bg mt10" > div class="oh"
    for oh in soup.select("div.t15l.bg.mt10 div.oh"):
        parent_a = oh.find("a", href=True, recursive=False)

        if not parent_a:
            continue

        parent_name = clean_text(parent_a.get_text(" ", strip=True))

        if not parent_name:
            continue

        for child_a in oh.select("ul li a[href]"):
            child_name = clean_text(child_a.get_text(" ", strip=True))
            href = child_a.get("href", "").strip()

            if not child_name or is_skip_url(href):
                continue

            detail_rows.append({
                "대분류": parent_name,
                "중분류": child_name,
                "소분류": child_name,
                "URL": urljoin(row["URL"], href),
                "교수URL": "",
                "교직원URL": "",
            })

    if not detail_rows:
        detail_rows.append(row)

    return detail_rows


# =========================
# 교수URL / 교직원URL 수집
# =========================

def has_menu_text(text, keywords):
    text = clean_text(text)
    text_no_space = text.replace(" ", "")

    for keyword in keywords:
        keyword_no_space = keyword.replace(" ", "")

        if keyword_no_space in text_no_space:
            return True

    return False


def find_menu_url_from_html(html, base_url, keywords):
    soup = BeautifulSoup(html, "html.parser")

    # a 태그 자체 텍스트에서 찾기
    for a_tag in soup.select("a[href]"):
        text = clean_text(a_tag.get_text(" ", strip=True))
        href = a_tag.get("href", "").strip()

        if has_menu_text(text, keywords) and not is_skip_url(href):
            return urljoin(base_url, href)

    # span, strong, b 등 내부 텍스트에서 찾고 부모 a 태그 확인
    text_nodes = soup.find_all(string=lambda x: x and has_menu_text(x, keywords))

    for text_node in text_nodes:
        parent = text_node.parent

        while parent:
            if getattr(parent, "name", "") == "a":
                href = parent.get("href", "").strip()

                if not is_skip_url(href):
                    return urljoin(base_url, href)

            parent = parent.parent

    return ""


def add_menu_urls(driver, row):
    url = row["URL"].strip()

    if not url:
        row["교수URL"] = ""
        row["교직원URL"] = ""
        return row

    if not url.startswith("http"):
        url = urljoin(BASE_URL, url)

    try:
        driver.get(url)

        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"]
        )

        time.sleep(0.5)

        html = driver.page_source
        current_url = driver.current_url

        row["교수URL"] = find_menu_url_from_html(html, current_url, PROFESSOR_KEYWORDS)
        row["교직원URL"] = find_menu_url_from_html(html, current_url, STAFF_KEYWORDS)

    except TimeoutException:
        print(f"  - 메뉴URL 접속 시간초과: {url}")
        row["교수URL"] = ""
        row["교직원URL"] = ""

    except WebDriverException as e:
        print(f"  - 메뉴URL 접속 실패: {url}")
        print(f"  - 사유: {(e and e.msg) or str(e)}")
        row["교수URL"] = ""
        row["교직원URL"] = ""

    return row


# =========================
# 교수 수집
# =========================

def get_name_from_prof_box(box):
    # 교수 case 1: .profList2
    name_tag = box.select_one(".view .name b")

    if name_tag:
        return clean_professor_name(name_tag.get_text(" ", strip=True))

    # 교수 case 2: .profList
    name_tag = box.select_one(".view .name a span")

    if name_tag:
        return clean_professor_name(name_tag.get_text(" ", strip=True))

    # fallback
    name_box = box.select_one(".view .name")

    if name_box:
        return clean_professor_name(name_box.get_text(" ", strip=True))

    return ""


def make_professor_data(name, email):
    return {
        "직위": "교수",
        "업무": "교육·연구",
        "이름": name,
        "이메일": email,
    }


def make_staff_data(work, name, email):
    work = clean_text(work)

    if not work:
        work = "행정"

    return {
        "직위": "행정",
        "업무": work,
        "이름": name,
        "이메일": email,
    }


def collect_prof_case_1_2(soup):
    rows = []

    # 교수 case 1: .profList2 > .box
    # 교수 case 2: .profList > .box
    boxes = soup.select(".profList2 > .box, .profList > .box")

    for box in boxes:
        name = get_name_from_prof_box(box)
        email = get_email_from_box(box)

        if not name:
            continue

        rows.append(make_professor_data(name, email))

    return rows


def collect_prof_case_3(soup):
    rows = []

    # 교수 case 3: .professor-list-wrap .professor-item
    items = soup.select(".professor-list-wrap .professor-item")

    for item in items:
        name_tag = item.select_one(".tit-box .name")
        name = ""

        if name_tag:
            name = clean_professor_name(name_tag.get_text(" ", strip=True))

        email = get_email_from_box(item)

        if not name:
            continue

        rows.append(make_professor_data(name, email))

    return rows


def collect_prof_case_4(soup):
    rows = []

    # 교수 case 4: .people .people_list
    people_list = soup.select(".people .people_list")

    for people in people_list:
        name_tag = people.select_one(".infor_list .title")
        name = ""

        if name_tag:
            name = clean_professor_name(name_tag.get_text(" ", strip=True))

        email = get_email_from_box(people)

        if not name:
            continue

        rows.append(make_professor_data(name, email))

    return rows


def collect_prof_case_5(soup):
    rows = []

    # 교수 case 5: .information .box
    boxes = soup.select(".information .box")

    for box in boxes:
        name_tag = box.select_one(".tb25")
        name = ""

        if name_tag:
            name = clean_professor_name(name_tag.get_text(" ", strip=True))

        if not name:
            continue

        rows.append(make_professor_data(name, ""))

    return rows


def collect_professors(professor_url):
    rows = []

    if not professor_url:
        return rows

    try:
        html = get_html(professor_url)
    except RequestException as e:
        print(f"  - 교수URL 접속 실패: {professor_url}")
        print(f"  - 사유: {str(e)}")
        return rows

    soup = BeautifulSoup(html, "html.parser")

    rows.extend(collect_prof_case_1_2(soup))
    rows.extend(collect_prof_case_3(soup))
    rows.extend(collect_prof_case_4(soup))
    rows.extend(collect_prof_case_5(soup))

    return remove_duplicate_people(rows)


# =========================
# 교직원 수집
# =========================

def collect_staff_case_1(soup):
    rows = []

    # 교직원 case 1: .staff > .box
    # .name = 이름
    # 담당업무: 뒤 텍스트 = 업무
    boxes = soup.select(".staff > .box")

    for box in boxes:
        name_tag = box.select_one(".t16 .name")
        name = ""

        if name_tag:
            name = clean_text(name_tag.get_text(" ", strip=True))

        work = get_staff_work_from_box(box)
        email = get_email_from_box(box)

        if not name and not work and not email:
            continue

        rows.append(make_staff_data(work, name, email))

    return rows


def collect_staff_case_2(soup):
    rows = []

    # 교직원 case 2: .professor-list-wrap .professor-item
    items = soup.select(".professor-list-wrap .professor-item")

    for item in items:
        name_tag = item.select_one(".tit-box .name")
        name = ""

        if name_tag:
            name = clean_text(name_tag.get_text(" ", strip=True))

        email = get_email_from_box(item)
        work = "행정"

        if not name and not email:
            continue

        rows.append(make_staff_data(work, name, email))

    return rows


def get_table_headers(table):
    first_tr = table.select_one("tr")

    if not first_tr:
        return []

    headers = []

    for cell in first_tr.select("th, td"):
        headers.append(clean_text(cell.get_text(" ", strip=True)))

    return headers


def collect_staff_case_3(soup):
    rows = []

    # 교직원 case 3: table01 형태
    # header: 연락처 / 이메일 / 담당업무 / 사무실
    tables = soup.select("table.table01")

    for table in tables:
        headers = get_table_headers(table)

        if "이메일" not in headers or "담당업무" not in headers:
            continue

        trs = table.select("tr")

        for tr in trs[1:]:
            cells = tr.select("td")

            if len(cells) < len(headers):
                continue

            email = ""
            work = ""
            name = ""

            for idx, header in enumerate(headers):
                value = clean_text(cells[idx].get_text(" ", strip=True))

                if "이메일" in header:
                    email = get_email_from_box(cells[idx])

                if "담당업무" in header:
                    work = value

                if "이름" in header or "성명" in header:
                    name = value

            if not work and not email and not name:
                continue

            rows.append(make_staff_data(work, name, email))

    return rows


def collect_staffs(staff_url):
    rows = []

    if not staff_url:
        return rows

    try:
        html = get_html(staff_url)
    except RequestException as e:
        print(f"  - 교직원URL 접속 실패: {staff_url}")
        print(f"  - 사유: {str(e)}")
        return rows

    soup = BeautifulSoup(html, "html.parser")

    rows.extend(collect_staff_case_1(soup))
    rows.extend(collect_staff_case_2(soup))
    rows.extend(collect_staff_case_3(soup))

    return remove_duplicate_people(rows)


# =========================
# 중복 / 결과 row / 저장
# =========================

def remove_duplicate_people(rows):
    result = []
    seen = set()

    for row in rows:
        key = (
            row.get("직위", ""),
            row.get("업무", ""),
            row.get("이름", ""),
            row.get("이메일", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result


def make_result_row(row, person, person_type):
    small = row["소분류"]
    position = person["직위"]
    work = person["업무"]

    if person_type == "staff":
        small = "행정"

        if not position:
            position = "행정"

        if not work:
            work = "행정"

    return {
        "대분류": row["대분류"],
        "중분류": row["중분류"],
        "소분류": small,
        "직위": position,
        "업무": work,
        "이름": person["이름"],
        "이메일": person["이메일"],
        "URL": row["URL"],
        "교수URL": row["교수URL"],
        "교직원URL": row["교직원URL"],
    }


def make_empty_row(row):
    return {
        "대분류": row["대분류"],
        "중분류": row["중분류"],
        "소분류": row["소분류"],
        "직위": "",
        "업무": "",
        "이름": "",
        "이메일": "",
        "URL": row["URL"],
        "교수URL": row["교수URL"],
        "교직원URL": row["교직원URL"],
    }


def get_columns():
    return [
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "교수URL",
        "교직원URL",
    ]


def save_excel(rows):
    columns = get_columns()
    df = pd.DataFrame(rows, columns=columns)

    # 1) 원본: 빈 이메일, 중복 이메일 모두 그대로 저장
    df.to_excel(OUTPUT_ORIGINAL_FILE, index=False)

    # 2) 정리본: 이메일 빈값 제거 + 이메일 기준 중복 제거
    clean_df = df.copy()
    clean_df["이메일"] = clean_df["이메일"].fillna("").astype(str).str.strip()
    clean_df = clean_df[clean_df["이메일"] != ""].copy()
    clean_df = clean_df.drop_duplicates(subset=["이메일"], keep="first").copy()
    clean_df.to_excel(OUTPUT_CLEAN_FILE, index=False)

    print(f"[완료] 원본 저장: {OUTPUT_ORIGINAL_FILE}")
    print(f"[건수] 원본 {len(df)}건")
    print(f"[완료] 정리본 저장: {OUTPUT_CLEAN_FILE}")
    print(f"[건수] 정리본 {len(clean_df)}건")


# =========================
# 전체 실행
# =========================

def collect_all_list():
    first_rows = collect_first_list()
    result_rows = []

    print(f"[1차] 수집 건수: {len(first_rows)}")

    for idx, row in enumerate(first_rows, start=1):
        print(f"[2차] {idx} / {len(first_rows)} {row['대분류']}")
        print(f"  - URL: {row['URL']}")

        detail_rows = collect_detail_list(row)
        result_rows.extend(detail_rows)

        time.sleep(0.2)

    print(f"[2차] 최종 건수: {len(result_rows)}")

    return result_rows


def add_all_menu_urls(rows):
    driver = create_driver()
    result_rows = []

    try:
        for idx, row in enumerate(rows, start=1):
            title = row["중분류"] if row["중분류"] else row["대분류"]

            print(f"[메뉴URL] {idx} / {len(rows)} {row['대분류']} > {title}")
            print(f"  - URL: {row['URL']}")

            row = add_menu_urls(driver, row)
            result_rows.append(row)

            if row["교수URL"]:
                print(f"  - 교수URL 발견: {row['교수URL']}")
            else:
                print("  - 교수URL 없음")

            if row["교직원URL"]:
                print(f"  - 교직원URL 발견: {row['교직원URL']}")
            else:
                print("  - 교직원URL 없음")

            time.sleep(0.3)

    finally:
        driver.quit()

    return result_rows


def collect_all_people(rows):
    result_rows = []
    professor_cache = {}
    staff_cache = {}

    for idx, row in enumerate(rows, start=1):
        title = row["중분류"] if row["중분류"] else row["대분류"]

        print(f"[상세수집] {idx} / {len(rows)} {row['대분류']} > {title}")

        professor_url = row["교수URL"]
        staff_url = row["교직원URL"]

        professor_rows = []
        staff_rows = []

        if professor_url:
            if professor_url not in professor_cache:
                print(f"  - 교수 접속: {professor_url}")
                professor_cache[professor_url] = collect_professors(professor_url)
                time.sleep(0.3)
            else:
                print("  - 교수URL 캐시 사용")

            professor_rows = professor_cache[professor_url]
        else:
            print("  - 교수URL 없음")

        if staff_url:
            if staff_url not in staff_cache:
                print(f"  - 교직원 접속: {staff_url}")
                staff_cache[staff_url] = collect_staffs(staff_url)
                time.sleep(0.3)
            else:
                print("  - 교직원URL 캐시 사용")

            staff_rows = staff_cache[staff_url]
        else:
            print("  - 교직원URL 없음")

        for person in professor_rows:
            result_rows.append(make_result_row(row, person, "professor"))

        for person in staff_rows:
            result_rows.append(make_result_row(row, person, "staff"))

        print(f"  - 교수 {len(professor_rows)}명")
        print(f"  - 교직원 {len(staff_rows)}명")

        if not professor_rows and not staff_rows:
            print("  - 상세 데이터 없음 / 빈 row 추가")
            result_rows.append(make_empty_row(row))

    return result_rows


def main():
    rows = collect_all_list()
    rows = add_all_menu_urls(rows)
    rows = collect_all_people(rows)

    for row in rows:
        print(row)

    save_excel(rows)


if __name__ == "__main__":
    main()
