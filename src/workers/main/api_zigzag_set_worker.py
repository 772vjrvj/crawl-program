# src/workers/main/api_zigzag_set_worker.py
from __future__ import annotations

import os
import random
import re
import threading
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from bs4 import BeautifulSoup

from src.repositories.worker_db_repository import WorkerDbRepository
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.workers.api_base_worker import BaseApiWorker


class CategoryBlockedError(RuntimeError):
    """상세 요청 차단으로 현재 카테고리를 중단한다."""


class ApiZigzagSetWorker(BaseApiWorker):
    """지그재그 상품을 조회하고 판매자 기준으로 저장한다."""

    LIST_API_URL = "https://api.zigzag.kr/api/2/graphql/GetSearchResult"
    PRODUCT_DETAIL_URL = "https://zigzag.kr/catalog/products/{product_id}"

    REQUEST_TIMEOUT = (10, 30)

    LIST_DELAY_SECONDS = (1.5, 3.0)
    DETAIL_DELAY_SECONDS = (2.5, 4.5)
    CATEGORY_DELAY_SECONDS = (15.0, 30.0)
    BLOCK_WAIT_SECONDS = (60.0, 120.0)

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )

    CURSOR_FIELD = "after"

    SHEET_COLUMNS: Tuple[Tuple[str, str], ...] = (
        ("collected_date", "수집일"),
        ("category", "카테고리"),
        ("shopping_mall_name", "쇼핑몰명"),
        ("company_name", "업체명"),
        ("representative_name", "대표자"),
        ("email", "이메일"),
        ("phone", "전화번호"),
    )

    SEARCH_QUERY = """
    fragment ProductFields on UxGoodsCardItem {
      catalog_product_id
      shop_id
      shop_name
    }

    query GetSearchResult($input: SearchResultInput!) {
      search_result(input: $input) {
        end_cursor
        has_next
        ui_item_list {
          __typename

          ...ProductFields

          ... on UxGoodsGroup {
            goods_carousel {
              component_list {
                ...ProductFields
              }
            }
          }

          ... on UxShopRankingCardItem {
            component_list {
              ...ProductFields
            }
          }

          ... on UxGoodsCarousel {
            component_list {
              ...ProductFields
            }
          }
        }
      }
    }
    """

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        if setting is not None:
            self.setting = setting

        self.site_name = "지그재그"
        self.worker_name = "zigzag"
        self.detail_table_name = "zigzag"
        self.detail_log_fields = (
            "product_id",
            "shopping_mall_name",
            "company_name",
        )

        self.running = True
        self.before_pro_value = 0.0
        self.init_flag = False
        self._cleaned_up = False
        self._stop_event = threading.Event()

        self.folder_path = ""
        self.auto_save_yn = False
        self.google_sheet_yn = False
        self.remove_duplicate_yn = True
        self.fr_page = 1
        self.to_page = 1
        self.spreadsheet_id = ""
        self.worksheet_name = ""
        self.json_path = ""
        self.out_dir = "output"

        self.category_list: List[Dict[str, str]] = []
        self.columns: List[str] = []

        self.api_client: Optional[APIClient] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.db_repository: Optional[WorkerDbRepository] = None

    # =========================================================
    # 초기화
    # =========================================================
    def init(self) -> bool:
        try:
            if self.init_flag:
                return True

            setting = getattr(self, "setting", None)
            if not isinstance(setting, list):
                self.log_signal_func("❌ setting 형식이 올바르지 않습니다.")
                return False

            self.folder_path = str(
                self.get_setting_value(setting, "folder_path") or ""
            ).strip()
            self.auto_save_yn = self._to_bool(
                self.get_setting_value(setting, "auto_save_yn")
            )
            self.google_sheet_yn = self._to_bool(
                self.get_setting_value(setting, "google_sheet_yn")
            )
            self.remove_duplicate_yn = self._to_bool(
                self.get_setting_value(setting, "remove_duplicate_yn")
            )
            self.fr_page = self._to_int(
                self.get_setting_value(setting, "fr_page"),
                1,
            )
            self.to_page = self._to_int(
                self.get_setting_value(setting, "to_page"),
                self.fr_page,
            )
            self.spreadsheet_id = str(
                self.get_setting_value(setting, "spreadsheet_id") or ""
            ).strip()
            self.worksheet_name = str(
                self.get_setting_value(setting, "worksheet_name") or ""
            ).strip()
            self.json_path = str(
                self.get_setting_value(setting, "json_path") or ""
            ).strip()
            self.category_list = self._get_selected_categories()

            if self.fr_page < 1:
                self.fr_page = 1

            if self.to_page < self.fr_page:
                self.log_signal_func(
                    "❌ 종료 페이지가 시작 페이지보다 작습니다."
                )
                return False

            if not self.category_list:
                self.log_signal_func("❌ 선택된 카테고리가 없습니다.")
                return False

            self.driver_set()

            if not self.db_set():
                return False

            self.init_flag = True
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.api_client = APIClient(
            timeout=self.REQUEST_TIMEOUT,
            verify=True,
            retries=3,
            backoff=1.0,
            use_cache=False,
            log_func=self.log_signal_func,
        )
        self.api_client.session.headers.update(
            {
                "user-agent": self.USER_AGENT,
                "accept-language": (
                    "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
                ),
            }
        )

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {
            "true",
            "1",
            "y",
            "yes",
            "on",
        }

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    def _get_selected_categories(self) -> List[Dict[str, str]]:
        rows = getattr(self, "setting_detail", None)
        if not isinstance(rows, list):
            return []

        result: List[Dict[str, str]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("row_type") != "item":
                continue
            if not self._to_bool(row.get("checked")):
                continue

            result.append(
                {
                    "code": str(row.get("code") or "").strip(),
                    "value": str(row.get("value") or "").strip(),
                    "list_url": str(row.get("list_url") or "").strip(),
                }
            )

        return result

    # =========================================================
    # 요청 공통
    # =========================================================
    def _sleep(self, seconds: float) -> None:
        self._stop_event.wait(seconds)

    def _wait_random(self, delay_range: Tuple[float, float]) -> None:
        if self.running and not self._stop_event.is_set():
            self._sleep(random.uniform(*delay_range))

    @staticmethod
    def _list_headers(category_url: str) -> Dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://zigzag.kr",
            "referer": category_url,
            "cache-control": "no-cache",
            "pragma": "no-cache",
        }

    @staticmethod
    def _detail_headers(category_url: str) -> Dict[str, str]:
        return {
            "accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "referer": category_url,
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "upgrade-insecure-requests": "1",
        }

    def _warm_up(self, category_url: str) -> None:
        if not self.api_client:
            raise RuntimeError("APIClient가 없습니다.")

        result = self.api_client.get(
            category_url,
            headers=self._detail_headers(category_url),
            timeout=self.REQUEST_TIMEOUT,
        )
        self._wait_random(self.LIST_DELAY_SECONDS)

        if result is None:
            self.log_signal_func(
                "⚠️ 카테고리 페이지 세션 준비 실패, 계속 진행합니다."
            )
            return

        cookie_count = len(self.api_client.session.cookies)
        self.log_signal_func(
            f"✅ 세션 준비 완료 / cookie={cookie_count}"
        )

    def _post_search(
            self,
            category_url: str,
            search_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.api_client:
            raise RuntimeError("APIClient가 없습니다.")

        payload = {
            "query": self.SEARCH_QUERY,
            "variables": {"input": search_input},
        }

        # APIClient는 POST를 자동 재시도하지 않으므로 여기서만 재시도한다.
        for attempt in range(1, 4):
            result = self.api_client.post(
                self.LIST_API_URL,
                headers=self._list_headers(category_url),
                json=payload,
                timeout=self.REQUEST_TIMEOUT,
            )
            self._wait_random(self.LIST_DELAY_SECONDS)

            if isinstance(result, dict):
                if result.get("errors"):
                    raise RuntimeError(
                        f"GraphQL 오류: {result['errors']}"
                    )
                return result

            if attempt < 3:
                wait_seconds = attempt * 10
                self.log_signal_func(
                    f"⚠️ 목록 요청 재시도 / {attempt}/3 "
                    f"/ 대기={wait_seconds}초"
                )
                self._sleep(wait_seconds)

        raise RuntimeError("목록 API 요청 실패")

    # =========================================================
    # 상품 목록
    # =========================================================
    @staticmethod
    def _extract_products(value: Any) -> List[Dict[str, str]]:
        products: List[Dict[str, str]] = []
        seen_ids: Set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                product_id = str(
                    node.get("catalog_product_id") or ""
                ).strip()
                shop_name = str(
                    node.get("shop_name") or ""
                ).strip()

                if product_id and shop_name and product_id not in seen_ids:
                    seen_ids.add(product_id)
                    products.append(
                        {
                            "product_id": product_id,
                            "shop_id": str(
                                node.get("shop_id") or ""
                            ).strip(),
                            "shop_name": shop_name,
                        }
                    )

                for child in node.values():
                    walk(child)

            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
        return products

    def _parse_search(
            self,
            body: Dict[str, Any],
    ) -> Tuple[List[Dict[str, str]], Optional[str], bool]:
        search_result = body.get("data", {}).get("search_result")

        if not isinstance(search_result, dict):
            raise RuntimeError(
                "data.search_result를 찾지 못했습니다."
            )

        products = self._extract_products(
            search_result.get("ui_item_list", [])
        )
        cursor = search_result.get("end_cursor")

        return products, str(cursor) if cursor else None, bool(
            search_result.get("has_next")
        )

    def _fetch_first_page(
            self,
            category_code: str,
            category_url: str,
    ) -> Tuple[List[Dict[str, str]], Optional[str], bool]:
        body = self._post_search(
            category_url,
            {
                "display_category_id_list": [category_code],
                "page_id": "web_srp_clp_category",
            },
        )
        return self._parse_search(body)

    def _fetch_next_page(
            self,
            category_code: str,
            category_url: str,
            cursor: str,
            previous_ids: Set[str],
    ) -> Tuple[List[Dict[str, str]], Optional[str], bool]:
        body = self._post_search(
            category_url,
            {
                "display_category_id_list": [category_code],
                "page_id": "web_srp_clp_category",
                self.CURSOR_FIELD: cursor,
            },
        )
        products, next_cursor, has_next = self._parse_search(body)

        current_ids = {
            product["product_id"]
            for product in products
        }
        if current_ids and current_ids == previous_ids:
            raise RuntimeError("이전 페이지와 동일한 상품이 반환됐습니다.")

        return products, next_cursor, has_next

    def _collect_product_list(
            self,
            category: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        category_code = category["code"]
        category_name = category["value"]
        category_url = category["list_url"]

        self.log_signal_func(
            f"✅ 목록 시작 / 카테고리={category_name} "
            f"/ page={self.fr_page}~{self.to_page}"
        )

        self._warm_up(category_url)

        result: List[Dict[str, Any]] = []
        seen_product_ids: Set[str] = set()

        cursor: Optional[str] = None
        previous_ids: Set[str] = set()

        # 커서 방식이라 시작 페이지 전까지도 순서대로 요청해야 한다.
        for page in range(1, self.to_page + 1):
            if not self.running or self._stop_event.is_set():
                break

            if page == 1:
                products, cursor, has_next = self._fetch_first_page(
                    category_code,
                    category_url,
                )
            else:
                if not cursor:
                    break

                products, cursor, has_next = self._fetch_next_page(
                    category_code,
                    category_url,
                    cursor,
                    previous_ids,
                )

            previous_ids = {
                product["product_id"]
                for product in products
            }

            added = 0

            if page >= self.fr_page:
                for product in products:
                    product_id = product["product_id"]

                    if product_id in seen_product_ids:
                        continue

                    seen_product_ids.add(product_id)

                    product_with_page: Dict[str, Any] = dict(product)
                    product_with_page["page"] = page
                    result.append(product_with_page)
                    added += 1

            self.log_signal_func(
                f"목록 완료 / 카테고리={category_name} "
                f"/ page={page}/{self.to_page} "
                f"/ 상품={len(products)} / 신규={added} "
                f"/ 누적={len(result)}"
            )

            if not has_next:
                break

        return result

    def _deduplicate_products_by_shop(
            self,
            products: Sequence[Dict[str, Any]],
            seen_shop_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        if not self.remove_duplicate_yn:
            return list(products)

        result: List[Dict[str, Any]] = []

        for product in products:
            # shop_id가 있을 때만 상세 요청을 미리 줄인다.
            shop_id = product.get("shop_id", "")

            if shop_id and shop_id in seen_shop_ids:
                continue

            if shop_id:
                seen_shop_ids.add(shop_id)

            result.append(product)

        return result

    # =========================================================
    # 판매자 상세
    # =========================================================
    @staticmethod
    def _find_shop_node(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            if (
                    isinstance(value.get("main_contact"), dict)
                    or isinstance(value.get("business_license"), dict)
            ):
                return value

            for child in value.values():
                found = ApiZigzagSetWorker._find_shop_node(child)
                if found is not None:
                    return found

        elif isinstance(value, list):
            for child in value:
                found = ApiZigzagSetWorker._find_shop_node(child)
                if found is not None:
                    return found

        return None

    @staticmethod
    def _combine_phone_numbers(*values: Any) -> str:
        result: List[str] = []

        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)

        return " / ".join(result)

    def _parse_seller_info(self, html: str) -> Dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")

        if script is None:
            raise RuntimeError("__NEXT_DATA__를 찾지 못했습니다.")

        raw_json = script.string or script.get_text(strip=True)
        if not raw_json:
            raise RuntimeError("__NEXT_DATA__가 비어 있습니다.")

        import json

        shop_node = self._find_shop_node(json.loads(raw_json))
        if shop_node is None:
            raise RuntimeError("판매자 정보를 찾지 못했습니다.")

        contact = shop_node.get("main_contact") or {}
        license_info = shop_node.get("business_license") or {}

        seller = {
            "company_name": str(
                license_info.get("company_name") or ""
            ).strip(),
            "representative_name": str(
                license_info.get("representative_name") or ""
            ).strip(),
            "email": str(contact.get("email") or "").strip(),
            "phone": self._combine_phone_numbers(
                contact.get("landline_number"),
                contact.get("mobile_number"),
            ),
        }

        if not any(
                (
                        seller["company_name"],
                        seller["representative_name"],
                        seller["phone"],
                )
        ):
            raise RuntimeError("판매자 핵심 정보가 비어 있습니다.")

        return seller

    def _fetch_seller_info(
            self,
            category_url: str,
            product_id: str,
    ) -> Dict[str, str]:
        if not self.api_client:
            raise RuntimeError("APIClient가 없습니다.")

        detail_url = self.PRODUCT_DETAIL_URL.format(
            product_id=product_id
        )

        for attempt in range(3):
            response = self.api_client.session.get(
                detail_url,
                headers=self._detail_headers(category_url),
                timeout=self.REQUEST_TIMEOUT,
                verify=self.api_client.verify,
            )

            if response.status_code in (403, 429):
                if attempt < len(self.BLOCK_WAIT_SECONDS):
                    wait_seconds = self.BLOCK_WAIT_SECONDS[attempt]
                    self.log_signal_func(
                        f"⚠️ 상세 접근 제한 / status={response.status_code} "
                        f"/ 재시도={attempt + 1}/2 "
                        f"/ 대기={int(wait_seconds)}초"
                    )
                    self._sleep(wait_seconds)
                    continue

                raise CategoryBlockedError(
                    f"상세 접근 제한 지속 / status={response.status_code}"
                )

            response.raise_for_status()
            html = response.text
            self._wait_random(self.DETAIL_DELAY_SECONDS)
            return self._parse_seller_info(html)

        raise CategoryBlockedError("상세 접근 제한 지속")

    def _collect_seller_rows(
            self,
            category: Dict[str, str],
            products: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        total = len(products)
        collected_date = datetime.now().strftime("%Y-%m-%d")

        for index, product in enumerate(products, start=1):
            if not self.running or self._stop_event.is_set():
                break

            row_start_at = self._now_db()
            product_id = str(product["product_id"])
            page = int(product.get("page") or 0)
            detail_url = self.PRODUCT_DETAIL_URL.format(
                product_id=product_id
            )

            try:
                seller = self._fetch_seller_info(
                    category["list_url"],
                    product_id,
                )

                row = {
                    "collected_date": collected_date,
                    "category": category["value"],
                    "page": page,
                    "shopping_mall_name": product["shop_name"],
                    "company_name": seller["company_name"],
                    "representative_name": seller[
                        "representative_name"
                    ],
                    "email": seller["email"],
                    "phone": seller["phone"],
                    "url": detail_url,
                    "product_id": product_id,
                }
                rows.append(row)

                self.log_signal_func(
                    f"상세 완료 / {index}/{total} "
                    f"/ page={page} "
                    f"/ 쇼핑몰={product['shop_name']} "
                    f"/ 업체명={seller['company_name'] or '없음'}"
                )

            except CategoryBlockedError as e:
                self.log_signal_func(
                    f"⛔ 카테고리 상세 수집 중단 "
                    f"/ 카테고리={category['value']} / {e}"
                )
                self.insert_detail_row(
                    {
                        "collected_date": collected_date,
                        "category": category["value"],
                        "shopping_mall_name": product["shop_name"],
                        "company_name": "",
                        "representative_name": "",
                        "email": "",
                        "phone": "",
                        "url": detail_url,
                        "product_id": product_id,
                    },
                    row_status="FAIL",
                    row_error_message=str(e),
                    row_start_at=row_start_at,
                    row_end_at=self._now_db(),
                )
                break

            except Exception as e:
                self.log_signal_func(
                    f"❌ 상세 실패 / {index}/{total} "
                    f"/ product_id={product_id} / {e}"
                )
                self.insert_detail_row(
                    {
                        "collected_date": collected_date,
                        "category": category["value"],
                        "shopping_mall_name": product["shop_name"],
                        "company_name": "",
                        "representative_name": "",
                        "email": "",
                        "phone": "",
                        "url": detail_url,
                        "product_id": product_id,
                    },
                    row_status="FAIL",
                    row_error_message=str(e),
                    row_start_at=row_start_at,
                    row_end_at=self._now_db(),
                )
                self._wait_random(self.DETAIL_DELAY_SECONDS)

        return rows

    def collect_zigzag_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen_shop_ids: Set[str] = set()
        total_categories = len(self.category_list)

        for index, category in enumerate(self.category_list, start=1):
            if not self.running or self._stop_event.is_set():
                break

            products = self._collect_product_list(category)
            products = self._deduplicate_products_by_shop(
                products,
                seen_shop_ids,
            )

            self.log_signal_func(
                f"✅ 상세 대상 / 카테고리={category['value']} "
                f"/ 상품={len(products)}"
            )

            rows.extend(
                self._collect_seller_rows(category, products)
            )

            if (
                    index < total_categories
                    and self.running
                    and not self._stop_event.is_set()
            ):
                delay = random.uniform(*self.CATEGORY_DELAY_SECONDS)
                self.log_signal_func(
                    f"ℹ️ 다음 카테고리 대기 / {int(delay)}초"
                )
                self._sleep(delay)

        return rows

    # =========================================================
    # 판매자 중복 제거
    # =========================================================
    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = unicodedata.normalize(
            "NFKC",
            str(value or ""),
        ).strip()
        return re.sub(r"\s+", " ", text).casefold()

    @staticmethod
    def _normalize_phone(value: Any) -> str:
        return re.sub(r"\D", "", str(value or ""))

    def _seller_key(self, row: Dict[str, Any]) -> str:
        return "|".join(
            (
                self._normalize_text(row.get("company_name")),
                self._normalize_text(
                    row.get("representative_name")
                ),
                self._normalize_phone(row.get("phone")),
            )
        )

    def build_seller_key_set(
            self,
            rows: Sequence[Dict[str, Any]],
    ) -> Set[str]:
        return {
            key
            for row in rows
            if (key := self._seller_key(row)) != "||"
        }

    def filter_new_seller_rows(
            self,
            rows: Sequence[Dict[str, Any]],
            existing_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        if not self.remove_duplicate_yn:
            return list(rows)

        result: List[Dict[str, Any]] = []
        seen_keys = set(existing_keys)

        for row in rows:
            key = self._seller_key(row)

            if key == "||":
                continue

            if key in seen_keys:
                continue

            seen_keys.add(key)
            result.append(row)

        self.log_signal_func(
            f"✅ 판매자 중복 제거 / 수집={len(rows)} "
            f"/ 신규={len(result)}"
        )
        return result

    # =========================================================
    # 구글 시트
    # =========================================================
    def _get_google_worksheet(self) -> Any:
        if not self.spreadsheet_id:
            raise ValueError("스프레드시트 ID가 없습니다.")
        if not self.worksheet_name:
            raise ValueError("워크시트명이 없습니다.")
        if not os.path.isfile(self.json_path):
            raise FileNotFoundError(
                f"인증 JSON 파일이 없습니다: {self.json_path}"
            )

        try:
            import gspread
        except ImportError as e:
            raise RuntimeError(
                "gspread와 google-auth를 설치해야 합니다."
            ) from e

        client = gspread.service_account(filename=self.json_path)
        return client.open_by_key(
            self.spreadsheet_id
        ).worksheet(self.worksheet_name)

    def read_google_sheet_rows(self) -> List[Dict[str, Any]]:
        worksheet = self._get_google_worksheet()
        values = worksheet.get_all_values()

        if not values:
            return []

        headers = [name for _, name in self.SHEET_COLUMNS]
        if values[0] != headers:
            raise ValueError(
                f"구글 시트 헤더 불일치 / 예상={headers} "
                f"/ 현재={values[0]}"
            )

        rows: List[Dict[str, Any]] = []

        for values_row in values[1:]:
            if not any(str(value).strip() for value in values_row):
                continue

            rows.append(
                {
                    code: (
                        values_row[index]
                        if index < len(values_row)
                        else ""
                    )
                    for index, (code, _) in enumerate(
                    self.SHEET_COLUMNS
                )
                }
            )

        self.log_signal_func(
            f"✅ 구글 시트 조회 완료 / 건수={len(rows)}"
        )
        return rows

    def append_google_sheet_rows(
            self,
            rows: Sequence[Dict[str, Any]],
    ) -> bool:
        if not rows:
            return True

        worksheet = self._get_google_worksheet()
        headers = [name for _, name in self.SHEET_COLUMNS]
        current_headers = worksheet.row_values(1)

        if not current_headers:
            worksheet.append_row(
                headers,
                value_input_option="RAW",
            )
        elif current_headers != headers:
            raise ValueError(
                f"구글 시트 헤더 불일치 / 예상={headers} "
                f"/ 현재={current_headers}"
            )

        values = [
            [
                str(row.get(code) or "")
                for code, _ in self.SHEET_COLUMNS
            ]
            for row in rows
        ]

        worksheet.append_rows(
            values,
            value_input_option="RAW",
        )
        self.log_signal_func(
            f"✅ 구글 시트 추가 완료 / 건수={len(values)}"
        )
        return True

    # =========================================================
    # 실행
    # =========================================================
    def main(self) -> bool:
        try:
            self.log_signal_func("✅ 지그재그 작업 시작")

            existing_sheet_rows: List[Dict[str, Any]] = []

            if self.google_sheet_yn:
                self.log_signal_func("✅ 구글 시트 기존 데이터 조회")
                existing_sheet_rows = self.read_google_sheet_rows()
            else:
                self.log_signal_func("ℹ️ 구글 시트 저장 미사용")

            existing_keys = self.build_seller_key_set(
                existing_sheet_rows
            )

            collected_rows = self.collect_zigzag_rows()

            if not self.running or self._stop_event.is_set():
                self.finish_job("STOP", "사용자 중단")
                return False

            new_rows = self.filter_new_seller_rows(
                collected_rows,
                existing_keys,
            )

            if new_rows and not self.insert_detail_rows(new_rows):
                raise RuntimeError("신규 판매자 DB 저장 실패")

            if self.google_sheet_yn and new_rows:
                self.append_google_sheet_rows(new_rows)

            self.finish_job("SUCCESS")
            self.log_signal_func(
                f"✅ 작업 완료 / 수집={len(collected_rows)} "
                f"/ 신규={len(new_rows)}"
            )
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 작업 실패: {e}")
            self.finish_job("FAIL", str(e))
            return False

    # =========================================================
    # DB / Excel
    # =========================================================
    def db_set(self) -> bool:
        config = self.read_runtime_customer_config(
            customer_name=self.worker_name
        )
        column_defs = config.get("columns") or []

        if not isinstance(column_defs, list) or not column_defs:
            self.log_signal_func("❌ config columns가 없습니다.")
            return False

        try:
            user = getattr(self, "user", None)
            user_id = getattr(user, "user_id", user)

            self.db_repository = WorkerDbRepository(
                db_path=self.get_runtime_db_path(),
                site_name=self.site_name,
                worker_name=self.worker_name,
                detail_table_name=self.detail_table_name,
                column_defs=column_defs,
                user_id=user_id,
                log_func=self.log_signal_func,
                detail_log_fields=self.detail_log_fields,
            )
        except Exception as e:
            self.log_signal_func(
                f"❌ DB Repository 생성 실패: {e}"
            )
            return False

        schema_files = [
            os.path.join(
                "resources",
                "customers",
                "common",
                "db",
                "schema_hist.sql",
            ),
            os.path.join(
                "resources",
                "customers",
                self.worker_name,
                "db",
                "schema_detail.sql",
            ),
        ]

        if not self.db_repository.initialize(
                schema_files,
                start_job=True,
        ):
            return False

        self.columns = list(self.db_repository.excel_columns)
        return True

    def finish_job(
            self,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        if self.db_repository:
            self.db_repository.set_job_result(
                status,
                error_message,
            )

    def insert_detail_row(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        if not self.db_repository:
            return False

        return self.db_repository.insert_detail(
            row,
            row_status=row_status,
            row_error_message=row_error_message,
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    def insert_detail_rows(
            self,
            rows: Sequence[Dict[str, Any]],
    ) -> bool:
        if not self.db_repository:
            return False

        return self.db_repository.insert_details(rows)

    @staticmethod
    def _now_db() -> str:
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

    def export_detail_to_excel(self) -> bool:
        if not self.excel_driver or not self.db_repository:
            return False

        excel_columns, excel_rows = (
            self.db_repository.get_excel_data()
        )
        if not excel_rows:
            return False

        job_id = (
                self.db_repository.job_id
                or datetime.now().strftime("%Y%m%d%H%M%S")
        )

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=f"{self.site_name}_{job_id}.xlsx",
            row_list=excel_rows,
            columns=excel_columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def finalize_db_and_excel(self) -> None:
        if not self.db_repository:
            return

        try:
            if self.db_repository.status == "RUNNING":
                self.db_repository.set_job_result(
                    "FAIL",
                    "비정상 종료",
                )

            self.db_repository.finish_job()

            if self.auto_save_yn:
                self.export_detail_to_excel()

        except Exception as e:
            self.log_signal_func(f"❌ 종료 처리 실패: {e}")

    # =========================================================
    # 종료
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        self.finalize_db_and_excel()

        try:
            if self.db_repository:
                self.db_repository.close()
        finally:
            self.db_repository = None

        try:
            if self.api_client:
                self.api_client.close()
        finally:
            self.api_client = None

        try:
            if self.excel_driver:
                self.excel_driver.close()
        finally:
            self.excel_driver = None

        self._cleaned_up = True

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()

        if (
                self.db_repository
                and self.db_repository.status == "RUNNING"
        ):
            self.finish_job("STOP", "사용자 중단")

        self.cleanup()

    def destroy(self) -> None:
        self.cleanup()
        self.progress_signal.emit(
            self.before_pro_value,
            1000000,
        )
        self.progress_end_signal.emit()
