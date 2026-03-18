# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from openpyxl import Workbook


# =========================================================
# 여기에 사용자가 만든 DEPT_DETAIL_URL_LIST 를 그대로 넣어서 사용
# =========================================================
DEPT_DETAIL_URL_LIST = [
    {
        "구분1": "대학",
        "구분2": "영어대학",
        "구분3": "ELLT학과",
        "URL": "https://www.hufs.ac.kr/hufs/11224/subview.do",
        "DETAIL_URL": "http://ellt.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "영어대학",
        "구분3": "영미문학·문화학과",
        "URL": "https://www.hufs.ac.kr/hufs/11224/subview.do",
        "DETAIL_URL": "https://elc.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "영어대학",
        "구분3": "영어통번역(EICC)학과",
        "URL": "https://www.hufs.ac.kr/hufs/11224/subview.do",
        "DETAIL_URL": "http://eicc.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "영어대학",
        "구분3": "영어학부(2014) *",
        "URL": "https://www.hufs.ac.kr/hufs/11224/subview.do",
        "DETAIL_URL": "http://eng.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "프랑스어학부",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "http://hufsfr.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "독일어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "https://deutsch.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "노어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "http://hufsrussia.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "스페인어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "http://hufspain.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "이탈리아어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "https://italiano.hufs.ac.kr"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "포르투갈어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "https://portuguese.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "네덜란드어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "http://neds.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "서양어대학",
        "구분3": "스칸디나비아어과",
        "URL": "https://www.hufs.ac.kr/hufs/11225/subview.do",
        "DETAIL_URL": "https://scan.hufs.ac.kr"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "말레이·인도네시아어과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "http://hufsmain.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "아랍어과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "http://arab.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "태국학과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "http://thai.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "베트남어과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "https://vietnamese.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "인도어과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "https://india.hufs.ac.kr"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "튀르키예·아제르바이잔학과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "http://turkazeri.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "페르시아어·이란학과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "https://iran.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "아시아언어문화대학",
        "구분3": "몽골어과",
        "URL": "https://www.hufs.ac.kr/hufs/11226/subview.do",
        "DETAIL_URL": "http://mongolian.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "중국학대학",
        "구분3": "중국언어문화학부",
        "URL": "https://www.hufs.ac.kr/hufs/11227/subview.do",
        "DETAIL_URL": "http://chufs1.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "중국학대학",
        "구분3": "중국외교통상학부",
        "URL": "https://www.hufs.ac.kr/hufs/11227/subview.do",
        "DETAIL_URL": "http://chufs2.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "일본학대학",
        "구분3": "일본언어문화학부",
        "URL": "https://www.hufs.ac.kr/hufs/11228/subview.do",
        "DETAIL_URL": "http://hufsjp1.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "일본학대학",
        "구분3": "융합일본지역학부",
        "URL": "https://www.hufs.ac.kr/hufs/11228/subview.do",
        "DETAIL_URL": "https://hufsjp.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사회과학대학",
        "구분3": "정치외교학과",
        "URL": "https://www.hufs.ac.kr/hufs/11229/subview.do",
        "DETAIL_URL": "http://hufspol.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사회과학대학",
        "구분3": "행정학과",
        "URL": "https://www.hufs.ac.kr/hufs/11229/subview.do",
        "DETAIL_URL": "http://hufspa.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사회과학대학",
        "구분3": "미디어커뮤니케이션학부",
        "URL": "https://www.hufs.ac.kr/hufs/11229/subview.do",
        "DETAIL_URL": "http://commu.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "상경대학",
        "구분3": "국제통상학과",
        "URL": "https://www.hufs.ac.kr/hufs/11230/subview.do",
        "DETAIL_URL": "http://iel.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "상경대학",
        "구분3": "경제학부",
        "URL": "https://www.hufs.ac.kr/hufs/11230/subview.do",
        "DETAIL_URL": "http://econ.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "영어교육과",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://hufsee.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "한국어교육과",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "https://hufskle.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "외국어교육학부(프랑스어교육전공)",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://fe.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "외국어교육학부(독일어교육전공)",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://germanedu.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "외국어교육학부(중국어교육전공)",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://cle.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "교육학전공",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://eduhufs.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "사범대학",
        "구분3": "체육학전공",
        "URL": "https://www.hufs.ac.kr/hufs/11232/subview.do",
        "DETAIL_URL": "http://eduhufs.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "AI융합대학",
        "구분3": "Language & AI 융합학부",
        "URL": "https://www.hufs.ac.kr/hufs/11233/subview.do",
        "DETAIL_URL": "https://langai.hufs.ac.kr/"
    },
    {
        "구분1": "대학",
        "구분2": "AI융합대학",
        "구분3": "Social Science & AI 융합학부",
        "URL": "https://www.hufs.ac.kr/hufs/11233/subview.do",
        "DETAIL_URL": "https://ssai.hufs.ac.kr/ssai/index.do"
    },
    {
        "구분1": "대학",
        "구분2": "KFL학부",
        "구분3": "외국어로서의 한국어교육 전공",
        "URL": "https://www.hufs.ac.kr/hufs/11237/subview.do",
        "DETAIL_URL": "https://dep.hufs.ac.kr/sites/hufskfl/index.do"
    },
    {
        "구분1": "대학",
        "구분2": "KFL학부",
        "구분3": "외국어로서의 한국어통번역 전공",
        "URL": "https://www.hufs.ac.kr/hufs/11237/subview.do",
        "DETAIL_URL": "https://dep.hufs.ac.kr/sites/hufskfl/index.do"
    }
]



