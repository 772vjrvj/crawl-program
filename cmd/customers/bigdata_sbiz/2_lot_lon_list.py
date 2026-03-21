# -*- coding: utf-8 -*-
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


INPUT_JSON = "data.json"
OUTPUT_JSON = "lat_lon_list.json"
TARGET_URL = "https://bigdata.sbiz.or.kr/#/hotplace/gis"
TARGET_API = "https://dapi.kakao.com/v2/local/search/address.json"


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("data.json은 객체 배열(list) 형식이어야 합니다.")

    return data


def save_json_file(file_path: Path, data: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_keyword(item: Dict[str, Any]) -> str:
    sido = str(item.get("시도", "")).strip()
    sigungu = str(item.get("시군구", "")).strip()
    eupmyeondong = str(item.get("읍면동", "")).strip()

    parts = [sido, sigungu, eupmyeondong]
    parts = [x for x in parts if x]
    return " ".join(parts)


def extract_lat_lon_from_kakao_response(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    documents = data.get("documents", [])
    if not documents:
        return None, None

    first = documents[0]

    lon = (
            first.get("x")
            or (first.get("address") or {}).get("x")
            or (first.get("road_address") or {}).get("x")
    )

    lat = (
            first.get("y")
            or (first.get("address") or {}).get("y")
            or (first.get("road_address") or {}).get("y")
    )

    if lat is not None:
        lat = str(lat).strip()
    if lon is not None:
        lon = str(lon).strip()

    return lat, lon


def search_lat_lon(page, frame, keyword: str) -> Tuple[Optional[str], Optional[str]]:
    search_input = frame.locator("#searchAddress")
    search_btn = frame.locator("#searchBtn")

    search_input.wait_for(state="visible", timeout=30000)

    # 입력창 초기화
    search_input.click()
    search_input.fill("")
    page.wait_for_timeout(200)

    # 키워드 입력
    search_input.type(keyword, delay=80)
    page.wait_for_timeout(500)

    # 1차: 검색 버튼 클릭으로 응답 대기
    try:
        with page.expect_response(
                lambda response: TARGET_API in response.url and response.status == 200,
                timeout=15000
        ) as response_info:
            search_btn.click()

        response = response_info.value
        data = response.json()
        return extract_lat_lon_from_kakao_response(data)

    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        print(f"[WARN] 버튼 클릭 응답 처리 실패 - {keyword}: {e}")

    # 2차: 엔터로 재시도
    try:
        with page.expect_response(
                lambda response: TARGET_API in response.url and response.status == 200,
                timeout=15000
        ) as response_info:
            search_input.press("Enter")

        response = response_info.value
        data = response.json()
        return extract_lat_lon_from_kakao_response(data)

    except PlaywrightTimeoutError:
        print(f"[WARN] 응답 타임아웃 - {keyword}")
        return None, None
    except Exception as e:
        print(f"[WARN] 엔터 응답 처리 실패 - {keyword}: {e}")
        return None, None


def main() -> None:
    base_dir = Path.cwd()
    input_path = base_dir / INPUT_JSON
    output_path = base_dir / OUTPUT_JSON

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {input_path}")

    source_list = load_json_file(input_path)
    result_list: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=300
        )

        context = browser.new_context(
            permissions=["geolocation"],
            geolocation={"latitude": 37.5665, "longitude": 126.9780},
            viewport={"width": 1400, "height": 900}
        )

        page = context.new_page()

        try:
            page.goto(TARGET_URL, wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)

            frame = page.frame_locator("#iframe")

            # 검색창 한번 미리 확인
            frame.locator("#searchAddress").wait_for(state="visible", timeout=30000)

            total_count = len(source_list)

            for idx, item in enumerate(source_list, start=1):
                new_item = dict(item)
                keyword = build_keyword(item)

                print(f"[{idx}/{total_count}] 검색어: {keyword}")

                lat = None
                lon = None

                try:
                    lat, lon = search_lat_lon(page, frame, keyword)
                except Exception as e:
                    print(f"[ERROR] 검색 중 예외 발생 - {keyword}: {e}")

                new_item["위도"] = lat
                new_item["경도"] = lon

                result_list.append(new_item)

                print(f"    -> 위도: {lat}, 경도: {lon}")

                # 중간 저장
                if idx % 20 == 0:
                    save_json_file(output_path, result_list)
                    print(f"    -> 중간 저장 완료: {output_path}")

                # 너무 빠르면 꼬일 수 있어서 약간 대기
                page.wait_for_timeout(700)

            save_json_file(output_path, result_list)
            print(f"\n최종 저장 완료: {output_path}")
            print(f"총 {len(result_list)}건 처리 완료")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()