import csv
import os
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# 오류 재시도 모드
# True  -> 기존 result 에서 성공 N 인 것들만 다시 시도
# False -> 기존 result 에서 성공 N 인 것도 스킵
ERROR_RETRY_MODE = True

PROGRAM_START_DT = datetime.now()


def format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_elapsed(seconds: float) -> str:
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours}시간 {minutes}분 {secs}초"


def log(message: str) -> None:
    now_dt = datetime.now()
    elapsed_str = format_elapsed((now_dt - PROGRAM_START_DT).total_seconds())
    print(
        f"[시작 시간 {format_dt(PROGRAM_START_DT)}] "
        f"[현재 시간 {format_dt(now_dt)}] "
        f"[현재 경과 {elapsed_str}] "
        f"{message}"
    )


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


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
        "게시글 제목",
        "게시글 작성자",
        "게시 날짜",
        "게시글 본문",
        "게시글 URL",
        "성공",
        "메모",
    ]

    for col in add_cols:
        if col not in fieldnames:
            fieldnames.append(col)

    return fieldnames


def write_all_rows(output_csv: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(csv_path: str) -> list[dict]:
    if not os.path.exists(csv_path):
        return []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=ko-KR")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)

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
            "게시글 제목": "",
            "게시글 작성자": "",
            "게시 날짜": "",
            "게시글 본문": "",
            "게시글 URL": post_url,
            "성공": "Y",
            "메모": not_found_msg,
        }

    wait = WebDriverWait(driver, 20)
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
        "게시글 제목": title,
        "게시글 작성자": author,
        "게시 날짜": post_date,
        "게시글 본문": body_text,
        "게시글 URL": final_url,
        "성공": "Y",
        "메모": "",
    }


def build_result_map(result_rows: list[dict]) -> dict[str, dict]:
    result_map: dict[str, dict] = {}

    for row in result_rows:
        url = str(row.get("URL", "")).strip()
        if url:
            result_map[url] = row

    return result_map


def normalize_input_row(row: dict, fieldnames: list[str]) -> dict:
    new_row = {}
    for col in fieldnames:
        new_row[col] = row.get(col, "")
    return new_row


