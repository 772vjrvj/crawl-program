# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import UnexpectedAlertPresentException, TimeoutException, WebDriverException

START_URL = "https://www.dongguk.edu/page/853#none"
OUT_FILE = "동국대_대학원_교수목록.xlsx"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

DEPT_MENU_NAMES = [
    "학과안내",
    "학과(전공)",
    "전공안내"
]

PROF_TOP_MENU_NAMES = [
    "교수소개",
    "교수 소개",
    "교수진 소개",
    "교수진"
]

PROF_LINK_TEXTS = [
    "교수진",
    "교수소개",
    "교수 소개",
    "교수진 소개"
]

SKIP_TEXTS = [
    "교과과정 안내",
    "교과과정안내",
    "교과과정",
    "교과이수기준",
    "전공별 세부교육과정"
]

def close_alert(driver):
    try:
        alert = driver.switch_to.alert
        text = alert.text
        alert.accept()
        print("[알림닫기]", text)
    except Exception:
        pass

def clean_text(text):
    return " ".join(str(text).split()).strip()


def norm_text(text):
    return clean_text(text).replace(" ", "")


def is_menu_text(text, names):
    text = norm_text(text)

    for name in names:
        if text == norm_text(name):
            return True

    return False


def is_skip_text(text):
    text = norm_text(text)

    for word in SKIP_TEXTS:
        if norm_text(word) in text:
            return True

    return False


