import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


URL = "https://data.seongnam.go.kr/portal/statDash/complainStatus.do"
START_MONTH = "2021-01"
END_MONTH = "2026-03"

INITIAL_WAIT_SEC = 5
SEARCH_WAIT_SEC = 5
DOWNLOAD_CLICK_WAIT_SEC = 20
DOWNLOAD_FINISH_TIMEOUT_SEC = 60

DOWNLOAD_DIR = Path.cwd() / "seongnam_downloads"
FILE_PREFIX = "민원현황_"


def month_range(start_ym: str, end_ym: str):
    sy, sm = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))

    y, m = sy, sm
    while (y < ey) or (y == ey and m <= em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y += 1
            m = 1


def load_downloaded_months(folder: Path) -> set[str]:
    downloaded_months = set()

    if not folder.exists():
        return downloaded_months

    pattern = re.compile(rf"^{re.escape(FILE_PREFIX)}(\d{{4}}-\d{{2}})\.[^.]+$")

    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue

        match = pattern.match(file_path.name)
        if match:
            downloaded_months.add(match.group(1))

    return downloaded_months


def snapshot_dir(folder: Path) -> dict[str, float]:
    result = {}
    for p in folder.iterdir():
        if p.is_file():
            result[p.name] = p.stat().st_mtime
    return result


def has_temp_file(folder: Path) -> bool:
    temp_suffixes = (".crdownload", ".tmp", ".part")
    for p in folder.iterdir():
        if p.is_file() and p.name.endswith(temp_suffixes):
            return True
    return False


def wait_for_download(folder: Path, before_snapshot: dict[str, float], timeout: int = 60) -> Path:
    end_time = time.time() + timeout

    while time.time() < end_time:
        candidates = []

        for p in folder.iterdir():
            if not p.is_file():
                continue

            if p.name.endswith((".crdownload", ".tmp", ".part")):
                continue

            old_mtime = before_snapshot.get(p.name)
            new_mtime = p.stat().st_mtime

            if old_mtime is None:
                candidates.append(p)
            elif new_mtime > old_mtime + 0.3:
                candidates.append(p)

        if candidates and not has_temp_file(folder):
            candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return candidates[0]

        time.sleep(1)

    raise TimeoutException("다운로드 완료 파일을 찾지 못했습니다.")


def click_by_js(driver, element):
    driver.execute_script(
        """
        arguments[0].scrollIntoView({block: 'center', inline: 'center'});
        arguments[0].click();
        """,
        element,
    )


def set_month_value(driver, input_el, ym: str):
    driver.execute_script(
        """
        const el = arguments[0];
        const value = arguments[1];

        el.removeAttribute('readonly');
        el.focus();
        el.value = '';
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        """,
        input_el,
        ym,
    )


def build_driver(download_dir: Path):
    options = webdriver.ChromeOptions()
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    return driver


def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    downloaded_months = load_downloaded_months(DOWNLOAD_DIR)
    print(f"[기존파일] 이미 다운로드된 월 수: {len(downloaded_months)}")

    driver = build_driver(DOWNLOAD_DIR)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(URL)
        print(f"[시작] 페이지 접속 완료: {URL}")
        time.sleep(INITIAL_WAIT_SEC)

        for ym in month_range(START_MONTH, END_MONTH):
            if ym in downloaded_months:
                print(f"[PASS] {ym} 이미 있음")
                continue

            try:
                print(f"\n[진행] {ym}")

                date_input = wait.until(EC.presence_of_element_located((By.ID, "startDate")))
                set_month_value(driver, date_input, ym)

                current_value = date_input.get_attribute("value")
                print(f"[입력] startDate = {current_value}")

                search_btn = wait.until(EC.element_to_be_clickable((By.ID, "dateSearchT1")))
                click_by_js(driver, search_btn)
                print("[클릭] 검색")
                time.sleep(SEARCH_WAIT_SEC)

                before_snapshot = snapshot_dir(DOWNLOAD_DIR)

                download_btn = wait.until(EC.element_to_be_clickable((By.ID, "excelDown")))
                click_by_js(driver, download_btn)
                print("[클릭] 다운로드")
                time.sleep(DOWNLOAD_CLICK_WAIT_SEC)

                downloaded_file = wait_for_download(
                    DOWNLOAD_DIR,
                    before_snapshot,
                    timeout=DOWNLOAD_FINISH_TIMEOUT_SEC,
                )

                suffix = downloaded_file.suffix if downloaded_file.suffix else ".xlsx"
                target_file = DOWNLOAD_DIR / f"{FILE_PREFIX}{ym}{suffix}"

                if downloaded_file.resolve() != target_file.resolve():
                    if target_file.exists():
                        target_file.unlink()
                    downloaded_file.rename(target_file)

                downloaded_months.add(ym)
                print(f"[완료] {ym} -> {target_file.name}")

            except Exception as e:
                print(f"[실패] {ym} / {e}")

        print("\n[종료] 전체 작업 완료")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()