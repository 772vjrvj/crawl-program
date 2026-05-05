# -*- coding: utf-8 -*-

import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

LIST_URL = "https://www.hanyang.ac.kr/web/www/s_college_department-info"
OUT = "한양대_행정_교수_직원.xlsx"


# =========================================================
# 실행 대상 설정
# =========================================================
# TARGET_DEPT_NOS 사용법
# - []      : 전체 학과 실행
# - [9]     : 로그의 [진행] 9번 전기공학전공만 실행
# - [9, 12] : 9번, 12번만 실행
#
# 번호 기준
# - main()에서 출력되는 [진행] 번호와 동일
# - collect_department_list() 결과 순서 기준
#
# 추가 작업할 때는 여기 번호만 바꾸면 전체를 다시 돌리지 않아도 됨
TARGET_DEPT_NOS = []

# 학과명으로도 제한하고 싶을 때 사용
# 예: TARGET_DEPT_NAME_KEYWORDS = ["전기공학전공"]
TARGET_DEPT_NAME_KEYWORDS = []

# === 교수 예외 case1 : 건설환경공학과 ===
CIVIL_PROF_URL = "https://civil.hanyang.ac.kr/bbs/board.php?bo_table=sub2_1"

# === 교수 예외 case2 : 도시공학과 ===
URBAN_LAB_URL = "https://changmoo.hanyang.ac.kr/"

# === 직원 예외 case1 : 도시공학과 공지사항 이메일 탐색 ===
URBAN_NOTICE_URL = "http://hyurban.hanyang.ac.kr/?module=Board&action=SiteBoard&sMode=SELECT_FORM&iBrdNo=9"

# === 교수 정상 case6 추가 적용 : 전기공학전공 ===
# [9] 전기공학전공은 requests로 메뉴가 안 잡히는 비동기/동적 페이지라서
# Selenium으로 메인 페이지에 들어간 뒤 교수 / 석학교수 메뉴를 클릭해서 수집한다.
EBE_BASE_URL = "https://ebe.hanyang.ac.kr"
EBE_PROF_MENU_NAMES = ["교수", "석학교수"]
EBE_PROF_FALLBACK_URLS = {
    "교수": "https://ebe.hanyang.ac.kr/bbs/theme/new/html/prof/01.php",
    "석학교수": "https://ebe.hanyang.ac.kr/bbs/theme/new/html/prof/02.php",
}

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def clean(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = text.replace("⌂", "")
    return re.sub(r"\s+", " ", text).strip()


def get_html(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.encoding = res.apparent_encoding
    return res.text


def get_soup(url):
    html = get_html(url)
    return BeautifulSoup(html, "html.parser")


def get_soup_selenium(url):
    # Selenium 전용 case에서만 사용
    import time
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,1200")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(2)
        html = driver.page_source
    finally:
        driver.quit()

    return BeautifulSoup(html, "html.parser")


def get_emails_from_soup(soup):
    emails = []

    for a in soup.select("a[href^='mailto:']"):
        href = a.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip()
        if re.match(EMAIL_RE, email):
            emails.append(email)

    text = soup.get_text(" ", strip=True)
    for email in re.findall(EMAIL_RE, text):
        emails.append(email)

    result = []
    for email in emails:
        email = email.strip()
        if email not in result:
            result.append(email)

    return result


def find_menu_url(soup, base_url, keywords):
    for a in soup.select("ul.menu a[href], ul.gnb a[href]"):
        text = clean(a.get_text(" ", strip=True))
        href = a.get("href", "")

        for keyword in keywords:
            if keyword.lower() in text.lower() or keyword.lower() in href.lower():
                return urljoin(base_url, href)

    for a in soup.select("a[href]"):
        text = clean(a.get_text(" ", strip=True))
        href = a.get("href", "")

        for keyword in keywords:
            if keyword.lower() in text.lower() or keyword.lower() in href.lower():
                return urljoin(base_url, href)

    return ""



def find_exact_menu_url(soup, base_url, keywords):
    for a in soup.select("ul.menu a[href], ul.gnb a[href], #mainMenu a[href], .lnb_wrap a[href], a[href]"):
        text = clean(a.get_text(" ", strip=True)).replace("└", "").strip()
        href = a.get("href", "")

        if not href or href == "#none":
            continue

        for keyword in keywords:
            if text == keyword:
                return urljoin(base_url, href)

    return ""


def find_exact_menu_urls(soup, base_url, keywords):
    urls = []

    for a in soup.select("ul.menu a[href], ul.gnb a[href], #mainMenu a[href], .lnb_wrap a[href], a[href]"):
        text = clean(a.get_text(" ", strip=True)).replace("└", "").strip()
        href = a.get("href", "")

        if not href or href == "#none":
            continue

        for keyword in keywords:
            if text == keyword:
                full_url = urljoin(base_url, href)
                if full_url not in urls:
                    urls.append(full_url)

    return urls


def get_field_text(box, label):
    for p in box.select("p"):
        strong = p.select_one("strong")
        if not strong:
            continue

        strong_text = clean(strong.get_text(" ", strip=True))
        if label not in strong_text:
            continue

        text = clean(p.get_text(" ", strip=True))
        text = text.replace(strong_text, "", 1).strip()
        return text

    return ""


def clean_faculty_name(text):
    text = clean(text)

    if "/" in text:
        parts = [clean(x) for x in text.split("/")]
        for part in parts:
            if "교수" in part:
                return clean(part.replace("교수", ""))

    text = text.replace("Prof.", "")
    text = text.replace("Professor", "")
    text = text.replace("교수", "")
    return clean(text)


def is_civil_dept(item):
    if item["중분류"] == "건설환경공학과":
        return True

    if item["소분류"] == "건설환경공학과":
        return True

    return False


def is_urban_dept(item):
    if item["중분류"] == "도시공학과":
        return True

    if item["소분류"] == "도시공학과":
        return True

    return False


def is_ebe_dept(item):
    # [9] 전기공학전공 전용 판별
    # 기존 requests 메뉴 탐색에서 교수 URL이 빈값으로 나와 Selenium click case로 우회한다.
    if item["중분류"] == "전기공학전공":
        return True

    if item["소분류"] == "전기공학전공":
        return True

    if EBE_BASE_URL in item.get("URL", ""):
        return True

    return False



def should_run_item(idx, item):
    # =========================================================
    # 학과별 단독 실행 필터
    # =========================================================
    # idx는 로그에 찍히는 [진행] 번호와 동일하다.
    # TARGET_DEPT_NOS에 번호를 넣으면 해당 번호만 실행한다.
    # TARGET_DEPT_NAME_KEYWORDS에 학과명을 넣으면 해당 이름이 포함된 학과만 실행한다.
    # =========================================================
    if TARGET_DEPT_NOS and idx not in TARGET_DEPT_NOS:
        return False

    if TARGET_DEPT_NAME_KEYWORDS:
        text = item["대분류"] + " " + item["중분류"] + " " + item["소분류"]

        matched = False
        for keyword in TARGET_DEPT_NAME_KEYWORDS:
            if keyword in text:
                matched = True

        if not matched:
            return False

    return True


def collect_department_list():
    soup = get_soup(LIST_URL)
    rows = []

    for box in soup.select(".container"):
        banner = box.select_one(".hyu-fragment-component-lineBanner-content-item")
        if not banner:
            continue

        a = banner.select_one("a[href]")
        p = banner.select_one("p")
        if not p:
            continue

        college = clean(p.get_text(" ", strip=True))
        college_url = urljoin(LIST_URL, a["href"]) if a else ""

        rows.append({
            "구분": "대학",
            "대분류": college,
            "중분류": college,
            "소분류": college,
            "URL": college_url
        })

        for tr in box.select("table tr"):
            a = tr.select_one("a[href]")
            if not a:
                continue

            names = [clean(td.get_text(" ", strip=True)) for td in tr.select("td")[:-1]]
            names = [x for x in names if x]

            if not names:
                continue

            dept = names[-1]
            dept_url = urljoin(LIST_URL, a["href"])

            rows.append({
                "구분": "대학",
                "대분류": college,
                "중분류": dept,
                "소분류": dept,
                "URL": dept_url
            })

    return rows


def add_main_admin_email(result_rows, item, soup, dept_url):
    emails = get_emails_from_soup(soup)
    cnt = 0

    for email in emails:
        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": "행정",
            "이름": "",
            "이메일": email,
            "URL": dept_url,
            "홈페이지URL": dept_url
        })
        cnt += 1

    return cnt


