# -*- coding: utf-8 -*-
"""
국민대학교 목록.csv 를 읽어서
각 ID(deptCd)별 국민대학교 조직도 페이지를 조회한 뒤

1) 행정/직원 prof_list
   - 이름
   - 이메일
   - 직위
   - 보직 및 겸무
   - 담당업무

2) 교수 organ_view > .col_cont.three > .prof_wrap
   - 이름
   - 이메일
   - 직위
   - 보직 및 겸무
   - 연구실/실험실
   - 담당업무

를 추출하여
구분1, 구분2, 구분3, ID 와 합쳐 최종 엑셀(xlsx)로 저장

명예교수는 제외
입력 CSV의 원래 순서를 유지하도록 정렬
"""

from __future__ import annotations

import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.kookmin.ac.kr"
VIEW_URL = "https://www.kookmin.ac.kr/user/unIntr/unSttu/univOrgn/view.do?deptCd={dept_cd}"

INPUT_CSV = "국민대학교 목록.csv"
OUTPUT_XLSX = "kookmin_univ_org_members.xlsx"

# 병렬 개수
MAX_WORKERS = 12

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.kookmin.ac.kr/",
    "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
}

_thread_local = threading.local()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _thread_local.session = session
    return session


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def join_texts(values: List[str], sep: str = " | ") -> str:
    cleaned = [clean_text(v) for v in values if clean_text(v)]
    return sep.join(cleaned)


def split_name_and_title(raw_name: str) -> Tuple[str, str]:
    """
    예:
    - '황보진석 부장' -> ('황보진석', '부장')
    - '이희진 부장' -> ('이희진', '부장')
    - '안동환 교수' -> ('안동환', '교수')
    - '김재헌' -> ('김재헌', '')
    - '이재갑 명예교수' -> ('이재갑', '명예교수')
    """
    text = clean_text(raw_name)
    if not text:
        return "", ""

    parts = text.rsplit(" ", 1)
    if len(parts) == 2:
        left, right = clean_text(parts[0]), clean_text(parts[1])

        # 마지막 토큰이 직위처럼 보이면 분리
        if right and len(right) <= 12:
            return left, right

    return text, ""


def get_soup(dept_cd: str) -> BeautifulSoup:
    url = VIEW_URL.format(dept_cd=dept_cd)
    session = get_session()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_label_block_map(prof_desc: Optional[Tag]) -> Dict[str, str]:
    """
    prof_desc 내부의
    <strong>보직 및 겸무</strong>
    <strong>담당업무</strong>
    <strong>연구실/실험실</strong>
    등을 key-value 형태로 추출
    """
    result: Dict[str, str] = {}

    if not prof_desc:
        return result

    for li in prof_desc.select("ul.dot_list > li"):
        strong = li.find("strong")
        if not strong:
            continue

        key = clean_text(strong.get_text(" ", strip=True))
        if not key:
            continue

        li_clone = BeautifulSoup(str(li), "html.parser")
        li_clone_root = li_clone.find("li")
        if li_clone_root:
            strong_clone = li_clone_root.find("strong")
            if strong_clone:
                strong_clone.extract()

            sub_items = []
            for sub_li in li_clone_root.select("ul li"):
                txt = clean_text(sub_li.get_text(" ", strip=True))
                if txt:
                    sub_items.append(txt)

            if sub_items:
                result[key] = join_texts(sub_items)
                continue

            txt = clean_text(li_clone_root.get_text(" ", strip=True))
            if txt:
                result[key] = txt

    return result


def extract_staff_from_prof_list(
        soup: BeautifulSoup,
        base_row: Dict[str, str],
        page_url: str,
) -> List[Dict[str, str]]:
    """
    직원/행정실 쪽:
    <ul class="prof_list"> ... </ul>
    """
    rows: List[Dict[str, str]] = []
    member_index = base_row.get("__member_index_start", 0)

    for ul in soup.select("ul.prof_list"):
        for li in ul.find_all("li", recursive=False):
            prof_box = li.find("div", class_="prof_box")
            if not prof_box:
                continue

            raw_name = ""
            email = ""

            name_tag = prof_box.select_one(".name_wrap .name")
            if name_tag:
                raw_name = clean_text(name_tag.get_text(" ", strip=True))

            name, title = split_name_and_title(raw_name)

            email_tag = prof_box.select_one(".prof_info .email")
            if email_tag:
                email = clean_text(email_tag.get_text(" ", strip=True))

            prof_desc = li.find("div", class_="prof_desc")
            label_map = extract_label_block_map(prof_desc)

            row = {
                **base_row,
                "구분3_상세": base_row.get("구분3", ""),
                "이름": name,
                "직위": title,
                "이메일": email,
                "보직및겸무": label_map.get("보직 및 겸무", ""),
                "담당업무": label_map.get("담당업무", ""),
                "연구실/실험실": "",
                "구성원구분": "직원/행정",
                "참고URL": page_url,
                "__member_index": member_index,
            }

            if (
                    row["이름"]
                    or row["직위"]
                    or row["이메일"]
                    or row["보직및겸무"]
                    or row["담당업무"]
            ):
                rows.append(row)
                member_index += 1

    return rows


