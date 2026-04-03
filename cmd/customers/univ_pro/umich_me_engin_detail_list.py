import time
from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LIST_URL = "https://me.engin.umich.edu/people/faculty/"
OUTPUT_FILE = "umich_me_faculty.xlsx"


def clean_text(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split()).strip()


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
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".faculty-row"))
    )
    time.sleep(2)

    items = []
    rows = driver.find_elements(By.CSS_SELECTOR, ".faculty-row")
    for row in rows:
        try:
            a = row.find_element(By.CSS_SELECTOR, ".faculty-name a")
            name = clean_text(a.text)
            url = a.get_attribute("href")
            if name and url:
                items.append({"name": name, "url": url})
        except:
            pass
    return items


def get_top_container(driver):
    return driver.find_element(By.CSS_SELECTOR, "div.col.col-lg-9")


def get_name(driver):
    try:
        return clean_text(driver.find_element(By.CSS_SELECTOR, "h1.entry-title").text)
    except:
        return ""


def get_role(container):
    try:
        imgs = container.find_elements(By.CSS_SELECTOR, "img.attachment-faculty-photo")
        if imgs:
            p = imgs[0].find_element(By.XPATH, "following-sibling::*[1][self::p]")
            return clean_text(p.text)
    except:
        pass

    try:
        ps = container.find_elements(By.CSS_SELECTOR, "p")
        if ps:
            return clean_text(ps[0].text)
    except:
        pass

    return ""


def get_lab_name(container):
    try:
        address_h2 = container.find_element(By.XPATH, './/h2[normalize-space()="Address"]')
        links = address_h2.find_elements(By.XPATH, "preceding-sibling::a")
        names = []
        for a in links:
            txt = clean_text(a.text)
            if txt:
                names.append(txt)
        return "\n".join(names)
    except:
        return ""


def get_p_after_h2(container, h2_text):
    try:
        h2 = container.find_element(By.XPATH, f'.//h2[normalize-space()="{h2_text}"]')
        p = h2.find_element(By.XPATH, "following-sibling::*[1][self::p]")
        return p.text.strip()
    except:
        return ""


def get_email(container, driver):
    try:
        email_strong = container.find_element(By.XPATH, './/strong[normalize-space()="Email:"]')
        phone_strong = container.find_element(By.XPATH, './/strong[normalize-space()="Phone:"]')

        text = driver.execute_script(
            """
            const startNode = arguments[0];
            const endNode = arguments[1];
            let out = "";
            let cur = startNode.nextSibling;

            while (cur && cur !== endNode) {
                if (cur.nodeType === Node.TEXT_NODE) {
                    out += cur.textContent || "";
                } else if (cur.nodeType === Node.ELEMENT_NODE) {
                    const tag = cur.tagName.toLowerCase();
                    if (tag === "br") out += "\\n";
                    else out += cur.innerText || cur.textContent || "";
                }
                cur = cur.nextSibling;
            }
            return out;
            """,
            email_strong,
            phone_strong
        )
        return clean_text(text)
    except:
        return ""


def get_phone(container, driver):
    try:
        phone_strong = container.find_element(By.XPATH, './/strong[normalize-space()="Phone:"]')
        research_h2 = container.find_element(By.XPATH, './/h2[normalize-space()="Research Areas"]')

        text = driver.execute_script(
            """
            const startNode = arguments[0];
            const endNode = arguments[1];
            let out = "";
            let cur = startNode.nextSibling;

            while (cur && cur !== endNode) {
                if (cur.nodeType === Node.TEXT_NODE) {
                    out += cur.textContent || "";
                } else if (cur.nodeType === Node.ELEMENT_NODE) {
                    const tag = cur.tagName.toLowerCase();
                    if (tag === "br") out += "\\n";
                    else out += cur.innerText || cur.textContent || "";
                }
                cur = cur.nextSibling;
            }
            return out;
            """,
            phone_strong,
            research_h2
        )
        return clean_text(text)
    except:
        return ""


def parse_detail(driver, url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.col.col-lg-9"))
    )
    time.sleep(1)

    container = get_top_container(driver)

    name = get_name(driver)
    role = get_role(container)
    lab_name = get_lab_name(container)
    office = get_p_after_h2(container, "Address")
    email = get_email(container, driver)
    phone = get_phone(container, driver)
    area = get_p_after_h2(container, "Research Areas")
    profile_url = url

    return [
        name,
        role,
        phone,
        email,
        office,
        area,
        lab_name,
        profile_url,
    ]


def save_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Faculty"

    ws.append([
        "Name",
        "Role",
        "Phone",
        "Email",
        "Office",
        "Area",
        "Lab Name",
        "Profile URL",
    ])

    for row in rows:
        ws.append(row)

    widths = {
        "A": 25,
        "B": 45,
        "C": 18,
        "D": 28,
        "E": 40,
        "F": 45,
        "G": 30,
        "H": 55,
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
            print(f"[{i}/{len(items)}] {item['name']}")
            try:
                row = parse_detail(driver, item["url"])
                rows.append(row)
            except Exception as e:
                print(f"상세 실패: {item['url']} / {e}")
                rows.append([
                    item["name"],
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    item["url"],
                ])

        save_excel(rows)
        print(f"저장 완료: {OUTPUT_FILE}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()