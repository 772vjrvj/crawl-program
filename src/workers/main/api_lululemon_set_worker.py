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
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiLululemonSetLoadWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()


        self.folder_path = None
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
        self.api_client: Optional[APIClient] = None

        self.url_list: List[str] = []
        self.running: bool = True

        self.company_name: str = "lululemon"
        self.site_name: str = "lululemon"
        self.worker_name: str = "lululemon"

        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0

        self.api_client = APIClient(use_cache=False)

        # 엑셀 파일 저장 시 출력될 표준 헤더 목록
        self.columns: List[str] = ["컬러", "사이즈", "옵션가", "재고수량", "관리코드", "사용여부"]

        self.out_dir: str = "output"

        # DB 저장용 상태 관리 필드
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None

        self.detail_table_name: str = "LULULEMON"
        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0

        # 데이터베이스 매핑을 위한 컬럼 명세 정의 (총 8개 컬럼)
        self.db_columns: List[str] = [
            "product_name", "color", "size", "option_price",
            "stock_qty", "manage_code", "use_yn", "item_url"
        ]

        self._size_rank: Dict[str, int] = {}
        self._cleaned_up: bool = False

    # -----------------------------------------------------
    # 초기화
    # -----------------------------------------------------
    def init(self) -> bool:
        try:
            self.excel_driver = ExcelUtils(self.log_signal_func)
            self.file_driver = FileUtils(self.log_signal_func)
            self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
            self.folder_path: str = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.log_signal.emit(f"[DEBUG] base_dir = {self.get_base_dir()}")
            self.log_signal.emit(f"[DEBUG] out_dir = {self.out_dir}")

            # SQLite 데이터베이스 세팅
            # (기존: 여기서 History를 1개 열었지만, 낱개 생성을 위해 제거함)
            if not self.db_set():
                return False

            return True
        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

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
            self.finish_job("FAIL", str(e))
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

            options, h1_product_name = self.product_api_data(url)

            if options:
                self.log_signal.emit(f"[옵션 미리보기] 총 {len(options)}건 / 첫번째 옵션: {options[0]}")
            else:
                self.log_signal.emit("[옵션 미리보기] 옵션 없음 (0건)")
                self.log_signal.emit(f"[SKIP] 저장할 옵션 없음: {url}")
                self.update_progress()
                time.sleep(random.uniform(1, 2))
                continue

            # ---------------------------------------------------------
            # 1. DB 히스토리 낱개 생성 (URL 1개 = 엑셀 1개 = History 1개)
            # ---------------------------------------------------------
            self.detail_success_count = 0
            self.detail_fail_count = 0
            self.hist_status = "RUNNING"
            self.hist_error_message = None

            if not self.insert_hist_start():
                self.log_signal.emit("[DB] 히스토리 생성 실패")

            # ---------------------------------------------------------
            # 2. SQLite 데이터베이스 Row M개 저장
            # ---------------------------------------------------------
            for opt_item in options:
                if not self.running:
                    break

                db_row_data = {
                    "product_name": h1_product_name,
                    "color": opt_item.get("컬러", ""),
                    "size": opt_item.get("사이즈", ""),
                    "option_price": opt_item.get("옵션가", 0),
                    "stock_qty": opt_item.get("재고수량", 0),
                    "manage_code": opt_item.get("관리코드", ""),
                    "use_yn": opt_item.get("사용여부", "Y"),
                    "item_url": url
                }
                self.insert_detail_row(db_row_data)

            # ---------------------------------------------------------
            # 3. 엑셀 파일 M개 데이터 낱개 저장
            # ---------------------------------------------------------
            filename = f"{self.safe_filename(h1_product_name)}_{self.now_stamp()}.xlsx"

            try:
                saved_path = self.excel_driver.save_obj_list_to_excel(
                    filename=filename,
                    obj_list=options,
                    columns=self.columns,
                    sheet_name="Sheet1",
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )

                if saved_path and os.path.exists(saved_path):
                    self.log_signal.emit(f"({num}/{self.total_cnt}) 엑셀 및 DB 저장완료: {saved_path}")
                else:
                    self.log_signal.emit(f"[저장실패] 파일이 생성되지 않음: {saved_path}")

            except Exception as e:
                self.log_signal.emit(f"[저장실패] {e}")

            # ---------------------------------------------------------
            # 4. DB 히스토리 낱개 닫기 (이번 URL 작업 완료 처리)
            # ---------------------------------------------------------
            if self.running:
                self.finish_job("SUCCESS")
            else:
                self.finish_job("STOP", "사용자 중단")

            # 히스토리를 닫고, 다음 루프를 위해 hist_id 초기화
            self.update_hist_end()
            self.hist_id = None

            self.update_progress()
            time.sleep(random.uniform(4.0, 7.0))

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

            h1_tag = soup.find("h1")
            h1_product_name = h1_tag.get_text(" ", strip=True) if h1_tag else ""

            size_order = self.extract_all_size_order_from_next_data(next_data)
            self._size_rank = self.build_size_rank(size_order)

            variants = self.extract_variants(next_data, soup)
            if not variants:
                self.log_signal.emit(f"[SKIP] variants 없음: {url}")
                return [], "product"

            rows = []
            for v in variants:
                row = self.normalize_variant(v)
                if row:
                    rows.append(row)

            if not rows:
                self.log_signal.emit(f"[SKIP] 정규화된 옵션 rows 없음: {url}")
                return [], h1_product_name

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

            return out, h1_product_name

        except Exception as e:
            self.log_signal.emit(f"[SKIP] 처리 실패: {url} / {e}")
            return [], "product"

    # -----------------------------------------------------
    # HTML 가져오기 (아카마이 우회 로직)
    # -----------------------------------------------------
    def fetch_product_soup(self, url: str) -> BeautifulSoup:
        # http://172.30.1.70:5000/api/crawl
        # http://220.94.196.191:5000/api/crawl

        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": "my-secret-key-1234"
        }
        payload = {
            "url": url
        }

        data = self.api_client.post(url='http://220.94.196.191:5000/api/crawl', headers=headers, json=payload)

        return BeautifulSoup(data['soup'], "html.parser")

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
    # __NEXT_DATA__ 에서 allSize 순서 추출
    # -----------------------------------------------------
    def extract_all_size_order_from_next_data(self, next_data: Dict[str, Any]) -> List[str]:
        result: List[str] = []

        for candidate in self.find_all_values_by_key(next_data, "allSize"):
            for item in candidate:
                size_text = str(item.get("size") or "").strip()
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
    # 최소가 및 계산 모듈
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

    def is_in_stock(self, availability: Any) -> bool:
        text = str(availability or "").strip().lower()
        return "instock" in text or text in {"available", "in_stock", "in stock", "available_now"}

    # -----------------------------------------------------
    # 정렬 및 랭크 처리
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
            "XXXS": 1, "XXS": 2, "XS": 3, "S": 4, "M": 5,
            "L": 6, "XL": 7, "XXL": 8, "1X": 9, "2X": 10, "3X": 11, "4X": 12,
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

    def parse_color_size_from_name(self, name: str) -> Tuple[str, str]:
        parts = [p.strip() for p in name.split(" - ") if p.strip()]
        if len(parts) >= 3:
            return parts[-2], parts[-1]
        if len(parts) >= 2:
            return "", parts[-1]
        return "", ""

    def shorten_color(self, color: str) -> str:
        color = color.strip()
        if len(color) <= 25:
            return color

        parts = color.split()
        if not parts:
            return color[:25]

        short_name = parts[0] + " " + "".join(p[0].upper() for p in parts[1:] if p)
        return short_name[:25]

    def safe_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
        return (name or "product")[:80]

    def now_stamp(self) -> str:
        return time.strftime("%Y%m%d_%H%M%S")

    def get_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.getcwd()

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

    # =========================================================
    # SQLite DB 관리 공용 모듈 파트
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)
        db_path = self.get_runtime_db_path()

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        # [변경점] init에서는 DB 연동 세팅만 하고 History는 생성하지 않음. (URL 루프에서 낱개로 생성)
        return True

    def insert_hist_start(self) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id, table_name, site_name, worker_name, user_id,
                    start_at, status, total_count, success_count, fail_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        params = (
            self.job_id, self.detail_table_name, self.site_name, self.worker_name,
            self.user,
            now, "RUNNING", 0, 0, 0, now, now,
        )

        if not self.sqlite_driver.execute(query, params):
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None
        return True

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not sqlite_driver or not self.hist_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        query = """
                UPDATE worker_job_hist
                SET end_at = ?, status = ?, total_count = ?, success_count = ?, fail_count = ?,
                    error_message = ?, updated_at = ?
                WHERE hist_id = ?
                """
        params = (
            now, self.hist_status, self.detail_success_count + self.detail_fail_count,
            self.detail_success_count, self.detail_fail_count, self.hist_error_message, now, self.hist_id,
        )
        return sqlite_driver.execute(query, params)

    def insert_detail_row(self, rs: Dict[str, Any]) -> bool:
        if not self.sqlite_driver or not self.db_columns:
            self.detail_fail_count += 1
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        base_columns = ["hist_id", "site_name", "worker_name", "table_name", "job_id", "user_id", "row_status"]
        all_columns = base_columns + self.db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(all_columns)

        query = f"INSERT INTO {self.detail_table_name} ({column_text}) VALUES ({placeholders})"
        params = (
            self.hist_id, self.site_name, self.worker_name, self.detail_table_name, self.job_id,
            getattr(self.user, "user_id", None) if self.user else None, "SUCCESS",
            *[rs.get(col, "") for col in self.db_columns], now, now,
        )

        ok = self.sqlite_driver.execute(query, params)
        if ok:
            self.detail_success_count += 1
        else:
            self.detail_fail_count += 1
        return ok

    def finalize_db_and_excel(self) -> None:
        temp_sqlite_driver = None
        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            if temp_sqlite_driver.connect(self.get_runtime_db_path()):
                # 중도 정지 시 열려있는 hist가 있다면 강제 업데이트
                if self.hist_id:
                    self.update_hist_end(temp_sqlite_driver)
        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")
        finally:
            if temp_sqlite_driver:
                temp_sqlite_driver.close()

    # =========================================================
    # 종료 / 자원 해제 정리
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        self.finalize_db_and_excel()

        try:
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
        except:
            pass
        finally:
            self.sqlite_driver = None

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

        self.file_driver, self.excel_driver, self.api_client = None, None, None
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()