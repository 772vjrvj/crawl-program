from __future__ import annotations

import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag


MAX_WORKERS = 8
TRD_DD = "20260307"
OUTPUT_FILE = "naver_market_all.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept": "application/json, text/plain, */*",
}

COOKIES = {
    "field_list": "12|06E10000"
}

MARKETS = [
    {
        "market_type": "STANDARD",
        "base_url": "https://finance.naver.com/sise/sise_market_sum.naver",
        "sosok": "0",
        "MKT_ID": "STK",
        "MKT_NM": "KOSPI",
    },
    {
        "market_type": "STANDARD",
        "base_url": "https://finance.naver.com/sise/sise_market_sum.naver",
        "sosok": "1",
        "MKT_ID": "KSQ",
        "MKT_NM": "KOSDAQ",
    },
    {
        "market_type": "KONEX",
        "base_url": "https://finance.naver.com/api/sise/konexItemList.nhn",
        "MKT_ID": "KNX",
        "MKT_NM": "KONEX",
    },
]

FIELD_IDS = [
    "quant",
    "amount",
    "open_val",
    "high_val",
    "low_val",
    "listed_stock_cnt",
    "market_sum",
]


def clean_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return " ".join(text.strip().split())


def to_int(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return int(value)

    value = clean_text(str(value)).replace(",", "").replace("%", "").replace("배", "")
    if value == "":
        return 0
    return int(float(value))


def to_float_str(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        return str(value)

    value = clean_text(str(value)).replace(",", "").replace("%", "")
    if value == "":
        return ""
    return value


def parse_fluc_tp_cd(value: str) -> str:
    value = clean_text(value)

    if value in ("상승", "상한"):
        return "1"
    if value in ("하락", "하한"):
        return "2"
    if value == "보합":
        return "0"

    if "상승" in value or "상한" in value:
        return "1"
    if "하락" in value or "하한" in value:
        return "2"
    if "보합" in value:
        return "0"

    return ""


def parse_konex_risefall(value: Any) -> str:
    risefall = to_int(value)

    # 네이버 코넥스 API risefall 값 예시
    # 1: 상한 / 2: 상승 / 3: 보합 / 4: 하한 / 5: 하락
    if risefall in (1, 2):
        return "1"
    if risefall == 3:
        return "0"
    if risefall in (4, 5):
        return "2"

    return ""


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(COOKIES)
    return session


def fetch_standard_page(session: requests.Session, market_info: Dict[str, str], page: int) -> str:
    params: List[Tuple[str, str]] = [
        ("sosok", market_info["sosok"]),
        ("page", str(page)),
    ]

    for field_id in FIELD_IDS:
        params.append(("fieldIds", field_id))

    resp = session.get(market_info["base_url"], params=params, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    return resp.text


def fetch_konex_page(session: requests.Session, market_info: Dict[str, str]) -> Dict[str, Any]:
    params = {
        "targetColumn": "default",
        "sortOrder": "desc",
    }

    resp = session.get(market_info["base_url"], params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def extract_headers(table: Tag) -> List[str]:
    return [
        clean_text(th.get_text())
        for th in table.select("thead tr th")
        if clean_text(th.get_text())
    ]


def extract_stock_info(tr: Tag) -> Tuple[str, str]:
    a_tag = tr.select_one('a[href*="/item/main.naver?code="]')
    if not a_tag:
        return "", ""

    name = clean_text(a_tag.get_text())
    href = a_tag.get("href", "")
    code = href.split("code=")[-1].split("&")[0] if "code=" in href else ""
    return name, code


def extract_row_values(tr: Tag) -> List[str]:
    values: List[str] = []

    for td in tr.find_all("td"):
        a_tag = td.select_one('a[href*="/item/main.naver?code="]')
        if a_tag:
            values.append(clean_text(a_tag.get_text()))
        else:
            values.append(clean_text(td.get_text()))

    return values


def map_row(headers_ko: List[str], values: List[str]) -> Dict[str, str]:
    row: Dict[str, str] = {}

    for i in range(min(len(headers_ko), len(values))):
        row[headers_ko[i]] = values[i]

    return row


def convert_standard_to_row(row: Dict[str, str], market_info: Dict[str, str]) -> Dict[str, Any]:
    current_price = to_int(row.get("현재가", "0"))
    listed_stock_cnt_thousand = to_int(row.get("상장주식수", "0"))

    # 네이버 시세총액 페이지의 상장주식수는 천주 단위
    list_shrs = listed_stock_cnt_thousand * 1000
    market_cap = current_price * list_shrs if current_price and list_shrs else 0

    return {
        "TRD_DD": TRD_DD,
        "ISU_SRT_CD": row.get("종목코드", ""),
        "ISU_CD": "",
        "ISU_ABBRV": row.get("종목명", ""),
        "MKT_NM": market_info["MKT_NM"],
        "SECT_TP_NM": "",
        "TDD_CLSPRC": current_price,
        "FLUC_TP_CD": parse_fluc_tp_cd(row.get("전일비", "")),
        "CMPPREVDD_PRC": "",
        "FLUC_RT": to_float_str(row.get("등락률", "")),
        "TDD_OPNPRC": to_int(row.get("시가", "0")),
        "TDD_HGPRC": to_int(row.get("고가", "0")),
        "TDD_LWPRC": to_int(row.get("저가", "0")),
        "ACC_TRDVOL": to_int(row.get("거래량", "0")),
        "ACC_TRDVAL": to_int(row.get("거래대금", "0")),
        "MKTCAP": market_cap,
        "LIST_SHRS": list_shrs,
        "MKT_ID": market_info["MKT_ID"],
        "CRAWL_TYPE": "NAVER",
    }


def parse_standard_page(html: str, market_info: Dict[str, str]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.type_2")
    if not table:
        return []

    headers_ko = extract_headers(table)
    results: List[Dict[str, Any]] = []

    for tr in table.select("tbody tr"):
        if not tr.find_all("td"):
            continue

        stock_name, stock_code = extract_stock_info(tr)
        if not stock_code:
            continue

        values = extract_row_values(tr)
        row = map_row(headers_ko, values)
        row["종목명"] = stock_name
        row["종목코드"] = stock_code

        results.append(convert_standard_to_row(row, market_info))

    return results


def parse_konex_page(json_data: Dict[str, Any], market_info: Dict[str, str]) -> List[Dict[str, Any]]:
    if not json_data or json_data.get("resultCode") != "success":
        return []

    result = json_data.get("result") or {}
    item_list = result.get("konexItemList") or []

    results: List[Dict[str, Any]] = []

    for item in item_list:
        current_price = to_int(item.get("nowVal"))
        change_val = to_int(item.get("changeVal"))
        open_val = to_int(item.get("openVal"))
        high_val = to_int(item.get("highVal"))
        low_val = to_int(item.get("lowVal"))
        acc_trdvol = to_int(item.get("accQuant"))
        acc_amount_thousand = to_int(item.get("accAmount"))      # 천원 단위
        market_sum_eok = to_int(item.get("marketSum"))           # 억 단위
        list_shrs = to_int(item.get("listedStockCount"))         # 주 단위

        results.append({
            "TRD_DD": TRD_DD,
            "ISU_SRT_CD": clean_text(str(item.get("itemcode", ""))),
            "ISU_CD": "",
            "ISU_ABBRV": clean_text(str(item.get("itemname", ""))),
            "MKT_NM": market_info["MKT_NM"],
            "SECT_TP_NM": "",
            "TDD_CLSPRC": current_price,
            "FLUC_TP_CD": parse_konex_risefall(item.get("risefall")),
            "CMPPREVDD_PRC": abs(change_val),
            "FLUC_RT": to_float_str(item.get("changeRate")),
            "TDD_OPNPRC": open_val,
            "TDD_HGPRC": high_val,
            "TDD_LWPRC": low_val,
            "ACC_TRDVOL": acc_trdvol,
            "ACC_TRDVAL": acc_amount_thousand * 1000,
            "MKTCAP": market_sum_eok * 100_000_000,
            "LIST_SHRS": list_shrs,
            "MKT_ID": market_info["MKT_ID"],
            "CRAWL_TYPE": "NAVER",
        })

    return results


def collect_standard_page(page: int, market_info: Dict[str, str]) -> List[Dict[str, Any]]:
    session = build_session()
    html = fetch_standard_page(session, market_info, page)
    return parse_standard_page(html, market_info)


def collect_market_all(market_info: Dict[str, str]) -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    page = 1

    while True:
        pages = list(range(page, page + MAX_WORKERS))
        page_results: Dict[int, List[Dict[str, Any]]] = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(collect_standard_page, p, market_info): p
                for p in pages
            }

            for future in as_completed(future_map):
                p = future_map[future]
                rows = future.result()
                page_results[p] = rows
                print(f"[{market_info['MKT_NM']}] page={p} rows={len(rows)}")

        stop = False

        for p in sorted(page_results.keys()):
            rows = page_results[p]
            if not rows:
                stop = True
                break
            all_rows.extend(rows)

        if stop:
            break

        page += MAX_WORKERS

    return all_rows


def collect_konex(market_info: Dict[str, str]) -> List[Dict[str, Any]]:
    session = build_session()
    json_data = fetch_konex_page(session, market_info)
    rows = parse_konex_page(json_data, market_info)
    print(f"[{market_info['MKT_NM']}] rows={len(rows)}")
    return rows


def save_to_csv(data: List[Dict[str, Any]], filename: str) -> None:
    if not data:
        print(f"저장할 데이터 없음: {filename}")
        return

    fieldnames = [
        "TRD_DD",
        "ISU_SRT_CD",
        "ISU_CD",
        "ISU_ABBRV",
        "MKT_NM",
        "SECT_TP_NM",
        "TDD_CLSPRC",
        "FLUC_TP_CD",
        "CMPPREVDD_PRC",
        "FLUC_RT",
        "TDD_OPNPRC",
        "TDD_HGPRC",
        "TDD_LWPRC",
        "ACC_TRDVOL",
        "ACC_TRDVAL",
        "MKTCAP",
        "LIST_SHRS",
        "MKT_ID",
        "CRAWL_TYPE",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"CSV 저장 완료: {filename}")


if __name__ == "__main__":
    start_time = time.perf_counter()

    all_result: List[Dict[str, Any]] = []

    for market_info in MARKETS:
        print(f"\n=== {market_info['MKT_NM']} 수집 시작 ===")

        if market_info["market_type"] == "KONEX":
            market_rows = collect_konex(market_info)
        else:
            market_rows = collect_market_all(market_info)

        print(f"=== {market_info['MKT_NM']} 수집 완료: {len(market_rows)}건 ===")
        all_result.extend(market_rows)

    save_to_csv(all_result, OUTPUT_FILE)

    end_time = time.perf_counter()
    elapsed = end_time - start_time

    print(f"\n전체 total={len(all_result)}")
    print(f"총 실행시간: {elapsed:.2f}초")