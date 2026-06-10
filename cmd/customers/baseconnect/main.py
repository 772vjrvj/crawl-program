import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse, unquote, parse_qs

import pandas as pd
import requests
from bs4 import BeautifulSoup


OUTPUT_EXCEL = "baseconnect_all_categories.xlsx"
BASE_URL = "https://baseconnect.in"

# 페이지당 요청 간격
REQUEST_DELAY_SEC = 1

# 안전장치: 한 URL당 최대 페이지 수
MAX_PAGES_PER_SOURCE = 100




# ============================================================
# 수집 대상
# search_category 컬럼에 이 값이 들어감
# ============================================================
SOURCES = [
    {
        "search_category": "라이선싱",
        "url": "https://baseconnect.in/companies/keyword/f69241fd-c6aa-4e01-8b74-29962c0f7c06",
    },
    {
        "search_category": "출판/플랫폼",
        "url": "https://baseconnect.in/companies/category/684ecb15-0316-4eea-a5df-3bbc3daab1c8",
    },
    {
        "search_category": "애니",
        "url": "https://baseconnect.in/companies/category/1536b372-85b1-4f8a-86af-f000f57377ef",
    },
    {
        "search_category": "영상",
        "url": "https://baseconnect.in/companies/category/c90aa02c-64fa-43db-a511-d63b1466c6a1",
    },
    {
        "search_category": "게임",
        "url": "https://baseconnect.in/companies/category/79525d9e-2fec-4e30-b088-b29d596ecaa7",
    },
    {
        "search_category": "캐릭터/일러스트 제작",
        "url": "https://baseconnect.in/companies/keyword/665b9c73-3f70-4705-93b5-2e03244966ba",
    },
]


# ============================================================
# 필요하면 쿠키 넣기
# 지금 HTML 방식이 잘 되면 빈 값으로 둬도 됨
# 403 뜨면 개발자도구에서 cookie 값만 복사해서 넣기
# ============================================================
COOKIE = ""


