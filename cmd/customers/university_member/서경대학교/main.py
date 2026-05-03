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


START_URL = "https://www.skuniv.ac.kr/organization-phone"

TARGET_MIDDLE_NAMES = ["대학", "대학원", "부속기관", "부설연구소"]

OUTPUT_ORIGIN_FILE = "서경대학교_교수_URL_이메일_원본.xlsx"
OUTPUT_CLEAN_FILE = "서경대학교_교수_URL_이메일_정리본.xlsx"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
SKUNIV_EMAIL_RE = r"[A-Za-z0-9._%+-]+@skuniv\.ac\.kr"
NOTICE_MAX_PAGES = 30

LIBERAL_ORG_URL = "https://liberal.skuniv.ac.kr/about#!/organization"
GRAD_ORG_URL = "https://grad.skuniv.ac.kr/organization"
LIFEEDU_URL = "https://lifeedu.skuniv.ac.kr/"

LIFEEDU_MAJOR_URLS = [
    {
        "중분류": "미용학전공",
        "소분류": "미용학전공",
        "URL": "https://lifeedu.skuniv.ac.kr/major_beauty_professor"
    },
    {
        "중분류": "모델학전공",
        "소분류": "모델학전공",
        "URL": "https://lifeedu.skuniv.ac.kr/major_model_professor"
    },
    {
        "중분류": "실용무용학",
        "소분류": "실용무용학",
        "URL": "https://lifeedu.skuniv.ac.kr/major_dance_professor"
    }
]


def log(message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}")


def clean_text(text):
    if not text:
        return ""

    return text.replace("\n", " ").replace("\t", " ").strip()


def clean_name(text):
    name = clean_text(text)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\s*/\s*.*$", "", name)

    title_pattern = (
        r"(연구교수|명예교수|석좌교수|특임교수|겸임교수|초빙교수|"
        r"객원교수|외래교수|전임교수|주임교수|부교수|조교수|교수|학과장)$"
    )

    name = re.sub(r"\s*" + title_pattern, "", name).strip()

    return name


def find_emails(text):
    emails = re.findall(EMAIL_RE, text or "")
    return list(dict.fromkeys(emails))


def find_emails_from_soup(area):
    text = area.get_text(" ", strip=True) if area else ""
    hrefs = []

    if area:
        for a in area.select('a[href^="mailto:"]'):
            href = a.get("href", "")
            href = href.replace("mailto:", "")
            href = href.split("?")[0]
            hrefs.append(href)

    return find_emails(text + " " + " ".join(hrefs))


def make_driver():
    options = Options()
    options.page_load_strategy = "eager"

    # 헤드리스
    options.add_argument("--headless=new")

    # 속도/안정화
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)

    return driver


def wait_page(driver, delay_sec=0.5):
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    time.sleep(delay_sec)


def get_page_html(driver, url, delay_sec=0.5):
    if not url:
        return ""

    try:
        driver.get(url)
        wait_page(driver, delay_sec)
        return driver.page_source
    except Exception as e:
        log(f"[ERROR] 페이지 이동 실패: {url} / {str(e)}")
        return ""


def get_skuniv_org_list(driver):
    log("[조직도] 접속 시작")
    driver.get(START_URL)

    WebDriverWait(driver, 10).until(
        lambda d: len(d.find_elements("css selector", ".org-middle-group")) > 0
    )

    log("[조직도] org-middle-group 확인 완료")

    rows = driver.execute_script("""
        const targetNames = arguments[0];
        const rows = [];

        function cleanText(text) {
            if (!text) {
                return "";
            }

            return text.replace(/\\s+/g, " ").trim();
        }

        function parseContext(button) {
            const raw = button.getAttribute("data-context");

            if (!raw) {
                return {};
            }

            try {
                return JSON.parse(raw);
            } catch (e) {
                return {};
            }
        }

        document.querySelectorAll(".org-middle-group").forEach(function(middleGroup) {
            const middleButton = middleGroup.querySelector(".org-middle-header .org-middle-button");

            if (!middleButton) {
                return;
            }

            const middleName = cleanText(middleButton.textContent);

            if (!targetNames.includes(middleName)) {
                return;
            }

            middleGroup.querySelectorAll(".org-middle-content .org-minor-group").forEach(function(minorGroup) {
                const minorButton = minorGroup.querySelector(".org-minor-title .org-minor-button");

                if (!minorButton) {
                    return;
                }

                const majorName = cleanText(minorButton.textContent);
                const subButtons = minorGroup.querySelectorAll(".org-sub-list .org-sub-item .org-sub-button");

                subButtons.forEach(function(subButton) {
                    const context = parseContext(subButton);

                    const subName = context["세분류"] || cleanText(subButton.textContent);
                    const homepage = context["홈페이지"] || "";

                    rows.push({
                        "대분류": majorName,
                        "중분류": subName,
                        "소분류": subName,
                        "URL": homepage
                    });
                });
            });
        });

        return rows;
    """, TARGET_MIDDLE_NAMES)

    log(f"[조직도] 수집 완료: {len(rows)}개")

    return rows


