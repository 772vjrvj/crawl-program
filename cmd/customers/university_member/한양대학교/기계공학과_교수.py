# -*- coding: utf-8 -*-

import re
import time
from datetime import datetime

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


URL = "https://me.hanyang.ac.kr/kor/member/member_01.html#contents"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_name(text):
    text = clean_text(text)
    text = text.replace("연구석학교수", "")
    text = text.replace("석학교수", "")
    text = text.replace("명예교수", "")
    text = text.replace("부교수", "")
    text = text.replace("조교수", "")
    text = text.replace("교수", "")
    return clean_text(text)


def make_driver():
    options = Options()

    # 화면 보면서 테스트할 때는 headless 끄는 게 좋음
    # options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    return driver


def collect_professor_list(driver):
    wait = WebDriverWait(driver, 15)

    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".bottom_list li")) > 0)

    rows = []
    seen_uid = set()

    items = driver.find_elements(By.CSS_SELECTOR, ".bottom_list li")

    for item in items:
        try:
            btn = item.find_element(By.CSS_SELECTOR, ".plus_btn[data-uid]")
            uid = btn.get_attribute("data-uid")

            if not uid or uid in seen_uid:
                continue

            seen_uid.add(uid)

            name = ""

            try:
                name = item.find_element(By.CSS_SELECTOR, ".name a").text
            except:
                pass

            if not name:
                try:
                    name = item.find_element(By.CSS_SELECTOR, "img").get_attribute("alt")
                except:
                    pass

            rows.append({
                "uid": uid,
                "name": clean_name(name),
            })

        except:
            continue

    return rows


def click_plus_button(driver, uid):
    buttons = driver.find_elements(By.CSS_SELECTOR, ".bottom_list a.plus_btn[data-uid='%s']" % uid)

    if not buttons:
        buttons = driver.find_elements(By.CSS_SELECTOR, ".bottom_list .plus_btn[data-uid='%s']" % uid)

    if not buttons:
        return False

    btn = buttons[-1]

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", btn)

    return True


def get_popup_text(driver):
    wait = WebDriverWait(driver, 10)

    def has_email(d):
        candidates = d.find_elements(By.CSS_SELECTOR, ".content_bx, .professor_info, .popup, .modal")
        for el in candidates:
            try:
                txt = el.text
                if re.search(EMAIL_RE, txt):
                    return txt
            except:
                pass
        return False

    try:
        return wait.until(has_email)
    except:
        return ""


def close_popup(driver):
    close_selectors = [
        ".close_btn",
        ".popup_close",
        ".btn_close",
        ".xi-close",
        ".modal-close",
        ".modal_close",
        "button.close",
    ]

    for selector in close_selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
                    return
        except:
            pass

    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except:
        pass


def collect_email_by_click(driver, prof):
    uid = prof["uid"]

    # 목록에서 가져온 이름만 사용
    name = prof["name"]

    print("[진행]", name, uid)

    ok = click_plus_button(driver, uid)
    if not ok:
        print("[실패] 버튼 없음:", name)
        return {
            "이름": name,
            "이메일": "",
        }

    popup_text = get_popup_text(driver)

    email = ""
    found = re.findall(EMAIL_RE, popup_text)
    if found:
        email = found[0].strip()

    close_popup(driver)

    print("[수집]", name, email)

    return {
        "이름": name,
        "이메일": email,
    }

def main():
    driver = make_driver()

    try:
        print("[시작]", URL)
        driver.get(URL)

        time.sleep(2)

        profs = collect_professor_list(driver)
        print("[교수 목록 수]", len(profs))

        result = []
        seen_email = set()

        for prof in profs:
            row = collect_email_by_click(driver, prof)

            # 이메일 중복 제거
            email_key = row["이메일"].lower()
            if email_key and email_key in seen_email:
                continue

            if email_key:
                seen_email.add(email_key)

            result.append(row)

        df = pd.DataFrame(result, columns=["이름", "이메일"])

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_name = "한양대_기계공학부_교수_이메일_%s.xlsx" % now

        df.to_excel(excel_name, index=False)

        print()
        print("===== 엑셀 붙여넣기용 =====")
        print(df.to_csv(sep="\t", index=False))

        print("[완료]", excel_name)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()