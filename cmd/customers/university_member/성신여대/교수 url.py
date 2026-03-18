# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.sungshin.ac.kr"
OUTPUT_CSV = "sungshin_detail_result.csv"


# =========================
# 공통 유틸
# =========================
def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def make_absolute_url(href: str, base_url: str) -> str:
    href = clean_text(href)
    if not href:
        return ""
    return urljoin(base_url, href)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    return session


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def extract_first_email(text: str) -> str:
    if not text:
        return ""
    found = EMAIL_REGEX.findall(text)
    if not found:
        return ""
    return clean_text(found[0])


# =========================
# 이메일 추출
# =========================
def extract_admin_email_from_footer_or_page(soup: BeautifulSoup) -> str:
    """
    우선순위
    1) footer 태그 내부
    2) id/class에 footer 포함된 영역
    3) 전체 페이지 텍스트
    """
    # 1. footer 태그
    footer_tag = soup.find("footer")
    if footer_tag:
        email = extract_first_email(footer_tag.get_text(" ", strip=True))
        if email:
            return email

    # 2. footer 느낌 나는 영역
    footer_like_tags = soup.find_all(
        lambda tag: (
                isinstance(tag, Tag)
                and tag.name in ("div", "section", "aside", "p")
                and (
                        "footer" in clean_text(" ".join(tag.get("class", []))).lower()
                        or "footer" in clean_text(tag.get("id", "")).lower()
                )
        )
    )
    for tag in footer_like_tags:
        email = extract_first_email(tag.get_text(" ", strip=True))
        if email:
            return email

    # 3. 전체 페이지
    return extract_first_email(soup.get_text(" ", strip=True))


# =========================
# 전임교수 URL 추출
# =========================
def find_professor_url(soup: BeautifulSoup, page_url: str) -> str:
    """
    '전임교수' 라는 텍스트가 포함된 a 태그 href 추출
    구조가 조금씩 달라도 텍스트 기준으로 찾음
    """
    # 1차: a 태그 텍스트에서 직접 찾기
    for a_tag in soup.find_all("a", href=True):
        text = clean_text(a_tag.get_text(" ", strip=True))
        if "전임교수" in text:
            return make_absolute_url(a_tag["href"], page_url)

    # 2차: hidden input menuTitle 값이 전임교수인 경우, 부모 a 찾기
    for input_tag in soup.find_all("input", {"type": "hidden"}):
        value = clean_text(input_tag.get("value", ""))
        if "전임교수" in value:
            parent_a = input_tag.find_parent("a", href=True)
            if parent_a:
                return make_absolute_url(parent_a["href"], page_url)

    return ""


