# main.py
# -*- coding: utf-8 -*-

import json
import random
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selenium.webdriver.common.keys import Keys

from src.utils.selenium_utils import SeleniumUtils


URL: str = "https://fin.land.naver.com/"
LIST_API_URL: str = "https://fin.land.naver.com/front-api/v1/article/boundedArticles"
DETAIL_API_URL: str = "https://fin.land.naver.com/front-api/v1/article/basicInfo"

# =========================
# 테스트용 전역값
# =========================
TEST_KEYWORDS: list[str] = [
    "망포동",
]

# 필터 안 보낼 거면 None 또는 {}
TEST_FILTERS: dict[str, Any] | None = {}


TRADE_TYPE_MAP: dict[str, str] = {
    "매매": "A1",
    "전세": "B1",
    "월세": "B2",
    "단기임대": "B3",
}

REAL_ESTATE_TYPE_MAP: dict[str, str] = {
    "아파트": "A01",
    "재건축": "A04",
    "오피스텔": "C01",
    "빌라": "B01",
    "아파트 분양권": "A05",
    "오피스텔 분양권": "C02",
    "원룸": "C03",
    "단독/다가구": "B02",
    "전원주택": "D04",
    "상가주택": "B02",
    "재개발": "A06",
    "상가": "D01",
    "토지": "E01",
    "사무실": "D02",
    "건물": "E04",
    "공장/창고": "E02",
    "지식산업센터": "D03",
}

ROOM_COUNT_MAP: dict[str, str] = {
    "1개": "RCF01",
    "2개": "RCF02",
    "3개": "RCF03",
    "4개 이상": "RCF04",
}

BATHROOM_COUNT_MAP: dict[str, str] = {
    "1개": "RCF01",
    "2개": "RCF02",
    "3개": "RCF03",
    "4개 이상": "RCF04",
}

FLOOR_TYPE_MAP: dict[str, str] = {
    "1층": "FLF01",
    "저층": "FLF02",
    "중층": "FLF03",
    "고층": "FLF04",
    "탑층": "FLF05",
}

DIRECTION_MAP: dict[str, str] = {
    "동향": "EE",
    "서향": "WW",
    "남향": "SS",
    "북향": "NN",
    "북동향": "EN",
    "남동향": "ES",
    "북서향": "WN",
    "남서향": "WS",
}

PARKING_TYPE_MAP: dict[str, str] = {
    "세대당 주차1대 이상": "PKF01",
    "세대당 주차 1.5대 이상": "PKF02",
    "전기차충전소": "PKF03",
}

ENTRANCE_TYPE_MAP: dict[str, str] = {
    "계단식": "10",
    "복도식": "20",
    "복합식": "30",
}

LOAN_RATIO_TYPE_MAP: dict[str, str] = {
    "융자금 없음": "00",
    "융자금 30% 이하": "10",
}

MOVE_IN_TYPE_MAP: dict[str, str] = {
    "바로입주": "MVF01",
    "90일 내 입주": "MVF02",
}

ONE_ROOM_SHAPE_MAP: dict[str, str] = {
    "오픈형": "10",
    "분리형": "20",
}

OPTION_TYPE_MAP: dict[str, str] = {
    "테라스": "OPF06",
    "마당": "OPF08",
    "풀옵션": "OPF04",
    "에어컨": "OPF05",
    "복층": "OPF09",
    "베란다": "OPF07",
    "보안시설": "OPF03",
    "엘리베이터": "OPF01",
    "주차 가능": "OPF02",
}


def sleep_rand(a: float, b: float) -> None:
    time.sleep(random.uniform(a, b))


def slug(text: str) -> str:
    return re.sub(r"[^\w가-힣]+", "_", text).strip("_")


def q(driver: Any, selector: str, wait_sec: int = 20) -> Any:
    end: float = time.time() + wait_sec
    while time.time() < end:
        el: Any = driver.execute_script("return document.querySelector(arguments[0]);", selector)
        if el:
            return el
        time.sleep(1)
    return None


def qq(driver: Any, selector: str, wait_sec: int = 20) -> list[Any]:
    end: float = time.time() + wait_sec
    while time.time() < end:
        els: list[Any] = driver.execute_script(
            "return Array.from(document.querySelectorAll(arguments[0]));",
            selector,
        )
        if els:
            return els
        time.sleep(1)
    return []