def extract_professors_from_organ_view(
        soup: BeautifulSoup,
        base_row: Dict[str, str],
        page_url: str,
        member_index_start: int,
) -> List[Dict[str, str]]:
    """
    실제 국민대 구조 기준:
    form#frm 내부에서 div.cont_section.organ_view 를 순서대로 돌면서

    1) p.cont_tit 가 있으면 현재 교수 섹션 제목(current_title) 갱신
    2) 다음 organ_view 에 .col_cont.three 가 있으면 그 안의 .prof_wrap 들을 교수로 추출
    3) .no_prof 는 건너뜀
    """
    rows: List[Dict[str, str]] = []

    frm = soup.select_one("form#frm")
    if not frm:
        return rows

    current_title = clean_text(base_row.get("구분3", ""))
    sections = frm.select("div.cont_section.organ_view")
    member_index = member_index_start

    for section in sections:
        class_list = section.get("class", [])

        if "no_prof" in class_list:
            continue

        title_tag = section.select_one(":scope > p.cont_tit")
        if title_tag:
            title_text = clean_text(title_tag.get_text(" ", strip=True))
            if title_text:
                current_title = title_text
            continue

        prof_wraps = section.select(":scope > .col_cont.three > .prof_wrap")
        if not prof_wraps:
            prof_wraps = section.select(".col_cont.three .prof_wrap")

        for prof_wrap in prof_wraps:
            name_tag = prof_wrap.select_one(".name_wrap .name")
            raw_name = clean_text(name_tag.get_text(" ", strip=True)) if name_tag else ""
            if not raw_name:
                continue

            if "명예교수" in raw_name:
                continue

            name, title = split_name_and_title(raw_name)

            if not title:
                title = "교수"

            name = re.sub(
                r"\s*(교수|부교수|조교수|객원교수|겸임교수|석좌교수|특임교수)\s*$",
                "",
                name,
            ).strip()

            email_tag = prof_wrap.select_one(".prof_info .email")
            email = clean_text(email_tag.get_text(" ", strip=True)) if email_tag else ""

            prof_desc = prof_wrap.select_one(".prof_desc")
            label_map = extract_label_block_map(prof_desc)

            row = {
                **base_row,
                "구분3_상세": current_title,
                "이름": name,
                "직위": title,
                "이메일": email,
                "보직및겸무": label_map.get("보직 및 겸무", ""),
                "담당업무": label_map.get("담당업무", ""),
                "연구실/실험실": label_map.get("연구실/실험실", ""),
                "구성원구분": "교수",
                "참고URL": page_url,
                "__member_index": member_index,
            }

            rows.append(row)
            member_index += 1

    return rows


def extract_page_rows(src_row: Dict[str, str]) -> List[Dict[str, str]]:
    dept_cd = clean_text(str(src_row.get("ID", "")))
    if not dept_cd:
        return []

    page_url = VIEW_URL.format(dept_cd=dept_cd)
    soup = get_soup(dept_cd)

    base_row = {
        "구분1": clean_text(str(src_row.get("구분1", ""))),
        "구분2": clean_text(str(src_row.get("구분2", ""))),
        "구분3": clean_text(str(src_row.get("구분3", ""))),
        "ID": dept_cd,
        "__input_index": int(src_row.get("__input_index", 0)),
    }

    rows: List[Dict[str, str]] = []

    staff_rows = extract_staff_from_prof_list(soup, {**base_row, "__member_index_start": 0}, page_url)
    rows.extend(staff_rows)

    professor_start_index = len(staff_rows)
    professor_rows = extract_professors_from_organ_view(soup, base_row, page_url, professor_start_index)
    rows.extend(professor_rows)

    return rows


def read_input_rows(csv_path: str) -> List[Dict[str, str]]:
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            df = pd.read_csv(csv_path, dtype=str, encoding=enc).fillna("")
            records = df.to_dict(orient="records")

            for idx, row in enumerate(records):
                row["__input_index"] = idx

            return records
        except Exception:
            pass

    raise ValueError(f"CSV 파일을 읽을 수 없습니다: {csv_path}")


def save_output(rows: List[Dict[str, str]], output_path: str) -> None:
    columns = [
        "구분1",
        "구분2",
        "구분3",
        "구분3_상세",
        "ID",
        "구성원구분",
        "이름",
        "직위",
        "이메일",
        "보직및겸무",
        "담당업무",
        "연구실/실험실",
        "참고URL",
    ]

    df = pd.DataFrame(rows)

    if df.empty:
        df = pd.DataFrame(columns=columns)
    else:
        if "__input_index" not in df.columns:
            df["__input_index"] = 0
        if "__member_index" not in df.columns:
            df["__member_index"] = 0

        df = df.sort_values(
            by=["__input_index", "__member_index"],
            ascending=[True, True],
            kind="stable",
        ).reset_index(drop=True)

        for col in columns:
            if col not in df.columns:
                df[col] = ""

        df = df[columns]

    df.to_excel(output_path, index=False)


def worker_task(idx: int, total: int, row: Dict[str, str]) -> List[Dict[str, str]]:
    dept_cd = clean_text(str(row.get("ID", "")))
    print(f"[{idx}/{total}] deptCd={dept_cd} 수집 중...")
    page_rows = extract_page_rows(row)
    print(f"[{idx}/{total}] deptCd={dept_cd} 완료 -> {len(page_rows)}건")
    return page_rows


def main() -> None:
    input_rows = read_input_rows(INPUT_CSV)
    all_rows: List[Dict[str, str]] = []
    total = len(input_rows)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(worker_task, idx, total, row): (idx, row)
            for idx, row in enumerate(input_rows, start=1)
        }

        for future in as_completed(futures):
            idx, row = futures[future]
            dept_cd = clean_text(str(row.get("ID", "")))

            try:
                page_rows = future.result()
                all_rows.extend(page_rows)
            except Exception as e:
                print(f"[{idx}/{total}] deptCd={dept_cd} 실패: {e}")

    save_output(all_rows, OUTPUT_XLSX)
    print(f"\n완료: {OUTPUT_XLSX} ({len(all_rows)}건)")


if __name__ == "__main__":
    main()