def make_page_url(base_url: str, page: int) -> str:
    """
    page=1은 원본 URL 그대로.
    page>=2는 ?page=2 형식으로 붙임.
    기존 query가 있으면 유지하면서 page만 갱신.
    """
    if page <= 1:
        return base_url

    parsed = urlparse(base_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["page"] = str(page)

    new_query = urlencode(query_items, doseq=True)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def restore_utf8_mojibake(value: str) -> str:
    """
    혹시 일본어가 깨진 경우 복구.
    정상 일본어면 대부분 그대로 반환됨.
    """
    if not isinstance(value, str):
        return value

    if "ã" not in value and "æ" not in value and "ï" not in value:
        return value

    raw = bytearray()
    changed = False

    for ch in value:
        code = ord(ch)

        if code <= 255:
            raw.append(code)
            if code >= 128:
                changed = True
        else:
            try:
                raw.extend(ch.encode("cp1252"))
                changed = True
            except UnicodeEncodeError:
                raw.extend(ch.encode("utf-8"))

    if not changed:
        return value

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return value


def fix_text(value: Optional[str]) -> str:
    return restore_utf8_mojibake(clean_text(value))


def normalize_image_url(src: str) -> str:
    """
    Next.js 이미지가 /_next/image?url=... 형태면 원본 이미지 URL 복구.
    """
    src = clean_text(src)

    if not src:
        return ""

    if src.startswith("/_next/image"):
        parsed = urlparse(src)
        qs = parse_qs(parsed.query)
        original = qs.get("url", [""])[0]

        if original:
            return unquote(original)

    return urljoin(BASE_URL, src)


def extract_image_url(card) -> str:
    img = card.find("img")

    if not img:
        return ""

    src = img.get("src") or ""
    if src:
        return normalize_image_url(src)

    srcset = img.get("srcset") or ""
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        return normalize_image_url(first)

    return ""


def extract_dt_dd_pairs(card) -> Dict[str, str]:
    result = {}

    for dt in card.find_all("dt"):
        key = fix_text(dt.get_text(" ", strip=True))
        key = key.replace(":", "").replace("：", "").strip()

        dd = None

        parent = dt.parent
        if parent:
            dd = parent.find("dd")

        if dd is None:
            dd = dt.find_next("dd")

        if not key or dd is None:
            continue

        value = fix_text(dd.get_text(" ", strip=True))

        if key:
            result[key] = value

    return result


def extract_tags(card) -> Dict[str, str]:
    categories = []
    listing_markets = []

    for a in card.find_all("a", href=True):
        href = a.get("href", "")
        label = fix_text(a.get_text(" ", strip=True))

        if not label:
            continue

        if href.startswith("/companies/category/"):
            categories.append(label)

        elif href.startswith("/companies/listing_market/"):
            listing_markets.append(label)

    return {
        "categories": ", ".join(dict.fromkeys(categories)),
        "listing_market": ", ".join(dict.fromkeys(listing_markets)),
    }


def find_company_cards(soup: BeautifulSoup):
    """
    회사명 h3를 포함한 /companies/{uuid} 링크 기준으로 카드 section 찾기.
    """
    cards = []
    seen_company_ids = set()

    company_href_pattern = re.compile(r"^/companies/[0-9a-f-]{36}$")

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")

        if not company_href_pattern.match(href):
            continue

        h3 = a.find("h3")
        if h3 is None:
            continue

        company_id = href.rstrip("/").split("/")[-1]

        if company_id in seen_company_ids:
            continue

        card = a.find_parent("section")
        if card is None:
            continue

        seen_company_ids.add(company_id)
        cards.append((company_id, href, card))

    return cards


def extract_company_from_card(
        search_category: str,
        source_url: str,
        page: int,
        page_url: str,
        company_id: str,
        href: str,
        card,
) -> Dict[str, str]:
    title_a = card.find("a", href=re.compile(rf"^/companies/{re.escape(company_id)}$"))
    h3 = title_a.find("h3") if title_a else card.find("h3")

    company_name = fix_text(h3.get_text(" ", strip=True)) if h3 else ""

    h5 = card.find("h5")
    summary = fix_text(h5.get_text(" ", strip=True)) if h5 else ""

    description = ""
    p = card.find("p")
    if p:
        description = fix_text(p.get_text(" ", strip=True))

    details = extract_dt_dd_pairs(card)
    tags = extract_tags(card)

    return {
        "search_category": search_category,
        "company_id": company_id,
        "company_name": company_name,
        "company_url": urljoin(BASE_URL, href),
        "image_url": extract_image_url(card),
        "categories": tags.get("categories", ""),
        "listing_market": tags.get("listing_market", ""),
        "summary": summary,
        "description": description,
        "head_office_address": details.get("本社登記住所", ""),
        "established": details.get("設立年月", ""),
        "capital": details.get("資本金", ""),
        "updated_at": details.get("更新日", ""),
        "page": page,
        "page_url": page_url,
        "source_url": source_url,
    }


def build_headers(page_url: str) -> Dict[str, str]:
    headers = {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": page_url,
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }

    if COOKIE:
        headers["cookie"] = COOKIE

    return headers


def fetch_html(session: requests.Session, page_url: str) -> str:
    headers = build_headers(page_url)

    res = session.get(page_url, headers=headers, timeout=30)

    print(f"[HTTP] status={res.status_code} url={res.url}")

    if res.status_code != 200:
        print(res.text[:1000])

    res.raise_for_status()
    res.encoding = "utf-8"

    return res.text


def parse_companies_from_html(
        html: str,
        search_category: str,
        source_url: str,
        page: int,
        page_url: str,
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    cards = find_company_cards(soup)

    if not cards:
        print(f"[INFO] 회사 카드 없음: {search_category} / page={page}")
        return []

    rows = []

    for company_id, href, card in cards:
        row = extract_company_from_card(
            search_category=search_category,
            source_url=source_url,
            page=page,
            page_url=page_url,
            company_id=company_id,
            href=href,
            card=card,
        )
        rows.append(row)

    return rows


def crawl_one_source(session: requests.Session, source: Dict[str, str]) -> List[Dict[str, str]]:
    search_category = source["search_category"]
    source_url = source["url"]

    print("=" * 100)
    print(f"[SOURCE 시작] {search_category}")
    print(f"[SOURCE URL] {source_url}")

    source_rows = []
    previous_page_company_ids = set()

    for page in range(1, MAX_PAGES_PER_SOURCE + 1):
        page_url = make_page_url(source_url, page)

        print("-" * 100)
        print(f"[페이지 시작] {search_category} / page={page}")
        print(f"[페이지 URL] {page_url}")

        try:
            html = fetch_html(session, page_url)

            # 디버깅용 저장
            debug_file = f"debug_{search_category.replace('/', '_')}_page_{page}.html"
            with open(debug_file, "w", encoding="utf-8", errors="replace") as f:
                f.write(html)

            rows = parse_companies_from_html(
                html=html,
                search_category=search_category,
                source_url=source_url,
                page=page,
                page_url=page_url,
            )

            if not rows:
                print(f"[페이지 종료] {search_category} / page={page} / 데이터 없음")
                break

            current_page_company_ids = {row["company_id"] for row in rows}

            # 마지막 페이지 이후 같은 결과가 반복되는 사이트 방어
            if current_page_company_ids == previous_page_company_ids:
                print(f"[중복 페이지 감지] {search_category} / page={page} / 종료")
                break

            previous_page_company_ids = current_page_company_ids

            source_rows.extend(rows)

            print(f"[페이지 완료] {search_category} / page={page} / count={len(rows)}")

            time.sleep(REQUEST_DELAY_SEC)

        except requests.HTTPError as e:
            print(f"[HTTP ERROR] {search_category} / page={page} / {e}")
            break

        except Exception as e:
            print(f"[ERROR] {search_category} / page={page} / {e}")
            break

    print(f"[SOURCE 완료] {search_category} / total={len(source_rows)}")

    return source_rows


def crawl_all_sources():
    session = requests.Session()
    all_rows = []

    for source in SOURCES:
        rows = crawl_one_source(session, source)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)

    columns = [
        "search_category",
        "company_id",
        "company_name",
        "company_url",
        "image_url",
        "categories",
        "listing_market",
        "summary",
        "description",
        "head_office_address",
        "established",
        "capital",
        "updated_at",
        "page",
        "page_url",
        "source_url",
    ]

    df = df.reindex(columns=columns)

    # 같은 회사가 여러 검색분류에 걸릴 수 있으므로 기본은 중복 제거 안 함
    df.to_excel(OUTPUT_EXCEL, index=False)

    print("=" * 100)
    print(f"[전체 완료] {len(df)}건 저장")
    print(f"[파일] {OUTPUT_EXCEL}")

    return df


if __name__ == "__main__":
    crawl_all_sources()