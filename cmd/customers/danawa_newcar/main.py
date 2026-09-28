"""다나와 자동차 간단 수집기

먼저 아래 설정만 바꾸고 실행합니다.
    pip install selenium beautifulsoup4
    python danawa_simple.py

requests를 사용하지 않고 Chrome 안에서 POST를 실행하므로
Python requests의 SSL handshake 오류를 피할 수 있습니다.
"""

import csv
import re
import time
from itertools import product
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# -------------------- 실행 설정 --------------------
OUTPUT = "danawa_master.csv"
TARGET_MODEL_ID = ""  # 특정 모델만: "4563" / 전체: ""
START_PAGE = 1
MAX_PAGES = 0  # 0이면 마지막 페이지까지
MAX_TRIMS = 0  # 테스트: 1 / 전체: 0
HEADLESS = False

BASE = "https://auto.danawa.com"
SEARCH = BASE + "/newcar/searchAjax.php"
MODEL = BASE + "/auto/?Work=model&Model={}&attributeList="
ESTIMATE = BASE + "/newcar/?Work=estimate&Model={}&Trims={}"

COLUMNS = [
    "country_type", "brand_id", "brand_name", "model_id", "model_name",
    "model_year", "lineup_id", "lineup_name", "trim_id", "trim_name",
    "trim_price", "option_id", "option_name", "option_price",
    "exterior_color_id", "exterior_color_name", "exterior_color_code",
    "exterior_color_price", "interior_color_id", "interior_color_name",
    "interior_color_code", "interior_color_price", "image_url", "source_url",
]

# ---------------------------------------------------------------------------
# HTML → CSV 컬럼 연결표
#
# [모델 목록 searchAjax.php 응답]
#   model_id      ← a[name="modelDetailLink"][model] 의 model="4563"
#   model_name    ← 같은 링크의 화면 문자열(브랜드명 제거)
#   brand_id      ← a[name="newcarSales"][brand] 의 brand="307"
#                   (없으면 견적 링크의 Brand= 쿼리값)
#   brand_name    ← 모델 링크 안 img 의 alt="기아"
#   country_type  ← brand_name을 국산 브랜드 목록과 비교해 국산/수입으로 계산
#   image_url     ← 모델 목록 li 안 img[src]
#   source_url    ← https://auto.danawa.com/auto/?Work=model&Model={model_id}...
#
# [모델 상세 Work=model HTML]
#   image_url     ← meta[property="og:image"] 의 content
#   lineup_id     ← .price_contents dt 안 button[data-lineup] 의 data-lineup
#   lineup_name   ← 같은 dt 안 strong의 텍스트
#   model_year    ← lineup_name 안 "2027년형" 정규식
#   trim_id       ← input[id^="trimsAll_"] 의 value="trims_98922"
#                   (value가 없으면 id="trimsAll_98922")
#   trim_name     ← 해당 input의 trimnamet 또는 연결 label의 텍스트
#   trim_price    ← 같은 li 안 .item.price의 텍스트
#   source_url    ← https://auto.danawa.com/newcar/?Work=estimate&Model=...&Trims=...
#
# [트림별 견적 Work=estimate HTML]
#   option_id     ← #popupItem_* 요소의 code 또는 data-optioncode
#   option_name   ← input과 연결된 label 텍스트 / data-optionname
#   option_price  ← 옵션 요소의 price 계열 속성 또는 가까운 부모의 가격 텍스트
#   exterior_*    ← [color] 또는 [data-colorcode] 요소의 color/data-colorcode,
#                   이름(화면 텍스트), data-colorvalue/data-paintcode 또는 괄호 안 코드
#   exterior_color_price
#                 ← "외장컬러" 옵션 항목의 가격을 외장색상 이름으로 연결
#   interior_*    ← 견적 HTML의 내장색상 항목에서 ID와 이름만 연결
#   interior_color_code / interior_color_price
#                 ← 다나와 응답에 별도 값이 없어 항상 공란으로 출력
#   (같은 트림에서 옵션 × 외장색상 × 내장색상 조합으로 여러 CSV 행 생성)
# ---------------------------------------------------------------------------


def text(tag):
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip() if tag else ""