def set_input(driver: Any, el: Any, value: str) -> None:
    driver.execute_script(
        """
        arguments[0].focus();
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
        """,
        el,
        value,
    )


def zoom_out(driver: Any, count: int = 2) -> None:
    for i in range(count):
        print(f"[지도 축소] {i + 1}/{count}")
        buttons: list[Any] = qq(driver, "button.MapZoomControls_button-control__fgFdq")
        if len(buttons) < 2:
            break
        driver.execute_script("arguments[0].click();", buttons[1])
        sleep_rand(1.2, 1.8)


def click_article_button(driver: Any, wait_sec: int = 20) -> None:
    end: float = time.time() + wait_sec
    while time.time() < end:
        buttons: list[Any] = driver.execute_script(
            "return Array.from(document.querySelectorAll('button.BottomInfoControls_link-item___xLdX'));"
        )
        if buttons:
            print(f"[매물 버튼] 발견 개수={len(buttons)}")
            driver.execute_script("arguments[0].click();", buttons[0])
            return
        time.sleep(1)


def inject_list_hook(driver: Any) -> None:
    driver.execute_script(
        """
        window.__naverListHookData = null;
        if (window.__naverListHookInstalled) return;
        window.__naverListHookInstalled = true;

        const target = '/front-api/v1/article/boundedArticles';

        const saveData = async (url, bodyText, response) => {
            try {
                const cloned = response.clone();
                const jsonData = await cloned.json();
                if (!window.__naverListHookData) {
                    window.__naverListHookData = {
                        url: url,
                        bodyText: bodyText || '',
                        responseJson: jsonData
                    };
                }
            } catch (e) {}
        };

        const oldFetch = window.fetch;
        window.fetch = async function(...args) {
            const res = await oldFetch.apply(this, args);
            try {
                const req = args[0];
                const url = typeof req === 'string' ? req : req.url;
                const opts = args[1] || {};
                const bodyText = opts && opts.body ? opts.body : '';
                if (url && url.includes(target)) saveData(url, bodyText, res);
            } catch (e) {}
            return res;
        };

        const oldOpen = XMLHttpRequest.prototype.open;
        const oldSend = XMLHttpRequest.prototype.send;

        XMLHttpRequest.prototype.open = function(method, url) {
            this.__hookUrl = url;
            return oldOpen.apply(this, arguments);
        };

        XMLHttpRequest.prototype.send = function(body) {
            this.addEventListener('load', function() {
                try {
                    if (this.__hookUrl && this.__hookUrl.includes(target) && !window.__naverListHookData) {
                        window.__naverListHookData = {
                            url: this.__hookUrl,
                            bodyText: body || '',
                            responseJson: JSON.parse(this.responseText)
                        };
                    }
                } catch (e) {}
            });
            return oldSend.apply(this, arguments);
        };
        """
    )


def get_first_list_hook_data(driver: Any, wait_sec: int = 20) -> dict[str, Any]:
    end: float = time.time() + wait_sec
    while time.time() < end:
        data: Any = driver.execute_script("return window.__naverListHookData;")
        if data:
            return data
        time.sleep(1)
    return {}


def join_codes(values: list[str]) -> str:
    return "-".join([v for v in values if v])


def minmax_text(value: tuple[int | float, int | float] | None) -> str | None:
    if not value:
        return None
    return f"{value[0]}-{value[1]}"


def map_codes(names: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping[x] for x in names if x in mapping]


def parse_range_value(text: str) -> dict[str, int | float]:
    a, b = text.split("-", 1)
    x: float = float(a)
    y: float = float(b)
    if x.is_integer() and y.is_integer():
        return {"min": int(x), "max": int(y)}
    return {"min": x, "max": y}


