import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


BASE_URL = "https://www.bu.edu"
LIST_URL = "https://www.bu.edu/eng/academics/departments-and-divisions/electrical-and-computer-engineering/people/?num={page}"
OUTPUT_FILE = "bu_ece_people.xlsx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split()).strip()


def get_soup(session, url):
    res = session.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def parse_area_from_meta(soup):
    meta = soup.select_one("div.profile-meta")
    if not meta:
        return ""

    for p in meta.select("p"):
        strong = p.find("strong")
        if not strong:
            continue

        label = clean_text(strong.get_text(" ", strip=True)).rstrip(":")
        if label == "Departments or Divisions":
            text = clean_text(p.get_text(" ", strip=True))
            text = text.replace("Departments or Divisions:", "").strip()
            text = text.replace("&", "")
            text = clean_text(text)
            return text

    return ""


def parse_area(soup):
    # 1순위: Departments or Divisions
    area = parse_area_from_meta(soup)
    if area:
        return area

    # 2순위: Primary Appointment
    primary = soup.select_one("li.profile-details-item.profile-details-primary-appointment")
    if primary:
        label = primary.select_one("span.label.profile-details-label")
        if label:
            label.extract()
        return clean_text(primary.get_text(" ", strip=True))

    return ""


def parse_contact(soup):
    office = ""
    email = ""
    phone = ""

    ul = soup.select_one("ul.profile-details-contact")
    if not ul:
        return office, email, phone

    for li in ul.select("li.profile-details-item"):
        classes = li.get("class", [])

        if "profile-details-office" in classes:
            label = li.select_one("span.label.profile-details-label")
            if label:
                label.extract()
            office = clean_text(li.get_text(" ", strip=True))

        elif "profile-details-email" in classes:
            a = li.select_one('a[href^="mailto:"]')
            if a:
                email = clean_text(a.get_text(" ", strip=True))
            else:
                label = li.select_one("span.label.profile-details-label")
                if label:
                    label.extract()
                email = clean_text(li.get_text(" ", strip=True))

        elif "profile-details-phone" in classes:
            label = li.select_one("span.label.profile-details-label")
            if label:
                label.extract()
            phone = clean_text(li.get_text(" ", strip=True))

    return office, email, phone


def collect_profile_links(session):
    links = []
    seen = set()
    page = 1

    while True:
        url = LIST_URL.format(page=page)
        print(f"[LIST] {url}")

        soup = get_soup(session, url)
        items = soup.select("h4.bu-filtering-result-item-title a")

        if not items:
            print(f"[END] page={page} 에서 목록 없음")
            break

        added = 0
        for a in items:
            href = (a.get("href") or "").strip()
            if not href:
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in seen:
                continue

            seen.add(full_url)
            links.append(full_url)
            added += 1

        print(f"[PAGE {page}] added={added}, total={len(links)}")
        page += 1
        time.sleep(0.3)

    return links


def parse_profile(session, url):
    print(f"[DETAIL] {url}")
    soup = get_soup(session, url)

    name_el = soup.select_one("h1.page-title")
    role_el = soup.select_one("h2.profile-single-title")

    name = clean_text(name_el.get_text(" ", strip=True)) if name_el else ""
    role = clean_text(role_el.get_text(" ", strip=True)) if role_el else ""

    office, email, phone = parse_contact(soup)
    area = parse_area(soup)

    return {
        "Name": name,
        "Role": role,
        "Area": area,
        "Office": office,
        "Email": email,
        "Phone": phone,
        "Lab Name": "",
        "Profile URL": url,
    }


def save_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "BU ECE"

    headers = ["Name", "Role", "Area", "Office", "Email", "Phone", "Lab Name", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    wb.save(OUTPUT_FILE)
    print(f"[SAVE] {OUTPUT_FILE}")


def main():
    session = requests.Session()

    profile_links = collect_profile_links(session)
    print(f"[TOTAL LINKS] {len(profile_links)}")

    rows = []
    for i, url in enumerate(profile_links, 1):
        try:
            row = parse_profile(session, url)
            rows.append(row)
            print(f"[{i}/{len(profile_links)}] {row['Name']}")
        except Exception as e:
            print(f"[ERROR] {url} -> {e}")

        time.sleep(0.3)

    save_excel(rows)


if __name__ == "__main__":
    main()