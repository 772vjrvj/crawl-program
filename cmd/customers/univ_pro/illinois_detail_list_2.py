import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://chbe.illinois.edu"
LIST_URL = "https://chbe.illinois.edu/people/faculty"
OUTPUT_FILE = "illinois_chbe_faculty.xlsx"


def clean_text(text):
    return " ".join(text.replace("\xa0", " ").split()).strip()


def text_or_empty(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if not els:
        return ""
    return clean_text(els[0].text)


def texts_join(parent, selector, sep="\n"):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    arr = []
    for el in els:
        t = clean_text(el.text)
        if t:
            arr.append(t)
    return sep.join(arr)


def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # 필요하면 아래 주석 해제
    # options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def collect_list(driver):
    result = []

    driver.get(LIST_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".item.person"))
    )

    items = driver.find_elements(By.CSS_SELECTOR, ".item.person")
    print(f"[목록] item person 개수: {len(items)}")

    for item in items:
        a_tags = item.find_elements(By.CSS_SELECTOR, ".name a")
        if not a_tags:
            continue

        a = a_tags[0]
        name = clean_text(a.text)
        profile_url = urljoin(BASE_URL, a.get_attribute("href"))

        data = {
            "Name": name,
            "Profile URL": profile_url,
        }
        result.append(data)

        print(f"Name: {name} | Profile URL: {profile_url}")

    return result


def parse_detail(driver, url):
    row = {
        "Name": "",
        "Role": "",
        "Phone": "",
        "Email": "",
        "Office": "",
        "Area": "",
        "Lab Name": "",
        "Profile URL": url,
    }

    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".roles"))
    )

    roles = driver.find_element(By.CSS_SELECTOR, ".roles")

    row["Name"] = text_or_empty(roles, "h1")
    row["Role"] = texts_join(roles, ".role .title li")
    row["Phone"] = text_or_empty(roles, ".role .phone")
    row["Email"] = text_or_empty(roles, ".role .email")
    row["Office"] = text_or_empty(roles, ".role .office")
    row["Area"] = text_or_empty(roles, ".role .bio")

    h2_list = driver.find_elements(By.CSS_SELECTOR, "h2")
    for h2 in h2_list:
        title = clean_text(h2.text)
        if title == "For More Information":
            ul_list = h2.find_elements(By.XPATH, "./following-sibling::ul[1]")
            if ul_list:
                li_texts = []
                for li in ul_list[0].find_elements(By.CSS_SELECTOR, "li"):
                    t = clean_text(li.text)
                    if t:
                        li_texts.append(t)
                row["Lab Name"] = "\n".join(li_texts)
            break

    return row


def save_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "faculty"

    headers = [
        "Name",
        "Role",
        "Phone",
        "Email",
        "Office",
        "Area",
        "Lab Name",
        "Profile URL",
    ]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("Name", ""),
            row.get("Role", ""),
            row.get("Phone", ""),
            row.get("Email", ""),
            row.get("Office", ""),
            row.get("Area", ""),
            row.get("Lab Name", ""),
            row.get("Profile URL", ""),
        ])

    wb.save(OUTPUT_FILE)
    print(f"[완료] 엑셀 저장: {OUTPUT_FILE}")


def main():
    driver = get_driver()

    try:
        faculty_list = collect_list(driver)

        result = []
        total = len(faculty_list)

        for idx, item in enumerate(faculty_list, 1):
            print(f"[상세] {idx}/{total} {item['Profile URL']}")
            try:
                row = parse_detail(driver, item["Profile URL"])
                if not row["Name"]:
                    row["Name"] = item["Name"]
                result.append(row)
            except Exception as e:
                print(f"[상세 실패] {item['Profile URL']} | {e}")
                result.append({
                    "Name": item["Name"],
                    "Role": "",
                    "Phone": "",
                    "Email": "",
                    "Office": "",
                    "Area": "",
                    "Lab Name": "",
                    "Profile URL": item["Profile URL"],
                })

            time.sleep(1)

        save_excel(result)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()