def price(value):
    value = str(value or "").replace(",", "").replace(" ", "")
    eok = re.search(r"(\d+(?:\.\d+)?)억", value)
    man = re.search(r"(\d+(?:\.\d+)?)만", value)
    if eok:
        return int(float(eok.group(1)) * 100_000_000) + (int(float(man.group(1)) * 10_000) if man else 0)
    if man:
        return int(float(man.group(1)) * 10_000)
    won = re.search(r"(\d[\d]*)원", value)
    return int(won.group(1)) if won else ""


def near_price(tag):
    for key in ("price", "data-price", "optionprice", "colorprice"):
        if tag and tag.get(key):
            return price(tag.get(key))
    parent = tag.parent if tag else None
    for _ in range(3):
        if not parent:
            break
        found = re.findall(r"\d[\d,]*\s*(?:억\s*\d[\d,]*\s*만|만\s*원|원)", text(parent))
        if found:
            return price(found[-1])
        parent = parent.parent
    return ""


def plain_color_name(value):
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", str(value or "").replace("외장컬러", "").replace("내장컬러", "")).strip())


def get_color_price(tag):
    for key in ("price", "data-price", "colorprice", "data-colorprice"):
        if tag and tag.get(key):
            return price(tag.get(key))
    # 색상 버튼 바로 바깥의 가격만 확인합니다. 페이지 전체의 다른 옵션 가격을
    # 색상 가격으로 잘못 가져오지 않도록 부모를 깊게 탐색하지 않습니다.
    parent = tag.parent if tag else None
    found = re.findall(r"\d[\d,]*\s*(?:억\s*\d[\d,]*\s*만|만\s*원|원)", text(parent)) if parent else []
    return price(found[-1]) if found else ""


def browser_post(driver, page):
    referer = (
        f"{BASE}/newcar/?listSortType=1&tab=all&rangeMinPrice=&rangeMaxPrice="
        f"&searchKeyword=&listCount=30&page={page}&brandList=&segmentList=&attributeList="
    )
    payload = urlencode({
        "listSortType": "1", "tab": "all", "rangeMinPrice": "", "rangeMaxPrice": "",
        "searchKeyword": "", "listCount": "30", "page": str(page),
        "brandList": "", "segmentList": "", "attributeList": "",
    })
    driver.get(referer)
    script = """
    const done = arguments[arguments.length - 1];
    fetch(arguments[0], {
        method: 'POST', credentials: 'include', cache: 'no-store',
        headers: {
            'Accept': 'text/html, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest'
        }, body: arguments[1]
    }).then(async r => done({status:r.status, text:await r.text()}))
      .catch(e => done({error:String(e)}));
    """
    result = driver.execute_async_script(script, SEARCH, payload)
    if result.get("error") or result.get("status") != 200:
        raise RuntimeError(result.get("error") or f"HTTP {result.get('status')}")
    return result["text"]


def parse_models(html):
    # searchAjax.php의 모델 목록 <li> 하나를 읽어 모델 단위 기본값을 만듭니다.
    soup = BeautifulSoup(html, "html.parser")
    models, seen = [], set()
    # model_id ← <a name="modelDetailLink" model="..."></a>
    for link in soup.select('a[name="modelDetailLink"][model]'):
        model_id = link.get("model")
        if not model_id or model_id in seen:
            continue
        li = link.find_parent("li")
        name_link = li.select_one('a[name="modelDetailLink"].name') or link
        # brand_name ← 모델명 링크 내부 <img alt="기아">
        brand_img = name_link.find("img")
        brand_name = brand_img.get("alt", "") if brand_img else ""
        full_name = text(name_link)
        model_name = full_name[len(brand_name):].strip() if full_name.startswith(brand_name) else full_name
        # brand_id ← <a name="newcarSales" brand="307">
        sales = li.select_one('a[name="newcarSales"][brand]')
        brand_id = sales.get("brand", "") if sales else ""
        if not brand_id:
            estimate = li.select_one('a.btn_estm[href*="Brand="]')
            query = parse_qs(urlparse(estimate.get("href", "") if estimate else "").query)
            brand_id = query.get("Brand", [""])[0]
        # image_url ← 모델 목록 <li> 내부의 첫 번째 <img src="...">
        img = li.select_one("img[src]")
        models.append({
            "country_type": "국산" if brand_name in {"현대", "기아", "제네시스", "르노코리아", "쉐보레", "KGM", "KG모빌리티", "쌍용"} else "수입",
            "brand_id": brand_id, "brand_name": brand_name, "model_id": model_id,
            "model_name": model_name, "image_url": img.get("src", "") if img else "",
            "source_url": MODEL.format(model_id),
        })
        seen.add(model_id)
    return models


