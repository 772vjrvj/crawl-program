import re
import csv
import json
import html
import threading
from typing import Any, Dict, List, Set
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


# === 신규 === 이메일 추출 정규식
EMAIL_PATTERN = re.compile(
    r'([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})',
    re.IGNORECASE
)

# === 신규 === 이메일이 아닌 리소스 파일 확장자 제외
EXCLUDED_ENDINGS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".map"
)

# === 신규 === 스레드별 Session 보관
_thread_local = threading.local()


def get_thread_session() -> requests.Session:
    """
    스레드별 requests.Session 생성/재사용
    """
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def normalize_email(value: str) -> str:
    """
    이메일 문자열 정리
    """
    if not value:
        return ""

    email = value.strip()
    email = html.unescape(email)
    email = unquote(email)

    email = email.strip(" \t\r\n<>[](){}'\";,|")

    if email.lower().startswith("mailto:"):
        email = email[7:].strip()

    if "?" in email:
        email = email.split("?", 1)[0].strip()

    return email.lower()


def is_valid_email(email: str) -> bool:
    """
    이메일 후보 검증
    """
    if not email:
        return False

    if "@" not in email:
        return False

    if email.endswith(EXCLUDED_ENDINGS):
        return False

    if ".." in email:
        return False

    return True


def extract_emails_from_text(text: str) -> Set[str]:
    """
    일반 텍스트에서 이메일 추출
    """
    found: Set[str] = set()

    if not text:
        return found

    for match in EMAIL_PATTERN.findall(text):
        email = normalize_email(match)
        if is_valid_email(email):
            found.add(email)

    return found


def extract_emails_from_html(html_text: str) -> List[str]:
    """
    HTML 전체에서 이메일 추출
    - mailto 링크
    - 페이지 텍스트
    - 원본 HTML
    """
    found: Set[str] = set()

    soup = BeautifulSoup(html_text, "html.parser")

    # 1) mailto 링크
    for a_tag in soup.select("a[href]"):
        href = a_tag.get("href", "").strip()
        if href.lower().startswith("mailto:"):
            email = normalize_email(href)
            if is_valid_email(email):
                found.add(email)

    # 2) 화면 텍스트 전체
    page_text = soup.get_text("\n", strip=True)
    found.update(extract_emails_from_text(page_text))

    # 3) 원본 HTML 전체
    found.update(extract_emails_from_text(html_text))

    return sorted(found)


def fetch_page_html(url: str, timeout: int = 20) -> str:
    """
    페이지 HTML 가져오기
    """
    session = get_thread_session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        )
    }

    response = session.get(
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=True
    )
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding

    return response.text


def collect_emails_from_url(url: str, timeout: int = 20) -> List[str]:
    """
    URL에서 이메일 목록 수집
    """
    html_text = fetch_page_html(url=url, timeout=timeout)
    return extract_emails_from_html(html_text)


def process_one_item(index: int, item: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    """
    단일 객체 처리
    """
    row = dict(item)
    url = str(row.get("url", "")).strip()

    row["emails"] = []
    row["email"] = ""
    row["email_count"] = 0
    row["error"] = ""
    row["_index"] = index

    if not url:
        row["error"] = "url 없음"
        print(f"[{index}] url 없음")
        return row

    try:
        emails = collect_emails_from_url(url=url, timeout=timeout)
        row["emails"] = emails
        row["email"] = emails[0] if emails else ""
        row["email_count"] = len(emails)

        print(f"[{index}] {url} -> {len(emails)}개")
        if emails:
            print(f"    emails: {emails}")

    except Exception as e:
        row["error"] = str(e)
        print(f"[{index}] 오류: {url} -> {str(e)}")

    return row


def enrich_items_with_emails_multithread(
        items: List[Dict[str, Any]],
        max_workers: int = 10,
        timeout: int = 20
) -> List[Dict[str, Any]]:
    """
    멀티쓰레드로 객체 리스트에 emails / email / email_count / error 추가
    """
    if not items:
        return []

    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(process_one_item, index, item, timeout): index
            for index, item in enumerate(items, start=1)
        }

        for future in as_completed(future_map):
            index = future_map[future]
            try:
                row = future.result()
                results.append(row)
            except Exception as e:
                print(f"[{index}] future 처리 오류 -> {str(e)}")
                results.append({
                    "name": "",
                    "url": "",
                    "emails": [],
                    "email": "",
                    "email_count": 0,
                    "error": str(e),
                    "_index": index
                })

    # === 신규 === 원래 입력 순서대로 정렬
    results.sort(key=lambda x: x.get("_index", 0))

    # === 신규 === 내부 인덱스 제거
    for row in results:
        if "_index" in row:
            del row["_index"]

    return results


