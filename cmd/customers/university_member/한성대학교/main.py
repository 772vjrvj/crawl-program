# -*- coding: utf-8 -*-

import time
import re
from urllib.parse import urljoin

import requests
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


BASE_URL = "https://www.hansung.ac.kr"

START_PAGES = [
    {
        "구분": "대학",
        "url": "https://www.hansung.ac.kr/hansung/6081/subview.do",
    },
    {
        "구분": "대학원",
        "url": "https://www.hansung.ac.kr/hansung/6091/subview.do",
    },
]

RND_URL = "https://www.hansung.ac.kr/rnd/4406/subview.do"
RND_TITLE = "산학연구처ㆍ산학협력단"

ORIGINAL_EXCEL = "한성대학교_전체_수집결과_원본.xlsx"
CLEAN_EXCEL = "한성대학교_전체_수집결과_정리본.xlsx"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
HANSUNG_KR_EMAIL_RE = r"[A-Za-z0-9._%+-]+@hansung\.kr"


def clean_text(text):
    return " ".join(text.split()).strip()


def make_url(href):
    if not href:
        return ""
    return urljoin(BASE_URL, href)


def find_emails(text):
    emails = re.findall(EMAIL_RE, text or "")
    return list(dict.fromkeys([x.strip() for x in emails]))


def find_hansung_kr_emails(text):
    emails = re.findall(HANSUNG_KR_EMAIL_RE, text or "")
    return list(dict.fromkeys([x.strip() for x in emails]))