# =========================================================
# 교수 예외 case1 : 건설환경공학과
# 건설환경공학과 전용 고정 URL 사용
# section#Prof li.flip-box 구조에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [5] 건설환경공학과
# =========================================================
def add_professor_exception_case1_civil(result_rows, item, dept_url):
    print("    [교수 예외 case1 건설환경공학과] 시작")
    print("    [교수 예외 case1 건설환경공학과] URL:", CIVIL_PROF_URL)

    soup = get_soup(CIVIL_PROF_URL)
    boxes = soup.select("section#Prof li.flip-box")

    if not boxes:
        print("    [교수 예외 case1 건설환경공학과] flip-box 없음")
        return 0

    cnt = 0

    for box in boxes:
        name_tag = box.select_one(".tit big b")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        emails = get_emails_from_soup(box)
        email = emails[0] if emails else ""

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": CIVIL_PROF_URL,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [교수 예외 case1 건설환경공학과] 수집:", cnt)
    return cnt


# =========================================================
# 교수 예외 case2 : 도시공학과
# 도시공학과 연구실 사이트 전용 처리
# 교수 1명 + 조교 카드 목록을 같이 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [6] 도시공학과
# =========================================================
def add_professor_exception_case2_urban(result_rows, item, dept_url):
    print("    [교수 예외 case2 도시공학과] 시작")
    print("    [교수 예외 case2 도시공학과] URL:", URBAN_LAB_URL)

    soup = get_soup(URBAN_LAB_URL)

    professor_cnt = add_urban_professor(result_rows, item, soup, dept_url)
    assistant_cnt = add_urban_assistants(result_rows, item, soup, dept_url)

    total_cnt = professor_cnt + assistant_cnt

    print("    [교수 예외 case2 도시공학과] 교수 수집:", professor_cnt)
    print("    [교수 예외 case2 도시공학과] 조교 수집:", assistant_cnt)
    print("    [교수 예외 case2 도시공학과] 전체 수집:", total_cnt)

    return total_cnt


def add_urban_professor(result_rows, item, soup, dept_url):
    blocks = soup.select("[data-testid='richTextElement'], .wixui-rich-text")
    last_name = ""
    cnt = 0

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        name_match = re.search(r"([가-힣]{2,5})\s*교수", text)
        if name_match:
            last_name = clean(name_match.group(1))

        emails = re.findall(EMAIL_RE, text)

        if last_name and emails:
            email = emails[0]

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": item["소분류"],
                "직위": "교수",
                "업무": "교육.연구",
                "이름": last_name,
                "이메일": email,
                "URL": URBAN_LAB_URL,
                "홈페이지URL": dept_url
            })

            cnt += 1
            break

    return cnt


def add_urban_assistants(result_rows, item, soup, dept_url):
    cards = soup.select(".SPY_vo")
    cnt = 0
    seen_emails = []

    for card in cards:
        emails = get_emails_from_soup(card)
        if not emails:
            continue

        email = emails[0]
        if email in seen_emails:
            continue

        name = find_urban_assistant_name(card)

        if not name:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "조교",
            "업무": "연구",
            "이름": name,
            "이메일": email,
            "URL": URBAN_LAB_URL,
            "홈페이지URL": dept_url
        })

        seen_emails.append(email)
        cnt += 1

    return cnt


def find_urban_assistant_name(card):
    for h in card.select("h6"):
        text = clean(h.get_text(" ", strip=True))

        if not text:
            continue

        if "@" in text:
            continue

        if "과정" in text:
            continue

        if "석사" in text:
            continue

        if "박사" in text:
            continue

        if "통합" in text:
            continue

        if re.fullmatch(r"[가-힣]{2,5}", text):
            return text

    text = clean(card.get_text(" ", strip=True))
    match = re.search(r"([가-힣]{2,5})\s+(석박통합|박사과정|석사과정|박사|석사)", text)

    if match:
        return clean(match.group(1))

    return ""


# =========================================================
# 교수 정상 case1 : photo_table figure 구조
# photo_table figure 목록에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [2] 반도체공학과
# =========================================================
def add_professor_normal_case1(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case1 photo-table] 시작")

    if not professor_url:
        print("    [교수 정상 case1 photo-table] URL 없음")
        return 0

    print("    [교수 정상 case1 photo-table] URL:", professor_url)

    soup = get_soup(professor_url)
    figures = soup.select(".photo_table figure")

    if not figures:
        print("    [교수 정상 case1 photo-table] figure 없음")
        return 0

    cnt = 0

    for fig in figures:
        name = ""

        name_a = fig.select_one("h6 > a")
        if name_a:
            name = clean(name_a.get_text(" ", strip=True))

        emails = get_emails_from_soup(fig)
        email = emails[0] if emails else ""

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": professor_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [교수 정상 case1 photo-table] 수집:", cnt)
    return cnt


# =========================================================
# 교수 정상 case2 : faculty Squarespace 구조
# faculty 페이지의 sqs-html-content에서 이름/이메일 연결 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [3] 건축학부
# =========================================================
def add_professor_normal_case2(result_rows, item, faculty_url, dept_url):
    print("    [교수 정상 case2 faculty] 시작")

    if not faculty_url:
        print("    [교수 정상 case2 faculty] URL 없음")
        return 0

    print("    [교수 정상 case2 faculty] URL:", faculty_url)

    soup = get_soup(faculty_url)

    blocks = soup.select(".sqs-html-content")
    last_name = ""
    cnt = 0

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        for a in block.select("a[href]"):
            a_text = clean(a.get_text(" ", strip=True))

            if "@" in a_text:
                continue

            if a_text.lower() == "faculty":
                continue

            if "Prof" in a_text or "교수" in a_text:
                last_name = clean_faculty_name(a_text)

        emails = re.findall(EMAIL_RE, text)

        for email in emails:
            if not last_name:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": item["소분류"],
                "직위": "교수",
                "업무": "교육.연구",
                "이름": last_name,
                "이메일": email,
                "URL": faculty_url,
                "홈페이지URL": dept_url
            })

            cnt += 1

    print("    [교수 정상 case2 faculty] 수집:", cnt)
    return cnt