def parse_total_pages(html):
    # 전체 페이지 수 ← <span class="box__total-page"><span class="text__number">...</span>
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.select_one(".box__total-page .text__number")
    match = re.search(r"\d+", text(tag)) if tag else None
    return int(match.group()) if match else None


def parse_trims(html, model_id):
    # Work=model 상세 페이지에서 라인업/트림 계층을 읽습니다.
    soup = BeautifulSoup(html, "html.parser")
    # image_url ← <meta property="og:image" content="...">
    image = soup.select_one('meta[property="og:image"]')
    trims, seen = [], set()
    # 라인업 ID ← dt 내부 <button data-lineup="54792">
    for dt in soup.select(".price_contents dt.price_title"):
        button = dt.select_one("button[data-lineup]")
        if not button:
            continue
        lineup_id = button.get("data-lineup")
        # lineup_name ← 같은 dt 내부 <strong>2027년형 ...</strong>
        lineup_name = text(dt.select_one("strong"))
        year = re.search(r"(20\d{2})년형", lineup_name)
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        for li in dd.select("li"):
            # trim_id ← <input id="trimsAll_98922" value="trims_98922">
            inp = li.select_one('input[id^="trimsAll_"]')
            if not inp:
                continue
            trim_id = inp.get("value", "").replace("trims_", "") or inp.get("id", "").replace("trimsAll_", "")
            if trim_id in seen:
                continue
            label = li.select_one("label")
            # trim_name ← input[trimnamet] 또는 input과 연결된 <label> 텍스트
            trim_name = inp.get("trimnamet", "") or text(label)
            # trim_price ← 트림 li 내부 <span class="item price">...</span>
            p = li.select_one(".item.price")
            trims.append({
                "model_year": year.group(1) if year else "",
                "lineup_id": lineup_id, "lineup_name": lineup_name,
                "trim_id": trim_id, "trim_name": trim_name,
                "trim_price": price(text(p)),
                "source_url": ESTIMATE.format(model_id, trim_id),
            })
            seen.add(trim_id)
    return image.get("content", "") if image else "", trims


def parse_estimate(html):
    # Work=estimate 페이지에서 옵션과 색상을 읽습니다.
    soup = BeautifulSoup(html, "html.parser")
    options = []
    color_prices = {}
    # 옵션 ID/명/가격
    #   option_id    ← #popupItem_*[code] 또는 [data-optioncode]
    #   option_name  ← 연결 label 또는 data-optionname
    #   option_price ← 요소의 price 계열 속성/가까운 부모 가격 텍스트
    for tag in soup.select('[id^="popupItem_"], [data-optioncode]'):
        option_id = tag.get("code") or tag.get("data-optioncode", "")
        if not option_id or re.fullmatch(r"C\d+", option_id, re.I):
            continue
        label = soup.find("label", attrs={"for": tag.get("id")}) if tag.get("id") else None
        name = text(label) or tag.get("data-optionname", "") or text(tag)
        if "외장컬러" in name or "내장컬러" in name:
            color_prices[plain_color_name(name)] = near_price(tag)
            continue
        # 외장/내장 색상이 견적 옵션 목록에도 한 번 노출되는 경우는
        # 옵션으로 중복 저장하지 않습니다.
        if name:
            options.append({"id": option_id, "name": name, "price": near_price(tag)})

    colors = []
    # 색상 ID/명/코드
    #   color_id   ← [color="C10"] 또는 [data-colorcode="C10"]
    #   color_name ← 내부 .screen_out/.blind 텍스트, title 또는 요소 텍스트
    #   color_code ← data-colorvalue/data-paintcode 또는 이름의 괄호 안 값
    for tag in soup.select("[color], [data-colorcode]"):
        color_id = tag.get("color") or tag.get("data-colorcode", "")
        if not re.fullmatch(r"C\d+", color_id, re.I):
            continue
        name = text(tag.select_one(".screen_out, .blind")) or tag.get("title", "") or text(tag)
        code_match = re.search(r"\(([^()]+)\)", name)
        parent_text = text(tag.parent.parent if tag.parent else tag)
        # 외장색상에는 보통 (SWP), (CGE) 같은 도장 코드가 있고,
        # 내장색상은 코드 없이 이름만 표시되는 구조입니다.
        kind = "interior" if "내장" in parent_text or not code_match else "exterior"
        code = tag.get("data-colorvalue") or tag.get("data-paintcode") or (code_match.group(1) if code_match else "")
        color_price_value = color_prices.get(plain_color_name(name), get_color_price(tag))
        # 내장색상 코드/가격은 현재 다나와 응답에서 제공되지 않으므로
        # CSV에는 의도적으로 공란을 저장합니다. (0으로 추정하지 않음)
        if kind == "interior":
            code, color_price_value = "", ""
        colors.append({"id": color_id, "name": name, "code": code, "price": color_price_value, "kind": kind})

    # 동일한 DOM 요소가 중복으로 잡히는 경우 제거
    options = list({(x["id"], x["name"], x["price"]): x for x in options}.values())
    colors = list({(x["id"], x["name"], x["kind"]): x for x in colors}.values())
    return options, [x for x in colors if x["kind"] == "exterior"], [x for x in colors if x["kind"] == "interior"]


