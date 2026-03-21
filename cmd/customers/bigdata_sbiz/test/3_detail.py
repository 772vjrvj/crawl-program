import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from pyproj import Transformer


class SbizHotplaceBatchRunner:
    def __init__(
            self,
            *,
            output_json_path: str = "sbiz_hotplace_result.json",
            map_level: int = 3,
            substr: int = 8,
            upjong_cd: str = "Q10210",
            bzzn_type: int = 1,
            bbox_width: int = 5512,
            bbox_height: int = 2476,
            timeout: int = 20,
    ) -> None:
        self.output_json_path = Path(output_json_path)

        self.map_level = map_level
        self.substr = substr
        self.upjong_cd = upjong_cd
        self.bzzn_type = bzzn_type

        # 사용자가 실제로 잡은 예시 bbox 기준
        # minXAxis=199255, maxXAxis=204767 => width=5512
        # minYAxis=445925, maxYAxis=448401 => height=2476
        self.bbox_width = bbox_width
        self.bbox_height = bbox_height

        self.timeout = timeout

        self.transformer = Transformer.from_crs(
            "EPSG:4326",
            "EPSG:5181",
            always_xy=True,
        )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://bigdata.sbiz.or.kr/",
            }
        )

    def parse_lat_lon(self, item: Dict[str, Any]) -> Tuple[float, float]:
        lat = item.get("lat")
        lon = item.get("lon")

        if lat in ("", None) or lon in ("", None):
            raise ValueError(f"lat/lon 누락: {item}")

        try:
            return float(lat), float(lon)
        except Exception:
            raise ValueError(f"lat/lon 숫자 변환 실패: lat={lat}, lon={lon}")

    def lonlat_to_epsg5181(self, lon: float, lat: float) -> Tuple[int, int]:
        x, y = self.transformer.transform(lon, lat)

        # 사이트 JS 흐름에 맞춰 floor 처리
        center_x = math.floor(x)
        center_y = math.floor(y)

        return center_x, center_y

    def build_bbox(self, center_x: int, center_y: int) -> Dict[str, int]:
        half_width = self.bbox_width // 2
        half_height = self.bbox_height // 2

        return {
            "minXAxis": center_x - half_width,
            "maxXAxis": center_x + half_width,
            "minYAxis": center_y - half_height,
            "maxYAxis": center_y + half_height,
        }

    def call_sbiz_api(self, bbox: Dict[str, int]) -> Dict[str, Any]:
        url = "https://bigdata.sbiz.or.kr/gis/api/getMapRadsStorCnt.json"

        params = {
            "mapLevel": self.map_level,
            "substr": self.substr,
            "minXAxis": bbox["minXAxis"],
            "maxXAxis": bbox["maxXAxis"],
            "minYAxis": bbox["minYAxis"],
            "maxYAxis": bbox["maxYAxis"],
            "upjongCd": self.upjong_cd,
            "bzznType": self.bzzn_type,
        }

        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()

        try:
            data = resp.json()
        except Exception:
            data = resp.text

        return {
            "request_url": resp.url,
            "status_code": resp.status_code,
            "response": data,
        }

    def process_one(self, item: Dict[str, Any]) -> Dict[str, Any]:
        lat, lon = self.parse_lat_lon(item)
        center_x, center_y = self.lonlat_to_epsg5181(lon=lon, lat=lat)
        bbox = self.build_bbox(center_x, center_y)
        api_result = self.call_sbiz_api(bbox)

        return {
            "input": {
                "name": item.get("name", ""),
                "lat": lat,
                "lon": lon,
            },
            "coord": {
                "lat": lat,
                "lon": lon,
                "centerX": center_x,
                "centerY": center_y,
            },
            "bbox": bbox,
            "api": api_result,
        }

    def run(self, target_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for idx, item in enumerate(target_items, start=1):
            try:
                result = self.process_one(item)
                result["success"] = True
                print(
                    f"[{idx}/{len(target_items)}] 성공 - "
                    f"name={item.get('name', '')}, lat={item.get('lat')}, lon={item.get('lon')}"
                )
            except Exception as e:
                result = {
                    "success": False,
                    "input": {
                        "name": item.get("name", ""),
                        "lat": item.get("lat"),
                        "lon": item.get("lon"),
                    },
                    "error": str(e),
                }
                print(
                    f"[{idx}/{len(target_items)}] 실패 - "
                    f"name={item.get('name', '')}, lat={item.get('lat')}, lon={item.get('lon')} / {str(e)}"
                )

            results.append(result)

        with self.output_json_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n저장 완료: {self.output_json_path.resolve()}")
        return results


def main() -> None:
    # 여기 배열에 lat, lon 만 넣으면 됩니다.
    target_items = [
        {
            "name": "테스트2",
            "lat": 37.500859552111955,
            "lon": 127.03549814805179,
        },
    ]

    runner = SbizHotplaceBatchRunner(
        output_json_path="sbiz_hotplace_result.json",
        map_level=3,
        substr=8,
        upjong_cd="Q10210",
        bzzn_type=1,
        bbox_width=5512,
        bbox_height=2476,
        timeout=20,
    )

    runner.run(target_items)


if __name__ == "__main__":
    main()