import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LIST_URL = "https://viterbi.usc.edu/directory/faculty/"
BASE_URL = "https://viterbi.usc.edu"
OUTPUT_XLSX = "usc_viterbi_faculty.xlsx"


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(180)
    return driver


def text_or_empty(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if not els:
        return ""
    return (els[0].get_attribute("textContent") or "").strip()


def get_profile_urls(driver):
    print("[1] 목록 접속")
    driver.get(LIST_URL)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#results"))
    )
    WebDriverWait(driver, 30).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#results > a"))
    )

    links = driver.find_elements(By.CSS_SELECTOR, "#results > a")
    print(f"[2] 링크 개수: {len(links)}")

    urls = []
    for i, link in enumerate(links, 1):
        href = (link.get_attribute("href") or "").strip()
        if not href:
            continue

        full_url = urljoin(BASE_URL, href)
        urls.append(full_url)
        print(f"    {i}/{len(links)} {full_url}")

    return urls


def get_block_items_by_title(driver, title_text):
    spans = driver.find_elements(By.CSS_SELECTOR, ".contactInformation > span")

    for span in spans:
        title = (span.get_attribute("textContent") or "").strip()
        if title != title_text:
            continue

        ul = span.find_element(By.XPATH, "following-sibling::ul[1]")
        lis = ul.find_elements(By.CSS_SELECTOR, "li")

        values = []
        for li in lis:
            text = (li.get_attribute("textContent") or "").strip()
            if text:
                values.append(text)

        return values

    return []


def parse_contact_info_items(items):
    phones = []
    emails = []

    for item in items:
        if "@" in item:
            emails.append(item)
        else:
            phones.append(item)

    return "\n".join(phones), "\n".join(emails)


def parse_profile(driver, profile_url):
    print(f"[상세 접속] {profile_url}")
    time.sleep(2)
    driver.get(profile_url)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".profileTopRight .facultyname"))
    )

    area_items = get_block_items_by_title(driver, "Appointments")
    office_items = get_block_items_by_title(driver, "Office")
    contact_items = get_block_items_by_title(driver, "Contact Information")

    contact_phone, contact_email = parse_contact_info_items(contact_items)

    phone = text_or_empty(driver, ".profileTopRight .phone")
    email = text_or_empty(driver, ".profileTopRight .email")

    if not phone:
        phone = contact_phone

    if not email:
        email = contact_email

    row = {
        "Name": text_or_empty(driver, ".profileTopRight .facultyname"),
        "Role": text_or_empty(driver, ".profileTopRight .faculty_academic_title"),
        "Area": "\n".join(area_items),
        "Office": "\n".join(office_items),
        "Phone": phone,
        "Email": email,
        "Profile URL": profile_url,
    }

    print(f"[상세 완료] {row['Name']}")
    return row


def save_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    headers = ["Name", "Role", "Area", "Office", "Phone", "Email", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("Name", ""),
            row.get("Role", ""),
            row.get("Area", ""),
            row.get("Office", ""),
            row.get("Phone", ""),
            row.get("Email", ""),
            row.get("Profile URL", ""),
        ])

    wb.save(OUTPUT_XLSX)
    print(f"[저장 완료] {OUTPUT_XLSX}")


def main():
    driver = create_driver()
    rows = []

    try:
        urls = get_profile_urls(driver)

        for i, url in enumerate(urls, 1):
            print(f"[진행] {i}/{len(urls)}")
            try:
                row = parse_profile(driver, url)
                rows.append(row)
                time.sleep(2)
            except Exception as e:
                print(f"[에러] {url} -> {e}")
                continue

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    save_excel(rows)


if __name__ == "__main__":
    main()