OUTPUT_CSV = "일반대학.csv"
OUTPUT_XLSX = "일반대학.xlsx"
MAX_WORKERS = 10
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


# =========================================================
# 공통 유틸
# =========================================================
def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_url(base_url: str, href: str) -> str:
    href = clean_text(href)
    if not href:
        return ""
    return urljoin(base_url, href)


def find_first_email(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
    return m.group(0).strip() if m else ""


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_soup(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] 요청 실패: {url} / {e}")
        return None


def extract_dl_map(container: Tag) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for dl in container.select("dl"):
        dt = dl.select_one("dt")
        dd = dl.select_one("dd")
        key = clean_text(dt.get_text(" ", strip=True)) if dt else ""
        val = clean_text(dd.get_text(" ", strip=True)) if dd else ""
        if key:
            result[key] = val
    return result


def extract_prof_name(raw_name: str) -> str:
    """
    예)
    - '홍성훈 교수 Prof. Sung-Hoon Hong' -> '홍성훈'
    - '김수연 교수 Prof. Soo Yeon Kim' -> '김수연'
    - 'Prof. Sung-Hoon Hong' -> 'Sung-Hoon Hong'
    - 'Professor Sung-Hoon Hong' -> 'Sung-Hoon Hong'
    - 'Sung-Hoon Hong' -> 'Sung-Hoon Hong'
    """
    raw_name = clean_text(raw_name)
    if not raw_name:
        return ""

    # 1) 한글 이름 + 교수
    m = re.search(r"([가-힣]{2,10})\s*교수", raw_name)
    if m:
        return clean_text(m.group(1))

    # 2) 한글 이름으로 시작
    m = re.match(r"^([가-힣]{2,10})", raw_name)
    if m:
        return clean_text(m.group(1))

    # 3) Prof. / Professor 제거
    english_name = raw_name
    english_name = re.sub(r"^(Prof\.?\s*)", "", english_name, flags=re.IGNORECASE).strip()
    english_name = re.sub(r"^(Professor\s+)", "", english_name, flags=re.IGNORECASE).strip()

    # 4) 혹시 뒤에 '교수' 같은 한글 직함이 붙은 경우 제거
    english_name = re.sub(r"\s*교수.*$", "", english_name).strip()

    # 5) 영문 이름 토큰만 남기기
    # 하이픈, 점, 아포스트로피 허용
    m = re.search(r"([A-Za-z][A-Za-z\s\-\.'`]+)$", english_name)
    if m:
        candidate = clean_text(m.group(1))
        if candidate:
            return candidate

    return clean_text(english_name)


# =========================================================
# 행정 이메일 추출
# =========================================================
def extract_admin_email_from_footer(soup: BeautifulSoup) -> str:
    footer = soup.select_one(".wrap-footer, .footer_wrap")
    if not footer:
        return ""

    mailto_el = footer.select_one('a[href^="mailto:"]')
    if mailto_el:
        href = clean_text(mailto_el.get("href", ""))
        email = href.replace("mailto:", "").strip()
        if email:
            return email

    return find_first_email(footer.get_text(" ", strip=True))


# =========================================================
# 교수 메뉴 URL 찾기
# =========================================================
def find_faculty_menu_url(soup: BeautifulSoup, detail_url: str) -> str:
    menu_root = soup.select_one("#menuUItop")
    if not menu_root:
        return ""

    candidates = menu_root.select("a[href]")

    priority_keywords = [
        "전임교수",
        "Faculty",
        "faculty",
    ]

    for keyword in priority_keywords:
        for a in candidates:
            text = clean_text(a.get_text(" ", strip=True))
            if keyword.lower() in text.lower():
                href = clean_text(a.get("href", ""))
                if href:
                    return normalize_url(detail_url, href)

    # 보조
    fallback_keywords = [
        "교수진",
        "교수",
    ]
    for keyword in fallback_keywords:
        for a in candidates:
            text = clean_text(a.get_text(" ", strip=True))
            if keyword in text:
                href = clean_text(a.get("href", ""))
                if href:
                    return normalize_url(detail_url, href)

    return ""


# =========================================================
# 교수 목록 추출
# =========================================================
def extract_professors_from_faculty_page(
        session: requests.Session,
        faculty_url: str,
        base_info: Dict[str, str],
) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []

    if not faculty_url:
        return result

    soup = get_soup(session, faculty_url)
    if not soup:
        return result

    prof_items = soup.select("ul._wizOdr._prFlList > li")
    if not prof_items:
        prof_items = soup.select("._prFlList > li")

    if not prof_items:
        print(f"[WARN] 교수 목록 없음: {faculty_url}")
        return result

    for li in prof_items:
        try:
            link_el = li.select_one("a._prFlLinkView[href]") or li.select_one("a[href]")
            prof_url = normalize_url(faculty_url, link_el.get("href", "")) if link_el else ""

            title_el = li.select_one(".artclTitle strong")
            raw_name = clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
            name = extract_prof_name(raw_name)

            info_map = extract_dl_map(li)

            email = info_map.get("이메일", "")
            if not email:
                email = find_first_email(li.get_text(" ", strip=True))

            degree = info_map.get("최종 학위", "") or info_map.get("최종학위", "")
            research = info_map.get("연구분야", "")

            row = dict(base_info)
            row.update(
                {
                    "업무": "교수",
                    "이름": name,
                    "이메일": email,
                    "최종학위": degree,
                    "연구분야": research,
                    "교수URL": prof_url,
                }
            )
            result.append(row)
        except Exception as e:
            print(f"[ERROR] 교수 파싱 실패: {faculty_url} / {e}")

    return result


# =========================================================
# 학과 상세 1개 처리
# =========================================================
def crawl_one_department(session: requests.Session, item: Dict[str, str]) -> List[Dict[str, str]]:
    result_rows: List[Dict[str, str]] = []

    detail_url = clean_text(item.get("DETAIL_URL", ""))
    if not detail_url:
        return result_rows

    print(f"[INFO] 처리 시작: {item.get('구분2', '')} / {item.get('구분3', '')} / {detail_url}")

    soup = get_soup(session, detail_url)
    if not soup:
        return result_rows

    base_info = {
        "구분1": clean_text(item.get("구분1", "")),
        "구분2": clean_text(item.get("구분2", "")),
        "구분3": clean_text(item.get("구분3", "")),
        "URL": clean_text(item.get("URL", "")),
        "DETAIL_URL": detail_url,
        "업무": "",
        "이름": "",
        "이메일": "",
        "최종학위": "",
        "연구분야": "",
        "교수URL": "",
    }

    # =========================
    # 행정 이메일 추출
    # =========================
    admin_email = extract_admin_email_from_footer(soup)
    if admin_email:
        admin_row = dict(base_info)
        admin_row.update(
            {
                "업무": "행정",
                "이름": "",
                "이메일": admin_email,
                "최종학위": "",
                "연구분야": "",
                "교수URL": "",
            }
        )
        result_rows.append(admin_row)

    # =========================
    # 교수 메뉴 URL 찾기
    # =========================
    faculty_url = find_faculty_menu_url(soup, detail_url)
    if faculty_url:
        prof_rows = extract_professors_from_faculty_page(session, faculty_url, base_info)
        result_rows.extend(prof_rows)
    else:
        print(f"[WARN] 교수 메뉴 URL 없음: {detail_url}")

    return result_rows


# =========================================================
# 멀티스레드 처리
# =========================================================
def crawl_one_department_worker(args: Tuple[int, Dict[str, str]]) -> List[Dict[str, str]]:
    index, item = args
    session = get_session()
    rows = crawl_one_department(session, item)

    for row in rows:
        row["_index"] = index

    return rows


def crawl_all_departments(dept_detail_url_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    all_rows: List[Dict[str, str]] = []
    indexed_items = list(enumerate(dept_detail_url_list))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(crawl_one_department_worker, pair)
            for pair in indexed_items
        ]

        for future in as_completed(futures):
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                print(f"[ERROR] 멀티스레드 작업 실패: {e}")

    # 입력 순서 기준 정렬
    all_rows.sort(key=lambda x: x.get("_index", 0))

    for row in all_rows:
        row.pop("_index", None)

    return all_rows


# =========================================================
# 저장
# =========================================================
def save_to_csv(rows: List[Dict[str, str]], filename: str) -> None:
    columns = [
        "구분1",
        "구분2",
        "구분3",
        "업무",
        "이름",
        "이메일",
        "최종학위",
        "연구분야",
        "URL",
        "DETAIL_URL",
        "교수URL",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})

    print(f"[INFO] CSV 저장 완료: {filename}")


def save_to_xlsx(rows: List[Dict[str, str]], filename: str) -> None:
    columns = [
        "구분1",
        "구분2",
        "구분3",
        "업무",
        "이름",
        "이메일",
        "최종학위",
        "연구분야",
        "URL",
        "DETAIL_URL",
        "교수URL",
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "HUFS"

    ws.append(columns)

    for row in rows:
        ws.append([row.get(col, "") for col in columns])

    wb.save(filename)
    print(f"[INFO] XLSX 저장 완료: {filename}")


# =========================================================
# 실행
# =========================================================
def main() -> None:
    rows = crawl_all_departments(DEPT_DETAIL_URL_LIST)

    # 이메일 없는 행 제거하고 싶으면 사용
    # rows = [row for row in rows if clean_text(row.get("이메일", ""))]

    print(f"[INFO] 총 수집 건수: {len(rows)}")

    save_to_csv(rows, OUTPUT_CSV)
    save_to_xlsx(rows, OUTPUT_XLSX)

    for i, row in enumerate(rows[:30], 1):
        print(f"[{i}] {row}")


if __name__ == "__main__":
    main()