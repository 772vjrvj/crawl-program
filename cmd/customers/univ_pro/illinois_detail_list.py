import time
from urllib.parse import urljoin

from openpyxl import Workbook
from selenium import webdriver
from selenium.webdriver.common.by import By


SITES = [
    {
        "name": "cs",
        "list_url": "https://siebelschool.illinois.edu/about/people/all-faculty",
        "base_url": "https://siebelschool.illinois.edu",
        "output": "illinois_cs_faculty.xlsx",
    },
    {
        "name": "matse",
        "list_url": "https://matse.illinois.edu/people/faculty",
        "base_url": "https://matse.illinois.edu",
        "output": "illinois_matse_faculty.xlsx",
    },
    {
        "name": "mechse",
        "list_url": "https://mechse.illinois.edu/people/faculty",
        "base_url": "https://mechse.illinois.edu",
        "output": "illinois_mechse_faculty.xlsx",
    },
    {
        "name": "chbe",
        "list_url": "https://chbe.illinois.edu/people/faculty",
        "base_url": "https://chbe.illinois.edu",
        "output": "illinois_chbe_faculty.xlsx",
    },
]


def text_or_empty(parent, selector):
    els = parent.find_elements(By.CSS_SELECTOR, selector)
    if not els:
        return ""
    return (els[0].get_attribute("textContent") or "").strip()


def get_profile_urls(driver, list_url, base_url):
    print(f"[목록] 접속: {list_url}")
    driver.get(list_url)
    time.sleep(2)

    items = driver.find_elements(By.CSS_SELECTOR, ".directory-list.directory-list-4 .item.person")
    print(f"[목록] item.person 개수: {len(items)}")

    urls = []

    for i, item in enumerate(items, 1):
        links = item.find_elements(By.CSS_SELECTOR, ".name a")
        if not links:
            continue

        href = (links[0].get_attribute("href") or "").strip()
        if not href:
            continue

        full_url = urljoin(base_url, href)
        urls.append(full_url)
        print(f"[목록] {i}/{len(items)} -> {full_url}")

    return urls


def get_lab_name(root):
    h2_list = root.find_elements(By.XPATH, './/h2[normalize-space()="For More Information"]')
    if not h2_list:
        return ""

    h2 = h2_list[0]
    li_list = h2.find_elements(By.XPATH, './following-sibling::ul[1]/li')
    if not li_list:
        return ""

    texts = []
    for li in li_list:
        text = (li.get_attribute("textContent") or "").strip()
        if text:
            texts.append(text)

    return "\n".join(texts)


def parse_profile(driver, profile_url):
    print(f"[상세] 접속: {profile_url}")
    driver.get(profile_url)
    time.sleep(2)

    root_list = driver.find_elements(By.CSS_SELECTOR, ".directory-profile.maxwidth800")
    root = root_list[0] if root_list else driver

    row = {
        "Name": text_or_empty(root, ".roles h1"),
        "Role": text_or_empty(root, ".roles .role .title"),
        "Phone": text_or_empty(root, ".roles .role .phone"),
        "Email": text_or_empty(root, ".roles .role .email"),
        "Office": text_or_empty(root, ".roles .role .office"),
        "Lab Name": get_lab_name(root),
        "Profile URL": profile_url,
    }

    print(f"[상세] 결과: {row}")
    return row


def save_excel(rows, output_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    headers = ["Name", "Role", "Phone", "Email", "Office", "Lab Name", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("Name", ""),
            row.get("Role", ""),
            row.get("Phone", ""),
            row.get("Email", ""),
            row.get("Office", ""),
            row.get("Lab Name", ""),
            row.get("Profile URL", ""),
        ])

    wb.save(output_path)
    print(f"[저장 완료] {output_path}")


def run_site(driver, site):
    print("=" * 80)
    print(f"[시작] {site['name']}")

    profile_urls = get_profile_urls(
        driver=driver,
        list_url=site["list_url"],
        base_url=site["base_url"],
    )

    rows = []

    for i, profile_url in enumerate(profile_urls, 1):
        print(f"[진행] {site['name']} {i}/{len(profile_urls)}")
        try:
            row = parse_profile(driver, profile_url)
            rows.append(row)
        except Exception as e:
            print(f"[에러] {profile_url} -> {e}")

    save_excel(rows, site["output"])
    print(f"[완료] {site['name']}")


def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)

    try:
        for site in SITES:
            run_site(driver, site)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()