import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


URL = "https://central.childcare.go.kr/ccef/job/JobOfferSlPL.jsp"
OUTPUT_JSON = "childcare_job_offer_list.json"

HEADLESS = False
SLEEP_SEC = 0.8
STEP = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

BASE_PAYLOAD: Dict[str, str] = {
    "flag": "SlPL",
    "JOSEQ": "",
    "total": "",
    "offset": "0",
    "limit": "",
    "returnUrl": "",
    "schCrType": "",
    "ctprvn": "",
    "signgu": "",
    "dong": "",
    "crspec": "",
    "crpub": "",
    "schEmpGbCode": "",
    "crcert": "",
    "endYn": "N",
    "schCrName": "",
}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def extract_joseq(onclick_text: str) -> str:
    if not onclick_text:
        return ""
    m = re.search(r"fnGoBoardSl\('(\d+)'\)", onclick_text)
    return m.group(1) if m else ""


def parse_rows(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.select_one(".com_list1 table tbody")
    if not tbody:
        return []

    rows: List[Dict[str, str]] = []

    for tr in tbody.find_all("tr", recursive=False):
        td_list = tr.find_all("td", recursive=False)
        if len(td_list) < 9:
            continue

        title_a = td_list[2].find("a")
        nursery_a = td_list[3].find("a")

        title = clean_text(
            title_a.get_text(" ", strip=True) if title_a else td_list[2].get_text(" ", strip=True)
        )
        nursery_name = clean_text(
            nursery_a.get_text(" ", strip=True) if nursery_a else td_list[3].get_text(" ", strip=True)
        )

        onclick_text = ""
        if nursery_a:
            onclick_text = nursery_a.get("onclick", "") or ""
        elif title_a:
            onclick_text = title_a.get("onclick", "") or ""

        joseq = extract_joseq(onclick_text)

        item = {
            "번호": clean_text(td_list[0].get_text(" ", strip=True)),
            "유형": clean_text(td_list[1].get_text(" ", strip=True)),
            "제목": title,
            "어린이집명": nursery_name,
            "JOSEQ": joseq,
            "직종": clean_text(td_list[4].get_text(" ", strip=True)),
            "소재지": clean_text(td_list[5].get_text(" ", strip=True)),
            "마감일": clean_text(td_list[6].get_text(" ", strip=True)),
            "작성일": clean_text(td_list[7].get_text(" ", strip=True)),
            "조회": clean_text(td_list[8].get_text(" ", strip=True)),
        }
        rows.append(item)

    return rows


def browser_fetch_list_html(page, offset: int) -> str:
    payload = dict(BASE_PAYLOAD)
    payload["offset"] = str(offset)

    js_code = """
    async ({ url, payload }) => {
        const form = new URLSearchParams();
        for (const [k, v] of Object.entries(payload)) {
            form.append(k, v ?? "");
        }

        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache"
            },
            body: form.toString(),
            credentials: "include"
        });

        return await res.text();
    }
    """

    return page.evaluate(js_code, {"url": URL, "payload": payload})


def save_json(data: List[Dict[str, str]], output_path: str) -> None:
    Path(output_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[INFO] 저장 완료: {output_path} / 총 {len(data)}건")


def crawl_all() -> List[Dict[str, str]]:
    all_items: List[Dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-dev-shm-usage",
            ],
        )

        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="ko-KR",
            viewport={"width": 1400, "height": 1000},
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        offset = 0

        while True:
            print(f"[INFO] offset={offset} 요청 중...")
            html = browser_fetch_list_html(page, offset)
            rows = parse_rows(html)

            if not rows:
                print(f"[INFO] offset={offset} 데이터 없음. 종료")
                break

            print(f"[INFO] offset={offset} -> {len(rows)}건 수집")
            all_items.extend(rows)

            if len(rows) < STEP:
                print("[INFO] 마지막 페이지로 판단. 종료")
                break

            offset += STEP
            time.sleep(SLEEP_SEC)

        browser.close()

    return all_items


if __name__ == "__main__":
    result = crawl_all()
    save_json(result, OUTPUT_JSON)