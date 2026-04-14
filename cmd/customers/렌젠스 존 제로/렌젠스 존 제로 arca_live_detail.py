import csv
import os
import sys
import time
import shutil
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


ERROR_RETRY_MODE = True
PROGRAM_START_DT = datetime.now()

LOG_FILE_PATH = ""
LAST_STATUS_LEN = 0

CSV_READ_ENCODINGS = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]

URL_COL = "URL"
SUCCESS_COL = "성공"
MEMO_COL = "메모"
POST_TITLE_COL = "게시글 제목"
POST_AUTHOR_COL = "게시글 작성자"
POST_DATE_COL = "게시 날짜"
POST_BODY_COL = "게시글 본문"
POST_URL_COL = "게시글 URL"

MAX_FETCH_RETRY = 2
SLOW_RESPONSE_SECONDS = 4.0
PAGE_LOAD_TIMEOUT_SECONDS = 15
ELEMENT_WAIT_SECONDS = 10


def format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_elapsed(seconds: float) -> str:
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours}시간 {minutes}분 {secs}초"


def build_log_prefix() -> str:
    now_dt = datetime.now()
    elapsed_str = format_elapsed((now_dt - PROGRAM_START_DT).total_seconds())
    return (
        f"[시작 시간 {format_dt(PROGRAM_START_DT)}] "
        f"[현재 시간 {format_dt(now_dt)}] "
        f"[현재 경과 {elapsed_str}] "
    )


def write_log_file(message: str) -> None:
    if not LOG_FILE_PATH:
        return

    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def clear_status_line() -> None:
    global LAST_STATUS_LEN

    if LAST_STATUS_LEN > 0:
        sys.stdout.write("\r" + (" " * LAST_STATUS_LEN) + "\r")
        sys.stdout.flush()
        LAST_STATUS_LEN = 0


def log_status(message: str) -> None:
    global LAST_STATUS_LEN

    full_message = build_log_prefix() + message
    padded = full_message

    if len(full_message) < LAST_STATUS_LEN:
        padded = full_message + (" " * (LAST_STATUS_LEN - len(full_message)))

    sys.stdout.write("\r" + padded)
    sys.stdout.flush()
    LAST_STATUS_LEN = len(full_message)

    write_log_file(full_message)


def log_line(message: str) -> None:
    clear_status_line()

    full_message = build_log_prefix() + message
    print(full_message)

    write_log_file(full_message)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def normalize_url(url: str) -> str:
    return str(url or "").strip()


def ask_csv_name() -> tuple[str, str]:
    raw = input("INPUT_CSV 이름을 입력하세요 (예: test): ").strip()

    if not raw:
        raise ValueError("파일명을 입력하지 않았습니다.")

    if raw.lower().endswith(".csv"):
        input_csv = raw
        base_name = raw[:-4]
    else:
        input_csv = f"{raw}.csv"
        base_name = raw

    output_csv = f"{base_name}_result.csv"
    return input_csv, output_csv


def ensure_output_columns(rows: list[dict]) -> list[str]:
    fieldnames = list(rows[0].keys()) if rows else []

    add_cols = [
        POST_TITLE_COL,
        POST_AUTHOR_COL,
        POST_DATE_COL,
        POST_BODY_COL,
        POST_URL_COL,
        SUCCESS_COL,
        MEMO_COL,
    ]

    for col in add_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    return fieldnames


def ensure_row_columns(row: dict, fieldnames: list[str]) -> dict:
    new_row = {}
    for col in fieldnames:
        new_row[col] = row.get(col, "")
    return new_row


def try_read_csv_rows(csv_path: str) -> tuple[list[dict] | None, str, str]:
    if not os.path.exists(csv_path):
        return [], "", ""

    if os.path.getsize(csv_path) == 0:
        return [], "empty", ""

    last_error = ""

    for encoding in CSV_READ_ENCODINGS:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

                if reader.fieldnames is None:
                    raise ValueError("헤더가 없습니다.")

                return rows, encoding, ""
        except Exception as e:
            last_error = f"{encoding}: {str(e)}"

    return None, "", last_error


def read_required_csv_rows(csv_path: str) -> tuple[list[dict], str]:
    rows, encoding, error = try_read_csv_rows(csv_path)

    if rows is None:
        raise ValueError(f"CSV 읽기 실패: {csv_path} / {error}")

    return rows, encoding


