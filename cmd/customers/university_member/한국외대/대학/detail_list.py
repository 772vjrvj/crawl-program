# -*- coding: utf-8 -*-
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DEPT_URL_LIST = [
    {
        "구분1": "대학",
        "구분2": "영어대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11224/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "중국학대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11227/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "일본학대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11228/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "사회과학대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11229/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "상경대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11230/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "경영대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11231/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "AI융합대학",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11233/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "국제학부",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11234/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "Language & Diplomacy학부",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11235/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "Language & Trade학부",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11236/subview.do",
    },
    {
        "구분1": "대학",
        "구분2": "KFL학부",
        "구분3": "",
        "URL": "https://www.hufs.ac.kr/hufs/11237/subview.do",
    },
]

def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_detail_dept_list(dept_list: list[dict]) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )
    }

    session = requests.Session()
    result_list: list[dict] = []

    for dept in dept_list:
        parent_url = dept["URL"]
        print(f"[INFO] 요청: {parent_url}")

        try:
            resp = session.get(parent_url, headers=headers, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"[ERROR] 요청 실패: {parent_url} / {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # 각 학과/전공 블록
        blocks = soup.select("div.heading-buttuon.type2")

        if not blocks:
            print(f"[WARN] 상세 블록 없음: {parent_url}")
            continue

        for block in blocks:
            title_el = block.select_one(".left .dp-title")
            link_el = block.select_one(".right a[href]")

            sub_name = clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
            detail_url = urljoin(parent_url, link_el.get("href", "").strip()) if link_el else ""

            row = {
                "구분1": dept.get("구분1", ""),
                "구분2": dept.get("구분2", ""),
                "구분3": sub_name,
                "URL": parent_url,
                "DETAIL_URL": detail_url,
            }
            result_list.append(row)

    return result_list


DETAIL_DEPT_URL_LIST = fetch_detail_dept_list(DEPT_URL_LIST)

print(DETAIL_DEPT_URL_LIST)