def process_posts() -> None:
    input_csv, output_csv = ask_csv_name()

    log("프로그램 시작")
    log(f"입력 파일: {input_csv}")
    log(f"결과 파일: {output_csv}")

    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"입력 파일이 없습니다: {input_csv}")

    input_rows = read_csv_rows(input_csv)
    if not input_rows:
        raise ValueError("원본 CSV 데이터가 비어 있습니다.")

    if "URL" not in input_rows[0]:
        raise ValueError('"URL" 컬럼이 없습니다.')

    fieldnames = ensure_output_columns(input_rows)

    for row in input_rows:
        for col in fieldnames:
            if col not in row:
                row[col] = ""

    log(f"원본 CSV 확인 완료: {input_csv} / {len(input_rows)}건")

    result_rows = read_csv_rows(output_csv)
    if result_rows:
        for row in result_rows:
            for col in fieldnames:
                if col not in row:
                    row[col] = ""
        log(f"기존 결과 CSV 확인 완료: {output_csv} / {len(result_rows)}건")
    else:
        log("기존 결과 CSV 없음 - 새로 시작")

    result_map = build_result_map(result_rows)

    driver = create_driver()
    log("크롬 실행 완료")

    try:
        if result_rows:
            log("1단계 시작 - 기존 result 기준 오류 행 정리")

            for idx, row in enumerate(result_rows, start=1):
                post_url = str(row.get("URL", "")).strip()
                success = str(row.get("성공", "")).strip().upper()

                if not post_url:
                    continue

                if success == "Y":
                    log(f"[기존결과 {idx}/{len(result_rows)}] 성공건 스킵 - {post_url}")
                    continue

                if not ERROR_RETRY_MODE:
                    log(f"[기존결과 {idx}/{len(result_rows)}] 실패건 스킵 - {post_url}")
                    continue

                log(f"[기존결과 {idx}/{len(result_rows)}] 실패건 재시도 시작 - {post_url}")

                try:
                    parsed = get_post_data(driver, post_url)

                    row["게시글 제목"] = parsed.get("게시글 제목", "")
                    row["게시글 작성자"] = parsed.get("게시글 작성자", "")
                    row["게시 날짜"] = parsed.get("게시 날짜", "")
                    row["게시글 본문"] = parsed.get("게시글 본문", "")
                    row["게시글 URL"] = parsed.get("게시글 URL", post_url)
                    row["성공"] = parsed.get("성공", "Y")
                    row["메모"] = parsed.get("메모", "")

                    log(f"[기존결과 {idx}/{len(result_rows)}] 재시도 성공 - {post_url}")

                except TimeoutException:
                    row["성공"] = "N"
                    row["메모"] = "2회 실패: 타임아웃 - article-wrapper 로딩 실패"
                    log(f"[기존결과 {idx}/{len(result_rows)}] 재시도 실패 - 타임아웃 - {post_url}")

                except Exception as e:
                    row["성공"] = "N"
                    row["메모"] = f"2회 실패: {e}"
                    log(f"[기존결과 {idx}/{len(result_rows)}] 재시도 실패 - {post_url} - {e}")

                write_all_rows(output_csv, fieldnames, result_rows)
                log(f"[기존결과 {idx}/{len(result_rows)}] 결과 CSV 즉시 저장 완료")

            result_map = build_result_map(result_rows)
            log("1단계 완료 - 기존 result 정리 완료")

        log("2단계 시작 - 원본 CSV 기준 신규 작업 확인")

        for idx, source_row in enumerate(input_rows, start=1):
            post_url = str(source_row.get("URL", "")).strip()

            if not post_url:
                log(f"[원본 {idx}/{len(input_rows)}] URL 비어있음 - 스킵")
                continue

            existing = result_map.get(post_url)

            if existing:
                existing_success = str(existing.get("성공", "")).strip().upper()

                if existing_success == "Y":
                    log(f"[원본 {idx}/{len(input_rows)}] 이미 성공한 건 스킵 - {post_url}")
                    continue

                if not ERROR_RETRY_MODE:
                    log(f"[원본 {idx}/{len(input_rows)}] 기존 실패건 스킵 - {post_url}")
                    continue

                log(f"[원본 {idx}/{len(input_rows)}] 기존 실패건은 1단계 처리됨 - 스킵 - {post_url}")
                continue

            row = normalize_input_row(source_row, fieldnames)

            row["게시글 제목"] = ""
            row["게시글 작성자"] = ""
            row["게시 날짜"] = ""
            row["게시글 본문"] = ""
            row["게시글 URL"] = post_url
            row["성공"] = "N"
            row["메모"] = ""

            log(f"[원본 {idx}/{len(input_rows)}] 신규 시작 - {post_url}")

            try:
                parsed = get_post_data(driver, post_url)

                row["게시글 제목"] = parsed.get("게시글 제목", "")
                row["게시글 작성자"] = parsed.get("게시글 작성자", "")
                row["게시 날짜"] = parsed.get("게시 날짜", "")
                row["게시글 본문"] = parsed.get("게시글 본문", "")
                row["게시글 URL"] = parsed.get("게시글 URL", post_url)
                row["성공"] = parsed.get("성공", "Y")
                row["메모"] = parsed.get("메모", "")

                log(f"[원본 {idx}/{len(input_rows)}] 성공 - {post_url}")

            except TimeoutException:
                row["성공"] = "N"
                row["메모"] = "실패: 타임아웃 - article-wrapper 로딩 실패"
                log(f"[원본 {idx}/{len(input_rows)}] 실패 - 타임아웃 - {post_url}")

            except Exception as e:
                row["성공"] = "N"
                row["메모"] = f"실패: {e}"
                log(f"[원본 {idx}/{len(input_rows)}] 실패 - {post_url} - {e}")

            result_rows.append(row)
            result_map[post_url] = row

            write_all_rows(output_csv, fieldnames, result_rows)
            log(f"[원본 {idx}/{len(input_rows)}] 결과 CSV 즉시 저장 완료")

        log(f"전체 완료: {output_csv}")

    finally:
        try:
            driver.quit()
            log("크롬 종료 완료")
        except Exception as e:
            log(f"크롬 종료 중 예외 발생: {e}")


if __name__ == "__main__":
    try:
        process_posts()
    except Exception as e:
        log(f"프로그램 오류: {e}")
    finally:
        input("엔터를 누르면 종료됩니다...")