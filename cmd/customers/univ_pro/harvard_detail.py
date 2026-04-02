import time
from typing import List, Dict

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://seas.harvard.edu"
TARGET_URL = "https://seas.harvard.edu/faculty/all-research-areas"
OUTPUT_XLSX = "harvard_people_all.xlsx"


def text_or_empty(driver: webdriver.Chrome, selector: str) -> str:
    els = driver.find_elements(By.CSS_SELECTOR, selector)
    if not els:
        return ""
    return (els[0].get_attribute("textContent") or "").strip()


def crawl_people_links(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    print(f"[1] 목록 페이지 접속: {TARGET_URL}")
    driver.get(TARGET_URL)

    print("[2] 목록 페이지 로딩 대기")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href^="/person/"]'))
    )

    time.sleep(2)

    print("[3] 사람 링크 수집")
    elements = driver.find_elements(By.CSS_SELECTOR, 'a[href^="/person/"]')
    print(f"[4] raw 링크 개수: {len(elements)}")

    people: List[Dict[str, str]] = []
    seen = set()

    for idx, el in enumerate(elements, 1):
        href = (el.get_attribute("href") or "").strip()
        name = (el.get_attribute("textContent") or "").strip()

        if not name:
            name = (el.get_attribute("innerText") or "").strip()

        if not href:
            continue

        if href.startswith("/"):
            href = BASE_URL + href

        if href in seen:
            continue

        seen.add(href)
        people.append({
            "name": name,
            "url": href
        })

        print(f"    [{idx}] {name} | {href}")

    print(f"[5] 최종 사람 수: {len(people)}")
    return people


def crawl_person_detail(driver: webdriver.Chrome, person: Dict[str, str]) -> Dict[str, str]:
    url = person.get("url", "").strip()
    if not url:
        return {}

    print(f"    상세 접속: {url}")
    driver.get(url)
    time.sleep(2)

    row = {
        "Name": text_or_empty(driver, "h1.node-title span.person__name--full"),
        "Area": text_or_empty(driver, "div.person__primary-teaching-area div.field-item"),
        "Office": text_or_empty(driver, "div.person__office div.field-item"),
        "Phone": text_or_empty(driver, "div.person__phone div.field-item"),
        "Email": text_or_empty(driver, "div.person__email div.field-item"),
        "Profile URL": url,
        "Role": text_or_empty(driver, "div.person__primary-title div.field-item"),
        "Lab Name": text_or_empty(driver, "div.person__lab-name div.field-item"),
    }

    if not row["Name"]:
        row["Name"] = person.get("name", "").strip()

    return row


def save_to_excel(rows: List[Dict[str, str]], output_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    headers = ["Name", "Area", "Office", "Phone", "Email", "Profile URL", "Role", "Lab Name"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("Name", ""),
            row.get("Area", ""),
            row.get("Office", ""),
            row.get("Phone", ""),
            row.get("Email", ""),
            row.get("Profile URL", ""),
            row.get("Role", ""),
            row.get("Lab Name", ""),
        ])

    wb.save(output_path)
    print(f"[완료] 엑셀 저장: {output_path}")


def main() -> None:
    print("[0] 크롬 옵션 설정")
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    print("[0] 크롬 실행")
    driver = webdriver.Chrome(options=options)

    try:
        people = crawl_people_links(driver)

        rows: List[Dict[str, str]] = []

        print("[6] 상세 페이지 수집 시작")
        for i, person in enumerate(people, 1):
            print(f"[{i}/{len(people)}] 처리 중")
            row = crawl_person_detail(driver, person)
            if row:
                print(row)
                rows.append(row)

        save_to_excel(rows, OUTPUT_XLSX)

    finally:
        print("[종료] 브라우저 종료")
        driver.quit()


if __name__ == "__main__":
    main()