# =========================================================
# 교수 정상 case3 : hyu-profile 구조
# hyu-fragment-component-profile 카드에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [4] 건축공학부
# - [22] 미래자동차공학과
# - [26] 국어국문학과
# - [27] 중어중문학과
# - [29] 독어독문학과
# - [30] 사학과
# - [31] 철학과
# - [32] 미래인문학융합학부
# - [34] 관광학부
# - [35] 미디어커뮤니케이션학과
# - [36] 사회학과
# - [37] 정치외교학과
# - [39] 수학과
# - [41] 화학과
# - [42] 생명과학과
# - [59] 식품영양학과
# - [60] 실내건축디자인학과
# - [62] 성악과
# - [63] 작곡과
# - [64] 피아노과
# - [65] 관현악과
# - [66] 국악과
# - [74] 글로벌콘텐츠융합학부
# =========================================================
def add_professor_normal_case3(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case3 hyu-profile] 시작")

    if not professor_url:
        print("    [교수 정상 case3 hyu-profile] URL 없음")
        return 0

    print("    [교수 정상 case3 hyu-profile] URL:", professor_url)

    soup = get_soup(professor_url)
    profiles = soup.select(".hyu-fragment-component-profile")

    if not profiles:
        print("    [교수 정상 case3 hyu-profile] profile 없음")
        return 0

    cnt = 0

    for profile in profiles:
        name_tag = profile.select_one(".hyu-profile-info-title-name")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        emails = get_emails_from_soup(profile)
        email = emails[0] if emails else ""

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": professor_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [교수 정상 case3 hyu-profile] 수집:", cnt)
    return cnt


# =========================================================
# 교수 정상 case4 : list01 + 탭 구조
# 교수/명예 및 퇴직교수/연구교수 탭 URL 순회
# ul.list01 > li 구조에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [7] 자원환경공학과
# =========================================================
def add_professor_normal_case4_list01_tabs(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case4 list01-tabs] 시작")

    if not professor_url:
        print("    [교수 정상 case4 list01-tabs] URL 없음")
        return 0

    print("    [교수 정상 case4 list01-tabs] 기본 URL:", professor_url)

    first_soup = get_soup(professor_url)

    tab_urls = []
    tab_keywords = ["교수", "명예 및 퇴직교수", "연구교수"]

    tab_urls.append(professor_url)

    for a in first_soup.select(".depth03_menu a[href], .tab_menu .menulink03 a[href]"):
        text = clean(a.get_text(" ", strip=True))
        href = a.get("href", "")

        if not href or href == "#none":
            continue

        for keyword in tab_keywords:
            if keyword in text:
                full_url = urljoin(professor_url, href)
                if full_url not in tab_urls:
                    tab_urls.append(full_url)

    print("    [교수 정상 case4 list01-tabs] 탭 URL 수:", len(tab_urls))

    cnt = 0
    seen = []

    for tab_idx, tab_url in enumerate(tab_urls, start=1):
        print("      [교수 정상 case4 탭]", tab_idx, "/", len(tab_urls), tab_url)

        soup = get_soup(tab_url)
        items = soup.select(".sub0104_wrap ul.list01 > li, ul.list01 > li")

        if not items:
            print("      [교수 정상 case4 탭] li 없음")
            continue

        for li in items:
            name_tag = li.select_one(".txt__wrap .tit p")
            name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

            emails = get_emails_from_soup(li)
            email = emails[0] if emails else ""

            key = name + "|" + email

            if not name and not email:
                continue

            if key in seen:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": item["소분류"],
                "직위": "교수",
                "업무": "교육.연구",
                "이름": name,
                "이메일": email,
                "URL": tab_url,
                "홈페이지URL": dept_url
            })

            seen.append(key)
            cnt += 1

    print("    [교수 정상 case4 list01-tabs] 수집:", cnt)
    return cnt



# =========================================================
# 교수 정상 case5 : graduateSchool professor.php 탭 + 상세 구조
# tab_box 탭 순회 후 a.box_wrap 상세페이지 진입
# 상세 .info_box에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [8] 융합전자공학부
# =========================================================
def add_professor_normal_case5_graduate_tabs_detail(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case5 graduate-tabs-detail] 시작")

    if not professor_url:
        print("    [교수 정상 case5 graduate-tabs-detail] URL 없음")
        return 0

    print("    [교수 정상 case5 graduate-tabs-detail] 기본 URL:", professor_url)

    first_soup = get_soup(professor_url)

    if not first_soup.select(".graduateSchool_15 .img_list a.box_wrap, .img_list a.box_wrap"):
        print("    [교수 정상 case5 graduate-tabs-detail] img_list 목록 없음")
        return 0

    tab_urls = [professor_url]

    for a in first_soup.select(".graduateSchool_15 .tab_box a[href], .tab_box a[href]"):
        href = a.get("href", "")
        if not href or href == "#none":
            continue

        full_url = urljoin(professor_url, href)
        if full_url not in tab_urls:
            tab_urls.append(full_url)

    print("    [교수 정상 case5 graduate-tabs-detail] 탭 URL 수:", len(tab_urls))

    cnt = 0
    seen = []

    for tab_idx, tab_url in enumerate(tab_urls, start=1):
        print("      [교수 정상 case5 탭]", tab_idx, "/", len(tab_urls), tab_url)

        soup = get_soup(tab_url)
        links = soup.select(".graduateSchool_15 .img_list a.box_wrap[href], .img_list a.box_wrap[href]")

        if not links:
            print("      [교수 정상 case5 탭] 교수 링크 없음")
            continue

        for a in links:
            detail_url = urljoin(tab_url, a.get("href", ""))

            if not detail_url:
                continue

            detail_soup = get_soup(detail_url)

            name_tag = detail_soup.select_one(".info_box .txt_box .name span, .info_box .name span")
            name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

            email_tag = detail_soup.select_one(".info_box .email")
            email = clean(email_tag.get_text(" ", strip=True)) if email_tag else ""

            if not email:
                emails = get_emails_from_soup(detail_soup)
                email = emails[0] if emails else ""

            key = name + "|" + email

            if not name and not email:
                continue

            if key in seen:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": item["소분류"],
                "직위": "교수",
                "업무": "교육.연구",
                "이름": name,
                "이메일": email,
                "URL": detail_url,
                "홈페이지URL": dept_url
            })

            seen.append(key)
            cnt += 1

    print("    [교수 정상 case5 graduate-tabs-detail] 수집:", cnt)
    return cnt


# =========================================================
# 교수 정상 case6 : Selenium + professor_box 구조
# request로 안 되는 페이지용
# 교수/석학교수 페이지의 .professor_box에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [9] 전기공학전공
#
# 처리 방식
# - [9] 전기공학전공은 requests에서 교수 메뉴 URL이 빈값으로 잡혔음
# - Selenium으로 https://ebe.hanyang.ac.kr 접속
# - 좌측/상단 메뉴에서 "교수", "석학교수" 링크를 찾아 클릭
# - 클릭 실패 시 fallback URL로 직접 이동
# - .professor_box 안에서 이름 / 이메일 수집
# =========================================================
def add_professor_normal_case6_selenium_professor_box(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case6 selenium-professor-box] 시작")

    if is_ebe_dept(item):
        return add_professor_normal_case6_ebe_click(result_rows, item, dept_url)

    if not professor_url:
        print("    [교수 정상 case6 selenium-professor-box] URL 없음")
        return 0

    print("    [교수 정상 case6 selenium-professor-box] 기본 URL:", professor_url)

    first_soup = get_soup_selenium(professor_url)

    page_urls = find_exact_menu_urls(first_soup, professor_url, ["교수", "석학교수"])

    if not page_urls:
        page_urls.append(professor_url)

    print("    [교수 정상 case6 selenium-professor-box] 페이지 URL 수:", len(page_urls))

    cnt = 0
    seen = []

    for page_idx, page_url in enumerate(page_urls, start=1):
        print("      [교수 정상 case6 페이지]", page_idx, "/", len(page_urls), page_url)

        soup = get_soup_selenium(page_url)
        boxes = soup.select(".professor_box")

        if not boxes:
            print("      [교수 정상 case6 페이지] professor_box 없음")
            continue

        cnt += append_professor_box_rows(result_rows, item, boxes, page_url, dept_url, "교수", seen)

    print("    [교수 정상 case6 selenium-professor-box] 수집:", cnt)
    return cnt


