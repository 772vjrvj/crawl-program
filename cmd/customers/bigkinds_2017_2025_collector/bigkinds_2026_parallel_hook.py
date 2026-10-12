from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import math
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page, async_playwright


SITE_URL = "https://www.bigkinds.or.kr/v2/news/search.do"
SEARCH_API_PATH = "/api/news/search.do"
DETAIL_API_PATH = "/news/detailView.do"
START_DATE = "2026-01-01"
END_DATE = "2026-09-30"

CULTURE_CATEGORY_CODES = [
    "004000000",
    "004002000",
    "004011000",
    "004006000",
    "004003000",
    "004007000",
    "004010000",
    "004004000",
    "004008000",
    "004001000",
    "004009000",
    "004005000",
]


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {seconds}초"
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


def progress_info(
    completed: int,
    total: int,
    started_at: float,
    unit: str = "건",
) -> str:
    elapsed = max(time.monotonic() - started_at, 0.001)
    rate = completed / elapsed if completed else 0.0
    remaining = max(total - completed, 0)
    eta_seconds = remaining / rate if rate > 0 else 0.0
    finish_at = datetime.now() + timedelta(seconds=eta_seconds)
    percent = completed / total * 100 if total else 100.0
    return (
        f"{percent:6.2f}% | 속도 {rate:.2f}{unit}/초 | "
        f"경과 {format_seconds(elapsed)} | 남은 예상 {format_seconds(eta_seconds)} | "
        f"완료 예상 {finish_at:%Y-%m-%d %H:%M:%S}"
    )


# 검색·상세 응답을 실제 브라우저 내부에서 후킹한다.
# Python requests는 사용하지 않는다.
NETWORK_HOOK_JS = r"""
(() => {
  if (window.__BIGKINDS_HOOK_INSTALLED__) return;
  window.__BIGKINDS_HOOK_INSTALLED__ = true;

  const store = window.__BIGKINDS_NETWORK__ = {
    sequence: 0,
    responses: []
  };

  const isTarget = (url) => {
    const value = String(url);
    return value.includes('/api/news/search.do') ||
           value.includes('/news/detailView.do');
  };

  const saveResponse = async ({
    transport,
    method,
    url,
    requestBody,
    captureId,
    response
  }) => {
    if (!isTarget(url)) return;

    let text = '';
    let data = null;
    let parseError = null;

    try {
      text = await response.clone().text();
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      parseError = String(error);
    }

    store.responses.push({
      id: ++store.sequence,
      capturedAt: new Date().toISOString(),
      transport,
      captureId: captureId ?? null,
      method,
      url: String(url),
      requestBody: requestBody ?? null,
      status: response.status,
      ok: response.ok,
      data,
      text: data === null ? text : null,
      parseError
    });

    if (store.responses.length > 300) {
      store.responses.splice(0, store.responses.length - 200);
    }
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    const method = init.method || (typeof input === 'string' ? 'GET' : input.method);
    const response = await originalFetch(input, init);

    void saveResponse({
      transport: 'fetch',
      method,
      url,
      requestBody: init.body ?? null,
      captureId: init.__bkCaptureId ?? null,
      response
    });
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__bkMethod = method;
    this.__bkUrl = url;
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function(body) {
    this.__bkRequestBody = body ?? null;
    this.addEventListener('load', () => {
      if (!isTarget(this.__bkUrl)) return;

      let data = null;
      let parseError = null;
      try {
        data = JSON.parse(this.responseText || 'null');
      } catch (error) {
        parseError = String(error);
      }

      store.responses.push({
        id: ++store.sequence,
        capturedAt: new Date().toISOString(),
        transport: 'xhr',
        captureId: null,
        method: this.__bkMethod,
        url: String(this.__bkUrl),
        requestBody: this.__bkRequestBody,
        status: this.status,
        ok: this.status >= 200 && this.status < 300,
        data,
        text: data === null ? this.responseText : null,
        parseError
      });
    });
    return originalSend.call(this, body);
  };
})();
"""


