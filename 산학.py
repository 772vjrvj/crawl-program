import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://rnd.dongguk.edu"
START_URL = "https://rnd.dongguk.edu/ko/page/sub/sub_0105_00.do;jsessionid=D92158A27813FF90B739371244D6603F"

EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

rows = []

html = requests.get(START_URL).text
soup = BeautifulSoup(html, "html.parser")

last_nav = soup.select(".nav-02")[-1]

menus = []

for a in last_nav.select("li a[href]"):
    text = a.get_text(strip=True)

    if text == "조직도":
        continue

    menus.append({
        "text": text,
        "url": urljoin(BASE_URL, a.get("href"))
    })

for idx, menu in enumerate(menus, start=1):
    print("[진행]", idx, "/", len(menus), menu["text"])

    html = requests.get(menu["url"]).text
    soup = BeautifulSoup(html, "html.parser")

    for tr in soup.select(".table-wrap table tbody tr"):
        tr_text = tr.get_text(" ", strip=True)
        emails = re.findall(EMAIL_RE, tr_text)

        if not emails:
            continue

        works = []

        for li in tr.select("td.left li"):
            works.append(li.get_text(" ", strip=True))

        work_text = "\n".join(works)

        for email in emails:
            rows.append({
                "대분류": "산학협력단",
                "중분류": menu["text"],
                "소분류": "행정",
                "직위": "",
                "업무": work_text,
                "이메일": email,
                "URL": menu["url"]
            })

df = pd.DataFrame(rows)
df.to_excel("동국대_산학협력단_행정.xlsx", index=False)

print("[완료]", len(rows), "건")