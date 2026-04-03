import time
from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


SITES = [
    {
        "name": "umich_ece_faculty",
        "url": "https://ece.engin.umich.edu/people/directory/faculty/",
        "output": "umich_ece_faculty.xlsx",
    },
    {
        "name": "umich_cse_faculty",
        "url": "https://cse.engin.umich.edu/people/faculty/",
        "output": "umich_cse_faculty.xlsx",
    },
]


HEADERS = [
    "Name",
    "Role",
    "Phone",
    "Email",
    "Office",
    "Area",
    "Lab Name",
    "Profile URL",
]


def clean_text(text: str) -> str:
    return " ".join((text or "").replace("\n", " ").replace("\t", " ").split()).strip()


def after_prefix(text: str, prefix: str) -> str:
    text = clean_text(text)
    if text.startswith(prefix):
        return clean_text(text[len(prefix):])
    return text


def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def parse_person(card, page_url):
    name = ""
    role = ""
    phone = ""
    email = ""
    office = ""
    area = ""
    lab_name = ""
    profile_url = page_url

    name_els = card.find_elements(By.CSS_SELECTOR, "p.eecs_person_name")
    if name_els:
        name = clean_text(name_els[0].text)

    role_els = card.find_elements(By.CSS_SELECTOR, "span.person_title_section")
    if role_els:
        role = clean_text(role_els[0].text)

    area_els = card.find_elements(By.CSS_SELECTOR, "span.person_copy_section.pcs_tall")
    if area_els:
        area = after_prefix(area_els[0].text, "Research Interests:")

    email_els = card.find_elements(By.CSS_SELECTOR, "a.person_email")
    if email_els:
        email = clean_text(email_els[-1].text)

    copy_sections = card.find_elements(By.CSS_SELECTOR, "span.person_copy_section")
    for sec in copy_sections:
        txt = clean_text(sec.text)
        if txt.startswith("Phone:"):
            phone = after_prefix(txt, "Phone:")
        elif txt.startswith("Office:"):
            office = after_prefix(txt, "Office:")

    return [name, role, phone, email, office, area, lab_name, profile_url]


def crawl_site(driver, site):
    url = site["url"]
    output = site["output"]

    print(f"[접속] {url}")
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".eecs_person_wrapper"))
    )
    time.sleep(2)

    cards = driver.find_elements(By.CSS_SELECTOR, ".eecs_person_wrapper")
    print(f"[목록 수집] {len(cards)}명")

    rows = []
    for i, card in enumerate(cards, 1):
        try:
            row = parse_person(card, url)
            rows.append(row)
            print(f"[{i}/{len(cards)}] {row[0]}")
        except Exception as e:
            print(f"[오류] {i}번째 카드 실패: {e}")

    wb = Workbook()
    ws = wb.active
    ws.title = "Faculty"
    ws.append(HEADERS)

    for row in rows:
        ws.append(row)

    for col in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        ws.column_dimensions[col].width = 25

    wb.save(output)
    print(f"[저장 완료] {output}")


def main():
    driver = get_driver()
    try:
        for site in SITES:
            crawl_site(driver, site)
    finally:
        driver.quit()
        print("[종료]")


if __name__ == "__main__":
    main()