def merge_result_rows(primary_rows: list[dict], backup_rows: list[dict]) -> list[dict]:
    merged = []
    index_map = {}

    for row in backup_rows:
        url = normalize_url(row.get(URL_COL, ""))
        if not url:
            continue

        copied = dict(row)
        merged.append(copied)
        index_map[url] = len(merged) - 1

    for row in primary_rows:
        url = normalize_url(row.get(URL_COL, ""))
        if not url:
            continue

        copied = dict(row)

        if url not in index_map:
            merged.append(copied)
            index_map[url] = len(merged) - 1
            continue

        old_row = merged[index_map[url]]
        old_success = str(old_row.get(SUCCESS_COL, "")).strip().upper()
        new_success = str(copied.get(SUCCESS_COL, "")).strip().upper()

        if old_success != "Y" and new_success == "Y":
            merged[index_map[url]] = copied
        elif old_success != "Y" and new_success != "Y":
            merged[index_map[url]] = copied

    return merged


def load_result_rows(output_csv: str) -> list[dict]:
    backup_csv = f"{output_csv}.bak"

    primary_rows, primary_encoding, primary_error = try_read_csv_rows(output_csv)
    backup_rows, backup_encoding, backup_error = try_read_csv_rows(backup_csv)

    if primary_rows is None:
        log_line(f"결과 CSV 읽기 실패: {output_csv} / {primary_error}")
    elif os.path.exists(output_csv):
        log_line(f"결과 CSV 읽기 성공: {output_csv} / encoding={primary_encoding} / {len(primary_rows)}건")

    if backup_rows is None:
        log_line(f"백업 CSV 읽기 실패: {backup_csv} / {backup_error}")
    elif os.path.exists(backup_csv):
        log_line(f"백업 CSV 읽기 성공: {backup_csv} / encoding={backup_encoding} / {len(backup_rows)}건")

    if primary_rows is None and backup_rows is None:
        log_line("결과 CSV와 백업 CSV 모두 읽기 실패 - 새로 시작")
        return []

    if primary_rows is None:
        log_line("백업 CSV 기준으로 복구해서 시작")
        return backup_rows

    if backup_rows is None:
        return primary_rows

    merged_rows = merge_result_rows(primary_rows, backup_rows)
    log_line(
        f"결과 CSV 병합 완료: 본파일 {len(primary_rows)}건 + 백업 {len(backup_rows)}건 -> 최종 {len(merged_rows)}건"
    )
    return merged_rows


def save_rows_atomic(output_csv: str, fieldnames: list[str], rows: list[dict]) -> None:
    temp_csv = f"{output_csv}.tmp"
    backup_csv = f"{output_csv}.bak"

    with open(temp_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_csv, output_csv)

    try:
        shutil.copy2(output_csv, backup_csv)
    except Exception:
        pass


def build_result_map(result_rows: list[dict]) -> dict[str, dict]:
    result_map = {}

    for row in result_rows:
        url = normalize_url(row.get(URL_COL, ""))
        if url:
            result_map[url] = row

    return result_map


def create_driver() -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ko-KR")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )

    prefs = {
        "profile.managed_default_content_settings.images": 2,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        },
    )

    return driver


def close_driver(driver) -> None:
    if driver is None:
        return

    try:
        driver.quit()
    except Exception:
        pass


def restart_driver(driver):
    close_driver(driver)
    time.sleep(1)
    new_driver = create_driver()
    log_line("크롬 재실행 완료")
    return new_driver


def extract_body_text(driver: webdriver.Chrome, wrapper) -> str:
    try:
        content_el = wrapper.find_element(
            By.CSS_SELECTOR,
            ".article-body .fr-view.article-content"
        )

        p_list = content_el.find_elements(By.CSS_SELECTOR, "p")
        lines = []

        for p in p_list:
            text = driver.execute_script(
                """
                const el = arguments[0];
                let result = '';

                for (const node of el.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        result += node.textContent;
                    } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'BR') {
                        result += '\\n';
                    }
                }

                return result;
                """,
                p
            )

            text = clean_text(text)
            if text:
                lines.append(text)

        return "\n".join(lines).strip()

    except Exception:
        return ""


def get_error_404_message(driver: webdriver.Chrome) -> str:
    try:
        error_code_els = driver.find_elements(By.CSS_SELECTOR, ".error-code")
        has_404 = False

        for el in error_code_els:
            code_text = clean_text(el.text)
            if "ERROR 404" in code_text:
                has_404 = True
                break

        if not has_404:
            return ""

        msg_els = driver.find_elements(By.CSS_SELECTOR, "p.pre-wrap")
        for msg_el in msg_els:
            msg_text = clean_text(msg_el.text)
            if "존재하지 않는 글입니다" in msg_text:
                return "존재하지 않는 글"

        return "존재하지 않는 글"

    except Exception:
        return ""


