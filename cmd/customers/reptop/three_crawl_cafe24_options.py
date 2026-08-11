#!/usr/bin/env python3
"""
products.csv의 상품번호로 렙탑 상품 상세 HTML을 요청하고,
상품 옵션을 Cafe24 옵션 수정용 CSV(13개 컬럼)로 저장한다.

필수 패키지:
    pip install requests beautifulsoup4

기본 실행:
    python crawl_cafe24_options.py

입출력 파일 지정:
    python crawl_cafe24_options.py --input products.csv --output cafe24_options.csv

요청 수 조절:
    python crawl_cafe24_options.py --workers 5 --timeout 20
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_INPUT_FILE = "products.csv"
DEFAULT_OUTPUT_FILE = "cafe24_options.csv"
DEFAULT_FAILURE_FILE = "cafe24_option_failures.csv"
DEFAULT_BASE_URL = "https://reptop.kr/product/detail.html?product_no={product_no}"

CAFE24_HEADERS = [
    "상품코드",
    "상품명",
    "옵션사용",
    "품목 구성방식",
    "옵션 표시방식",
    "옵션입력",
    "옵션 스타일",
    "버튼이미지 설정",
    "색상 설정",
    "추가입력옵션",
    "추가입력옵션 명칭",
    "추가입력옵션 선택/필수여부",
    "입력글자수(자)",
]

FAILURE_HEADERS = [
    "product_no",
    "product_name",
    "url",
    "reason",
]

PLACEHOLDER_OPTION_VALUES = {"", "*", "**"}
SIZE_VALUE_PATTERN = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)?(?:\s*(?:mm|cm|m|인치|inch))?"
    r"|[2-9]?X{0,2}[SL]|FREE|F|OS|ONE\s*SIZE"
    r"|가로.+|세로.+|폭.+|단일\s*사이즈|단일사이즈"
    r")$",
    re.IGNORECASE,
)

_thread_local = threading.local()


@dataclass(frozen=True)
class ProductItem:
    index: int
    product_no: str
    product_name: str


@dataclass
class CrawlResult:
    index: int
    product_no: str
    product_name: str
    url: str
    option_input: str = ""
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="렙탑 상품 옵션을 Cafe24 옵션 수정용 CSV로 변환합니다."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE, help="입력 products.csv 경로")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="결과 CSV 경로")
    parser.add_argument(
        "--failure-output",
        default=DEFAULT_FAILURE_FILE,
        help="옵션 없음/수집 실패 내역 CSV 경로",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="상품 상세 URL. {product_no} 자리표시자를 포함해야 합니다.",
    )
    parser.add_argument("--workers", type=int, default=5, help="동시 요청 수(기본 5)")
    parser.add_argument("--timeout", type=float, default=20.0, help="요청 제한시간 초(기본 20)")
    return parser.parse_args()


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10))
    session.mount("http://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
            "Connection": "keep-alive",
        }
    )
    return session


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = create_session()
        _thread_local.session = session
    return session


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    raw = path.read_bytes()
    text: Optional[str] = None
    used_encoding = ""

    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = raw.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ValueError("CSV 인코딩을 확인할 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.")

    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError("products.csv에 헤더가 없습니다.")

    required = {"product_no", "product_name"}
    missing = required - set(reader.fieldnames)
    if missing:
        raise ValueError("products.csv 필수 컬럼이 없습니다: " + ", ".join(sorted(missing)))

    print(f"입력 파일 인코딩: {used_encoding}")
    return [dict(row) for row in reader]


def load_products(path: Path) -> List[ProductItem]:
    rows = read_csv_rows(path)
    products: List[ProductItem] = []
    seen_product_numbers = set()

    for row in rows:
        product_no = (row.get("product_no") or "").strip()
        product_name = normalize_space(row.get("product_name") or "")

        if not product_no or not product_name:
            continue
        if product_no in seen_product_numbers:
            continue

        seen_product_numbers.add(product_no)
        products.append(
            ProductItem(
                index=len(products),
                product_no=product_no,
                product_name=product_name,
            )
        )

    return products


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def ordered_unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        normalized = normalize_space(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def is_real_option(option_tag: Tag) -> bool:
    value = normalize_space(option_tag.get("value"))
    text = normalize_space(option_tag.get_text(" ", strip=True))

    if value in PLACEHOLDER_OPTION_VALUES:
        return False
    if not text or "옵션을 선택" in text:
        return False
    if re.fullmatch(r"[-─—_\s]+", text):
        return False
    return True


def option_title_from_select(select: Tag, position: int) -> str:
    title = normalize_space(select.get("option_title"))
    if title:
        return title

    row = select.find_parent("tr")
    if row:
        th = row.find("th")
        if th:
            title = normalize_space(th.get_text(" ", strip=True))
            if title:
                return title

    return f"옵션{position}"


def parse_html_option_selects(soup: BeautifulSoup) -> Tuple[List[str], List[List[str]]]:
    selectors = soup.select('select[option_select_element="ec-option-select-finder"]')
    if not selectors:
        selectors = soup.select("select[option_title][product_option_area]")

    grouped: Dict[str, Dict[str, Any]] = {}

    for position, select in enumerate(selectors, start=1):
        title = option_title_from_select(select, position)
        values = ordered_unique(
            option.get_text(" ", strip=True)
            for option in select.find_all("option")
            if is_real_option(option)
        )
        # PC/모바일 영역에 동일한 select가 중복되어도 옵션을 한 번만 만든다.
        sort_no = normalize_space(select.get("option_sort_no"))
        select_name = normalize_space(select.get("name"))
        key = sort_no or select_name or f"{position}:{title}"
        if key not in grouped:
            grouped[key] = {"title": title, "values": []}
        grouped[key]["values"].extend(values)

    titles = [str(item["title"]) for item in grouped.values()]
    value_groups = [ordered_unique(item["values"]) for item in grouped.values()]

    return titles, value_groups


def json_type_contains_product(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() == "product"
    if isinstance(value, list):
        return any(json_type_contains_product(item) for item in value)
    return False


def walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def parse_json_ld_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for obj in walk_json(data):
            if json_type_contains_product(obj.get("@type")):
                products.append(obj)

    return products


def flatten_offers(offers: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    if isinstance(offers, list):
        for item in offers:
            result.extend(flatten_offers(item))
    elif isinstance(offers, dict):
        nested = offers.get("offers")
        if nested is not None:
            result.extend(flatten_offers(nested))
        if offers.get("name"):
            result.append(offers)

    return result


def remove_product_name_prefix(offer_name: str, names: Sequence[str]) -> str:
    normalized_offer = normalize_space(offer_name)
    normalized_names = sorted(
        {normalize_space(name) for name in names if normalize_space(name)},
        key=len,
        reverse=True,
    )

    for name in normalized_names:
        if normalized_offer.casefold().startswith(name.casefold()):
            return normalized_offer[len(name) :].lstrip(" -:：/|")

    return normalized_offer


def infer_single_option_title(values: Sequence[str]) -> str:
    if values and all(SIZE_VALUE_PATTERN.match(normalize_space(value)) for value in values):
        return "사이즈"
    return "옵션"


def split_offer_suffix(suffix: str, option_count: int) -> Optional[List[str]]:
    suffix = normalize_space(suffix)
    if not suffix:
        return None

    if option_count <= 1:
        return [suffix]

    parts = [normalize_space(part) for part in suffix.split("-", option_count - 1)]
    if len(parts) != option_count or any(not part for part in parts):
        return None
    return parts


def merge_json_ld_offer_values(
        soup: BeautifulSoup,
        input_product_name: str,
        titles: List[str],
        value_groups: List[List[str]],
) -> Tuple[List[str], List[List[str]]]:
    json_products = parse_json_ld_products(soup)
    if not json_products:
        return titles, value_groups

    product = max(
        json_products,
        key=lambda item: len(flatten_offers(item.get("offers"))),
    )
    json_product_name = normalize_space(product.get("name"))
    offer_names = [
        normalize_space(offer.get("name"))
        for offer in flatten_offers(product.get("offers"))
        if normalize_space(offer.get("name"))
    ]
    if not offer_names:
        return titles, value_groups

    option_count = len(titles)
    if option_count == 0:
        # HTML에 옵션명이 없을 때 JSON-LD의 offers 이름을 단일 옵션으로 처리한다.
        option_count = 1
        value_groups = [[]]

    while len(value_groups) < option_count:
        value_groups.append([])

    parsed_combinations: List[List[str]] = []
    for offer_name in offer_names:
        suffix = remove_product_name_prefix(
            offer_name,
            [json_product_name, input_product_name],
        )
        parts = split_offer_suffix(suffix, option_count)
        if parts:
            parsed_combinations.append(parts)

    for combination in parsed_combinations:
        for index, value in enumerate(combination):
            value_groups[index].append(value)

    value_groups = [ordered_unique(values) for values in value_groups]

    if not titles and value_groups and value_groups[0]:
        titles = [infer_single_option_title(value_groups[0])]

    return titles, value_groups


def build_cafe24_option_input(titles: Sequence[str], value_groups: Sequence[Sequence[str]]) -> str:
    parts: List[str] = []

    for index, title in enumerate(titles):
        if index >= len(value_groups):
            break

        values = ordered_unique(value_groups[index])
        if not values:
            continue

        safe_title = normalize_space(title).replace("{", "(").replace("}", ")")
        safe_values = [
            normalize_space(value).replace("|", "/").replace("{", "(").replace("}", ")")
            for value in values
        ]
        parts.append(f"{safe_title}{{{'|'.join(safe_values)}}}")

    return "//".join(parts)


def extract_option_input(html: str, input_product_name: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    titles, value_groups = parse_html_option_selects(soup)
    titles, value_groups = merge_json_ld_offer_values(
        soup,
        input_product_name,
        titles,
        value_groups,
    )
    return build_cafe24_option_input(titles, value_groups)


def crawl_product(
        product: ProductItem,
        base_url: str,
        timeout: float,
) -> CrawlResult:
    url = base_url.format(product_no=product.product_no)
    result = CrawlResult(
        index=product.index,
        product_no=product.product_no,
        product_name=product.product_name,
        url=url,
    )

    try:
        response = get_session().get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"

        option_input = extract_option_input(response.text, product.product_name)
        if not option_input:
            result.error = "옵션을 찾지 못했습니다."
        else:
            result.option_input = option_input
    except Exception as exc:  # 개별 상품 실패가 전체 작업을 중단시키지 않도록 한다.
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def result_to_cafe24_row(result: CrawlResult) -> Dict[str, str]:
    has_option = bool(result.option_input)
    return {
        "상품코드": "",
        "상품명": result.product_name,
        "옵션사용": "Y" if has_option else "N",
        "품목 구성방식": "T" if has_option else "",
        "옵션 표시방식": "S" if has_option else "",
        "옵션입력": result.option_input,
        "옵션 스타일": "",
        "버튼이미지 설정": "",
        "색상 설정": "",
        "추가입력옵션": "F",
        "추가입력옵션 명칭": "",
        "추가입력옵션 선택/필수여부": "",
        "입력글자수(자)": "",
    }


def write_cafe24_csv(path: Path, results: Sequence[CrawlResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CAFE24_HEADERS)
        writer.writeheader()
        for result in results:
            writer.writerow(result_to_cafe24_row(result))


def write_failure_csv(path: Path, results: Sequence[CrawlResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FAILURE_HEADERS)
        writer.writeheader()
        for result in results:
            if not result.error:
                continue
            writer.writerow(
                {
                    "product_no": result.product_no,
                    "product_name": result.product_name,
                    "url": result.url,
                    "reason": result.error,
                }
            )


def crawl_all(
        products: Sequence[ProductItem],
        base_url: str,
        timeout: float,
        workers: int,
) -> List[CrawlResult]:
    results: List[CrawlResult] = []
    total = len(products)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(crawl_product, product, base_url, timeout): product
            for product in products
        }

        for completed, future in enumerate(as_completed(future_map), start=1):
            result = future.result()
            results.append(result)
            status = "성공" if result.option_input else "옵션 없음/실패"
            print(
                f"[{completed}/{total}] {status} | "
                f"{result.product_no} | {result.product_name}"
            )

    return sorted(results, key=lambda item: item.index)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    failure_path = Path(args.failure_output)

    if "{product_no}" not in args.base_url:
        raise ValueError("--base-url에는 {product_no} 자리표시자가 필요합니다.")
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {input_path.resolve()}")

    products = load_products(input_path)
    if not products:
        raise ValueError("수집할 상품이 없습니다. product_no, product_name 컬럼을 확인해 주세요.")

    print(f"중복 제거 후 수집 대상: {len(products)}개")
    results = crawl_all(
        products=products,
        base_url=args.base_url,
        timeout=args.timeout,
        workers=args.workers,
    )

    write_cafe24_csv(output_path, results)
    write_failure_csv(failure_path, results)

    success_count = sum(bool(result.option_input) for result in results)
    failure_count = len(results) - success_count
    print()
    print(f"완료: 성공 {success_count}개 / 옵션 없음·실패 {failure_count}개")
    print(f"Cafe24 옵션 CSV: {output_path.resolve()}")
    print(f"실패 내역 CSV: {failure_path.resolve()}")


if __name__ == "__main__":
    main()
