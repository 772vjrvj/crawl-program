import csv
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://midomae.com"

# 사이트 카테고리 코드
CATEGORY_CODE = "166"

# 상품 이미지 저장용 카테고리
PRODUCT_CATEGORY = "kidsclothing"

INPUT_CSV = f"midomae_{CATEGORY_CODE}_recent_list.csv"
DETAIL_OUTPUT_CSV = f"midomae_{CATEGORY_CODE}_recent_detail.csv"
OPTION_OUTPUT_CSV = f"midomae_{CATEGORY_CODE}_option.csv"

IMAGE_PATH_PREFIX = f"lucidshop/{PRODUCT_CATEGORY}"
IMAGE_SAVE_DIR = os.path.join("data", "item", "lucidshop", PRODUCT_CATEGORY)

COOKIE_STRING = "al=KR; _fwb=110jaNMQZPiTnwRkaotg716.1773038464433; SITE_STAT_SID=2026031169b04d25039185.63326282; SITE_BEGIN_SID_m2026030548f0e1733e859=2026031169b04d2d0f51a4.68252818; SITE_SHOP_PROD_VIEW_SID_m2026030548f0e1733e859_s2026031011b358b27d4a6=2026031169b04d34e050c5.27466795; _dd_s=isExpired=1&aid=857f6956-1d72-4f12-945c-78f19aa3f563; IMWEBVSSID=46imsqu29ujukjrepm893pib843iq0b0tlu44fgg3ugqts8fvj3ei48ap6rqs7rd52996t3h3k2h1051n95v1gglvoe6r00qc4e0dl0; ISDID=69b16f598fa33; ilc=cjXwjGgi%2FGToTJgkEfR8wI0FkvpE6LwOkiE%2BK0ZuZuY%3D; ial=9e2d9efd2a99902dcce754e7a9333051960d937af2bc1eef5d8dabb0648658a2; _imweb_login_state=Y; alarm_cnt_member=1; __bs_imweb=%7B%22deviceId%22%3A%22019cd153ee14793484733dd57391ff6b%22%2C%22deviceIdCreatedAt%22%3A%222025-02-15T18%3A30%3A00%22%2C%22siteCode%22%3A%22S202512165282acc7684d6%22%2C%22unitCode%22%3A%22u20251216d69091d26aac8%22%2C%22platform%22%3A%22DESKTOP%22%2C%22browserSessionId%22%3A%22019cdd1b1b337808b8d6d489801b564a%22%2C%22sdkJwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMyMzYxMzUsImV4cCI6MTc3MzIzNjczNX0.14FXibnIYywoYNFd-Y1IfTsqB4Cfkkv0zgFueUC0KCE%22%2C%22referrer%22%3A%22https%3A%2F%2Fmidomae.com%2F166%22%2C%22initialReferrer%22%3A%22https%3A%2F%2Fmidomae.com%2Flogin%3Fback_url%3DLzE2Ng%253D%253D%22%2C%22initialReferrerDomain%22%3A%22midomae.com%22%2C%22utmSource%22%3Anull%2C%22utmMedium%22%3Anull%2C%22utmCampaign%22%3Anull%2C%22utmTerm%22%3Anull%2C%22utmContent%22%3Anull%2C%22utmLandingUrl%22%3Anull%2C%22utmUpdatedTime%22%3Anull%2C%22updatedAt%22%3A%222026-03-11T13%3A36%3A36.190Z%22%2C%22commonSessionId%22%3A%22sc_019cdd1b1b35769fb5864b54632182df%22%2C%22commonSessionUpdatedAt%22%3A%222026-03-11T13%3A36%3A35.701Z%22%2C%22customSessionId%22%3A%22cs_019cdd1b1b35769fb5864b55b8891575%22%2C%22customSessionUpdatedAt%22%3A%222026-03-11T13%3A36%3A35.702Z%22%2C%22browser_session_id%22%3A%22019cdd1b1b337808b8d6d489801b564a%22%2C%22sdk_jwt%22%3A%22eyJhbGciOiJFUzI1NiIsImtpZCI6bnVsbH0.eyJzdWIiOiJtMjAyNjAzMDU0OGYwZTE3MzNlODU5Iiwic2l0ZUNvZGUiOiJTMjAyNTEyMTY1MjgyYWNjNzY4NGQ2IiwidW5pdENvZGUiOiJ1MjAyNTEyMTZkNjkwOTFkMjZhYWM4IiwiY2hlY2tPZmZpY2UiOmZhbHNlLCJpYXQiOjE3NzMyMzYxMzUsImV4cCI6MTc3MzIzNjczNX0.14FXibnIYywoYNFd-Y1IfTsqB4Cfkkv0zgFueUC0KCE%22%2C%22initial_referrer%22%3A%22https%3A%2F%2Fmidomae.com%2Flogin%3Fback_url%3DLzE2Ng%253D%253D%22%2C%22initial_referrer_domain%22%3A%22midomae.com%22%2C%22utm_source%22%3Anull%2C%22utm_medium%22%3Anull%2C%22utm_campaign%22%3Anull%2C%22utm_term%22%3Anull%2C%22utm_content%22%3Anull%2C%22utm_landing_url%22%3Anull%2C%22utm_updated_time%22%3Anull%2C%22updated_at%22%3A%222026-03-11T13%3A36%3A36.190Z%22%2C%22common_session_id%22%3A%22sc_019cdd1b1b35769fb5864b54632182df%22%2C%22common_session_updated_at%22%3A%222026-03-11T13%3A36%3A35.701Z%22%2C%22custom_session_id%22%3A%22cs_019cdd1b1b35769fb5864b55b8891575%22%2C%22custom_session_updated_at%22%3A%222026-03-11T13%3A36%3A35.702Z%22%7D"