# =========================
# 단건 처리
# =========================
def parse_detail_page(session: requests.Session, item: Dict[str, str]) -> Dict[str, str]:
    """
    item 예시:
    {
        "구분1": "대학",
        "구분2": "인문대학",
        "구분3": "일어일문학과",
        "URL": "...",
        "DETAIL_URL": "..."
    }
    """
    row = dict(item)
    row["업무"] = "행정"
    row["이메일"] = ""
    row["PROFESSOR_URL"] = ""
    row["error"] = ""

    detail_url = clean_text(item.get("DETAIL_URL", ""))

    if not detail_url:
        row["error"] = "DETAIL_URL 없음"
        return row

    try:
        resp = session.get(detail_url, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        row["error"] = f"요청 실패: {e}"
        return row

    soup = BeautifulSoup(resp.text, "html.parser")

    # 행정실 이메일
    row["이메일"] = extract_admin_email_from_footer_or_page(soup)

    # 전임교수 URL
    row["PROFESSOR_URL"] = find_professor_url(soup, detail_url)

    return row


# =========================
# 전체 처리
# =========================
def build_result_rows(obj_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    session = create_session()
    results: List[Dict[str, str]] = []

    total = len(obj_list)

    for idx, item in enumerate(obj_list, start=1):
        row = parse_detail_page(session, item)
        results.append(row)

        print(
            f"[{idx}/{total}] "
            f"{clean_text(item.get('구분2'))} / {clean_text(item.get('구분3'))} | "
            f"EMAIL={row.get('이메일', '')} | "
            f"PROFESSOR_URL={row.get('PROFESSOR_URL', '')} | "
            f"ERROR={row.get('error', '')}"
        )

    return results


# =========================
# CSV 저장
# =========================
def save_csv(rows: List[Dict[str, str]], output_csv: str) -> None:
    if not rows:
        print("[WARN] 저장할 데이터가 없습니다.")
        return

    fieldnames: List[str] = []
    seen = set()

    # 키 순서 최대한 유지
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] CSV 저장 완료: {output_csv}")


# =========================
# 실행 예시
# =========================
if __name__ == "__main__":
    # 사용자가 직접 넣는다고 해서 예시만 둠
    obj_list = [
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "국어국문학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/korean/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "영어영문학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/english/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "독일어문·문화학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/german/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "프랑스어문·문화학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/france/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "일본어문·문화학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/japanese/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "중국어문·문화학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/chinese/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "사학과(수정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/history/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "문화예술경영학과(운정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "http://www.sungshin.ac.kr/cultureart/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "미디어영상연기학과(운정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "http://www.sungshin.ac.kr/vmacting/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "현대실용음악학과(운정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "http://www.sungshin.ac.kr/ctpmusic/index.do"},
        {"구분1": "대학", "구분2": "인문융합예술대학", "구분3": "무용예술학과(운정)", "URL": "https://www.sungshin.ac.kr/humanity/index.do",
         "DETAIL_URL": "http://www.sungshin.ac.kr/danceart/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "정치외교학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/politics/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "심리학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/psy/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "지리학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/geographic/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "경제학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/economic/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "경영학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/bizadm/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "미디어커뮤니케이션학과(수정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/mediacomm/index.do"},
        {"구분1": "대학", "구분2": "사회과학대학", "구분3": "사회복지학과(운정)", "URL": "https://www.sungshin.ac.kr/social/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/welfare/index.do"},
        {"구분1": "대학", "구분2": "법과대학", "구분3": "법학부", "URL": "https://www.sungshin.ac.kr/lawdean/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/solaw"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "수학과(수정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/math/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "통계학과(수정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/statistics/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "생명과학·화학부(운정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/bio/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "화학과(운정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/chm/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "수리통계데이터사이언스학부(수정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/math-statistics/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "화학·에너지융합학부(운정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/chem-energy/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "바이오헬스융합학부(운정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/biohealth/index.do"},
        {"구분1": "대학", "구분2": "자연과학대학", "구분3": "식품영양학과(운정)", "URL": "https://www.sungshin.ac.kr/natscience/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/nutrition/12021/subview.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "서비스디자인공학과(수정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/serdesign/index.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "융합보안공학과(수정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/cse/index.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "컴퓨터공학과(수정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/ce/index.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "청정신소재공학과(운정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/dmse/index"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "바이오식품공학과(운정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/bif/index.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "바이오생명공학과(운정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/bte/index.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "바이오신약의과학부(운정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/biopharm/17441/subview.do"},
        {"구분1": "대학", "구분2": "공과대학", "구분3": "AI융합학부(수정)", "URL": "https://www.sungshin.ac.kr/eng/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/aiot/index.do"},
        {"구분1": "대학", "구분2": "IT융합대학", "구분3": "AI융합학부", "URL": "https://www.sungshin.ac.kr/itc/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/aiot/index.do"},
        {"구분1": "대학", "구분2": "IT융합대학", "구분3": "컴퓨터공학과", "URL": "https://www.sungshin.ac.kr/itc/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/ce/index.do"},
        {"구분1": "대학", "구분2": "IT융합대학", "구분3": "융합보안공학과", "URL": "https://www.sungshin.ac.kr/itc/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/cse/index.do"},
        {"구분1": "대학", "구분2": "IT융합대학", "구분3": "서비스디자인공학과", "URL": "https://www.sungshin.ac.kr/itc/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/serdesign/index.do"},
        {"구분1": "대학", "구분2": "간호대학", "구분3": "설립목적", "URL": "https://www.sungshin.ac.kr/nursing/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/nursing/15470/subview.do"},
        {"구분1": "대학", "구분2": "간호대학", "구분3": "연혁", "URL": "https://www.sungshin.ac.kr/nursing/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/nursing/15471/subview.do"},
        {"구분1": "대학", "구분2": "간호대학", "구분3": "규정", "URL": "https://www.sungshin.ac.kr/nursing/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/nursing/15472/subview.do"},
        {"구분1": "대학", "구분2": "생활산업대학", "구분3": "의류산업학과(운정)", "URL": "https://www.sungshin.ac.kr/lifeindustry/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/cloth/index.do"},
        {"구분1": "대학", "구분2": "생활산업대학", "구분3": "소비자산업학과(운정)", "URL": "https://www.sungshin.ac.kr/lifeindustry/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/family/index.do"},
        {"구분1": "대학", "구분2": "생활산업대학", "구분3": "뷰티산업학과(운정)", "URL": "https://www.sungshin.ac.kr/lifeindustry/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/insbeauty/index.do"},
        {"구분1": "대학", "구분2": "생활산업대학", "구분3": "스포츠과학부(수정)", "URL": "https://www.sungshin.ac.kr/lifeindustry/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/sportsscience/index.do"},
        {"구분1": "대학", "구분2": "사범대학", "구분3": "교육학과", "URL": "https://www.sungshin.ac.kr/teacher/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/education/index.do"},
        {"구분1": "대학", "구분2": "사범대학", "구분3": "사회교육과", "URL": "https://www.sungshin.ac.kr/teacher/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/edusociety/index.do"},
        {"구분1": "대학", "구분2": "사범대학", "구분3": "윤리교육과", "URL": "https://www.sungshin.ac.kr/teacher/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/eduethics/index.do"},
        {"구분1": "대학", "구분2": "사범대학", "구분3": "한문교육과", "URL": "https://www.sungshin.ac.kr/teacher/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/educhinese/index.do"},
        {"구분1": "대학", "구분2": "사범대학", "구분3": "유아교육과", "URL": "https://www.sungshin.ac.kr/teacher/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/sites/edukids/index.do"},
        {"구분1": "대학", "구분2": "음악대학", "구분3": "성악과", "URL": "https://www.sungshin.ac.kr/music/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/vocal/index.do"},
        {"구분1": "대학", "구분2": "음악대학", "구분3": "기악과", "URL": "https://www.sungshin.ac.kr/music/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/instrumental/index.do"},
        {"구분1": "대학", "구분2": "음악대학", "구분3": "작곡과", "URL": "https://www.sungshin.ac.kr/music/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/composition/index.do"},
        {"구분1": "대학", "구분2": "창의융합대학", "구분3": "교양 영역별 구성", "URL": "https://www.sungshin.ac.kr/generaledu/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/generaledu/16043/subview.do"},
        {"구분1": "대학", "구분2": "창의융합대학", "구분3": "핵심교양 영역별 정의", "URL": "https://www.sungshin.ac.kr/generaledu/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/generaledu/16044/subview.do"},
        {"구분1": "대학", "구분2": "창의융합대학", "구분3": "GeM 교과목", "URL": "https://www.sungshin.ac.kr/generaledu/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/generaledu/19977/subview.do"},
        {"구분1": "대학", "구분2": "창의융합대학", "구분3": "신규 교양 교과목", "URL": "https://www.sungshin.ac.kr/generaledu/index.do",
         "DETAIL_URL": "https://www.sungshin.ac.kr/generaledu/20794/subview.do"}
    ]

    rows = build_result_rows(obj_list)
    save_csv(rows, OUTPUT_CSV)
