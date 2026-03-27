import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


CATEGORY_LIST = [
    # {"category_no": 167001, "category_name": "스킨/토너"},
    {"category_no": 167003, "category_name": "에센스/세럼/엠플"},
    {"category_no": 167004, "category_name": "크림"},
    # {"category_no": 167008, "category_name": "아이크림"},
]


def safe_folder_name(name):
    return str(name).replace("/", "_").replace("\\", "_").strip()


def get_kurly_list(cookie_str="", category_no=167001):
    result = []
    page = 1

    while True:
        url = f"https://api.kurly.com/collection/v2/home/sites/beauty/product-categories/{category_no}/products"
        params = {
            "sort_type": 1,
            "page": page,
            "per_page": 96,
            "filters": "",
        }
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.kurly.com",
            "referer": f"https://www.kurly.com/categories/{category_no}?filters=&page={page}&site=beauty&per_page=96&sorted_type=1",
            "user-agent": "Mozilla/5.0",
        }

        if cookie_str.strip():
            headers["cookie"] = cookie_str.strip()

        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()

        json_data = res.json()
        data = json_data.get("data", [])

        if not data:
            print(f"category={category_no} page={page} 빈배열 -> 중단")
            break

        rows = []
        for item in data:
            rows.append({
                "no": item.get("no"),
                "name": item.get("name", ""),
            })

        print(f"category={category_no} page={page} 수집={len(rows)}건")
        result.extend(rows)
        page += 1

    return result


def build_detail_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    result_soup = BeautifulSoup(
        '''
        <div id="merged_detail" style="width:100%; text-align:center; margin:0 auto;"></div>
        ''',
        "html.parser"
    )
    result_root = result_soup.find("div", id="merged_detail")

    found_description_part = False
    description_type_list = []

    description_div = soup.find("div", id="description")
    if description_div:
        # 1차
        intro_blocks = description_div.find_all(
            "div",
            class_=lambda x: x and ("goods_intro" in x or "about_brand" in x)
        )
        if intro_blocks:
            description_type_list.append("설명유형1")
            for block in intro_blocks:
                found_description_part = True
                block_soup = BeautifulSoup(str(block), "html.parser")
                block_tag = block_soup.find()
                if block_tag:
                    old_style = block_tag.get("style", "")
                    block_tag["style"] = f"{old_style}; text-align:center; margin-left:auto; margin-right:auto;".strip("; ")
                    result_root.append(block_tag)

        # 2차
        goods_desc = description_div.find("div", class_="goods_desc")
        if goods_desc:
            fallback_blocks = goods_desc.find_all(
                "div",
                class_=lambda x: x and "context" in x and "last" in x
            )
            if fallback_blocks:
                description_type_list.append("설명유형2")
                for block in fallback_blocks:
                    found_description_part = True
                    block_soup = BeautifulSoup(str(block), "html.parser")
                    block_tag = block_soup.find()
                    if block_tag:
                        old_style = block_tag.get("style", "")
                        block_tag["style"] = f"{old_style}; text-align:center; margin-left:auto; margin-right:auto;".strip("; ")
                        result_root.append(block_tag)

        # 3차
        third_blocks = []

        custom_blocks = description_div.find_all(attrs={"data-block-type": "CUSTOM"})
        if custom_blocks:
            third_blocks.append(custom_blocks[-1])

        about_brand_blocks = description_div.find_all(attrs={"data-block-type": "ABOUT_BRAND"})
        if about_brand_blocks:
            third_blocks.extend(about_brand_blocks)

        banner_blocks = description_div.find_all(attrs={"data-block-type": "BANNER"})
        if banner_blocks:
            third_blocks.extend(banner_blocks)

        if third_blocks:
            description_type_list.append("설명유형3")
            for block in third_blocks:
                found_description_part = True
                block_soup = BeautifulSoup(str(block), "html.parser")
                block_tag = block_soup.find()
                if block_tag:
                    old_style = block_tag.get("style", "")
                    block_tag["style"] = f"{old_style}; text-align:center; margin-left:auto; margin-right:auto;".strip("; ")
                    result_root.append(block_tag)

    description_type = ",".join(description_type_list)

    found_detail_part = False
    origin_detail = soup.find("div", id="detail")
    if origin_detail:
        detail_wrap_soup = BeautifulSoup(
            '''
            <div id="detail" style="width:100%; text-align:center; margin:0 auto;"></div>
            ''',
            "html.parser"
        )
        detail_wrap = detail_wrap_soup.find("div", id="detail")

        for child in origin_detail.find_all(recursive=False):
            if child.name == "article":
                break
            if child.name == "div":
                found_detail_part = True
                child_soup = BeautifulSoup(str(child), "html.parser")
                child_tag = child_soup.find()
                if child_tag:
                    old_style = child_tag.get("style", "")
                    child_tag["style"] = f"{old_style}; text-align:center; margin-left:auto; margin-right:auto;".strip("; ")
                    detail_wrap.append(child_tag)

        if found_detail_part:
            result_root.append(detail_wrap)

    for img in result_root.find_all("img"):
        old_style = img.get("style", "")
        img["style"] = f"{old_style}; display:block; margin:0 auto;".strip("; ")

    final_html = str(result_root)
    has_img = BeautifulSoup(final_html, "html.parser").find("img") is not None

    return final_html, has_img, found_description_part, found_detail_part, description_type


