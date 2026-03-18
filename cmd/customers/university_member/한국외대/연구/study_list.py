

# -*- coding: utf-8 -*-
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


OGCHART_URL = "https://www.hufs.ac.kr/ogchart/hufs/getOgchart.do"
MAX_WORKERS = 10

orgList = [
    { "구분1": "연구산학협력단", "구분2": "연구지원1팀(서울)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구지원1팀(서울)" },
    { "구분1": "연구산학협력단", "구분2": "연구지원2팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구지원2팀(글로벌)" },
    { "구분1": "연구산학협력단", "구분2": "기획총괄팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기획총괄팀(글로벌)" },
    { "구분1": "연구산학협력단", "구분2": "산학지원팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "산학지원팀(글로벌)" },
    { "구분1": "연구산학협력단", "구분2": "산학재무회계팀(글로벌)", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "산학재무회계팀(글로벌)" },
    { "구분1": "연구산학협력단", "구분2": "창업보육센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업보육센터" },
    { "구분1": "연구산학협력단", "구분2": "지산학협력R&DB센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "지산학협력R&DB센터" },
    { "구분1": "연구산학협력단", "구분2": "기술이전센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기술이전센터" },
    { "구분1": "연구산학협력단", "구분2": "다문화교육원", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "다문화교육원" },
    { "구분1": "연구산학협력단", "구분2": "공동기기원", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "공동기기원" },
    { "구분1": "연구산학협력단", "구분2": "연구윤리센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "연구윤리센터" },

    { "구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "외국어교육연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국어교육연구소" },
    { "구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "외국문학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국문학연구소" },
    { "구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "언어연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어연구소" },
    { "구분1": "부속연구기관", "구분2": "외국어문연구센터", "구분3": "통번역연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "통번역연구소" },

    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "일본연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "일본연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중국연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중국연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "동남아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "동남아연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중동연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중동연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "영미연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "영미연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중남미연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중남미연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "EU연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "EU연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "동유럽발칸연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "동유럽발칸연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "러시아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "러시아연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "아프리카연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "아프리카연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "인도연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "인도연구소" },
    { "구분1": "부속연구기관", "구분2": "국제지역연구센터", "구분3": "중앙아시아연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "중앙아시아연구소" },

    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "경제경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "경제경영연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "철학문화연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "철학문화연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "역사문화연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "역사문화연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "미디어커뮤니케이션연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "미디어커뮤니케이션연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "글로벌경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "글로벌경영연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "기초과학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "기초과학연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "법학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "법학연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "정보산업공학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "정보산업공학연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "환경과학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "환경과학연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "글로벌정치연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "글로벌정치연구소" },
    { "구분1": "부속연구기관", "구분2": "전문분야연구센터", "구분3": "국정관리연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "국정관리연구소" },

    { "구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "언어공학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어공학연구소" },
    { "구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "세계문화예술경영연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "세계문화예술경영연구소" },
    { "구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "디지털인문한국학연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "디지털인문한국학연구소" },
    { "구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "언어문화소통연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "언어문화소통연구소" },
    { "구분1": "부속연구기관", "구분2": "융합연구센터", "구분3": "정보ㆍ기록학 연구소", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "정보ㆍ기록학 연구소" },

    { "구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업지원팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업지원팀" },
    { "구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영1팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영1팀" },
    { "구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영2팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영2팀" },
    { "구분1": "부속교육기관", "구분2": "사업지원처", "구분3": "사업본부 운영3팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "사업본부 운영3팀" },

    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "통번역센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "통번역센터" },
    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "외국어연수평가원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "외국어연수평가원" },
    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "FLEX센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "FLEX센터" },
    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "서울평생교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "서울평생교육원" },
    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "TESOL전문교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "TESOL전문교육원" },
    { "구분1": "부속교육기관", "구분2": "외국어연수평가원(서울평생교육원)", "구분3": "한국어문화교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "한국어문화교육원" },

    { "구분1": "부속교육기관", "구분2": "국제사회교육원(글로벌평생교육원)", "구분3": "국제사회교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "국제사회교육원" },
    { "구분1": "부속교육기관", "구분2": "국제사회교육원(글로벌평생교육원)", "구분3": "영재교육원", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "영재교육원" },

    { "구분1": "RISE사업본부", "구분2": "경기RISE사업단", "구분3": "경기RISE사업운영팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "경기RISE사업운영팀" },
    { "구분1": "RISE사업본부", "구분2": "서울RISE사업단", "구분3": "서울RISE사업운영팀", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "서울RISE사업운영팀" },

    { "구분1": "글로벌창업지원단", "구분2": "창업지원운영팀", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업지원운영팀" },
    { "구분1": "글로벌창업지원단", "구분2": "창업인재양성센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "창업인재양성센터" },
    { "구분1": "글로벌창업지원단", "구분2": "학생창업보육센터", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "학생창업보육센터" },

    { "구분1": "첨단미래교육원", "구분2": "첨단미래교육지원팀", "구분3": "", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "첨단미래교육지원팀" },
    { "구분1": "첨단미래교육원", "구분2": "AI교육단", "구분3": "SW기초교육센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "SW기초교육센터" },
    { "구분1": "첨단미래교육원", "구분2": "시스템반도체교육단", "구분3": "SoC기초교육센터", "selectedDepthNm": "산학연계 부총장", "selectedOgNm": "SoC기초교육센터" }
]

# =========================
# 공통
# =========================
def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.hufs.ac.kr/hufs/11367/subview.do",
        "Origin": "https://www.hufs.ac.kr",
    })
    return session


def extract_homepage_url_from_cn(cn_html: str) -> str:
    if not cn_html:
        return ""

    soup = BeautifulSoup(cn_html, "html.parser")

    # 1순위: 홈페이지 바로가기 영역
    a_tag = soup.select_one(".home-icon-box a[href]")
    if a_tag:
        return (a_tag.get("href") or "").strip()

    # 2순위: 텍스트 기반 fallback
    for a_tag in soup.select("a[href]"):
        href = (a_tag.get("href") or "").strip()
        text = a_tag.get_text(" ", strip=True)
        if href and "홈페이지" in text:
            return href

    return ""


def fetch_homepage_url(
        selected_depth_nm: str,
        selected_og_nm: str,
        timeout: int = 20,
) -> str:
    payload = {
        "selectedDepthNm": selected_depth_nm,
        "selectedOgNm": selected_og_nm,
    }

    with create_session() as session:
        resp = session.post(OGCHART_URL, data=payload, timeout=timeout)
        resp.raise_for_status()

        data = resp.json()
        cn_html = data.get("cn", "") or ""
        return extract_homepage_url_from_cn(cn_html)


def enrich_one(index: int, item: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    result = dict(item)

    selected_depth_nm = str(result.get("selectedDepthNm", "") or "").strip()
    selected_og_nm = str(result.get("selectedOgNm", "") or "").strip()

    homepage_url = ""
    error_msg = ""

    try:
        homepage_url = fetch_homepage_url(
            selected_depth_nm=selected_depth_nm,
            selected_og_nm=selected_og_nm,
        )
    except Exception as e:
        error_msg = str(e)

    result["홈페이지URL"] = homepage_url
    result["error"] = error_msg

    return index, result


def enrich_org_list_multithread(items: List[Dict[str, Any]], max_workers: int = MAX_WORKERS) -> List[Dict[str, Any]]:
    if not items:
        return []

    results: List[Optional[Dict[str, Any]]] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(enrich_one, idx, item): idx
            for idx, item in enumerate(items)
        }

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                result_index, result_item = future.result()
                results[result_index] = result_item
                print(f"[{result_index + 1}/{len(items)}] 완료 - {result_item.get('selectedOgNm', '')}")
            except Exception as e:
                failed_item = dict(items[idx])
                failed_item["홈페이지URL"] = ""
                failed_item["error"] = str(e)
                results[idx] = failed_item
                print(f"[{idx + 1}/{len(items)}] 실패 - {failed_item.get('selectedOgNm', '')} / {e}")

    return [item if item is not None else dict(items[idx]) for idx, item in enumerate(results)]


# =========================
# 실행
# =========================
if __name__ == "__main__":
    # 전역 orgList 를 멀티쓰레드로 돌려서 홈페이지URL 붙이기
    orgList = enrich_org_list_multithread(orgList, max_workers=10)

    for row in orgList:
        print(row)