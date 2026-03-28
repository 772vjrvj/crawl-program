import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from openpyxl import Workbook
from playwright.sync_api import sync_playwright


DETAIL_URL = "https://central.childcare.go.kr/ccef/job/JobOfferSl.jsp"

INPUT_JSON_PATH = Path("resources/customers/childcare/childcare_job_offer_list.json")
OUTPUT_JSON_PATH = Path("resources/customers/childcare/childcare_job_offer_detail_list.json")
OUTPUT_XLSX_PATH = Path("resources/customers/childcare/childcare_job_offer_detail_list.xlsx")

HEADLESS = False
SLEEP_SEC = 0.5
WORKER_COUNT = 8

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def load_list_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"입력 파일이 없습니다: {path}")

    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("입력 JSON은 배열(list)이어야 합니다.")

    return data


def fetch_detail_html(page, joseq: str) -> str:
    payload = {
        "flag": "Sl",
        "JOSEQ": str(joseq),
        "offset": "20",
        "endYn": "N",
    }

    js_code = """
    async ({ url, payload }) => {
        const form = new URLSearchParams();
        for (const [k, v] of Object.entries(payload)) {
            form.append(k, v ?? "");
        }

        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache"
            },
            body: form.toString(),
            credentials: "include"
        });

        return await res.text();
    }
    """
    return page.evaluate(js_code, {"url": DETAIL_URL, "payload": payload})


def parse_detail_html(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.select_one(".com_view tbody")
    if not tbody:
        return {}

    result: Dict[str, str] = {}

    tr_list = tbody.find_all("tr", recursive=False)
    for tr in tr_list:
        memo_td = tr.find("td", class_="con_con")
        if memo_td:
            result["메모"] = clean_text(memo_td.get_text(" ", strip=True))
            continue

        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue

        i = 0
        while i < len(cells) - 1:
            if cells[i].name == "th" and cells[i + 1].name == "td":
                key = clean_text(cells[i].get_text(" ", strip=True))
                value = clean_text(cells[i + 1].get_text(" ", strip=True))

                if key and key != "공유하기":
                    result[key] = value
                i += 2
            else:
                i += 1

    return result


def split_indexed_items(
        items: List[Dict[str, Any]],
        worker_count: int,
) -> List[List[Tuple[int, Dict[str, Any]]]]:
    buckets: List[List[Tuple[int, Dict[str, Any]]]] = [[] for _ in range(worker_count)]

    for idx, item in enumerate(items):
        bucket_index = idx % worker_count
        buckets[bucket_index].append((idx, item))

    return [bucket for bucket in buckets if bucket]


def crawl_detail_batch(
        worker_id: int,
        indexed_items: List[Tuple[int, Dict[str, Any]]],
        total_count: int,
) -> List[Tuple[int, Dict[str, Any]]]:
    worker_results: List[Tuple[int, Dict[str, Any]]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-dev-shm-usage",
            ],
        )

        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="ko-KR",
            viewport={"width": 1400, "height": 1000},
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

        page = context.new_page()
        page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        for idx, item in indexed_items:
            joseq = clean_text(item.get("JOSEQ"))

            if not joseq:
                print(f"[SKIP][W{worker_id}] {idx + 1}/{total_count} JOSEQ 없음")
                failed = dict(item)
                failed["상세조회실패"] = "JOSEQ 없음"
                worker_results.append((idx, failed))
                continue

            try:
                print(f"[INFO][W{worker_id}] {idx + 1}/{total_count} JOSEQ={joseq} 상세조회 중...")
                html = fetch_detail_html(page, joseq)
                detail_obj = parse_detail_html(html)

                merged = dict(item)
                merged.update(detail_obj)

                worker_results.append((idx, merged))
                print(f"[DONE][W{worker_id}] {idx + 1}/{total_count} JOSEQ={joseq}")
            except Exception as e:
                print(f"[ERROR][W{worker_id}] {idx + 1}/{total_count} JOSEQ={joseq} 실패: {e}")
                failed = dict(item)
                failed["상세조회실패"] = str(e)
                worker_results.append((idx, failed))

            time.sleep(SLEEP_SEC)

        context.close()
        browser.close()

    return worker_results


def crawl_detail_all(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total_count = len(items)
    if total_count == 0:
        return []

    actual_worker_count = min(WORKER_COUNT, total_count)
    buckets = split_indexed_items(items, actual_worker_count)

    indexed_results: List[Tuple[int, Dict[str, Any]]] = []

    with ThreadPoolExecutor(max_workers=actual_worker_count) as executor:
        futures = [
            executor.submit(crawl_detail_batch, worker_id + 1, bucket, total_count)
            for worker_id, bucket in enumerate(buckets)
        ]

        for future in as_completed(futures):
            batch_result = future.result()
            indexed_results.extend(batch_result)

    indexed_results.sort(key=lambda x: x[0])
    return [row for _, row in indexed_results]


def save_json(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON 저장 완료: {path} / 총 {len(data)}건")


def build_excel_headers(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return []

    headers: List[str] = []
    seen = set()

    for key in rows[0].keys():
        if key not in seen:
            headers.append(key)
            seen.add(key)

    for row in rows[1:]:
        for key in row.keys():
            if key not in seen:
                headers.append(key)
                seen.add(key)

    return headers


def save_excel(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "detail_list"

    if not data:
        wb.save(path)
        print(f"[INFO] XLSX 저장 완료(빈 파일): {path}")
        return

    headers = build_excel_headers(data)

    ws.append(headers)

    for row in data:
        ws.append([clean_text(row.get(header, "")) for header in headers])

    for column_cells in ws.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter

        for cell in column_cells:
            cell_value = "" if cell.value is None else str(cell.value)
            if len(cell_value) > max_length:
                max_length = len(cell_value)

        adjusted_width = min(max_length + 2, 60)
        ws.column_dimensions[column_letter].width = adjusted_width

    wb.save(path)
    print(f"[INFO] XLSX 저장 완료: {path} / 총 {len(data)}건")


def main():
    items = load_list_json(INPUT_JSON_PATH)
    print(f"[INFO] 목록 로드 완료: {len(items)}건")
    print(f"[INFO] 멀티쓰레드 시작: WORKER_COUNT={WORKER_COUNT}")

    results = crawl_detail_all(items)

    save_json(OUTPUT_JSON_PATH, results)
    save_excel(OUTPUT_XLSX_PATH, results)

    print("[INFO] 전체 작업 완료")


if __name__ == "__main__":
    main()