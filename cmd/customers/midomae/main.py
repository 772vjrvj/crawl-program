import csv
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://midomae.com"
INPUT_CSV = "midomae_270_recent.csv"
OUTPUT_CSV = "midomae_270_recent_detail.csv"

IMAGE_DIR = "midomae_images"
HTML_DIR = "midomae_html"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def sanitize_filename(name: str, max_length: int = 150) -> str:
    if not name:
        return "no_name"

    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(".")

    if not name:
        name = "no_name"

    return name[:max_length]


def read_csv_rows(csv_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    return rows


def write_csv_rows(csv_path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def extract_prod_idx(row: Dict[str, Any]) -> str:
    """
    href 또는 url 에서 idx / prod_idx 추출
    예:
      /270/?idx=21926
      https://midomae.com/270/?idx=21926
      https://midomae.com/ajax/oms/OMS_get_product.cm?prod_idx=21926
    """
    candidates = [
        (row.get("href") or "").strip(),
        (row.get("url") or "").strip(),
    ]

    for value in candidates:
        if not value:
            continue

        parsed = urlparse(value)
        query = parse_qs(parsed.query)

        if query.get("idx"):
            return str(query["idx"][0]).strip()

        if query.get("prod_idx"):
            return str(query["prod_idx"][0]).strip()

        m = re.search(r"(?:idx|prod_idx)=(\d+)", value)
        if m:
            return m.group(1)

    return ""


def build_detail_page_headers(cookie_str: str = "") -> Dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "cookie": cookie_str or "",
    }


def build_ajax_headers(cookie_str: str = "", referer: str = "") -> Dict[str, str]:
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": referer,
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": cookie_str or "",
    }


def build_image_headers(cookie_str: str = "", referer: str = "") -> Dict[str, str]:
    return {
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": referer,
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "image",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "cookie": cookie_str or "",
    }