def add_professor_normal_case6_ebe_click(result_rows, item, dept_url):
    print("    [교수 정상 case6 EBE 전기공학전공] 시작")
    print("    [교수 정상 case6 EBE 전기공학전공] 메인 URL:", dept_url)
    print("    [교수 정상 case6 EBE 전기공학전공] 대상: 교수 + 석학교수")

    import time
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,1200")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    cnt = 0
    seen = []

    try:
        driver.get(dept_url)
        time.sleep(2)

        # === 신규 ===
        # 석학교수는 클릭 방식에서 누락되는 경우가 있어서
        # 1) 메뉴에서 찾은 URL
        # 2) 고정 fallback URL
        # 을 합친 뒤 URL로 직접 이동해서 수집한다.
        menu_targets = find_ebe_professor_menu_targets(driver, dept_url)
        menu_targets = merge_ebe_professor_fallback_targets(menu_targets, dept_url)

        print("    [교수 정상 case6 EBE 전기공학전공] 메뉴 수:", len(menu_targets))

        for page_idx, target in enumerate(menu_targets, start=1):
            menu_name = target["menu_name"]
            page_url = target["url"]

            print("      [교수 정상 case6 EBE 페이지]", page_idx, "/", len(menu_targets), menu_name, page_url)

            # === 신규 ===
            # 클릭 대신 직접 이동을 기본으로 한다.
            # 이유: 교수 페이지는 잘 가져오지만 석학교수 클릭이 누락되는 경우가 있었음.
            driver.get(page_url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            row_cnt = append_ebe_professor_rows_from_soup(
                result_rows,
                item,
                soup,
                driver.current_url,
                dept_url,
                menu_name,
                seen
            )
            cnt += row_cnt

            print("      [교수 정상 case6 EBE 페이지] 수집:", row_cnt)

    finally:
        driver.quit()

    print("    [교수 정상 case6 EBE 전기공학전공] 수집:", cnt)
    return cnt


def merge_ebe_professor_fallback_targets(menu_targets, dept_url):
    result = []
    seen_keys = []

    for target in menu_targets:
        key = target["menu_name"] + "|" + target["url"]
        if key not in seen_keys:
            result.append(target)
            seen_keys.append(key)

    for menu_name in EBE_PROF_MENU_NAMES:
        fallback_url = EBE_PROF_FALLBACK_URLS.get(menu_name, "")
        if not fallback_url:
            continue

        full_url = urljoin(dept_url, fallback_url)
        key = menu_name + "|" + full_url

        if key not in seen_keys:
            result.append({
                "menu_name": menu_name,
                "url": full_url
            })
            seen_keys.append(key)

    return result


def find_ebe_professor_menu_targets(driver, dept_url):
    from selenium.webdriver.common.by import By

    targets = []
    seen_names = []

    links = driver.find_elements(By.CSS_SELECTOR, "#mainMenu a[href], .lnb_wrap a[href], a[href]")

    for menu_name in EBE_PROF_MENU_NAMES:
        found_url = ""

        for a in links:
            text = clean(a.text).replace("└", "").replace("-", "").strip()
            href = a.get_attribute("href")

            if text == menu_name and href:
                found_url = href
                break

        if not found_url:
            found_url = EBE_PROF_FALLBACK_URLS.get(menu_name, "")

        if found_url and menu_name not in seen_names:
            targets.append({
                "menu_name": menu_name,
                "url": urljoin(dept_url, found_url)
            })
            seen_names.append(menu_name)

    return targets


def append_ebe_professor_rows_from_soup(result_rows, item, soup, page_url, dept_url, menu_name, seen):
    # === 신규 ===
    # EBE 전기공학전공 전용 파서
    # 1순위: .professor_box 구조
    # 2순위: mailto 기준 부모 영역에서 이름/이메일 추출
    boxes = soup.select(".professor_box")

    if boxes:
        return append_professor_box_rows(result_rows, item, boxes, page_url, dept_url, menu_name, seen)

    print("      [교수 정상 case6 EBE 페이지] professor_box 없음, mailto fallback 진행")
    return append_ebe_professor_rows_from_mailto(result_rows, item, soup, page_url, dept_url, menu_name, seen)


def append_ebe_professor_rows_from_mailto(result_rows, item, soup, page_url, dept_url, menu_name, seen):
    cnt = 0

    for mail in soup.select("a[href^='mailto:']"):
        href = mail.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip()

        if not re.match(EMAIL_RE, email):
            email = clean(mail.get_text(" ", strip=True))

        if not re.match(EMAIL_RE, email):
            continue

        box = find_ebe_mail_parent_box(mail)
        name = extract_ebe_professor_name_from_box(box)

        key = menu_name + "|" + name + "|" + email

        if key in seen:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": page_url,
            "홈페이지URL": dept_url
        })

        seen.append(key)
        cnt += 1

    return cnt


def find_ebe_mail_parent_box(mail):
    parent = mail

    for _ in range(8):
        if not parent:
            break

        text = clean(parent.get_text(" ", strip=True))

        if "Position" in text and "E-mail" in text:
            return parent

        if parent.name in ["li", "div", "dl"] and "E-mail" in text:
            return parent

        parent = parent.parent

    return mail.parent


def extract_ebe_professor_name_from_box(box):
    if not box:
        return ""

    strong = box.select_one("strong")
    if strong:
        return clean(strong.get_text(" ", strip=True))

    text = clean(box.get_text(" ", strip=True))

    match = re.search(r"([가-힣]{2,5})\s*교수", text)
    if match:
        return clean(match.group(1))

    match = re.search(r"([A-Za-z][A-Za-z .\-]+)\s*교수", text)
    if match:
        return clean(match.group(1))

    return ""


def click_ebe_professor_menu(driver, dept_url, menu_name, page_url):
    # 현재는 EBE case에서 직접 URL 이동 방식을 사용한다.
    # 기존 클릭 방식이 필요할 때를 위해 함수는 남겨둔다.
    import time
    from selenium.webdriver.common.by import By

    try:
        driver.get(dept_url)
        time.sleep(1)

        links = driver.find_elements(By.CSS_SELECTOR, "#mainMenu a[href], .lnb_wrap a[href], a[href]")

        for a in links:
            text = clean(a.text).replace("└", "").replace("-", "").strip()
            href = a.get_attribute("href")

            if text == menu_name and href == page_url:
                driver.execute_script("arguments[0].click();", a)
                time.sleep(2)
                return True

        for a in links:
            text = clean(a.text).replace("└", "").replace("-", "").strip()

            if text == menu_name:
                driver.execute_script("arguments[0].click();", a)
                time.sleep(2)
                return True

    except Exception as e:
        print("      [교수 정상 case6 EBE 페이지] 클릭 오류:", e)

    return False


