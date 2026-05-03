# -*- coding: utf-8 -*-

import re
import time
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


START_URL = "https://www.dongguk.edu/page/853#none"
OUT_FILE = "동국대_교수목록.xlsx"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
NOTICE_MAX_PAGE = 20

PROF_TEXTS = [
    "교수진",
    "현직교수",
    "현직 교수",
    "교수소개",
    "교수 소개",
    "교수님 소개",
    "전임교원"
]

# === 신규 === 공지/게시판 메뉴명 확장
NOTICE_TEXTS = [
    "학과사무실공지",
    "학사공지",
    "학부공지",
    "학사정보",
    "학과소식",
    "알림판",
    "공지사항",
    "게시판"
]

NAME_ALIASES = {
    "불교학과": ["불교학과", "불교학부"],
    "영어영문학부": ["영어영문학부", "영어통번역학전공", "영어문학전공"]
}

# === 신규 === 학과별 강제 URL 예외
SPECIAL_DEPT_URLS = {
    "의료인공지능공학과": "https://medai.dongguk.edu/main",
    "산업시스템공학과": "https://ise.dongguk.edu/main",
    "사회복지상담학과": "https://dswc.dongguk.edu/main",
    "글로벌무역학과": "https://gt.dongguk.edu"
}

SPECIAL_PROFESSOR_URLS = {
    "광고홍보학과": "http://dguadpr.kr/sh_page/page26.php",
    "의료인공지능공학과": "https://medai.dongguk.edu/professor/list?professor_type=PROF_006 | https://medai.dongguk.edu/professor/list?professor_type=PROF_015 | https://medai.dongguk.edu/professor/list?professor_type=PROF_032",
    "산업시스템공학과": "https://ise.dongguk.edu/professor/list?professor_haggwa_type=PROFH_039&professor_type=PROF_006 | https://ise.dongguk.edu/professor/list?professor_haggwa_type=PROFH_039&professor_type=PROF_010",
    "영화영상학과": "https://movie.dongguk.edu/movie23_1_1_3",
    "영화영상제작학과": "https://movie.dongguk.edu/movie23_1_1_3",
    "영상영화학과": "https://movie.dongguk.edu/movie23_1_1_3",
    "사회복지상담학과": "https://dswc.dongguk.edu/professor/list?professor_haggwa_type=PROFH_059&professor_type=PROF_007 | https://dswc.dongguk.edu/professor/list?professor_haggwa_type=PROFH_059&professor_type=PROF_034",
    "글로벌무역학과": "https://gt.dongguk.edu/ibuilder.do?menu_idx=49"
}

SPECIAL_NOTICE_URLS = {
    "광고홍보학과": "http://dguadpr.kr/bbs/board.php?bo_table=table31",
    "글로벌무역학과": "https://gt.dongguk.edu/bbs/data/list.do?menu_idx=58"
}

# === 신규 === 메인 목록에서 누락될 때 강제로 한 번 더 처리할 학과
EXTRA_DEPTS = [
    {
        "대분류": "미래융합대학",
        "중분류": "글로벌무역학과",
        "URL": "https://gt.dongguk.edu"
    }
]


def clean_text(text):
    return " ".join(str(text).split()).replace("홈페이지 바로가기", "").strip()


def norm_text(text):
    return clean_text(text).replace(" ", "")


def clean_name(text):
    text = clean_text(text)
    text = text.replace("교수님", "")
    text = text.replace("강의초빙교수", "")
    text = text.replace("초빙교수", "")
    text = text.replace("명예교수", "")
    text = text.replace("석좌교수", "")
    text = text.replace("겸임교수", "")
    text = text.replace("교수", "")
    return clean_text(text)


def clean_prof_name_text(text):
    text = clean_name(text)
    text = text.replace(" ", "")
    return text


def get_special_value(mapping, dept_name):
    dept_key = norm_text(dept_name)

    for key in mapping:
        if norm_text(key) == dept_key:
            return mapping[key]

    for key in mapping:
        key_text = norm_text(key)
        if key_text and (key_text in dept_key or dept_key in key_text):
            return mapping[key]

    return ""


