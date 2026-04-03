import time
from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LIST_URL = "https://mse.engin.umich.edu/people"
OUTPUT_FILE = "umich_mse_people.xlsx"


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    return " ".join(text.split()).strip()


def clean_html_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    return text.strip()


def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def get_list_items(driver):
    driver.get(LIST_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".listing"))
    )
    time.sleep(2)

    listing = driver.find_element(By.CSS_SELECTOR, ".listing")
    tbodys = listing.find_elements(By.CSS_SELECTOR, "tbody")

    items = []

    for tbody in tbodys:
        trs = tbody.find_elements(By.CSS_SELECTOR, "tr")
        if len(trs) < 2:
            continue

        for tr in trs[1:]:
            try:
                name_td = tr.find_element(By.CSS_SELECTOR, "td.personName")
                a = name_td.find_element(By.TAG_NAME, "a")

                name = clean_text(a.text)
                profile_url = a.get_attribute("href")

                phone = ""
                email = ""

                tds = tr.find_elements(By.TAG_NAME, "td")
                if len(tds) >= 2:
                    phone = clean_text(tds[1].text)

                if len(tds) >= 3:
                    email_links = tds[2].find_elements(By.CSS_SELECTOR, 'a[href^="mailto:"]')
                    if email_links:
                        email = clean_text(email_links[0].text)
                    else:
                        email = clean_text(tds[2].text)

                items.append({
                    "Name": name,
                    "Phone": phone,
                    "Email": email,
                    "Profile URL": profile_url,
                })
            except:
                pass

    return items


def get_role(driver):
    try:
        el = driver.find_element(By.CSS_SELECTOR, "p.people-title")
        return clean_text(el.text)
    except:
        return ""


def get_area(driver):
    try:
        bio = driver.find_element(By.CSS_SELECTOR, "div.biography")
        ps = bio.find_elements(By.TAG_NAME, "p")
        if len(ps) >= 2:
            return clean_text(ps[1].text)
    except:
        pass

    try:
        bio = driver.find_element(By.CSS_SELECTOR, "div.biography")
        text = driver.execute_script(
            """
            const bio = arguments[0];
            const ps = bio.querySelectorAll('p');
            if (ps.length >= 2) {
                return (ps[1].innerText || ps[1].textContent || '').replace(/\\u00a0/g, ' ').trim();
            }
            return '';
            """,
            bio
        )
        return clean_text(text)
    except:
        return ""

    return ""


def get_office(driver):
    try:
        p = driver.find_element(By.CSS_SELECTOR, "p.people-address")
        span = p.find_element(By.TAG_NAME, "span")
        return clean_text(span.text)
    except:
        return ""


def parse_detail(driver, url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)

    role = get_role(driver)
    area = get_area(driver)
    office = get_office(driver)

    return role, area, office


def save_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "People"

    ws.append([
        "Name",
        "Role",
        "Phone",
        "Email",
        "Office",
        "Area",
        "Profile URL",
    ])

    for row in rows:
        ws.append(row)

    widths = {
        "A": 28,
        "B": 55,
        "C": 18,
        "D": 30,
        "E": 22,
        "F": 80,
        "G": 55,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    wb.save(OUTPUT_FILE)


def main():
    driver = get_driver()
    try:
        items = get_list_items(driver)
        print(f"목록 수집 완료: {len(items)}명")

        rows = []

        for i, item in enumerate(items, 1):
            print(f"[{i}/{len(items)}] {item['Name']}")
            try:
                role, area, office = parse_detail(driver, item["Profile URL"])
            except Exception as e:
                print(f"상세 실패: {item['Profile URL']} / {e}")
                role, area, office = "", "", ""

            rows.append([
                item["Name"],
                role,
                item["Phone"],
                item["Email"],
                office,
                area,
                item["Profile URL"],
            ])

        save_excel(rows)
        print(f"저장 완료: {OUTPUT_FILE}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()