def get_html_by_requests(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL,
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = "utf-8"
    return res.text


def get_html_by_selenium(url):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--window-size=1200,900")
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(1.5)

    html = driver.page_source
    driver.quit()

    return html


def get_html(url):
    html = get_html_by_requests(url)

    soup = BeautifulSoup(html, "html.parser")
    if (
            soup.select_one(".major-list-title")
            or soup.select_one(".professor_list")
            or soup.select_one(".tab_div.div_3")
            or soup.select_one("._wizOdr._prFlList.prfl-list")
            or soup.select_one("table.board-table")
            or soup.select_one(".txt")
    ):
        return html

    return get_html_by_selenium(url)


def parse_major_list(page_info, html):
    soup = BeautifulSoup(html, "html.parser")

    title_list = soup.select(".major-list-title")
    content_list = soup.select(".major-list-content")

    print()
    print("[목록]", page_info["구분"])
    print("[INFO] 대분류 개수:", len(title_list))
    print("[INFO] 내용영역 개수:", len(content_list))

    rows = []

    for title_box, content_box in zip(title_list, content_list):
        big_title_tag = title_box.select_one("h1")
        big_title = clean_text(big_title_tag.get_text()) if big_title_tag else ""

        li_list = content_box.select("ul > li")

        print("[대분류]", big_title, "/ 중분류 후보:", len(li_list))

        for li in li_list:
            mid_title_tag = li.select_one(".major-list-content-title h1")
            if not mid_title_tag:
                continue

            mid_title = clean_text(mid_title_tag.get_text())

            professor_a = li.select_one(".major-list-content-title .link1 a")
            home_a = li.select_one(".major-list-content-title .link2 a")

            professor_url = make_url(professor_a.get("href")) if professor_a else ""
            url = make_url(home_a.get("href")) if home_a else ""

            rows.append({
                "구분": page_info["구분"],
                "대분류": big_title,
                "중분류": mid_title,
                "교수URL": professor_url,
                "URL": url,
            })

    return rows


def collect_major_rows():
    rows = []

    for page_info in START_PAGES:
        print()
        print("[시작]", page_info["구분"], page_info["url"])

        html = get_html(page_info["url"])
        page_rows = parse_major_list(page_info, html)

        print("[완료]", page_info["구분"], "목록 수:", len(page_rows))

        rows.extend(page_rows)

    return rows


def find_tab_url(soup, tab_text):
    tab_box = soup.select_one(".tab_div.div_3")
    if not tab_box:
        return ""

    for a in tab_box.select("ul li a"):
        text = clean_text(a.get_text())
        if text == tab_text:
            return make_url(a.get("href"))

    return ""


def get_professor_name(li):
    p = li.select_one(".artclInfo p")
    if not p:
        return ""

    span = p.select_one("span")
    if span:
        span.extract()

    return clean_text(p.get_text())


def get_professor_email(li):
    mail_a = li.select_one('a[href^="mailto:"]')
    if not mail_a:
        return ""

    href = mail_a.get("href", "")
    emails = find_emails(href)
    return emails[0] if emails else ""


def parse_professors(base_row, html):
    soup = BeautifulSoup(html, "html.parser")

    board_url = find_tab_url(soup, "게시판")
    notice_url = find_tab_url(soup, "공지사항")

    professor_li_list = soup.select(".professor_list ul > li")

    rows = []

    for li in professor_li_list:
        name = get_professor_name(li)
        email = get_professor_email(li)

        rows.append({
            "구분": base_row["구분"],
            "대분류": base_row["대분류"],
            "중분류": base_row["중분류"],
            "소분류": base_row["중분류"],
            "직위": "교수",
            "직책": "",
            "업무": "교육·연구",
            "이름": name,
            "이메일": email,
            "교수URL": base_row["교수URL"],
            "게시판URL": board_url,
            "공지사항URL": notice_url,
            "URL": base_row["URL"],
            "게시글URL": "",
        })

    if len(rows) == 0:
        rows.append({
            "구분": base_row["구분"],
            "대분류": base_row["대분류"],
            "중분류": base_row["중분류"],
            "소분류": base_row["중분류"],
            "직위": "교수",
            "직책": "",
            "업무": "교육·연구",
            "이름": "",
            "이메일": "",
            "교수URL": base_row["교수URL"],
            "게시판URL": board_url,
            "공지사항URL": notice_url,
            "URL": base_row["URL"],
            "게시글URL": "",
        })

    return rows


def collect_all_professors(major_rows):
    result_rows = []

    for idx, row in enumerate(major_rows, start=1):
        professor_url = row["교수URL"]

        print()
        print("[교수페이지]", idx, "/", len(major_rows))
        print("[구분]", row["구분"])
        print("[분류]", row["대분류"], ">", row["중분류"])
        print("[URL]", professor_url)

        if not professor_url:
            result_rows.append({
                "구분": row["구분"],
                "대분류": row["대분류"],
                "중분류": row["중분류"],
                "소분류": row["중분류"],
                "직위": "교수",
                "직책": "",
                "업무": "교육·연구",
                "이름": "",
                "이메일": "",
                "교수URL": "",
                "게시판URL": "",
                "공지사항URL": "",
                "URL": row["URL"],
                "게시글URL": "",
            })
            continue

        html = get_html(professor_url)
        professor_rows = parse_professors(row, html)

        print("[교수 수]", len([x for x in professor_rows if x["이름"]]))
        print("[게시판URL]", professor_rows[0]["게시판URL"])
        print("[공지사항URL]", professor_rows[0]["공지사항URL"])

        result_rows.extend(professor_rows)

    return result_rows


def get_info_value(li, key):
    for dl in li.select(".artclInfo dl"):
        dt = dl.select_one("dt")
        dd = dl.select_one("dd")

        if not dt or not dd:
            continue

        if clean_text(dt.get_text()) == key:
            return clean_text(dd.get_text(" "))

    return ""


def get_rnd_email(li):
    mail_a = li.select_one('.artclInfo a[href^="mailto:"]')
    if mail_a:
        emails = find_emails(mail_a.get("href", ""))
        if emails:
            return emails[0]

    text = get_info_value(li, "EMAIL")
    emails = find_emails(text)
    return emails[0] if emails else ""


def parse_rnd_tabs(html):
    soup = BeautifulSoup(html, "html.parser")

    tab_box = soup.select_one(".tab_div.div_3")
    rows = []

    if not tab_box:
        return rows

    for a in tab_box.select("ul li a"):
        mid_title = clean_text(a.get_text())
        url = make_url(a.get("href"))

        if not mid_title or not url:
            continue

        rows.append({
            "구분": RND_TITLE,
            "대분류": RND_TITLE,
            "중분류": mid_title,
            "소분류": "행정",
            "URL": url,
        })

    return rows


def parse_rnd_people(base_row, html):
    soup = BeautifulSoup(html, "html.parser")

    li_list = soup.select("._wizOdr._prFlList.prfl-list > li")
    rows = []

    for li in li_list:
        name_tag = li.select_one(".prfl-name strong")
        rank_tag = li.select_one(".prof-rank p")

        name = clean_text(name_tag.get_text()) if name_tag else ""
        rank = clean_text(rank_tag.get_text()) if rank_tag else ""

        position = get_info_value(li, "직책")
        work = get_info_value(li, "담당업무")
        email = get_rnd_email(li)

        if not position:
            position = rank

        rows.append({
            "구분": base_row["구분"],
            "대분류": base_row["대분류"],
            "중분류": base_row["중분류"],
            "소분류": base_row["소분류"],
            "직위": "",
            "직책": position,
            "업무": work,
            "이름": name,
            "이메일": email,
            "교수URL": "",
            "게시판URL": "",
            "공지사항URL": "",
            "URL": base_row["URL"],
            "게시글URL": "",
        })

    if len(rows) == 0:
        rows.append({
            "구분": base_row["구분"],
            "대분류": base_row["대분류"],
            "중분류": base_row["중분류"],
            "소분류": base_row["소분류"],
            "직위": "",
            "직책": "",
            "업무": "",
            "이름": "",
            "이메일": "",
            "교수URL": "",
            "게시판URL": "",
            "공지사항URL": "",
            "URL": base_row["URL"],
            "게시글URL": "",
        })

    return rows


def collect_rnd_rows():
    print()
    print("[산학연구처ㆍ산학협력단] 탭 목록 수집 시작")

    html = get_html(RND_URL)
    tab_rows = parse_rnd_tabs(html)

    print("[산학연구처ㆍ산학협력단] 탭 수:", len(tab_rows))

    result_rows = []

    for idx, row in enumerate(tab_rows, start=1):
        print()
        print("[산학연구처ㆍ산학협력단]", idx, "/", len(tab_rows), row["중분류"])
        print("[URL]", row["URL"])

        html = get_html(row["URL"])
        people_rows = parse_rnd_people(row, html)

        print("[인원 수]", len([x for x in people_rows if x["이름"]]))

        result_rows.extend(people_rows)

    return result_rows


def get_total_page(html):
    soup = BeautifulSoup(html, "html.parser")

    tot = soup.select_one("._paging ._totPage")
    if tot:
        text = clean_text(tot.get_text())
        if text.isdigit():
            return int(text)

    page_nums = []

    for a in soup.select("._paging ul li a"):
        text = clean_text(a.get_text())
        if text.isdigit():
            page_nums.append(int(text))

    for strong in soup.select("._paging ul li strong"):
        text = clean_text(strong.get_text())
        if text.isdigit():
            page_nums.append(int(text))

    if page_nums:
        return max(page_nums)

    return 1


def parse_board_articles(html):
    soup = BeautifulSoup(html, "html.parser")

    rows = []

    for tr in soup.select("table.board-table tbody tr"):
        a = tr.select_one(".td-title a")
        writer_td = tr.select_one(".td-write")

        if not a:
            continue

        title = clean_text(a.get_text())
        writer = clean_text(writer_td.get_text()) if writer_td else ""
        article_url = make_url(a.get("href"))

        rows.append({
            "제목": title,
            "작성자": writer,
            "게시글URL": article_url,
        })

    return rows


def find_article_detail_emails(article_url):
    html = get_html_by_requests(article_url)
    soup = BeautifulSoup(html, "html.parser")

    txt = soup.select_one(".txt")
    if txt:
        text = txt.get_text(" ")
    else:
        text = soup.get_text(" ")

    return find_hansung_kr_emails(text)


def make_board_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--window-size=1200,900")
    options.page_load_strategy = "eager"

    return webdriver.Chrome(options=options)


def crawl_board_one(driver, base_row, board_url, board_name, professor_email_set, added_email_set):
    print()
    print("[게시글 이메일 수집]", board_name)
    print("[분류]", base_row["구분"], ">", base_row["대분류"], ">", base_row["중분류"])
    print("[URL]", board_url)

    driver.get(board_url)
    time.sleep(1.2)

    total_page = get_total_page(driver.page_source)
    print("[페이지 수]", total_page)

    for page in range(1, total_page + 1):
        print("[페이지]", page, "/", total_page)

        driver.get(board_url)
        time.sleep(0.8)

        if page > 1:
            driver.execute_script("page_link('" + str(page) + "')")
            time.sleep(0.8)

        articles = parse_board_articles(driver.page_source)
        print("[게시글 수]", len(articles))

        for idx, article in enumerate(articles, start=1):
            print("[게시글]", idx, "/", len(articles), article["작성자"], article["제목"][:30])

            emails = find_article_detail_emails(article["게시글URL"])

            for email in emails:
                email_key = email.lower()

                if email_key in professor_email_set:
                    continue

                if email_key in added_email_set:
                    continue

                added_email_set.add(email_key)

                print("[이메일 추가 후 중지]", article["작성자"], email)

                return [{
                    "구분": base_row["구분"],
                    "대분류": base_row["대분류"],
                    "중분류": base_row["중분류"],
                    "소분류": "행정",
                    "직위": "",
                    "직책": "",
                    "업무": "행정",
                    "이름": article["작성자"],
                    "이메일": email,
                    "교수URL": base_row["교수URL"],
                    "게시판URL": base_row["게시판URL"],
                    "공지사항URL": base_row["공지사항URL"],
                    "URL": article["게시글URL"],
                    "게시글URL": article["게시글URL"],
                }]

    return []


def collect_board_admin_rows(professor_rows):
    print()
    print("[게시판/공지사항 이메일 보강 시작]")

    professor_email_set = set()

    for row in professor_rows:
        email = row.get("이메일", "")
        if row.get("직위") == "교수" and email:
            professor_email_set.add(email.lower())

    dept_map = {}

    for row in professor_rows:
        if row.get("구분") not in ["대학", "대학원"]:
            continue

        if not row.get("게시판URL") and not row.get("공지사항URL"):
            continue

        key = row["구분"] + "|" + row["대분류"] + "|" + row["중분류"]

        if key not in dept_map:
            dept_map[key] = row

    print("[대상 학과/학부/대학원 수]", len(dept_map))

    result_rows = []
    added_email_set = set()

    driver = make_board_driver()

    for idx, row in enumerate(dept_map.values(), start=1):
        print()
        print("[대상]", idx, "/", len(dept_map), row["구분"], row["대분류"], row["중분류"])

        found_rows = []

        if row["게시판URL"]:
            found_rows = crawl_board_one(
                driver,
                row,
                row["게시판URL"],
                "게시판",
                professor_email_set,
                added_email_set,
            )
            result_rows.extend(found_rows)

        if len(found_rows) > 0:
            continue

        if row["공지사항URL"]:
            found_rows = crawl_board_one(
                driver,
                row,
                row["공지사항URL"],
                "공지사항",
                professor_email_set,
                added_email_set,
            )
            result_rows.extend(found_rows)

    driver.quit()

    print()
    print("[게시판/공지사항 이메일 보강 완료]", len(result_rows))

    return result_rows


def save_excels(result_rows):
    columns = [
        "구분",
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "직책",
        "업무",
        "이름",
        "이메일",
        "교수URL",
        "게시판URL",
        "공지사항URL",
        "URL",
        "게시글URL",
    ]

    df = pd.DataFrame(result_rows)
    df = df.reindex(columns=columns)

    df.to_excel(ORIGINAL_EXCEL, index=False)
    print("[엑셀] 원본 저장 완료:", ORIGINAL_EXCEL)

    clean_df = df.copy()
    clean_df["이메일"] = clean_df["이메일"].fillna("").astype(str).str.strip()
    clean_df = clean_df[clean_df["이메일"] != ""]
    clean_df["_email_key"] = clean_df["이메일"].str.lower()
    clean_df = clean_df.drop_duplicates(subset=["_email_key"], keep="first")
    clean_df = clean_df.drop(columns=["_email_key"])

    clean_df.to_excel(CLEAN_EXCEL, index=False)
    print("[엑셀] 정리본 저장 완료:", CLEAN_EXCEL)


def main():
    print("[INFO] 한성대학교 대학/대학원 목록 수집 시작")

    major_rows = collect_major_rows()

    print()
    print("[INFO] 전체 학과/전공 URL 수:", len(major_rows))
    print("[INFO] 교수 목록 수집 시작")

    professor_rows = collect_all_professors(major_rows)

    print()
    print("[INFO] 산학연구처ㆍ산학협력단 수집 시작")

    rnd_rows = collect_rnd_rows()

    print()
    print("[INFO] 게시판/공지사항 이메일 보강 시작")

    board_admin_rows = collect_board_admin_rows(professor_rows)

    result_rows = professor_rows + rnd_rows + board_admin_rows

    print()
    print("[INFO] 교수 row 수:", len(professor_rows))
    print("[INFO] 산학연구처ㆍ산학협력단 row 수:", len(rnd_rows))
    print("[INFO] 게시판/공지사항 보강 row 수:", len(board_admin_rows))
    print("[INFO] 최종 row 수:", len(result_rows))

    save_excels(result_rows)

    print("[INFO] 전체 작업 완료")


if __name__ == "__main__":
    main()
