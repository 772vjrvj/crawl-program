import csv
import os
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


BASE_URL = "https://arca.live/b/zenlesszonezero"
OUTPUT_CSV = "arca_zenlesszonezero_list.csv"

SLEEP_SEC = 2

# 비어있으면 CSV 마지막 next_before 기준으로 이어서 시작
# 직접 특정 지점부터 시작하고 싶으면 값 넣으면 됨
START_NEXT_BEFORE = ""

# 한국시간 기준
KST = timezone(timedelta(hours=9))
STOP_DT = datetime(2025, 4, 11, 0, 0, 0, tzinfo=KST)

CSV_COLUMNS = [
    "before",
    "next_before",
    "URL",
    "게시 번호",
    "게시 날짜",
    "게시글 제목",
    "게시글 본문",
    "성공",
]


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)


def parse_datetime_to_kst(datetime_str: str):
    datetime_str = str(datetime_str or "").strip()
    if not datetime_str:
        return None

    try:
        if "." in datetime_str:
            utc_dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            utc_dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%SZ")

        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(KST)
    except Exception:
        return None


def build_url(before_value: str = "") -> str:
    if before_value:
        return f"{BASE_URL}?{urlencode({'before': before_value})}"
    return BASE_URL


def ensure_csv_exists(file_path: str) -> None:
    if os.path.exists(file_path):
        return

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()


def append_csv(rows, file_path: str) -> None:
    if not rows:
        return

    ensure_csv_exists(file_path)

    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerows(rows)


def load_existing_state(file_path: str):
    seen_urls = set()
    last_next_before = ""

    if not os.path.exists(file_path):
        return seen_urls, last_next_before

    with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            url = str(row.get("URL", "") or "").strip()
            next_before = str(row.get("next_before", "") or "").strip()

            if url:
                seen_urls.add(url)

            if next_before:
                last_next_before = next_before

    return seen_urls, last_next_before


def fetch_page_rows(driver, page_no: int, before_value: str = ""):
    url = build_url(before_value)

    log(f"페이지 이동: page={page_no}, before={before_value or '-'}")
    log(f"요청 URL: {url}")

    driver.get(url)
    time.sleep(SLEEP_SEC)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    table = soup.select_one(".list-table.table")
    if not table:
        log(f"목록 테이블 못찾음: page={page_no}")
        return [], False, ""

    rows = table.select("a.vrow.column")
    if not rows:
        log(f"목록 row 없음: page={page_no}")
        return [], False, ""

    parsed_items = []
    should_stop = False
    next_before = ""

    valid_row_count = 0

    for idx, row in enumerate(rows, start=1):
        class_list = row.get("class", [])

        if "head" in class_list or "notice" in class_list:
            continue

        href = row.get("href", "").strip()
        if not href:
            continue

        if not href.startswith("/b/zenlesszonezero/"):
            continue

        full_url = "https://arca.live" + href

        id_tag = row.select_one(".col-id span")
        post_no = id_tag.get_text(strip=True) if id_tag else ""

        title_tag = row.select_one(".title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

        time_tag = row.select_one(".col-time time")
        raw_datetime = time_tag.get("datetime", "").strip() if time_tag else ""
        post_dt = parse_datetime_to_kst(raw_datetime)

        if not raw_datetime:
            log(f"datetime 없음: page={page_no}, item={idx}, 번호={post_no}")
            continue

        if not post_dt:
            log(f"날짜 파싱 실패: page={page_no}, item={idx}, 번호={post_no}, raw={raw_datetime}")
            continue

        valid_row_count += 1
        next_before = raw_datetime

        if post_dt < STOP_DT:
            log(
                f"중단 기준 도달: page={page_no}, item={idx}, 번호={post_no}, "
                f"게시날짜={post_dt.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            should_stop = True
            break

        parsed_items.append({
            "URL": full_url,
            "게시 번호": post_no,
            "게시 날짜": post_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "게시글 제목": title,
            "게시글 본문": "",
            "성공": "",
        })

    log(
        f"페이지 파싱 완료: page={page_no}, "
        f"유효row={valid_row_count}, 저장대상={len(parsed_items)}, next_before={next_before or '-'}"
    )

    rows_to_save = []
    for item in parsed_items:
        row = {
            "before": before_value,
            "next_before": next_before,
            "URL": item["URL"],
            "게시 번호": item["게시 번호"],
            "게시 날짜": item["게시 날짜"],
            "게시글 제목": item["게시글 제목"],
            "게시글 본문": item["게시글 본문"],
            "성공": item["성공"],
        }
        rows_to_save.append(row)

    return rows_to_save, should_stop, next_before


def main():
    driver = create_driver()

    try:
        seen_urls, csv_last_next_before = load_existing_state(OUTPUT_CSV)

        before_value = str(START_NEXT_BEFORE or "").strip()
        if not before_value and csv_last_next_before:
            before_value = csv_last_next_before

        prev_before_value = ""
        page_no = 1
        total_added = 0

        log("수집 시작")
        log(f"수집 범위: 2024-07-04 11:00:00 ~ 현재")
        log(f"저장 파일: {OUTPUT_CSV}")
        log(f"기존 URL 수: {len(seen_urls)}")
        log(f"재시작 next_before: {before_value or '-'}")

        while True:
            try:
                page_rows, should_stop, next_before = fetch_page_rows(driver, page_no, before_value)
            except Exception as e:
                log(f"페이지 처리 중 에러: page={page_no}, before={before_value or '-'}, error={e}")
                break

            if not page_rows and not should_stop:
                log(f"더 이상 데이터 없음, 종료: page={page_no}")
                break

            append_rows = []

            for row in page_rows:
                url = row["URL"]

                if url in seen_urls:
                    continue

                seen_urls.add(url)
                append_rows.append(row)

            if append_rows:
                append_csv(append_rows, OUTPUT_CSV)
                total_added += len(append_rows)
                log(
                    f"CSV 저장 완료: page={page_no}, "
                    f"이번추가={len(append_rows)}, 총추가={total_added}, 누적URL={len(seen_urls)}"
                )
            else:
                log(f"CSV 저장 스킵: page={page_no}, 신규 데이터 없음")

            if should_stop:
                log(f"기준일 이전 글 확인되어 종료: page={page_no}")
                break

            if not next_before:
                log(f"다음 next_before 값이 없어 종료: page={page_no}")
                break

            if next_before == before_value or next_before == prev_before_value:
                log(f"next_before 반복 감지 종료: page={page_no}, next_before={next_before}")
                break

            prev_before_value = before_value
            before_value = next_before
            page_no += 1

        log("전체 작업 종료")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()