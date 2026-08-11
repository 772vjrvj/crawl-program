import csv
import json
import threading
import requests

from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


BASE_URL = "https://reptop.kr/product/list.html"
CATEGORY_FILE = "categories.json"
RESULT_FILE = "products.csv"

MAX_WORKERS = 8

# 스레드마다 별도의 Session 사용
thread_local = threading.local()


def get_session():
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0"
        })
        thread_local.session = session

    return thread_local.session


def get_products(cate_no, page):
    session = get_session()

    response = session.get(
        BASE_URL,
        params={
            "cate_no": cate_no,
            "page": page
        },
        timeout=10
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    products = []

    for item in soup.select(".prdList > li[id^='anchorBoxId_']"):
        product_no = item.get("id", "").replace("anchorBoxId_", "")
        name_element = item.select_one(".description .name a")

        if not product_no or not name_element:
            continue

        product_name = (
            name_element
            .get_text(" ", strip=True)
            .replace("상품명 :", "")
            .strip()
        )

        products.append({
            "product_no": product_no,
            "product_name": product_name
        })

    return products


def collect_category_products(parent, child):
    cate_no = child["cate_no"] if child else parent["cate_no"]
    child_cate_no = child["cate_no"] if child else ""
    child_name = child["name"] if child else ""

    rows = []
    page = 1

    while True:
        products = get_products(cate_no, page)

        # 상품이 없는 페이지가 나오면 종료
        if not products:
            break

        for product in products:
            rows.append([
                parent["cate_no"],
                parent["name"],
                child_cate_no,
                child_name,
                page,
                product["product_no"],
                product["product_name"]
            ])

        print(
            f'부모: {parent["name"]} | '
            f'자식: {child_name or "없음"} | '
            f'페이지: {page} | '
            f'상품: {len(products)}개'
        )

        page += 1

    return rows


def create_tasks(categories):
    tasks = []

    for parent in categories:
        children = parent.get("children", [])

        if children:
            for child in children:
                tasks.append((parent, child))
        else:
            tasks.append((parent, None))

    return tasks


def main():
    with open(CATEGORY_FILE, "r", encoding="utf-8") as file:
        categories = json.load(file)

    tasks = create_tasks(categories)
    result = []

    print(
        f"수집 시작: {len(tasks)}개 카테고리, "
        f"{MAX_WORKERS}개 스레드"
    )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                collect_category_products,
                parent,
                child
            ): (parent, child)
            for parent, child in tasks
        }

        for future in as_completed(futures):
            parent, child = futures[future]

            try:
                rows = future.result()
                result.extend(rows)

                print(
                    f'완료: {parent["name"]} > '
                    f'{child["name"] if child else "자식 없음"} | '
                    f'{len(rows)}개'
                )

            except Exception as error:
                print(
                    f'오류: {parent["name"]} > '
                    f'{child["name"] if child else "자식 없음"} | '
                    f'{error}'
                )

    # 멀티스레드 작업 완료 순서와 관계없이 정렬
    result.sort(
        key=lambda row: (
            int(row[0]),
            int(row[2]) if row[2] != "" else 0,
            int(row[4]),
            int(row[5])
        )
    )

    with open(
            RESULT_FILE,
            "w",
            newline="",
            encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "parent_cate_no",
            "parent_category",
            "child_cate_no",
            "child_category",
            "page",
            "product_no",
            "product_name"
        ])

        writer.writerows(result)

    print(
        f"전체 완료: 총 {len(result)}개 상품을 "
        f"{RESULT_FILE}에 저장했습니다."
    )


if __name__ == "__main__":
    main()