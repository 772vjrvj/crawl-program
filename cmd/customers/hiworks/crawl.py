# -*- coding: utf-8 -*-
import os
import re
import sys
import time
import shutil

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


# === 실행 경로 기준 import ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.utils.selenium_utils import SeleniumUtils


LOGIN_URL = "https://mails.office.hiworks.com"
PAGE_URL = (
    "https://mails.office.hiworks.com/list/inbox"
    "?DSto=selah%40promatch.co.kr&DShasAttachment=true&page={page}&returnInfo=inbox"
)

START_PAGE = 1
END_PAGE = 91

# 임시 다운로드 폴더
DOWNLOAD_DIR = r"C:\Users\772vj\Downloads\hiworks_tmp"

# 완료 파일 보관 폴더
RESULT_DIR = os.path.join(BASE_DIR, "result")


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def ensure_dirs():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(RESULT_DIR, exist_ok=True)


def clear_download_dir():
    if not os.path.isdir(DOWNLOAD_DIR):
        return

    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            log(f"임시 다운로드 폴더 정리 실패: {path} / {e}")


def set_download_dir(driver, download_dir):
    os.makedirs(download_dir, exist_ok=True)

    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": download_dir,
            }
        )
        log(f"다운로드 폴더 설정 완료: {download_dir}")
        return
    except Exception:
        pass

    try:
        driver.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": download_dir,
                "eventsEnabled": True,
            }
        )
        log(f"다운로드 폴더 설정 완료: {download_dir}")
    except Exception as e:
        log(f"다운로드 폴더 설정 실패: {e}")


def wait_ready(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def find_visible(driver, xpath, timeout=10):
    return WebDriverWait(driver, timeout).until(
        lambda d: next(
            (el for el in d.find_elements(By.XPATH, xpath) if el.is_displayed()),
            False
        )
    )


def find_visible_any(driver, xpaths, timeout=10):
    return WebDriverWait(driver, timeout).until(
        lambda d: next(
            (
                el
                for xpath in xpaths
                for el in d.find_elements(By.XPATH, xpath)
                if el.is_displayed()
            ),
            False
        )
    )


def js_click(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
        element
    )
    time.sleep(0.3)

    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def click_first_checkbox(driver):
    xpath = "(//span[@role='checkbox' and contains(@class,'Checkbox_checkbox-surface')])[1]"
    el = find_visible(driver, xpath, timeout=12)
    js_click(driver, el)
    log("첫 번째 체크박스 클릭")


def click_other_work(driver):
    xpaths = [
        "//*[contains(@class,'DropdownButton_label') and normalize-space()='다른 작업']",
        "//span[normalize-space()='다른 작업']",
        "//button[.//*[normalize-space()='다른 작업']]",
        "//*[self::button or self::span or self::div][normalize-space()='다른 작업']",
    ]
    el = find_visible_any(driver, xpaths, timeout=15)
    js_click(driver, el)
    log("'다른 작업' 클릭")


def click_download_pc(driver):
    xpaths = [
        "//*[contains(@class,'DropdownOption_truncate') and normalize-space()='다운로드(PC 저장)']",
        "//span[normalize-space()='다운로드(PC 저장)']",
        "//*[self::button or self::span or self::div][normalize-space()='다운로드(PC 저장)']",
    ]
    el = find_visible_any(driver, xpaths, timeout=15)
    js_click(driver, el)
    log("'다운로드(PC 저장)' 클릭")


def wait_download_complete(download_dir, timeout=180):
    end_time = time.time() + timeout
    last_zip = None

    while time.time() < end_time:
        names = os.listdir(download_dir)

        # 다운로드 중 파일 있으면 계속 대기
        cr_files = [x for x in names if x.lower().endswith(".crdownload")]
        if cr_files:
            time.sleep(1)
            continue

        zip_files = []
        for name in names:
            path = os.path.join(download_dir, name)
            if os.path.isfile(path) and name.lower().endswith(".zip"):
                zip_files.append(path)

        if zip_files:
            zip_files.sort(key=os.path.getmtime, reverse=True)
            last_zip = zip_files[0]

            size1 = os.path.getsize(last_zip)
            time.sleep(1)
            if not os.path.exists(last_zip):
                continue
            size2 = os.path.getsize(last_zip)

            if size1 == size2:
                return last_zip

        time.sleep(1)

    return last_zip


def move_zip_to_result(zip_path, page):
    if not zip_path or not os.path.exists(zip_path):
        raise Exception("완료된 zip 파일이 없습니다.")

    ext = os.path.splitext(zip_path)[1] or ".zip"
    result_name = f"download_{page:03d}{ext}"
    result_path = os.path.join(RESULT_DIR, result_name)

    if os.path.exists(result_path):
        os.remove(result_path)

    shutil.move(zip_path, result_path)
    return result_path


def get_done_pages():
    done_pages = set()

    if not os.path.isdir(RESULT_DIR):
        return done_pages

    for name in os.listdir(RESULT_DIR):
        m = re.match(r"^download_(\d{3})\.zip$", name, re.IGNORECASE)
        if not m:
            continue

        page = int(m.group(1))
        if START_PAGE <= page <= END_PAGE:
            done_pages.add(page)

    return done_pages


def get_target_pages():
    done_pages = get_done_pages()
    return [page for page in range(START_PAGE, END_PAGE + 1) if page not in done_pages]


def process_page(driver, page):
    result_path = os.path.join(RESULT_DIR, f"download_{page:03d}.zip")
    if os.path.exists(result_path):
        log(f"[page={page}] 이미 완료됨, 건너뜀: {result_path}")
        return

    url = PAGE_URL.format(page=page)
    log(f"페이지 이동: {page} / {url}")

    clear_download_dir()

    driver.get(url)
    wait_ready(driver)
    time.sleep(2)

    click_first_checkbox(driver)
    time.sleep(1)

    click_other_work(driver)
    time.sleep(1)

    click_download_pc(driver)

    zip_path = wait_download_complete(DOWNLOAD_DIR, timeout=180)
    if not zip_path:
        raise Exception("zip 다운로드 완료 확인 실패")

    result_path = move_zip_to_result(zip_path, page)
    log(f"완료 파일 이동: {result_path}")

    time.sleep(1)


def main():
    ensure_dirs()

    target_pages = get_target_pages()
    if not target_pages:
        log("이미 모든 페이지 zip 이 존재합니다. 작업 종료")
        return

    log(f"재시작 대상 페이지: {target_pages}")
    log(f"첫 시작 페이지: {target_pages[0]}")

    su = SeleniumUtils(headless=False, debug=True)
    driver = None

    try:
        driver = su.start_driver(
            timeout=30,
            view_mode="browser",
            window_size=(1400, 900),
        )

        set_download_dir(driver, DOWNLOAD_DIR)

        driver.get(LOGIN_URL)
        wait_ready(driver)

        input("\n로그인 후 엔터를 치세요...\n")

        for page in target_pages:
            success = False

            for attempt in range(1, 4):
                try:
                    log(f"[page={page}] 시도 {attempt}/3")
                    process_page(driver, page)
                    success = True
                    break

                except TimeoutException as e:
                    log(f"[page={page}] timeout {attempt}/3 : {e}")
                except Exception as e:
                    log(f"[page={page}] error {attempt}/3 : {e}")

                time.sleep(2)

            if not success:
                log(f"[page={page}] 최종 실패, 다음 재실행 때 다시 시도됨")

        remain_pages = get_target_pages()
        if remain_pages:
            log(f"남은 페이지: {remain_pages}")
        else:
            log("전체 작업 완료")

    finally:
        su.quit()


if __name__ == "__main__":
    main()