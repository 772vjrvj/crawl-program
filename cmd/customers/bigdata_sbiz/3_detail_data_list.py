# -*- coding: utf-8 -*-
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from pyproj import Transformer


INPUT_JSON = "lat_lon_list.json"
OUTPUT_JSON = "gu_grouped_stats.json"

BASE_URL = "https://bigdata.sbiz.or.kr/gis/api"

MAP_LEVEL = 3
SUBSTR = 8
BZZN_TYPE = 1

# 사용자가 실제로 잡은 bbox 예시 기준
# minXAxis=199255, maxXAxis=204767 => width=5512
# minYAxis=445925, maxYAxis=448401 => height=2476
BBOX_WIDTH = 5512
BBOX_HEIGHT = 2476

TIMEOUT = 30

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Referer": "https://bigdata.sbiz.or.kr/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    # 필요하면 추가
    # "Cookie": "여기에_쿠키",
}


API_CONFIGS = [
    {
        "name": "업소",
        "path": "/getMapRadsStorCnt.json",
        "extra_params": {},
        "value_field": "storeCnt",
    },
    {
        "name": "유동인구",
        "path": "/getMapRadsPopCnt.json",
        "extra_params": {},
        "value_field": "popCnt",
    },
    {
        "name": "직장인구",
        "path": "/getMapRadsWrcpplCnt.json",
        "extra_params": {},
        "value_field": "wrcpplCnt",
    },
    {
        "name": "주거인구",
        "path": "/getMapRadsWholPpltnCnt.json",
        "extra_params": {},
        "value_field": "wholPpltnCnt",
    },
    {
        "name": "치과수",
        "path": "/getMapRadsStorCnt.json",
        "extra_params": {"upjongCd": "Q10210"},
        "value_field": "storeCnt",
    },
]


transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:5181",
    always_xy=True,
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_adm_name(value: Any) -> str:
    return normalize_text(value).replace(" ", "")


def parse_count(value: Any) -> Optional[int]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", "")

    try:
        return int(float(text))
    except Exception:
        return None


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("lat_lon_list.json은 객체 배열(list) 형식이어야 합니다.")

    return data


def save_json_file(file_path: Path, data: Dict[str, List[Dict[str, Any]]]) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def get_item_lat_lon(item: Dict[str, Any]) -> Tuple[float, float]:
    """
    입력 객체에서 위도/경도 추출
    - "위도", "경도" 우선
    - 없으면 "lat", "lon"도 허용
    """
    lat = item.get("위도")
    lon = item.get("경도")

    if lat in ("", None):
        lat = item.get("lat")
    if lon in ("", None):
        lon = item.get("lon")

    if lat in ("", None) or lon in ("", None):
        raise ValueError(f"위도/경도 누락: {item}")

    try:
        return float(lat), float(lon)
    except Exception:
        raise ValueError(f"위도/경도 숫자 변환 실패: lat={lat}, lon={lon}")


def lonlat_to_epsg5181(lon: float, lat: float) -> Tuple[int, int]:
    """
    반드시 (lon, lat) 순서로 넣어야 함
    """
    x, y = transformer.transform(lon, lat)
    center_x = math.floor(x)
    center_y = math.floor(y)
    return center_x, center_y


def build_bbox(center_x: int, center_y: int) -> Dict[str, int]:
    half_width = BBOX_WIDTH // 2
    half_height = BBOX_HEIGHT // 2

    return {
        "minXAxis": center_x - half_width,
        "maxXAxis": center_x + half_width,
        "minYAxis": center_y - half_height,
        "maxYAxis": center_y + half_height,
    }


def build_common_params(bbox: Dict[str, int]) -> Dict[str, Any]:
    return {
        "mapLevel": MAP_LEVEL,
        "substr": SUBSTR,
        "minXAxis": bbox["minXAxis"],
        "maxXAxis": bbox["maxXAxis"],
        "minYAxis": bbox["minYAxis"],
        "maxYAxis": bbox["maxYAxis"],
        "bzznType": BZZN_TYPE,
    }


def fetch_api_array(
        session: requests.Session,
        url: str,
        params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    response = session.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"응답이 배열이 아닙니다. url={response.url}")

    return data


def find_first_matching_value(
        rows: List[Dict[str, Any]],
        target_adm_nm: str,
        value_field: str,
) -> Optional[int]:
    target_key = normalize_adm_name(target_adm_nm)

    for row in rows:
        if not isinstance(row, dict):
            continue

        adm_nm = normalize_adm_name(row.get("admNm"))
        if not adm_nm:
            continue

        if adm_nm == target_key:
            return parse_count(row.get(value_field))

    return None