def append_professor_box_rows(result_rows, item, boxes, page_url, dept_url, menu_name, seen):
    cnt = 0

    for box in boxes:
        name_tag = box.select_one(".professor_info dt strong, dt strong, strong")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        emails = get_emails_from_soup(box)
        email = emails[0] if emails else ""

        if not name:
            name = extract_ebe_professor_name_from_box(box)

        key = menu_name + "|" + name + "|" + email

        if not name and not email:
            continue

        if not email:
            continue

        if key in seen:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": page_url,
            "홈페이지URL": dept_url
        })

        seen.append(key)
        cnt += 1

    return cnt


# =========================================================
# 교수 정상 case7 : BME member-list 구조
# member-list에서 이름/이메일 수집
# 이메일이 없는 경우도 이름 확인용으로 저장
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [10] 바이오메디컬공학전공
# =========================================================
def add_professor_normal_case7_bme_member_list(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case7 bme-member-list] 시작")

    if not professor_url:
        print("    [교수 정상 case7 bme-member-list] URL 없음")
        return 0

    print("    [교수 정상 case7 bme-member-list] URL:", professor_url)

    soup = get_soup(professor_url)
    members = soup.select(".contents-wrap .member-list, .member-list")

    if not members:
        print("    [교수 정상 case7 bme-member-list] member-list 없음")
        return 0

    cnt = 0
    seen = []

    for member in members:
        name_tag = member.select_one(".member-info-list strong[id^='professor'], .member-info-list strong, .member-info strong")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        emails = get_emails_from_soup(member)
        email = emails[0] if emails else ""

        key = name + "|" + email

        if not name and not email:
            continue

        if key in seen:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육.연구",
            "이름": name,
            "이메일": email,
            "URL": professor_url,
            "홈페이지URL": dept_url
        })

        seen.append(key)
        cnt += 1

    print("    [교수 정상 case7 bme-member-list] 수집:", cnt)
    return cnt



# =========================================================
# 교수 정상 case8 : prof_f / graylinebox 구조
# 교수소개/명예교수 페이지 순회
# .prof_f 박스에서 이름/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [11] 신소재공학부
# =========================================================
def add_professor_normal_case8_prof_f_graylinebox(result_rows, item, professor_url, dept_url):
    print("    [교수 정상 case8 prof-f-graylinebox] 시작")

    if not professor_url:
        print("    [교수 정상 case8 prof-f-graylinebox] URL 없음")
        return 0

    print("    [교수 정상 case8 prof-f-graylinebox] 기본 URL:", professor_url)

    first_soup = get_soup(professor_url)

    page_urls = []
    page_urls.append(professor_url)

    extra_urls = find_exact_menu_urls(first_soup, professor_url, ["교수소개", "명예교수"])
    for url in extra_urls:
        if url not in page_urls:
            page_urls.append(url)

    print("    [교수 정상 case8 prof-f-graylinebox] 페이지 URL 수:", len(page_urls))

    cnt = 0
    seen = []

    for page_idx, page_url in enumerate(page_urls, start=1):
        print("      [교수 정상 case8 페이지]", page_idx, "/", len(page_urls), page_url)

        soup = get_soup(page_url)
        boxes = soup.select(".prof .prof_f, .prof_f")

        if not boxes:
            print("      [교수 정상 case8 페이지] prof_f 없음")
            continue

        for box in boxes:
            name_tag = box.select_one(".prof_l h5")
            name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

            # h5 안의 영문명/span/상세보기 제거
            span_tag = name_tag.select_one("span") if name_tag else None
            if span_tag:
                name = name.replace(clean(span_tag.get_text(" ", strip=True)), "")

            name = name.replace("상세보기 Detailed", "")
            name = name.replace("Detailed", "")
            name = clean(name)

            emails = get_emails_from_soup(box)
            email = emails[0] if emails else ""

            key = name + "|" + email

            if not name and not email:
                continue

            if key in seen:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": item["소분류"],
                "직위": "교수",
                "업무": "교육.연구",
                "이름": name,
                "이메일": email,
                "URL": page_url,
                "홈페이지URL": dept_url
            })

            seen.append(key)
            cnt += 1

    print("    [교수 정상 case8 prof-f-graylinebox] 수집:", cnt)
    return cnt


