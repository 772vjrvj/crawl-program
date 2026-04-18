import asyncio
import aiohttp
import re
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import csv
import os

# ── 설정 ──────────────────────────────────────────────────────
CARD_LIST = ["AAP1731", "ABP1689", "ABP1384", "ABP1383", "AAP1483", "AAP1452"]

BASE_URL = "https://www.samsungcard.com/home/card/cardinfo/PGHPPCCCardCardinfoDetails001?code="
CDN_BASE = "https://static11.samsungcard.com"

category_data = [
    {"category_id": 1, "category_name": "온라인쇼핑", "category_list": ["온라인쇼핑", "삼성카드 쇼핑", "G마켓", "옥션", "11번가", "인터파크", "쿠팡", "티몬", "위메프", "SSG.COM", "롯데ON", "마켓컬리", "오아시스마켓"]},
    {"category_id": 2, "category_name": "패션/뷰티", "category_list": ["패션", "뷰티", "올리브영", "유니클로", "자라", "H&M", "8SECONDS"]},
    {"category_id": 3, "category_name": "슈퍼마켓/생활잡화", "category_list": ["슈퍼마켓", "생활잡화", "이마트", "트레이더스", "롯데마트", "홈플러스", "에브리데이", "빅마켓", "다이소"]},
    {"category_id": 4, "category_name": "백화점/아울렛/면세점", "category_list": ["백화점", "아울렛", "면세점", "신세계", "롯데", "현대", "갤러리아", "동아", "대구백화점", "AK플라자", "NC 대전 유성점", "NC 대전유성점", "신세계사이먼 프리미엄 아울렛", "현대프리미엄아울렛"]},
    {"category_id": 5, "category_name": "대중교통/택시", "category_list": ["대중교통", "택시"]},
    {"category_id": 6, "category_name": "자동차/주유", "category_list": ["자동차", "주유", "SK에너지", "GS칼텍스", "현대오일뱅크", "S-OIL"]},
    {"category_id": 7, "category_name": "반려동물", "category_list": ["반려동물"]},
    {"category_id": 8, "category_name": "구독/스트리밍", "category_list": ["구독", "스트리밍", "넷플릭스", "웨이브", "티빙", "왓챠", "멜론", "FLO"]},
    {"category_id": 9, "category_name": "레저/스포츠", "category_list": ["레저", "스포츠", "에버랜드", "롯데월드", "서울랜드", "통도환타지아", "대전오월드", "경주월드", "이월드", "캐리비안베이", "아쿠아환타지아", "캘리포니아비치", "중흥골드스파", "디오션리조트 워터파크", "스파밸리"]},
    {"category_id": 10, "category_name": "페이/간편결제", "category_list": ["페이", "간편결제", "삼성페이", "네이버페이", "카카오페이", "PAYCO", "스마일페이", "coupay", "SSGPAY", "L.PAY"]},
    {"category_id": 11, "category_name": "문화/엔터", "category_list": ["문화", "엔터", "YES24", "인터파크 도서", "알라딘", "교보문고"]},
    {"category_id": 12, "category_name": "생활비", "category_list": ["생활비", "SKT", "KT", "LG U+"]},
    {"category_id": 13, "category_name": "편의점", "category_list": ["편의점"]},
    {"category_id": 14, "category_name": "커피/카페/베이커리", "category_list": ["커피", "카페", "베이커리", "스타벅스", "이디야커피", "커피빈", "투썸플레이스", "블루보틀", "파리바게뜨", "배스킨라빈스", "던킨", "카페베네", "탐앤탐스", "엔제리너스", "할리스", "파스쿠찌", "아티제", "폴 바셋"]},
    {"category_id": 15, "category_name": "배달", "category_list": ["배달", "배달의민족", "요기요"]},
    {"category_id": 16, "category_name": "외식", "category_list": ["외식", "쉐이크쉑", "써브웨이"]},
    {"category_id": 17, "category_name": "여행/숙박", "category_list": ["여행", "숙박"]},
    {"category_id": 18, "category_name": "항공", "category_list": ["항공"]},
    {"category_id": 19, "category_name": "해외", "category_list": ["해외"]},
    {"category_id": 20, "category_name": "교육/육아", "category_list": ["교육", "육아", "씽크빅", "교원", "대교", "한솔교육"]},
    {"category_id": 21, "category_name": "의료", "category_list": ["의료"]},
]