OPTION_NAME = "사이즈"
OPTION_ITEMS = ["1", "2", "3", "4", "5"]
OPTION_PRICE = "0"
STOCK_QTY = "9999"
NOTICE_QTY = "100"
USE_YN = "1"
OPTION_TYPE = "0"

# 0이면 전체 처리, 3이면 3건만 테스트
TEST_LIMIT = 0


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_csv_rows(csv_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    return rows


def write_csv_rows(csv_path: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_cookie_string(cookie_string: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}

    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()

    return cookies


def get_detail_url_from_row(row: Dict[str, Any]) -> str:
    for key in ["url", "href"]:
        value = sanitize_text(row.get(key))
        if not value:
            continue

        if value.startswith("http://") or value.startswith("https://"):
            return value

        return urljoin(BASE_URL, value)

    return ""


def extract_prod_idx(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    if query.get("idx"):
        return sanitize_text(query["idx"][0])

    if query.get("prod_idx"):
        return sanitize_text(query["prod_idx"][0])

    m = re.search(r"(?:idx|prod_idx)=(\d+)", url)
    if m:
        return m.group(1)

    return ""


def build_detail_headers(cookie_str: str = "") -> Dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "cookie": cookie_str,
    }


def build_ajax_headers(cookie_str: str = "", referer: str = "") -> Dict[str, str]:
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": referer,
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "cookie": cookie_str,
    }


def build_image_headers(cookie_str: str = "", referer: str = "") -> Dict[str, str]:
    return {
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
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
        "cookie": cookie_str,
    }


def fetch_detail_page_html(session: requests.Session, detail_url: str, cookie_str: str = "") -> str:
    response = session.get(detail_url, headers=build_detail_headers(cookie_str), timeout=30)
    response.raise_for_status()
    return response.text


def parse_thumbnail_url(detail_html: str, detail_url: str) -> str:
    soup = BeautifulSoup(detail_html, "html.parser")
    img_tag = soup.select_one("img#main-image")

    if not img_tag:
        return ""

    src = sanitize_text(img_tag.get("src"))
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
    response = session.get(
        ajax_url,
        headers=build_ajax_headers(cookie_str=cookie_str, referer=referer),
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    data_obj = payload.get("data") or {}

    if isinstance(data_obj, list):
        data_obj = data_obj[0] if data_obj else {}

    if not isinstance(data_obj, dict):
        data_obj = {}

    product_name = sanitize_text(data_obj.get("name"))
    detail_html = str(data_obj.get("content") or "")
    detail_html = detail_html.replace('\\"', '"')

    return {
        "product_name": product_name,
        "detail_html": detail_html,
    }


def get_image_name_from_url(image_url: str) -> str:
    if not image_url:
        return ""

    parsed = urlparse(image_url)
    return sanitize_text(os.path.basename(parsed.path))


def get_image_folder_name(image_name: str) -> str:
    if not image_name:
        return ""
    return sanitize_text(os.path.splitext(image_name)[0])


def build_image_path(image_name: str) -> str:
    if not image_name:
        return ""

    folder_name = get_image_folder_name(image_name)
    return f"{IMAGE_PATH_PREFIX}/{folder_name}/{image_name}"


def download_image(
        session: requests.Session,
        image_url: str,
        image_name: str,
        cookie_str: str = "",
        referer: str = "",
) -> str:
    if not image_url or not image_name:
        return ""

    folder_name = get_image_folder_name(image_name)
    target_dir = os.path.join(IMAGE_SAVE_DIR, folder_name)
    ensure_dir(target_dir)

    response = session.get(
        image_url,
        headers=build_image_headers(cookie_str=cookie_str, referer=referer),
        timeout=30,
        stream=True,
    )
    response.raise_for_status()

    save_path = os.path.join(target_dir, image_name)

    with open(save_path, "wb") as f:
        for chunk in response.iter_content(8192):
            if chunk:
                f.write(chunk)

    return save_path


def make_product_code(seq: int) -> str:
    today = datetime.now().strftime("%Y%m%d")
    return f"{today}{seq:03d}"


def make_option_rows(product_code: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for option_item in OPTION_ITEMS:
        rows.append(
            {
                "상품코드": product_code,
                "옵션명": OPTION_NAME,
                "옵션항목": option_item,
                "옵션가격": OPTION_PRICE,
                "재고수량": STOCK_QTY,
                "통보수량": NOTICE_QTY,
                "사용여부": USE_YN,
                "옵션형식": OPTION_TYPE,
            }
        )

    return rows


def process_rows(
        input_csv: str,
        detail_output_csv: str,
        option_output_csv: str,
        cookie_str: str = "",
        sleep_sec: float = 0.3,
) -> None:
    rows = read_csv_rows(input_csv)
    session = requests.Session()
    session.cookies.update(parse_cookie_string(cookie_str))

    detail_rows: List[Dict[str, Any]] = []
    option_rows: List[Dict[str, str]] = []

    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        if TEST_LIMIT > 0 and idx > TEST_LIMIT:
            print(f"[TEST] {TEST_LIMIT}건까지만 테스트 진행 후 종료")
            break

        detail_url = get_detail_url_from_row(row)
        prod_idx = extract_prod_idx(detail_url)
        product_code = make_product_code(idx)

        page = sanitize_text(row.get("page"))
        no = sanitize_text(row.get("no"))
        list_product_name = sanitize_text(row.get("product_name")) or sanitize_text(row.get("title"))

        new_row: Dict[str, Any] = {
            "page": page,
            "no": no,
            "url": detail_url,
            "상품명": "",
            "상품코드": product_code,
            "상세보기": "",
            "이미지명": "",
            "이미지경로": "",
        }

        if not detail_url or not prod_idx:
            detail_rows.append(new_row)
            print(f"[{idx}/{total}] skip | url 또는 prod_idx 없음")
            continue

        try:
            detail_page_html = fetch_detail_page_html(
                session=session,
                detail_url=detail_url,
                cookie_str=cookie_str,
            )

            thumbnail_url = parse_thumbnail_url(
                detail_html=detail_page_html,
                detail_url=detail_url,
            )

            ajax_data = fetch_ajax_product_data(
                session=session,
                prod_idx=prod_idx,
                cookie_str=cookie_str,
                referer=detail_url,
            )

            product_name = ajax_data.get("product_name") or list_product_name
            detail_html = ajax_data.get("detail_html", "")
            image_name = get_image_name_from_url(thumbnail_url)
            image_path = build_image_path(image_name)

            if thumbnail_url and image_name:
                download_image(
                    session=session,
                    image_url=thumbnail_url,
                    image_name=image_name,
                    cookie_str=cookie_str,
                    referer=detail_url,
                )

            new_row["상품명"] = product_name
            new_row["상세보기"] = detail_html
            new_row["이미지명"] = image_name
            new_row["이미지경로"] = image_path

            detail_rows.append(new_row)
            option_rows.extend(make_option_rows(product_code))

            print(
                f"[{idx}/{total}] 완료 | "
                f"상품코드={product_code} | "
                f"상품명={product_name} | "
                f"이미지명={image_name}"
            )

            if sleep_sec > 0:
                time.sleep(sleep_sec)

        except Exception as e:
            detail_rows.append(new_row)
            print(f"[{idx}/{total}] ERROR | url={detail_url} | {e}")

    write_csv_rows(
        detail_output_csv,
        detail_rows,
        ["page", "no", "url", "상품명", "상품코드", "상세보기", "이미지명", "이미지경로"],
    )

    write_csv_rows(
        option_output_csv,
        option_rows,
        ["상품코드", "옵션명", "옵션항목", "옵션가격", "재고수량", "통보수량", "사용여부", "옵션형식"],
    )

    print(f"[DONE] 상세 CSV 저장: {detail_output_csv}")
    print(f"[DONE] 옵션 CSV 저장: {option_output_csv}")


def main() -> None:
    process_rows(
        input_csv=INPUT_CSV,
        detail_output_csv=DETAIL_OUTPUT_CSV,
        option_output_csv=OPTION_OUTPUT_CSV,
        cookie_str=COOKIE_STRING,
        sleep_sec=0.3,
    )


if __name__ == "__main__":
    main()