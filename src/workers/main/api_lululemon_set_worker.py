from __future__ import annotations

import os
import re
import json
import time
import random
import sys
from decimal import Decimal
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiLululemonSetLoadWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.url_list: List[str] = []
        self.running: bool = True

        self.company_name: str = "lululemon_option"
        self.site_name: str = "lululemon_option"

        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0

        self.api_client = APIClient(use_cache=False)

        self.columns: List[str] = ["컬러", "사이즈", "옵션가", "재고수량", "관리코드", "사용여부"]

        base_dir = self.get_base_dir()
        self.out_dir: str = os.path.join(base_dir, "output_lululemon")
        os.makedirs(self.out_dir, exist_ok=True)

        self._size_rank: Dict[str, int] = {}

    # -----------------------------------------------------
    # 초기화
    # -----------------------------------------------------
    def init(self) -> bool:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        self.out_dir = os.path.join(self.get_base_dir(), "output_lululemon")
        os.makedirs(self.out_dir, exist_ok=True)

        self.log_signal.emit(f"[DEBUG] cwd = {os.getcwd()}")
        self.log_signal.emit(f"[DEBUG] base_dir = {self.get_base_dir()}")
        self.log_signal.emit(f"[DEBUG] out_dir = {self.out_dir}")
        return True

    # -----------------------------------------------------
    # 메인
    # -----------------------------------------------------
    def main(self) -> bool:
        try:
            self.log_signal.emit("크롤링 시작")

            self.url_list = [
                str(row[k]).strip()
                for row in self.excel_data_list
                for k in row.keys()
                if k.lower() == "url" and str(row.get(k, "")).strip()
            ]

            self.total_cnt = len(self.url_list)
            self.current_cnt = 0
            self.before_pro_value = 0

            self.log_signal.emit(f"[INFO] URL 갯수: {self.total_cnt}")

            self.call_product_list()
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 전체 실행 중 예외 발생: {e}")
            return False

    # -----------------------------------------------------
    # URL 목록 처리
    # -----------------------------------------------------
    def call_product_list(self) -> None:
        if not self.url_list:
            self.log_signal.emit("[SKIP] URL 없음")
            return

        for num, url in enumerate(self.url_list, start=1):
            if not self.running:
                break

            self.current_cnt += 1
            self.log_signal.emit(f"[{num}/{self.total_cnt}] 처리 시작: {url}")

            options, product_name = self.product_api_data(url)

            if options:
                self.log_signal.emit(f"[옵션 미리보기] 총 {len(options)}건 / 첫번째 옵션: {options[0]}")
            else:
                self.log_signal.emit("[옵션 미리보기] 옵션 없음 (0건)")
                self.log_signal.emit(f"[SKIP] 저장할 옵션 없음: {url}")
                self.update_progress()
                time.sleep(random.uniform(1, 2))
                continue

            filename = f"{self.safe_filename(product_name)}_{self.now_stamp()}.xls"
            fullpath = os.path.join(self.out_dir, filename)

            self.log_signal.emit(f"[DEBUG] 저장 시도 경로: {fullpath}")

            try:
                self.excel_driver.save_obj_list_to_excel(
                    filename=fullpath,
                    obj_list=options,
                    columns=self.columns,
                    sheet_name="Sheet1"
                )

                if os.path.exists(fullpath):
                    self.log_signal.emit(f"({num}/{self.total_cnt}) 저장완료: {fullpath}")
                else:
                    self.log_signal.emit(f"[저장실패] 파일이 생성되지 않음: {fullpath}")

            except Exception as e:
                self.log_signal.emit(f"[저장실패] {fullpath} / {e}")

            self.update_progress()
            time.sleep(random.uniform(2, 4))

    def update_progress(self) -> None:
        pro_value = (self.current_cnt / self.total_cnt) * 1000000 if self.total_cnt else 1000000
        self.progress_signal.emit(self.before_pro_value, pro_value)
        self.before_pro_value = pro_value

    # -----------------------------------------------------
    # 단일 상품 처리
    # -----------------------------------------------------
    def product_api_data(self, url: str) -> Tuple[List[Dict[str, Any]], str]:
        try:
            soup = self.fetch_product_soup(url)
            next_data = self.extract_next_data(soup)

            size_order = self.extract_all_size_order_from_next_data(next_data)
            self._size_rank = self.build_size_rank(size_order)

            variants = self.extract_variants(next_data, soup)
            if not variants:
                self.log_signal.emit(f"[SKIP] variants 없음: {url}")
                return [], "product"

            product_name = self.extract_product_name(variants, next_data)

            rows = []
            for v in variants:
                row = self.normalize_variant(v)
                if row:
                    rows.append(row)

            if not rows:
                self.log_signal.emit(f"[SKIP] 정규화된 옵션 rows 없음: {url}")
                return [], product_name

            min_price = self.find_min_price(rows)
            self.sort_rows_by_color_and_size(rows)

            out = []
            for r in rows:
                price_val = self.to_decimal(r.get("price"))
                diff = price_val - min_price if min_price is not None and price_val is not None else Decimal("0")
                opt = int(diff) * 1000 if diff > 0 else 0

                out.append({
                    "컬러": self.shorten_color(str(r.get("color", ""))),
                    "사이즈": str(r.get("size", "")),
                    "옵션가": opt,
                    "재고수량": 5 if self.is_in_stock(r.get("availability", "")) else 0,
                    "관리코드": "",
                    "사용여부": "Y",
                })

            return out, product_name

        except Exception as e:
            self.log_signal.emit(f"[SKIP] 처리 실패: {url} / {e}")
            return [], "product"

    # -----------------------------------------------------
    # HTML 가져오기
    # -----------------------------------------------------
    def fetch_product_soup(self, url: str) -> BeautifulSoup:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        referer = origin + "/"
        path = u.path + (("?" + u.query) if u.query else "")

        headers: Dict[str, str] = {
            "authority": u.netloc,
            "method": "GET",
            "path": path,
            "scheme": u.scheme,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "max-age=0",
            "priority": "u=0, i",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
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
                "Chrome/143.0.0.0 Safari/537.36"
            ),
            "host": u.netloc,
            "origin": origin,
            "referer": referer,
        }

        resp = self.api_client.get(url, headers=headers)
        return BeautifulSoup(resp, "html.parser")

    # -----------------------------------------------------
    # __NEXT_DATA__ 추출
    # -----------------------------------------------------
    def extract_next_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        sc = soup.find("script", id="__NEXT_DATA__")
        text = sc.string if sc else ""
        if not text:
            self.log_signal.emit("[DEBUG] __NEXT_DATA__ 없음")
            return {}

        try:
            data = json.loads(text)
            self.log_signal.emit("[DEBUG] __NEXT_DATA__ 파싱 성공")
            return data or {}
        except Exception as e:
            self.log_signal.emit(f"[DEBUG] __NEXT_DATA__ 파싱 실패: {e}")
            return {}

    # -----------------------------------------------------
    # __NEXT_DATA__ 에서 allSize 순서 추출 ['0', '2', '4', '6', '8', '10', '12', '14', '16', '18', '20']
    # -----------------------------------------------------
    def extract_all_size_order_from_next_data(self, next_data: Dict[str, Any]) -> List[str]:
        result: List[str] = []

        for candidate in self.find_all_values_by_key(next_data, "allSize"):
            for item in candidate:
                size_text = str(
                    item.get("size") or ""
                ).strip()
                if size_text and size_text not in result:
                    result.append(size_text)

        if result:
            self.log_signal.emit(f"[DEBUG] allSize 추출: {result}")
        else:
            self.log_signal.emit("[DEBUG] allSize 추출 실패")

        return result

    # -----------------------------------------------------
    # variants 추출
    # -----------------------------------------------------
    def extract_variants(self, next_data: Dict[str, Any], soup: BeautifulSoup) -> List[Dict[str, Any]]:
        variants = self.extract_variants_from_next_data(next_data)
        if variants:
            self.log_signal.emit(f"[DEBUG] __NEXT_DATA__ variants 추출 성공: {len(variants)}건")
            return variants

        variants = self.extract_variants_from_ld_json(soup)
        if variants:
            self.log_signal.emit(f"[DEBUG] ld+json variants 추출 성공: {len(variants)}건")
            return variants

        self.log_signal.emit("[DEBUG] variants 추출 실패")
        return []

    def extract_variants_from_next_data(self, next_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        best: List[Dict[str, Any]] = []

        for candidate in self.find_all_values_by_key(next_data, "variants"):
            normalized = [x for x in candidate if x]
            if len(normalized) > len(best):
                best = normalized

        return best

    def extract_variants_from_ld_json(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        for sc in soup.find_all("script", type="application/ld+json"):
            text = sc.string or ""
            if not text:
                continue

            try:
                data = json.loads(text)
            except Exception:
                continue

            objs = data if isinstance(data, list) else [data]

            for obj in objs:
                if obj.get("@type") == "ProductGroup" and obj.get("hasVariant"):
                    return obj.get("hasVariant") or []

        return []

    # -----------------------------------------------------
    # 상품명 추출
    # -----------------------------------------------------
    def extract_product_name(self, variants: List[Dict[str, Any]], next_data: Dict[str, Any]) -> str:
        for nm in self.find_all_values_by_key(next_data, "name"):
            text = str(nm).strip()
            if len(text) >= 3:
                return self.clean_product_name(text)

        for v in variants:
            nm = str(v.get("name", "")).strip()
            if nm:
                return self.clean_product_name(nm)

        return "product"

    def clean_product_name(self, name: str) -> str:
        parts = [p.strip() for p in name.split(" - ") if p.strip()]
        return parts[0] if parts else (name.strip() or "product")

    # -----------------------------------------------------
    # variant 정규화
    # -----------------------------------------------------
    def normalize_variant(self, v: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        color = self.pick_first_text(
            v.get("color"),
            v.get("colour"),
            self.deep_get(v, ["attributes", "color"]),
            self.deep_get(v, ["attributes", "colour"]),
        )

        size = self.pick_first_text(
            v.get("size"),
            v.get("displaySize"),
            self.deep_get(v, ["attributes", "size"]),
            self.deep_get(v, ["attributes", "displaySize"]),
        )

        name = str(v.get("name", "")).strip()
        if name and (not color or not size):
            parsed_color, parsed_size = self.parse_color_size_from_name(name)
            color = color or parsed_color
            size = size or parsed_size

        offers = v.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        price_currency = self.pick_first_text(
            offers.get("priceCurrency"),
            v.get("priceCurrency"),
            self.deep_get(v, ["pricing", "currencyCode"]),
            "CAD",
        )

        price = self.pick_first_text(
            offers.get("price"),
            v.get("price"),
            self.deep_get(v, ["pricing", "price"]),
            self.deep_get(v, ["priceInfo", "price"]),
        )

        availability = self.pick_first_text(
            offers.get("availability"),
            v.get("availability"),
            self.deep_get(v, ["inventory", "availability"]),
            self.deep_get(v, ["inventory", "status"]),
        )

        if not color and not size and not price:
            return None

        return {
            "color": color,
            "size": size,
            "priceCurrency": price_currency,
            "price": price,
            "availability": availability,
        }

    # -----------------------------------------------------
    # 최소가
    # -----------------------------------------------------
    def find_min_price(self, rows: List[Dict[str, Any]]) -> Optional[Decimal]:
        prices = [self.to_decimal(r.get("price")) for r in rows]
        prices = [p for p in prices if p is not None]
        return min(prices) if prices else None

    def to_decimal(self, value: Any) -> Optional[Decimal]:
        text = str(value or "").replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except Exception:
            return None

    # -----------------------------------------------------
    # 재고 판별
    # -----------------------------------------------------
    def is_in_stock(self, availability: Any) -> bool:
        text = str(availability or "").strip().lower()
        return "instock" in text or text in {"available", "in_stock", "in stock", "available_now"}

    # -----------------------------------------------------
    # rows 정렬
    # -----------------------------------------------------
    def sort_rows_by_color_and_size(self, rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            color = str(r.get("color", "")).strip()
            size = str(r.get("size", "")).strip()

            r["_sort_color"] = color.lower()
            r["_size_order"] = self._size_rank.get(size, self.guess_size_rank(size))
            r["_sort_size_text"] = size.lower()

        rows.sort(key=self.sort_key_with_cached_order)

        for r in rows:
            r.pop("_sort_color", None)
            r.pop("_size_order", None)
            r.pop("_sort_size_text", None)

    def sort_key_with_cached_order(self, row: Dict[str, Any]) -> Tuple[str, int, str]:
        return (
            str(row.get("_sort_color", "")),
            int(row.get("_size_order", 9999)),
            str(row.get("_sort_size_text", "")),
        )
    # {'0': 0, '10': 5, '12': 6, '14': 7, '16': 8, '18': 9, '2': 1, '20': 10, '4': 2, '6': 3, '8': 4} 순서 매김
    def build_size_rank(self, size_order: List[str]) -> Dict[str, int]:
        rank: Dict[str, int] = {}
        for idx, s in enumerate(size_order):
            key = str(s).strip()
            if key and key not in rank:
                rank[key] = idx
        return rank

    def guess_size_rank(self, size: str) -> int:
        s = str(size or "").strip().upper()

        base_rank = {
            "XXXS": 1,
            "XXS": 2,
            "XS": 3,
            "S": 4,
            "M": 5,
            "L": 6,
            "XL": 7,
            "XXL": 8,
            "1X": 9,
            "2X": 10,
            "3X": 11,
            "4X": 12,
        }

        if s in base_rank:
            return base_rank[s]

        m = re.match(r"^(\d+(?:\.\d+)?)$", s)
        if m:
            return 100 + int(float(m.group(1)) * 10)

        m = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Z]+)$", s)
        if m:
            return 200 + int(float(m.group(1)) * 10)

        return 9999

    # -----------------------------------------------------
    # 이름에서 color/size 추출
    # -----------------------------------------------------
    def parse_color_size_from_name(self, name: str) -> Tuple[str, str]:
        parts = [p.strip() for p in name.split(" - ") if p.strip()]
        if len(parts) >= 3:
            return parts[-2], parts[-1]
        if len(parts) >= 2:
            return "", parts[-1]
        return "", ""

    # -----------------------------------------------------
    # 컬러명 25자 제한 축약
    # -----------------------------------------------------
    def shorten_color(self, color: str) -> str:
        color = color.strip()
        if len(color) <= 25:
            return color

        parts = color.split()
        if not parts:
            return color[:25]

        short_name = parts[0] + " " + "".join(p[0].upper() for p in parts[1:] if p)
        return short_name[:25]

    # -----------------------------------------------------
    # 파일명 안전 처리
    # -----------------------------------------------------
    def safe_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
        return (name or "product")[:80]

    # -----------------------------------------------------
    # yyyyMMdd_HHmmss
    # -----------------------------------------------------
    def now_stamp(self) -> str:
        return time.strftime("%Y%m%d_%H%M%S")

    # -----------------------------------------------------
    # 경로 기준
    # -----------------------------------------------------
    def get_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.getcwd()

    # -----------------------------------------------------
    # 공용 유틸
    # -----------------------------------------------------
    def pick_first_text(self, *values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def deep_get(self, data: Any, keys: List[str]) -> Any:
        cur = data
        for key in keys:
            cur = cur.get(key) if cur else None
        return cur

    def find_all_values_by_key(self, data: Any, target_key: str) -> List[Any]:
        found: List[Any] = []

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == target_key:
                        found.append(v)
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
        return found


    def cleanup(self) -> None:
        try:
            if self.api_client:
                self.api_client.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")


    # -----------------------------------------------------
    # 종료
    # -----------------------------------------------------
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()


    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self.cleanup()
        self.log_signal_func("✅ stop 완료")