def save_results_to_csv(results: List[Dict[str, Any]], output_path: str) -> None:
    """
    결과를 CSV로 저장
    """
    fieldnames = ["name", "url", "email", "email_count", "emails", "error"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in results:
            writer.writerow({
                "name": row.get("name", ""),
                "url": row.get("url", ""),
                "email": row.get("email", ""),
                "email_count": row.get("email_count", 0),
                "emails": " | ".join(row.get("emails", [])),
                "error": row.get("error", "")
            })


if __name__ == "__main__":
    # === 신규 === 여기에 객체 리스트 직접 넣으시면 됩니다
    items: List[Dict[str, Any]] = [
        { "name": "경영연구원", "url": "http://mri.khu.ac.kr/" },
        { "name": "경희법학연구소", "url": "http://ils.khu.ac.kr/" },
        { "name": "고황의학연구소", "url": "" },
        { "name": "공공거버넌스연구소", "url": "https://pnc.khu.ac.kr/" },
        { "name": "관광산업연구원", "url": "" },
        { "name": "교육발전연구원", "url": "https://character.khu.ac.kr/" },
        { "name": "국제개발협력연구센터", "url": "http://cidec.khu.ac.kr/" },
        { "name": "글로벌통상금융연구원", "url": "http://khtri.khu.ac.kr/" },
        { "name": "글로컬역사문화연구소", "url": "" },
        { "name": "기초과학연구소", "url": "" },
        { "name": "기후-몸 연구소", "url": "http://thericb.khu.ac.kr/" },
        { "name": "노인성및뇌질환연구소", "url": "" },
        { "name": "동서간호학연구소", "url": "http://www.ewnri.or.kr/" },
        { "name": "동서골관절연구소", "url": "" },
        { "name": "동서의학연구소", "url": "http://khmsri.or.kr/ewmri/" },
        { "name": "디지털헬스센터", "url": "https://cdh.khu.ac.kr" },
        { "name": "디지털콘텐츠 IP & Assets 연구소", "url": "" },
        { "name": "문화예술경영연구소", "url": "http://acm.khu.ac.kr/" },
        { "name": "미디어혁신연구소", "url": "http://comstudy.khu.ac.kr/" },
        { "name": "미래융합치의학연구소", "url": "" },
        { "name": "미래혁신정책연구원", "url": "" },
        { "name": "바이오나노컴포지트연구소", "url": "" },
        { "name": "비폭력연구소", "url": "" },
        { "name": "사회과학연구원", "url": "http://riss.khu.ac.kr/" },
        { "name": "산업관계연구소", "url": "http://www.khuiir.ac.kr/" },
        { "name": "생활과학연구소", "url": "" },
        { "name": "스마트관광연구소", "url": "http://strc.khu.ac.kr/" },
        { "name": "스마트 국방·우주 융합 연구소", "url": "" },
        { "name": "언어정보연구소", "url": "http://isli.khu.ac.kr/" },
        { "name": "융합약학연구소", "url": "http://pharm.khu.ac.kr/" },
        { "name": "융합한의과학연구소", "url": "" },
        { "name": "의과학연구소", "url": "https://sites.google.com/site/khubiomedins/" },
        { "name": "의료산업연구원", "url": "" },
        { "name": "인류사회재건연구원", "url": "http://kihs.khu.ac.kr/" },
        { "name": "인문·사회과학 데이터 연구소", "url": "" },
        { "name": "인문융합연구센터", "url": "" },
        { "name": "인문학연구원", "url": "http://ihuman.khu.ac.kr/index.asp" },
        { "name": "임상영양연구소", "url": "http://www.rimn.re.kr/public_html/renewal/" },
        { "name": "임피던스영상신기술연구센터", "url": "http://iirc.khu.ac.kr/" },
        { "name": "장애인건강연구소", "url": "" },
        { "name": "정보디스플레이연구소", "url": "http://adrc2000.com/" },
        { "name": "종교시민문화연구소", "url": "https://ircc.khu.ac.kr" },
        { "name": "청강한의학역사문화연구소", "url": "" },
        { "name": "침구경락융학연구센터", "url": "http://amsrc.org/" },
        { "name": "K-컬처·스토리콘텐츠연구소", "url": "https://kcsc.khu.ac.kr/" },
        { "name": "한국고대사·고고학연구소", "url": "http://www.ikaa.or.kr/" },
        { "name": "한국조류연구소", "url": "http://birds.khu.ac.kr" },
        { "name": "한국현대사연구원", "url": "http://blog.naver.com/modernhistory21" },
        { "name": "현대미술연구소", "url": "http://khufineart.wordpress.com/394-2/" },
        { "name": "후마니타스 교양교육연구소", "url": "http://liberal.khu.ac.kr/" }
    ]

    results = enrich_items_with_emails_multithread(
        items=items,
        max_workers=10,   # 동시 요청 개수
        timeout=20
    )

    # === 신규 === JSON도 같이 저장
    with open("research_institutes_with_emails.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # === 신규 === CSV 저장
    save_results_to_csv(
        results=results,
        output_path="research_institutes_with_emails.csv"
    )

    print("\n=== 완료 ===")
    print("JSON 저장: research_institutes_with_emails.json")
    print("CSV 저장 : research_institutes_with_emails.csv")