def build_filter_query(filters: dict[str, Any] | None) -> dict[str, str]:
    if not filters:
        return {}

    params: dict[str, str] = {}

    trade_codes: list[str] = map_codes(filters.get("trade_types", []), TRADE_TYPE_MAP)
    if trade_codes:
        params["tradeTypes"] = join_codes(trade_codes)

    real_estate_codes: list[str] = map_codes(filters.get("real_estate_types", []), REAL_ESTATE_TYPE_MAP)
    if real_estate_codes:
        params["realEstateTypes"] = join_codes(real_estate_codes)

    if filters.get("deal_price"):
        params["dealPrice"] = minmax_text(filters["deal_price"]) or ""
    if filters.get("warranty_price"):
        params["warrantyPrice"] = minmax_text(filters["warranty_price"]) or ""
    if filters.get("rent_price"):
        params["rentPrice"] = minmax_text(filters["rent_price"]) or ""

    if filters.get("space"):
        params["space"] = minmax_text(filters["space"]) or ""
    if filters.get("exclusive_space_mode"):
        params["exclusiveSpaceMode"] = "true"

    if filters.get("household_number"):
        params["householdNumber"] = minmax_text(filters["household_number"]) or ""

    parking_codes: list[str] = map_codes(filters.get("parking_types", []), PARKING_TYPE_MAP)
    if parking_codes:
        params["parkingTypes"] = join_codes(parking_codes)

    entrance_codes: list[str] = map_codes(filters.get("entrance_types", []), ENTRANCE_TYPE_MAP)
    if entrance_codes:
        params["entranceTypes"] = join_codes(entrance_codes)

    if filters.get("has_article_complex"):
        params["hasArticleComplex"] = "true"

    if filters.get("subway_walking_minute") is not None:
        params["subwayWalkingMinute"] = str(filters["subway_walking_minute"])

    if filters.get("has_article_photo"):
        params["hasArticlePhoto"] = "true"
    if filters.get("is_authorized_by_owner"):
        params["isAuthorizedByOwner"] = "true"

    room_codes: list[str] = map_codes(filters.get("room_counts", []), ROOM_COUNT_MAP)
    if room_codes:
        params["roomCount"] = join_codes(room_codes)

    bath_codes: list[str] = map_codes(filters.get("bathroom_counts", []), BATHROOM_COUNT_MAP)
    if bath_codes:
        params["bathRoomCount"] = join_codes(bath_codes)

    floor_codes: list[str] = map_codes(filters.get("floor_types", []), FLOOR_TYPE_MAP)
    if floor_codes:
        params["floor"] = join_codes(floor_codes)

    direction_codes: list[str] = map_codes(filters.get("direction_types", []), DIRECTION_MAP)
    if direction_codes:
        params["direction"] = join_codes(direction_codes)

    if filters.get("approval_elapsed_year"):
        params["approvalElapsedYear"] = minmax_text(filters["approval_elapsed_year"]) or ""
    if filters.get("management_fee"):
        params["managementFee"] = minmax_text(filters["management_fee"]) or ""

    loan_ratio_type: str | None = LOAN_RATIO_TYPE_MAP.get(filters.get("loan_ratio_type", ""))
    if loan_ratio_type:
        params["loanRatioType"] = loan_ratio_type

    move_in_codes: list[str] = map_codes(filters.get("move_in_types", []), MOVE_IN_TYPE_MAP)
    if move_in_codes:
        params["moveInTypes"] = join_codes(move_in_codes)

    option_codes: list[str] = map_codes(filters.get("option_types", []), OPTION_TYPE_MAP)
    if option_codes:
        params["facilities"] = join_codes(option_codes)

    one_room_shape_codes: list[str] = map_codes(filters.get("one_room_shape_types", []), ONE_ROOM_SHAPE_MAP)
    if one_room_shape_codes:
        params["oneRoomShapeTypes"] = join_codes(one_room_shape_codes)

    params["showOnlySelectedRegion"] = "true"
    return params