# ── 공통 ──────────────────────────────────────────────────────
def log(msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

def line():
    print("=" * 60)

# ── STEP 1: Playwright로 __NUXT__ 추출 ────────────────────────
async def get_nuxt_data(card_code: str) -> dict:
    url = BASE_URL + card_code

    async def handle_route(route):
        if route.request.resource_type in ("image", "media", "font", "stylesheet"):
            await route.abort()
        else:
            await route.continue_()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="ko-KR",
        )
        page = await context.new_page()
        await page.route("**/*", handle_route)

        log(f"페이지 접속: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_function(
                """
                () => {
                    try {
                        const d = window.__NUXT__?.data?.[0];
                        return !!(d?.wcms?.pdList?.length);
                    } catch (e) {
                        return false;
                    }
                }
                """,
                timeout=15000,
            )
        except:
            await page.wait_for_timeout(5000)

        nuxt_data = await page.evaluate("() => window.__NUXT__?.data?.[0] || null")
        sell_start_dt = await page.evaluate(
            "() => document.getElementById('sellStrtdt')?.textContent?.trim() || ''"
        )

        await browser.close()

    if not nuxt_data:
        raise RuntimeError("__NUXT__.data[0] 추출 실패")

    return {
        "card_code": card_code,
        "sell_start_dt": sell_start_dt,
        "nuxt_data": nuxt_data,
    }

# ── STEP 2: 혜택 [카드 서비스 상세] HTML benefit_content 수집 ────────────────────────
def _get_text(el):
    soup = BeautifulSoup(str(el), "html.parser")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    return soup.get_text("", strip=True)

def _has_class(tag, keyword):
    return any(keyword in c for c in (tag.get("class") or []))

def _get_text_lines(elements):
    return "\n".join(
        txt
        for txt in [_get_text(el) for el in elements]
        if txt
    )

def _get_dt_dd_content(title_el):
    dds = []

    for sib in title_el.next_siblings:
        name = getattr(sib, "name", None)

        if name == "dt":
            break

        if name == "dd":
            dds.append(sib)

    return _get_text_lines(dds)

def _get_next_ul_content(title_el, ul_class_name):
    lines = []

    for sib in title_el.next_siblings:
        if not getattr(sib, "name", None):
            continue

        if sib.name in ["h5", "dt"]:
            break

        if sib.name == "ul" and ul_class_name in (sib.get("class") or []):
            table_box = sib.find(
                lambda tag: getattr(tag, "name", None) == "div"
                            and "table_col" in (tag.get("class") or [])
            )

            if table_box:
                for tr in table_box.find_all("tr"):
                    row_parts = []

                    for cell in tr.find_all(["th", "td"], recursive=False):
                        txt = _get_text(cell)
                        if not txt:
                            continue

                        if "first" in (cell.get("class") or []):
                            row_parts.append(f"{txt} :")
                        else:
                            row_parts.append(txt)

                    if row_parts:
                        if len(row_parts) >= 2 and row_parts[0].endswith(" :"):
                            lines.append(row_parts[0] + " " + " | ".join(row_parts[1:]))
                        else:
                            lines.append(" | ".join(row_parts))

                for li in sib.find_all("li", recursive=False):
                    if li.find(
                            lambda tag: getattr(tag, "name", None) == "div"
                                        and "table_col" in (tag.get("class") or [])
                    ):
                        continue

                    txt = _get_text(li)
                    if txt:
                        lines.append(txt)

                break

            for li in sib.find_all("li", recursive=False):
                txt = _get_text(li)
                if txt:
                    lines.append(txt)

            break

        if "table_col" in (sib.get("class") or []):
            for tr in sib.find_all("tr"):
                row_parts = []

                for cell in tr.find_all(["th", "td"], recursive=False):
                    txt = _get_text(cell)
                    if not txt:
                        continue

                    if "first" in (cell.get("class") or []):
                        row_parts.append(f"{txt} :")
                    else:
                        row_parts.append(txt)

                if row_parts:
                    if len(row_parts) >= 2 and row_parts[0].endswith(" :"):
                        lines.append(row_parts[0] + " " + " | ".join(row_parts[1:]))
                    else:
                        lines.append(" | ".join(row_parts))

            break

    return "\n".join(lines)

