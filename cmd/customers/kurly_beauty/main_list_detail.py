import os
import re
import requests
import pandas as pd


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


def get_kurly_detail_and_save_images(no, category_no, category_name, cookie_str=""):
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

    data = res.json().get("data", {})
    product_detail = data.get("product_detail", {})

    legacy_content = str(product_detail.get("legacy_content") or "")
    legacy_pi_images = product_detail.get("legacy_pi_images") or []

    content_imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', legacy_content, flags=re.I)
    last_content_img = content_imgs[-1] if content_imgs else ""

    image_urls = []
    if last_content_img:
        image_urls.append(last_content_img)

    for img_url in legacy_pi_images:
        img_url = str(img_url).strip()
        if img_url:
            image_urls.append(img_url)

    category_folder = safe_folder_name(category_name)
    root_dir = os.path.join(os.getcwd(), "상세페이지", category_folder)
    save_dir = os.path.join(root_dir, str(no))
    os.makedirs(save_dir, exist_ok=True)

    image_names = []
    download_yn = "Y"
    memo_list = []

    for idx, img_url in enumerate(image_urls, 1):
        try:
            ext = ".jpg"
            m = re.search(r"\.(jpg|jpeg|png|webp|gif)(?:\?|$)", img_url, flags=re.I)
            if m:
                ext = "." + m.group(1).lower()

            file_name = f"{no}_{idx}{ext}"
            file_path = os.path.join(save_dir, file_name)

            img_res = requests.get(img_url, headers={"user-agent": "Mozilla/5.0"}, timeout=30)
            img_res.raise_for_status()

            with open(file_path, "wb") as f:
                f.write(img_res.content)

            image_names.append(idx)

        except Exception as e:
            download_yn = "N"
            memo_list.append(f"{idx}:{e}")

    memo = " | ".join(memo_list)

    return {
        "카테고리명": category_name,
        "카테고리번호": category_no,
        "제품번호": no,
        "제품명": data.get("name", ""),
        "제품 가격": data.get("retail_price"),
        "제품 할인된가격": data.get("base_price"),
        "할인율": data.get("discount_rate"),
        "상세이미지폴더": f"상세페이지/{category_folder}/{no}",
        "URL": f"https://www.kurly.com/goods/{no}",
        "이미지명": str(image_names),
        "다운로드": download_yn,
        "메모": memo,
    }


def run_kurly_top50_by_categories(cookie_str="", excel_name="kurly_detail.xlsx"):
    rows = []

    for cate in CATEGORY_LIST:
        category_no = cate["category_no"]
        category_name = cate["category_name"]

        print(f"\n===== 카테고리 시작: {category_name} ({category_no}) =====")
        product_list = get_kurly_list(cookie_str=cookie_str, category_no=category_no)
        top50 = product_list[:50]

        for idx, item in enumerate(top50, 1):
            no = item.get("no")
            try:
                row = get_kurly_detail_and_save_images(
                    no=no,
                    category_no=category_no,
                    category_name=category_name,
                    cookie_str=cookie_str,
                )
                rows.append(row)
                print(f"완료: {category_name} {idx}/50 no={no}")
            except Exception as e:
                rows.append({
                    "카테고리명": category_name,
                    "카테고리번호": category_no,
                    "제품번호": no,
                    "제품명": item.get("name", ""),
                    "제품 가격": "",
                    "제품 할인된가격": "",
                    "할인율": "",
                    "상세이미지폴더": "",
                    "URL": f"https://www.kurly.com/goods/{no}",
                    "이미지명": "[]",
                    "다운로드": "N",
                    "메모": str(e),
                })
                print(f"실패: {category_name} no={no} / {e}")

    df = pd.DataFrame(rows, columns=[
        "카테고리명",
        "카테고리번호",
        "제품번호",
        "제품명",
        "제품 가격",
        "제품 할인된가격",
        "할인율",
        "상세이미지폴더",
        "URL",
        "이미지명",
        "다운로드",
        "메모",
    ])
    df.to_excel(excel_name, index=False)
    print(f"\n엑셀 저장 완료: {excel_name}")

    return rows


if __name__ == "__main__":
    cookie_str = ""

    result = run_kurly_top50_by_categories(
        cookie_str=cookie_str,
        excel_name="kurly_detail.xlsx",
    )

    print(result)