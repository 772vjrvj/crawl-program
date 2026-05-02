import re
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By


START_URL = "https://www.swu.ac.kr/www/swuniversity.html"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def clean_text(text):
    return text.replace("(*)", "").strip()


def clean_name(text):
    return re.sub(r"(명예|석좌|특임|부|조)?교수|강사", "", text).replace(" ", "").strip()


def find_emails(text):
    return ", ".join(dict.fromkeys(re.findall(EMAIL_RE, text)))


def get_dept_list(driver):
    driver.get(START_URL)
    time.sleep(1)

    rows = []

    for section in driver.find_elements(By.CSS_SELECTOR, "#main .section"):
        titles = section.find_elements(By.CSS_SELECTOR, ".titl1")
        if not titles:
            continue

        big = clean_text(titles[0].text)
        links = section.find_elements(By.CSS_SELECTOR, "ul.col_list0 li a")

        if links:
            for a in links:
                name = clean_text(a.text)

                rows.append({
                    "대분류": big,
                    "중분류": name,
                    "소분류": name,
                    "URL": a.get_attribute("href")
                })
        else:
            a_tags = titles[0].find_elements(By.TAG_NAME, "a")
            if a_tags:
                rows.append({
                    "대분류": big,
                    "중분류": big,
                    "소분류": big,
                    "URL": a_tags[0].get_attribute("href")
                })

    return rows


def expand_tabui4(driver, item):
    driver.get(item["URL"])
    time.sleep(0.7)

    tabs = driver.find_elements(By.CSS_SELECTOR, ".tabui4 .row a")

    if not tabs:
        return [item]

    rows = []

    for a in tabs:
        rows.append({
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": clean_text(a.text),
            "URL": a.get_attribute("href")
        })

    return rows


def get_homepage_url(driver):
    for a in driver.find_elements(By.CSS_SELECTOR, "a.btn_blue_gray[href]"):
        if "홈페이지바로가기" in a.text.replace(" ", ""):
            return a.get_attribute("href")

    return ""


def get_professor_url(driver):
    for a in driver.find_elements(By.CSS_SELECTOR, ".tabui0 .row a"):
        if "교수진" in a.text:
            return a.get_attribute("href")

    return ""


def get_professors(driver, item, professor_url, homepage_url):
    driver.get(professor_url)
    time.sleep(0.7)

    rows = []

    for li in driver.find_elements(By.CSS_SELECTOR, ".pro_list > li"):
        names = li.find_elements(By.CSS_SELECTOR, ".name")
        if not names:
            continue

        rows.append({
            "대분류": item["대분류"],
            "중분류": item["중분류"],
            "소분류": item["소분류"],
            "직위": "교수",
            "업무": "교육·연구",
            "이름": clean_name(names[0].text),
            "이메일": find_emails(li.text),
            "URL": professor_url,
            "홈페이지주소": homepage_url
        })

    return rows


def get_admin(driver, item, homepage_url):
    if not homepage_url:
        return None

    driver.get(homepage_url)
    time.sleep(1)

    # 홈페이지 안에 있는 모든 이메일 형식 수집
    email = find_emails(driver.page_source)

    if not email:
        return None

    return {
        "대분류": item["대분류"],
        "중분류": item["중분류"],
        "소분류": "행정실",
        "직위": "",
        "업무": "행정",
        "이름": "",
        "이메일": email,
        "URL": homepage_url,
        "홈페이지주소": homepage_url
    }


def main():
    driver = webdriver.Chrome()

    result = []
    dept_list = get_dept_list(driver)

    final_list = []
    for item in dept_list:
        final_list += expand_tabui4(driver, item)

    for item in final_list:
        driver.get(item["URL"])
        time.sleep(0.7)

        homepage_url = get_homepage_url(driver)
        professor_url = get_professor_url(driver)

        if professor_url:
            result += get_professors(driver, item, professor_url, homepage_url)

        admin = get_admin(driver, item, homepage_url)
        if admin:
            result.append(admin)

    driver.quit()

    df = pd.DataFrame(result)

    columns = [
        "대분류",
        "중분류",
        "소분류",
        "직위",
        "업무",
        "이름",
        "이메일",
        "URL",
        "홈페이지주소"
    ]

    df = df.reindex(columns=columns)
    df.to_excel("swu_result.xlsx", index=False)

    print("저장 완료: swu_result.xlsx")
    print("총 개수:", len(result))


if __name__ == "__main__":
    main()