def get_dept_url(dept_name, dept_url):
    special_url = get_special_value(SPECIAL_DEPT_URLS, dept_name)

    if special_url:
        return special_url

    return urljoin(START_URL, dept_url)


# === 신규 === 광고홍보학과 교수진 소개 전용 파서
# 구조: #page26 .table_box 안에 p.name, p.mail 이 있음
# 예: <p class="name">조 형 오</p>, <p class="mail">02-2260-3808<br>hocho@dongguk.edu</p>
def parse_adpr_professors(soup):
    rows = []

    for box in soup.select("#page26 .table_box"):
        name = ""
        email = ""

        name_tag = box.select_one("p.name")
        if name_tag:
            name = clean_prof_name_text(name_tag.get_text(" ", strip=True))

        mail_tag = box.select_one("p.mail")
        if mail_tag:
            emails = find_dongguk_emails(str(mail_tag) + " " + mail_tag.get_text(" ", strip=True))
            if emails:
                email = emails[0]

        if not email:
            emails = find_dongguk_emails(str(box) + " " + box.get_text(" ", strip=True))
            if emails:
                email = emails[0]

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


# === 신규 === 영화/영상 학과 교수 페이지 전용 파서
# 구조: .tbl_basic9 테이블 안에 strong 이름, E-mail 행이 있음
def parse_movie_professors(soup):
    rows = []

    for table in soup.select("table.tbl_basic9"):
        name = ""
        email = ""

        name_tag = table.select_one("strong")
        if name_tag:
            name = clean_prof_name_text(name_tag.get_text(" ", strip=True))

        emails = find_emails(str(table) + " " + table.get_text(" ", strip=True))
        if emails:
            email = emails[0]

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


def find_emails(text):
    emails = []

    for email in re.findall(EMAIL_RE, str(text)):
        email = email.strip().strip(".,;:)'\"")
        emails.append(email)

    return list(dict.fromkeys(emails))


def find_dongguk_emails(text):
    result = []

    for email in find_emails(text):
        if "@dongguk" in email.lower():
            result.append(email)

    return list(dict.fromkeys(result))


def make_driver():
    options = Options()

    # 필요하면 주석 해제
    options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.set_capability("acceptInsecureCerts", True)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)
    return driver


def get_soup(driver, url):
    driver.get(url)
    time.sleep(1)
    return BeautifulSoup(driver.page_source, "html.parser")


def is_prof_menu(text):
    text = norm_text(text)

    for word in PROF_TEXTS:
        if norm_text(word) in text:
            return True

    return False


def is_notice_menu(text):
    text = norm_text(text)

    for word in NOTICE_TEXTS:
        if norm_text(word) in text:
            return True

    return False


def get_notice_text_score(text):
    text = norm_text(text)
    score = 0

    for index, word in enumerate(NOTICE_TEXTS):
        if norm_text(word) in text:
            score = max(score, 100 - index)

    return score


def is_board_href(href):
    href = str(href).lower()
    checks = [
        "/article/",
        "/bbs/",
        "bo_table=",
        "board",
        "notice",
        "list.do",
        "list"
    ]

    for word in checks:
        if word in href:
            return True

    return False


def is_same_dept(link_text, dept_name):
    link_text = norm_text(link_text)
    dept_name = norm_text(dept_name)

    if link_text == dept_name:
        return True

    names = NAME_ALIASES.get(dept_name, [])
    for name in names:
        if norm_text(name) == link_text:
            return True

    return False


