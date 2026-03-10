import csv
import time
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://midomae.com"
CATEGORY_PATH = "/271/"
OUTPUT_CSV = "midomae_271_recent_list.csv"

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": "https://midomae.com/270/?idx=24473",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

COOKIE_STRING = "al=KR; _fwb=110jaNMQZPiTnwRkaotg716.1773038464433; SITE_STAT_SID=2026031069af7b10ba3315.84714732; SITE_BEGIN_SID_m2026030548f0e1733e859=2026031069af7b10ba7702.46745979; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s20260306df62975954fdc=2026031069af7b9d6b1aa5.28757230; IMWEB_REFRESH_TOKEN=d3ded79f-554c-4722-b860-78ced58490e0; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s20260303f0b4fa9db204f=2026031069af7c5e82d453.62033879; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s202603100a25fe4ff0b08=2026031069af7f751e81f9.22147723; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s2026031098906a66a5771=2026031069b003ea415fd9.48918999; IMWEBVSSID=dms40eu4ls11f0ve2snsfeoh1kgsf937iegv91c7qsjb3m50q213anqmkb4jr9r73mo9bqks95ahldq8papa3qsma5rijmdivppnrn2; ISDID=69b023638087b; ilc=cjXwjGgi%2FGToTJgkEfR8wI0FkvpE6LwOkiE%2BK0ZuZuY%3D; ial=f00ee1783fbac9e906af205cdac5bf1593f90c91e07f0c119cb57ea46ab25f0c; _imweb_login_state=Y; __bs_imweb=%7B%22deviceId%22%3A%22019cd153ee14793484733dd57391ff6b%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202512165282acc7684d6%22%2C%22unitCode%22%3A%22u20251216d69091d26aac8%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019cd80a454b7fbaa526811c6cdb6547%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMxNTIyNjgsImV4cCI6MTc3MzE1Mjg2OH0.gr_fA6u3Khi4NFfxvIuIh6dp1dvdqST-3hYYIlLMhXk%22%2C%22referrer%22%3A%22%40direct%22%2C%22initialReferrer%22%3A%22%40direct%22%2C%22initialReferrerDomain%22%3A%22%40direct%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-03-10T14%3A31%3A58.207Z%22%2C%22commonSessionId%22%3A%22sc_019cd80a454e7f1bbd4001469f19e5d9%22%2C%22commonSessionUpdatedAt%22%3A%222026-03-10T14%3A17%3A53.757Z%22%2C%22customSessionId%22%3A%22cs_019cd80a454f7665af995b76368542e8%22%2C%22customSessionUpdatedAt%22%3A%222026-03-10T14%3A17%3A53.759Z%22%2C%22browser_session_id%22%3A%22019cd80a454b7fbaa526811c6cdb6547%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMxNTIyNjgsImV4cCI6MTc3MzE1Mjg2OH0.gr_fA6u3Khi4NFfxvIuIh6dp1dvdqST-3hYYIlLMhXk%22%2C%22initial_referrer%22%3A%22%40direct%22%2C%22initial_referrer_domain%22%3A%22%40direct%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-03-10T14%3A31%3A58.207Z%22%2C%22common_session_id%22%3A%22sc_019cd80a454e7f1bbd4001469f19e5d9%22%2C%22common_session_updated_at%22%3A%222026-03-10T14%3A17%3A53.757Z%22%2C%22custom_session_id%22%3A%22cs_019cd80a454f7665af995b76368542e8%22%2C%22custom_session_updated_at%22%3A%222026-03-10T14%3A17%3A53.759Z%22%7D; _dd_s=aid=857f6956-1d72-4f12-945c-78f19aa3f563&rum=0&expire=1773154018277"


def parse_cookie_string(cookie_string: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def build_page_url(page: int) -> str:
    return f"{BASE_URL}{CATEGORY_PATH}?page={page}&sort=recent"


def fetch_page_html(session: requests.Session, page: int) -> str:
    resp = session.get(build_page_url(page), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def extract_items(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[Dict[str, str]] = []

    for card in soup.select("._fade_link.shop-item-thumb"):
        href = urljoin(BASE_URL, card["href"].strip()) if card.has_attr("href") else ""
        h2_tag = card.find("h2")
        product_name = h2_tag.get_text(" ", strip=True) if h2_tag else ""

        if href:
            rows.append(
                {
                    "product_name": product_name,
                    "href": href,
                }
            )

    return rows


def save_csv(rows: List[Dict[str, str]], csv_path: str) -> None:
    fieldnames = ["page", "no", "product_name", "href"]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def crawl_midomae_list() -> None:
    session = requests.Session()
    session.cookies.update(parse_cookie_string(COOKIE_STRING))

    all_rows: List[Dict[str, str]] = []
    page = 1
    prev_signature: List[str] = []

    while True:
        print(f"[PAGE] {page}")

        try:
            html = fetch_page_html(session, page)
            items = extract_items(html)
        except Exception as e:
            print(f"[ERROR] {e}")
            break

        if not items:
            break

        current_signature = [f'{item["product_name"]}|{item["href"]}' for item in items]

        if current_signature == prev_signature:
            print(f"[STOP] 직전 페이지와 동일: page={page}")
            break

        for item in items:
            all_rows.append(
                {
                    "page": str(page),
                    "no": str(len(all_rows) + 1),
                    "product_name": item["product_name"],
                    "href": item["href"],
                }
            )

        print(f"[OK] page={page}, count={len(items)}, total={len(all_rows)}")
        prev_signature = current_signature
        page += 1

    save_csv(all_rows, OUTPUT_CSV)
    print(f"[DONE] {OUTPUT_CSV}")


if __name__ == "__main__":
    crawl_midomae_list()