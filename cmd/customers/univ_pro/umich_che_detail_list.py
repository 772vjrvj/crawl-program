import time
from openpyxl import Workbook

from selenium import webdriver
from selenium.webdriver.common.by import By


def get_text(driver, selector):
    els = driver.find_elements(By.CSS_SELECTOR, selector)
    if els:
        return els[0].text.strip()
    return ""


def clean_lines(text):
    return [x.strip() for x in text.splitlines() if x.strip()]


def get_labeled_value(block, label_text):
    groups = block.find_elements(By.CSS_SELECTOR, "div.wp-block-group")
    target = label_text.strip().lower()

    for group in groups:
        ps = group.find_elements(By.CSS_SELECTOR, "p")
        if not ps:
            continue

        p = ps[0]
        strongs = p.find_elements(By.CSS_SELECTOR, "strong")
        if not strongs:
            continue

        label = strongs[0].text.strip()
        label_lower = label.lower()

        matched = False

        if target == "phone":
            if "phone" in label_lower:
                matched = True
        else:
            if label_lower == target:
                matched = True

        if not matched:
            continue

        links = group.find_elements(By.CSS_SELECTOR, "a")
        if links:
            return links[0].text.strip()

        full_text = p.text.strip()
        if full_text:
            if full_text.lower().startswith(label_lower):
                value = full_text[len(label):].strip()
                if value:
                    return value

            lines = clean_lines(full_text)
            if len(lines) >= 2:
                return "\n".join(lines[1:]).strip()

        if len(ps) >= 2:
            value = ps[1].text.strip()
            if value:
                return value

    return ""


def get_office(driver):
    blocks = driver.find_elements(By.CSS_SELECTOR, "div.wp-block-columns")

    for block in blocks:
        groups = block.find_elements(By.CSS_SELECTOR, "div.wp-block-group")

        for group in groups:
            ps = group.find_elements(By.CSS_SELECTOR, "p")
            if not ps:
                continue

            p = ps[0]
            strongs = p.find_elements(By.CSS_SELECTOR, "strong")
            if not strongs:
                continue

            label = strongs[0].text.strip().lower()
            if label != "location":
                continue

            full_text = p.text.strip()
            if full_text.startswith(strongs[0].text.strip()):
                value = full_text[len(strongs[0].text.strip()):].strip()
                if value:
                    return value

            lines = clean_lines(full_text)
            if len(lines) >= 2:
                return "\n".join(lines[1:]).strip()

            if len(ps) >= 2:
                value = ps[1].text.strip()
                if value:
                    return value

    return ""


def get_area(driver):
    items = driver.find_elements(By.CSS_SELECTOR, "div.wp-block-pb-accordion-item")

    for item in items:
        titles = item.find_elements(By.CSS_SELECTOR, "h3.c-accordion__title")
        if not titles:
            continue

        title = titles[0].text.strip().lower()
        if title != "research interests":
            continue

        contents = item.find_elements(By.CSS_SELECTOR, "div.c-accordion__content")
        if not contents:
            continue

        text = contents[0].get_attribute("textContent") or ""
        lines = clean_lines(text)
        return "\n".join(lines)

    return ""


def collect_profile_links(driver):
    all_links = []
    seen = set()
    page = 1

    while True:
        url = f"https://che.engin.umich.edu/role/core-faculty/?query-19-page={page}"
        print(f"[LIST] {url}")
        driver.get(url)
        time.sleep(2)

        elements = driver.find_elements(By.CSS_SELECTOR, "h2.wp-block-post-title a")
        if not elements:
            print(f"[END] page {page} 에서 목록 없음")
            break

        new_count = 0

        for el in elements:
            href = el.get_attribute("href")
            if href and href not in seen:
                seen.add(href)
                all_links.append(href)
                new_count += 1
                print(href)

        if new_count == 0:
            print(f"[END] page {page} 에서 신규 링크 없음")
            break

        page += 1

    return all_links


def crawl_detail(driver, url):
    print(f"[DETAIL] {url}")
    driver.get(url)
    time.sleep(2)

    name = get_text(driver, "h1.wp-block-post-title")
    role = get_text(driver, "div.is-meta-field .value")

    email = ""
    phone = ""

    blocks = driver.find_elements(By.CSS_SELECTOR, "div.wp-block-columns")
    for block in blocks:
        if not email:
            email = get_labeled_value(block, "email")
        if not phone:
            phone = get_labeled_value(block, "phone")

    office = get_office(driver)
    area = get_area(driver)

    print(f"[PHONE] {phone}")
    print(f"[AREA] {area}")

    return {
        "Name": name,
        "Role": role,
        "Email": email,
        "Phone": phone,
        "Office": office,
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
        profile_links = collect_profile_links(driver)
        print(f"[TOTAL LINKS] {len(profile_links)}")

        results = []

        for i, url in enumerate(profile_links, 1):
            print(f"[{i}/{len(profile_links)}]")
            try:
                row = crawl_detail(driver, url)
                results.append(row)
            except Exception as e:
                print(f"[ERROR] {url} -> {e}")

        save_excel(results, "umich_che_core_faculty.xlsx")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()