def get_post_data(driver: webdriver.Chrome, post_url: str) -> dict:
    driver.get(post_url)

    not_found_msg = get_error_404_message(driver)
    if not_found_msg:
        return {
            POST_TITLE_COL: "",
            POST_AUTHOR_COL: "",
            POST_DATE_COL: "",
            POST_BODY_COL: "",
            POST_URL_COL: post_url,
            SUCCESS_COL: "Y",
            MEMO_COL: not_found_msg,
        }

    wait = WebDriverWait(driver, ELEMENT_WAIT_SECONDS)
    wrapper = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".article-wrapper"))
    )

    title = ""
    author = ""
    post_date = ""
    body_text = ""
    final_url = post_url

    try:
        title_el = wrapper.find_element(By.CSS_SELECTOR, ".article-head .title")
        title = clean_text(title_el.text).replace("\n", " ")
    except Exception:
        pass

    try:
        author_el = wrapper.find_element(By.CSS_SELECTOR, ".info-row .user-info a")
        author = clean_text(author_el.text).replace("\n", " ")
    except Exception:
        pass

    try:
        date_el = wrapper.find_element(
            By.CSS_SELECTOR,
            ".article-info.article-info-section .date .body time"
        )
        post_date = clean_text(date_el.text).replace("\n", " ")
    except Exception:
        pass

    try:
        link_el = wrapper.find_element(By.CSS_SELECTOR, ".article-link a")
        href = clean_text(link_el.get_attribute("href")).replace("\n", " ")
        text = clean_text(link_el.text).replace("\n", " ")
        final_url = href or text or post_url
    except Exception:
        pass

    body_text = extract_body_text(driver, wrapper)

    return {
        POST_TITLE_COL: title,
        POST_AUTHOR_COL: author,
        POST_DATE_COL: post_date,
        POST_BODY_COL: body_text,
        POST_URL_COL: final_url,
        SUCCESS_COL: "Y",
        MEMO_COL: "",
    }


def apply_parsed_to_row(row: dict, parsed: dict, post_url: str) -> None:
    row[POST_TITLE_COL] = parsed.get(POST_TITLE_COL, "")
    row[POST_AUTHOR_COL] = parsed.get(POST_AUTHOR_COL, "")
    row[POST_DATE_COL] = parsed.get(POST_DATE_COL, "")
    row[POST_BODY_COL] = parsed.get(POST_BODY_COL, "")
    row[POST_URL_COL] = parsed.get(POST_URL_COL, post_url)
    row[SUCCESS_COL] = parsed.get(SUCCESS_COL, "Y")
    row[MEMO_COL] = parsed.get(MEMO_COL, "")


def fetch_post_with_recovery(driver_box: dict, post_url: str, log_prefix_text: str) -> dict:
    last_error = ""

    for attempt in range(1, MAX_FETCH_RETRY + 1):
        if driver_box["driver"] is None:
            driver_box["driver"] = create_driver()
            log_line("크롬 실행 완료")

        start_ts = time.time()

        try:
            parsed = get_post_data(driver_box["driver"], post_url)
            elapsed = time.time() - start_ts

            if elapsed > SLOW_RESPONSE_SECONDS:
                log_line(
                    f"{log_prefix_text} 응답 {elapsed:.1f}초 - "
                    f"{SLOW_RESPONSE_SECONDS}초 초과로 크롬 재시작"
                )
                driver_box["driver"] = restart_driver(driver_box["driver"])

            return parsed

        except TimeoutException:
            elapsed = time.time() - start_ts
            last_error = f"타임아웃 - article-wrapper 로딩 실패 ({elapsed:.1f}초)"
            log_line(f"{log_prefix_text} {attempt}차 실패 - {last_error}")
            driver_box["driver"] = restart_driver(driver_box["driver"])

        except Exception as e:
            elapsed = time.time() - start_ts
            last_error = f"{str(e)} ({elapsed:.1f}초)"
            log_line(f"{log_prefix_text} {attempt}차 실패 - {last_error}")
            driver_box["driver"] = restart_driver(driver_box["driver"])

    raise RuntimeError(last_error or "알 수 없는 오류")


def process_failed_rows(
        driver_box: dict,
        output_csv: str,
        fieldnames: list[str],
        result_rows: list[dict],
) -> None:
    if not result_rows:
        return

    log_line("1단계 시작 - 기존 result 실패건 재처리")

    for idx, row in enumerate(result_rows, start=1):
        post_url = normalize_url(row.get(URL_COL, ""))
        success = str(row.get(SUCCESS_COL, "")).strip().upper()

        if not post_url:
            continue

        if success == "Y":
            continue

        if not ERROR_RETRY_MODE:
            continue

        log_status(f"[기존결과 {idx}/{len(result_rows)}] 실패건 재처리 중 - {post_url}")

        try:
            parsed = fetch_post_with_recovery(
                driver_box,
                post_url,
                f"[기존결과 {idx}/{len(result_rows)}]"
            )
            apply_parsed_to_row(row, parsed, post_url)

        except Exception as e:
            row[SUCCESS_COL] = "N"
            row[MEMO_COL] = f"{MAX_FETCH_RETRY}회 실패: {str(e)}"
            log_line(f"[기존결과 {idx}/{len(result_rows)}] 최종 실패 - {post_url} - {str(e)}")

        save_rows_atomic(output_csv, fieldnames, result_rows)

    clear_status_line()
    log_line("1단계 완료 - 기존 실패건 재처리 완료")