def main():
    chrome = Options()
    if HEADLESS:
        chrome.add_argument("--headless=new")
    chrome.add_argument("--window-size=1440,1000")
    driver = webdriver.Chrome(options=chrome)
    try:
        driver.get(BASE)
        models, seen_models, page = [], set(), START_PAGE
        total_pages = None
        while True:
            print(f"모델 목록 page={page}")
            search_html = browser_post(driver, page)
            if total_pages is None:
                total_pages = parse_total_pages(search_html)
                print(f"전체 페이지: {total_pages or '확인 불가'}")
            found = parse_models(search_html)
            if not found:
                break
            for model in found:
                if model["model_id"] not in seen_models:
                    models.append(model)
                    seen_models.add(model["model_id"])
            if TARGET_MODEL_ID and any(x["model_id"] == TARGET_MODEL_ID for x in found):
                models = [x for x in models if x["model_id"] == TARGET_MODEL_ID]
                break
            if total_pages and page >= total_pages:
                break
            if MAX_PAGES and page >= START_PAGE + MAX_PAGES - 1:
                break
            page += 1

        with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNS)
            writer.writeheader()
            for model in models:
                driver.get(model["source_url"])
                image, trims = parse_trims(driver.page_source, model["model_id"])
                model["image_url"] = image or model["image_url"]
                if MAX_TRIMS:
                    trims = trims[:MAX_TRIMS]
                for trim in trims:
                    driver.get(trim["source_url"])
                    time.sleep(1)
                    options, exterior, interior = parse_estimate(driver.page_source)
                    for option, ext, inside in product(options or [{}], exterior or [{}], interior or [{}]):
                        # 아래 한 행은 [옵션 1개] × [외장색상 1개] × [내장색상 1개]입니다.
                        # 즉, 같은 트림이라도 선택 가능한 옵션/색상 조합 수만큼 행이 생성됩니다.
                        # 각 값은 위 parse_models(), parse_trims(), parse_estimate()의
                        # HTML 매핑 주석을 따라 CSV 컬럼으로 들어갑니다.
                        writer.writerow({
                            # 모델 목록/상세 HTML 매핑
                            # country_type, brand_id, brand_name, model_id, model_name,
                            # image_url ← parse_models()의 모델 목록 태그
                            # source_url ← 아래 trim의 견적 URL이 model의 모델 URL을 덮어씀
                            **model,
                            # 모델 상세 HTML 매핑
                            # model_year, lineup_id, lineup_name, trim_id, trim_name, trim_price
                            **trim,
                            # 견적 HTML 옵션 매핑
                            "option_id": option.get("id", ""), "option_name": option.get("name", ""), "option_price": option.get("price", ""),
                            # 견적 HTML 외장색상 매핑
                            "exterior_color_id": ext.get("id", ""), "exterior_color_name": ext.get("name", ""), "exterior_color_code": ext.get("code", ""), "exterior_color_price": ext.get("price", ""),
                            # 견적 HTML 내장색상 매핑
                            # interior_color_code / interior_color_price는 원본 값이 없어 공란 유지
                            "interior_color_id": inside.get("id", ""), "interior_color_name": inside.get("name", ""), "interior_color_code": "", "interior_color_price": "",
                        })
                    file.flush()
        print(f"완료: {OUTPUT}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