def build_search_payload(page_no: int, page_size: int) -> dict[str, Any]:
    return {
        "indexName": "news",
        "searchKey": "(논란 AND 대응)",
        "searchKeys": [{"andKeywords": ["논란,대응"]}],
        "byLine": "",
        "searchFilterType": "1",
        "searchScopeType": "1",
        "searchSortType": "date",
        "sortMethod": "date",
        "mainTodayPersonYn": "",
        "startDate": START_DATE,
        "endDate": END_DATE,
        "newsIds": None,
        "categoryCodes": CULTURE_CATEGORY_CODES,
        "providerCodes": [],
        "incidentCodes": [],
        "networkNodeType": "",
        "topicOrigin": "",
        "dateCodes": [],
        "editorialIs": False,
        "startNo": page_no,
        "resultNumber": page_size,
        "isTmUsable": False,
        "isNotTmUsable": False,
    }


def build_detail_url(news_id: str) -> str:
    return f"{DETAIL_API_PATH}?{urlencode({'docId': news_id, 'returnCnt': 1, 'sectionDiv': 1000})}"


async def prepare_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    await page.add_init_script(NETWORK_HOOK_JS)
    await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(700)
    await page.evaluate(NETWORK_HOOK_JS)
    return page


async def browser_fetch_json(
    page: Page,
    *,
    url: str,
    method: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_result = await page.evaluate(
        """
        async ({ url, method, payload }) => {
          const captureId = crypto.randomUUID();
          const headers = {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest'
          };
          const options = {
            method,
            credentials: 'include',
            __bkCaptureId: captureId,
            headers
          };

          if (payload !== null) {
            headers['Content-Type'] = 'application/json;charset=UTF-8';
            options.body = JSON.stringify(payload);
          }

          const response = await window.fetch(url, options);
          return { status: response.status, ok: response.ok, captureId };
        }
        """,
        {"url": url, "method": method, "payload": payload},
    )

    capture_id = request_result["captureId"]
    await page.wait_for_function(
        "captureId => window.__BIGKINDS_NETWORK__?.responses.some(item => item.captureId === captureId)",
        arg=capture_id,
        timeout=30_000,
    )
    captured = await page.evaluate(
        "captureId => window.__BIGKINDS_NETWORK__.responses.find(item => item.captureId === captureId)",
        capture_id,
    )

    if not request_result["ok"]:
        raise RuntimeError(
            f"HTTP {request_result['status']} / {captured.get('text') or url}"
        )
    if captured.get("parseError"):
        raise RuntimeError(f"응답 JSON 변환 실패: {captured['parseError']} / {url}")

    data = captured.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"응답이 JSON 객체가 아닙니다: {url}")
    if data.get("success") is False:
        raise RuntimeError(
            f"API 오류: {data.get('errorCode')} / {data.get('errorMessage')}"
        )

    await page.evaluate(
        "captureId => { const s = window.__BIGKINDS_NETWORK__.responses; "
        "const i = s.findIndex(item => item.captureId === captureId); "
        "if (i >= 0) s.splice(i, 1); }",
        capture_id,
    )
    return data


T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int,
    label: str,
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await operation()
        except Exception as error:
            last_error = error
            if attempt < retries:
                wait_seconds = min(0.8 * (2 ** (attempt - 1)), 5.0)
                log(
                    f"[재시도 {attempt}/{retries - 1}] {label} / "
                    f"{type(error).__name__}: {error}"
                )
                await asyncio.sleep(wait_seconds)
    raise RuntimeError(f"{label} 최종 실패: {last_error}") from last_error


async def fetch_search_page(
    page: Page,
    page_no: int,
    page_size: int,
    retries: int,
) -> dict[str, Any]:
    payload = build_search_payload(page_no, page_size)
    return await with_retry(
        lambda: browser_fetch_json(
            page,
            url=SEARCH_API_PATH,
            method="POST",
            payload=payload,
        ),
        retries=retries,
        label=f"목록 페이지 {page_no}",
    )