def add_dept_admin_email_rows(result_rows, base_row, soup):
    emails = find_emails(soup.get_text(" ", strip=True))
    emails = list(dict.fromkeys(emails))

    for email in emails:
        result_rows.append({
            "구분": "대학원",
            "대분류": base_row["대분류"],
            "중분류": base_row["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": "행정",
            "이름": "",
            "이메일": email,
            "URL": base_row["URL"],
            "학과URL": base_row.get("학과URL", ""),
            "교수URL": ""
        })

        print("[행정]", base_row["대분류"], ">", base_row["중분류"], email)




def find_emails(text):
    return list(dict.fromkeys(re.findall(EMAIL_RE, text)))


def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver


def get_soup(driver, url):
    try:
        driver.get(url)
        time.sleep(1)
        return BeautifulSoup(driver.page_source, "html.parser")

    except UnexpectedAlertPresentException:
        close_alert(driver)
        print("[페이지 스킵 - 알림]", url)
        return BeautifulSoup("", "html.parser")

    except TimeoutException:
        print("[페이지 스킵 - 타임아웃]", url)
        return BeautifulSoup("", "html.parser")

    except WebDriverException as e:
        close_alert(driver)
        print("[페이지 스킵 - 실패]", url, str(e).splitlines()[0])
        return BeautifulSoup("", "html.parser")


def get_graduate_list(driver):
    soup = get_soup(driver, START_URL)

    rows = []

    for li in soup.select(".ft-major-list li"):
        title_a = li.select_one("p.ft-major-tit a")
        if not title_a:
            continue

        title = clean_text(title_a.get_text(" ", strip=True))

        if title != "대학원":
            continue

        for a in li.select(".col a"):
            name = clean_text(a.get_text(" ", strip=True))
            url = a.get("href", "").strip()

            rows.append({
                "구분": "대학원",
                "대분류": name,
                "중분류": name,
                "소분류": name,
                "URL": url,
                "학과URL": ""
            })

            print("[대학원]", name, url)

    return rows


def get_top_menu_links(soup, base_url, menu_names):
    links = []

    for li in soup.select("#gnb ul.depth01 > li"):
        menu_a = li.find("a", recursive=False)
        if not menu_a:
            continue

        menu_text = clean_text(menu_a.get_text(" ", strip=True))

        if not is_menu_text(menu_text, menu_names):
            continue

        for a in li.select(".depth02 a"):
            text = clean_text(a.get_text(" ", strip=True))
            href = a.get("href", "").strip()

            if not text or not href or href == "#":
                continue

            links.append({
                "text": text,
                "url": urljoin(base_url, href)
            })

    for dl in soup.select(".gnbs .sitemap_nav3 dl"):
        dt = dl.select_one("dt")
        if not dt:
            continue

        menu_text = clean_text(dt.get_text(" ", strip=True))

        if not is_menu_text(menu_text, menu_names):
            continue

        for a in dl.select("dd a"):
            text = clean_text(a.get_text(" ", strip=True))
            href = a.get("href", "").strip()

            if not text or not href or href == "#":
                continue

            links.append({
                "text": text,
                "url": urljoin(base_url, href)
            })

    return unique_links(links)


def unique_links(links):
    result = []
    seen = set()

    for item in links:
        key = item["text"] + "|" + item["url"]
        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def get_dept_list(soup, grad_row):
    grad_name = grad_row["대분류"]
    grad_url = grad_row["URL"]

    links = get_top_menu_links(soup, grad_url, DEPT_MENU_NAMES)

    rows = []

    for item in links:
        dept_name = item["text"]
        dept_url = item["url"]

        if is_skip_text(dept_name):
            continue

        if is_menu_text(dept_name, PROF_LINK_TEXTS):
            continue

        rows.append({
            "구분": "대학원",
            "대분류": grad_name,
            "중분류": dept_name,
            "소분류": dept_name,
            "URL": grad_url,
            "학과URL": dept_url
        })

        print("[학과]", grad_name, ">", dept_name, dept_url)

    return rows


def get_professor_links(soup, base_url):
    links = []

    # 교수소개 / 교수진 소개 메뉴 안의 링크
    links.extend(get_top_menu_links(soup, base_url, PROF_TOP_MENU_NAMES))

    # 영상대학원 case:
    # 학과 페이지 안의 .menu_tabs .depth3 에 교수진 소개 링크가 있음
    for a in soup.select(".menu_tabs .depth3 a, .menu_tabs .depth4 a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href or href == "#":
            continue

        if "/professor/list" in href or is_menu_text(text, PROF_LINK_TEXTS):
            links.append({
                "text": text,
                "url": urljoin(base_url, href)
            })

    # 전체 a 중에서 text가 교수진 / 교수소개 / 교수진 소개 인 것만 추가
    for a in soup.select("a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href or href == "#":
            continue

        if is_menu_text(text, PROF_LINK_TEXTS):
            links.append({
                "text": text,
                "url": urljoin(base_url, href)
            })

    # 왼쪽 메뉴 case
    for a in soup.select(".s_left_area_menu1 a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href or href == "#":
            continue

        if is_menu_text(text, PROF_LINK_TEXTS):
            links.append({
                "text": text,
                "url": urljoin(base_url, href)
            })

    return unique_links(links)


def get_bo_cate_urls(soup, base_url):
    urls = []

    for a in soup.select("#bo_cate a"):
        text = clean_text(a.get_text(" ", strip=True))
        text = text.replace("열린 분류", "").strip()

        href = a.get("href", "").strip()

        if not text or not href or href == "#":
            continue

        urls.append({
            "text": text,
            "url": urljoin(base_url, href)
        })

    return unique_links(urls)


def get_depth_professor_urls(soup, professor_url):
    urls = []

    # 교수진 카테고리가 있으면 그 링크들을 우선 사용
    bo_cate_urls = get_bo_cate_urls(soup, professor_url)

    if bo_cate_urls:
        return bo_cate_urls

    # 교수소개 내부 professor/list 카테고리
    for a in soup.select(".menu_tabs .depth4 a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not href or href == "#":
            continue

        if "/professor/list" in href:
            urls.append({
                "text": text,
                "url": urljoin(professor_url, href)
            })

    for a in soup.select(".menu_tabs .depth3 a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not href or href == "#":
            continue

        if "/professor/list" in href:
            urls.append({
                "text": text,
                "url": urljoin(professor_url, href)
            })

        elif is_menu_text(text, PROF_LINK_TEXTS):
            urls.append({
                "text": text,
                "url": urljoin(professor_url, href)
            })

    return unique_links(urls)


def parse_prof_items(soup):
    rows = []

    for item in soup.select(".prof_item"):
        name = ""
        email = ""

        name_tag = item.select_one(".prof_info strong")
        if name_tag:
            name = clean_text(name_tag.get_text(" ", strip=True))

        mail_tag = item.select_one("li.mail .txt")
        if mail_tag:
            email = clean_text(mail_tag.get_text(" ", strip=True))

        if email == "-":
            email = ""

        if not email:
            emails = find_emails(item.get_text(" ", strip=True))
            if emails:
                email = emails[0]

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


def parse_tbl_basic2(soup):
    rows = []

    for table in soup.select("table.tbl_basic2"):
        name = ""
        email = ""

        name_tag = table.select_one("strong")
        if name_tag:
            name = clean_text(name_tag.get_text(" ", strip=True))

        emails = find_emails(table.get_text(" ", strip=True))
        if emails:
            email = emails[0]

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


def parse_professors(soup):
    rows = []

    rows.extend(parse_prof_items(soup))
    rows.extend(parse_tbl_basic2(soup))

    return rows


def get_professors(driver, professor_url):
    result = []

    soup = get_soup(driver, professor_url)

    if not soup.get_text(strip=True):
        print("[교수URL 스킵]", professor_url)
        return result

    depth_urls = get_depth_professor_urls(soup, professor_url)

    if not depth_urls:
        depth_urls = [{
            "text": "",
            "url": professor_url
        }]

    for item in depth_urls:
        url = item["url"]
        cate_name = item["text"]

        prof_soup = get_soup(driver, url)

        if not prof_soup.get_text(strip=True):
            print("[교수상세 스킵]", url)
            continue

        profs = parse_professors(prof_soup)

        for prof in profs:
            prof["교수URL"] = url
            prof["분류명"] = cate_name
            result.append(prof)

        print("[교수수집]", url, len(profs), "명")

    return result


def get_professor_category_names(base_row, cate_name=""):
    # 학과가 있는 경우: 교수 탭명은 쓰지 않고 학과명을 중분류/소분류에 그대로 사용
    if base_row.get("학과URL"):
        return base_row["중분류"], base_row["소분류"]

    # 학과가 없는 경우: 중분류/소분류 모두 대분류와 동일하게 처리
    return base_row["대분류"], base_row["대분류"]


def make_empty_professor_row(base_row, professor_url):
    mid_name, sub_name = get_professor_category_names(base_row)

    return {
        "구분": "대학원",
        "대분류": base_row["대분류"],
        "중분류": mid_name,
        "소분류": sub_name,
        "직위": "교수",
        "업무": "교육·연구",
        "이름": "",
        "이메일": "",
        "URL": base_row["URL"],
        "학과URL": base_row.get("학과URL", ""),
        "교수URL": professor_url
    }


def collect_professor_rows(driver, result_rows, base_row, professor_links):
    if not professor_links:
        result_rows.append(make_empty_professor_row(base_row, ""))
        return

    total = 0

    for item in professor_links:
        professor_url = item["url"]
        professors = get_professors(driver, professor_url)
        total += len(professors)

        if not professors:
            result_rows.append(make_empty_professor_row(base_row, professor_url))

        for prof in professors:
            mid_name, sub_name = get_professor_category_names(base_row, prof.get("분류명", ""))

            result_rows.append({
                "구분": "대학원",
                "대분류": base_row["대분류"],
                "중분류": mid_name,
                "소분류": sub_name,
                "직위": "교수",
                "업무": "교육·연구",
                "이름": prof.get("이름", ""),
                "이메일": prof.get("이메일", ""),
                "URL": base_row["URL"],
                "학과URL": base_row.get("학과URL", ""),
                "교수URL": prof.get("교수URL", professor_url)
            })

    print("[교수완료]", base_row["대분류"], ">", base_row["중분류"], total, "명")


def add_education_admin_rows(result_rows, grad_row, soup):
    emails = find_emails(soup.get_text(" ", strip=True))[:2]

    for email in emails:
        result_rows.append({
            "구분": "대학원",
            "대분류": grad_row["대분류"],
            "중분류": grad_row["대분류"],
            "소분류": "행정",
            "직위": "",
            "업무": "행정",
            "이름": "",
            "이메일": email,
            "URL": grad_row["URL"],
            "학과URL": "",
            "교수URL": ""
        })

        print("[교육대학원 행정]", email)


def is_direct_professor_grad(grad_name):
    names = [
        "미래융합대학원",
        "교육서비스과학대학원"
    ]

    return grad_name in names


def main():
    print("[시작] 동국대 대학원 교수 목록 수집")

    driver = make_driver()

    grad_rows = get_graduate_list(driver)
    result_rows = []

    for i, grad_row in enumerate(grad_rows, start=1):
        grad_name = grad_row["대분류"]
        grad_url = grad_row["URL"]

        print("[진행]", i, "/", len(grad_rows), grad_name)

        soup = get_soup(driver, grad_url)

        if grad_name == "교육대학원":
            add_education_admin_rows(result_rows, grad_row, soup)
            continue

        # 미래융합대학원 / 교육서비스과학대학원은 학과URL보다 교수진 메뉴로 바로 진입
        if is_direct_professor_grad(grad_name):
            # 학과가 없는 대학원은 대학원 메인 페이지에서 행정 이메일 수집
            add_dept_admin_email_rows(result_rows, grad_row, soup)

            professor_links = get_professor_links(soup, grad_url)
            collect_professor_rows(driver, result_rows, grad_row, professor_links)
            continue

        dept_rows = get_dept_list(soup, grad_row)

        if dept_rows:

            for dept_row in dept_rows:
                dept_soup = get_soup(driver, dept_row["학과URL"])

                # 학과URL 메인 페이지 이메일 먼저 수집
                add_dept_admin_email_rows(result_rows, dept_row, dept_soup)

                # 그 다음 교수진 링크 수집
                professor_links = get_professor_links(dept_soup, dept_row["학과URL"])

                if not professor_links:
                    professor_links = get_professor_links(soup, grad_url)

                collect_professor_rows(driver, result_rows, dept_row, professor_links)

        else:
            # 학과 목록이 없는 대학원은 대학원 메인 페이지에서 행정 이메일 수집
            add_dept_admin_email_rows(result_rows, grad_row, soup)

            professor_links = get_professor_links(soup, grad_url)
            collect_professor_rows(driver, result_rows, grad_row, professor_links)

    driver.quit()

    df = pd.DataFrame(result_rows, columns=[
        "구분",
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "학과URL",
        "교수URL"
    ])

    df.to_excel(OUT_FILE, index=False)

    print("[완료] 총", len(result_rows), "건 저장")
    print("[파일]", OUT_FILE)


if __name__ == "__main__":
    main()