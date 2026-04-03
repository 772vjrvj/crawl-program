import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By


BASE_URL = "https://www.cms.caltech.edu"
LIST_URL = "https://www.cms.caltech.edu/people/faculty"
OUTPUT_FILE = "caltech_mce_faculty.xlsx"


def get_text(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return els[0].text.strip()
    return ""


def get_attr(parent, selector, attr):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return (els[0].get_attribute(attr) or "").strip()
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


def get_assistant_contact(driver, field_name):
    blocks = driver.find_elements(By.CSS_SELECTOR, "div.person-page2__assistants__contact_information")

    for block in blocks:
        if field_name == "email":
            value = get_text(block, "div.person-page2__assistants__email span.person-page2__field-data a")
            if not value:
                value = get_text(block, "div.person-page2__assistants__email span.person-page2__field-data")
            if value:
                return value

        if field_name == "phone":
            value = get_text(block, "div.person-page2__assistants__phone span.person-page2__field-data a")
            if not value:
                value = get_text(block, "div.person-page2__assistants__phone span.person-page2__field-data")
            if value:
                return value

    return ""


def get_area(driver):
    blocks = driver.find_elements(By.CSS_SELECTOR, "section.block-PersonProfileBlock")

    for block in blocks:
        title = get_text(block, "h3.person-page2__profile-block__title")
        if title.lower() != "overview":
            continue

        ps = block.find_elements(By.CSS_SELECTOR, "div.person-page2__profile-block__profile.profile-text div.rich-text p")
        texts = [p.text.strip() for p in ps if p.text.strip()]
        if texts:
            return "\n".join(texts)

        text = get_text(block, "div.person-page2__profile-block__profile.profile-text div.rich-text")
        if text:
            return text

    return ""


def crawl_detail(driver, url):
    print(f"[DETAIL] {url}")
    driver.get(url)
    time.sleep(2)

    name = get_text(driver, "div.person-page2__field.field__title h2")
    role = get_text(driver, "div.person-page2__field.field__job_title h5")
    email = get_assistant_contact(driver, "email")
    phone = get_assistant_contact(driver, "phone")
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