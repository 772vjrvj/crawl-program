import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


CATEGORY_LIST = [
    {"category_no": 167001, "category_name": "스킨/토너"},
    {"category_no": 167003, "category_name": "에센스/세럼/엠플"},
    {"category_no": 167004, "category_name": "크림"},
    {"category_no": 167008, "category_name": "아이크림"},
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
    result_soup = BeautifulSoup('<div id="detail"></div>', "html.parser")
    result_detail = result_soup.find("div", id="detail")

    origin_detail = soup.find("div", id="detail")
    if origin_detail:
        for child in origin_detail.find_all(recursive=False):
            if child.name == "article":
                break
            if child.name == "div":
                child_soup = BeautifulSoup(str(child), "html.parser")
                result_detail.append(child_soup)

    final_html = str(result_detail)
    has_img = BeautifulSoup(final_html, "html.parser").find("img") is not None
    return final_html, has_img


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


def get_kurly_detail_and_save_html(no, product_name, category_no, category_name, cookie_str=""):
    api_data = fetch_kurly_detail_api(no=no, cookie_str=cookie_str)

    page_url = f"https://www.kurly.com/goods/{no}"
    page_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "referer": "https://www.kurly.com/",
        "user-agent": "Mozilla/5.0",
    }

    if cookie_str.strip():
        page_headers["cookie"] = cookie_str.strip()

    res = requests.get(page_url, headers=page_headers, timeout=30)
    res.raise_for_status()

    final_html, has_img = build_detail_html(res.text)

    category_folder = safe_folder_name(category_name)
    save_root = os.path.join(os.getcwd(), "상세페이지", category_folder)
    os.makedirs(save_root, exist_ok=True)

    html_path = os.path.join(save_root, f"{no}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(final_html)

    memo = ""
    if not has_img:
        memo = "이미지 없음"

    return {
        "카테고리명": category_name,
        "카테고리번호": category_no,
        "제품번호": no,
        "제품명": api_data.get("name") or product_name,
        "제품 가격": api_data.get("retail_price", ""),
        "제품 할인된가격": api_data.get("base_price", ""),
        "할인율": api_data.get("discount_rate", ""),
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
            "URL": f"https://www.kurly.com/goods/{no}",
            "다운로드": "N",
            "메모": str(e),
            "상세HTML경로": "",
        }


def run_kurly_top50_by_categories(cookie_str="", excel_name="kurly_detail.xlsx", max_workers=5):
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
        max_workers=5,
    )

    print(result)