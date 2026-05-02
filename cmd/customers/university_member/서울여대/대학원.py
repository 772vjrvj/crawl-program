import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ==============================
# 교수 페이지
# ==============================
professor_pages = [
    # ==============================
    # 특수치료전문대학원
    # ==============================
    ["특수치료전문대학원", "특수치료전문대학원", "특수치료전문대학원", "https://www.swu.ac.kr/therapy/thprof.html"],

    # ==============================
    # 휴먼서비스대학원
    # ==============================
    ["휴먼서비스대학원", "휴먼서비스대학원", "가족상담전공", "https://www.swu.ac.kr/human/huchrist_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "인성교육전공", "https://www.swu.ac.kr/human/huedu_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "도서관·정보정책전공", "https://www.swu.ac.kr/human/hulib_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "영유아보육학전공", "https://www.swu.ac.kr/human/huchi_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "스포츠헬스케어전공", "https://www.swu.ac.kr/human/humov_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "사회복지실천행정전공", "https://www.swu.ac.kr/human/huso_2.html"],
    ["휴먼서비스대학원", "휴먼서비스대학원", "외국어로서의 한국어교육전공", "https://www.swu.ac.kr/human/hufor_2.html"],

    # ==============================
    # 교육대학원
    # ==============================
    ["교육대학원", "교육대학원", "국어교육전공", "https://www.swu.ac.kr/edu/edukor_2.html"],
    ["교육대학원", "교육대학원", "상담심리전공", "https://www.swu.ac.kr/edu/educoun_2.html"],
    ["교육대학원", "교육대학원", "유아교육전공", "https://www.swu.ac.kr/edu/educhild_2.html"],
    ["교육대학원", "교육대학원", "체육교육전공", "https://www.swu.ac.kr/edu/eduphy_2.html"],

    # ==============================
    # 일반대학원 - 인문계열
    # ==============================
    ["일반대학원", "인문계열", "국어국문학과", "https://www.swu.ac.kr/grd/unlibera_2.html"],
    ["일반대학원", "인문계열", "영어영문학과", "https://www.swu.ac.kr/grd/unliberb_2.html"],
    ["일반대학원", "인문계열", "불어불문학과", "https://www.swu.ac.kr/grd/unliberc_2.html"],
    ["일반대학원", "인문계열", "독어독문학과", "https://www.swu.ac.kr/grd/unliberd_2.html"],
    ["일반대학원", "인문계열", "중어중문학과", "https://www.swu.ac.kr/grd/unlibere_2.html"],
    ["일반대학원", "인문계열", "사학과", "https://www.swu.ac.kr/grd/unliberf_2.html"],
    ["일반대학원", "인문계열", "기독교학과", "https://www.swu.ac.kr/grd/unliberg_2.html"],

    # ==============================
    # 일반대학원 - 사회계열
    # ==============================
    ["일반대학원", "사회계열", "경영학과", "https://www.swu.ac.kr/grd/unsociencea_2.html"],
    ["일반대학원", "사회계열", "경제학과", "https://www.swu.ac.kr/grd/unsocienceb_2.html"],
    ["일반대학원", "사회계열", "사회복지학과", "https://www.swu.ac.kr/grd/unsociencec_2.html"],
    ["일반대학원", "사회계열", "문헌정보학과", "https://www.swu.ac.kr/grd/unsocienced_2.html"],
    ["일반대학원", "사회계열", "아동학과", "https://www.swu.ac.kr/grd/unsociencee_2.html"],
    ["일반대학원", "사회계열", "심리·인지과학학과", "https://www.swu.ac.kr/grd/unsociencef_2.html"],
    ["일반대학원", "사회계열", "행정학과", "https://www.swu.ac.kr/grd/unsocienceg_2.html"],
    ["일반대학원", "사회계열", "언론영상학과", "https://www.swu.ac.kr/grd/unsocienceh_2.html"],
    ["일반대학원", "사회계열", "국제개발협력학과", "https://www.swu.ac.kr/grd/unsociencei_2.html"],
    ["일반대학원", "사회계열", "공공빅데이터관리학과(학․연․산 협동과정)", "https://www.swu.ac.kr/grd/unsociencej_2.html"],
    ["일반대학원", "사회계열", "예술심리치료학과", "https://www.swu.ac.kr/grd/unsociencek_2.html"],

    # ==============================
    # 일반대학원 - 자연계열
    # ==============================
    ["일반대학원", "자연계열", "원예생명조경학과", "https://www.swu.ac.kr/grd/unnatusca_2.html"],
    ["일반대학원", "자연계열", "의류학과", "https://www.swu.ac.kr/grd/unnatuscb_2.html"],
    ["일반대학원", "자연계열", "식품공학과", "https://www.swu.ac.kr/grd/unnatuscc_2.html"],
    ["일반대학원", "자연계열", "식품영양학과", "https://www.swu.ac.kr/grd/unnatuscd_2.html"],
    ["일반대학원", "자연계열", "화학과", "https://www.swu.ac.kr/grd/unnatusce_2.html"],
    ["일반대학원", "자연계열", "생명환경공학과", "https://www.swu.ac.kr/grd/unnatuscf_2.html"],
    ["일반대학원", "자연계열", "수학과", "https://www.swu.ac.kr/grd/unnatuscg_2.html"],
    ["일반대학원", "자연계열", "컴퓨터학과", "https://www.swu.ac.kr/grd/unnatusch_2.html"],
    ["일반대학원", "자연계열", "바이오헬스공학과(학과간 협동과정)", "https://www.swu.ac.kr/grd/unnatusci_2.html"],

    # ==============================
    # 일반대학원 - 예체능계열
    # ==============================
    ["일반대학원", "예체능계열", "조형학과 공예학", "https://www.swu.ac.kr/grd/unarta_2.html"],
    ["일반대학원", "예체능계열", "조형학과 현대미술", "https://www.swu.ac.kr/grd/unartb_2.html"],
    ["일반대학원", "예체능계열", "디자인학과 타이포그라피전공", "https://www.swu.ac.kr/grd/unartcb_2.html"],
    ["일반대학원", "예체능계열", "디자인학과 인터랙션디자인전공", "https://www.swu.ac.kr/grd/unartc_2.html"],
    ["일반대학원", "예체능계열", "스포츠운동과학과", "https://www.swu.ac.kr/grd/unartd_2.html"],

    # ==============================
    # 일반대학원 - 협동과정
    # ==============================
    ["일반대학원", "협동과정", "공공빅데이터관리학과", "https://www.swu.ac.kr/grd/uncola_2.html"],
    ["일반대학원", "협동과정", "바이오헬스공학과", "https://www.swu.ac.kr/grd/uncolb_2.html"],
    ["일반대학원", "협동과정", "예술심리치료학과", "https://www.swu.ac.kr/grd/uncolc_2.html"],
    ["일반대학원", "협동과정", "아트앤테크놀로지학과", "https://www.swu.ac.kr/grd/uncold_2.html"],
    ["일반대학원", "협동과정", "AI기술융합학과", "https://www.swu.ac.kr/grd/uncole_2.html"],
    ["일반대학원", "협동과정", "글로벌비즈니스학과", "https://www.swu.ac.kr/grd/uncolf_2.html"],
    ["일반대학원", "협동과정", "AI안전·신뢰성학과", "https://www.swu.ac.kr/grd/uncolg_2.html"],
    ["일반대학원", "협동과정", "사회혁신융합학과", "https://www.swu.ac.kr/grd/uncolh_2.html"],
]


# ==============================
# 교학팀 페이지
# ==============================
staff_pages = [
    ["교육대학원", "교육대학원", "교학팀", "https://www.swu.ac.kr/edu/edutint.html"],
    ["일반대학원", "일반대학원", "교학팀", "https://www.swu.ac.kr/grd/intedu.html"],
]


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def get_email(text):
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def get_html(url):
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    res.encoding = res.apparent_encoding
    return res.text


def parse_professor_page(big, middle, small, url):
    soup = BeautifulSoup(get_html(url), "html.parser")
    rows = []

    for name_tag in soup.select(".name"):
        name = name_tag.get_text(strip=True).replace("교수", "").strip()

        box = name_tag.find_parent("li")
        text = box.get_text(" ", strip=True) if box else name_tag.parent.get_text(" ", strip=True)
        email = get_email(text)

        rows.append({
            "대분류": big,
            "중분류": middle,
            "소분류": small,
            "이름": name,
            "업무": "교육·연구",
            "직위": "교수",
            "연락처": email,
            "URL": url,
        })

    return rows


def parse_staff_page(driver, big, middle, small, url):
    driver.get(url)

    WebDriverWait(driver, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".table0.center table tr")) > 1
    )

    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = []

    for tr in soup.select(".table0.center table tr"):
        cols = tr.select("td")

        if len(cols) < 5:
            continue

        position = clean(cols[0].get_text(" ", strip=True))
        name = clean(cols[1].get_text(" ", strip=True))
        email = get_email(cols[3].get_text(" ", strip=True))
        work = clean(cols[4].get_text(" / ", strip=True))

        if name == "이름":
            continue

        rows.append({
            "대분류": big,
            "중분류": middle,
            "소분류": small,
            "이름": name,
            "업무": work,
            "직위": position,
            "연락처": email,
            "URL": url,
        })

    return rows


def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    return webdriver.Chrome(options=options)


def main():
    result = []

    for big, middle, small, url in professor_pages:
        try:
            rows = parse_professor_page(big, middle, small, url)
            result.extend(rows)
            print(f"[교수] {big} / {middle} / {small} : {len(rows)}건")

        except Exception as e:
            print(f"[교수 ERROR] {url} : {e}")

    driver = get_driver()

    try:
        for big, middle, small, url in staff_pages:
            try:
                rows = parse_staff_page(driver, big, middle, small, url)
                result.extend(rows)
                print(f"[교학팀] {big} / {middle} / {small} : {len(rows)}건")

            except Exception as e:
                print(f"[교학팀 ERROR] {url} : {e}")

    finally:
        driver.quit()

    columns = [
        "대분류",
        "중분류",
        "소분류",
        "이름",
        "업무",
        "직위",
        "연락처",
        "URL",
    ]

    df = pd.DataFrame(result)
    df = df.reindex(columns=columns)

    df.to_excel("swu_result.xlsx", index=False)
    df.to_csv("swu_result.csv", index=False, encoding="utf-8-sig")

    print()
    print(df)
    print()
    print(f"총 {len(df)}건 저장 완료")


if __name__ == "__main__":
    main()