def _get_wcms_txt_content(title_el):
    section = title_el.find_parent("section", class_="section-container")
    if not section:
        return ""

    lines = []
    started = False

    for el in section.find_all(True):
        if el == title_el:
            started = True
            continue

        if not started:
            continue

        if _has_class(el, "wcms-tit"):
            break

        if _has_class(el, "wcms-txt"):
            txt = _get_text(el)
            if txt:
                lines.append(txt)

    return "\n".join(lines)

def _get_only_wcms_txt_content(soup):
    lines = []

    for p in soup.find_all("p", class_=lambda x: x and "wcms-txt" in x):
        txt = _get_text(p)
        if txt:
            lines.append(txt)

    return "\n".join(lines)

def _find_amounts(text):
    if not text:
        return []

    items = []

    for m in re.finditer(r"(\d[\d,]*)\s*(만원|원|%|포인트|마일리지)", text):
        raw = int(m.group(1).replace(",", ""))
        src_unit = m.group(2)

        items.append({
            "start": m.start(),
            "text": m.group(0),
            "unit": "원" if src_unit in ["만원", "원"] else src_unit,
            "value": raw * 10000 if src_unit == "만원" else raw,
        })

    return items

def _get_region(text):
    has_domestic = "국내" in text
    has_global = "해외" in text

    if has_domestic and has_global:
        return "둘다"

    if has_global:
        return "해외"

    return "국내"

def _get_benefit_type(text):
    items = [("할인", "할인"), ("포인트적립", "포인트적립"), ("포인트 적립", "포인트적립"), ("마일리지적립", "마일리지적립"), ("마일리지 적립", "마일리지적립"), ("캐시백", "캐시백"), ("서비스", "서비스")]

    found = []

    for keyword, value in items:
        idx = text.find(keyword)
        if idx >= 0:
            found.append((idx, value))

    if not found:
        return ""

    found.sort(key=lambda x: x[0])
    return found[0][1]

def _get_unit_value(text):
    amounts = _find_amounts(text)

    if not amounts:
        return "", ""

    return amounts[0]["unit"], amounts[0]["value"]

def _get_max_limit(text):
    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if ("월" in line and "할인" in line) or ("적립" in line):
            amounts = _find_amounts(line)
            if amounts:
                return amounts[-1]["value"]

    return ""