# =========================================================
# 교수 수집 전체 실패 학과 - 제공 로그 기준
# - [9] 전기공학전공
# - [12] 화학공학과
# - [13] 생명공학과
# - [14] 유기나노공학과
# - [15] 에너지공학과
# - [16] 기계공학부
# - [17] 원자력공학과
# - [18] 산업공학과
# - [19] 데이터사이언스학부
# - [20] 컴퓨터소프트웨어학부
# - [21] 정보시스템학과
# - [28] 영어영문학과
# - [40] 물리학과
# - [44] 정책학과
# - [45] 행정학과
# - [48] 경영학부
# - [49] 파이낸스경영학과
# - [51] 교육학과
# - [52] 교육공학과
# - [53] 국어교육과
# - [54] 영어교육과
# - [55] 수학교육과
# - [56] 응용미술교육과
# - [58] 의류학과
# - [68] 스포츠산업과학부 스포츠사이언스전공
# - [69] 스포츠산업과학부 스포츠매니지먼트전공
# - [70] 연극영화학과
# - [71] 무용학과
# - [73] 국제학부
# =========================================================
def collect_professors_by_cases(result_rows, item, soup, dept_url):
    print("  [교수 수집] 시작")

    # 예외 case1
    if is_civil_dept(item):
        print("  [교수 수집] 교수 예외 case1 건설환경공학과 적용")
        cnt = add_professor_exception_case1_civil(result_rows, item, dept_url)

        if cnt > 0:
            print("  [교수 수집] 교수 예외 case1 성공, 정상 case 건너뜀")
            return cnt

        print("  [교수 수집] 교수 예외 case1 실패, 정상 case 진행")

    # 예외 case2
    if is_urban_dept(item):
        print("  [교수 수집] 교수 예외 case2 도시공학과 적용")
        cnt = add_professor_exception_case2_urban(result_rows, item, dept_url)

        if cnt > 0:
            print("  [교수 수집] 교수 예외 case2 성공, 정상 case 건너뜀")
            return cnt

        print("  [교수 수집] 교수 예외 case2 실패, 정상 case 진행")

    professor_url = find_exact_menu_url(soup, dept_url, ["교수"])
    if not professor_url:
        professor_url = find_exact_menu_url(soup, dept_url, ["교수진"])
    if not professor_url:
        professor_url = find_exact_menu_url(soup, dept_url, ["교수소개"])
    if not professor_url:
        professor_url = find_menu_url(soup, dept_url, ["교수진 소개", "교수 소개", "교수소개", "교수진", "교수"])

    if is_ebe_dept(item) and not professor_url:
        print("    [교수 수집] [9] 전기공학전공 requests 메뉴 탐색 실패")
        print("    [교수 수집] [9] 전기공학전공 Selenium click case6에서 처리")

    faculty_url = find_menu_url(soup, dept_url, ["faculty"])

    print("    [교수 수집] 정상 case1 후보:", professor_url)
    print("    [교수 수집] 정상 case2 후보:", faculty_url)
    print("    [교수 수집] 정상 case3 후보:", professor_url)
    print("    [교수 수집] 정상 case4 후보:", professor_url)
    print("    [교수 수집] 정상 case5 후보:", professor_url)
    print("    [교수 수집] 정상 case6 후보:", professor_url)
    print("    [교수 수집] 정상 case7 후보:", professor_url)
    print("    [교수 수집] 정상 case8 후보:", professor_url)

    cnt = add_professor_normal_case1(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case1 성공, 정상 case2~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case1 실패, 정상 case2 진행")

    cnt = add_professor_normal_case2(result_rows, item, faculty_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case2 성공, 정상 case3~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case2 실패, 정상 case3 진행")

    cnt = add_professor_normal_case3(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case3 성공, 정상 case4~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case3 실패, 정상 case4 진행")

    cnt = add_professor_normal_case4_list01_tabs(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case4 성공, 정상 case5~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case4 실패, 정상 case5 진행")

    cnt = add_professor_normal_case5_graduate_tabs_detail(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case5 성공, 정상 case6~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case5 실패, 정상 case6 진행")

    cnt = add_professor_normal_case6_selenium_professor_box(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case6 성공, 정상 case7~8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case6 실패, 정상 case7 진행")

    cnt = add_professor_normal_case7_bme_member_list(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case7 성공, 정상 case8 건너뜀")
        return cnt

    print("  [교수 수집] 정상 case7 실패, 정상 case8 진행")

    cnt = add_professor_normal_case8_prof_f_graylinebox(result_rows, item, professor_url, dept_url)

    if cnt > 0:
        print("  [교수 수집] 정상 case8 성공")
        return cnt

    print("  [교수 수집] 전체 실패")
    return 0


# =========================================================
# 직원 정상 case1 : office dl 구조
# office .photo_table dl 구조에서 이름/직위/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [2] 반도체공학과
# =========================================================
def add_staff_normal_case1(result_rows, item, office_url, dept_url):
    print("    [직원 정상 case1 office] 시작")

    if not office_url:
        print("    [직원 정상 case1 office] URL 없음")
        return 0

    print("    [직원 정상 case1 office] URL:", office_url)

    soup = get_soup(office_url)
    dls = soup.select(".office .photo_table dl")
    cnt = 0

    if not dls:
        print("    [직원 정상 case1 office] dl 없음")
        return 0

    for dl in dls:
        name_tag = dl.select_one("h6")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        emails = get_emails_from_soup(dl)
        email = emails[0] if emails else ""

        position = get_field_text(dl, "직위")

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": position,
            "업무": "행정",
            "이름": name,
            "이메일": email,
            "URL": office_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [직원 정상 case1 office] 수집:", cnt)
    return cnt


# =========================================================
# 직원 정상 case2 : 직원 table 구조
# 직위/이름/이메일 헤더가 있는 table에서 직원 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [4] 건축공학부
# =========================================================
def add_staff_normal_case2(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case2 table] 시작")

    if not staff_url:
        print("    [직원 정상 case2 table] URL 없음")
        return 0

    print("    [직원 정상 case2 table] URL:", staff_url)

    soup = get_soup(staff_url)
    cnt = 0

    for table in soup.select("table"):
        headers = [clean(th.get_text(" ", strip=True)) for th in table.select("thead th")]

        if not headers:
            first_tr = table.select_one("tr")
            if first_tr:
                headers = [clean(x.get_text(" ", strip=True)) for x in first_tr.select("th,td")]

        has_position = "직위" in headers
        has_name = "이름" in headers
        has_email = "이메일" in headers

        if not has_position or not has_name or not has_email:
            continue

        body_rows = table.select("tbody tr")
        if not body_rows:
            body_rows = table.select("tr")[1:]

        for tr in body_rows:
            tds = tr.select("td")
            if len(tds) < 2:
                continue

            data = {}
            for i, header in enumerate(headers):
                if i < len(tds):
                    data[header] = clean(tds[i].get_text(" ", strip=True))

            position = data.get("직위", "")
            name = data.get("이름", "")
            task = data.get("담당업무", "")
            if not task:
                task = data.get("업무", "")

            emails = get_emails_from_soup(tr)
            email = emails[0] if emails else ""

            if not name and not email:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": "행정",
                "직위": position,
                "업무": task,
                "이름": name,
                "이메일": email,
                "URL": staff_url,
                "홈페이지URL": dept_url
            })

            cnt += 1

    print("    [직원 정상 case2 table] 수집:", cnt)
    return cnt


# =========================================================
# 직원 정상 case3 : sub0105_wrap box 구조
# sub0105_wrap .box에서 이름/담당업무/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [7] 자원환경공학과
# =========================================================
def add_staff_normal_case3_sub0105_box(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case3 sub0105-box] 시작")

    if not staff_url:
        print("    [직원 정상 case3 sub0105-box] URL 없음")
        return 0

    print("    [직원 정상 case3 sub0105-box] URL:", staff_url)

    soup = get_soup(staff_url)
    boxes = soup.select(".sub0105_wrap .box")

    if not boxes:
        print("    [직원 정상 case3 sub0105-box] box 없음")
        return 0

    cnt = 0

    for box in boxes:
        name_tag = box.select_one(".name")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        email = ""
        task = ""

        for li in box.select("li"):
            title_tag = li.select_one(".p_tit")
            value_tag = li.select_one(".p_con")

            title = clean(title_tag.get_text(" ", strip=True)) if title_tag else ""
            value = clean(value_tag.get_text(" ", strip=True)) if value_tag else ""

            if "E-mail" in title or "이메일" in title:
                email = value

            if "담당업무" in title or "업무" in title:
                task = value

        if not email:
            emails = get_emails_from_soup(box)
            email = emails[0] if emails else ""

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": task,
            "이름": name,
            "이메일": email,
            "URL": staff_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [직원 정상 case3 sub0105-box] 수집:", cnt)
    return cnt



# =========================================================
# 직원 정상 case4 보조 함수 : undergraduate_07 행정직원 table 구조
# 현재 collect_staffs_by_cases에서 직접 호출하지 않는 예비 함수
# 성명/업무/E-mail 수집, rowspan td 개수 차이 보정
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [8] 융합전자공학부
# =========================================================
def add_staff_normal_case4_undergraduate_07_table(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case4 undergraduate_07-table] 시작")

    if not staff_url:
        print("    [직원 정상 case4 undergraduate_07-table] URL 없음")
        return 0

    print("    [직원 정상 case4 undergraduate_07-table] URL:", staff_url)

    soup = get_soup(staff_url)
    table = soup.select_one(".undergraduate_07 table")

    if not table:
        print("    [직원 정상 case4 undergraduate_07-table] table 없음")
        return 0

    cnt = 0

    for tr in table.select("tbody tr"):
        tds = tr.select("td")

        if len(tds) >= 5:
            name_td = tds[1]
            task_td = tds[2]
            email_td = tds[4]
        elif len(tds) >= 4:
            name_td = tds[0]
            task_td = tds[1]
            email_td = tds[3]
        else:
            continue

        name = clean(name_td.get_text(" ", strip=True))
        task = clean(task_td.get_text(" ", strip=True))

        emails = get_emails_from_soup(email_td)
        email = emails[0] if emails else clean(email_td.get_text(" ", strip=True))

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": task,
            "이름": name,
            "이메일": email,
            "URL": staff_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [직원 정상 case4 undergraduate_07-table] 수집:", cnt)
    return cnt


# =========================================================
# 직원 정상 case4 : undergraduate07 table 구조
# undergraduate_07 table에서 성명/업무/E-mail 수집
# rowspan 때문에 td 개수 차이를 보정
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [8] 융합전자공학부
# =========================================================
def add_staff_normal_case4_undergraduate07_table(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case4 undergraduate07-table] 시작")

    if not staff_url:
        print("    [직원 정상 case4 undergraduate07-table] URL 없음")
        return 0

    print("    [직원 정상 case4 undergraduate07-table] URL:", staff_url)

    soup = get_soup(staff_url)
    tables = soup.select(".undergraduate_07 table")

    if not tables:
        print("    [직원 정상 case4 undergraduate07-table] table 없음")
        return 0

    cnt = 0

    for table in tables:
        headers = [clean(th.get_text(" ", strip=True)) for th in table.select("thead th")]

        if not headers:
            continue

        body_rows = table.select("tbody tr")

        for tr in body_rows:
            tds = tr.select("td")
            if len(tds) < 3:
                continue

            # rowspan 때문에 첫 행과 다음 행의 td 개수가 다를 수 있음
            if len(tds) >= 5:
                name_td = tds[1]
                task_td = tds[2]
                email_td = tds[4]
            else:
                name_td = tds[0]
                task_td = tds[1]
                email_td = tds[3] if len(tds) > 3 else None

            name = clean(name_td.get_text(" ", strip=True)) if name_td else ""
            task = clean(task_td.get_text(" ", strip=True)) if task_td else ""

            email = ""
            if email_td:
                emails = get_emails_from_soup(email_td)
                email = emails[0] if emails else clean(email_td.get_text(" ", strip=True))

            if not name and not email:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": "행정",
                "직위": "",
                "업무": task,
                "이름": name,
                "이메일": email,
                "URL": staff_url,
                "홈페이지URL": dept_url
            })

            cnt += 1

    print("    [직원 정상 case4 undergraduate07-table] 수집:", cnt)
    return cnt



# =========================================================
# 직원 정상 case5 : Selenium + professor_box 직원 구조
# request로 안 되는 직원 페이지용
# .professor_box에서 이름/업무/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - 현재 제공 로그 기준 성공 적용 학과 없음
# =========================================================
def add_staff_normal_case5_selenium_professor_box(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case5 selenium-professor-box] 시작")

    if not staff_url:
        print("    [직원 정상 case5 selenium-professor-box] URL 없음")
        return 0

    print("    [직원 정상 case5 selenium-professor-box] URL:", staff_url)

    soup = get_soup_selenium(staff_url)
    boxes = soup.select(".professor_box")

    if not boxes:
        print("    [직원 정상 case5 selenium-professor-box] professor_box 없음")
        return 0

    cnt = 0
    seen = []

    for box in boxes:
        name_tag = box.select_one(".professor_info dt strong")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        task = ""
        for dd in box.select(".professor_info dd"):
            label_tag = dd.select_one("span")
            label = clean(label_tag.get_text(" ", strip=True)) if label_tag else ""

            if "업무" in label:
                value = clean(dd.get_text(" ", strip=True))
                task = value.replace(label, "", 1).strip()

        emails = get_emails_from_soup(box)
        email = emails[0] if emails else ""

        key = name + "|" + email

        if not name and not email:
            continue

        if not email:
            continue

        if key in seen:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": task,
            "이름": name,
            "이메일": email,
            "URL": staff_url,
            "홈페이지URL": dept_url
        })

        seen.append(key)
        cnt += 1

    print("    [직원 정상 case5 selenium-professor-box] 수집:", cnt)
    return cnt



# =========================================================
# 직원 정상 case6 : BME tbl-edu 행정직 table 구조
# table.tbl-edu에서 성명/업무/E-Mail 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [10] 바이오메디컬공학전공
# =========================================================
def add_staff_normal_case6_bme_tbl_edu(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case6 bme-tbl-edu] 시작")

    if not staff_url:
        print("    [직원 정상 case6 bme-tbl-edu] URL 없음")
        return 0

    print("    [직원 정상 case6 bme-tbl-edu] URL:", staff_url)

    soup = get_soup(staff_url)
    tables = soup.select("table.tbl-edu")

    if not tables:
        print("    [직원 정상 case6 bme-tbl-edu] tbl-edu 없음")
        return 0

    cnt = 0

    for table in tables:
        rows = table.select("tr")

        for tr in rows:
            cells = tr.select("td")
            if len(cells) < 3:
                continue

            # rowspan 때문에 첫 행은 5칸, 이후 행은 4칸일 수 있음
            if len(cells) >= 5:
                name_td = cells[1]
                task_td = cells[2]
                email_td = cells[4]
            else:
                name_td = cells[0]
                task_td = cells[1]
                email_td = cells[3] if len(cells) > 3 else None

            name = clean(name_td.get_text(" ", strip=True)) if name_td else ""
            task = clean(task_td.get_text(" ", strip=True)) if task_td else ""

            email = ""
            if email_td:
                emails = get_emails_from_soup(email_td)
                email = emails[0] if emails else clean(email_td.get_text(" ", strip=True))

            if not name and not email:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": "행정",
                "직위": "",
                "업무": task,
                "이름": name,
                "이메일": email,
                "URL": staff_url,
                "홈페이지URL": dept_url
            })

            cnt += 1

    print("    [직원 정상 case6 bme-tbl-edu] 수집:", cnt)
    return cnt



