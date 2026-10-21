"""디스코 목록·상세 조회 → 체크한 컬럼만 공통 SQLite DB에 저장합니다."""

import json
import math
import random
import re
import time
import requests
from datetime import datetime
from urllib.parse import urlencode, parse_qs, urlsplit

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException as SeleniumTimeoutException

from src.utils.disco_filters import build_disco_form
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
from src.repositories.worker_db_repository import WorkerDbRepository



LIST_LIMIT = 20
MAP_LEVEL = 3

# 디스코 화면에서 확인한 map_lv=3의 네 방향 거리를 기준으로 사용합니다.
# 실제 요청 범위는 config의 가로·세로 배율(기본 1.5)을 적용해 중간값으로 넓힙니다.
EARTH_RADIUS = 6378137.0
REFERENCE_MAP = {
    "swLat": 37.488512425802476, "swLng": 127.046812752172,
    "neLat": 37.49796186353175, "neLng": 127.06659383688581,
    "centerLat": 37.49323776305756, "centerLng": 127.05670253513213,
}

DEFAULT_FORM = [
    ("approvalYear", "null"),
    ("minPrice", "null"),
    ("maxPrice", "null"),
    ("minMonthly", "null"),
    ("maxMonthly", "null"),
    ("minDeposit", "null"),
    ("maxDeposit", "null"),
    ("minArea", "null"),
    ("maxArea", "null"),
    ("areaUnit", "pyeong"),
    ("selectedCategory", "null"),
    ("ownerVerifiedOnly", ""),
]

# 네이버 지도 화면 또는 후킹 응답이 일시적으로 늦을 때 재시도할 예외입니다.
NAVER_TRANSIENT_ERRORS = (TimeoutError, SeleniumTimeoutException)
NAVER_RECOVERABLE_ERRORS = (LookupError, TimeoutError, SeleniumTimeoutException)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def _date_text(value):
    """YYYYMMDD를 YYYY-MM-DD로 바꿉니다."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return str(value or "") or None


def _number_value(value):
    """숫자 값을 엑셀에서 계산 가능한 int/float 형태로 정리합니다."""
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _disco_price_to_manwon(value):
    """디스코의 '79억 5000만원' 또는 숫자 가격을 만원 단위로 변환합니다."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return _number_value(value)

    text = str(value).replace(",", "").replace(" ", "").strip()
    total = 0.0
    billion = re.search(r"([\d.]+)억", text)
    manwon = re.search(r"([\d.]+)만(?:원)?", text)
    if billion:
        total += float(billion.group(1)) * 10000
    if manwon:
        total += float(manwon.group(1))
    if total > 0:
        return int(total) if total.is_integer() else round(total, 2)
    return _number_value(text)


def _won_to_manwon(value):
    """원 단위 공시지가/공시가격을 만원 단위 숫자로 변환합니다."""
    number = _number_value(value)
    if number is None:
        return None
    converted = float(number) / 10000
    return int(converted) if converted.is_integer() else round(converted, 2)


PROPERTY_TYPE_NAMES = {
    0: "아파트", 1: "주상복합", 2: "오피스텔", 3: "단독주택",
    4: "다가구", 5: "전원주택", 6: "상가주택", 7: "연립",
    8: "다세대", 10: "상가", 11: "사무실", 12: "상업용건물",
    15: "숙박시설", 16: "토지", 17: "공장", 18: "지식산업센터",
    19: "창고", 20: "생활숙박시설",
}
DEAL_TYPE_NAMES = {0: "매매", 1: "전세", 2: "월세"}