async def collect_list_parallel(
    pages: list[Page],
    *,
    page_size: int,
    delay: float,
    retries: int,
) -> dict[str, Any]:
    started_at = time.monotonic()
    first_response = await fetch_search_page(pages[0], 1, page_size, retries)
    first_rows = first_response.get("resultList") or []
    total_count = int(first_response.get("totalCount") or 0)
    effective_page_size = len(first_rows) or page_size
    total_pages = math.ceil(total_count / effective_page_size) if total_count else 1

    log(
        f"검색 결과: 총 {total_count:,}건 / "
        f"페이지당 {effective_page_size:,}건 / 총 {total_pages:,}페이지"
    )

    responses: dict[int, dict[str, Any]] = {1: first_response}
    errors: list[dict[str, Any]] = []
    queue: asyncio.Queue[int | None] = asyncio.Queue()
    for page_no in range(2, total_pages + 1):
        queue.put_nowait(page_no)
    for _ in pages:
        queue.put_nowait(None)

    completed = 1
    received_count = len(first_rows)
    log(
        f"목록 진행: {completed:,}/{total_pages:,}페이지 / "
        f"응답 누적 {received_count:,}/{total_count:,}건 | "
        f"{progress_info(completed, total_pages, started_at, '페이지')}"
    )

    async def worker(page: Page) -> None:
        nonlocal completed, received_count
        while True:
            page_no = await queue.get()
            try:
                if page_no is None:
                    return
                try:
                    response = await fetch_search_page(
                        page, page_no, page_size, retries
                    )
                    responses[page_no] = response
                    completed += 1
                    received_count += len(response.get("resultList") or [])
                    log(
                        f"목록 진행: {completed:,}/{total_pages:,}페이지 / "
                        f"방금 완료 {page_no}페이지 / "
                        f"응답 누적 {received_count:,}/{total_count:,}건 | "
                        f"{progress_info(completed, total_pages, started_at, '페이지')}"
                    )
                except Exception as error:
                    errors.append({"pageNo": page_no, "error": str(error)})
                await asyncio.sleep(delay)
            finally:
                queue.task_done()

    tasks = [asyncio.create_task(worker(page)) for page in pages]
    await queue.join()
    await asyncio.gather(*tasks)

    if errors:
        raise RuntimeError(
            f"목록 {len(errors)}개 페이지 수집 실패: "
            + ", ".join(str(item["pageNo"]) for item in errors[:20])
        )

    rows_by_id: dict[str, dict[str, Any]] = {}
    raw_pages: list[dict[str, Any]] = []
    for page_no in sorted(responses):
        response = responses[page_no]
        rows = response.get("resultList") or []
        raw_pages.append(
            {
                "pageNo": page_no,
                "payload": build_search_payload(page_no, page_size),
                "documentCount": response.get("documentCount"),
                "resultList": rows,
            }
        )
        for row in rows:
            news_id = str(row.get("NEWS_ID") or "").strip()
            if news_id:
                rows_by_id[news_id] = row

    if len(rows_by_id) != total_count:
        log(
            f"[주의] API 총 건수 {total_count:,}건과 "
            f"NEWS_ID 중복 제거 후 {len(rows_by_id):,}건이 다릅니다."
        )

    return {
        "searchCondition": {
            "searchKey": "(논란 AND 대응)",
            "startDate": START_DATE,
            "endDate": END_DATE,
            "category": "문화",
        },
        "totalCount": total_count,
        "collectedCount": len(rows_by_id),
        "items": list(rows_by_id.values()),
        "pages": raw_pages,
    }


async def fetch_detail(
    page: Page,
    news_id: str,
    retries: int,
) -> dict[str, Any]:
    return await with_retry(
        lambda: browser_fetch_json(
            page,
            url=build_detail_url(news_id),
            method="GET",
        ),
        retries=retries,
        label=f"상세 {news_id}",
    )


def load_detail_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(item["NEWS_ID"]): item
            for item in saved.get("items", [])
            if item.get("NEWS_ID")
        }
    except Exception as error:
        log(f"[주의] 상세 체크포인트를 읽지 못해 처음부터 진행합니다: {error}")
        return {}