def rebuild_map_url(current_url: str, filters: dict[str, Any] | None) -> str:
    filter_query: dict[str, str] = build_filter_query(filters)
    if not filter_query:
        return current_url

    parsed = urlparse(current_url)
    query: dict[str, list[str]] = parse_qs(parsed.query, keep_blank_values=True)

    for k, v in filter_query.items():
        query[k] = [v]

    flat_query: dict[str, str] = {k: v[-1] for k, v in query.items()}
    new_query: str = urlencode(flat_query, doseq=False, safe="-")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def build_payload_from_current_url(current_url: str) -> dict[str, Any]:
    parsed = urlparse(current_url)
    qs: dict[str, list[str]] = parse_qs(parsed.query, keep_blank_values=True)

    def get_one(name: str) -> str:
        values: list[str] = qs.get(name, [])
        return values[-1] if values else ""

    def get_codes(name: str) -> list[str]:
        text: str = get_one(name)
        return [x for x in text.split("-") if x] if text else []

    center_text: str = get_one("center")
    zoom_text: str = get_one("zoom")

    center_x: float = 127.0
    center_y: float = 37.0
    if center_text and "-" in center_text:
        cx, cy = center_text.split("-", 1)
        center_x = float(cx)
        center_y = float(cy)

    zoom_value: float = float(zoom_text) if zoom_text else 14.0
    x_gap: float = 0.04
    y_gap: float = 0.015

    payload: dict[str, Any] = {
        "filter": {
            "tradeTypes": get_codes("tradeTypes"),
            "realEstateTypes": get_codes("realEstateTypes"),
            "roomCount": get_codes("roomCount"),
            "bathRoomCount": get_codes("bathRoomCount"),
            "optionTypes": get_codes("facilities"),
            "oneRoomShapeTypes": get_codes("oneRoomShapeTypes"),
            "moveInTypes": get_codes("moveInTypes"),
            "filtersExclusiveSpace": get_one("exclusiveSpaceMode") == "true",
            "floorTypes": get_codes("floor"),
            "directionTypes": get_codes("direction"),
            "hasArticlePhoto": get_one("hasArticlePhoto") == "true",
            "isAuthorizedByOwner": get_one("isAuthorizedByOwner") == "true",
            "parkingTypes": get_codes("parkingTypes"),
            "entranceTypes": get_codes("entranceTypes"),
            "hasArticle": get_one("hasArticleComplex") == "true",
            "legalDivisionNumbers": [],
            "legalDivisionType": "EUP",
        },
        "boundingBox": {
            "left": center_x - x_gap,
            "right": center_x + x_gap,
            "top": center_y + y_gap,
            "bottom": center_y - y_gap,
        },
        "precision": zoom_value,
        "userChannelType": "PC",
        "articlePagingRequest": {
            "size": 30,
            "articleSortType": "RANKING_DESC",
            "lastInfo": [],
        },
    }

    if get_one("dealPrice"):
        payload["filter"]["dealPrice"] = parse_range_value(get_one("dealPrice"))
    if get_one("warrantyPrice"):
        payload["filter"]["warrantyPrice"] = parse_range_value(get_one("warrantyPrice"))
    if get_one("rentPrice"):
        payload["filter"]["rentPrice"] = parse_range_value(get_one("rentPrice"))
    if get_one("space"):
        payload["filter"]["space"] = parse_range_value(get_one("space"))
    if get_one("approvalElapsedYear"):
        payload["filter"]["approvalElapsedYear"] = parse_range_value(get_one("approvalElapsedYear"))
    if get_one("managementFee"):
        payload["filter"]["managementFee"] = parse_range_value(get_one("managementFee"))
    if get_one("householdNumber"):
        payload["filter"]["householdNumber"] = parse_range_value(get_one("householdNumber"))
    if get_one("subwayWalkingMinute"):
        payload["filter"]["walkingMinuteToSubwayStation"] = {
            "min": 0,
            "max": int(float(get_one("subwayWalkingMinute"))),
        }
    if get_one("loanRatioType"):
        payload["filter"]["loanRatioType"] = get_one("loanRatioType")

    return payload


def browser_fetch_bounded_articles(
        driver: Any,
        payload: dict[str, Any],
        wait_sec: int = 30,
) -> dict[str, Any]:
    script: str = """
    const payload = arguments[0];
    const done = arguments[arguments.length - 1];

    (async () => {
        try {
            const res = await fetch("https://fin.land.naver.com/front-api/v1/article/boundedArticles", {
                method: "POST",
                credentials: "include",
                headers: {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            let text = "";
            try {
                text = await res.text();
            } catch (e) {}

            let jsonData = null;
            try {
                jsonData = text ? JSON.parse(text) : null;
            } catch (e) {}

            done({
                ok: res.ok,
                status: res.status,
                statusText: res.statusText,
                url: res.url,
                text: text,
                json: jsonData
            });
        } catch (e) {
            done({
                ok: false,
                status: -1,
                statusText: String(e),
                url: "",
                text: "",
                json: null
            });
        }
    })();
    """
    driver.set_script_timeout(wait_sec)
    return driver.execute_async_script(script, payload)