def _clean_benefit_summary_text(text):
    if not text:
        return ""

    text = text.strip()

    text = re.sub(r'^\s*[①-⑳]\s*', '', text)
    text = re.sub(r'^\s*[A-Z]\.\s*', '', text)
    text = re.sub(r'^\s*\d+\.\s*', '', text)
    text = re.sub(r'\b[A-Z]\.\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text

def _is_bad_summary_line(text):
    if not text:
        return True

    if "|" in text or ":" in text:
        return True

    if "전월" in text and "이용금액" in text:
        return True

    return False

def _get_benefit_summary(text):
    for line in text.splitlines():
        line = _clean_benefit_summary_text(line)

        if not line:
            continue

        if len(line) <= 60 and _find_amounts(line) and "할인" in line and not _is_bad_summary_line(line):
            return line[:120]

    text = _clean_benefit_summary_text(text)
    return text[:120]

def _get_category_info(text):
    target_merchants = []
    category_id = ""
    category = ""

    for item in category_data:
        matched = []

        for merchant in item.get("category_list", []):
            if merchant and merchant in text:
                matched.append(merchant)

        if matched:
            for merchant in matched:
                if merchant not in target_merchants:
                    target_merchants.append(merchant)

            if not category_id:
                category_id = item.get("category_id", "")
                category = item.get("category_name", "")

    return ",".join(target_merchants), category_id, category


# ── STEP 2: 혜택 [카드 서비스 상세] HTML 수집 ────────────────────────
async def get_benefit_rows(card_id: str, nuxt_data: dict, session: aiohttp.ClientSession) -> list[dict]:
    rows = []
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bubbles = (
        nuxt_data.get("wcms", {})
        .get("detail", {})
        .get("bubble", [])
    )

    for b in bubbles:
        svc_url = b.get("serviceUrl", "")
        if not svc_url:
            continue

        tab_name = b.get("tabName") or b.get("title") or ""
        serviceName = b.get("serviceName") or ""
        url = svc_url if svc_url.startswith("http") else CDN_BASE + svc_url

        async with session.get(url) as resp:
            benefit_html = await resp.text()

        soup = BeautifulSoup(benefit_html, "html.parser")

        found = False

        for selector in ['h5.tit04', 'h5.tit', 'p[class*="wcms-tit"]', 'dt']:
            for title_el in soup.select(selector):

                # region benefit_title [시작] ==========
                benefit_title = _get_text(title_el)

                if not benefit_title:
                    continue
                # endregion benefit_title [끝] ==========

                # region benefit_content [시작] ==========
                benefit_content = ""

                if selector == "dt":
                    benefit_content = _get_dt_dd_content(title_el)

                elif selector == 'p[class*="wcms-tit"]':
                    benefit_content = _get_wcms_txt_content(title_el)

                elif selector == "h5.tit04":
                    benefit_content = _get_next_ul_content(title_el, "txt_list")

                elif selector == "h5.tit":
                    benefit_content = _get_next_ul_content(title_el, "shopList")
                # endregion benefit_content [끝] ==========

                if selector == "h5.tit04" and "유의사항" in benefit_title:
                    found = True

                    rows.append({
                        "card_id": card_id,
                        "row_type": "유의사항",
                        "benefit_group": tab_name,
                        "benefit_main_title": serviceName,
                        "benefit_title": benefit_title,
                        "benefit_content": benefit_content,
                        "region": "",
                        "benefit_type": "",
                        "unit": "",
                        "value": "",
                        "max_limit": "",
                        "benefit_summary": benefit_content[:120],
                        "target_merchants": "",
                        "category_id": "",
                        "category": "",
                        "on_offline": "",
                        "excluded_merchants": "",
                        "performance_level": "",
                        "updated_at": updated_at
                    })
                    continue

                region = _get_region(benefit_content)
                benefit_type = _get_benefit_type(benefit_content)
                unit, value = _get_unit_value(benefit_content)
                max_limit = _get_max_limit(benefit_content)
                benefit_summary = _get_benefit_summary(benefit_content)
                target_merchants, category_id, category = _get_category_info(benefit_content)

                found = True

                rows.append({
                    "card_id": card_id,
                    "row_type": "혜택",
                    "benefit_group": tab_name,
                    "benefit_main_title": serviceName,
                    "benefit_title": benefit_title,
                    "benefit_content": benefit_content,
                    "region": region,
                    "benefit_type": benefit_type,
                    "unit": unit,
                    "value": value,
                    "max_limit": max_limit,
                    "benefit_summary": benefit_summary,
                    "target_merchants": target_merchants,
                    "category_id": category_id,
                    "category": category,
                    "on_offline": "",
                    "excluded_merchants": "",
                    "performance_level": "",
                    "updated_at": updated_at
                })

        if not found and serviceName:
            benefit_content = _get_only_wcms_txt_content(soup)

            region = _get_region(benefit_content)
            benefit_type = _get_benefit_type(benefit_content)
            unit, value = _get_unit_value(benefit_content)
            max_limit = _get_max_limit(benefit_content)
            benefit_summary = _get_benefit_summary(benefit_content)
            target_merchants, category_id, category = _get_category_info(benefit_content)

            rows.append({
                "card_id": card_id,
                "row_type": "혜택",
                "benefit_group": tab_name,
                "benefit_main_title": serviceName,
                "benefit_title": serviceName,
                "benefit_content": benefit_content,
                "region": region,
                "benefit_type": benefit_type,
                "unit": unit,
                "value": value,
                "max_limit": max_limit,
                "benefit_summary": benefit_summary,
                "target_merchants": target_merchants,
                "category_id": category_id,
                "category": category,
                "on_offline": "",
                "excluded_merchants": "",
                "performance_level": "",
                "updated_at": updated_at
            })

    for row in rows:
        log(str(row))

    return rows


# ── STEP 3: 연회비 HTML 수집 ────────────────────────
def _fee_clean(text):
    text = BeautifulSoup(str(text or ""), "html.parser").get_text(" ", strip=True)
    text = text.replace("총연회비", "총 연회비").replace("기본연회비", "기본 연회비").replace("제휴연회비", "제휴 연회비")
    text = text.replace("( ", "(").replace(" )", ")")
    text = re.sub(r"(\d[\d,]*)\s+(원)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _fee_expand(trs):
    rows = []
    spans = {}

    for tr in trs:
        row = []
        col = 0

        for cell in tr.find_all(["th", "td"], recursive=False):
            while col in spans:
                row.append(spans[col]["text"])
                spans[col]["left"] -= 1
                if spans[col]["left"] == 0:
                    del spans[col]
                col += 1

            text = _fee_clean(cell)
            rowspan = int(cell.get("rowspan", 1) or 1)
            colspan = int(cell.get("colspan", 1) or 1)

            for i in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[col + i] = {"text": text, "left": rowspan - 1}

            col += colspan

        while col in spans:
            row.append(spans[col]["text"])
            spans[col]["left"] -= 1
            if spans[col]["left"] == 0:
                del spans[col]
            col += 1

        rows.append(row)

    return rows


def _make_fee_row(card_id, title, content, updated_at):
    unit, value = _get_unit_value(content)

    return {
        "card_id": card_id,
        "row_type": "연회비",
        "benefit_group": "연회비",
        "benefit_main_title": title,
        "benefit_title": title,
        "benefit_content": content,
        "region": "해외" if "해외" in content else "국내",
        "benefit_type": "",
        "unit": unit,
        "value": value,
        "max_limit": "",
        "benefit_summary": content[:120],
        "target_merchants": "",
        "category_id": "",
        "category": "",
        "on_offline": "",
        "excluded_merchants": "",
        "performance_level": "",
        "updated_at": updated_at,
    }


async def get_fee_rows(card_id: str, nuxt_data: dict, session: aiohttp.ClientSession) -> list[dict]:
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    fee_url = (
        nuxt_data.get("wcms", {})
        .get("detail", {})
        .get("htmlList", {})
        .get("feeUrl", "")
    )

    if not fee_url:
        return rows

    url = fee_url if fee_url.startswith("http") else CDN_BASE + fee_url

    async with session.get(url) as resp:
        fee_html = await resp.text()

    soup = BeautifulSoup(fee_html, "html.parser")

    for indv in soup.select("article.terms > div.indv"):
        title = _fee_clean(indv.select_one("h4.t_web_em"))
        if not title:
            continue

        table = indv.find("table")

        if table:
            head_rows = _fee_expand(table.select("thead tr"))
            headers = []

            max_cols = max((len(r) for r in head_rows), default=0)
            for i in range(1, max_cols):
                parts = []
                for r in head_rows:
                    txt = r[i] if i < len(r) else ""
                    if txt and txt != "구분" and txt not in parts:
                        parts.append(txt)
                headers.append(" ".join(parts).strip())

            for r in _fee_expand(table.select("tbody tr")):
                fee_type = _fee_clean(r[0] if len(r) > 0 else "")
                if not fee_type:
                    continue

                for i, header in enumerate(headers, start=1):
                    if not header:
                        continue

                    amount = _fee_clean(r[i] if i < len(r) else "") or "없음"
                    rows.append(_make_fee_row(card_id, title, f"{header} {fee_type} {amount}", updated_at))

        notes = []
        for el in indv.select(".btm_info .alert_s_new, .btm_info li"):
            txt = _fee_clean(el)
            if txt and txt not in notes:
                notes.append(txt)

        for txt in notes:
            rows.append(_make_fee_row(card_id, title, txt, updated_at))

    # === 연회비 유의사항 추가 ===
    notice_lines = []

    for box in soup.select(".b_note .list_box_nt"):
        h4 = box.select_one("h4.tit04")
        if not h4 or "유의사항" not in _get_text(h4):
            continue

        for li in box.select("ul.txt_list > li"):
            txt = _get_text(li)
            if txt:
                notice_lines.append(txt)
        break

    if notice_lines:
        notice_content = "\n".join(notice_lines)

        rows.append({
            "card_id": card_id,
            "row_type": "유의사항",
            "benefit_group": "연회비",
            "benefit_main_title": "연회비 유의사항",
            "benefit_title": "연회비 유의사항",
            "benefit_content": notice_content,
            "region": "국내",
            "benefit_type": "",
            "unit": "",
            "value": "",
            "max_limit": "",
            "benefit_summary": notice_content[:120],
            "target_merchants": "",
            "category_id": "",
            "category": "",
            "on_offline": "",
            "excluded_merchants": "",
            "performance_level": "",
            "updated_at": updated_at
        })

    for row in rows:
        log(str(row))

    return rows

def save_rows_to_csv(rows, filename="card_benefit.csv"):
    if not rows:
        return

    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())

        if not file_exists:
            writer.writeheader()

        writer.writerows(rows)

def _format_event_date(value: str) -> str:
    if not value:
        return ""

    value = value.split("-")[0]

    if len(value) == 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    return value

async def get_event_rows(card_id: str, nuxt_data: dict, session: aiohttp.ClientSession) -> list[dict]:
    rows = []

    banner_list = (
        nuxt_data.get("wcms", {})
        .get("detail", {})
        .get("bannerList", [])
    )

    for banner in banner_list:
        evt_url = banner.get("evtUrl", "")
        if not evt_url:
            continue

        event_url = evt_url if evt_url.startswith("http") else CDN_BASE + evt_url

        async with session.get(event_url) as resp:
            event_html = await resp.text()

        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows.append({
            "card_id": card_id,
            "card_company": "삼성카드",
            "card_name": "",
            "source_event_id": banner.get("id", ""),
            "event_title": banner.get("evtTitle", ""),
            "event_url": event_url,
            "event_start_date": _format_event_date(banner.get("sDate", "")),
            "event_end_date": _format_event_date(banner.get("eDate", "")),
            "benefit_type": "",
            "section": "",
            "content": event_html,
            "crawled_at": crawled_at,
        })

    for row in rows:
        log(str(row))

    return rows


# ── 메인 처리 ─────────────────────────────────────────────────
async def crawl_one(card_code: str, session: aiohttp.ClientSession):
    result = await get_nuxt_data(card_code)
    #
    # benefit_rows = await get_benefit_rows(
    #     card_id=card_code,
    #     nuxt_data=result["nuxt_data"],
    #     session=session
    # )
    #
    # fee_rows = await get_fee_rows(
    #     card_id=card_code,
    #     nuxt_data=result["nuxt_data"],
    #     session=session
    # )
    #
    # all_rows = benefit_rows + fee_rows
    # save_rows_to_csv(all_rows, "card_benefit.csv")
    #
    # result["benefit_rows"] = benefit_rows
    # result["fee_rows"] = fee_rows
    #
    # log(f"{card_code} 추출 성공")
    # log(f"출시일: {result['sell_start_dt']}")
    # log(f"혜택 건수: {len(benefit_rows)}")
    # log(f"연회비 건수: {len(fee_rows)}")

    # 이벤트
    event_rows = await get_event_rows(
        card_id=card_code,
        nuxt_data=result["nuxt_data"],
        session=session,
    )

    result["event_rows"] = event_rows
    log(f"이벤트 건수: {len(event_rows)}")

    return result


async def main():
    log(f"삼성카드 크롤링 시작 - 총 {len(CARD_LIST)}개 카드")
    line()

    results = []

    async with aiohttp.ClientSession(headers={
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }) as session:
        for idx, card_code in enumerate(CARD_LIST, 1):
            log(f"[{idx}/{len(CARD_LIST)}] {card_code} 크롤링 중...")
            try:
                result = await crawl_one(card_code, session)
                results.append(result)
            except Exception as e:
                log(f"[ERR] {card_code} 오류: {e}")

    line()
    log(f"전체 크롤링 완료 - 성공 {len(results)} / 전체 {len(CARD_LIST)}")
    line()


if __name__ == "__main__":
    asyncio.run(main())