

# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


MAX_WORKERS = 10

# =========================
# 전역변수
# 여기에 직접 넣어서 사용
# =========================
detail_url_list = [
    {"구분1": "연구산학협력단", "구분2": "연구지원1팀(서울)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구지원1팀(서울)", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "연구지원2팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구지원2팀(글로벌)", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "기획총괄팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기획총괄팀(글로벌)", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "산학지원팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "산학지원팀(글로벌)", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "산학재무회계팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "산학재무회계팀(글로벌)", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "창업보육센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업보육센터", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "지산학협력R&DB센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "지산학협력R&DB센터", "홈페이지URL": "", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "기술이전센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기술이전센터", "홈페이지URL": "https://iucf.hufs.ac.kr/", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "다문화교육원", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "다문화교육원", "홈페이지URL": "https://builder.hufs.ac.kr/user/hufsmcs", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "공동기기원", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "공동기기원", "홈페이지URL": "https://iucf.hufs.ac.kr/iucf/crfc", "error": ""},
    {"구분1": "연구산학협력단", "구분2": "연구윤리센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구윤리센터", "홈페이지URL": "https://rec.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "외국어교육연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국어교육연구소", "홈페이지URL": "http://ifle.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "외국문학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국문학연구소", "홈페이지URL": "http://ifl.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "언어연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어연구소", "홈페이지URL": "http://lri.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "통번역연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "통번역연구소", "홈페이지URL": "http://itri.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "일본연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "일본연구소", "홈페이지URL": "http://hufsjapan.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중국연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중국연구소", "홈페이지URL": "http://china114.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "동남아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "동남아연구소", "홈페이지URL": "http://cseas.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중동연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중동연구소", "홈페이지URL": "https://middleeast.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "영미연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "영미연구소", "홈페이지URL": "http://ibas.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중남미연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중남미연구소", "홈페이지URL": "http://ilas.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "EU연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "EU연구소", "홈페이지URL": "http://eu.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "동유럽발칸연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "동유럽발칸연구소", "홈페이지URL": "http://eebi.ac.kr/main/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "러시아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "러시아연구소", "홈페이지URL": "http://www.rus.or.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "아프리카연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "아프리카연구소", "홈페이지URL": "http://www.afstudy.org/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "인도연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "인도연구소", "홈페이지URL": "http://iis.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중앙아시아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중앙아시아연구소", "홈페이지URL": "http://www.central-asia.or.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "경제경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "경제경영연구소", "홈페이지URL": "", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "철학문화연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "철학문화연구소", "홈페이지URL": "http://human.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "역사문화연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "역사문화연구소", "홈페이지URL": "http://iohac.jams.or.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "미디어커뮤니케이션연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "미디어커뮤니케이션연구소", "홈페이지URL": "http://ici.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "글로벌경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "글로벌경영연구소", "홈페이지URL": "https://biz.hufs.ac.kr/biz/7692/subview.do", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "기초과학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기초과학연구소", "홈페이지URL": "http://ibs.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "법학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "법학연구소", "홈페이지URL": "http://lawri.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "정보산업공학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "정보산업공학연구소", "홈페이지URL": "http://iie.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "환경과학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "환경과학연구소", "홈페이지URL": "", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "글로벌정치연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "글로벌정치연구소", "홈페이지URL": "http://gpi.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "국정관리연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "국정관리연구소", "홈페이지URL": "", "error": ""},
    {"구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "언어공학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어공학연구소", "홈페이지URL": "http://langtech.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "세계문화예술경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "세계문화예술경영연구소", "홈페이지URL": "http://waci.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "디지털인문한국학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "디지털인문한국학연구소", "홈페이지URL": "http://dhks.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "언어문화소통연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어문화소통연구소", "홈페이지URL": "https://lisi.hufs.ac.kr/", "error": ""},
    {"구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "정보ㆍ기록학 연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "정보ㆍ기록학 연구소", "홈페이지URL": "", "error": ""},
    {"구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업지원팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업지원팀", "홈페이지URL": "", "error": ""},
    {"구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영1팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영1팀", "홈페이지URL": "", "error": ""},
    {"구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영2팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영2팀", "홈페이지URL": "", "error": ""},
    {"구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영3팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영3팀", "홈페이지URL": "", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "통번역센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "통번역센터", "홈페이지URL": "http://www.hufscit.com/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "외국어연수평가원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국어연수평가원", "홈페이지URL": "http://flttc.hufs.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "FLEX센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "FLEX센터", "홈페이지URL": "http://flex.hufs.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "서울평생교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "서울평생교육원", "홈페이지URL": "http://edulife.hufs.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "TESOL전문교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "TESOL전문교육원", "홈페이지URL": "http://tesol.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "한국어문화교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "한국어문화교육원", "홈페이지URL": "http://www.korean.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "국제사회교육원(글로벌평생교육원)", "구분3": "국제사회교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "국제사회교육원", "홈페이지URL": "http://gla.hufs.ac.kr/", "error": ""},
    {"구분1": "부속교육기관", "구분2": "국제사회교육원(글로벌평생교육원)", "구분3": "영재교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "영재교육원", "홈페이지URL": "http://gifted.hufs.ac.kr/", "error": ""},
    {"구분1": "RISE사업본부", "구분2": "경기RISE사업단", "구분3": "경기RISE사업운영팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "경기RISE사업운영팀", "홈페이지URL": "", "error": ""},
    {"구분1": "RISE사업본부", "구분2": "서울RISE사업단", "구분3": "서울RISE사업운영팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "서울RISE사업운영팀", "홈페이지URL": "", "error": ""},
    {"구분1": "글로벌창업지원단", "구분2": "창업지원운영팀", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업지원운영팀", "홈페이지URL": "https://startup.hufs.ac.kr/", "error": ""},
    {"구분1": "글로벌창업지원단", "구분2": "창업인재양성센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업인재양성센터", "홈페이지URL": "https://startup.hufs.ac.kr/", "error": ""},
    {"구분1": "글로벌창업지원단", "구분2": "학생창업보육센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "학생창업보육센터", "홈페이지URL": "https://startup.hufs.ac.kr/", "error": ""},
    {"구분1": "첨단미래교육원", "구분2": "첨단미래교육지원팀", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "첨단미래교육지원팀", "홈페이지URL": "", "error": ""},
    {"구분1": "첨단미래교육원", "구분2": "AI교육단", "구분3": "SW기초교육센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "SW기초교육센터", "홈페이지URL": "http://soft.hufs.ac.kr/", "error": ""},
    {"구분1": "첨단미래교육원", "구분2": "시스템반도체교육단", "구분3": "SoC기초교육센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "SoC기초교육센터", "홈페이지URL": "", "error": ""}
]


# =========================
# 공통
# =========================
EMAIL_REGEX = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )
    })
    return session


def absolute_url(base_url: str, href: str) -> str:
    href = clean_text(href)
    if not href:
        return ""
    return urljoin(base_url, href)


def unique_keep_order(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for v in values:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(v)
    return result


def extract_emails_from_text(text: str) -> List[str]:
    if not text:
        return []
    emails = EMAIL_REGEX.findall(text)
    emails = [clean_text(x).strip(".,;:()[]<>") for x in emails if clean_text(x)]
    return unique_keep_order(emails)


def extract_mailtos(soup: BeautifulSoup) -> List[str]:
    emails: List[str] = []
    for a_tag in soup.select('a[href^="mailto:"]'):
        href = a_tag.get("href") or ""
        email = href.replace("mailto:", "").strip()
        email = email.split("?")[0].strip()
        if email:
            emails.append(email)
    return unique_keep_order(emails)


def score_email(email: str, og_name: str, url: str) -> int:
    """
    점수 높을수록 우선
    - 조직명 일부가 메일 앞부분/도메인에 들어가면 가점
    - 대표메일 성격(admin, office 등) 가점
    """
    score = 0
    email_l = email.lower()
    og_l = clean_text(og_name).lower()
    url_l = clean_text(url).lower()

    if og_l:
        og_tokens = re.findall(r"[가-힣A-Za-z0-9]+", og_l)
        for token in og_tokens:
            if len(token) >= 2 and token.lower() in email_l:
                score += 5

    for token in ["admin", "office", "dept", "info", "staff", "support", "manager", "contact"]:
        if token in email_l:
            score += 3

    if "hufs.ac.kr" in email_l:
        score += 2

    if url_l:
        try:
            host = re.sub(r"^https?://", "", url_l).split("/")[0]
            if host and host in email_l:
                score += 3
        except Exception:
            pass

    return score


def choose_best_email(emails: List[str], og_name: str, url: str) -> str:
    if not emails:
        return ""
    scored = sorted(
        emails,
        key=lambda x: (-score_email(x, og_name, url), x)
    )
    return scored[0]


# =========================
# 페이지 파싱
# =========================
def fetch_html(url: str, session: Optional[requests.Session] = None, timeout: int = 20) -> str:
    sess = session or create_session()
    resp = sess.get(url, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def extract_footer_text(soup: BeautifulSoup) -> str:
    texts: List[str] = []

    for sel in ["footer", "#footer", ".footer", ".foot", "#ft", "#fnb"]:
        for tag in soup.select(sel):
            txt = clean_text(tag.get_text(" ", strip=True))
            if txt:
                texts.append(txt)

    return " ".join(texts).strip()


def extract_all_page_text(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    return clean_text(body.get_text(" ", strip=True))


def find_emails_in_page(html: str, base_url: str, og_name: str) -> Tuple[str, List[str]]:
    soup = BeautifulSoup(html, "html.parser")

    # 1) footer 우선
    footer_text = extract_footer_text(soup)
    footer_emails = extract_emails_from_text(footer_text)
    footer_mailtos = extract_mailtos(soup)

    footer_all = unique_keep_order(footer_emails + footer_mailtos)
    best_footer_email = choose_best_email(footer_all, og_name, base_url)
    if best_footer_email:
        return best_footer_email, footer_all

    # 2) 전체 페이지 fallback
    page_text = extract_all_page_text(soup)
    page_emails = extract_emails_from_text(page_text)
    page_mailtos = extract_mailtos(soup)

    page_all = unique_keep_order(page_emails + page_mailtos)
    best_page_email = choose_best_email(page_all, og_name, base_url)
    if best_page_email:
        return best_page_email, page_all

    # 3) iframe fallback
    iframe_emails: List[str] = []
    for iframe in soup.select("iframe[src]"):
        src = clean_text(iframe.get("src"))
        iframe_url = absolute_url(base_url, src)
        if not iframe_url:
            continue

        try:
            iframe_html = fetch_html(iframe_url)
            iframe_soup = BeautifulSoup(iframe_html, "html.parser")
            iframe_text = extract_footer_text(iframe_soup) or extract_all_page_text(iframe_soup)
            iframe_found = extract_emails_from_text(iframe_text) + extract_mailtos(iframe_soup)
            iframe_emails.extend(iframe_found)
        except Exception:
            pass

    iframe_emails = unique_keep_order(iframe_emails)
    best_iframe_email = choose_best_email(iframe_emails, og_name, base_url)
    if best_iframe_email:
        return best_iframe_email, iframe_emails

    return "", []


# =========================
# 업무명 생성
# =========================
def make_task_name(item: Dict[str, Any]) -> str:
    """
    사용자가 원한 형태:
    '업무': '행정'
    일단 기본값은 행정으로 넣고,
    필요하면 구분값 기반으로 확장 가능
    """
    return "행정"


# =========================
# 1건 처리
# =========================
def enrich_detail_item(index: int, item: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    result = dict(item)

    homepage_url = clean_text(result.get("홈페이지URL", ""))
    og_name = clean_text(result.get("selectedOgNm", "")) or clean_text(result.get("구분3", "")) or clean_text(result.get("구분2", ""))

    result["업무"] = ""
    result["이메일"] = ""
    result["이메일목록"] = ""
    result["상세에러"] = ""

    if not homepage_url:
        result["상세에러"] = "홈페이지URL 없음"
        return index, result

    try:
        html = fetch_html(homepage_url)
        best_email, all_emails = find_emails_in_page(html, homepage_url, og_name)

        result["업무"] = make_task_name(result)
        result["이메일"] = best_email
        result["이메일목록"] = " | ".join(all_emails)
        return index, result

    except Exception as e:
        result["상세에러"] = str(e)
        return index, result


# =========================
# 멀티쓰레드
# =========================
def enrich_detail_url_list_multithread(
        items: List[Dict[str, Any]],
        max_workers: int = MAX_WORKERS,
) -> List[Dict[str, Any]]:
    if not items:
        return []

    results: List[Optional[Dict[str, Any]]] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(enrich_detail_item, idx, item): idx
            for idx, item in enumerate(items)
        }

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                result_index, result_item = future.result()
                results[result_index] = result_item
                print(
                    f"[{result_index + 1}/{len(items)}] 완료 "
                    f"- {result_item.get('selectedOgNm', '')} "
                    f"/ {result_item.get('이메일', '')}"
                )
            except Exception as e:
                failed_item = dict(items[idx])
                failed_item["업무"] = ""
                failed_item["이메일"] = ""
                failed_item["이메일목록"] = ""
                failed_item["상세에러"] = str(e)
                results[idx] = failed_item
                print(f"[{idx + 1}/{len(items)}] 실패 - {failed_item.get('selectedOgNm', '')} / {e}")

    final_list: List[Dict[str, Any]] = []
    for idx, row in enumerate(results):
        if row is None:
            fallback = dict(items[idx])
            fallback["업무"] = ""
            fallback["이메일"] = ""
            fallback["이메일목록"] = ""
            fallback["상세에러"] = "결과 없음"
            final_list.append(fallback)
        else:
            final_list.append(row)

    return final_list


# =========================
# 실행
# =========================
if __name__ == "__main__":
    detail_url_list = enrich_detail_url_list_multithread(detail_url_list, max_workers=10)

    for row in detail_url_list:
        print(row)