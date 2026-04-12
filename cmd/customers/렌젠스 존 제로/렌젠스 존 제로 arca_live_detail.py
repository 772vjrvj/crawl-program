import csv
import os
import sys
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


INPUT_CSV = "test.csv"
OUTPUT_CSV = "test_result.csv"
CHROMEDRIVER_NAME = "chromedriver.exe"

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
    elapsed = now_dt - PROGRAM_START_DT
    elapsed_str = format_elapsed(elapsed.total_seconds())
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


def save_rows_to_csv(output_csv: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resource_path(filename: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)


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

    # options.add_argument("--headless=new")

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


def get_post_data(driver: webdriver.Chrome, post_url: str) -> dict:
    driver.get(post_url)

    wait = WebDriverWait(driver, 20)
    wrapper = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".article-wrapper"))
    )

    time.sleep(1)

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
    }


def process_posts() -> None:
    log("프로그램 시작")

    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(f"입력 파일이 없습니다: {INPUT_CSV}")

    log(f"입력 파일 확인 완료: {INPUT_CSV}")

    with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV 데이터가 비어 있습니다.")

    if "URL" not in rows[0]:
        raise ValueError('"URL" 컬럼이 없습니다.')

    log(f"입력 행 수 확인 완료: {len(rows)}건")

    fieldnames = ensure_output_columns(rows)

    save_rows_to_csv(OUTPUT_CSV, fieldnames, [])
    log(f"결과 파일 초기화 완료: {OUTPUT_CSV}")

    driver = create_driver()
    log("크롬 드라이버 실행 완료")

    try:
        result_rows = []

        for idx, row in enumerate(rows, start=1):
            post_url = str(row.get("URL", "")).strip()

            row["게시글 제목"] = ""
            row["게시글 작성자"] = ""
            row["게시 날짜"] = ""
            row["게시글 본문"] = ""
            row["게시글 URL"] = ""
            row["성공"] = "N"
            row["메모"] = ""

            if not post_url:
                row["메모"] = "URL 값이 비어있음"
                result_rows.append(row)
                save_rows_to_csv(OUTPUT_CSV, fieldnames, result_rows)
                log(f"[{idx}/{len(rows)}] 실패 - URL 비어있음")
                continue

            row["게시글 URL"] = post_url
            log(f"[{idx}/{len(rows)}] 시작 - {post_url}")

            try:
                parsed = get_post_data(driver, post_url)

                row["게시글 제목"] = parsed["게시글 제목"]
                row["게시글 작성자"] = parsed["게시글 작성자"]
                row["게시 날짜"] = parsed["게시 날짜"]
                row["게시글 본문"] = parsed["게시글 본문"]
                row["게시글 URL"] = parsed["게시글 URL"]
                row["성공"] = "Y"
                row["메모"] = ""

                log(f"[{idx}/{len(rows)}] 성공 - {post_url}")

            except TimeoutException:
                row["성공"] = "N"
                row["메모"] = "타임아웃 - article-wrapper 로딩 실패"
                log(f"[{idx}/{len(rows)}] 실패 - {post_url} - 타임아웃")

            except Exception as e:
                row["성공"] = "N"
                row["메모"] = f"실패: {e}"
                log(f"[{idx}/{len(rows)}] 실패 - {post_url} - {e}")

            result_rows.append(row)
            save_rows_to_csv(OUTPUT_CSV, fieldnames, result_rows)
            log(f"[{idx}/{len(rows)}] CSV 저장 완료")

            time.sleep(1)

        log(f"전체 완료: {OUTPUT_CSV}")

    finally:
        try:
            driver.quit()
            log("크롬 드라이버 종료 완료")
        except Exception as e:
            log(f"크롬 드라이버 종료 중 예외 발생: {e}")


if __name__ == "__main__":
    try:
        process_posts()
    except Exception as e:
        log(f"프로그램 오류: {e}")
    finally:
        input("엔터를 누르면 종료됩니다...")