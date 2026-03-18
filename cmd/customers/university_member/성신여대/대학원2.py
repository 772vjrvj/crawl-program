# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


URL_ROWS = [
    # {
    #     "구분1": "생애복지대학원",
    #     "구분2": "보육학과",
    #     "URL": "https://www.sungshin.ac.kr/fiba/14964/subview.do",
    # },
    # {
    #     "구분1": "생애복지대학원",
    #     "구분2": "건강운동관리학과",
    #     "URL": "https://www.sungshin.ac.kr/fiba/14965/subview.do",
    # },
    {
        "구분1": "생애복지대학원",
        "구분2": "식품영양학과",
        "URL": "https://www.sungshin.ac.kr/fiba/17698/subview.do",
    },
    # {
    #     "구분1": "생애복지대학원",
    #     "구분2": "가족상담‧치료학과",
    #     "URL": "https://www.sungshin.ac.kr/fiba/18263/subview.do",
    # },
]

OUTPUT_CSV = "sungshin_fiba_professors.csv"
MAX_WORKERS = 8
TIMEOUT = 20


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Connection": "keep-alive",
        }
    )
    return session


def extract_table_kv(section: Tag) -> Dict[str, str]:
    data: Dict[str, str] = {}

    table = section.select_one("table.table01")
    if not table:
        return data

    for tr in table.select("tbody tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue

        key = clean_text(th.get_text(" ", strip=True))
        val = clean_text(td.get_text(" ", strip=True))

        if key:
            data[key] = val

    return data


def extract_image_url(section: Tag, page_url: str) -> str:
    img = section.select_one(".pic_area img")
    if not img:
        return ""
    src = clean_text(img.get("src"))
    if not src:
        return ""
    return urljoin(page_url, src)


def parse_professor_sections(html: str, page_url: str, row_meta: Dict[str, str]) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    sections = soup.select("div.section_professor_info")
    results: List[Dict[str, str]] = []

    for idx, section in enumerate(sections, start=1):
        info = extract_table_kv(section)
        image_url = extract_image_url(section, page_url)

        row = {
            "구분1": row_meta.get("구분1", ""),
            "구분2": row_meta.get("구분2", ""),
            "URL": page_url,
            "순번": str(idx),

            "성명": info.get("성명", ""),
            "연구분야": info.get("연구분야", ""),
            "담당과목": info.get("담당과목", ""),
            "연구실": info.get("연구실", ""),
            "전화번호": info.get("전화번호", ""),
            "이메일": info.get("이메일", ""),
            "홈페이지": info.get("홈페이지", ""),
            "이미지URL": image_url,
        }

        # 혹시 사이트마다 항목명이 조금 다를 수 있어서 보조 처리
        if not row["성명"]:
            row["성명"] = info.get("이름", "")

        results.append(row)

    return results


def crawl_one(index: int, row_meta: Dict[str, str]) -> List[Dict[str, str]]:
    url = row_meta["URL"]
    session = create_session()

    try:
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        rows = parse_professor_sections(resp.text, url, row_meta)

        # 정렬 복원을 위해 index 부여
        for r in rows:
            r["_index"] = index

        return rows

    except Exception as e:
        return [
            {
                "구분1": row_meta.get("구분1", ""),
                "구분2": row_meta.get("구분2", ""),
                "URL": url,
                "순번": "",
                "성명": "",
                "연구분야": "",
                "담당과목": "",
                "연구실": "",
                "전화번호": "",
                "이메일": "",
                "홈페이지": "",
                "이미지URL": "",
                "_index": index,
                "_error": clean_text(str(e)),
            }
        ]


def save_csv(rows: List[Dict[str, str]], output_csv: str) -> None:
    fieldnames = [
        "구분1",
        "구분2",
        "성명",
        "연구분야",
        "담당과목",
        "연구실",
        "전화번호",
        "이메일",
        "홈페이지",
        "이미지URL",
        "URL",
        "순번",
    ]

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    all_rows: List[Dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(crawl_one, idx, row): idx
            for idx, row in enumerate(URL_ROWS)
        }

        for future in as_completed(future_map):
            result_rows = future.result()
            all_rows.extend(result_rows)

    # 입력 URL 순서대로 정렬, 같은 페이지 내에서는 순번 유지
    all_rows.sort(key=lambda x: (x.get("_index", 999999), int(x.get("순번", "999999") or "999999")))

    save_csv(all_rows, OUTPUT_CSV)

    print(f"완료: {OUTPUT_CSV}")
    print(f"총 {len(all_rows)}건 저장")


if __name__ == "__main__":
    main()