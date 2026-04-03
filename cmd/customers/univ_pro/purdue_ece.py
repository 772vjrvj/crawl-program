import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LIST_URL = "https://engineering.purdue.edu/ECE/People/Faculty"
OUTPUT_FILE = "purdue_ece_faculty.xlsx"


def text_or_empty(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return els[0].text.strip()
    return ""


def attr_or_empty(parent, selector, attr):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return (els[0].get_attribute(attr) or "").strip()
    return ""


def normalize_text(text):
    return " ".join(text.split()).strip()


def build_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)
    return driver


def collect_profile_links(driver):
    driver.get(LIST_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.col-12.list-name a"))
    )
    time.sleep(1)

    links = []
    seen = set()

    items = driver.find_elements(By.CSS_SELECTOR, "div.col-12.list-name a")
    for a in items:
        href = (a.get_attribute("href") or "").strip()
        if not href:
            continue

        href = urljoin(LIST_URL, href)
        if href in seen:
            continue

        seen.add(href)
        links.append(href)

    return links


def parse_contact_info(profile_box):
    office = ""
    phone = ""
    email = ""

    blocks = profile_box.find_elements(By.CSS_SELECTOR, ".profile-contact-info > div")
    for block in blocks:
        strongs = block.find_elements(By.TAG_NAME, "strong")
        if not strongs:
            continue

        label = strongs[0].text.strip().replace(":", "")
        value = normalize_text(block.text.replace(strongs[0].text, "").strip())

        if label == "Office":
            office = value
        elif label == "Office Phone":
            phone = value
        elif label == "E-mail":
            mailto = attr_or_empty(block, 'a[href^="mailto:"]', "href")
            if mailto.lower().startswith("mailto:"):
                email = mailto[7:].strip()
            else:
                email = value

    return office, phone, email


def parse_area(profile_box):
    h2_list = profile_box.find_elements(By.TAG_NAME, "h2")
    for h2 in h2_list:
        if normalize_text(h2.text) != "Areas of Interest":
            continue

        ul_list = h2.find_elements(By.XPATH, "./following-sibling::ul[1]")
        if ul_list:
            values = []
            li_list = ul_list[0].find_elements(By.CSS_SELECTOR, "li.primary")
            for li in li_list:
                txt = normalize_text(li.text)
                if txt:
                    values.append(txt)

            if values:
                return "\n".join(values)
        break

    research = text_or_empty(profile_box, "p.profile-research")
    return normalize_text(research)


def parse_profile(driver, url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.container.profile-page"))
    )
    time.sleep(1)

    profile_box = driver.find_element(By.CSS_SELECTOR, "div.container.profile-page")

    name = normalize_text(text_or_empty(profile_box, "h1"))
    role = normalize_text(text_or_empty(profile_box, "div.profile-titles"))
    office, phone, email = parse_contact_info(profile_box)
    area = parse_area(profile_box)

    return {
        "Name": name,
        "Role": role,
        "Area": area,
        "Office": office,
        "Phone": phone,
        "Email": email,
        "Lab Name": "",
        "Profile URL": url,
    }


def save_to_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Faculty"

    headers = ["Name", "Role", "Area", "Office", "Phone", "Email", "Lab Name", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row["Name"],
            row["Role"],
            row["Area"],
            row["Office"],
            row["Phone"],
            row["Email"],
            row["Lab Name"],
            row["Profile URL"],
        ])

    wb.save(OUTPUT_FILE)


def main():
    driver = build_driver()
    try:
        profile_links = collect_profile_links(driver)
        print(f"수집된 상세 링크 수: {len(profile_links)}")

        result = []
        for idx, url in enumerate(profile_links, 1):
            print(f"[{idx}/{len(profile_links)}] {url}")
            try:
                data = parse_profile(driver, url)
                result.append(data)
            except Exception as e:
                print(f"상세 실패: {url} | {e}")

        save_to_excel(result)
        print(f"저장 완료: {OUTPUT_FILE}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()