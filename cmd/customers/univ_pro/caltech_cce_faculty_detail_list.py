import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By


BASE_URL = "https://www.cce.caltech.edu/people"
LIST_URL = "https://www.cce.caltech.edu/people"
OUTPUT_FILE = "caltech_cce_faculty.xlsx"


def get_text(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return els[0].text.strip()
    return ""


def get_profile_links(driver):
    driver.get(LIST_URL)
    time.sleep(2)

    links = []
    seen = set()

    items = driver.find_elements(By.CSS_SELECTOR, "div.person-teaser__title a.person-teaser__link")

    for a in items:
        href = (a.get_attribute("href") or "").strip()
        if not href:
            continue

        href = urljoin(BASE_URL, href)
        if href in seen:
            continue

        seen.add(href)
        links.append(href)

    return links


def get_email(driver):
    value = get_text(driver, "span.person-page2__field-data.field-data__email a")
    if value:
        return value
    return get_text(driver, "span.person-page2__field-data.field-data__email")


def get_phone(driver):
    value = get_text(driver, "div.person-page2__field.field__office_phone span.person-page2__field-data.field-data__office_phone a")
    if value:
        return value
    return get_text(driver, "div.person-page2__field.field__office_phone span.person-page2__field-data.field-data__office_phone")


def get_area(driver):
    value = get_text(driver, "div.person-page2__field.field__research_summary div.person-page2__field-data.field-data__research_summary")
    return value


def get_role(driver):
    for selector in [
        "div.person-page2__field.field__job_title h3",
        "div.person-page2__field.field__job_title h4",
        "div.person-page2__field.field__job_title h5",
        "div.person-page2__field.field__job_title h6",
    ]:
        value = get_text(driver, selector)
        if value:
            return value
    return ""


def crawl_detail(driver, url):
    print(f"[DETAIL] {url}")
    driver.get(url)
    time.sleep(2)

    name = get_text(driver, "h1.simple-page-header-block__title")
    email = get_email(driver)
    phone = get_phone(driver)
    role = get_role(driver)
    area = get_area(driver)

    return {
        "Name": name,
        "Role": role,
        "Email": email,
        "Phone": phone,
        "Office": "",
        "Area": area,
        "Lab Name": "",
        "Profile URL": url,
    }


def save_excel(rows, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "faculty"

    ws.append([
        "Name",
        "Role",
        "Email",
        "Phone",
        "Office",
        "Area",
        "Lab Name",
        "Profile URL",
    ])

    for row in rows:
        ws.append([
            row["Name"],
            row["Role"],
            row["Email"],
            row["Phone"],
            row["Office"],
            row["Area"],
            row["Lab Name"],
            row["Profile URL"],
        ])

    wb.save(path)
    print(f"[SAVE] {path}")


def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)

    try:
        profile_links = get_profile_links(driver)
        print(f"[TOTAL LINKS] {len(profile_links)}")

        results = []

        for i, url in enumerate(profile_links, 1):
            print(f"[{i}/{len(profile_links)}]")
            try:
                row = crawl_detail(driver, url)
                results.append(row)
                print(row["Name"], "|", row["Email"], "|", row["Phone"])
            except Exception as e:
                print(f"[ERROR] {url} -> {e}")

        save_excel(results, OUTPUT_FILE)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()