import copy
import json
import os
import re
import sys
import time
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from PIL import Image

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.str_utils import split_comma_keywords
from src.workers.api_base_worker import BaseApiWorker


class ApiCocoLabelSetWorker(BaseApiWorker):
    CATEGORY_ROOT_MAP: Dict[str, str] = {
        "가방": "여성 가방",
        "지갑": "여성 지갑",
        "의류": "여성 의류",
        "신발": "여성 신발",
        "잡화": "여성 패션 잡화",
        "명품시계": "명품 시계",
        "샤넬프리미엄": "샤넬 프리미엄",
        "에르메스프리미엄": "에르메스 프리미엄",
        "남성>남성가방": "남성 가방",
        "남성>남성신발": "남성 신발",
        "남성>남성의류": "남성 의류",
        "남성>남성지갑": "남성 지갑",
        "남성>남성패션잡화": "남성 패션 잡화",
        "남성>크롬하츠": "크롬하츠",
        "sale(당일발송)": "SALE (당일발송)",
    }

    IMAGE_URL_PREFIX: str = "/data/item/"
    OPTION_COMMON_VALUE: str = "0|9999|100|1"

    def __init__(self) -> None:
        super().__init__()

        self.csv_filename: Optional[str] = None
        self.coco_label_admin_list: Optional[List[Dict[str, Any]]] = None
        self.coco_label_site_list: Optional[List[Dict[str, Any]]] = None
        self.site_name: str = "COCO_LABEL"
        self.shop_url: str = "https://coco-label.com"
        self.shop_detail_url: str = "https://coco-label.com/ajax/get_shop_list_view.cm"

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.total_cnt: int = 0
        self.total_pages: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0
        self.keyword_list: Optional[List[str]] = None

        self.sess: Optional[requests.Session] = None
        self.result: List[Dict[str, Any]] = []

        self.headers: Dict[str, str] = {
            "authority": "coco-label.com",
            "method": "GET",
            "path": "/",
            "scheme": "https",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=0, i",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }

        self.main_category_obj_list: List[Dict[str, Any]] = []
        self.main_category_obj_filter_list: List[Dict[str, Any]] = []
        self.main_sub_category_obj_list: List[Dict[str, Any]] = []

        self.folder_path: str = ""
        self.out_dir: str = "output_coco_label"
        self.admin_lookup_by_path: Dict[str, Dict[str, Any]] = {}

    def init(self) -> bool:
        self.driver_set()

        self.coco_label_admin_list = self.file_driver.read_json_array_from_resources(
            "coco_label_admin_list.json",
            "customers/coco_label",
        )

        self.coco_label_site_list = self.file_driver.read_json_array_from_resources(
            "coco_label_site_list.json",
            "customers/coco_label",
        )

        if not self.coco_label_admin_list:
            self.log_signal_func("ADMIN JSON 데이터가 없습니다.")
            return False

        if not self.coco_label_site_list:
            self.log_signal_func("SITE JSON 데이터가 없습니다.")
            return False

        keyword_str: str = self.get_setting_value(self.setting, "keyword")
        self.keyword_list = split_comma_keywords(keyword_str)

        self.log_signal_func(f"✅ 요청 목록 : {self.keyword_list}")
        return True

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.log_signal_func("✅ 드라이버 세팅 완료")

    def cleanup(self) -> None:
        try:
            self.excel_driver.convert_csv_to_excel_and_delete(
                csv_filename=self.csv_filename,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )
            self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

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

        self.api_client = None
        self.file_driver = None
        self.excel_driver = None
        self.log_signal_func("✅ cleanup")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def main(self) -> bool:
        self.log_signal_func("크롤링 시작.")

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

        self.excel_driver.init_csv(
            self.csv_filename,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

        self.main_category_list()
        self.attach_site_full_paths()
        self.filter_by_keywords()
        self.build_admin_lookup()
        self.map_category()
        self.sub_category_list()
        self.get_product_detail()

        return True

    def main_category_list(self) -> None:
        if self.coco_label_site_list:
            self.main_category_obj_list = copy.deepcopy(self.coco_label_site_list)
            self.log_signal_func(f"✅ site json 카테고리 로드 완료: {len(self.main_category_obj_list)}개")
            return

        if not self.api_client:
            return

        response: str = self.api_client.get(url=self.shop_url, headers=self.headers)
        soup: BeautifulSoup = BeautifulSoup(response, "html.parser")
        root: Optional[Tag] = soup.select_one(".viewport-nav.desktop._main_menu")

        self.main_category_obj_list = []

        if not root:
            return

        def parse_li(li: Tag) -> Optional[Dict[str, Any]]:
            a: Optional[Tag] = li.find("a", recursive=False)
            if not a:
                return None

            span: Optional[Tag] = a.find("span", recursive=False)
            obj: Dict[str, Any] = {
                "name": span.get_text(strip=True) if span else "",
                "href": (a.get("href") or "").strip(),
            }

            ul: Optional[Tag] = li.find("ul", recursive=False)
            if ul:
                children: List[Dict[str, Any]] = []

                for child_li in ul.find_all("li", recursive=False):
                    if not isinstance(child_li, Tag):
                        continue

                    child_obj: Optional[Dict[str, Any]] = parse_li(child_li)
                    if child_obj:
                        children.append(child_obj)

                if children:
                    obj["children"] = children

            return obj

        for li in root.find_all("li", class_="dropdown", recursive=False):
            if not isinstance(li, Tag):
                continue

            obj: Optional[Dict[str, Any]] = parse_li(li)
            if obj:
                self.main_category_obj_list.append(obj)

    def attach_site_full_paths(self) -> None:
        def walk(node: Dict[str, Any], parent_path: List[str]) -> None:
            node_name: str = str(node.get("name") or "").strip()
            current_path: List[str] = parent_path + [node_name]
            node["_site_full_path"] = current_path

            children: List[Dict[str, Any]] = node.get("children") or []
            for child in children:
                walk(child, current_path)

        for root in self.main_category_obj_list:
            walk(root, [])

    def filter_by_keywords(self) -> None:
        self.main_category_obj_filter_list = []

        if not self.keyword_list:
            self.main_category_obj_filter_list = copy.deepcopy(self.main_category_obj_list)
            return

        keyword_path_list: List[List[str]] = []

        for keyword in self.keyword_list:
            keyword_text: str = str(keyword or "").strip()
            if not keyword_text:
                continue

            parts: List[str] = [x.strip() for x in keyword_text.split(">") if str(x).strip()]
            if parts:
                keyword_path_list.append(parts)

        if not keyword_path_list:
            self.main_category_obj_filter_list = copy.deepcopy(self.main_category_obj_list)
            return

        def is_same_path(path1: List[str], path2: List[str]) -> bool:
            if len(path1) != len(path2):
                return False

            for a, b in zip(path1, path2):
                if self.normalize_text(a) != self.normalize_text(b):
                    return False

            return True

        def find_node(node: Dict[str, Any], keyword_path: List[str]) -> Optional[Dict[str, Any]]:
            site_full_path: List[str] = node.get("_site_full_path") or []

            if is_same_path(site_full_path, keyword_path):
                return copy.deepcopy(node)

            children: List[Dict[str, Any]] = node.get("children") or []
            for child in children:
                found: Optional[Dict[str, Any]] = find_node(child, keyword_path)
                if found:
                    return found

            return None

        added_key_set: Set[str] = set()

        for keyword_path in keyword_path_list:
            keyword_key: str = self.make_path_key(keyword_path)

            for root in self.main_category_obj_list:
                found_node: Optional[Dict[str, Any]] = find_node(root, keyword_path)
                if not found_node:
                    continue

                if keyword_key in added_key_set:
                    break

                added_key_set.add(keyword_key)
                self.main_category_obj_filter_list.append(found_node)
                break

        self.log_signal_func(f"✅ 필터링 카테고리 수 : {len(self.main_category_obj_filter_list)}")

    def build_admin_lookup(self) -> None:
        self.admin_lookup_by_path = {}

        if not self.coco_label_admin_list:
            return

        def walk(
                nodes: List[Dict[str, Any]],
                name_path: List[str],
                value_path: List[str],
        ) -> None:
            for node in nodes:
                name: str = str(node.get("name") or "").strip()
                value: str = str(node.get("value") or "").strip()

                next_name_path: List[str] = name_path + [name]
                next_value_path: List[str] = list(value_path)

                if value:
                    next_value_path.append(value)

                path_key: str = self.make_path_key(next_name_path)
                self.admin_lookup_by_path[path_key] = {
                    "name_path": next_name_path,
                    "value_path": next_value_path,
                }

                children: List[Dict[str, Any]] = node.get("children") or []
                if children:
                    walk(children, next_name_path, next_value_path)

        walk(self.coco_label_admin_list, [], [])

    def map_category(self) -> None:
        if not self.main_category_obj_filter_list:
            return

        def walk(node: Dict[str, Any]) -> None:
            site_path: List[str] = node.get("_site_full_path") or []
            mapped: Optional[Dict[str, Any]] = self.resolve_admin_path(site_path)

            if mapped:
                value_path: List[str] = mapped.get("value_path") or []
                name_path: List[str] = mapped.get("name_path") or []

                node["_admin_name_path"] = name_path
                node["_admin_value_path"] = value_path
                node["_mapped_root_name"] = name_path[0] if name_path else ""

                node["기본분류"] = value_path[0] if len(value_path) >= 1 else ""
                node["분류2"] = value_path[1] if len(value_path) >= 2 else ""
                node["분류3"] = value_path[2] if len(value_path) >= 3 else ""

            children: List[Dict[str, Any]] = node.get("children") or []
            for child in children:
                walk(child)

        for root in self.main_category_obj_filter_list:
            walk(root)

    def sub_category_list(self) -> None:
        self.main_sub_category_obj_list = []

        def walk(node: Dict[str, Any]) -> None:
            children: List[Dict[str, Any]] = node.get("children") or []

            if not children:
                href: str = str(node.get("href") or "").strip()
                url: str = f"{self.shop_url}{href}" if href else ""

                full_category_path_codes: List[str] = [
                    str(node.get("기본분류") or "").strip(),
                    str(node.get("분류2") or "").strip(),
                    str(node.get("분류3") or "").strip(),
                ]
                full_category_path_codes = [x for x in full_category_path_codes if x]

                last_category_code: str = full_category_path_codes[-1] if full_category_path_codes else ""
                site_full_path: List[str] = node.get("_site_full_path") or []

                obj: Dict[str, Any] = self.make_empty_row()
                obj["기본분류"] = last_category_code
                obj["분류2"] = ""
                obj["분류3"] = ""
                obj["URL"] = url

                obj["_site_name_path"] = list(site_full_path)
                obj["_site_leaf_name"] = str(node.get("name") or "").strip()
                obj["_href"] = href
                obj["_url"] = url
                obj["_category_code"] = self.extract_category_code(url)
                obj["_category_path_codes"] = full_category_path_codes

                self.main_sub_category_obj_list.append(obj)
                return

            for child in children:
                walk(child)

        for root in self.main_category_obj_filter_list:
            walk(root)

        self.log_signal_func(f"✅ leaf 카테고리 수집 완료 : {len(self.main_sub_category_obj_list)}")

    def get_product_detail(self) -> None:
        self.total_cnt = len(self.main_sub_category_obj_list)
        if self.total_cnt <= 0:
            self.total_cnt = 1

        self.current_cnt = 0

        for base_obj in self.main_sub_category_obj_list:
            if not self.running:
                return

            category_code: str = str(base_obj.get("_category_code", "")).strip()
            category_name: str = " > ".join(base_obj.get("_site_name_path") or [])

            if not category_code:
                self.log_signal_func(f"[WARN] 카테고리 코드 없음: {category_name} / url={base_obj.get('_url')}")
                self.collect_products_from_html(base_obj)
            else:
                self.collect_products_from_ajax(base_obj, category_code, category_name)

            self.current_cnt += 1
            pro_value: float = (self.current_cnt / self.total_cnt) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

    def collect_products_from_html(self, base_obj: Dict[str, Any]) -> None:
        if not self.api_client:
            return

        url: str = str(base_obj.get("_url") or "").strip()
        category_name: str = " > ".join(base_obj.get("_site_name_path") or [])

        if not url:
            return

        response: str = self.api_client.get(url=url, headers=self.headers)
        soup: BeautifulSoup = BeautifulSoup(response, "html.parser")
        items: List[Tag] = soup.select(".shop-item")

        if not items:
            self.log_signal_func(f"[종료] 아이템 없음: {category_name}")
            return

        for item in items:
            if not self.running:
                return

            idx_number: str = self.extract_idx_from_item(item)
            if not idx_number:
                continue

            row: Optional[Dict[str, Any]] = self._crawl_one_product(base_obj, idx_number)
            if not row:
                continue

            self.result.append(row)
            self.excel_driver.append_to_csv(
                self.csv_filename,
                [row],
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

    def collect_products_from_ajax(
            self,
            base_obj: Dict[str, Any],
            category_code: str,
            category_name: str,
    ) -> None:
        if not self.api_client:
            return

        stop: bool = False
        idx_number_list: Set[str] = set()
        href: str = str(base_obj.get("_href") or "").strip()

        for page in range(1, 10000):
            if not self.running:
                return

            if stop:
                break

            params: Dict[str, Any] = {
                "page": page,
                "pagesize": "24",
                "category": category_code,
                "sort": "recent",
                "menu_url": f"{href}/",
                "_": int(time.time() * 1000),
            }

            self.log_signal_func(f"[{category_name}] {page}페이지 조회중...")

            headers_ajax: Dict[str, str] = {
                "authority": "coco-label.com",
                "method": "GET",
                "path": "/ajax/get_shop_list_view.cm",
                "scheme": "https",
                "accept": "application/json, text/javascript, */*; q=0.01",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "priority": "u=0, i",
                "referer": f"https://coco-label.com{href}",
                "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "x-requested-with": "XMLHttpRequest",
                "user-agent": self.headers.get("user-agent", ""),
            }

            data_text: str = self.api_client.get(
                url=self.shop_detail_url,
                params=params,
                headers=headers_ajax,
            )

            try:
                data_json: Dict[str, Any] = json.loads(data_text)
            except Exception as e:
                self.log_signal_func(f"[에러] json 파싱 실패: {category_name} page={page} / {e}")
                break

            html: str = str(data_json.get("html", ""))
            if not html:
                self.log_signal_func(f"[종료] html 비어있음: {category_name} page={page}")
                break

            soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
            items: List[Tag] = soup.select(".shop-item")
            if not items:
                self.log_signal_func(f"[종료] 아이템 없음: {category_name} page={page}")
                break

            for item in items:
                if not self.running:
                    return

                idx_number: str = self.extract_idx_from_item(item)
                if not idx_number:
                    continue

                if idx_number in idx_number_list:
                    self.log_signal_func(f"[중복] {idx_number} 중복 -> 다음 카테고리로 넘어감")
                    stop = True
                    break

                idx_number_list.add(idx_number)

                row: Optional[Dict[str, Any]] = self._crawl_one_product(base_obj, idx_number)
                if not row:
                    continue

                self.result.append(row)
                self.excel_driver.append_to_csv(
                    self.csv_filename,
                    [row],
                    self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
                )

        self.log_signal_func(f"[완료] {category_name} 처리 끝. 수집={len(idx_number_list)}")

    def _crawl_one_product(self, base_obj: Dict[str, Any], idx_number: str) -> Optional[Dict[str, Any]]:
        if not idx_number or not self.api_client:
            return None

        href: str = str(base_obj.get("_href") or "").strip()

        headers_oms: Dict[str, str] = {
            "authority": "coco-label.com",
            "method": "GET",
            "path": "/ajax/oms/OMS_get_products.cm",
            "scheme": "https",
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=1, i",
            "referer": f"https://coco-label.com{href}/?idx={idx_number}",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.headers.get("user-agent", ""),
        }

        detail_url: str = f"{self.shop_url}/ajax/oms/OMS_get_product.cm?prod_idx={idx_number}"
        detail_res: Any = self.api_client.get(url=detail_url, headers=headers_oms)
        detail_data: Dict[str, Any] = self.ensure_dict(detail_res)

        data: Dict[str, Any] = self.ensure_dict(detail_data.get("data"))
        if not data:
            self.log_signal_func(f"[에러] detail data 없음: idx={idx_number}")
            return None

        name: str = str(data.get("name") or "").strip()
        brand: str = str(data.get("brand") or "").strip()
        price: str = self.to_price_str(data.get("price"))
        price_org: str = self.to_price_str(data.get("price_org"))

        self.log_signal_func(f"[상품] idx={idx_number} / {brand} / {name}")

        basic_code: str = str(base_obj.get("기본분류") or "").strip()
        if not basic_code:
            self.log_signal_func(f"[WARN] 분류 코드 없음: idx={idx_number}")
            return None

        category_path_codes: List[str] = base_obj.get("_category_path_codes") or []
        category_path_codes = [str(x).strip() for x in category_path_codes if str(x).strip()]
        if not category_path_codes:
            category_path_codes = [basic_code]

        product_image_urls: List[str] = self.extract_product_image_urls(data)
        product_image_rel_paths: List[str] = self.download_product_images(
            image_links=product_image_urls,
            category_path_codes=category_path_codes,
            idx_number=idx_number,
            prefix="main",
            limit=10,
        )

        content_html: str = str(data.get("content") or "")
        size_wrap_img_links: List[str] = self.extract_size_wrap_image_urls(content_html)
        size_wrap_img_rel_paths: List[str] = self.download_product_images(
            image_links=size_wrap_img_links,
            category_path_codes=category_path_codes,
            idx_number=idx_number,
            prefix="size",
            limit=50,
        )

        detail_img_links: List[str] = self.extract_detail_content_images(content_html)
        detail_img_rel_paths: List[str] = self.download_product_images(
            image_links=detail_img_links,
            category_path_codes=category_path_codes,
            idx_number=idx_number,
            prefix="detail",
            limit=9999,
        )

        final_desc_html: str = self.build_detail_html(
            detail_img_rel_paths=detail_img_rel_paths,
            content_html=content_html,
            size_wrap_img_rel_paths=size_wrap_img_rel_paths,
        )
        option1, option2, option3 = self.build_option_columns(data)
        product_url: str = f"{self.shop_url}{href}/?idx={idx_number}"

        row: Dict[str, Any] = self.make_empty_row()
        row["상품코드"] = idx_number
        row["기본분류"] = basic_code
        row["분류2"] = ""
        row["분류3"] = ""
        row["상품명"] = name
        row["브랜드"] = brand
        row["상품옵션1"] = option1
        row["상품옵션2"] = option2
        row["상품옵션3"] = option3
        row["옵션공통"] = self.OPTION_COMMON_VALUE
        row["상품설명"] = final_desc_html
        row["모바일상품설명"] = final_desc_html
        row["시중가격"] = price_org
        row["판매가격"] = price
        row["판매가능"] = "1"
        row["재고수량"] = "9999"
        row["재고통보수량"] = "100"
        row["URL"] = product_url

        for i in range(10):
            col_name: str = f"이미지{i + 1}"
            if i < len(product_image_rel_paths):
                row[col_name] = self.make_relative_image_path(product_image_rel_paths[i])
            else:
                row[col_name] = ""

        return row

    def get_column_name_list(self) -> List[str]:
        result: List[str] = []

        for col in self.columns or []:
            if isinstance(col, dict):
                col_name: str = (
                        str(col.get("value") or "").strip()
                        or str(col.get("name") or "").strip()
                        or str(col.get("code") or "").strip()
                )
            else:
                col_name = str(col or "").strip()

            if col_name:
                result.append(col_name)

        return result

    def make_empty_row(self) -> Dict[str, Any]:
        return {col: "" for col in self.get_column_name_list()}

    def extract_idx_from_item(self, item: Tag) -> str:
        product_prop: str = str(item.get("data-product-properties") or "")
        if not product_prop:
            return ""

        try:
            prop_json: Dict[str, Any] = json.loads(product_prop)
            return str(prop_json.get("idx") or "").strip()
        except Exception:
            return ""

    def extract_category_code(self, url: str) -> str:
        if not url or not self.api_client:
            return ""

        try:
            response: str = self.api_client.get(url=url, headers=self.headers)
            pattern: str = r"['\"]category['\"]\s*:\s*['\"]([^'\"]+)['\"]"
            match: Optional[re.Match[str]] = re.search(pattern, response)
            return match.group(1).strip() if match else ""
        except Exception as e:
            self.log_signal_func(f"[WARN] category code 추출 실패: {url} / {e}")
            return ""

    def resolve_admin_path(self, site_name_path: List[str]) -> Optional[Dict[str, Any]]:
        if not site_name_path:
            return None

        key2: str = self.make_path_key(site_name_path[:2])
        key1: str = self.make_path_key(site_name_path[:1])

        if key2 in self.CATEGORY_ROOT_MAP:
            mapped_root_name: str = self.CATEGORY_ROOT_MAP[key2]
            remain_names: List[str] = site_name_path[2:]
        elif key1 in self.CATEGORY_ROOT_MAP:
            mapped_root_name = self.CATEGORY_ROOT_MAP[key1]
            remain_names = site_name_path[1:]
        else:
            fallback = self.admin_lookup_by_path.get(self.make_path_key(site_name_path))
            if fallback:
                return fallback
            return None

        admin_name_path: List[str] = [mapped_root_name] + remain_names
        admin_key: str = self.make_path_key(admin_name_path)
        return self.admin_lookup_by_path.get(admin_key)

    def make_path_key(self, names: List[str]) -> str:
        return ">".join(self.normalize_text(x) for x in names if str(x).strip())

    def normalize_text(self, text: Any) -> str:
        return re.sub(r"\s+", "", str(text or "")).strip().lower()

    def ensure_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            try:
                parsed: Any = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}

        return {}

    def to_price_str(self, value: Any) -> str:
        if value is None:
            return ""

        text: str = str(value).strip()
        if not text:
            return ""

        return text.replace(",", "").strip()

    def extract_product_image_urls(self, data: Dict[str, Any]) -> List[str]:
        images: List[Any] = data.get("images") or []
        image_url: Dict[str, str] = data.get("image_url") or {}

        result: List[str] = []
        seen: Set[str] = set()

        for code in images:
            key: str = str(code or "").strip()
            if not key:
                continue

            url: str = str(image_url.get(key) or "").strip()
            if not url:
                continue

            url = self.upgrade_image_size(url)

            if url in seen:
                continue

            seen.add(url)
            result.append(url)

        return result

    def extract_detail_content_images(self, content_html: str) -> List[str]:
        if not content_html.strip():
            return []

        soup: BeautifulSoup = BeautifulSoup(content_html, "html.parser")
        result: List[str] = []
        seen: Set[str] = set()

        for img in soup.find_all("img"):
            if not isinstance(img, Tag):
                continue

            if img.find_parent(class_="size-wrap"):
                continue

            src: str = str(img.get("src") or "").strip()
            if not src or src.startswith("data:image"):
                continue

            src = self.upgrade_image_size(src)
            if src in seen:
                continue

            seen.add(src)
            result.append(src)

        return result

    def extract_size_wrap_image_urls(self, content_html: str) -> List[str]:
        if not content_html.strip():
            return []

        soup: BeautifulSoup = BeautifulSoup(content_html, "html.parser")
        result: List[str] = []
        seen: Set[str] = set()

        for img in soup.select(".size-wrap img"):
            if not isinstance(img, Tag):
                continue

            src: str = str(img.get("src") or "").strip()
            if not src or src.startswith("data:image"):
                continue

            src = self.upgrade_image_size(src)
            if src in seen:
                continue

            seen.add(src)
            result.append(src)

        return result

    def upgrade_image_size(self, url: str) -> str:
        if not url:
            return url

        if "w=368" in url:
            return url.replace("w=368", "w=750")

        if re.search(r"([?&])w=\d+", url):
            return re.sub(r"([?&])w=\d+", r"\1w=750", url)

        if "?" in url:
            return f"{url}&w=750"

        return f"{url}?w=750"

    def build_option_columns(self, data: Dict[str, Any]) -> Tuple[str, str, str]:
        options: List[Any] = data.get("options") or []
        built: List[str] = []

        for opt in options:
            if len(built) >= 3:
                break

            if not isinstance(opt, dict):
                continue

            option_name: str = (
                    str(opt.get("name") or "")
                    or str(opt.get("title") or "")
                    or str(opt.get("label") or "")
                    or str(opt.get("option_name") or "")
            ).strip()

            values_raw: Any = opt.get("value_list")
            values: List[str] = []

            if isinstance(values_raw, dict):
                for _, value in values_raw.items():
                    v: str = str(value or "").strip()
                    if v and v not in values:
                        values.append(v)

            elif isinstance(values_raw, list):
                for value in values_raw:
                    if isinstance(value, dict):
                        v: str = (
                                str(value.get("name") or "")
                                or str(value.get("label") or "")
                                or str(value.get("value") or "")
                        ).strip()
                    else:
                        v = str(value or "").strip()

                    if v and v not in values:
                        values.append(v)

            if option_name and values:
                built.append(f"{option_name}|{','.join(values)}")

        while len(built) < 3:
            built.append("")

        return built[0], built[1], built[2]

    def build_detail_html(
            self,
            detail_img_rel_paths: List[str],
            content_html: str = "",
            size_wrap_img_rel_paths: Optional[List[str]] = None,
    ) -> str:
        size_wrap_html: str = self.extract_size_wrap_html(content_html, size_wrap_img_rel_paths or [])

        html_list: List[str] = [
            '<div class="detail-desc-center-wrap" style="text-align:center;">'
        ]

        for rel_path in detail_img_rel_paths:
            html_list.append(
                f'<div><img src="{self.make_public_image_url(rel_path)}" style="display:block; margin:0 auto;"></div>'
            )

        if size_wrap_html:
            html_list.append(self.build_size_wrap_block(size_wrap_html))

        html_list.append("</div>")
        return "".join(html_list)

    def extract_size_wrap_html(self, content_html: str, size_wrap_img_rel_paths: List[str]) -> str:
        if not content_html.strip():
            return ""

        soup: BeautifulSoup = BeautifulSoup(content_html, "html.parser")
        size_wrap_list: List[Tag] = soup.select(".size-wrap")
        if not size_wrap_list:
            return ""

        html_list: List[str] = []
        img_idx: int = 0

        for size_wrap in size_wrap_list:
            for style_tag in size_wrap.find_all("style"):
                style_tag.decompose()

            for img in size_wrap.find_all("img"):
                if not isinstance(img, Tag):
                    continue

                if img_idx < len(size_wrap_img_rel_paths):
                    img["src"] = self.make_public_image_url(size_wrap_img_rel_paths[img_idx])
                    img_idx += 1
                else:
                    src: str = str(img.get("src") or "").strip()
                    if not src:
                        img.decompose()
                        continue
                    img["src"] = self.upgrade_image_size(src)

                for attr in ["srcset", "sizes", "loading", "width", "height", "style"]:
                    if img.has_attr(attr):
                        del img[attr]

            if size_wrap.has_attr("style"):
                del size_wrap["style"]

            for tag in size_wrap.select(".size-img, .size-table, .table-size, thead th, tbody, tbody td"):
                if tag.has_attr("style"):
                    del tag["style"]

            html_list.append(str(size_wrap))

        return "".join(html_list)

    def build_size_wrap_block(self, size_wrap_html: str) -> str:
        return f"{size_wrap_html}{self.build_size_notice_html()}"

    def get_detail_desc_css(self) -> str:
        return ""

    def build_size_notice_html(self) -> str:
        return (
            '<p class="size-notice">'
            '※사이즈 측정법에 따라 1~3cm 가량 오차가 생길 수 있습니다.'
            '</p>'
        )

    def make_public_image_url(self, relative_path: str) -> str:
        rel: str = relative_path.replace("\\", "/").lstrip("/")
        return f"{self.IMAGE_URL_PREFIX}{rel}"

    def get_existing_file_name_set(self, target_dir: str) -> Set[str]:
        if not os.path.isdir(target_dir):
            return set()

        result: Set[str] = set()

        for file_name in os.listdir(target_dir):
            full_path: str = os.path.join(target_dir, file_name)
            if not os.path.isfile(full_path):
                continue
            if os.path.getsize(full_path) <= 0:
                continue
            result.add(file_name)

        return result

    def download_product_images(
            self,
            image_links: List[str],
            category_path_codes: List[str],
            idx_number: str,
            prefix: str,
            limit: int,
    ) -> List[str]:
        if not image_links:
            return []

        target_dir: str = self.get_item_target_dir(category_path_codes, idx_number)
        os.makedirs(target_dir, exist_ok=True)

        existing_file_name_set: Set[str] = self.get_existing_file_name_set(target_dir)
        result_paths: List[str] = []
        img_headers: Dict[str, str] = {"User-Agent": self.headers.get("user-agent", "")}

        for i, url in enumerate(image_links, start=1):
            if len(result_paths) >= limit:
                break

            file_name: str = f"{idx_number}_{prefix}_{i:02d}.jpg"
            save_path: str = os.path.join(target_dir, file_name)
            relative_path: str = "/".join(category_path_codes + [idx_number, file_name])

            if file_name in existing_file_name_set:
                result_paths.append(relative_path)
                continue

            try:
                response: requests.Response = requests.get(url, headers=img_headers, timeout=40)
                if response.status_code != 200:
                    continue

                img: Image.Image = Image.open(BytesIO(response.content))
                if img.mode != "RGB":
                    img = img.convert("RGB")

                img.save(save_path, "JPEG", quality=100, subsampling=0)
                existing_file_name_set.add(file_name)
                result_paths.append(relative_path)

            except Exception as e:
                self.log_signal_func(f"[이미지에러] idx={idx_number} prefix={prefix} url={url} err={e}")

        return result_paths

    def get_item_target_dir(self, category_path_codes: List[str], idx_number: str) -> str:
        if getattr(sys, "frozen", False):
            root_dir: str = os.path.dirname(sys.executable)
        else:
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

        return os.path.join(root_dir, "data", "item", *category_path_codes, idx_number)

    def make_relative_image_path(self, relative_path: str) -> str:
        return str(relative_path or "").replace("\\", "/").lstrip("/")