# =========================================================
# 직원 정상 case7 : member_l / graylinebox 구조
# member_l + graylinebox 구조에서 이름/담당업무/이메일 수집
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [11] 신소재공학부
# =========================================================
def add_staff_normal_case7_member_l_graylinebox(result_rows, item, staff_url, dept_url):
    print("    [직원 정상 case7 member-l-graylinebox] 시작")

    if not staff_url:
        print("    [직원 정상 case7 member-l-graylinebox] URL 없음")
        return 0

    print("    [직원 정상 case7 member-l-graylinebox] URL:", staff_url)

    soup = get_soup(staff_url)
    boxes = soup.select(".member .member_l, .member_l")

    if not boxes:
        print("    [직원 정상 case7 member-l-graylinebox] member_l 없음")
        return 0

    cnt = 0

    for box in boxes:
        name_tag = box.select_one("h5")
        name = clean(name_tag.get_text(" ", strip=True)) if name_tag else ""

        # 괄호 안 업무표기는 이름에서 제거
        name = re.sub(r"\(.*?\)", "", name)
        name = clean(name)

        task = ""
        email = ""

        for dl in box.select(".graylinebox dl, dl"):
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")

            label = clean(dt.get_text(" ", strip=True)) if dt else ""
            value = clean(dd.get_text(" ", strip=True)) if dd else ""

            if "담당업무" in label or "업무" in label:
                task = value

            if "E-Mail" in label or "E-mail" in label or "이메일" in label:
                emails = get_emails_from_soup(dl)
                email = emails[0] if emails else value

        if not email:
            emails = get_emails_from_soup(box)
            email = emails[0] if emails else ""

        if not name and not email:
            continue

        result_rows.append({
            "구분": item["구분"],
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": "행정",
            "직위": "",
            "업무": task,
            "이름": name,
            "이메일": email,
            "URL": staff_url,
            "홈페이지URL": dept_url
        })

        cnt += 1

    print("    [직원 정상 case7 member-l-graylinebox] 수집:", cnt)
    return cnt



