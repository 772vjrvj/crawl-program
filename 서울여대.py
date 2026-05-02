import re
import json
import pandas as pd

from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


START_URL = "https://www.swu.ac.kr/www/swuniversity.html"
GRAD_ADMIN_URL = "https://www.swu.ac.kr/www/swuprea_58.html"
GRAD_INDEX_URL = "https://www.swu.ac.kr/grdindex.do"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

COLUMNS = [
    "대분류",
    "중분류",
    "소분류",
    "직위",
    "업무",
    "이름",
    "이메일",
    "URL",
    "홈페이지URL"
]


def clean_text(text):
    return text.replace("(*)", "").replace("\n", " ").strip()


def clean_name(text):
    name = clean_text(text)

    for word in ["명예교수", "석좌교수", "특임교수", "부교수", "조교수", "교수", "강사"]:
        name = name.replace(word, "")

    return name.replace(" ", "").strip()


def clean_grad_name(text):
    return re.sub(r"\(.*?\)", "", clean_text(text)).strip()


def find_emails(text):
    return list(dict.fromkeys(re.findall(EMAIL_RE, text)))


def unique_list(values):
    return list(dict.fromkeys([v for v in values if v]))


def get_mailto_email(parent):
    mails = parent.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")

    if len(mails) == 0:
        return ""

    return mails[0].get_attribute("href").replace("mailto:", "").strip()


def get_email_from_box(parent):
    email = get_mailto_email(parent)

    if email:
        return email

    emails = find_emails(parent.text)

    if len(emails) > 0:
        return emails[0]

    return ""


def make_row(big, mid, small, position, work, name, email, url, home_url):
    return {
        "대분류": big,
        "중분류": mid,
        "소분류": small,
        "직위": position,
        "업무": work,
        "이름": name,
        "이메일": email,
        "URL": url,
        "홈페이지URL": home_url
    }


def get_categories(driver):
    print("[1단계] 대학 목록 수집 시작")

    driver.get(START_URL)

    rows = []

    for section in driver.find_elements(By.CSS_SELECTOR, "#main .section"):
        title_list = section.find_elements(By.CSS_SELECTOR, ".titl1, .titl0")
        title = clean_text(title_list[0].text)

        if title == "대학원":
            continue

        links = section.find_elements(By.CSS_SELECTOR, "ul.col_list0 > li > a")

        if len(links) == 0:
            title_links = title_list[0].find_elements(By.CSS_SELECTOR, "a")
            url = title_links[0].get_attribute("href") if len(title_links) > 0 else ""

            rows.append({
                "대분류": title,
                "중분류": title,
                "소분류": title,
                "URL": url
            })

        for a in links:
            name = clean_text(a.text)

            rows.append({
                "대분류": title,
                "중분류": name if name else title,
                "소분류": name if name else title,
                "URL": a.get_attribute("href")
            })

    print("[1단계 완료] 대학 목록 수:", len(rows))
    return rows


def get_tabui4_pages(driver, row):
    driver.get(row["URL"])

    tabs = driver.find_elements(By.CSS_SELECTOR, ".tabui4 a[href]")

    if len(tabs) == 0:
        return [row]

    pages = []

    for a in tabs:
        name = clean_text(a.text)

        item = row.copy()
        item["소분류"] = name
        item["URL"] = a.get_attribute("href")
        pages.append(item)

    return pages


def get_home_urls(driver):
    urls = []

    for a in driver.find_elements(By.CSS_SELECTOR, "a.btn.btn_xl.btn_blue_gray[href]"):
        href = a.get_attribute("href")

        if href and href.startswith("http"):
            urls.append(href)

    return unique_list(urls)


def get_professor_url(driver):
    for a in driver.find_elements(By.CSS_SELECTOR, ".tabui0 a[href]"):
        text = clean_text(a.text)

        if "교수진" in text or "교수진 소개" in text:
            return a.get_attribute("href")

    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        text = clean_text(a.text)

        if "교수진" in text or "교수진 소개" in text:
            return a.get_attribute("href")

    return ""


def get_professors(driver, page, home_urls):
    rows = []

    for li in driver.find_elements(By.CSS_SELECTOR, "ul.pro_list li"):
        name_list = li.find_elements(By.CSS_SELECTOR, ".CELL.CELL1 .name")
        email = get_email_from_box(li)

        if len(name_list) > 0 and email:
            rows.append(make_row(
                page["대분류"],
                page["중분류"],
                page["소분류"],
                "교수",
                "교육·연구",
                clean_name(name_list[0].text),
                email,
                page["URL"],
                ", ".join(home_urls)
            ))

    return rows


def get_homepage_emails(driver, page, home_urls):
    rows = []

    for home_url in home_urls:
        print("[홈페이지 확인]", home_url)

        try:
            driver.get(home_url)
        except Exception as e:
            print("[홈페이지 접속 실패]", home_url, "/", e)
            continue

        emails = find_emails(driver.page_source)

        for email in emails:
            rows.append(make_row(
                page["대분류"],
                page["중분류"],
                "행정실",
                "",
                "행정",
                "",
                email,
                page["URL"],
                home_url
            ))

    return rows