def save_detail_json(
    path: Path,
    result_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    expected_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "startDate": START_DATE,
        "endDate": END_DATE,
        "expectedCount": expected_count,
        "collectedCount": len(result_by_id),
        "failedCount": len(errors),
        "items": list(result_by_id.values()),
        "errors": errors,
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


async def collect_details_parallel(
    pages: list[Page],
    *,
    list_items: list[dict[str, Any]],
    detail_json_path: Path,
    delay: float,
    retries: int,
    checkpoint_every: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    result_by_id = load_detail_checkpoint(detail_json_path)
    errors: list[dict[str, Any]] = []
    pending = [
        item
        for item in list_items
        if str(item.get("NEWS_ID") or "").strip() not in result_by_id
    ]

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    for item in pending:
        queue.put_nowait(item)
    for _ in pages:
        queue.put_nowait(None)

    expected_count = len(list_items)
    completed_this_run = 0
    save_lock = asyncio.Lock()
    started_at = time.monotonic()
    log(
        f"상세 수집: 전체 {expected_count:,}건 / "
        f"기존 {len(result_by_id):,}건 / 이번 실행 {len(pending):,}건"
    )

    async def worker(page: Page) -> None:
        nonlocal completed_this_run
        while True:
            list_item = await queue.get()
            try:
                if list_item is None:
                    return

                news_id = str(list_item.get("NEWS_ID") or "").strip()
                succeeded = False
                try:
                    response = await fetch_detail(page, news_id, retries)
                    result_by_id[news_id] = {
                        "NEWS_ID": news_id,
                        "list": list_item,
                        "response": response,
                    }
                    succeeded = True
                except Exception as error:
                    errors.append(
                        {
                            "NEWS_ID": news_id,
                            "TITLE": list_item.get("TITLE"),
                            "error": str(error),
                        }
                    )

                completed_this_run += 1
                article_date = plain_text(list_item.get("DATE"))
                article_title = plain_text(list_item.get("TITLE"))
                if len(article_title) > 60:
                    article_title = article_title[:60] + "..."
                log(
                    f"상세 진행: {completed_this_run:,}/{len(pending):,}건 / "
                    f"전체 저장 {len(result_by_id):,}/{expected_count:,}건 / "
                    f"이번 실행 성공 {completed_this_run - len(errors):,}건 / "
                    f"실패 {len(errors):,}건 / 최근 {'성공' if succeeded else '실패'} "
                    f"[{article_date}] {article_title} | "
                    f"{progress_info(completed_this_run, len(pending), started_at)}"
                )

                if completed_this_run % checkpoint_every == 0:
                    async with save_lock:
                        save_detail_json(
                            detail_json_path,
                            result_by_id,
                            errors,
                            expected_count,
                        )
                        log(
                            f"체크포인트 저장: {detail_json_path.resolve()} / "
                            f"전체 저장 {len(result_by_id):,}/{expected_count:,}건"
                        )
                await asyncio.sleep(delay)
            finally:
                queue.task_done()

    tasks = [asyncio.create_task(worker(page)) for page in pages]
    await queue.join()
    await asyncio.gather(*tasks)

    save_detail_json(
        detail_json_path,
        result_by_id,
        errors,
        expected_count,
    )
    log(
        f"상세 최종 저장: {detail_json_path.resolve()} / "
        f"성공 {len(result_by_id):,}/{expected_count:,}건 / "
        f"실패 {len(errors):,}건 / "
        f"소요 {format_seconds(time.monotonic() - started_at)}"
    )
    return result_by_id, errors


def plain_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def save_list_files(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "bigkinds_2026_01_09_list.json"
    csv_path = output_dir / "bigkinds_2026_01_09_list.csv"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    columns = [
        "NEWS_ID",
        "DATE",
        "TITLE",
        "SUB_TITLE",
        "CONTENT",
        "CATEGORY_NAMES",
        "PROVIDER",
        "BYLINE",
        "PROVIDER_LINK_PAGE",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=columns)
        writer.writeheader()
        for item in result["items"]:
            writer.writerow({column: plain_text(item.get(column)) for column in columns})
    return json_path, csv_path


def save_detail_csv(
    result_by_id: dict[str, dict[str, Any]],
    output_dir: Path,
) -> Path:
    csv_path = output_dir / "bigkinds_2026_01_09_detail.csv"
    columns = [
        "NEWS_ID",
        "DATE",
        "TITLE",
        "SUB_TITLE",
        "CONTENT",
        "CATEGORY_MAIN",
        "CATEGORY",
        "PROVIDER",
        "BYLINE",
        "PROVIDER_LINK_PAGE",
        "TMS_NE_PERSON",
        "TMS_NE_ORGANIZATION",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=columns)
        writer.writeheader()
        for record in result_by_id.values():
            list_item = record.get("list") or {}
            detail = (record.get("response") or {}).get("detail") or {}
            writer.writerow(
                {
                    column: plain_text(detail.get(column, list_item.get(column, "")))
                    for column in columns
                }
            )
    return csv_path


async def open_context(
    playwright: Any,
    profile_dir: Path,
    headless: bool,
) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    common = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "viewport": {"width": 1500, "height": 950},
        "locale": "ko-KR",
    }
    try:
        return await playwright.chromium.launch_persistent_context(
            channel="chrome",
            **common,
        )
    except Exception:
        return await playwright.chromium.launch_persistent_context(**common)


async def async_main(args: argparse.Namespace) -> None:
    max_workers = max(args.list_workers, args.detail_workers)

    async with async_playwright() as playwright:
        context = await open_context(playwright, args.profile_dir, args.headless)

        # Playwright 페이지를 Python ThreadPoolExecutor에서 공유하지 않고,
        # 하나의 실제 Chrome 안에서 독립 탭을 worker처럼 병렬 실행한다.
        pages = await asyncio.gather(
            *(prepare_page(context) for _ in range(max_workers))
        )

        list_result = await collect_list_parallel(
            pages[: args.list_workers],
            page_size=args.page_size,
            delay=args.list_delay,
            retries=args.retries,
        )
        list_json_path, list_csv_path = save_list_files(
            list_result,
            args.output_dir,
        )

        detail_json_path = args.output_dir / "bigkinds_2026_01_09_detail.json"
        detail_results, detail_errors = await collect_details_parallel(
            pages[: args.detail_workers],
            list_items=list_result["items"],
            detail_json_path=detail_json_path,
            delay=args.detail_delay,
            retries=args.retries,
            checkpoint_every=args.checkpoint_every,
        )
        detail_csv_path = save_detail_csv(detail_results, args.output_dir)

        log(f"목록 JSON : {list_json_path.resolve()}")
        log(f"목록 CSV  : {list_csv_path.resolve()}")
        log(f"상세 JSON : {detail_json_path.resolve()}")
        log(f"상세 CSV  : {detail_csv_path.resolve()}")
        log(
            f"상세 완료 {len(detail_results):,}건 / "
            f"실패 {len(detail_errors):,}건"
        )
        await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="브라우저 JS 후킹으로 2026년 빅카인즈 목록·상세를 병렬 수집합니다."
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--list-workers", type=int, default=4)
    parser.add_argument("--detail-workers", type=int, default=6)
    parser.add_argument("--list-delay", type=float, default=0.25)
    parser.add_argument("--detail-delay", type=float, default=0.35)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".browser-profile-bigkinds"),
    )
    args = parser.parse_args()

    if args.page_size < 1:
        parser.error("--page-size는 1 이상이어야 합니다.")
    if args.list_workers < 1 or args.detail_workers < 1:
        parser.error("worker 수는 1 이상이어야 합니다.")
    if args.retries < 1:
        parser.error("--retries는 1 이상이어야 합니다.")
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every는 1 이상이어야 합니다.")
    return args


def main() -> None:
    asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    main()