def fetch_single_metric(
        item: Dict[str, Any],
        bbox: Dict[str, int],
        config: Dict[str, Any],
) -> Tuple[str, Optional[int]]:
    api_name = config["name"]
    path = config["path"]
    value_field = config["value_field"]

    url = BASE_URL + path
    params = build_common_params(bbox)
    params.update(config.get("extra_params", {}))

    dong_name = normalize_text(item.get("읍면동"))
    session = create_session()

    try:
        rows = fetch_api_array(session, url, params)
        value = find_first_matching_value(rows, dong_name, value_field)
        return api_name, value
    finally:
        session.close()


def fetch_metrics_multithread(
        item: Dict[str, Any],
        bbox: Dict[str, int],
) -> Dict[str, Optional[int]]:
    result = {
        "업소": None,
        "유동인구": None,
        "직장인구": None,
        "주거인구": None,
        "치과수": None,
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {}

        for config in API_CONFIGS:
            future = executor.submit(fetch_single_metric, item, bbox, config)
            future_map[future] = config["name"]

        for future in as_completed(future_map):
            api_name = future_map[future]

            try:
                result_name, value = future.result()
                result[result_name] = value
            except Exception as e:
                print(f"[ERROR] {api_name} 호출 실패 - {item.get('시군구')} {item.get('읍면동')} / {e}")
                result[api_name] = None

    return result


def process_one(item: Dict[str, Any]) -> Dict[str, Any]:
    new_item = dict(item)

    lat, lon = get_item_lat_lon(item)

    # 중요: 변환 시 lon, lat 순서
    center_x, center_y = lonlat_to_epsg5181(lon=lon, lat=lat)
    bbox = build_bbox(center_x, center_y)

    metrics = fetch_metrics_multithread(item, bbox)

    new_item["위도"] = lat
    new_item["경도"] = lon
    new_item["업소"] = metrics.get("업소")
    new_item["유동인구"] = metrics.get("유동인구")
    new_item["직장인구"] = metrics.get("직장인구")
    new_item["주거인구"] = metrics.get("주거인구")
    new_item["치과수"] = metrics.get("치과수")

    # 디버깅 필요하면 사용
    new_item["centerX"] = center_x
    new_item["centerY"] = center_y
    new_item["minXAxis"] = bbox["minXAxis"]
    new_item["maxXAxis"] = bbox["maxXAxis"]
    new_item["minYAxis"] = bbox["minYAxis"]
    new_item["maxYAxis"] = bbox["maxYAxis"]

    return new_item


def group_by_gu(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        gu_name = normalize_text(item.get("시군구"))

        if gu_name not in grouped:
            grouped[gu_name] = []

        grouped[gu_name].append(item)

    return grouped


def print_summary(grouped: Dict[str, List[Dict[str, Any]]]) -> None:
    total = 0

    for gu_name, items in grouped.items():
        total += len(items)
        print(f"[구 요약] {gu_name}: {len(items)}개")

    print(f"\n총 처리 건수: {total}개")


def main() -> None:
    base_dir = Path.cwd()
    input_path = base_dir / INPUT_JSON
    output_path = base_dir / OUTPUT_JSON

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {input_path}")

    source_list = load_json_file(input_path)
    print(f"[로드 완료] {len(source_list)}개")

    processed_list: List[Dict[str, Any]] = []

    for idx, item in enumerate(source_list, start=1):
        try:
            processed = process_one(item)
            processed_list.append(processed)

            print(
                f"[{idx}/{len(source_list)}] 완료 - "
                f"{processed.get('시군구')} {processed.get('읍면동')} / "
                f"업소={processed.get('업소')}, "
                f"유동인구={processed.get('유동인구')}, "
                f"직장인구={processed.get('직장인구')}, "
                f"주거인구={processed.get('주거인구')}, "
                f"치과수={processed.get('치과수')}"
            )

        except Exception as e:
            failed_item = dict(item)
            failed_item["업소"] = None
            failed_item["유동인구"] = None
            failed_item["직장인구"] = None
            failed_item["주거인구"] = None
            failed_item["치과수"] = None
            failed_item["error"] = str(e)
            processed_list.append(failed_item)

            print(
                f"[{idx}/{len(source_list)}] 실패 - "
                f"{item.get('시군구')} {item.get('읍면동')} / {e}"
            )

    grouped = group_by_gu(processed_list)
    save_json_file(output_path, grouped)

    print_summary(grouped)
    print(f"저장 완료: {output_path}")


if __name__ == "__main__":
    main()