def get_university_rows(driver):
    result = []

    categories = get_categories(driver)

    print("[2단계] 대학 상세 페이지 수집 시작")

    for category in categories:
        pages = get_tabui4_pages(driver, category)

        for page in pages:
            driver.get(page["URL"])

            home_urls = get_home_urls(driver)
            professor_url = get_professor_url(driver)

            if professor_url:
                driver.get(professor_url)
                page["URL"] = professor_url

            professors = get_professors(driver, page, home_urls)
            admins = get_homepage_emails(driver, page, home_urls)

            result.extend(professors)
            result.extend(admins)

            print(
                "[대학 수집중]",
                page["대분류"],
                ">",
                page["중분류"],
                ">",
                page["소분류"],
                "/ 교수:",
                len(professors),
                "/ 행정:",
                len(admins),
                "/ 누적:",
                len(result)
            )

    return result


def get_graduate_admin_rows(driver):
    print("[3단계] 대학원 교학팀 수집 시작")

    driver.get(GRAD_ADMIN_URL)

    rows = []

    for tr in driver.find_elements(By.CSS_SELECTOR, "div.table0.center tr"):
        tds = tr.find_elements(By.CSS_SELECTOR, "td")

        if len(tds) < 5:
            continue

        position = clean_text(tds[0].text)
        name = clean_text(tds[1].text)
        email = get_email_from_box(tds[3])
        work = clean_text(tds[4].text)

        if email:
            rows.append(make_row(
                "대학원",
                "대학원",
                "대학원 교학팀",
                position,
                work,
                name,
                email,
                GRAD_ADMIN_URL,
                ""
            ))

    print("[3단계 완료] 대학원 교학팀 수:", len(rows))
    return rows


def get_graduate_sites(driver):
    print("[4단계] 대학원 사이트 목록 수집 시작")

    driver.get(GRAD_INDEX_URL)

    rows = []

    for a in driver.find_elements(By.CSS_SELECTOR, ".site_box a[href]"):
        href = a.get_attribute("href")
        name = clean_grad_name(a.text)

        if name == "서울여자대학교":
            continue

        rows.append({
            "대학원명": name,
            "URL": href
        })

        print("[대학원 사이트]", name, href)

    print("[4단계 완료] 대학원 사이트 수:", len(rows))
    return rows


def get_first_direct_link(li):
    links = li.find_elements(By.XPATH, "./a")

    if len(links) == 0:
        return None

    return links[0]


def get_first_direct_ul(li):
    uls = li.find_elements(By.XPATH, "./ul")

    if len(uls) == 0:
        return None

    return uls[0]


def get_graduate_departments(driver, grad):
    driver.get(grad["URL"])

    dept_menu = None
    menu_names = ["학과안내", "학과소개", "전공안내", "전공소개"]

    for li in driver.find_elements(By.CSS_SELECTOR, "ul#gnb > li"):
        a = get_first_direct_link(li)

        if not a:
            continue

        text = clean_text(a.text)

        for menu_name in menu_names:
            if menu_name in text:
                dept_menu = li
                break

        if dept_menu:
            break

    if not dept_menu:
        return [{
            "대분류": grad["대학원명"],
            "중분류": grad["대학원명"],
            "소분류": grad["대학원명"],
            "URL": grad["URL"]
        }]

    root_ul = get_first_direct_ul(dept_menu)

    if not root_ul:
        return [{
            "대분류": grad["대학원명"],
            "중분류": grad["대학원명"],
            "소분류": grad["대학원명"],
            "URL": grad["URL"]
        }]

    rows = []

    for li in root_ul.find_elements(By.XPATH, "./li"):
        a = get_first_direct_link(li)
        child_ul = get_first_direct_ul(li)

        if not a:
            continue

        first_name = clean_text(a.text)

        if child_ul:
            for child_li in child_ul.find_elements(By.XPATH, "./li"):
                child_a = get_first_direct_link(child_li)

                if not child_a:
                    continue

                dept_name = clean_text(child_a.text)

                rows.append({
                    "대분류": grad["대학원명"] + " / " + first_name,
                    "중분류": dept_name,
                    "소분류": dept_name,
                    "URL": child_a.get_attribute("href")
                })
        else:
            rows.append({
                "대분류": grad["대학원명"],
                "중분류": first_name,
                "소분류": first_name,
                "URL": a.get_attribute("href")
            })

    if len(rows) == 0:
        rows.append({
            "대분류": grad["대학원명"],
            "중분류": grad["대학원명"],
            "소분류": grad["대학원명"],
            "URL": grad["URL"]
        })

    return rows


def get_graduate_professor_rows(driver):
    result = []

    sites = get_graduate_sites(driver)

    print("[5단계] 대학원 교수 수집 시작")

    for site in sites:
        pages = get_graduate_departments(driver, site)

        print("[대학원 학과 수]", site["대학원명"], len(pages))

        for page in pages:
            driver.get(page["URL"])

            professor_url = get_professor_url(driver)

            if professor_url:
                driver.get(professor_url)
                page["URL"] = professor_url

            professors = get_professors(driver, page, [])

            result.extend(professors)

            print(
                "[대학원 수집중]",
                page["대분류"],
                ">",
                page["중분류"],
                ">",
                page["소분류"],
                "/ 교수:",
                len(professors),
                "/ 누적:",
                len(result)
            )

    return result


def main():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    result = []

    result.extend(get_university_rows(driver))
    result.extend(get_graduate_admin_rows(driver))
    result.extend(get_graduate_professor_rows(driver))

    driver.quit()

    print("[6단계] 전체 수집 완료:", len(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    now = datetime.now().strftime("%Y%m%d%H%M%S")
    excel_name = f"swu_result_{now}.xlsx"

    df = pd.DataFrame(result, columns=COLUMNS)
    df.to_excel(excel_name, index=False)

    print("[저장 완료]", excel_name)


if __name__ == "__main__":
    main()