def browser_fetch_basic_info(
        driver: Any,
        article_no: str,
        real_estate_type: str,
        trade_type: str,
        wait_sec: int = 30,
) -> dict[str, Any]:
    script: str = """
    const articleNo = arguments[0];
    const realEstateType = arguments[1];
    const tradeType = arguments[2];
    const done = arguments[arguments.length - 1];

    const url = new URL("https://fin.land.naver.com/front-api/v1/article/basicInfo");
    url.searchParams.set("articleNumber", articleNo);
    url.searchParams.set("realEstateType", realEstateType);
    url.searchParams.set("tradeType", tradeType);

    (async () => {
        try {
            const res = await fetch(url.toString(), {
                method: "GET",
                credentials: "include",
                headers: {
                    "Accept": "application/json, text/plain, */*"
                }
            });

            let text = "";
            try {
                text = await res.text();
            } catch (e) {}

            let jsonData = null;
            try {
                jsonData = text ? JSON.parse(text) : null;
            } catch (e) {}

            done({
                ok: res.ok,
                status: res.status,
                statusText: res.statusText,
                url: res.url,
                text: text,
                json: jsonData
            });
        } catch (e) {
            done({
                ok: false,
                status: -1,
                statusText: String(e),
                url: "",
                text: "",
                json: null
            });
        }
    })();
    """
    driver.set_script_timeout(wait_sec)
    return driver.execute_async_script(script, article_no, real_estate_type, trade_type)