def process_new_rows(
        driver_box: dict,
        input_rows: list[dict],
        output_csv: str,
        fieldnames: list[str],
        result_rows: list[dict],
) -> None:
    log_line("2단계 시작 - 원본 CSV 기준 남은 건 이어서 처리")

    result_map = build_result_map(result_rows)

    for idx, source_row in enumerate(input_rows, start=1):
        post_url = normalize_url(source_row.get(URL_COL, ""))

        if not post_url:
            continue

        existing = result_map.get(post_url)
        if existing:
            existing_success = str(existing.get(SUCCESS_COL, "")).strip().upper()

            if existing_success == "Y":
                continue

            if not ERROR_RETRY_MODE:
                continue

            continue

        row = ensure_row_columns(source_row, fieldnames)
        row[POST_TITLE_COL] = ""
        row[POST_AUTHOR_COL] = ""
        row[POST_DATE_COL] = ""
        row[POST_BODY_COL] = ""
        row[POST_URL_COL] = post_url
        row[SUCCESS_COL] = "N"
        row[MEMO_COL] = ""

        log_status(f"[원본 {idx}/{len(input_rows)}] 작업 중 - {post_url}")

        try:
            parsed = fetch_post_with_recovery(
                driver_box,
                post_url,
                f"[원본 {idx}/{len(input_rows)}]"
            )
            apply_parsed_to_row(row, parsed, post_url)

        except Exception as e:
            row[SUCCESS_COL] = "N"
            row[MEMO_COL] = f"{MAX_FETCH_RETRY}회 실패: {str(e)}"
            log_line(f"[원본 {idx}/{len(input_rows)}] 최종 실패 - {post_url} - {str(e)}")

        result_rows.append(row)
        result_map[post_url] = row
        save_rows_atomic(output_csv, fieldnames, result_rows)

    clear_status_line()
    log_line("2단계 완료 - 남은 건 처리 완료")


def process_posts() -> None:
    global LOG_FILE_PATH

    input_csv, output_csv = ask_csv_name()

    base_name = os.path.splitext(input_csv)[0]
    LOG_FILE_PATH = f"{base_name}_log.txt"

    log_line("프로그램 시작")
    log_line(f"입력 파일: {input_csv}")
    log_line(f"결과 파일: {output_csv}")
    log_line(f"로그 파일: {LOG_FILE_PATH}")

    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"입력 파일이 없습니다: {input_csv}")

    input_rows, input_encoding = read_required_csv_rows(input_csv)
    if not input_rows:
        raise ValueError("원본 CSV 데이터가 비어 있습니다.")

    if URL_COL not in input_rows[0]:
        raise ValueError(f'"{URL_COL}" 컬럼이 없습니다.')

    log_line(f"원본 CSV 읽기 성공: encoding={input_encoding} / {len(input_rows)}건")

    fieldnames = ensure_output_columns(input_rows)

    for i in range(len(input_rows)):
        input_rows[i] = ensure_row_columns(input_rows[i], fieldnames)

    result_rows = load_result_rows(output_csv)
    for i in range(len(result_rows)):
        result_rows[i] = ensure_row_columns(result_rows[i], fieldnames)

    if result_rows:
        log_line(f"기존 결과 기준으로 이어서 시작: {len(result_rows)}건")
    else:
        log_line("기존 결과 없음 - 새로 시작")

    driver_box = {"driver": None}

    try:
        process_failed_rows(
            driver_box=driver_box,
            output_csv=output_csv,
            fieldnames=fieldnames,
            result_rows=result_rows,
        )

        process_new_rows(
            driver_box=driver_box,
            input_rows=input_rows,
            output_csv=output_csv,
            fieldnames=fieldnames,
            result_rows=result_rows,
        )

        log_line(f"전체 완료: {output_csv}")

    finally:
        close_driver(driver_box["driver"])
        log_line("크롬 종료 완료")


if __name__ == "__main__":
    try:
        process_posts()
    except Exception as e:
        log_line(f"프로그램 오류: {str(e)}")
    finally:
        clear_status_line()
        input("엔터를 누르면 종료됩니다...")