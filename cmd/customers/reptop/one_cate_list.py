import json
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


# 부모 카테고리 목록
PARENT_CATEGORIES = [
    {"cate_no": 47, "name": "BEST"},
    {"cate_no": 1637, "name": "가방"},
    {"cate_no": 1667, "name": "지갑"},
    {"cate_no": 1714, "name": "시계"},
    {"cate_no": 1683, "name": "신발"},
    {"cate_no": 1740, "name": "벨트"},
    {"cate_no": 1748, "name": "악세사리"},
    {"cate_no": 1742, "name": "여성의류"},
    {"cate_no": 1741, "name": "남성의류"},
    {"cate_no": 1743, "name": "아우터"},
    {"cate_no": 1744, "name": "패딩"},
    {"cate_no": 1633, "name": "수영복"}
]


def get_cate_no(href):
    query = parse_qs(urlparse(href).query)
    return int(query["cate_no"][0])


def get_children(parent_cate_no):
    url = f"https://reptop.kr/product/list.html?cate_no={parent_cate_no}"

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    children = []

    for link in soup.select(".sidebar-category a.depth1-link"):
        href = link.get("href", "")
        name = link.get_text(" ", strip=True).lstrip("›").strip()

        if "cate_no=" not in href:
            continue

        cate_no = get_cate_no(href)

        children.append({
            "cate_no": cate_no,
            "name": name
        })

    return children


def main():
    result = []

    for parent in PARENT_CATEGORIES:
        children = get_children(parent["cate_no"])

        result.append({
            "cate_no": parent["cate_no"],
            "name": parent["name"],
            "has_children": len(children) > 0,
            "children": children
        })

        print(
            f'{parent["name"]}: '
            f'{len(children)}개 자식 카테고리 수집'
        )

    with open("categories.json", "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print("완료: categories.json 파일로 저장했습니다.")


if __name__ == "__main__":
    main()