def collect_next_list_pages_by_browser(
        driver: Any,
        base_payload: dict[str, Any],
        first_result: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_items(page_list: list[dict[str, Any]]) -> None:
        for item in page_list:
            info: dict[str, Any] = item.get("representativeArticleInfo", {})
            article_no: str = str(info.get("articleNumber", "")).strip()
            if article_no and article_no not in seen:
                seen.add(article_no)
                items.append(item)

    first_list: list[dict[str, Any]] = first_result.get("list", [])
    add_items(first_list)

    print(
        f"[목록] first "
        f"count={len(first_list)} "
        f"hasNext={first_result.get('hasNextPage')} "
        f"total={first_result.get('totalCount')}"
    )

    seed: str | None = first_result.get("seed")
    last_info: list[Any] = first_result.get("lastInfo", [])
    has_next: bool = bool(first_result.get("hasNextPage"))
    page: int = 2

    while has_next and last_info:
        req: dict[str, Any] = json.loads(json.dumps(base_payload))
        req.setdefault("articlePagingRequest", {})
        req["articlePagingRequest"]["seed"] = seed
        req["articlePagingRequest"]["lastInfo"] = last_info

        print(f"[목록] page={page} 브라우저 fetch 요청")
        res_data: dict[str, Any] = browser_fetch_bounded_articles(driver, req, 30)

        print(
            f"[목록] page={page} "
            f"status={res_data.get('status')} "
            f"ok={res_data.get('ok')}"
        )

        if res_data.get("status") != 200:
            print(f"[목록] page={page} 실패 body={res_data.get('text', '')[:500]}")
            break

        json_data: dict[str, Any] = res_data.get("json") or {}
        result: dict[str, Any] = json_data.get("result", {})
        page_list: list[dict[str, Any]] = result.get("list", [])

        print(
            f"[목록] page={page} "
            f"count={len(page_list)} "
            f"hasNext={result.get('hasNextPage')} "
            f"total={result.get('totalCount')}"
        )

        if not page_list:
            break

        add_items(page_list)

        seed = result.get("seed", seed)
        last_info = result.get("lastInfo", [])
        has_next = bool(result.get("hasNextPage"))
        page += 1
        sleep_rand(0.8, 1.2)

    print(f"[목록] 최종 수집 건수={len(items)}")
    return items


def collect_detail_by_browser(
        driver: Any,
        items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []

    for i, item in enumerate(items, 1):
        info: dict[str, Any] = item["representativeArticleInfo"]
        article_no: str = str(info["articleNumber"])
        real_estate_type: str = str(info["realEstateType"])
        trade_type: str = str(info["tradeType"])

        print(f"[상세] {i}/{len(items)} articleNumber={article_no}")

        res_data: dict[str, Any] = browser_fetch_basic_info(
            driver,
            article_no,
            real_estate_type,
            trade_type,
            30,
        )

        print(
            f"[상세] {i}/{len(items)} "
            f"status={res_data.get('status')} "
            f"ok={res_data.get('ok')}"
        )

        details.append(
            {
                "articleNumber": article_no,
                "realEstateType": real_estate_type,
                "tradeType": trade_type,
                "listItem": item,
                "detail": res_data.get("json"),
                "detailFetchMeta": {
                    "status": res_data.get("status"),
                    "ok": res_data.get("ok"),
                    "statusText": res_data.get("statusText"),
                    "url": res_data.get("url"),
                    "text": res_data.get("text"),
                },
            }
        )

        sleep_rand(2.2, 3.2)

    print(f"[상세] 최종 수집 건수={len(details)}")
    return details


def run_one_keyword(driver: Any, keyword: str, filters: dict[str, Any] | None) -> None:
    print(f"\n===== 시작: {keyword} =====")

    print("[1] 메인 이동")
    driver.get(URL)
    time.sleep(4)

    print("[2] 검색 버튼 클릭")
    driver.execute_script("arguments[0].click();", q(driver, "div.HeaderSearch_area-search-capsule__MhT1a button"))
    time.sleep(1.5)

    print("[3] 검색어 입력")
    search_input: Any = q(driver, "#header-search")
    set_input(driver, search_input, keyword)
    time.sleep(0.5)
    search_input.send_keys(Keys.ENTER)

    print("[4] 첫 번째 지역 클릭")
    region_buttons: list[Any] = qq(driver, "button.SearchResultList_link__0yl8W")
    if not region_buttons:
        raise Exception("첫 번째 지역 버튼을 찾지 못했습니다.")
    driver.execute_script("arguments[0].click();", region_buttons[0])
    time.sleep(5)

    current_url: str = driver.current_url
    print(f"[5] 현재 URL\n{current_url}")

    filtered_url: str = rebuild_map_url(current_url, filters)
    print(f"[6] 최종 URL\n{filtered_url}")

    print("[7] 최종 URL 요청")
    driver.get(filtered_url)
    time.sleep(5)

    print("[8] 지도 축소 2번")
    zoom_out(driver, 2)
    time.sleep(2)

    print("[9] 목록 후킹 설치")
    inject_list_hook(driver)

    print("[10] 매물 버튼 클릭")
    click_article_button(driver, 20)

    print("[11] 첫 목록 요청/응답 대기")
    hook_data: dict[str, Any] = get_first_list_hook_data(driver, 20)
    body_text: str = hook_data.get("bodyText", "")
    response_json: dict[str, Any] = hook_data.get("responseJson", {})

    print(f"[후킹] 수신 여부={bool(hook_data)}")
    print(f"[후킹] bodyText 존재={bool(body_text)}")
    print(f"[후킹] responseJson 존재={bool(response_json)}")

    if body_text:
        base_payload: dict[str, Any] = json.loads(body_text)
    else:
        print("[후킹] bodyText 없음 -> 현재 URL 기준 payload 복구")
        base_payload = build_payload_from_current_url(driver.current_url)

    first_result: dict[str, Any] = response_json.get("result", {})

    if not first_result:
        print("[후킹] 첫 응답 result 없음 -> 브라우저 fetch로 첫 페이지 재요청")
        retry_res: dict[str, Any] = browser_fetch_bounded_articles(driver, base_payload, 30)
        print(
            f"[후킹 재요청] status={retry_res.get('status')} "
            f"ok={retry_res.get('ok')}"
        )
        retry_json: dict[str, Any] = retry_res.get("json") or {}
        first_result = retry_json.get("result", {})

    if not first_result:
        raise Exception("첫 목록 result를 확보하지 못했습니다.")

    print("[12] 목록 수집")
    items: list[dict[str, Any]] = collect_next_list_pages_by_browser(driver, base_payload, first_result)
    with open(f"{slug(keyword)}_list.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("[13] 상세 수집")
    details: list[dict[str, Any]] = collect_detail_by_browser(driver, items)
    with open(f"{slug(keyword)}_detail.json", "w", encoding="utf-8") as f:
        json.dump(details, f, ensure_ascii=False, indent=2)

    print(f"===== 완료: {keyword} / 목록={len(items)} / 상세={len(details)} =====")


def main() -> None:
    su: SeleniumUtils = SeleniumUtils(headless=False, debug=True)
    try:
        driver: Any = su.start_driver(timeout=60, view_mode="browser", window_size=(1600, 1000))
        for keyword in TEST_KEYWORDS:
            run_one_keyword(driver, keyword, TEST_FILTERS)
        input("엔터 누르면 종료")
    finally:
        su.quit()


if __name__ == "__main__":
    main()