def fetch_kurly_detail_api(no, cookie_str=""):
    url = f"https://api.kurly.com/showroom/v2/products/{no}"
    params = {"join_order_code": ""}
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://www.kurly.com",
        "referer": f"https://www.kurly.com/goods/{no}",
        "user-agent": "Mozilla/5.0",
    }

    if cookie_str.strip():
        headers["cookie"] = cookie_str.strip()

    res = requests.get(url, params=params, headers=headers, timeout=30)
    res.raise_for_status()

    return res.json().get("data", {})


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,3000")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--user-agent=Mozilla/5.0")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def add_cookies(driver, cookie_str):
    if not cookie_str.strip():
        return

    driver.get("https://www.kurly.com/")
    time.sleep(1)

    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()

        if not name:
            continue

        try:
            driver.add_cookie({
                "name": name,
                "value": value,
                "domain": ".kurly.com",
                "path": "/",
            })
        except Exception:
            pass


def get_rendered_html(page_url, cookie_str=""):
    driver = create_driver()
    try:
        add_cookies(driver, cookie_str)
        driver.get(page_url)

        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "#description img, #detail img")
            )
        except Exception:
            pass

        time.sleep(2)
        return driver.page_source
    finally:
        driver.quit()


def get_kurly_detail_and_save_html(no, product_name, category_no, category_name, cookie_str=""):
    api_data = fetch_kurly_detail_api(no=no, cookie_str=cookie_str)

    page_url = f"https://www.kurly.com/goods/{no}"
    rendered_html = get_rendered_html(page_url=page_url, cookie_str=cookie_str)

    final_html, has_img, found_description_part, found_detail_part, description_type = build_detail_html(rendered_html)

    category_folder = safe_folder_name(category_name)
    save_root = os.path.join(os.getcwd(), "상세페이지", category_folder)
    os.makedirs(save_root, exist_ok=True)

    html_path = os.path.join(save_root, f"{no}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(final_html)

    memo_list = []

    if not found_description_part:
        memo_list.append("설명 없음")
    if not found_detail_part:
        memo_list.append("상세 설명 없음")
    if not has_img:
        memo_list.append("이미지 없음")

    memo = " | ".join(memo_list)

    return {
        "카테고리명": category_name,
        "카테고리번호": category_no,
        "제품번호": no,
        "제품명": api_data.get("name") or product_name,
        "제품 가격": api_data.get("retail_price", ""),
        "제품 할인된가격": api_data.get("base_price", ""),
        "할인율": api_data.get("discount_rate", ""),
        "설명유형": description_type,
        "URL": page_url,
        "다운로드": "Y",
        "메모": memo,
        "상세HTML경로": f"상세페이지/{category_folder}/{no}.html",
    }


def process_one_product(item, category_no, category_name, cookie_str=""):
    no = item.get("no")
    name = item.get("name", "")

    try:
        row = get_kurly_detail_and_save_html(
            no=no,
            product_name=name,
            category_no=category_no,
            category_name=category_name,
            cookie_str=cookie_str,
        )
        print(f"완료: {category_name} no={no}")
        return row
    except Exception as e:
        print(f"실패: {category_name} no={no} / {e}")
        return {
            "카테고리명": category_name,
            "카테고리번호": category_no,
            "제품번호": no,
            "제품명": name,
            "제품 가격": "",
            "제품 할인된가격": "",
            "할인율": "",
            "설명유형": "",
            "URL": f"https://www.kurly.com/goods/{no}",
            "다운로드": "N",
            "메모": str(e),
            "상세HTML경로": "",
        }


def run_kurly_top50_by_categories(cookie_str="", excel_name="kurly_detail.xlsx", max_workers=2):
    rows = []

    for cate in CATEGORY_LIST:
        category_no = cate["category_no"]
        category_name = cate["category_name"]

        print(f"\n===== 카테고리 시작: {category_name} ({category_no}) =====")
        product_list = get_kurly_list(cookie_str=cookie_str, category_no=category_no)
        top50 = product_list[:50]

        futures = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for item in top50:
                future = executor.submit(
                    process_one_product,
                    item,
                    category_no,
                    category_name,
                    cookie_str,
                )
                futures.append(future)

            for future in as_completed(futures):
                rows.append(future.result())

    df = pd.DataFrame(rows, columns=[
        "카테고리명",
        "카테고리번호",
        "제품번호",
        "제품명",
        "제품 가격",
        "제품 할인된가격",
        "할인율",
        "설명유형",
        "URL",
        "다운로드",
        "메모",
        "상세HTML경로",
    ])
    df.to_excel(excel_name, index=False)
    print(f"\n엑셀 저장 완료: {excel_name}")

    return rows


if __name__ == "__main__":
    cookie_str = ""

    result = run_kurly_top50_by_categories(
        cookie_str=cookie_str,
        excel_name="kurly_detail.xlsx",
        max_workers=2,
    )

    print(result)