def fetch_detail_page_html(session: requests.Session, detail_url: str, cookie_str: str = "") -> str:
    headers = build_detail_page_headers(cookie_str=cookie_str)
    response = session.get(detail_url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_thumbnail_url_from_detail_page(detail_html: str, detail_url: str) -> str:
    soup = BeautifulSoup(detail_html, "html.parser")

    main_image = soup.select_one("img#main-image")
    if not main_image:
        return ""

    src = (main_image.get("src") or "").strip()
    if not src:
        return ""

    return urljoin(detail_url, src)


def fetch_ajax_product_data(
        session: requests.Session,
        prod_idx: str,
        cookie_str: str = "",
        referer: str = "",
) -> Dict[str, str]:
    ajax_url = f"{BASE_URL}/ajax/oms/OMS_get_product.cm?prod_idx={prod_idx}"
    headers = build_ajax_headers(cookie_str=cookie_str, referer=referer)

    response = session.get(ajax_url, headers=headers, timeout=30)
    response.raise_for_status()

    payload = response.json()

    if str(payload.get("msg", "")).upper() != "SUCCESS":
        raise ValueError(f"AJAX 응답 실패: {payload}")

    data_obj = payload.get("data") or {}

    # 혹시라도 list로 오는 경우까지 방어
    if isinstance(data_obj, list):
        data_obj = data_obj[0] if data_obj else {}

    if not isinstance(data_obj, dict):
        data_obj = {}

    product_name = str(data_obj.get("name") or "").strip()
    detail_html = str(data_obj.get("content") or "")

    # 사용자가 말한 대로 \" -> " 치환
    detail_html = detail_html.replace('\\"', '"')

    return {
        "product_name": product_name,
        "detail_html": detail_html,
        "ajax_url": ajax_url,
    }

def guess_extension_from_url_or_type(url: str, content_type: str = "") -> str:
    lower_type = (content_type or "").lower()

    if "jpeg" in lower_type or "jpg" in lower_type:
        return ".jpg"
    if "png" in lower_type:
        return ".png"
    if "webp" in lower_type:
        return ".webp"
    if "gif" in lower_type:
        return ".gif"
    if "bmp" in lower_type:
        return ".bmp"
    if "svg" in lower_type:
        return ".svg"

    parsed = urlparse(url)
    path = parsed.path.lower()

    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"]:
        if path.endswith(ext):
            return ext

    return ".jpg"


def save_html_file(product_name: str, detail_html: str, html_dir: str) -> str:
    ensure_dir(html_dir)

    safe_name = sanitize_filename(product_name or "no_name")
    html_path = os.path.join(html_dir, f"{safe_name}.html")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(detail_html or "")

    return html_path


def download_thumbnail_image(
        session: requests.Session,
        image_url: str,
        product_name: str,
        image_dir: str,
        cookie_str: str = "",
        referer: str = "",
) -> str:
    ensure_dir(image_dir)

    headers = build_image_headers(cookie_str=cookie_str, referer=referer)
    response = session.get(image_url, headers=headers, timeout=30, stream=True)
    response.raise_for_status()

    ext = guess_extension_from_url_or_type(
        url=image_url,
        content_type=response.headers.get("Content-Type", ""),
    )

    safe_name = sanitize_filename(product_name or "no_name")
    image_path = os.path.join(image_dir, f"{safe_name}{ext}")

    with open(image_path, "wb") as f:
        for chunk in response.iter_content(8192):
            if chunk:
                f.write(chunk)

    return image_path


def process_rows(
        input_csv: str,
        output_csv: str,
        cookie_str: str = "",
        sleep_sec: float = 0.5,
) -> None:
    ensure_dir(IMAGE_DIR)
    ensure_dir(HTML_DIR)

    rows = read_csv_rows(input_csv)
    session = requests.Session()

    result_rows: List[Dict[str, Any]] = []
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        new_row = dict(row)

        detail_url = (row.get("url") or "").strip()
        prod_idx = extract_prod_idx(row)

        if not detail_url or not prod_idx:
            new_row["prod_idx"] = prod_idx
            new_row["product_name"] = ""
            new_row["thumbnail_url"] = ""
            new_row["image_path"] = ""
            new_row["detail_html_path"] = ""
            result_rows.append(new_row)
            print(f"[{idx}/{total}] url 또는 prod_idx 없음 -> skip")
            continue

        try:
            # 1) 상세페이지에서 썸네일 추출
            detail_page_html = fetch_detail_page_html(
                session=session,
                detail_url=detail_url,
                cookie_str=cookie_str,
            )
            thumbnail_url = parse_thumbnail_url_from_detail_page(
                detail_html=detail_page_html,
                detail_url=detail_url,
            )

            # 2) AJAX에서 상품명 / 상세 HTML 추출
            ajax_data = fetch_ajax_product_data(
                session=session,
                prod_idx=prod_idx,
                cookie_str=cookie_str,
                referer=detail_url,
            )
            product_name = ajax_data.get("product_name", "") or ""
            detail_html = ajax_data.get("detail_html", "") or ""

            image_path = ""
            detail_html_path = ""

            if product_name and detail_html:
                detail_html_path = save_html_file(
                    product_name=product_name,
                    detail_html=detail_html,
                    html_dir=HTML_DIR,
                )

            if product_name and thumbnail_url:
                image_path = download_thumbnail_image(
                    session=session,
                    image_url=thumbnail_url,
                    product_name=product_name,
                    image_dir=IMAGE_DIR,
                    cookie_str=cookie_str,
                    referer=detail_url,
                )

            new_row["prod_idx"] = prod_idx
            new_row["product_name"] = product_name
            new_row["thumbnail_url"] = thumbnail_url
            new_row["image_path"] = image_path
            new_row["detail_html_path"] = detail_html_path

            result_rows.append(new_row)

            print(
                f"[{idx}/{total}] 완료 | "
                f"prod_idx={prod_idx} | "
                f"product_name={product_name} | "
                f"thumb={'Y' if image_path else 'N'} | "
                f"html={'Y' if detail_html_path else 'N'}"
            )

        except Exception as e:
            new_row["prod_idx"] = prod_idx
            new_row["product_name"] = ""
            new_row["thumbnail_url"] = ""
            new_row["image_path"] = ""
            new_row["detail_html_path"] = ""
            result_rows.append(new_row)

            print(f"[{idx}/{total}] ERROR | url={detail_url} | {e}")

        time.sleep(sleep_sec)

    write_csv_rows(output_csv, result_rows)
    print(f"[DONE] 저장 완료: {output_csv}")


def main() -> None:
    # 여기에 실제 cookie 문자열 넣으시면 됩니다.
    COOKIE = "al=KR; _fwb=110jaNMQZPiTnwRkaotg716.1773038464433; SITE_STAT_SID=2026031069af7b10ba3315.84714732; SITE_BEGIN_SID_m2026030548f0e1733e859=2026031069af7b10ba7702.46745979; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s20260306df62975954fdc=2026031069af7b9d6b1aa5.28757230; IMWEB_REFRESH_TOKEN=d3ded79f-554c-4722-b860-78ced58490e0; IMWEBVSSID=jf6b54itsdjuiaspcsv32nisdfsv032sst7sqtbnl9e8sbpa9dl98ilboatr0qv1934bd02blfucakvkus76r0dt9d0am0gm08j28r3; ISDID=69af7befd8263; ilc=cjXwjGgi%2FGToTJgkEfR8wI0FkvpE6LwOkiE%2BK0ZuZuY%3D; ial=afc339a15a4f49535d7b768adaccbd23f2798568822b3503f2a68e8aeddb156d; _imweb_login_state=Y; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s20260303f0b4fa9db204f=2026031069af7c5e82d453.62033879; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s202603100a25fe4ff0b08=2026031069af7f751e81f9.22147723; IMWEB_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJob3N0IjoibWlkb21hZS5jb20iLCJzaXRlQ29kZSI6IlMyMDI1MTIxNjUyODJhY2M3Njg0ZDYiLCJ1bml0Q29kZSI6InUyMDI1MTIxNmQ2OTA5MWQyNmFhYzgiLCJtZW1iZXJDb2RlIjoibTIwMjYwMzA1NDhmMGUxNzMzZTg1OSIsInJvbGUiOiJtZW1iZXIiLCJpYXQiOjE3NzMxMTA4OTMsImV4cCI6MTc3MzExMTE5MywiaXNzIjoiaW13ZWItY29yZS1hdXRoLXNpdGUifQ.zeHkbx1T4fMg-3EX6mgdm7XjkADCNay508_aqzZ8bL8; __bs_imweb=%7B%22deviceId%22%3A%22019cd153ee14793484733dd57391ff6b%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202512165282acc7684d6%22%2C%22unitCode%22%3A%22u20251216d69091d26aac8%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019cd57dd16378a88d1c3247d33cf1ce%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMxMTA5MjQsImV4cCI6MTc3MzExMTUyNH0.T9HnRdsc3BGIPK_QZYgpyvYf8YS85waeA35ZP0Ye060%22%2C%22referrer%22%3A%22%40direct%22%2C%22initialReferrer%22%3A%22%40direct%22%2C%22initialReferrerDomain%22%3A%22%40direct%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-03-10T02%3A48%3A45.718Z%22%2C%22commonSessionId%22%3A%22sc_019cd57dd1867670a40fe506f3df8686%22%2C%22commonSessionUpdatedAt%22%3A%222026-03-10T02%3A48%3A45.745Z%22%2C%22customSessionId%22%3A%22cs_019cd57dd1877d70a48996a1a156e951%22%2C%22customSessionUpdatedAt%22%3A%222026-03-10T02%3A48%3A45.746Z%22%2C%22browser_session_id%22%3A%22019cd57dd16378a88d1c3247d33cf1ce%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMxMTA5MjQsImV4cCI6MTc3MzExMTUyNH0.T9HnRdsc3BGIPK_QZYgpyvYf8YS85waeA35ZP0Ye060%22%2C%22initial_referrer%22%3A%22%40direct%22%2C%22initial_referrer_domain%22%3A%22%40direct%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-03-10T02%3A48%3A45.718Z%22%2C%22common_session_id%22%3A%22sc_019cd57dd1867670a40fe506f3df8686%22%2C%22common_session_updated_at%22%3A%222026-03-10T02%3A33%3A35.736Z%22%2C%22custom_session_id%22%3A%22cs_019cd57dd1877d70a48996a1a156e951%22%2C%22custom_session_updated_at%22%3A%222026-03-10T02%3A33%3A35.737Z%22%7D; alarm_cnt_member=1; _dd_s=aid=857f6956-1d72-4f12-945c-78f19aa3f563&rum=0&expire=1773111994823"

    process_rows(
        input_csv=INPUT_CSV,
        output_csv=OUTPUT_CSV,
        cookie_str=COOKIE,
        sleep_sec=0.5,
    )


if __name__ == "__main__":
    main()