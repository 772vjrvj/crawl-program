import time

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


OUTPUT_FILE = "purdue_me_faculty_retry.xlsx"

FAILED_URLS =['https://engineering.purdue.edu/BME/People/ptProfile?resource_id=241220', 'https://polytechnic.purdue.edu/profile/jmgarcia', 'https://www.physics.purdue.edu/people/faculty/anjung.php', 'https://polytechnic.purdue.edu/profile/akostrow', 'https://www.pnw.edu/people/prashant-k-sarswat-ph-d/', 'https://engineering.purdue.edu/IE/people/ptProfile?resource_id=256650', 'https://engineering.purdue.edu/ECE/People/ptProfile?resource_id=117180', 'https://engineering.purdue.edu/SEE/People/ptProfile?resource_id=57089', 'https://polytechnic.purdue.edu/profile/rweissba', 'https://academics.pnw.edu/engineering/chenn-zhou/', 'https://engineering.purdue.edu/Engr/People/ptProfile?resource_id=4110', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=28548', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=11828', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=29601', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=11205', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=29613', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=28815', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=29622', 'https://engineering.purdue.edu/ME/People/ptProfile?resource_id=29391']

def text_or_empty(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return els[0].text.strip()
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


def get_h2_ul_text(profile_box, title_text):
    h2_list = profile_box.find_elements(By.TAG_NAME, "h2")
    for h2 in h2_list:
        if normalize_text(h2.text) != title_text:
            continue

        ul_list = h2.find_elements(By.XPATH, "./following-sibling::ul[1]")
        if not ul_list:
            return ""

        values = []
        li_list = ul_list[0].find_elements(By.TAG_NAME, "li")
        for li in li_list:
            txt = normalize_text(li.text)
            if txt:
                values.append(txt)

        return "\n".join(values)

    return ""


def parse_profile(driver, url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.profile-name"))
    )
    time.sleep(1)

    name = normalize_text(text_or_empty(driver, "h1.profile-name"))
    role = normalize_text(text_or_empty(driver, "p.profile-title"))
    email = normalize_text(text_or_empty(driver, ".profile-email a"))
    office = normalize_text(text_or_empty(driver, "p.profile-office span"))
    phone = normalize_text(text_or_empty(driver, ".profile-phone span"))

    area = get_h2_ul_text(driver, "Application Area(s)")
    lab_name = get_h2_ul_text(driver, "Websites")

    return {
        "Name": name,
        "Role": role,
        "Area": area,
        "Office": office,
        "Phone": phone,
        "Email": email,
        "Lab Name": lab_name,
        "Profile URL": url,
    }


def save_to_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Retry"

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
        result = []
        still_failed = []

        print(f"재처리 대상 수: {len(FAILED_URLS)}")

        for idx, url in enumerate(FAILED_URLS, 1):
            print(f"[{idx}/{len(FAILED_URLS)}] {url}")
            try:
                data = parse_profile(driver, url)
                result.append(data)
            except Exception as e:
                print(f"재처리 실패: {url} | {e}")
                still_failed.append(url)

        print()
        print("최종 실패 URL 리스트:")
        print(still_failed)

        save_to_excel(result)
        print(f"저장 완료: {OUTPUT_FILE}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()