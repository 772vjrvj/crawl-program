from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


BASE_URL = "https://www.cs.stanford.edu"
HTML_FILE = "Stanford.html"
OUTPUT_FILE = "stanford_faculty.xlsx"

DEFAULT_OFFICE = """Gates Computer Science Building
353 Jane Stanford Way
Stanford, CA 94305
United States"""


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def clean_multiline_text(text):
    if not text:
        return ""
    lines = [line.strip().replace("\xa0", " ") for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def get_preceding_h2_text(tag):
    prev = tag.find_previous_sibling()
    while prev:
        if prev.name == "h2":
            return clean_text(prev.get_text(" ", strip=True))
        prev = prev.find_previous_sibling()
    return ""


def parse_list_html():
    file_path = Path.cwd() / HTML_FILE
    if not file_path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {file_path}")

    html = file_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    result = []
    seen = set()

    ul_list = soup.select("ul.su-list-unstyled.grid-container-3")

    for ul in ul_list:
        area = get_preceding_h2_text(ul)

        for li in ul.find_all("li", recursive=False):
            a = li.select_one('div.node.stanford-person.node-title.ds.label-hidden h3 a')
            if not a:
                continue

            name = clean_text(a.get_text(" ", strip=True))
            href = (a.get("href") or "").strip()
            if not href:
                continue

            profile_url = urljoin(BASE_URL, href)

            if profile_url in seen:
                continue
            seen.add(profile_url)

            result.append({
                "Name": name,
                "Profile URL": profile_url,
                "Area": area,
            })

    return result


def fetch_detail(session, item):
    url = item["Profile URL"]
    print(f"[DETAIL] {url}")

    try:
        res = session.get(url, timeout=30)
        res.raise_for_status()
    except Exception as e:
        print(f"상세 실패: {url} | {e}")
        item["Role"] = ""
        item["Office"] = DEFAULT_OFFICE
        item["Email"] = ""
        item["Phone"] = ""
        return item

    soup = BeautifulSoup(res.text, "html.parser")

    name_el = soup.select_one("h1#page-title")
    name = clean_text(name_el.get_text(" ", strip=True)) if name_el else item["Name"]

    role_el = soup.select_one("div.su-person-full-title.node.stanford-person.string-long.label-hidden")
    role = clean_multiline_text(role_el.get_text("\n", strip=True)) if role_el else ""

    office_el = soup.select_one(
        "div.su-person-location-address.su-wysiwyg-text.node.stanford-person.text-long.label-hidden"
    )
    office = clean_multiline_text(office_el.get_text("\n", strip=True)) if office_el else DEFAULT_OFFICE

    email_el = soup.select_one("div.su-person-email.node.stanford-person.email.label-hidden a[href^='mailto:']")
    email = clean_text(email_el.get_text(" ", strip=True)) if email_el else ""

    phone_el = soup.select_one("div.su-person-telephone.node.stanford-person.string.label-hidden")
    phone = clean_text(phone_el.get_text(" ", strip=True)) if phone_el else ""

    item["Name"] = name
    item["Role"] = role
    item["Office"] = office
    item["Email"] = email
    item["Phone"] = phone

    return item


def save_to_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Stanford Faculty"

    headers = ["Name", "Role", "Area", "Office", "Email", "Phone", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([
            row.get("Name", ""),
            row.get("Role", ""),
            row.get("Area", ""),
            row.get("Office", ""),
            row.get("Email", ""),
            row.get("Phone", ""),
            row.get("Profile URL", ""),
        ])

    wb.save(OUTPUT_FILE)
    print(f"\n엑셀 저장 완료: {OUTPUT_FILE}")


def main():
    items = parse_list_html()
    print(f"목록 수집 완료: {len(items)}건")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
    })

    results = []
    for i, item in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {item['Name']} | {item['Area']}")
        detail_item = fetch_detail(session, item)
        results.append(detail_item)

    save_to_excel(results)


if __name__ == "__main__":
    main()