def find_professor_url(driver, page_url, dept_name):
    # === 신규 === 학과별 교수 URL 예외를 먼저 사용
    special_url = get_special_value(SPECIAL_PROFESSOR_URLS, dept_name)
    if special_url:
        return special_url

    if not page_url:
        return ""

    try:
        soup = get_soup(driver, page_url)
    except Exception:
        print("[교수URL 실패]", page_url)
        return ""

    matched_urls = []
    candidate_urls = []

    for a in soup.select("a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not is_prof_menu(text):
            continue

        if href and href != "#":
            return urljoin(page_url, href)

        parent = a.find_parent("li")
        if not parent:
            parent = a.find_parent()

        for sub_a in parent.select("a"):
            sub_text = clean_text(sub_a.get_text(" ", strip=True))
            sub_href = sub_a.get("href", "").strip()

            if not sub_href or sub_href == "#":
                continue

            full_url = urljoin(page_url, sub_href)
            candidate_urls.append(full_url)

            if is_same_dept(sub_text, dept_name):
                matched_urls.append(full_url)

    if matched_urls:
        return " | ".join(dict.fromkeys(matched_urls))

    if candidate_urls:
        return " | ".join(dict.fromkeys(candidate_urls))

    return ""


def add_notice_candidate(candidates, page_url, text, href):
    if not href or href == "#" or href == "#none":
        return

    if not is_notice_menu(text):
        return

    full_url = urljoin(page_url, href.strip())
    score = get_notice_text_score(text)

    if is_board_href(full_url):
        score += 1000

    if "게시판" in norm_text(text):
        score += 50

    candidates.append({
        "score": score,
        "url": full_url,
        "text": clean_text(text)
    })


def find_notice_url(driver, page_url, dept_name):
    # === 신규 === 학과별 공지사항 URL 예외를 먼저 사용
    special_url = get_special_value(SPECIAL_NOTICE_URLS, dept_name)
    if special_url:
        return special_url

    if not page_url:
        return ""

    try:
        soup = get_soup(driver, page_url)
    except Exception:
        print("[공지URL 실패]", page_url)
        return ""

    candidates = []

    for a in soup.select("a"):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        add_notice_candidate(candidates, page_url, text, href)

        if href and href not in ["#", "#none"]:
            continue

        if not is_notice_menu(text):
            continue

        parent = a.find_parent("li")
        if not parent:
            parent = a.find_parent()

        for sub_a in parent.select("a"):
            sub_text = clean_text(sub_a.get_text(" ", strip=True))
            sub_href = sub_a.get("href", "").strip()
            add_notice_candidate(candidates, page_url, sub_text, sub_href)

    candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

    if candidates:
        print("[공지URL]", dept_name, candidates[0].get("text", ""), candidates[0].get("url", ""))
        return candidates[0].get("url", "")

    return ""


def build_notice_page_url(notice_url, page_index):
    # === 신규 === 그누보드 계열 공지사항 예외
    if "bo_table=" in notice_url:
        if page_index == 1:
            return notice_url
        sep = "&" if "?" in notice_url else "?"
        return notice_url + sep + "page=" + str(page_index)

    # === 신규 === iBuilder 게시판 계열 예외
    if "/bbs/data/list.do" in notice_url:
        if page_index == 1:
            return notice_url
        sep = "&" if "?" in notice_url else "?"
        return notice_url + sep + "pageIndex=" + str(page_index)

    base = notice_url.split("?")[0]
    return base + "?pageIndex=" + str(page_index) + "&searchCondition=&searchKeyword=&category_cd="


def make_notice_detail_url(notice_url, seq, page_index):
    base = notice_url.split("?")[0]

    if "/list" in base:
        detail_base = base.replace("/list", "/detail")
    else:
        detail_base = base.rstrip("/") + "/detail"

    return detail_base.rstrip("/") + "/" + seq + "?pageIndex=" + str(page_index)


def make_url_target(url):
    return {
        "type": "url",
        "key": url,
        "url": url
    }


def make_fn_view_target(bm_id, bd_id, etc):
    return {
        "type": "fn_view",
        "key": "fn_view:" + bm_id + ":" + bd_id + ":" + etc,
        "bm_id": bm_id,
        "bd_id": bd_id,
        "etc": etc
    }


def get_notice_detail_targets(soup, notice_url, page_index):
    targets = []

    for a in soup.select("table.board tbody a"):
        href = a.get("href", "").strip()
        onclick = a.get("onclick", "").strip()

        if href and href != "#none" and "/detail/" in href:
            targets.append(make_url_target(urljoin(notice_url, href)))
            continue

        match = re.search(r"goDetail\((\d+)\)", onclick)
        if match:
            targets.append(make_url_target(make_notice_detail_url(notice_url, match.group(1), page_index)))

    for a in soup.select("a"):
        href = a.get("href", "").strip()

        if not href or href == "#" or href == "#none":
            continue

        full_url = urljoin(notice_url, href)

        # === 신규 === 그누보드 계열 상세 URL 예외
        if "bo_table=" in full_url and "wr_id=" in full_url:
            targets.append(make_url_target(full_url))
            continue

        # === 신규 === iBuilder 게시판 javascript:fn_view 예외
        match = re.search(r"fn_view\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?([^'\"]*)['\"]?\)", href)
        if match:
            targets.append(make_fn_view_target(match.group(1), match.group(2), match.group(3)))

    result = []
    used = set()

    for target in targets:
        key = target.get("key", "")
        if key in used:
            continue

        used.add(key)
        result.append(target)

    return result


def get_detail_soup_by_target(driver, list_url, target):
    if target.get("type") == "url":
        url = target.get("url", "")
        return get_soup(driver, url), url

    if target.get("type") == "fn_view":
        driver.get(list_url)
        time.sleep(0.5)
        driver.execute_script(
            "fn_view(arguments[0], arguments[1], arguments[2]);",
            target.get("bm_id", ""),
            target.get("bd_id", ""),
            target.get("etc", "")
        )
        time.sleep(1)
        return BeautifulSoup(driver.page_source, "html.parser"), driver.current_url

    return None, ""


def find_notice_admin_email(driver, notice_url, professor_emails):
    if not notice_url:
        return None

    checked_keys = set()

    for page_index in range(1, NOTICE_MAX_PAGE + 1):
        list_url = build_notice_page_url(notice_url, page_index)

        try:
            soup = get_soup(driver, list_url)
        except Exception:
            print("[공지목록 실패]", list_url)
            continue

        detail_targets = get_notice_detail_targets(soup, notice_url, page_index)
        detail_targets = [target for target in detail_targets if target.get("key", "") not in checked_keys]

        if not detail_targets:
            print("[공지] 상세 URL 없음", list_url)
            break

        print("[공지] page=", page_index, "상세=", len(detail_targets))

        for target in detail_targets:
            checked_keys.add(target.get("key", ""))

            try:
                detail_soup, detail_url = get_detail_soup_by_target(driver, list_url, target)
            except Exception:
                print("[공지상세 실패]", target.get("key", ""))
                continue

            if not detail_soup:
                continue

            board_view = detail_soup.select_one(".board_view")
            if not board_view:
                board_view = detail_soup.select_one(".board_view2")
            if not board_view:
                board_view = detail_soup.select_one(".board_view_wrap")
            if not board_view:
                board_view = detail_soup.select_one(".view")
            if not board_view:
                board_view = detail_soup

            html_text = str(board_view)
            body_text = board_view.get_text(" ", strip=True)
            emails = find_dongguk_emails(html_text + " " + body_text)

            for email in emails:
                if email.lower() not in professor_emails:
                    print("[공지메일 발견]", email, detail_url)
                    return {
                        "이메일": email,
                        "공지사항URL": detail_url
                    }

        time.sleep(0.2)

    return None


def get_depth3_urls(soup, professor_url):
    urls = []

    for a in soup.select(".depth3 a"):
        href = a.get("href", "").strip()

        if not href or href == "#":
            continue

        urls.append(urljoin(professor_url, href))

    return list(dict.fromkeys(urls))


def parse_prof_items(soup):
    rows = []

    for item in soup.select(".prof_item"):
        name = ""
        email = ""

        name_tag = item.select_one(".prof_info strong")
        if name_tag:
            name = clean_name(name_tag.get_text(" ", strip=True))

        mail_tag = item.select_one("li.mail .txt")
        if mail_tag:
            email = clean_text(mail_tag.get_text(" ", strip=True))

        if not email:
            emails = re.findall(EMAIL_RE, item.get_text(" ", strip=True))
            if emails:
                email = emails[0]

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


def parse_cons_teaching(soup):
    rows = []

    for item in soup.select(".cons-teaching"):
        name = ""
        email = ""

        photo_ps = item.select(".photo p")
        for p in photo_ps:
            text = clean_text(p.get_text(" ", strip=True))
            if "교수" in text:
                name = clean_name(text)
                break

        emails = re.findall(EMAIL_RE, item.get_text(" ", strip=True))
        if emails:
            email = clean_text(emails[0].replace("\xa0", ""))

        if name or email:
            rows.append({
                "이름": name,
                "이메일": email
            })

    return rows


def guess_prof_name(text, email):
    text = clean_text(text).replace(email, " ")

    match = re.search(r"([가-힣]{2,5})\s*(명예교수|석좌교수|초빙교수|겸임교수|부교수|조교수|교수)", text)
    if match:
        return clean_name(match.group(1))

    match = re.search(r"(명예교수|석좌교수|초빙교수|겸임교수|부교수|조교수|교수)\s*([가-힣]{2,5})", text)
    if match:
        return clean_name(match.group(2))

    skip_words = [
        "광고홍보학과", "동국대학교", "교수소개", "교수진", "이메일", "메일", "연구실", "전화", "학력", "경력", "전공"
    ]

    for word in re.findall(r"[가-힣]{2,5}", text):
        if word in skip_words:
            continue
        if "학과" in word or "교수" in word or "소개" in word:
            continue
        return clean_name(word)

    return ""


def parse_generic_professors(soup):
    rows = []
    used = set()

    for item in soup.select("tr, li, td, .prof, .professor, .member, .person, .item, .box"):
        item_text = item.get_text(" ", strip=True)
        emails = find_emails(str(item) + " " + item_text)

        for email in emails:
            key = email.lower()
            if key in used:
                continue

            used.add(key)
            rows.append({
                "이름": guess_prof_name(item_text, email),
                "이메일": email
            })

    if not rows:
        body_text = soup.get_text(" ", strip=True)
        for email in find_emails(str(soup) + " " + body_text):
            key = email.lower()
            if key in used:
                continue

            used.add(key)
            rows.append({
                "이름": guess_prof_name(body_text, email),
                "이메일": email
            })

    return rows


def parse_professors(soup):
    rows = []
    result = []
    used = set()

    # === 신규 === 학과별 전용 구조를 먼저 파싱
    rows.extend(parse_adpr_professors(soup))
    rows.extend(parse_movie_professors(soup))
    rows.extend(parse_prof_items(soup))
    rows.extend(parse_cons_teaching(soup))

    # 전용/기존 구조에서 못 잡힌 경우만 보조 파서 사용
    if not rows:
        rows.extend(parse_generic_professors(soup))

    for row in rows:
        key = (row.get("이름", ""), row.get("이메일", ""))
        if key in used:
            continue

        used.add(key)
        result.append(row)

    return result


def get_professors(driver, professor_url):
    if not professor_url:
        return []

    result = []

    for url in professor_url.split("|"):
        url = url.strip()
        if not url:
            continue

        try:
            soup = get_soup(driver, url)
        except Exception:
            print("[교수목록 실패]", url)
            continue

        depth3_urls = get_depth3_urls(soup, url)

        if depth3_urls:
            for depth_url in depth3_urls:
                try:
                    depth_soup = get_soup(driver, depth_url)
                    profs = parse_professors(depth_soup)

                    for prof in profs:
                        prof["교수URL"] = depth_url
                        result.append(prof)

                    print("[교수수집]", depth_url, len(profs), "명")
                except Exception:
                    print("[교수목록 실패]", depth_url)
        else:
            profs = parse_professors(soup)

            for prof in profs:
                prof["교수URL"] = url
                result.append(prof)

            print("[교수수집]", url, len(profs), "명")

    return result


def add_professor_rows(rows, driver, big_name, dept_name, dept_url):
    professor_url = find_professor_url(driver, dept_url, dept_name)
    professors = get_professors(driver, professor_url)
    professor_emails = set()

    if not professors:
        rows.append({
            "구분": "대학",
            "대분류": big_name,
            "중분류": dept_name,
            "소분류": dept_name,
            "직위": "교수",
            "업무": "교육·연구",
            "이름": "",
            "이메일": "",
            "URL": dept_url,
            "교수URL": professor_url
        })

        print("[수집]", big_name, ">", dept_name, "| 교수 0명")
        return professor_emails

    for prof in professors:
        for email in find_emails(prof.get("이메일", "")):
            professor_emails.add(email.lower())

        rows.append({
            "구분": "대학",
            "대분류": big_name,
            "중분류": dept_name,
            "소분류": dept_name,
            "직위": "교수",
            "업무": "교육·연구",
            "이름": prof.get("이름", ""),
            "이메일": prof.get("이메일", ""),
            "URL": dept_url,
            "교수URL": prof.get("교수URL", professor_url)
        })

    print("[수집]", big_name, ">", dept_name, "| 교수", len(professors), "명")
    return professor_emails


def add_notice_admin_row(rows, driver, big_name, dept_name, dept_url, professor_emails):
    notice_url = find_notice_url(driver, dept_url, dept_name)

    if not notice_url:
        print("[공지]", big_name, ">", dept_name, "| 공지사항 URL 없음")
        return

    found = find_notice_admin_email(driver, notice_url, professor_emails)

    if not found:
        print("[공지]", big_name, ">", dept_name, "| 행정 이메일 없음")
        return

    rows.append({
        "구분": "대학",
        "대분류": big_name,
        "중분류": dept_name,
        "소분류": "행정",
        "직위": "",
        "업무": "행정",
        "이름": "",
        "이메일": found.get("이메일", ""),
        "URL": found.get("공지사항URL", notice_url),
        "교수URL": ""
    })

    print("[수집]", big_name, ">", dept_name, "| 공지 행정", found.get("이메일", ""))


def main():
    print("[시작] 동국대 교수 목록 수집")

    driver = make_driver()
    rows = []
    processed_depts = set()

    soup = get_soup(driver, START_URL)

    for item in soup.select(".univ .item"):
        h3 = item.select_one("h3.depart_tit")
        if not h3:
            continue

        big_name = clean_text(h3.get_text(" ", strip=True))

        # 대분류 = 중분류 = 소분류 row는 pass
        # 그래서 여기서는 대분류 자체 row를 만들지 않음

        for a in item.select("ul.univ_list a.link"):
            span = a.select_one("span")
            if not span:
                continue

            dept_name = clean_text(span.get_text(" ", strip=True))
            dept_url = a.get("href", "").strip()
            dept_url = get_dept_url(dept_name, dept_url)

            processed_depts.add(norm_text(dept_name))

            professor_emails = add_professor_rows(rows, driver, big_name, dept_name, dept_url)
            add_notice_admin_row(rows, driver, big_name, dept_name, dept_url, professor_emails)

        for div in item.select("ul.univ_list div.link"):
            span = div.select_one("span")
            if not span:
                continue

            dept_name = clean_text(span.get_text(" ", strip=True))

            rows.append({
                "구분": "대학",
                "대분류": big_name,
                "중분류": dept_name,
                "소분류": dept_name,
                "직위": "교수",
                "업무": "교육·연구",
                "이름": "",
                "이메일": "",
                "URL": "",
                "교수URL": ""
            })

            processed_depts.add(norm_text(dept_name))

            print("[수집]", big_name, ">", dept_name, "| URL 없음")

    # === 신규 === 메인 목록에서 빠진 예외 학과 보정 처리
    for extra in EXTRA_DEPTS:
        big_name = extra.get("대분류", "")
        dept_name = extra.get("중분류", "")
        dept_url = extra.get("URL", "")

        if norm_text(dept_name) in processed_depts:
            continue

        print("[예외학과]", big_name, ">", dept_name)
        professor_emails = add_professor_rows(rows, driver, big_name, dept_name, dept_url)
        add_notice_admin_row(rows, driver, big_name, dept_name, dept_url, professor_emails)

    driver.quit()

    df = pd.DataFrame(rows, columns=[
        "구분",
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "교수URL"
    ])

    df.to_excel(OUT_FILE, index=False)

    print("[완료] 총", len(rows), "건 저장")
    print("[파일]", OUT_FILE)


if __name__ == "__main__":
    main()