def find_professor_url(driver, homepage_url):
    html = get_page_html(driver, homepage_url)

    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # 1차: a 태그 text가 교수인 링크
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "")

        if text == "교수" or text.startswith("교수 "):
            return urljoin(homepage_url, href)

    # 2차: text에 교수가 있고 href/class에 professor가 있는 링크
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "")
        class_text = " ".join(a.get("class", []))

        check_text = href.lower() + " " + class_text.lower()

        if "교수" in text and "professor" in check_text:
            return urljoin(homepage_url, href)

    # 3차: href에 professor가 있는 링크
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")

        if "professor" in href.lower():
            return urljoin(homepage_url, href)

    return ""


def get_professors(driver, professor_url):
    html = get_page_html(driver, professor_url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    panel_wrappers = soup.select(".panel-wrapper")

    if len(panel_wrappers) >= 2:
        area = panel_wrappers[1]
    elif len(panel_wrappers) == 1:
        area = panel_wrappers[0]
    else:
        area = soup

    trs = area.select("table tbody tr")

    if not trs:
        trs = area.select("tr")

    professors = []

    for tr in trs:
        h4 = tr.find("h4")

        if not h4:
            continue

        name = clean_name(h4.get_text(" ", strip=True))
        email = ""

        mail_a = tr.select_one('a[href^="mailto:"]')

        if mail_a:
            email = mail_a.get("href", "")
            email = email.replace("mailto:", "")
            email = email.split("?")[0].strip()

        if not email:
            emails = find_emails_from_soup(tr)

            if emails:
                email = emails[0]

        professors.append({
            "이름": name,
            "이메일": email
        })

    return professors


def find_skuniv_emails(text):
    emails = re.findall(SKUNIV_EMAIL_RE, text or "", re.I)
    return list(dict.fromkeys(emails))


def find_skuniv_emails_from_soup(area):
    text = area.get_text(" ", strip=True) if area else ""
    hrefs = []

    if area:
        for a in area.select('a[href^="mailto:"]'):
            href = a.get("href", "")
            href = href.replace("mailto:", "")
            href = href.split("?")[0]
            hrefs.append(href)

    return find_skuniv_emails(text + " " + " ".join(hrefs))


def make_notice_page_url(notice_url, page):
    if page <= 1:
        return notice_url

    if re.search(r"([?&])page=\d+", notice_url):
        return re.sub(r"([?&])page=\d+", r"\1page=" + str(page), notice_url)

    sep = "&" if "?" in notice_url else "?"
    return notice_url + sep + "page=" + str(page)


def find_notice_url(driver, homepage_url):
    html = get_page_html(driver, homepage_url, 0.5)

    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        text = re.sub(r"\s+", " ", text)
        href = a.get("href", "")

        if "학부 공지사항" in text:
            return urljoin(homepage_url, href)

    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        text = re.sub(r"\s+", " ", text)
        href = a.get("href", "")

        if "공지사항" in text and "notice" in href.lower():
            return urljoin(homepage_url, href)

    return ""


def get_notice_article_links(soup, notice_url):
    links = []

    for a in soup.select("table.boardList td.title a[href]"):
        href = a.get("href", "")
        full_url = urljoin(notice_url, href)

        if "document_srl=" in full_url or re.search(r"/\d+($|[?#])", full_url):
            links.append(full_url)

    if not links:
        for a in soup.find_all("a", href=True):
            text = clean_text(a.get_text(" ", strip=True))
            href = a.get("href", "")
            full_url = urljoin(notice_url, href)

            if not text:
                continue

            if "document_srl=" in full_url or re.search(r"/\d+($|[?#])", full_url):
                links.append(full_url)

    return list(dict.fromkeys(links))


def find_notice_admin_email(driver, notice_url, professor_email_set):
    seen_links = set()

    for page in range(1, NOTICE_MAX_PAGES + 1):
        page_url = make_notice_page_url(notice_url, page)
        log(f"[공지사항] page={page} 접속: {page_url}")

        html = get_page_html(driver, page_url, 0.4)

        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        links = get_notice_article_links(soup, page_url)
        new_links = []

        for link in links:
            key = link.split("#")[0]

            if key in seen_links:
                continue

            seen_links.add(key)
            new_links.append(link)

        if not new_links:
            log(f"[공지사항] page={page} 신규 게시글 없음 → 중지")
            break

        for idx, detail_url in enumerate(new_links, start=1):
            log(f"[공지사항] page={page} 상세 {idx}/{len(new_links)} 확인")

            detail_html = get_page_html(driver, detail_url, 0.3)

            if not detail_html:
                continue

            detail_soup = BeautifulSoup(detail_html, "html.parser")
            area = detail_soup.select_one(".viewDocument")

            if not area:
                area = detail_soup.select_one(".boardRead")

            if not area:
                area = detail_soup

            emails = find_skuniv_emails_from_soup(area)

            for email in emails:
                if email.lower() in professor_email_set:
                    continue

                return {
                    "이메일": email,
                    "상세URL": detail_url
                }

    return {}


def collect_notice_admin_row(driver, org, professor_email_set, fallback_url=""):
    homepage_url = org.get("URL", "")

    if not homepage_url:
        return None

    notice_url = find_notice_url(driver, homepage_url)

    if not notice_url and fallback_url:
        notice_url = find_notice_url(driver, fallback_url)

    if not notice_url:
        log("[공지사항] 학부 공지사항 URL 없음")
        return None

    log(f"[공지사항] 학부 공지사항 URL 발견: {notice_url}")

    found = find_notice_admin_email(driver, notice_url, professor_email_set)

    if not found:
        log("[공지사항] 교수 메일이 아닌 @skuniv.ac.kr 이메일 없음")
        return None

    admin_org = dict(org)
    admin_org["소분류"] = "행정"

    log(f"[공지사항] 행정 이메일 발견: {found.get('이메일', '')}")

    return make_result_row(
        admin_org,
        found.get("상세URL", notice_url),
        "",
        "행정",
        "",
        found.get("이메일", ""),
        "성공",
        "학부 공지사항 상세페이지에서 교수 메일이 아닌 @skuniv.ac.kr 이메일을 수집했습니다."
    )


def make_result_row(org, professor_url, position, duty, name, email, status, message):
    return {
        "대분류": org.get("대분류", ""),
        "중분류": org.get("중분류", ""),
        "소분류": org.get("소분류", ""),
        "직위": position,
        "업무": duty,
        "이름": clean_name(name),
        "이메일": email,
        "URL": org.get("URL", ""),
        "교수URL": professor_url,
        "상태": status,
        "메시지": message
    }


def make_professor_row(org, professor_url, name, email, status, message):
    return make_result_row(
        org,
        professor_url,
        "교수",
        "교육·연구",
        name,
        email,
        status,
        message
    )


def get_cell_text(cells, index):
    if len(cells) <= index:
        return ""

    return clean_text(cells[index].get_text(" ", strip=True))


def get_cell_email(cells, index):
    if len(cells) <= index:
        return ""

    emails = find_emails_from_soup(cells[index])

    if emails:
        return ", ".join(emails)

    return ""


def collect_liberal_exception(driver):
    log("[예외1] 인성교양대학/교양교육연구소 수집 시작")

    html = get_page_html(driver, LIBERAL_ORG_URL, 1.5)
    rows = []

    if not html:
        rows.append(make_result_row(
            {"대분류": "인성교양대학", "중분류": "교양교육연구소", "소분류": "교양교육연구소", "URL": LIBERAL_ORG_URL},
            LIBERAL_ORG_URL,
            "",
            "",
            "",
            "",
            "페이지실패",
            "예외1 페이지 접속에 실패했습니다."
        ))
        return rows

    soup = BeautifulSoup(html, "html.parser")
    response_tables = soup.select(".response_table")

    log(f"[예외1] response_table 수: {len(response_tables)}")

    # 1번 response_table: 행정
    if len(response_tables) >= 1:
        table = response_tables[0].find("table")

        if table:
            trs = table.select("tbody tr")

            for tr in trs:
                cells = tr.find_all("td")

                position = get_cell_text(cells, 1)
                name = get_cell_text(cells, 2)
                duty = get_cell_text(cells, 3)
                email = get_cell_email(cells, 5)

                if not name and not email:
                    continue

                status = "성공" if email else "이메일없음"
                message = "예외1 1번 response_table 행정 데이터를 수집했습니다."

                rows.append(make_result_row(
                    {"대분류": "인성교양대학", "중분류": "교양교육연구소", "소분류": "행정", "URL": LIBERAL_ORG_URL},
                    LIBERAL_ORG_URL,
                    position,
                    duty,
                    name,
                    email,
                    status,
                    message
                ))

    # 2번, 3번 response_table: 교수
    for table_idx in [1, 2]:
        if len(response_tables) <= table_idx:
            continue

        table = response_tables[table_idx].find("table")

        if not table:
            continue

        trs = table.select("tbody tr")

        for tr in trs:
            cells = tr.find_all("td")

            name = get_cell_text(cells, 1)
            email = get_cell_email(cells, 5)

            if not name and not email:
                continue

            status = "성공" if email else "이메일없음"
            message = f"예외1 {table_idx + 1}번 response_table 교수 데이터를 수집했습니다."

            rows.append(make_professor_row(
                {"대분류": "인성교양대학", "중분류": "교양교육연구소", "소분류": "인성교양대학", "URL": LIBERAL_ORG_URL},
                LIBERAL_ORG_URL,
                name,
                email,
                status,
                message
            ))

    # divide_table 1번: FYP 디렉터
    divide_tables = soup.select(".divide_table")

    log(f"[예외1] divide_table 수: {len(divide_tables)}")

    if len(divide_tables) >= 1:
        table = divide_tables[0].find("table")

        if table:
            trs = table.select("tbody tr")

            for tr in trs:
                cells = tr.find_all("td")

                name = get_cell_text(cells, 0)
                email = get_cell_email(cells, 2)

                if not name and not email:
                    continue

                status = "성공" if email else "이메일없음"
                message = "예외1 divide_table FYP 디렉터 데이터를 수집했습니다."

                rows.append(make_result_row(
                    {"대분류": "인성교양대학", "중분류": "교양교육연구소", "소분류": "행정", "URL": LIBERAL_ORG_URL},
                    LIBERAL_ORG_URL,
                    "",
                    "FYP 디렉터",
                    name,
                    email,
                    status,
                    message
                ))

    if not rows:
        rows.append(make_result_row(
            {"대분류": "인성교양대학", "중분류": "교양교육연구소", "소분류": "교양교육연구소", "URL": LIBERAL_ORG_URL},
            LIBERAL_ORG_URL,
            "",
            "",
            "",
            "",
            "수집없음",
            "예외1 페이지에서 수집 가능한 데이터를 찾지 못했습니다."
        ))

    log(f"[예외1] 수집 완료: {len(rows)}행")

    return rows


def make_cell_data(cell):
    return {
        "text": clean_text(cell.get_text(" ", strip=True)),
        "email": ", ".join(find_emails_from_soup(cell))
    }


def parse_rowspan_table(table):
    active = {}
    rows = []

    for tr in table.select("tbody tr"):
        row = []
        col = 0
        cells = tr.find_all(["th", "td"], recursive=False)

        for cell in cells:
            while col in active:
                item = active[col]
                row.append(item["data"])
                item["left"] -= 1

                if item["left"] <= 0:
                    del active[col]

                col += 1

            data = make_cell_data(cell)
            rowspan = cell.get("rowspan", "1")
            colspan = cell.get("colspan", "1")

            if not str(rowspan).isdigit():
                rowspan = 1
            else:
                rowspan = int(rowspan)

            if not str(colspan).isdigit():
                colspan = 1
            else:
                colspan = int(colspan)

            for offset in range(colspan):
                row.append(data)

                if rowspan > 1:
                    active[col + offset] = {
                        "left": rowspan - 1,
                        "data": data
                    }

            col += colspan

        while col in active:
            item = active[col]
            row.append(item["data"])
            item["left"] -= 1

            if item["left"] <= 0:
                del active[col]

            col += 1

        rows.append(row)

    return rows


def get_table_value(row, index, key):
    if len(row) <= index:
        return ""

    return row[index].get(key, "")


def collect_grad_exception(driver):
    log("[예외2] 대학원 조직도 수집 시작")

    html = get_page_html(driver, GRAD_ORG_URL, 1.0)
    rows = []

    if not html:
        rows.append(make_result_row(
            {"대분류": "대학원", "중분류": "대학원", "소분류": "행정", "URL": GRAD_ORG_URL},
            GRAD_ORG_URL,
            "",
            "",
            "",
            "",
            "페이지실패",
            "예외2 페이지 접속에 실패했습니다."
        ))
        return rows

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select(".sku-table")

    log(f"[예외2] sku-table 수: {len(tables)}")

    for table in tables:
        parsed_rows = parse_rowspan_table(table)

        for parsed_row in parsed_rows:
            position = get_table_value(parsed_row, 0, "text")
            duty = get_table_value(parsed_row, 1, "text")
            name = get_table_value(parsed_row, 2, "text")
            email = get_table_value(parsed_row, 4, "email")

            if not email:
                email = ", ".join(find_emails(get_table_value(parsed_row, 4, "text")))

            if not position and not name and not email:
                continue

            status = "성공" if email else "이메일없음"
            message = "예외2 대학원 조직도 데이터를 수집했습니다."

            rows.append(make_result_row(
                {"대분류": "대학원", "중분류": "대학원", "소분류": "행정", "URL": GRAD_ORG_URL},
                GRAD_ORG_URL,
                position,
                duty,
                name,
                email,
                status,
                message
            ))

    if not rows:
        rows.append(make_result_row(
            {"대분류": "대학원", "중분류": "대학원", "소분류": "행정", "URL": GRAD_ORG_URL},
            GRAD_ORG_URL,
            "",
            "",
            "",
            "",
            "수집없음",
            "예외2 페이지에서 수집 가능한 데이터를 찾지 못했습니다."
        ))

    log(f"[예외2] 수집 완료: {len(rows)}행")

    return rows


def collect_lifeedu_home(driver):
    log("[예외3] 예술교육원 메인 이메일 수집 시작")

    html = get_page_html(driver, LIFEEDU_URL, 1.0)
    rows = []

    if not html:
        rows.append(make_result_row(
            {"대분류": "예술교육원", "중분류": "입학홍보실", "소분류": "행정", "URL": LIFEEDU_URL},
            LIFEEDU_URL,
            "",
            "행정",
            "",
            "",
            "페이지실패",
            "예외3 예술교육원 메인 접속에 실패했습니다."
        ))
        return rows

    soup = BeautifulSoup(html, "html.parser")
    emails = find_emails_from_soup(soup)

    if not emails:
        rows.append(make_result_row(
            {"대분류": "예술교육원", "중분류": "입학홍보실", "소분류": "행정", "URL": LIFEEDU_URL},
            LIFEEDU_URL,
            "",
            "행정",
            "",
            "",
            "이메일없음",
            "예외3 예술교육원 메인에서 이메일을 찾지 못했습니다."
        ))
        return rows

    for email in emails:
        rows.append(make_result_row(
            {"대분류": "예술교육원", "중분류": "입학홍보실", "소분류": "행정", "URL": LIFEEDU_URL},
            LIFEEDU_URL,
            "",
            "행정",
            "",
            email,
            "성공",
            "예외3 예술교육원 메인 이메일을 수집했습니다."
        ))

    log(f"[예외3] 예술교육원 메인 이메일 수집 완료: {len(rows)}행")

    return rows


def get_lifeedu_email(soup):
    for li in soup.select(".info_content li"):
        label = li.find("span")
        label_text = clean_text(label.get_text(" ", strip=True)) if label else ""

        if "이메일" not in label_text and "메일" not in label_text:
            continue

        emails = find_emails_from_soup(li)

        if emails:
            return emails[0]

    emails = find_emails_from_soup(soup)

    if emails:
        return emails[0]

    return ""


def collect_lifeedu_major(driver, item):
    middle = item.get("중분류", "")
    sub = item.get("소분류", "")
    list_url = item.get("URL", "")

    log(f"[예외3] 예술교육원 {middle} 교수 수집 시작")

    html = get_page_html(driver, list_url, 1.0)
    rows = []

    org = {
        "대분류": "예술교육원",
        "중분류": middle,
        "소분류": sub,
        "URL": list_url
    }

    if not html:
        rows.append(make_professor_row(
            org,
            list_url,
            "",
            "",
            "페이지실패",
            f"예외3 {middle} 교수 목록 페이지 접속에 실패했습니다."
        ))
        return rows

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for li in soup.select(".major_professor_wrapper li"):
        a = li.find("a", href=True)

        if not a:
            continue

        name_el = li.select_one(".kor_name")
        name = clean_name(name_el.get_text(" ", strip=True)) if name_el else ""
        detail_url = urljoin(list_url, a.get("href", ""))

        links.append({
            "이름": name,
            "상세URL": detail_url
        })

    log(f"[예외3] {middle} 교수 상세 링크 수: {len(links)}")

    if not links:
        rows.append(make_professor_row(
            org,
            list_url,
            "",
            "",
            "교수목록없음",
            f"예외3 {middle} major_professor_wrapper 교수 목록을 찾지 못했습니다."
        ))
        return rows

    for idx, link in enumerate(links, start=1):
        detail_url = link.get("상세URL", "")
        log(f"[예외3] {middle} {idx}/{len(links)} 상세 접속: {detail_url}")

        detail_html = get_page_html(driver, detail_url, 0.7)

        if not detail_html:
            rows.append(make_professor_row(
                org,
                detail_url,
                link.get("이름", ""),
                "",
                "페이지실패",
                f"예외3 {middle} 교수 상세 페이지 접속에 실패했습니다."
            ))
            continue

        detail_soup = BeautifulSoup(detail_html, "html.parser")

        name_el = detail_soup.select_one(".kor_name")
        name = clean_name(name_el.get_text(" ", strip=True)) if name_el else link.get("이름", "")
        email = get_lifeedu_email(detail_soup)

        status = "성공" if email else "이메일없음"
        message = f"예외3 {middle} 교수 상세 데이터를 수집했습니다."

        rows.append(make_professor_row(
            org,
            detail_url,
            name,
            email,
            status,
            message
        ))

    log(f"[예외3] 예술교육원 {middle} 교수 수집 완료: {len(rows)}행")

    return rows


def collect_lifeedu_exception(driver):
    rows = []

    rows.extend(collect_lifeedu_home(driver))

    for item in LIFEEDU_MAJOR_URLS:
        rows.extend(collect_lifeedu_major(driver, item))

    log(f"[예외3] 예술교육원 전체 수집 완료: {len(rows)}행")

    return rows


def collect_exception_rows(driver):
    log("[예외] 추가 예외 데이터 수집 시작")

    rows = []
    rows.extend(collect_liberal_exception(driver))
    rows.extend(collect_grad_exception(driver))
    rows.extend(collect_lifeedu_exception(driver))

    log(f"[예외] 추가 예외 데이터 수집 종료: {len(rows)}행")

    return rows


def collect_all(driver):
    org_rows = get_skuniv_org_list(driver)
    result_rows = []

    total = len(org_rows)

    log(f"[전체] 교수 정보 수집 시작: {total}개")

    for idx, org in enumerate(org_rows, start=1):
        major = org.get("대분류", "")
        middle = org.get("중분류", "")
        homepage_url = org.get("URL", "")
        professor_email_set = set()

        if homepage_url:
            homepage_url = urljoin(START_URL, homepage_url)
            org["URL"] = homepage_url

        log(f"[{idx}/{total}] 시작: {major} > {middle}")
        log(f"[{idx}/{total}] 홈페이지 URL: {homepage_url}")

        if not homepage_url:
            log(f"[{idx}/{total}] 홈페이지 없음 → 빈 row 추가")

            result_rows.append(
                make_professor_row(
                    org,
                    "",
                    "",
                    "",
                    "홈페이지없음",
                    "조직도 data-context에 홈페이지 값이 없습니다."
                )
            )
            continue

        professor_url = find_professor_url(driver, homepage_url)

        if not professor_url:
            log(f"[{idx}/{total}] 교수URL 못 찾음 → 빈 row 추가")

            result_rows.append(
                make_professor_row(
                    org,
                    "",
                    "",
                    "",
                    "교수URL없음",
                    "홈페이지에서 교수 메뉴 링크를 찾지 못했습니다."
                )
            )

            notice_row = collect_notice_admin_row(driver, org, professor_email_set)

            if notice_row:
                result_rows.append(notice_row)

            log(f"[{idx}/{total}] 완료: {major} > {middle}")
            continue

        log(f"[{idx}/{total}] 교수URL 발견: {professor_url}")

        professors = get_professors(driver, professor_url)

        if not professors:
            log(f"[{idx}/{total}] 교수 목록 없음 → 빈 row 추가")

            result_rows.append(
                make_professor_row(
                    org,
                    professor_url,
                    "",
                    "",
                    "교수목록없음",
                    "교수URL에 접속했지만 교수 목록을 찾지 못했습니다."
                )
            )

            notice_row = collect_notice_admin_row(driver, org, professor_email_set, professor_url)

            if notice_row:
                result_rows.append(notice_row)

            log(f"[{idx}/{total}] 완료: {major} > {middle}")
            continue

        log(f"[{idx}/{total}] 교수 수집 성공: {len(professors)}명")

        for professor in professors:
            for email_item in find_emails(professor.get("이메일", "")):
                professor_email_set.add(email_item.lower())

        for professor in professors:
            name = professor.get("이름", "")
            email = professor.get("이메일", "")

            if email:
                status = "성공"
                message = "교수명과 이메일을 수집했습니다."
            else:
                status = "이메일없음"
                message = "교수명은 수집했지만 이메일이 없습니다."

            result_rows.append(
                make_professor_row(
                    org,
                    professor_url,
                    name,
                    email,
                    status,
                    message
                )
            )

        notice_row = collect_notice_admin_row(driver, org, professor_email_set, professor_url)

        if notice_row:
            result_rows.append(notice_row)

        log(f"[{idx}/{total}] 완료: {major} > {middle}")

    log(f"[전체] 일반 교수/공지사항 정보 수집 종료: {len(result_rows)}행")

    exception_rows = collect_exception_rows(driver)
    result_rows.extend(exception_rows)

    log(f"[전체] 전체 정보 수집 종료: {len(result_rows)}행")

    return result_rows

def save_excel(rows):
    columns = [
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "교수URL",
        "상태",
        "메시지"
    ]

    df = pd.DataFrame(rows, columns=columns)

    # 1) 원본 엑셀: 수집 결과 전체 저장
    df.to_excel(OUTPUT_ORIGIN_FILE, index=False)

    # 2) 정리본 엑셀: 이메일 공백 제거 + 이메일 중복 제거
    clean_df = df.copy()
    clean_df["이메일"] = clean_df["이메일"].fillna("").astype(str).str.strip()
    clean_df = clean_df[clean_df["이메일"] != ""]
    clean_df["이메일_KEY"] = clean_df["이메일"].str.lower()
    clean_df = clean_df.drop_duplicates(subset=["이메일_KEY"], keep="first")
    clean_df = clean_df.drop(columns=["이메일_KEY"])
    clean_df.to_excel(OUTPUT_CLEAN_FILE, index=False)

    log(f"[엑셀] 원본 저장 완료: {OUTPUT_ORIGIN_FILE}")
    log(f"[엑셀] 원본 저장 행: {len(df)}")
    log(f"[엑셀] 정리본 저장 완료: {OUTPUT_CLEAN_FILE}")
    log(f"[엑셀] 정리본 저장 행: {len(clean_df)}")


def print_summary(rows):
    summary = {}

    for row in rows:
        status = row.get("상태", "")

        if status not in summary:
            summary[status] = 0

        summary[status] += 1

    log("[요약] 상태별 건수")

    for key, value in summary.items():
        log(f"[요약] {key}: {value}")


def main():
    driver = make_driver()

    try:
        rows = collect_all(driver)

        print_summary(rows)
        save_excel(rows)

    finally:
        time.sleep(1)
        driver.quit()
        log("[종료] 브라우저 종료 완료")


if __name__ == "__main__":
    main()
