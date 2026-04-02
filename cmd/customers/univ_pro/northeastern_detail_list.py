import re
import html
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook


SITES = [
    ("che", "https://che.northeastern.edu/faculty/faculty-directory/", "northeastern_che_faculty.xlsx"),
    ("mie", "https://mie.northeastern.edu/faculty/faculty-directory/", "northeastern_mie_faculty.xlsx"),
    ("ece", "https://ece.northeastern.edu/fac/faculty-directory/", "northeastern_ece_faculty.xlsx"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

MAX_WORKERS = 16


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def join_lines(lines):
    result = []
    seen = set()
    for x in lines:
        x = clean_text(x)
        if x and x not in seen:
            seen.add(x)
            result.append(x)
    return "\n".join(result)


def is_email(text):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean_text(text)))


def is_phone(text):
    text = clean_text(text)
    return bool(re.fullmatch(r"(?:\(?\d{3}\)?[\s.\-]*)?\d{3}[\s.\-]\d{4}(?:\s*,\s*(?:\(?\d{3}\)?[\s.\-]*)?\d{3}[\s.\-]\d{4})*", text))


def get_soup(url):
    res = requests.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def get_li_text(li):
    return clean_text(li.get_text("\n", strip=True))


def get_section_values(soup, title):
    for col in soup.select("div.faculty__col"):
        for h2 in col.select("h2.h5"):
            if clean_text(h2.get_text()) == title:
                ul = h2.find_next_sibling("ul")
                if not ul:
                    return []
                return [get_li_text(li) for li in ul.select("li")]
    return []


def parse_detail(url):
    try:
        soup = get_soup(url)
    except Exception as e:
        print(f"[상세 오류] {url} / {e}")
        return None

    name = ""
    role = ""
    area = ""
    email_list = []
    office_list = []
    phone_list = []
    lab_list = []

    intro = soup.select_one("div.faculty__intro")
    if intro:
        h1 = intro.select_one("h1.h2")
        if h1:
            name = clean_text(h1.get_text(" ", strip=True))
        p = intro.find("p")
        if p:
            role = join_lines(p.get_text("\n", strip=True).split("\n"))

    for x in get_section_values(soup, "Contact"):
        for line in x.split("\n"):
            line = clean_text(line)
            if not line:
                continue
            if is_email(line):
                email_list.append(line)
            else:
                office_list.append(line)

    for x in get_section_values(soup, "Office"):
        for line in x.split("\n"):
            line = clean_text(line)
            if not line:
                continue
            if is_phone(line):
                phone_list.append(line)
            else:
                office_list.append(line)

    for x in get_section_values(soup, "Lab"):
        for line in x.split("\n"):
            line = clean_text(line)
            if line:
                lab_list.append(line)

    for div in soup.find_all("div"):
        h2 = div.find("h2", class_="h4")
        if h2 and clean_text(h2.get_text()) == "Research Focus":
            p = div.find("p")
            if p:
                area = clean_text(p.get_text(" ", strip=True))
            break

    return {
        "Name": name,
        "Role": role,
        "Area": area,
        "Office": join_lines(office_list),
        "Phone": join_lines(phone_list),
        "Email": join_lines(email_list),
        "Lab Name": join_lines(lab_list),
        "Profile URL": url,
    }


def collect_links(start_url):
    urls = []
    seen_profile = set()
    seen_page = set()
    page_url = start_url

    while page_url and page_url not in seen_page:
        seen_page.add(page_url)
        print(f"[목록] {page_url}")

        try:
            soup = get_soup(page_url)
        except Exception as e:
            print(f"[목록 오류] {page_url} / {e}")
            break

        for a in soup.select("a.contact__name.add__decoration[href]"):
            name = clean_text(a.get_text(" ", strip=True))
            href = urljoin(page_url, a["href"])
            if href not in seen_profile:
                seen_profile.add(href)
                urls.append((name, href))

        next_url = None
        for a in soup.select("a[href]"):
            text = clean_text(a.get_text(" ", strip=True))
            if text in ("Next »", "Next", "»"):
                next_url = urljoin(page_url, a["href"])
                break

        page_url = next_url

    return urls


def save_excel(rows, filename):
    wb = Workbook()
    ws = wb.active
    ws.title = "Faculty"

    headers = ["Name", "Role", "Area", "Office", "Phone", "Email", "Lab Name", "Profile URL"]
    ws.append(headers)

    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    for col, width in {
        "A": 28, "B": 45, "C": 40, "D": 30,
        "E": 20, "F": 30, "G": 25, "H": 55
    }.items():
        ws.column_dimensions[col].width = width

    wb.save(filename)


def run_site(site_name, start_url, output_file):
    print(f"\n===== {site_name} 시작 =====")
    links = collect_links(start_url)
    print(f"[{site_name}] 링크 수: {len(links)}")

    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(parse_detail, url): (name, url) for name, url in links}

        for i, future in enumerate(as_completed(future_map), 1):
            name, url = future_map[future]
            data = future.result()
            if data:
                if not data["Name"]:
                    data["Name"] = name
                rows.append(data)
                print(f"[{site_name}] {i}/{len(links)} 완료 - {data['Name']}")

    rows.sort(key=lambda x: x["Name"].lower() if x["Name"] else "")
    save_excel(rows, output_file)
    print(f"[{site_name}] 저장 완료: {output_file}")


def main():
    for site_name, start_url, output_file in SITES:
        run_site(site_name, start_url, output_file)

    print("전체 완료")


if __name__ == "__main__":
    main()