def _first_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _code_value(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _minimum_positive(values):
    numbers = [_number_value(value) for value in values]
    numbers = [value for value in numbers if value is not None]
    return min(numbers) if numbers else None


def _listing_url(list_rows):
    """목록/그룹 광고 중 첫 번째 유효 광고의 디스코 상세 링크를 반환합니다."""
    for row in _advertisement_rows(list_rows):
        direct_url = _first_value(row, "url", "link", "sale_url", "detail_url")
        if direct_url and str(direct_url).startswith(("http://", "https://")):
            return str(direct_url).strip()

        # 디스코 웹 매물 상세 주소는 목록 응답의 suid(uuid)로 구성됩니다.
        sale_id = _first_value(row, "suid", "uuid")
        if sale_id:
            return f"https://www.disco.re/m/{str(sale_id).strip()}"
    return None


def _property_type_from_title(value):
    """코드가 없는 광고는 제목의 명시적인 유형 표현만 보조적으로 사용합니다."""
    title = str(value or "")
    keyword_names = (
        ("지식산업센터", "지식산업센터"), ("생활숙박시설", "생활숙박시설"),
        ("상업용건물", "상업용건물"), ("상가주택", "상가주택"),
        ("주상복합", "주상복합"), ("오피스텔", "오피스텔"),
        ("아파트", "아파트"), ("다가구", "다가구"), ("다세대", "다세대"),
        ("연립", "연립"), ("전원주택", "전원주택"), ("단독주택", "단독주택"),
        ("숙박시설", "숙박시설"), ("공장", "공장"), ("창고", "창고"),
        ("사무실", "사무실"), ("상가", "상가"), ("토지", "토지"),
    )
    return next((name for keyword, name in keyword_names if keyword in title), None)


def _advertisement_rows(list_rows):
    """목록 행과 sale/jeonse/monthly 같은 중첩 광고 행을 모두 펼칩니다."""
    result = []
    nested_deal_codes = {
        "sale": 0, "trade": 0, "매매": 0,
        "jeonse": 1, "전세": 1,
        "monthly": 2, "rent": 2, "월세": 2,
    }
    for source in list_rows or []:
        if not isinstance(source, dict):
            continue
        result.append(dict(source))
        for key, deal_code in nested_deal_codes.items():
            nested = source.get(key)
            nested_rows = nested if isinstance(nested, list) else [nested]
            for nested_row in nested_rows:
                if not isinstance(nested_row, dict):
                    continue
                merged = dict(source)
                merged.update(nested_row)
                merged.setdefault("_deal_type", deal_code)
                result.append(merged)
    return result


def _korean_advertisement_summary(list_rows):
    """동일 PNU 광고 중 거래유형별 최저 금액을 만원 단위로 집계합니다."""
    property_types, deal_types = [], []
    sale_prices, jeonse_prices = [], []
    monthly_deposits, monthly_rents, management_fees = [], [], []

    for row in _advertisement_rows(list_rows):
        property_code = _code_value(_first_value(
            row, "e_rand_type", "randType", "rand_type", "propertyType", "property_type",
            "categoryCode", "category_code", "rt"
        ))
        property_name = _first_value(
            row, "estate_type_tag", "tag", "randTypeName", "rand_type_name", "propertyTypeName",
            "property_type_name", "매물유형"
        ) or PROPERTY_TYPE_NAMES.get(property_code) or _property_type_from_title(row.get("title"))
        if property_name and property_name not in property_types:
            property_types.append(str(property_name))

        raw_deal_type = _first_value(row, "_deal_type", "dealType", "deal_type", "dt")
        deal_code = _code_value(raw_deal_type)
        deal_name = _first_value(
            row, "dealTypeName", "deal_type_name", "거래방식"
        ) or DEAL_TYPE_NAMES.get(deal_code)
        if not deal_name and str(raw_deal_type or "").strip() in ("매매", "전세", "월세"):
            deal_name = str(raw_deal_type).strip()
            deal_code = {"매매": 0, "전세": 1, "월세": 2}[deal_name]
        if deal_name and deal_name not in deal_types:
            deal_types.append(str(deal_name))

        # 디스코 목록의 p는 광고 대표금액이며 이미 만원 단위입니다.
        representative_price = _first_value(row, "p", "price", "deal_price")
        if deal_code == 0:
            sale_prices.append(_disco_price_to_manwon(
                _first_value(row, "sale_price", "trade_price") or representative_price
            ))
        elif deal_code == 1:
            jeonse_prices.append(_disco_price_to_manwon(
                _first_value(row, "jeonse_price", "deposit_price") or representative_price
            ))
        elif deal_code == 2:
            monthly_deposits.append(_disco_price_to_manwon(_first_value(
                row, "monthly_deposit", "deposit", "dp", "d"
            )))
            monthly_rents.append(_disco_price_to_manwon(_first_value(
                row, "monthly_rent", "rent_price", "drt", "m"
            ) or representative_price))
            management_fees.append(_disco_price_to_manwon(_first_value(
                row, "management_fee", "maintenance_fee", "expense_value", "dc"
            )))

    return {
        "매물유형": ", ".join(property_types) or None,
        "거래방식": ", ".join(deal_types) or None,
        "매물링크": _listing_url(list_rows),
        "광고 금액_매매가": _minimum_positive(sale_prices),
        "광고 금액_전세": _minimum_positive(jeonse_prices),
        "광고 금액_월세_보증금": _minimum_positive(monthly_deposits),
        "광고 금액_월세_월세": _minimum_positive(monthly_rents),
        "광고 금액_월세_관리비": _minimum_positive(management_fees),
    }


def _address_parts(address):
    """지번주소에서 시도, 시군구, 읍면동을 단순 분리합니다."""
    tokens = str(address or "").split()
    if not tokens:
        return None, None, None

    lot_index = next(
        (index for index, token in enumerate(tokens) if any(ch.isdigit() for ch in token)),
        len(tokens),
    )
    regions = tokens[:lot_index]
    sido = regions[0] if regions else None
    eup_myeon_dong = regions[-1] if len(regions) >= 2 else None
    sigungu = " ".join(regions[1:-1]) or None
    return sido, sigungu, eup_myeon_dong


def _planning_values(value):
    """토지이용계획 문장을 화면의 포함/저촉/접함 항목으로 분리합니다."""
    relations = {"포함": [], "저촉": [], "접함": []}
    for text in str(value or "").split(","):
        text = text.strip()
        for relation in relations:
            suffix = f"({relation})"
            if text.endswith(suffix):
                relations[relation].append(text[:-len(suffix)].strip())
                break
    return {
        relation: ", ".join(values) if values else None
        for relation, values in relations.items()
    }


def _korean_land_info(result):
    """land_by_pnu 응답을 실제 화면 명칭으로 변환합니다."""
    main_plan = _planning_values(result.get("land_use_planning_info_main"))
    etc_plan = _planning_values(result.get("land_use_planning_info_etc"))
    owner = result.get("owner_gbn")
    share = result.get("share")
    if owner not in (None, "") and share not in (None, ""):
        owner = f"{owner} (공유인수 {share})"

    return {
        "토지 정보_면적": result.get("area"),
        "토지 정보_지목": result.get("purpose"),
        "토지 정보_용도지역": result.get("p6"),
        "토지 정보_이용상황": result.get("p10"),
        "토지 정보_소유구분": owner,
        "토지 정보_소유권변동일자": _date_text(result.get("days")),
        "토지 정보_소유권변동원인": result.get("why"),
        "토지 정보_도로접면": result.get("p16"),
        "토지 정보_지형높이": result.get("p12"),
        "토지 정보_지형형상": result.get("p14"),
        "토지이용계획_국토의 계획 및 이용에 관한 법률_포함": main_plan["포함"],
        "토지이용계획_국토의 계획 및 이용에 관한 법률_저촉": main_plan["저촉"],
        "토지이용계획_국토의 계획 및 이용에 관한 법률_접함": main_plan["접함"],
        "토지이용계획_기타법률_포함": etc_plan["포함"],
        "토지이용계획_기타법률_저촉": etc_plan["저촉"],
        "토지이용계획_기타법률_접함": etc_plan["접함"],
    }


def _korean_land_history(rows):
    """화면의 토지 이동(변동) 사유 표와 동일한 키로 변환합니다."""
    return [
        {
            "일자": _date_text(row.get("move_date")),
            "사유": row.get("reason"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _korean_price_table(rows, value_name):
    """공시지가·주택가격 공통 배열과 최신 금액을 만듭니다."""
    prices = []
    sortable = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        year, month, price = row[0], str(row[1]).zfill(2), _won_to_manwon(row[2])
        prices.append({"기준년도": f"{year}.{month}", value_name: price})
        try:
            sortable.append((int(year), int(month), price))
        except (TypeError, ValueError):
            pass
    return prices, max(sortable, default=(None, None, None))[2]


def _korean_land_prices(rows):
    """개별공시지가 표를 기준년도/공시지가 배열과 현재 금액으로 만듭니다."""
    prices, current = _korean_price_table(rows, "공시지가(㎡)")
    return {
        "개별공시지가": prices,
        "개별공시지가_공시지가(㎡)": current,
    }


def _mapped_fields(row, fields, date_sources=()):
    return {
        label: _date_text(row.get(source)) if source in date_sources else row.get(source)
        for label, source in fields
    }


ARCH_INFO_FIELDS = (
    ("건물 정보_건물이름", "a23"), ("건물 정보_주용도", "a36"),
    ("건물 정보_기타용도", "a37"), ("건물 정보_주구조", "a33"),
    ("건물 정보_지붕구조", "a39"), ("건물 정보_높이", "a43"),
    ("건물 정보_지상", "a44"), ("건물 정보_지하", "a45"),
    ("건물 정보_대지면적", "a26"), ("건물 정보_건축면적", "a27"),
    ("건물 정보_건축면적_건폐율", "a28"), ("건물 정보_연면적", "a29"),
    ("건물 정보_용적률산정연면적", "a30"), ("건물 정보_용적률산정연면적_용적률", "a31"),
    ("건물 정보_세대 수_세대", "a41"), ("건물 정보_세대 수_가구", "a42"),
    ("건물 정보_세대 수_호수", "a67"), ("건물 정보_외필지 수", "a17"),
    ("건물 정보_오수정화시설_형식", "g23"), ("건물 정보_오수정화시설_형식(기타)", "g24"),
    ("건물 정보_오수정화시설_용량(인용)", "g26"), ("건물 정보_오수정화시설_용량(루베)", "g27"),
    ("건물 정보_주차장_자주식_옥내_댓수", "a55"), ("건물 정보_주차장_자주식_옥내_면적", "a56"),
    ("건물 정보_주차장_자주식_옥외_댓수", "a57"), ("건물 정보_주차장_자주식_옥외_면적", "a58"),
    ("건물 정보_주차장_기계식_옥내_댓수", "a51"), ("건물 정보_주차장_기계식_옥내_면적", "a52"),
    ("건물 정보_주차장_기계식_옥외_댓수", "a53"), ("건물 정보_주차장_기계식_옥외_면적", "a54"),
    ("건물 정보_승강기_승용", "a46"), ("건물 정보_승강기_비상용", "a47"),
    ("건물 정보_일자정보_허가일", "a59"), ("건물 정보_일자정보_착공일", "a60"),
    ("건물 정보_일자정보_사용승인일", "a61"),
)
ARCH_FLOOR_FIELDS = (
    ("건축물구분", "d31"), ("층", "floor"), ("주용도", "d27"),
    ("기타용도", "d28"), ("구조", "d24"), ("면적", "d29"), ("건물이름", "d32"),
)
EXCLUSIVE_PART_FIELDS = (
    ("구분", "e28"), ("층", "e31"), ("면적", "e38"),
    ("건축물", "e30"), ("용도", "e37"),
)


def _korean_arch_info(result):
    """arch_by_pnu의 첫 표제부를 화면의 건물 정보 명칭으로 변환합니다."""
    rows = result.get("title_section") or result.get("overall_title_section") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    return _mapped_fields(rows[0], ARCH_INFO_FIELDS, {"a59", "a60", "a61"})


def _korean_arch_floors(rows):
    """arch_floor_list 응답을 건축물현황의 한글 키 배열로 변환합니다."""
    return [
        _mapped_fields(row, ARCH_FLOOR_FIELDS) for row in rows if isinstance(row, dict)
    ]


def _korean_businesses(rows):
    """상가업소정보를 화면 상세 팝업의 명칭으로 변환합니다."""
    businesses = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        location = ""
        if row.get("dong"):
            location += f"{row['dong']}동"
        if row.get("floor"):
            location += f" {row['floor']}층"
        if row.get("ho"):
            location += f" {row['ho']}호"
        businesses.append({
            "상호명": row.get("sbname"),
            "층호정보": location.strip() or "층호정보없음",
            "업종 대분류": row.get("sbclass1name"),
            "업종 중분류": row.get("sbclass2name"),
            "업종 소분류": row.get("sbclass3name"),
        })
    return businesses


def _korean_house_prices(rows):
    """개별주택공시가격을 화면 표와 현재 가격으로 변환합니다."""
    prices, current = _korean_price_table(rows, "공시가격")
    return {
        "개별주택공시가격": prices,
        "개별주택공시가격_공시가격": current,
    }


def _korean_exclusive_parts(rows):
    """전유부 표를 화면의 한글 키 배열로 변환합니다."""
    return [
        _mapped_fields(row, EXCLUSIVE_PART_FIELDS)
        for row in rows if isinstance(row, dict)
    ]


def _korean_apart_prices(rows):
    """공동주택공시가격을 화면 표와 현재 가격으로 변환합니다."""
    prices, current = _korean_price_table(rows, "공시가격")
    first = rows[0] if rows and isinstance(rows[0], (list, tuple)) else []
    return {
        "공동주택공시가격": prices,
        "공동주택공시가격_공시가격": current,
        "공동주택공시가격_동": first[3] if len(first) > 3 else None,
        "공동주택공시가격_층": first[4] if len(first) > 4 else None,
        "공동주택공시가격_호": first[5] if len(first) > 5 else None,
        "공동주택공시가격_전용면적": first[6] if len(first) > 6 else None,
    }


def make_map_bounds(center_lat, center_lng, width_scale=1.0, height_scale=1.0):
    """중심 위·경도로 map_lv=4의 남서/북동 좌표를 계산합니다."""
    lat = float(center_lat)
    lng = float(center_lng)
    if not -85.0 < lat < 85.0 or not -180.0 <= lng <= 180.0:
        raise ValueError(f"잘못된 중심 좌표입니다: lat={lat}, lng={lng}")
    if not 0 < width_scale <= 3 or not 0 < height_scale <= 3:
        raise ValueError("지도 배율은 0보다 크고 3 이하여야 합니다.")

    def mercator_y(latitude):
        return EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))

    # 기준 화면의 중심이 사각형의 정확한 중앙이 아니므로 네 방향을 따로 보존합니다.
    left = EARTH_RADIUS * math.radians(REFERENCE_MAP["centerLng"] - REFERENCE_MAP["swLng"])
    right = EARTH_RADIUS * math.radians(REFERENCE_MAP["neLng"] - REFERENCE_MAP["centerLng"])
    down = mercator_y(REFERENCE_MAP["centerLat"]) - mercator_y(REFERENCE_MAP["swLat"])
    up = mercator_y(REFERENCE_MAP["neLat"]) - mercator_y(REFERENCE_MAP["centerLat"])

    center_x = EARTH_RADIUS * math.radians(lng)
    center_y = EARTH_RADIUS * math.log(
        math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)
    )

    def to_lat_lng(x, y):
        out_lat = math.degrees(2.0 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2.0)
        out_lng = math.degrees(x / EARTH_RADIUS)
        return out_lat, out_lng

    sw_lat, sw_lng = to_lat_lng(
        center_x - left * width_scale,
        center_y - down * height_scale,
        )
    ne_lat, ne_lng = to_lat_lng(
        center_x + right * width_scale,
        center_y + up * height_scale,
        )
    return {
        "swLat": sw_lat,
        "swLng": sw_lng,
        "neLat": ne_lat,
        "neLng": ne_lng,
        "map_lv": MAP_LEVEL,
        "centerLat": lat,
        "centerLng": lng,
    }


def _subway_filter_limit(filters):
    """출력 컬럼 체크와 분리: 상위 '역세권' 체크 + 입력값만 사용합니다."""
    limits = []

    def visit(nodes, enabled=True):
        if isinstance(nodes, dict):
            nodes = [nodes]
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            active = enabled
            if 'checked' in node:
                active = active and str(node['checked']).lower() in ('true', '1', 'y', 'yes', 'on')
            if not active:
                continue
            if node.get('code') in ('subway_walking_minute', 'subwayWalkingMinute'):
                raw = str(node.get('value') if node.get('value') is not None else '').strip()
                if raw:
                    if not re.fullmatch(r'[0-9]+', raw) or int(raw) <= 0:
                        raise ValueError('역세권 도보 시간은 1 이상의 정수(분)로 입력해주세요.')
                    limits.append(int(raw))
            for name in ('children', 'items'):
                visit(node.get(name), active)

    visit(filters)
    return min(limits) if limits else None


def _naver_first_subway_name(payload):
    """'지하철역' 검색 결과에서 첫 지하철역 이름을 보조값으로 얻습니다."""
    result = payload.get('result') if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return None
    place = result.get('place') or {}
    rows = place.get('list') if isinstance(place, dict) else None
    first_name = None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        theme = row.get('theme') or {}
        if not isinstance(theme, dict):
            theme = {}
        category = ' '.join(str(row.get(key) or '') for key in ('category', 'categoryName'))
        is_subway = (
                str(theme.get('isSubway') or '') == '1'
                or '지하철' in category
                or '전철' in category
        )
        name = str(row.get('name') or row.get('display') or row.get('title') or '').strip()
        if name:
            name = re.sub(r'<[^>]+>', '', name)
            first_name = first_name or name
            if is_subway:
                return name
    # 검색어 자체가 '지하철역'이므로 응답에 isSubway 표시가 없는 버전에서도
    # 네이버가 거리순으로 돌려준 첫 장소를 사용합니다.
    return first_name


def _naver_search_has_results(payload):
    """allSearch 응답에 장소/지번/도로명 검색 결과가 하나라도 있는지 확인합니다."""
    result = payload.get('result') if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return False

    def contains_rows(value):
        if isinstance(value, list):
            return any(
                isinstance(row, dict)
                and any(row.get(key) not in (None, '') for key in (
                    'name', 'title', 'display', 'address', 'jibunAddress',
                    'roadAddress', 'x', 'y', 'id', 'placeId',
                ))
                for row in value
            )
        if not isinstance(value, dict):
            return False
        rows = value.get('list')
        if isinstance(rows, list) and contains_rows(rows):
            return True
        return any(
            contains_rows(child)
            for key, child in value.items()
            if key != 'list' and isinstance(child, (dict, list))
        )

    return contains_rows(result)


def _naver_walking_result(payload, fallback_station=None):
    """도보 길찾기 응답에서 추천(reco) 경로의 실제 초·미터 값을 읽습니다."""
    if not isinstance(payload, dict):
        raise ValueError('네이버 도보 길찾기 JSON 응답 형식이 아닙니다.')
    routes = payload.get('routes')
    if not isinstance(routes, list):
        result = payload.get('result') or {}
        routes = result.get('routes') if isinstance(result, dict) else None
    if not isinstance(routes, list):
        raise ValueError('네이버 도보 길찾기 응답에 routes가 없습니다.')

    route = next(
        (
            row for row in routes
            if isinstance(row, dict)
               and isinstance(row.get('summary'), dict)
               and row['summary'].get('option') == 'reco'
        ),
        None,
    )
    if route is None:
        raise ValueError('네이버 도보 길찾기 응답에 추천(reco) 경로가 없습니다.')

    summary = route['summary']
    try:
        distance = int(float(summary.get('distance')))
        duration = int(float(summary.get('duration')))
    except (TypeError, ValueError):
        raise ValueError('네이버 추천 경로의 거리 또는 시간이 숫자가 아닙니다.')
    if distance < 0 or duration <= 0:
        raise ValueError('네이버 추천 경로의 거리 또는 시간이 올바르지 않습니다.')

    way_names = []
    for way in summary.get('ways') or []:
        if not isinstance(way, dict):
            continue
        name = str(way.get('name') or '').strip()
        if name:
            way_names.append(name)

    fallback_station = str(fallback_station or '').strip()
    # 길찾기 출발지로 실제 선택한 '근처지하철역' 검색 결과를 우선합니다.
    # ways에는 목적지 주소도 포함되므로 단순히 '역' 포함 여부로 판단하면
    # '역삼동', '역촌동', '역곡동' 같은 주소를 역 이름으로 오인할 수 있습니다.
    station = fallback_station
    if not station:
        station = next(
            (
                name for name in way_names
                if re.search(r'(?:^|\s)[^\s]+역(?:\s|$)', name)
            ),
            None,
        )
    if not station:
        raise ValueError('네이버 추천 경로에서 지하철역 이름을 확인하지 못했습니다.')

    return {
        'nearest_subway_station': station,
        'subway_walking_minute': math.ceil(duration / 60),
        '_subway_walking_seconds': duration,
        '_subway_walking_distance_meter': distance,
    }


class ApiDiscoReDetailSetWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()
        self.major_repair_master_api_key = None
        self.major_repair_server_url = None
        self.worker_name = "disco_re_detail"
        self.driver = None
        self.selenium_driver = None
        self.file_driver = None
        self.browser_fetch_js = ""
        self.naver_subway_hook_js = ""
        self.region_coordinates = {}
        self._stopping = False
        self.list_items = []
        self.detail_items = []
        self._seen_items = set()
        self._seen_pnus = set()
        self.column_defs = None
        self.selected_column_defs = []
        self.db_repository = None
        self.job_status = "RUNNING"
        self.job_error = None
        self.geocode_js = ""
        self.get_json_js = ""
        self.get_json_batch_js = ""
        self._json_prefetch_cache = {}
        self._batch_fallback_logged = False
        self.page_delay = 0.3
        self.region_delay = 2.0
        self.request_delay = 0.1
        self.detail_thread_count = 4
        self.map_width_scale = 1.2
        self.map_height_scale = 1.2
        self.excel_header_merge_yn = True
        self._row_errors = []
        self._current_stat = None
        self._cleaned_up = False
        self.folder_path = ""
        self.auto_save_yn = False
        self.detail_log_yn = True
        self._naver_window_handle = None
        self._naver_subway_cache = {}
        self._naver_consecutive_search_misses = 0
        self._naver_last_missed_address = None
        self._active_subway_limit = None
        self._subway_lookup_failures = 0
        self._subway_filtered_count = 0

    def set_columns(self, columns):
        self.column_defs = [
            dict(row) for row in (columns or [])
            if isinstance(row, dict) and row.get("code") and row.get("checked", True)
        ]
        self.columns = [row["value"] for row in self.column_defs]

    def _setting(self, config, code, default):
        values = {row.get("code"): row.get("value") for row in config.get("setting", [])}
        values.update({row.get("code"): row.get("value")
                       for row in (getattr(self, "setting", None) or [])})
        return values.get(code, default)

    @staticmethod
    def _bool(value):
        return str(value).strip().lower() in ("true", "1", "y", "yes", "on")

    def _pause(self, seconds):
        end = time.monotonic() + seconds
        while self.running and time.monotonic() < end:
            time.sleep(min(0.1, max(0, end - time.monotonic())))
        return self.running

    def db_set(self):
        config = self.read_runtime_customer_config(customer_name=self.worker_name)
        definitions = self.column_defs if self.column_defs is not None else [
            dict(row) for row in config.get("columns", [])
            if isinstance(row, dict) and row.get("code") and row.get("checked", True)
        ]
        self.selected_column_defs = definitions
        if not self.selected_column_defs:
            raise ValueError("출력항목을 하나 이상 선택해주세요.")
        for name, default in (("page_delay", 0.3), ("region_delay", 2), ("request_delay", 0.1),
                              ("map_width_scale", 1.2), ("map_height_scale", 1.2)):
            value = float(self._setting(config, name, default))
            if not math.isfinite(value) or value < 0 or value > (3 if "scale" in name else 60):
                raise ValueError(f"잘못된 설정값: {name}={value}")
            if "scale" in name and value == 0:
                raise ValueError("지도 배율은 0보다 커야 합니다.")
            setattr(self, name, value)
        try:
            self.detail_thread_count = int(
                str(self._setting(config, "detail_thread_count", 4)).strip()
            )
        except (TypeError, ValueError):
            raise ValueError("상세 동시 조회 수는 1~4 사이의 정수여야 합니다.")
        if not 1 <= self.detail_thread_count <= 4:
            raise ValueError("상세 동시 조회 수는 1~4 사이여야 합니다.")
        self.folder_path = str(self._setting(config, "folder_path", "") or "")
        self.auto_save_yn = self._bool(self._setting(config, "auto_save_yn", False))
        self.detail_log_yn = self._bool(self._setting(config, "detail_log_yn", True))
        self.excel_header_merge_yn = self._bool(
            self._setting(config, "excel_header_merge_yn", True)
        )
        stat_defs = []
        for tab in config.get("db_tabs", []):
            if isinstance(tab, dict) and tab.get("key") == "stat":
                stat_defs = [
                    dict(row) for row in tab.get("columns", [])
                    if isinstance(row, dict) and row.get("code")
                       and row.get("checked", True)
                ]
                break
        user = getattr(self, "user", None)
        self.db_repository = WorkerDbRepository(
            db_path=self.get_runtime_db_path(),
            site_name="disco_re",
            worker_name=self.worker_name,
            detail_table_name="DISCO_RE_DETAIL",
            column_defs=self.selected_column_defs,
            user_id=getattr(user, "user_id", user),
            log_func=self.log_signal_func,
            detail_log_fields=("pnu",),
            stat_table_name="DISCO_RE_STAT",
            stat_column_defs=stat_defs,
        )
        schema_files = [
            "resources/customers/common/db/schema_hist.sql",
            "resources/customers/disco_re_detail/db/schema_detail.sql",
            "resources/customers/disco_re_detail/db/schema_stat.sql",
        ]
        if not self.db_repository.initialize(schema_files, start_job=True):
            raise RuntimeError("공통 WorkerDbRepository 초기화 실패")
        self._ensure_added_columns()
        self.log_signal_func("[디스코] 저장 컬럼: " + json.dumps(
            [c["value"] for c in self.selected_column_defs], ensure_ascii=False))
        self.log_signal_func(f"[디스코] DB 작업 시작: {self.db_repository.job_id}")

    def _ensure_added_columns(self):
        """기존 SQLite DB에도 이번 작업의 신규 컬럼을 안전하게 추가합니다."""
        rows = self.db_repository.sqlite.fetchall(
            'PRAGMA table_info("disco_re_detail")'
        )
        column_names = {
            str(row.get("name") or "")
            for row in (rows or [])
            if isinstance(row, dict)
        }
        added_columns = {
            "search_keyword": "TEXT",
            "property_type": "TEXT",
            "deal_type": "TEXT",
            "listing_url": "TEXT",
            "nearest_subway_station": "TEXT",
            "subway_walking_minute": "INTEGER",
            "ad_sale_price": "INTEGER",
            "ad_jeonse_price": "INTEGER",
            "ad_monthly_deposit": "INTEGER",
            "ad_monthly_rent": "INTEGER",
            "ad_management_fee": "INTEGER",
            "ground_floor_count": "INTEGER",
            "underground_floor_count": "INTEGER",
            "violation_building_yn": "TEXT",
            "violation_building_content": "TEXT",
        }
        for column_name, column_type in added_columns.items():
            if column_name in column_names:
                continue
            if not self.db_repository.sqlite.execute(
                    f'ALTER TABLE "disco_re_detail" ADD COLUMN "{column_name}" {column_type}'
            ):
                raise RuntimeError(f"기존 DB에 {column_name} 컬럼을 추가하지 못했습니다.")
            self.log_signal_func(f"[디스코] 기존 DB에 {column_name} 컬럼을 추가했습니다.")

    def init(self) -> bool:
        try:
            self.file_driver = FileUtils(self.log_signal_func)
            self.browser_fetch_js = self.file_driver.read_text_from_resources(
                "browser_fetch_json.js", "customers/disco_re_detail/js"
            )
            if not self.browser_fetch_js:
                raise FileNotFoundError("browser_fetch_json.js 파일을 찾을 수 없습니다.")
            self.geocode_js = self.file_driver.read_text_from_resources(
                "disco_geocode.js", "customers/disco_re_detail/js")
            self.get_json_js = self.file_driver.read_text_from_resources(
                "browser_get_json.js", "customers/disco_re_detail/js")
            self.get_json_batch_js = self.file_driver.read_text_from_resources(
                "browser_get_json_batch.js", "customers/disco_re_detail/js")
            self.naver_subway_hook_js = self.file_driver.read_text_from_resources(
                "naver_subway_hook.js", "customers/disco_re_detail/js")
            if not all((self.geocode_js, self.get_json_js, self.get_json_batch_js,
                        self.naver_subway_hook_js)):
                raise FileNotFoundError("디스코 주소검색/상세조회 JS 파일이 없습니다.")
            self.db_set()

            self.major_repair_server_url = str(
                self.get_runtime_customer_config_value(
                    key_name="server_url",
                    default="",
                    customer_name=self.worker_name
                ) or ""
            ).strip()

            self.major_repair_master_api_key = str(
                self.get_runtime_customer_config_value(
                    key_name="master_api_key",
                    default="",
                    customer_name=self.worker_name
                ) or ""
            ).strip()

            try:
                coordinate_rows = self.file_driver.read_json_array_from_resources(
                    "korea_eup_myeon_dong.json",
                    "customers/disco_re_detail/region",
                ) or []
            except Exception as error:
                coordinate_rows = []
                self.log_signal_func(
                    f"[디스코] 지역 좌표 파일을 읽지 못했습니다. "
                    f"화면 전달 좌표를 사용합니다: {error}"
                )
            for row in coordinate_rows:
                if not isinstance(row, dict):
                    continue
                key = self._region_key(row)
                if all(key):
                    self.region_coordinates[key] = row

            self.selenium_driver = SeleniumUtils(
                headless=False,
                debug=True,
                log_func=self.log_signal_func,
            )
            self.driver = self.selenium_driver.start_driver(
                timeout=1200,
                view_mode="browser",
                window_size=(1600, 1000),
            )
            if self.driver is None:
                raise RuntimeError("브라우저를 시작하지 못했습니다.")
            return True
        except Exception as error:
            self.job_status, self.job_error = "FAIL", str(error)
            self.log_signal_func(f"[디스코] 초기화 실패: {error}")
            self.cleanup()
            return False

    @staticmethod
    def _region_key(region):
        return tuple(
            str(region.get(name) or "").strip()
            for name in ("시도", "시군구", "읍면동")
        )

    @staticmethod
    def _read_coordinates(region):
        data = region.get("data") or {}
        coordinates = data.get("coordinates") or region.get("coordinates") or {}
        lng = (
                coordinates.get("xCoordinate")
                or coordinates.get("lng")
                or coordinates.get("longitude")
                or region.get("lng")
                or region.get("longitude")
                or region.get("경도")
        )
        lat = (
                coordinates.get("yCoordinate")
                or coordinates.get("lat")
                or coordinates.get("latitude")
                or region.get("lat")
                or region.get("latitude")
                or region.get("위도")
        )
        if lng in (None, "") or lat in (None, ""):
            return None
        return float(lat), float(lng)

    def _fallback_coordinates(self, region):
        coordinates = self._read_coordinates(region)
        if coordinates is None:
            source = self.region_coordinates.get(self._region_key(region))
            if source is None:
                address = " ".join(self._region_key(region))
                raise ValueError(f"지역 중심 좌표를 찾을 수 없습니다: {address}")
            coordinates = self._read_coordinates(source)
        if coordinates is None:
            address = " ".join(self._region_key(region))
            raise ValueError(f"지역 중심 좌표가 비어 있습니다: {address}")
        return coordinates

    def _disco_coordinates(self, region):
        address = " ".join(self._region_key(region))
        try:
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script(
                    "return !!(window.geocoder && "
                    "typeof window.geocoder.addressSearch === 'function');"
                )
            )
            self.driver.set_script_timeout(15)
            result = self.driver.execute_async_script(self.geocode_js, address) or {}
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "디스코 주소 검색 실패")

            lat = float(result["lat"])
            lng = float(result["lng"])
            if not -85.0 < lat < 85.0 or not -180.0 <= lng <= 180.0:
                raise ValueError(f"잘못된 검색 좌표: lat={lat}, lng={lng}")

            self.log_signal_func(
                f"[디스코] 주소 검색 좌표 사용: {address} / lat={lat}, lng={lng}"
            )
            return lat, lng
        except Exception as error:
            coordinates = self._fallback_coordinates(region)
            self.log_signal_func(
                f"[디스코] 주소 검색 실패, 예비 좌표 사용: {address} / "
                f"lat={coordinates[0]}, lng={coordinates[1]} / 사유={error}"
            )
            return coordinates

    def _map_for_region(self, region):
        return make_map_bounds(*self._disco_coordinates(region),
                               self.map_width_scale, self.map_height_scale)

    @staticmethod
    def _request_form(filters):
        form = build_disco_form(filters) if filters else DEFAULT_FORM.copy()
        if not any(key == "selectedCategory" for key, _ in form):
            form.append(("selectedCategory", "null"))
        return form

    def _fetch_page(self, base_form, map_values, offset):
        payload = base_form.copy()
        payload.extend((key, str(value)) for key, value in map_values.items())
        payload.extend([
            ("offset", str(offset)),
            ("limit", str(LIST_LIMIT)),
        ])

        self.driver.set_script_timeout(30)
        response = self.driver.execute_async_script(self.browser_fetch_js, payload) or {}
        if not response.get("ok"):
            self._request_error(response.get("error") or "목록 요청 실패")

        result = response.get("json")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("목록 응답에 data 배열이 없습니다.")
        if "has_next" not in result:
            raise ValueError("목록 응답에 has_next가 없습니다.")
        if any(not isinstance(row, dict) or not row.get("pnu") for row in result["data"]):
            raise ValueError("목록에 PNU가 없는 행이 있습니다.")
        return result

    def _fetch_group_advertisements(self, list_rows):
        """목록의 group_key별 광고 전체를 조회합니다."""
        all_rows = []
        seen_group_keys = set()
        script = """
            const done = arguments[arguments.length - 1];
            const payload = arguments[0] || {};
            const params = new URLSearchParams();
            for (const pair of (payload.baseForm || [])) {
                params.append(String(pair[0]), String(pair[1]));
            }
            for (const [key, value] of Object.entries(payload.mapValues || {})) {
                params.append(key, String(value));
            }
            params.set('groupKey', String(payload.groupKey || ''));
            fetch('/sale/v2/detail/', {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: params.toString()
            }).then(async response => {
                const text = await response.text();
                if (!response.ok) {
                    done({ok: false, error: `HTTP ${response.status}: ${text.slice(0, 300)}`});
                    return;
                }
                try { done({ok: true, json: JSON.parse(text)}); }
                catch (error) { done({ok: false, error: `JSON 변환 실패: ${error}`}); }
            }).catch(error => done({ok: false, error: String(error)}));
        """

        for row in list_rows or []:
            group_key = str(row.get("group_key") or row.get("groupKey") or "").strip()
            if not group_key or group_key in seen_group_keys:
                continue
            seen_group_keys.add(group_key)
            if not self._pause(self.request_delay):
                raise InterruptedError("사용자 중단")
            self.driver.set_script_timeout(30)
            response = self.driver.execute_async_script(script, {
                "groupKey": group_key,
                "baseForm": row.get("_base_form") or [],
                "mapValues": row.get("_map_values") or {},
            }) or {}
            if not response.get("ok"):
                self._request_error(response.get("error") or "광고 그룹 조회 실패")
            result = response.get("json")
            rows = result.get("data") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                raise ValueError("광고 그룹 응답에 data 배열이 없습니다.")
            all_rows.extend(row for row in rows if isinstance(row, dict))
        return all_rows

    def _fetch_json(self, url, response_name):
        response = self._json_prefetch_cache.pop(url, None)
        if response is None:
            if not self._pause(self.request_delay):
                raise InterruptedError("사용자 중단")
            self.driver.set_script_timeout(30)
            response = self.driver.execute_async_script(self.get_json_js, url) or {}
        if not response.get("ok"):
            self._request_error(response.get("error") or f"{response_name} 요청 실패")

        return response.get("json")

    def _prefetch_json(self, requests):
        """브라우저 세션 안에서 상세 GET 요청을 설정 개수만큼 동시에 처리합니다."""
        pending = [
            {"url": url, "name": name}
            for url, name in requests
            if url and url not in self._json_prefetch_cache
        ]
        if self.detail_thread_count <= 1 or len(pending) <= 1:
            return
        # 실제 Selenium 세션에서만 브라우저 병렬 요청을 사용합니다.
        if not getattr(self.driver, "session_id", None):
            return
        if not self._pause(self.request_delay):
            raise InterruptedError("사용자 중단")

        try:
            self.driver.set_script_timeout(120)
            response = self.driver.execute_async_script(
                self.get_json_batch_js,
                {"requests": pending, "concurrency": self.detail_thread_count},
            ) or {}
            results = response.get("results")
            if not response.get("ok") or not isinstance(results, list):
                raise RuntimeError(response.get("error") or "동시 상세 요청 실패")
            by_url = {
                str(row.get("url") or ""): row
                for row in results
                if isinstance(row, dict) and row.get("url")
            }
            if len(by_url) != len(pending):
                raise RuntimeError("동시 상세 요청 결과 수가 일치하지 않습니다.")
            self._json_prefetch_cache.update(by_url)
        except (PermissionError, InterruptedError):
            raise
        except Exception as error:
            # 일부 WebDriver 환경에서 배치 스크립트를 지원하지 않으면 기존 순차 조회로 복귀합니다.
            if not self._batch_fallback_logged:
                self.log_signal_func(
                    f"[디스코] 동시 상세 조회를 사용할 수 없어 순차 조회로 전환합니다: {error}"
                )
                self._batch_fallback_logged = True

    @staticmethod
    def _land_history_url(pnu, list_rows):
        url = f"https://data.disco.re/home/get_land_history/?pnu={pnu}"
        first_row = list_rows[0] if list_rows else {}
        lat = first_row.get("lat")
        lng = first_row.get("lng")
        if lat not in (None, "") and lng not in (None, ""):
            url += f"&lng={lng}&lat={lat}"
        return url

    def _core_detail_requests(self, pnu, list_rows):
        return [
            (f"https://data.disco.re/home/land_by_pnu/?pnu={pnu}", "토지정보"),
            (self._land_history_url(pnu, list_rows), "토지이동이력"),
            (f"https://data.disco.re/home/land_price/?pnu={pnu}", "개별공시지가"),
            (f"https://data.disco.re/home/arch_by_pnu/?pnu={pnu}", "건물정보"),
            (self._data_url("home/get_arch_business/", {"p": pnu}), "상가업소정보"),
            (self._data_url("home/house_price/", {"pnu": pnu}), "개별주택공시가격"),
        ]

    @staticmethod
    def _request_error(message):
        if any(code in str(message) for code in ("HTTP 401", "HTTP 403", "HTTP 429")):
            raise PermissionError(f"접근/요청 제한으로 수집을 중단합니다: {message}")
        raise RuntimeError(message)

    @staticmethod
    def _data_url(path, params):
        return f"https://data.disco.re/{path}?{urlencode(params)}"

    @staticmethod
    def _empty_unit_info():
        return {
            "호별정보_동": None,
            "호별정보_층": None,
            "호별정보_호": None,
            "호별정보_대지권 비율": None,
            "호별정보_전유부": [],
        }

    def _fetch_typed_json(self, url, name, expected_type, error_message, extract=None):
        result = self._fetch_json(url, name)
        result = extract(result) if extract else result
        if not isinstance(result, expected_type):
            raise ValueError(error_message)
        return result

    def _fetch_short_info(self, pnu):
        return self._fetch_typed_json(
            f"/common/short_info/?p={pnu}", "기본정보", dict,
            "기본정보 응답이 JSON 객체가 아닙니다.",
        )

    def _fetch_land_info(self, pnu):
        return self._fetch_typed_json(
            f"https://data.disco.re/home/land_by_pnu/?pnu={pnu}", "토지정보", dict,
            "토지정보 응답이 JSON 객체가 아닙니다.",
        )

    def _fetch_land_history(self, pnu, list_rows):
        return self._fetch_typed_json(
            self._land_history_url(pnu, list_rows), "토지이동이력", list,
            "토지이동이력 응답이 JSON 배열이 아닙니다.",
            lambda result: result.get("data") if isinstance(result, dict) else result,
        )

    def _fetch_land_prices(self, pnu):
        return self._fetch_typed_json(
            f"https://data.disco.re/home/land_price/?pnu={pnu}", "개별공시지가", list,
            "개별공시지가 응답이 JSON 배열이 아닙니다.",
        )

    def _fetch_arch_info(self, pnu):
        return self._fetch_typed_json(
            f"https://data.disco.re/home/arch_by_pnu/?pnu={pnu}", "건물정보", dict,
            "건물정보 응답이 JSON 객체가 아닙니다.",
        )

    def _fetch_arch_floors(self, key):
        return self._fetch_typed_json(
            f"https://data.disco.re/home/arch_floor_list/?key={key}", "건축물현황", list,
            "건축물현황 응답이 JSON 배열이 아닙니다.",
        )

    def _fetch_businesses(self, pnu):
        return self._fetch_typed_json(
            self._data_url("home/get_arch_business/", {"p": pnu}),
            "상가업소정보", list, "상가업소정보 응답에 data 배열이 없습니다.",
            lambda result: result.get("data") if isinstance(result, dict) else None,
        )

    def _fetch_house_prices(self, pnu):
        return self._fetch_typed_json(
            self._data_url("home/house_price/", {"pnu": pnu}),
            "개별주택공시가격", list, "개별주택공시가격 응답이 JSON 배열이 아닙니다.",
        )

    def _fetch_first_unit_info(self, pnu):
        """디스코 화면과 같이 첫 동·층·호의 대지권과 전유부를 조회합니다."""
        dong_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_dong_2/", {"p": pnu}),
            "호별 동정보",
        )
        if not isinstance(dong_data, dict):
            raise ValueError("호별 동정보 응답이 JSON 객체가 아닙니다.")

        jeonyu_dongs = dong_data.get("jeonyu") or []
        daeji_dongs = dong_data.get("daeji") or []
        jeonyu_dong = jeonyu_dongs[0] if jeonyu_dongs else ""
        daeji_dong = daeji_dongs[0] if daeji_dongs else ""

        floor_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_floor_2/", {
                "p": pnu,
                "j_d": jeonyu_dong,
                "d_d": daeji_dong,
            }),
            "호별 층정보",
        )
        if not isinstance(floor_data, dict):
            raise ValueError("호별 층정보 응답이 JSON 객체가 아닙니다.")

        jeonyu_floors = floor_data.get("jeonyu") or []
        daeji_floors = floor_data.get("daeji") or []
        if not jeonyu_floors:
            return None
        floor_row = jeonyu_floors[0]
        floor_type = floor_row[0] if len(floor_row) > 0 else ""
        floor = floor_row[1] if len(floor_row) > 1 else ""
        daeji_floor = ""
        if daeji_floors:
            daeji_floor = (
                daeji_floors[0][0]
                if isinstance(daeji_floors[0], (list, tuple))
                else daeji_floors[0]
            )

        ho_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_ho_2/", {
                "p": pnu,
                "jd": jeonyu_dong,
                "dd": daeji_dong,
                "g": floor_type,
                "jf": floor,
                "df": daeji_floor,
            }),
            "호별 호정보",
        )
        if not isinstance(ho_data, dict):
            raise ValueError("호별 호정보 응답이 JSON 객체가 아닙니다.")
        ho_rows = ho_data.get("jeonyu") or []
        if not ho_rows:
            return None
        ho = ho_rows[0][0] if isinstance(ho_rows[0], (list, tuple)) else ho_rows[0]

        parts_result = self._fetch_json(
            self._data_url("home/arch_exclusive_share_list_2/", {
                "p": pnu,
                "d": str(jeonyu_dong).replace("동", ""),
                "t": floor_type,
                "f": floor,
                "h": ho,
            }),
            "전유부",
        )
        parts = parts_result.get("parts") if isinstance(parts_result, dict) else None
        if not isinstance(parts, list):
            raise ValueError("전유부 응답에 parts 배열이 없습니다.")

        rights_result = self._fetch_json(
            self._data_url("home/land_rights_registration/", {
                "p": pnu,
                "d": str(jeonyu_dong).replace("동", ""),
                "f": floor,
                "h": ho,
            }),
            "대지권 비율",
        )
        rights = (
            rights_result.get("land_rights_registration")
            if isinstance(rights_result, dict)
            else None
        )
        rights_text = None
        if isinstance(rights, str) and "/" in rights:
            numerator, denominator = rights.split("/", 1)
            rights_text = f"{denominator}분의 {numerator}"

        return {
            "호별정보_동": jeonyu_dong,
            "호별정보_층": floor,
            "호별정보_호": ho,
            "호별정보_대지권 비율": rights_text,
            "호별정보_전유부": _korean_exclusive_parts(parts),
        }

    def _fetch_first_apart_prices(self, pnu):
        """디스코 화면과 같이 첫 동·층·호의 공동주택공시가격을 조회합니다."""
        dongs = self._fetch_json(
            self._data_url("home/apart_price_info_dong/", {"p": pnu}),
            "공동주택 동정보",
        )
        if not isinstance(dongs, list) or not dongs:
            return []
        dong = dongs[0]

        floors = self._fetch_json(
            self._data_url("home/apart_price_info_floor/", {"p": pnu, "d": dong}),
            "공동주택 층정보",
        )
        if not isinstance(floors, list) or not floors:
            return []
        floor = floors[0][0] if isinstance(floors[0], (list, tuple)) else floors[0]

        hos = self._fetch_json(
            self._data_url("home/apart_price_info_ho/", {
                "p": pnu,
                "d": dong,
                "f": floor,
            }),
            "공동주택 호정보",
        )
        if not isinstance(hos, list) or not hos:
            return []
        ho = hos[0][0] if isinstance(hos[0], (list, tuple)) else hos[0]

        prices = self._fetch_json(
            self._data_url("apart_price/", {
                "p": pnu,
                "d": dong,
                "f": floor,
                "h": ho,
            }),
            "공동주택공시가격",
        )
        if not isinstance(prices, list):
            raise ValueError("공동주택공시가격 응답이 JSON 배열이 아닙니다.")
        return prices

    @staticmethod
    def _korean_short_info(pnu, result):
        """short_info 응답을 화면/최종 표의 부모_자식 키로 변환합니다."""
        address = result.get("address")
        sido, sigungu, eup_myeon_dong = _address_parts(address)
        completed_date = _date_text(result.get("const_year"))
        recent_deal_date = _date_text(result.get("realp_date"))
        recent_price = result.get("price")

        return {
            "PNU": str(pnu),
            "기본_시도": sido,
            "기본_시군구": sigungu,
            "기본_읍면동": eup_myeon_dong,
            "기본_주소(지번)": address,
            "기본_주소(도로명)": result.get("road_address"),
            "기본_준공": completed_date,
            "실거래가_등록된 매물수": result.get("count"),
            # short_info의 price는 이미 만원 단위이므로 표시문자열로 바꾸지 않습니다.
            "실거래가_최근실거래가": _number_value(recent_price),
            "실거래가_최근실거래가 일자": recent_deal_date,
            "토지 정보_면적": result.get("land_area"),
            "토지 정보_지목": result.get("purpose"),
            "토지 정보_용도지역": result.get("use_district"),
            "토지 정보_소유구분": result.get("owner_gbn"),
            "건물 정보_건물이름": result.get("name"),
            "건물 정보_대지면적": result.get("land_area"),
            "건물 정보_연면적": result.get("floor_area"),
            "건물 정보_지상": result.get("ground_floor"),
            "건물 정보_지하": result.get("basement_floor"),
            "건물 정보_세대 수_가구": result.get("family"),
            "건물 정보_세대 수_호수": result.get("ho"),
        }

    def _naver_check_running(self):
        if not self.running:
            raise InterruptedError('사용자 중단')

    def _naver_event_pause(self, minimum, maximum):
        """네이버 UI 이벤트 사이에 짧고 일정하지 않은 간격을 둡니다."""
        if not self._pause(random.uniform(minimum, maximum)):
            raise InterruptedError('사용자 중단')

    def _naver_open_window(self):
        """기존 Selenium 세션에서 네이버 지도 전용 창을 한 번만 생성합니다."""
        self._naver_check_running()
        if self._naver_window_handle in self.driver.window_handles:
            self.driver.switch_to.window(self._naver_window_handle)
            return False
        self.driver.switch_to.new_window('window')
        self._naver_window_handle = self.driver.current_window_handle
        # 문서가 바뀌어도 앱의 첫 네트워크 요청보다 먼저 후킹합니다.
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                                    {'source': self.naver_subway_hook_js})
        self.driver.get('https://map.naver.com/')
        self.log_signal_func('[디스코] 도보 필터용 네이버 지도 창을 열었습니다.')
        return True

    def _naver_clear_hook(self):
        self.driver.execute_script(self.naver_subway_hook_js)
        self.driver.execute_script('''
            window.__discoSubwayHook.generation += 1;
            window.__discoSubwayHook.rows = [];
        ''')

    def _naver_wait_hook(self, path, timeout=20, query=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._naver_check_running()
            if query is not None:
                for element in self.driver.find_elements(By.CSS_SELECTOR, '.notice_title'):
                    if not element.is_displayed():
                        continue
                    notice = str(element.text or '').strip()
                    if query in notice and '검색 결과가 없습니다' in notice:
                        raise LookupError(f'네이버 지도에 검색 결과가 없습니다: {query}')

            rows = self.driver.execute_script(
                'return window.__discoSubwayHook ? window.__discoSubwayHook.rows : [];') or []
            for row in reversed(rows):
                url = str(row.get('url') or '')
                if path not in url:
                    continue
                if query is not None:
                    params = parse_qs(urlsplit(url).query)
                    response_query = (
                            params.get('query', [''])[0]
                            or params.get('queryString', [''])[0]
                    )
                    if response_query and response_query != query:
                        continue
                status = row.get('status')
                if status in (401, 403, 429):
                    raise PermissionError(f'네이버 요청 제한/인증 확인 필요 (HTTP {status})')
                if status != 200:
                    raise RuntimeError(f'네이버 {path} 조회 실패 (HTTP {status})')
                if not isinstance(row.get('data'), dict):
                    raise ValueError(f'네이버 {path} JSON 응답 형식 오류')
                return row
            self._pause(0.15)
        raise TimeoutError(f'네이버 네트워크 후킹 시간 초과: {path}')

    def _naver_search_input(self):
        """네이버 지도 상단의 현재 표시 중인 통합 검색 입력창을 찾습니다."""
        def search_input(driver):
            self._naver_check_running()
            for element in driver.find_elements(
                    By.CSS_SELECTOR, 'input.input_search[role="combobox"]'):
                # 길찾기 화면의 출발지/도착지 입력창은 통합 검색창으로 보지 않습니다.
                direction_parent = element.find_elements(
                    By.XPATH,
                    './ancestor::*[contains(concat(" ", normalize-space(@class), " "), '
                    '" search_input_box_wrap ")]'
                )
                if (not direction_parent
                        and element.is_displayed()
                        and element.is_enabled()):
                    return element
            return False
        return WebDriverWait(self.driver, 20, poll_frequency=0.2).until(search_input)

    def _naver_prepare_search_home(self, force=False):
        """사용 가능한 통합 검색창이 있으면 재사용하고, 없을 때만 지도 홈을 엽니다."""
        self._naver_check_running()
        if not force:
            for element in self.driver.find_elements(
                    By.CSS_SELECTOR, 'input.input_search[role="combobox"]'):
                direction_parent = element.find_elements(
                    By.XPATH,
                    './ancestor::*[contains(concat(" ", normalize-space(@class), " "), '
                    '" search_input_box_wrap ")]'
                )
                if (not direction_parent
                        and element.is_displayed()
                        and element.is_enabled()):
                    return element

        self.driver.get('https://map.naver.com/')
        WebDriverWait(self.driver, 20, poll_frequency=0.2).until(
            lambda driver: driver.execute_script('return document.readyState') == 'complete'
        )
        return self._naver_search_input()

    def _naver_submit_search(self, query):
        """검색창에 직접 문자열을 입력하고 Enter를 눌러 발생한 응답을 후킹합니다."""
        self._naver_check_running()
        if not self._pause(max(self.request_delay, random.uniform(0.2, 0.35))):
            raise InterruptedError('사용자 중단')
        element = self._naver_search_input()
        element.click()
        self._naver_event_pause(0.15, 0.25)
        element.send_keys(Keys.CONTROL, 'a')
        self._naver_event_pause(0.08, 0.15)
        element.send_keys(Keys.BACKSPACE)
        self._naver_event_pause(0.12, 0.2)
        self._naver_clear_hook()
        element.send_keys(query)
        # 검색어 입력 직후 Enter를 누르면 React 입력 상태가 간헐적으로 반영되지 않습니다.
        self._naver_event_pause(0.4, 0.6)
        element.send_keys(Keys.ENTER)
        data = self._naver_wait_hook(
            '/p/api/search/allSearch', timeout=12, query=query
        )['data']
        if not _naver_search_has_results(data):
            raise LookupError(f'네이버 지도에 검색 결과가 없습니다: {query}')
        # Enter 직후 화면 갱신이 끝나기 전에 다음 검색을 넣지 않고, 요청 간격도
        # 매번 같지 않게 하여 짧은 시간에 요청이 몰리지 않도록 합니다.
        if not self._pause(random.uniform(0.7, 1.0)):
            raise InterruptedError('사용자 중단')
        return data

    def _naver_open_directions_panel(self):
        """상단 내비게이션의 '길찾기' 버튼을 눌러 입력 화면을 엽니다."""
        def directions_button(driver):
            self._naver_check_running()
            selectors = (
                '//button[contains(concat(" ", normalize-space(@class), " "), " btn_navbar ")]'
                '[.//span[normalize-space()="길찾기"]]',
                '//button[.//span[normalize-space()="길찾기"]]',
            )
            for selector in selectors:
                for element in driver.find_elements(By.XPATH, selector):
                    if element.is_displayed() and element.is_enabled():
                        return element
            return False

        button = WebDriverWait(self.driver, 20, poll_frequency=0.2).until(directions_button)
        self._naver_event_pause(0.5, 0.8)
        button.click()
        self._naver_event_pause(0.8, 1.2)
        self._naver_direction_input('start')
        self._naver_direction_input('goal')

    def _naver_direction_input(self, point):
        """길찾기의 출발지(start) 또는 도착지(goal) 입력창을 찾습니다."""
        if point not in ('start', 'goal'):
            raise ValueError(f'지원하지 않는 길찾기 입력 구분: {point}')

        selector = f'.search_input_box_wrap.{point} input.input_search[role="combobox"]'

        def direction_input(driver):
            self._naver_check_running()
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if element.is_displayed() and element.is_enabled():
                    return element
            return False

        return WebDriverWait(self.driver, 20, poll_frequency=0.2).until(direction_input)

    def _naver_set_direction_point(self, point, query):
        """길찾기 입력창에 값을 넣고 검색 목록의 첫 결과를 Enter로 확정합니다."""
        self._naver_check_running()
        element = self._naver_direction_input(point)
        self._naver_event_pause(0.1, 0.2)
        element.click()
        self._naver_event_pause(0.08, 0.15)
        element.send_keys(Keys.CONTROL, 'a')
        self._naver_event_pause(0.05, 0.1)
        element.send_keys(Keys.BACKSPACE)
        self._naver_event_pause(0.08, 0.15)
        element.send_keys(query)
        # 자동완성 요청이 시작되기 전에 Enter를 보내지 않습니다.
        self._naver_event_pause(0.3, 0.5)

        # 자동완성 목록이 열리면 첫 결과를 명시적으로 선택합니다. 목록이 늦게
        # 열리거나 없는 경우에는 Enter로 네이버 자체 검색/확정 동작을 수행합니다.
        deadline = time.monotonic() + 1.0
        expanded = False
        while time.monotonic() < deadline:
            self._naver_check_running()
            try:
                expanded = element.get_attribute('aria-expanded') == 'true'
            except Exception:
                element = self._naver_direction_input(point)
            if expanded:
                break
            self._pause(0.15)
        if expanded:
            element.send_keys(Keys.ARROW_DOWN)
            self._naver_event_pause(0.08, 0.15)
        element.send_keys(Keys.ENTER)
        # 출발지/도착지 확정 후 React 상태가 반영되기 전에 다음 입력으로 넘어가지 않습니다.
        if not self._pause(max(self.request_delay, random.uniform(0.35, 0.55))):
            raise InterruptedError('사용자 중단')

    def _naver_select_walking(self):
        """길찾기 이동수단을 도보로 선택합니다."""
        def walking_button(driver):
            self._naver_check_running()
            for element in driver.find_elements(
                    By.XPATH, '//button[@role="tab"][.//span[normalize-space()="도보"]]'):
                if element.is_displayed() and element.is_enabled():
                    return element
            return False

        button = WebDriverWait(self.driver, 20, poll_frequency=0.2).until(walking_button)
        if button.get_attribute('aria-selected') != 'true':
            self._naver_event_pause(0.4, 0.7)
            button.click()
            self._naver_event_pause(0.6, 0.9)

    def _naver_request_walking_route(self):
        """길찾기를 클릭하고, 응답이 없을 때만 버튼을 다시 찾아 한 번 재시도합니다."""
        def search_button(driver):
            self._naver_check_running()
            for element in driver.find_elements(
                    By.CSS_SELECTOR, '.search_btn_area button.btn_direction.search'):
                if element.is_displayed() and element.is_enabled():
                    return element
            return False

        for attempt in range(2):
            self._naver_clear_hook()
            try:
                button = WebDriverWait(
                    self.driver, 5, poll_frequency=0.2
                ).until(search_button)
                self.driver.execute_script(
                    'arguments[0].scrollIntoView({block: "center", inline: "center"});',
                    button,
                )
                self._naver_event_pause(0.6, 1.0)
                button.click()
            except InterruptedError:
                raise
            except Exception as error:
                if attempt == 0:
                    self.log_signal_func(
                        f'[디스코] 네이버 길찾기 첫 클릭 실패, 버튼 재검색 후 재시도: {error}'
                    )
                    if not self._pause(0.4):
                        raise InterruptedError('사용자 중단')
                    continue
                raise

            try:
                # 첫 클릭이 실제로 적용되지 않은 경우를 오래 기다리지 않습니다.
                wait_seconds = 4 if attempt == 0 else 6
                route_payload = self._naver_wait_hook(
                    '/p/api/directions/walk', timeout=wait_seconds
                )['data']
                # 응답 직후 화면을 닫지 않고 실제 길찾기 결과가 잠시 보이게 합니다.
                self._naver_event_pause(1.5, 2.0)
                return route_payload
            except TimeoutError:
                if attempt == 0:
                    self.log_signal_func(
                        '[디스코] 네이버 길찾기 응답 없음, 버튼 재검색 후 한 번 더 클릭합니다.'
                    )
                    if not self._pause(0.4):
                        raise InterruptedError('사용자 중단')
                    continue
                raise TimeoutError('네이버 길찾기 버튼을 2회 클릭했지만 도보 응답이 없습니다.')

        raise TimeoutError('네이버 길찾기 재시도에 실패했습니다.')

    def _naver_lookup_route_once(self, address, force_home=False):
        """네이버 UI에서 주소→근처 지하철역→도보 길찾기를 한 번 수행합니다."""
        self._naver_prepare_search_home(force=force_home)
        self._naver_submit_search(address)
        station_payload = self._naver_submit_search('근처지하철역')
        fallback_station = _naver_first_subway_name(station_payload)
        if not fallback_station:
            raise LookupError('네이버 지도에서 주변 지하철역 검색 결과를 찾지 못했습니다.')

        self._naver_open_directions_panel()
        self._naver_select_walking()
        # 지하철역에서 매물까지 걷는 방향으로 입력합니다.
        self._naver_set_direction_point('start', fallback_station)
        self._naver_set_direction_point('goal', address)
        route_payload = self._naver_request_walking_route()
        result = _naver_walking_result(route_payload, fallback_station)

        # 주소 검색 뒤에도 이전 지도 위치가 남으면 수백 분 거리의 엉뚱한 역이
        # 반환될 수 있습니다. 그런 결과는 저장하지 않고 홈에서 다시 조회합니다.
        walking_seconds = result.get('_subway_walking_seconds')
        if isinstance(walking_seconds, (int, float)) and walking_seconds >= 180 * 60:
            raise TimeoutError(
                '네이버 지도 위치가 갱신되지 않은 비정상 도보 결과: '
                f'{result.get("nearest_subway_station")} '
                f'{result.get("subway_walking_minute")}분'
            )
        return result

    def _naver_reset_search_misses(self):
        self._naver_consecutive_search_misses = 0
        self._naver_last_missed_address = None

    def _naver_lookup_route_with_recovery(self, address):
        """현재 화면 재검색 후 실패하면 지도 홈에서 한 번 더 처음부터 수행합니다."""
        last_error = None
        try:
            return self._naver_lookup_route_once(address)
        except NAVER_TRANSIENT_ERRORS as transient_error:
            # 네트워크 후킹 또는 Selenium 화면 대기가 늦어진 경우 지도 홈에서
            # 주소 검색부터 전체 과정을 다시 시작합니다.
            last_error = transient_error
            error_text = str(transient_error).strip() or type(transient_error).__name__
            self.log_signal_func(
                '[디스코] 네이버 화면/네트워크 응답 지연, '
                f'지도 홈에서 처음부터 재시도: {address} / {error_text}'
            )
            self._naver_event_pause(1.0, 1.5)
            try:
                return self._naver_lookup_route_once(address, force_home=True)
            except NAVER_RECOVERABLE_ERRORS as home_error:
                raise home_error from last_error
        except LookupError as first_error:
            last_error = first_error
            self.log_signal_func(
                f'[디스코] 네이버 조회 실패, 현재 화면에서 1회 재검색: {address}'
            )
            self._naver_event_pause(2.0, 3.0)

        try:
            return self._naver_lookup_route_once(address)
        except NAVER_RECOVERABLE_ERRORS as retry_error:
            last_error = retry_error
            self.log_signal_func(
                f'[디스코] 네이버 재검색 실패, 지도 홈에서 처음부터 재시도: {address}'
            )
            self._naver_event_pause(1.0, 1.5)

        try:
            return self._naver_lookup_route_once(address, force_home=True)
        except NAVER_RECOVERABLE_ERRORS as home_error:
            raise home_error from last_error

    def _lookup_naver_subway(self, pnu, item):
        if pnu in self._naver_subway_cache:
            return self._naver_subway_cache[pnu]

        jibun_address = str(item.get('기본_주소(지번)') or '').strip()
        road_address = str(item.get('기본_주소(도로명)') or '').strip()
        addresses = []
        for candidate in (jibun_address, road_address):
            if candidate and candidate not in addresses:
                addresses.append(candidate)
        if not addresses:
            raise ValueError('디스코 매물 주소가 없습니다.')

        address = addresses[0]
        cooldown_applied = False
        previous_handle = self.driver.current_window_handle
        try:
            self._naver_open_window()
            try:
                value = self._naver_lookup_route_with_recovery(address)
            except NAVER_RECOVERABLE_ERRORS as primary_error:
                last_error = primary_error
                value = None

                # 지번 주소가 네이버에 없고 도로명 주소만 등록된 경우를 한 번 더
                # 확인합니다. 앞에서 홈 재시도까지 했으므로 도로명은 1회만 요청합니다.
                if isinstance(primary_error, LookupError) and len(addresses) > 1:
                    alternate = addresses[1]
                    self.log_signal_func(
                        f'[디스코] 네이버 도로명 주소로 대체 검색: {alternate}'
                    )
                    self._naver_event_pause(1.0, 1.5)
                    try:
                        value = self._naver_lookup_route_once(
                            alternate, force_home=True
                        )
                        address = alternate
                    except NAVER_RECOVERABLE_ERRORS as alternate_error:
                        last_error = alternate_error

                if value is None:
                    # 현재 화면 재검색과 홈 재시도가 모두 실패했으므로 약 10초간
                    # 요청을 멈춥니다. 길찾기 응답 누락이면 홈에서 마지막으로 재시도합니다.
                    cooldown = random.uniform(9.0, 11.0)
                    if isinstance(last_error, NAVER_TRANSIENT_ERRORS):
                        self.log_signal_func(
                            '[디스코] 네이버 길찾기 응답이 계속 없어 '
                            f'{cooldown:.1f}초 후 홈에서 마지막으로 재시도합니다: {address}'
                        )
                    else:
                        self.log_signal_func(
                            '[디스코] 네이버 조회가 계속 실패하여 '
                            f'{cooldown:.1f}초 쉬고 다음 매물로 진행합니다: {address}'
                        )
                    if not self._pause(cooldown):
                        raise InterruptedError('사용자 중단')
                    cooldown_applied = True

                    if isinstance(last_error, NAVER_TRANSIENT_ERRORS):
                        try:
                            value = self._naver_lookup_route_once(
                                addresses[0], force_home=True
                            )
                            address = addresses[0]
                        except NAVER_RECOVERABLE_ERRORS as final_error:
                            last_error = final_error

                    if value is None:
                        if address != self._naver_last_missed_address:
                            self._naver_consecutive_search_misses += 1
                        self._naver_last_missed_address = address

                        # 충분한 재시도와 휴식 후에도 서로 다른 주소가 3건 연속 실패하면
                        # 개별 주소 문제가 아닌 일시 조회 제한으로 판단합니다.
                        if self._naver_consecutive_search_misses >= 3:
                            raise PermissionError(
                                '네이버 지도 조회가 서로 다른 주소에서 3건 연속 실패했습니다. '
                                '정상 매물의 대량 오제외를 막기 위해 작업을 중단합니다. '
                                f'마지막 응답: {last_error}'
                            )

                        # 실패 결과는 캐시하지 않아 다른 즐겨찾기 조건에서 다시 평가합니다.
                        error_text = str(last_error).strip() or type(last_error).__name__
                        return (None, error_text)

            self._naver_reset_search_misses()
            result = (value, None)
            # 성공 결과만 캐시합니다. 일시적인 빈 검색 응답은 저장하지 않습니다.
            self._naver_subway_cache[pnu] = result
            return result
        finally:
            # 디스코의 후속 목록/상세 요청은 반드시 원래 창에서 실행합니다.
            if previous_handle in self.driver.window_handles:
                self.driver.switch_to.window(previous_handle)
            # 매물 사이의 간격을 두어 네이버 검색 요청이 짧은 시간에 몰리지 않게 합니다.
            if self.running and not cooldown_applied:
                self._pause(random.uniform(2.0, 3.0))

    def _detail_step(self, pnu, label, action, fallback=None, error_prefix=None):
        """상세 하위 API의 공통 성공/부분실패 처리를 수행합니다."""
        try:
            action()
            return 1
        except PermissionError:
            raise
        except Exception as error:
            self._row_errors.append(
                f"{error_prefix}: {error}" if error_prefix else str(error)
            )
            if fallback:
                fallback()
            self.log_signal_func(f"[디스코] {label} 실패 (PNU={pnu}): {error}")
            return 0

    def _collect_arch_details(self, pnu, item):
        arch_info = self._fetch_arch_info(pnu)
        item.update(_korean_arch_info(arch_info))
        arch_rows = arch_info.get("title_section") or arch_info.get("overall_title_section") or []
        arch_keys = {
            str(row.get("a1") or "").strip()
            for row in arch_rows if isinstance(row, dict) and row.get("a1")
        }
        self._prefetch_json([
            (f"https://data.disco.re/home/arch_floor_list/?key={key}", "건축물현황")
            for key in arch_keys
        ])
        floors = []
        for key in arch_keys:
            try:
                floors.extend(_korean_arch_floors(self._fetch_arch_floors(key)))
            except PermissionError:
                raise
            except Exception as error:
                self._row_errors.append(str(error))
                self.log_signal_func(
                    f"[디스코] 건축물현황 실패 (PNU={pnu}, key={key}): {error}"
                )
        item["건물 정보_건축물현황"] = floors

    def _major_repair_selected(self):
        return any(
            col.get("code", "").startswith(("major_repair_", "violation_building_"))
            or any(word in str(col.get("value", "")) for word in ("대수선", "위반건축물"))
            for col in self.selected_column_defs
        )

    def _collect_short_infos(self, progress_start=0, progress_end=1000000):
        rows_by_pnu = {}
        missing_pnu = 0
        skipped_pnus = set()
        for row in self.list_items:
            # 다른 즐겨찾기의 도보 조건으로 수집한 행을 섞지 않습니다.
            if row.get("_subway_limit") != self._active_subway_limit:
                continue
            pnu = str(row.get("pnu") or "").strip()
            if pnu in self._seen_pnus:
                continue
            if not pnu:
                missing_pnu += 1
                continue
            # 목록에는 필지 PNU(19자리)가 아닌 법정동/지역코드(10자리)가
            # 포함될 수 있습니다. 상세조회 대상이 아니므로 실패가 아닌 SKIP 처리합니다.
            if len(pnu) != 19 or not pnu.isdigit():
                skipped_pnus.add(pnu)
                self._seen_pnus.add(pnu)
                continue
            rows_by_pnu.setdefault(pnu, []).append(row)

        total = len(rows_by_pnu)
        self.log_signal_func(
            f"[디스코] 상세 요약 조회 시작: 대상 PNU {total}건"
            + (f", SKIP {len(skipped_pnus)}건" if skipped_pnus else "")
            + (f", PNU 없는 목록 {missing_pnu}건" if missing_pnu else "")
        )
        for pnu in sorted(skipped_pnus):
            self.log_signal_func(
                f"[디스코] 상세 SKIP (상세 대상이 아닌 지역코드): {pnu}"
            )

        success = 0
        filtered_count = 0
        progress_value = int(progress_start)

        def update_detail_progress(done):
            nonlocal progress_value
            if total <= 0:
                target = int(progress_end)
            else:
                ratio = min(1.0, max(0.0, done / total))
                target = int(progress_start + (progress_end - progress_start) * ratio)
            self.progress_signal.emit(progress_value, target)
            progress_value = target

        if total == 0:
            update_detail_progress(0)

        for index, (pnu, list_rows) in enumerate(rows_by_pnu.items(), 1):
            if not self.running:
                break

            # 기본정보를 먼저 만들고, 뒤에서 조회한 토지 상세정보로 같은 컬럼을 덮어씁니다.
            self._row_errors = []
            started_at = now_text()
            item = self._korean_short_info(pnu, {})
            try:
                group_ad_rows = self._fetch_group_advertisements(list_rows)
                item.update(_korean_advertisement_summary(group_ad_rows or list_rows))
            except (PermissionError, InterruptedError):
                raise
            except Exception as error:
                # 그룹 상세 실패 시에도 기존 목록값으로 결과를 보존합니다.
                item.update(_korean_advertisement_summary(list_rows))
                self.log_signal_func(
                    f"[디스코] 광고 그룹 조회 실패, 목록값 사용 (PNU={pnu}): {error}"
                )
            item["검색 키워드"] = next(
                (
                    str(row.get("_search_keyword") or "").strip()
                    for row in list_rows
                    if str(row.get("_search_keyword") or "").strip()
                ),
                None,
            )
            fetched = 0
            short_info = {}

            try:
                short_info = self._fetch_short_info(pnu)
                item.update(self._korean_short_info(pnu, short_info))
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                self._seen_pnus.add(pnu)
                self.log_signal_func(
                    f"[디스코] 기본정보 실패 (PNU={pnu}): {error} / DB 저장하지 않음"
                )
                # 기본정보가 없으면 주소/PNU 검증이 되지 않은 행이므로
                # 나머지 상세 API도 호출하지 않고 완전히 제외합니다.
                update_detail_progress(index)
                continue

            # 도보 설정이 꺼져 있으면 네이버 창 생성/검색/요청을 전혀 수행하지 않습니다.
            if self._active_subway_limit is not None:
                try:
                    walk, reason = self._lookup_naver_subway(pnu, item)
                except (PermissionError, InterruptedError):
                    raise
                except Exception as error:
                    self._subway_lookup_failures += 1
                    self.log_signal_func(f"[디스코] 도보 조회 실패로 제외: PNU={pnu} / {error}")
                    update_detail_progress(index)
                    continue
                walking_seconds = walk.get('_subway_walking_seconds') if walk else None
                over_limit = (
                        walk is None
                        or not isinstance(walking_seconds, int)
                        or walking_seconds > self._active_subway_limit * 60
                )
                if over_limit:
                    filtered_count += 1
                    self._subway_filtered_count += 1
                    if walk is None:
                        reason = reason or '네이버 추천 도보 경로가 없습니다.'
                    else:
                        reason = reason or (f'{walk["nearest_subway_station"]} 도보 '
                                            f'{walk["subway_walking_minute"]}분 > '
                                            f'설정 {self._active_subway_limit}분')
                    self.log_signal_func(f"[디스코] 도보 조건 제외: PNU={pnu} / {reason}")
                    # 제외 PNU는 완료로 기록하지 않아 다른 즐겨찾기 조건에서 재평가합니다.
                    update_detail_progress(index)
                    continue
                item["가까운 지하철역"] = walk["nearest_subway_station"]
                item["도보거리(단위 분)"] = walk["subway_walking_minute"]
                self.log_signal_func(f'[디스코] 도보 조건 통과: PNU={pnu} / '
                                     f'{walk["nearest_subway_station"]} 도보 {walk["subway_walking_minute"]}분 '
                                     f'({walk["_subway_walking_distance_meter"]}m, '
                                     f'{walk["_subway_walking_seconds"]}초 / '
                                     f'설정 {self._active_subway_limit}분 이내)')

            self._prefetch_json(self._core_detail_requests(pnu, list_rows))
            fetched += self._detail_step(
                pnu, "토지정보",
                lambda: item.update(_korean_land_info(self._fetch_land_info(pnu))),
            )
            fetched += self._detail_step(
                pnu, "토지이동이력",
                lambda: item.__setitem__(
                    "토지 이동(변동) 사유",
                    _korean_land_history(self._fetch_land_history(pnu, list_rows)),
                ),
                lambda: item.__setitem__("토지 이동(변동) 사유", []),
            )
            fetched += self._detail_step(
                pnu, "개별공시지가",
                lambda: item.update(_korean_land_prices(self._fetch_land_prices(pnu))),
                lambda: item.update(_korean_land_prices([])),
            )
            fetched += self._detail_step(
                pnu, "건물정보", lambda: self._collect_arch_details(pnu, item),
                lambda: item.__setitem__("건물 정보_건축물현황", []),
            )
            fetched += self._detail_step(
                pnu, "상가업소정보",
                lambda: item.__setitem__(
                    "상가업소정보", _korean_businesses(self._fetch_businesses(pnu))
                ),
                lambda: item.__setitem__("상가업소정보", []),
            )
            fetched += self._detail_step(
                pnu, "개별주택공시가격",
                lambda: item.update(_korean_house_prices(self._fetch_house_prices(pnu))),
                lambda: item.update(_korean_house_prices([])),
            )

            is_ziphap = str(short_info.get("ziphap") or "").strip() == "1"
            if is_ziphap:
                fetched += self._detail_step(
                    pnu, "호별정보",
                    lambda: item.update(self._fetch_first_unit_info(pnu) or self._empty_unit_info()),
                    lambda: item.update(self._empty_unit_info()),
                )
                fetched += self._detail_step(
                    pnu, "공동주택공시가격",
                    lambda: item.update(_korean_apart_prices(self._fetch_first_apart_prices(pnu))),
                    lambda: item.update(_korean_apart_prices([])),
                )
            else:
                item.update(self._empty_unit_info())
                item.update(_korean_apart_prices([]))

            if self._major_repair_selected():
                fetched += self._detail_step(
                    pnu, "대수선 정보",
                    lambda: item.update(self._fetch_major_repair_info(pnu) or {}),
                    error_prefix="대수선",
                )

            if not self.running:
                break
            row_status = "SUCCESS" if fetched and not self._row_errors else ("PARTIAL" if fetched else "FAIL")
            db_item = {
                column["code"]: item.get(column["value"])
                for column in self.selected_column_defs
            }
            stored = self.db_repository.insert_detail(
                db_item,
                row_status=row_status,
                row_error_message="; ".join(self._row_errors) or None,
                row_start_at=started_at,
                row_end_at=now_text(),
            )
            if not stored:
                self._row_errors.append("detail DB 저장 실패")
                self.job_error = "detail DB 저장 실패"
            self._seen_pnus.add(pnu)
            selected_item = {c["value"]: item.get(c["value"]) for c in self.selected_column_defs}
            self.detail_items.append(selected_item)
            if row_status == "SUCCESS":
                success += 1
            if self.detail_log_yn:
                self.log_signal_func("[디스코] 상세: " + json.dumps(selected_item, ensure_ascii=False))
            self.log_signal_func(f"[디스코] DB 저장 {index}/{total} / PNU={pnu} / {row_status}")
            update_detail_progress(index)

        self.log_signal_func(
            f"[디스코] 상세 요약 조회 완료: 성공 {success}/{total}건"
        )
        if filtered_count:
            self.log_signal_func(f"[디스코] 도보 조건 제외 {filtered_count}건 (오류 건수와 별도)")
        return success, total - filtered_count

    def _collect_region(self, region, filters):
        address = " ".join(self._region_key(region))
        map_values = self._map_for_region(region)
        base_form = self._request_form(filters)
        self.log_signal_func(
            f"[디스코] {address} 지도 좌표: "
            + json.dumps(map_values, ensure_ascii=False)
        )

        offset = 0
        region_count = 0
        region_keys = set()
        self._current_stat = {"bounds": map_values, "total": None, "count": 0}
        previous_page_keys = None
        while self.running:
            result = self._fetch_page(base_form, map_values, offset)
            rows = result["data"]
            page_keys = [
                str(row.get("suid") or row.get("uuid") or row.get("refer_uuid")
                    or row.get("u") or json.dumps(row, sort_keys=True))
                for row in rows
            ]
            if previous_page_keys == page_keys and rows:
                raise RuntimeError("같은 목록 페이지가 반복되어 중단했습니다.")
            previous_page_keys = page_keys
            if result.get("total_count") is not None:
                self._current_stat["total"] = int(result["total_count"])

            self.log_signal_func(
                f"[디스코] {address} / offset={offset}, 조회={len(rows)}건, "
                f"total_count={result.get('total_count')}, "
                f"has_next={result.get('has_next')}"
            )
            for key, row in zip(page_keys, rows):
                region_keys.add(key)
                self._current_stat["count"] = len(region_keys)
                seen_key = (key, self._active_subway_limit)
                if seen_key in self._seen_items:
                    continue
                self._seen_items.add(seen_key)
                detail_row = dict(row)
                detail_row["_search_keyword"] = address
                detail_row["_subway_limit"] = self._active_subway_limit
                detail_row["_base_form"] = base_form
                detail_row["_map_values"] = map_values
                self.list_items.append(detail_row)
                region_count += 1

            has_next = result.get("has_next") is True or str(result.get("has_next")).lower() == "true"
            if not rows and has_next:
                raise RuntimeError("has_next=true인데 목록이 비어 있습니다.")
            if not has_next:
                break
            offset += LIST_LIMIT
            if not self._pause(self.page_delay):
                break

        return region_count

    def _jobs(self):
        favorites = self.setting_region_filter_favorite or []
        checked = [
            favorite for favorite in favorites
            if isinstance(favorite, dict) and favorite.get("checked")
        ]
        if checked:
            return checked
        return [{
            "regions": self.region or [],
            "filters": self.setting_detail_all_style or [],
        }]

    def _fetch_major_repair_info(self, pnu):
        """웹서버(https://goodbye772.com/archhub/major-repair)를 호출하여 대수선 정보를 조회합니다."""
        if not self.major_repair_master_api_key:
            self.log_signal_func("[디스코] master_api_key 설정이 없어 대수선 조회를 건너뜁니다.")
            return {}

        url = self.major_repair_server_url or "https://goodbye772.com/archhub/major-repair"
        response = requests.get(
            url, headers={"X-API-KEY": self.major_repair_master_api_key},
            params={"pnu": pnu}, timeout=10,
        )
        if response.status_code != 200:
            raise RuntimeError(f"대수선 API 오류 (HTTP {response.status_code}): {response.text}")

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("대수선 API 응답이 JSON 객체가 아닙니다.")
        keys = (
            "건물 정보_대수선조회상태", "건물 정보_대수선조회메시지", "건물 정보_대수선여부",
            "건물 정보_대수선건수", "건물 정보_최근대수선사용승인일", "건물 정보_대수선이력",
            "건물 정보_대수선조회일시", "건물 정보_대수선데이터기준일시",
            "건물 정보_위반건축물여부", "건물 정보_위반건축물내용",
        )
        result = {key: data.get(key) for key in keys}
        history = result["건물 정보_대수선이력"]
        if isinstance(history, (list, dict)):
            result["건물 정보_대수선이력"] = json.dumps(history, ensure_ascii=False)
        return result

    def main(self) -> bool:
        tasks = [
            (region, job.get("filters") or [])
            for job in self._jobs()
            for region in (job.get("regions") or [])
        ]
        if not tasks:
            self.log_signal_func("[디스코] 전체세팅에서 지역을 하나 이상 선택해주세요.")
            self.job_status, self.job_error = "FAIL", "선택 지역 없음"
            self.cleanup()
            return False

        completed = 0
        processed_tasks = 0
        try:
            self.driver.get("https://www.disco.re/")
            WebDriverWait(self.driver, 20).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

            for index, (region, filters) in enumerate(tasks, 1):
                if not self.running:
                    break
                self._active_subway_limit = _subway_filter_limit(filters)
                self.log_signal_func(
                    "[디스코] 도보 필터: " + (f"{self._active_subway_limit}분 이내" if self._active_subway_limit is not None
                                       else "미사용 (네이버 조회 생략)")
                )
                address = " ".join(self._region_key(region))
                region_start = int((index - 1) / len(tasks) * 1000000)
                detail_start = int((index - 0.9) / len(tasks) * 1000000)
                region_end = int(index / len(tasks) * 1000000)
                self.log_signal_func(f"[디스코] 지역 {index}/{len(tasks)}: {address}")
                self._current_stat = {"bounds": {}, "total": None, "count": 0}
                region_status, region_error = "SUCCESS", None
                try:
                    count = self._collect_region(region, filters)
                    completed += 1
                    self.log_signal_func(
                        f"[디스코] 지역 완료 {count}건 / 전체 누적 {len(self.list_items)}건"
                    )
                except Exception as error:
                    if isinstance(error, PermissionError):
                        raise
                    region_status, region_error = "FAIL", str(error)
                    self.log_signal_func(f"[디스코] 지역 실패 ({address}): {error}")
                stat = self._current_stat
                # 각 지역이 끝날 때 저장하므로 다음 지역 실패에도 이전 결과는 보존됩니다.
                self.progress_signal.emit(region_start, detail_start)
                detail_success, detail_total = self._collect_short_infos(
                    detail_start, region_end
                )
                if not self.running:
                    region_status, region_error = "STOP", "사용자 중단"

                # 디스코의 total_count는 화면 마커/그룹 수가 섞여 실제 상세 대상과
                # 일치하지 않습니다. 통계는 중복 및 SKIP을 제거한 유효 PNU 기준입니다.
                stat_matched = (
                        region_status == "SUCCESS"
                        and detail_success == detail_total
                )
                self.db_repository.insert_stat({
                    "task_index": index,
                    "city": region.get("시도"),
                    "division": region.get("시군구"),
                    "sector": region.get("읍면동"),
                    "totalCount": detail_total,
                    "crawledCount": detail_success,
                    "trueFalse": "T" if stat_matched else "F",
                    "status": region_status,
                    "error_message": region_error,
                    "map_bounds": json.dumps(stat["bounds"], ensure_ascii=False),
                })
                self.log_signal_func(
                    f"[디스코] 지역 통계: 전체={detail_total}, "
                    f"수집={detail_success}, 일치={'T' if stat_matched else 'F'} "
                    f"(중복·SKIP 제외)"
                )
                processed_tasks = index
                if index < len(tasks) and not self._pause(self.region_delay):
                    break

            self.log_signal_func(
                f"[디스코] 목록 수집 완료: {completed}/{len(tasks)} 지역, "
                f"중복 제외 {len(self.list_items)}건"
            )
            if not self.running:
                self.job_status, self.job_error = "STOP", "사용자 중단"
            elif completed != len(tasks) or self.db_repository.fail_count or self._subway_lookup_failures:
                self.job_status, self.job_error = "FAIL", "일부 지역 또는 상세 조회 실패(행/지역 오류 확인)"
            else:
                self.job_status = "SUCCESS"
            if self.running and processed_tasks == len(tasks):
                self.progress_signal.emit(1000000, 1000000)
            return self.job_status == "SUCCESS"
        except Exception as error:
            self.job_status = "FAIL" if self.running else "STOP"
            self.job_error = str(error)
            self.log_signal_func(f"[디스코] 작업 종료: {self.job_error}")
            return False
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if self.db_repository is not None:
            try:
                if self.job_status == "RUNNING":
                    self.job_status = "FAIL" if self.running else "STOP"
                    self.job_error = self.job_error or "작업 미완료"
                self.db_repository.set_job_result(self.job_status, self.job_error)
                self.db_repository.finish_job()
                if self.auto_save_yn:
                    from src.utils.excel_utils import ExcelUtils

                    labels, rows = self.db_repository.get_excel_data()
                    if rows:
                        header_groups = [
                            [part.strip() for part in str(label or "").split("_") if part.strip()]
                            or [str(label or "")]
                            for label in labels
                        ]
                        excel = ExcelUtils(self.log_signal_func)
                        saved = excel.save_db_rows_to_excel(
                            excel_filename=f"disco_re_{self.db_repository.job_id}.xlsx",
                            row_list=rows,
                            columns=labels,
                            folder_path=self.folder_path,
                            sub_dir="output",
                            header_groups=header_groups,
                            merge_headers=self.excel_header_merge_yn,
                        )
                        if not saved:
                            self.log_signal_func("[디스코] 엑셀 저장 실패. DB 데이터는 유지됩니다.")
            except Exception as error:
                self.log_signal_func(f"[디스코] 작업 마감/엑셀 저장 실패: {error}")
            finally:
                self.db_repository.close()
        self._naver_window_handle = None
        self._naver_subway_cache.clear()
        # 네이버 전용 창도 같은 Selenium 세션이므로 quit()에서 함께 종료됩니다.
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        if self.file_driver is not None:
            try:
                self.file_driver.close()
            except Exception:
                pass
            self.file_driver = None

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self.running = False
        # UI 스레드에서 SQLite 연결을 닫지 않습니다. main의 finally에서 마감합니다.

    def destroy(self) -> None:
        self.cleanup()
        self.progress_end_signal.emit()