# =========================================================
# 직원 예외 case1 : 도시공학과 공지사항 이메일 탐색
#
# 적용 학과 번호 / 학과명 - 제공 로그 기준
# - [6] 도시공학과
#
# 로그 참고
# - 기존 코드에서는 add_staff_exception_case1_urban_notice 함수가 없어 오류 발생
# - 이 함수는 오류 방지용 최소 구현
# - 공지사항 URL과 상세 링크 일부에서 이메일을 찾아 행정 데이터로 저장
# =========================================================
def add_staff_exception_case1_urban_notice(result_rows, item, dept_url):
    print("    [직원 예외 case1 도시공학과 공지사항] 시작")
    print("    [직원 예외 case1 도시공학과 공지사항] URL:", URBAN_NOTICE_URL)

    soup = get_soup(URBAN_NOTICE_URL)
    urls = [URBAN_NOTICE_URL]

    for a in soup.select("a[href]"):
        href = a.get("href", "")

        if not href:
            continue

        if "Board" not in href and "iBrdNo" not in href and "SELECT" not in href:
            continue

        full_url = urljoin(URBAN_NOTICE_URL, href)
        if full_url not in urls:
            urls.append(full_url)

        if len(urls) >= 15:
            break

    cnt = 0
    seen_emails = []

    for url in urls:
        notice_soup = get_soup(url)
        emails = get_emails_from_soup(notice_soup)

        for email in emails:
            if email in seen_emails:
                continue

            result_rows.append({
                "구분": item["구분"],
                "대분류": item["대분류"],
                "중분류": item["중분류"],
                "소분류": "행정",
                "직위": "",
                "업무": "행정",
                "이름": "",
                "이메일": email,
                "URL": url,
                "홈페이지URL": dept_url
            })

            seen_emails.append(email)
            cnt += 1

    print("    [직원 예외 case1 도시공학과 공지사항] 수집:", cnt)
    return cnt


# =========================================================
# 직원 수집 전체 실패 학과 - 제공 로그 기준
# - [3] 건축학부
# - [5] 건설환경공학과
# - [6] 도시공학과
# - [9] 전기공학전공
# - [12] 화학공학과
# - [13] 생명공학과
# - [14] 유기나노공학과
# - [15] 에너지공학과
# - [16] 기계공학부
# - [17] 원자력공학과
# - [18] 산업공학과
# - [19] 데이터사이언스학부
# - [20] 컴퓨터소프트웨어학부
# - [21] 정보시스템학과
# - [22] 미래자동차공학과
# - [26] 국어국문학과
# - [27] 중어중문학과
# - [28] 영어영문학과
# - [29] 독어독문학과
# - [30] 사학과
# - [31] 철학과
# - [32] 미래인문학융합학부
# - [34] 관광학부
# - [35] 미디어커뮤니케이션학과
# - [36] 사회학과
# - [37] 정치외교학과
# - [39] 수학과
# - [40] 물리학과
# - [41] 화학과
# - [42] 생명과학과
# - [44] 정책학과
# - [45] 행정학과
# - [48] 경영학부
# - [49] 파이낸스경영학과
# - [51] 교육학과
# - [52] 교육공학과
# - [53] 국어교육과
# - [54] 영어교육과
# - [55] 수학교육과
# - [56] 응용미술교육과
# - [58] 의류학과
# - [59] 식품영양학과
# - [60] 실내건축디자인학과
# - [62] 성악과
# - [63] 작곡과
# - [64] 피아노과
# - [65] 관현악과
# - [66] 국악과
# - [68] 스포츠산업과학부 스포츠사이언스전공
# - [69] 스포츠산업과학부 스포츠매니지먼트전공
# - [70] 연극영화학과
# - [71] 무용학과
# - [73] 국제학부
# - [74] 글로벌콘텐츠융합학부
# =========================================================
def collect_staffs_by_cases(result_rows, item, soup, dept_url):
    print("  [직원 수집] 시작")

    # 직원 예외 case1
    if is_urban_dept(item):
        print("  [직원 수집] 직원 예외 case1 도시공학과 공지사항 적용")
        cnt = add_staff_exception_case1_urban_notice(result_rows, item, dept_url)

        if cnt > 0:
            print("  [직원 수집] 직원 예외 case1 성공, 정상 case 건너뜀")
            return cnt

        print("  [직원 수집] 직원 예외 case1 실패, 정상 case 진행")

    office_url = find_exact_menu_url(soup, dept_url, ["직원", "교직원", "행정직원", "행정직", "직원 소개", "직원소개"])
    if not office_url:
        office_url = find_menu_url(soup, dept_url, ["직원 소개", "직원소개", "교직원", "행정직원", "행정직", "직원"])

    print("    [직원 수집] 정상 case1 후보:", office_url)
    print("    [직원 수집] 정상 case2 후보:", office_url)
    print("    [직원 수집] 정상 case3 후보:", office_url)
    print("    [직원 수집] 정상 case4 후보:", office_url)
    print("    [직원 수집] 정상 case5 후보:", office_url)
    print("    [직원 수집] 정상 case6 후보:", office_url)
    print("    [직원 수집] 정상 case7 후보:", office_url)

    cnt = add_staff_normal_case1(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case1 성공, 정상 case2~7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case1 실패, 정상 case2 진행")

    cnt = add_staff_normal_case2(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case2 성공, 정상 case3~7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case2 실패, 정상 case3 진행")

    cnt = add_staff_normal_case3_sub0105_box(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case3 성공, 정상 case4~7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case3 실패, 정상 case4 진행")

    cnt = add_staff_normal_case4_undergraduate07_table(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case4 성공, 정상 case5~7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case4 실패, 정상 case5 진행")

    cnt = add_staff_normal_case5_selenium_professor_box(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case5 성공, 정상 case6~7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case5 실패, 정상 case6 진행")

    cnt = add_staff_normal_case6_bme_tbl_edu(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case6 성공, 정상 case7 건너뜀")
        return cnt

    print("  [직원 수집] 정상 case6 실패, 정상 case7 진행")

    cnt = add_staff_normal_case7_member_l_graylinebox(result_rows, item, office_url, dept_url)

    if cnt > 0:
        print("  [직원 수집] 정상 case7 성공")
        return cnt

    print("  [직원 수집] 전체 실패")
    return 0


def main():
    print("[1] 학과 목록 수집 시작")
    dept_rows = collect_department_list()
    print("[1] 학과 목록 수:", len(dept_rows))
    print("[설정] TARGET_DEPT_NOS:", TARGET_DEPT_NOS)
    print("[설정] TARGET_DEPT_NAME_KEYWORDS:", TARGET_DEPT_NAME_KEYWORDS)

    result_rows = []

    for idx, item in enumerate(dept_rows, start=1):
        big = item["대분류"]
        mid = item["중분류"]
        sub = item["소분류"]
        dept_url = item["URL"]

        if big == mid and mid == sub:
            print("[SKIP]", idx, "/", len(dept_rows), big)
            continue

        if not should_run_item(idx, item):
            print("[SKIP-TARGET]", idx, "/", len(dept_rows), big, ">", mid, ">", sub)
            continue

        print("")
        print("=" * 80)
        print("[진행]", idx, "/", len(dept_rows))
        print("[분류]", big, ">", mid, ">", sub)
        print("[URL]", dept_url)

        try:
            soup = get_soup(dept_url)

            print("  [메인 행정 이메일] 시작")
            admin_cnt = add_main_admin_email(result_rows, item, soup, dept_url)
            print("  [메인 행정 이메일] 수집:", admin_cnt)

            professor_cnt = collect_professors_by_cases(result_rows, item, soup, dept_url)
            staff_cnt = collect_staffs_by_cases(result_rows, item, soup, dept_url)

            print("[완료]", mid)
            print("  행정 이메일:", admin_cnt)
            print("  교수/조교:", professor_cnt)
            print("  직원:", staff_cnt)

        except Exception as e:
            print("[오류]", dept_url, e)

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
        "홈페이지URL"
    ])

    df.to_excel(OUT, index=False)

    print("")
    print("=" * 80)
    print("저장완료:", OUT)
    print("수집건수:", len(df))


if __name__ == "__main__":
    main()
