import csv
import re
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


URL = "https://www.kookmin.ac.kr/user/unIntr/unSttu/univOrgn/index.do"
OUTPUT_CSV = "국민대학교 목록.csv"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_view_id(onclick_value: str) -> str:
    """
    onclick="view(10072);" 또는 onclick='view("10370");' 형태에서 ID 추출
    """
    if not onclick_value:
        return ""

    match = re.search(r'view\((?:"|\')?(\d+)(?:"|\')?\)', onclick_value)
    return match.group(1) if match else ""


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def get_direct_child_anchor(li_tag):
    """
    li 바로 아래 자식 중 onclick 속성이 있는 a 태그만 반환
    """
    for child in li_tag.children:
        if getattr(child, "name", None) != "a":
            continue

        if child.get("onclick"):
            return child

    return None


def extract_text_and_id_from_anchor(a_tag) -> Dict[str, str]:
    onclick_value = a_tag.get("onclick", "")
    item_id = extract_view_id(onclick_value)
    text = clean_text(a_tag.get_text(" ", strip=True))
    return {
        "id": item_id,
        "text": text,
    }


def parse_li_list_from_td(td_tag, gu_bun_1: str, gu_bun_2: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    ul_list = td_tag.find_all("ul", recursive=False)
    for ul in ul_list:
        li_list = ul.find_all("li", recursive=False)

        for li in li_list:
            a_tag = get_direct_child_anchor(li)
            if not a_tag:
                continue

            parsed = extract_text_and_id_from_anchor(a_tag)
            if not parsed["id"] and not parsed["text"]:
                continue

            results.append({
                "구분1": gu_bun_1,
                "구분2": gu_bun_2,
                "구분3": parsed["text"],
                "ID": parsed["id"]
            })

    return results


def get_gu_bun_1(cont_box, organ_section) -> str:
    """
    구분1 추출 우선순위
    1. cont_box 내부 table_top
    2. organ_section 내부 cont_tit organ_1dep
    """
    table_top = cont_box.select_one("div.table_top")
    if table_top:
        text = clean_text(table_top.get_text(" ", strip=True))
        if text:
            return text

    organ_1dep = organ_section.select_one("p.cont_tit.organ_1dep")
    if organ_1dep:
        text = clean_text(organ_1dep.get_text(" ", strip=True))
        if text:
            return text

    return ""


def parse_organization(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, str]] = []

    organ_sections = soup.select("div.cont_section.organ")

    for organ_section in organ_sections:
        cont_boxes = organ_section.select("div.cont_box")

        for cont_box in cont_boxes:
            table_wrap = cont_box.select_one("div.table_wrap.write_table")
            if not table_wrap:
                continue

            gu_bun_1 = get_gu_bun_1(cont_box, organ_section)

            tbody = table_wrap.select_one("tbody")
            if not tbody:
                continue

            tr_list = tbody.find_all("tr", recursive=False)

            for tr in tr_list:
                th = tr.find("th", recursive=False)
                td = tr.find("td", recursive=False)

                if not td:
                    continue

                if th:
                    gu_bun_2 = clean_text(th.get_text(" ", strip=True))
                else:
                    gu_bun_2 = ""

                results.extend(parse_li_list_from_td(td, gu_bun_1, gu_bun_2))

    return results


def save_csv(rows: List[Dict[str, str]], output_path: str) -> None:
    fieldnames = ["구분1", "구분2", "구분3", "ID"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    html = fetch_html(URL)
    rows = parse_organization(html)
    save_csv(rows, OUTPUT_CSV)

    print(f"총 {len(rows)}건 저장 완료")
    print(f"저장 파일: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()