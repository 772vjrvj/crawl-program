from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import bigkinds_2026_parallel_hook as core
from playwright.async_api import async_playwright


DEFAULT_START_YEAR = 2017
DEFAULT_END_YEAR = 2025


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_list_files(result: dict[str, Any], year_dir: Path) -> tuple[Path, Path]:
    json_path = year_dir / "list.json"
    csv_path = year_dir / "list.csv"
    write_json(json_path, result)

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
            writer.writerow(
                {column: core.plain_text(item.get(column)) for column in columns}
            )
    return json_path, csv_path


def save_detail_csv(
    result_by_id: dict[str, dict[str, Any]],
    list_items: list[dict[str, Any]],
    year_dir: Path,
) -> Path:
    csv_path = year_dir / "detail.csv"
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

        # 병렬 완료 순서가 아니라 목록의 날짜 정렬 순서대로 저장한다.
        for list_item in list_items:
            news_id = str(list_item.get("NEWS_ID") or "").strip()
            record = result_by_id.get(news_id)
            if not record:
                continue
            detail = (record.get("response") or {}).get("detail") or {}
            writer.writerow(
                {
                    column: core.plain_text(
                        detail.get(column, list_item.get(column, ""))
                    )
                    for column in columns
                }
            )
    return csv_path


def is_completed(year_dir: Path) -> bool:
    marker_path = year_dir / "complete.json"
    required_paths = [
        year_dir / "list.json",
        year_dir / "list.csv",
        year_dir / "detail.json",
        year_dir / "detail.csv",
    ]
    if not marker_path.exists() or not all(path.exists() for path in required_paths):
        return False

    try:
        marker = read_json(marker_path)
        return bool(marker.get("success"))
    except Exception:
        return False


def load_saved_list(year_dir: Path, year: int) -> dict[str, Any] | None:
    list_path = year_dir / "list.json"
    if not list_path.exists():
        return None

    try:
        result = read_json(list_path)
        condition = result.get("searchCondition") or {}
        expected_start = f"{year}-01-01"
        expected_end = f"{year}-12-31"

        if condition.get("startDate") != expected_start:
            return None
        if condition.get("endDate") != expected_end:
            return None
        if not isinstance(result.get("items"), list):
            return None

        core.log(
            f"[{year}] 기존 목록 사용: "
            f"{len(result['items']):,}건 ({list_path.resolve()})"
        )
        return result
    except Exception as error:
        core.log(f"[{year}] 기존 목록을 읽지 못해 다시 수집합니다: {error}")
        return None


async def collect_year(
    year: int,
    *,
    pages: list[Any],
    output_root: Path,
    page_size: int,
    list_workers: int,
    detail_workers: int,
    list_delay: float,
    detail_delay: float,
    retries: int,
    checkpoint_every: int,
    force: bool,
) -> dict[str, Any]:
    year_dir = output_root / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    if is_completed(year_dir) and not force:
        marker = read_json(year_dir / "complete.json")
        core.log(
            f"[{year}] 이미 완료되어 건너뜁니다: "
            f"{marker.get('detailCount', 0):,}건"
        )
        return marker

    core.START_DATE = f"{year}-01-01"
    core.END_DATE = f"{year}-12-31"

    started_at = datetime.now().isoformat(timespec="seconds")
    started_monotonic = time.monotonic()
    status: dict[str, Any] = {
        "year": year,
        "startDate": core.START_DATE,
        "endDate": core.END_DATE,
        "startedAt": started_at,
        "success": False,
    }
    write_json(year_dir / "status.json", status)

    core.log("=" * 72)
    core.log(f"[{year}] 수집 시작: {core.START_DATE} ~ {core.END_DATE}")

    list_result = None if force else load_saved_list(year_dir, year)
    if list_result is None:
        list_result = await core.collect_list_parallel(
            pages[:list_workers],
            page_size=page_size,
            delay=list_delay,
            retries=retries,
        )
        list_json_path, list_csv_path = save_list_files(list_result, year_dir)
        core.log(f"[{year}] 목록 JSON: {list_json_path.resolve()}")
        core.log(f"[{year}] 목록 CSV : {list_csv_path.resolve()}")

    list_items = list_result["items"]
    detail_json_path = year_dir / "detail.json"

    if force:
        # 강제 실행은 목록을 다시 받고, 상세도 기존 체크포인트를 사용하지 않는다.
        if detail_json_path.exists():
            detail_json_path.unlink()

    detail_results, detail_errors = await core.collect_details_parallel(
        pages[:detail_workers],
        list_items=list_items,
        detail_json_path=detail_json_path,
        delay=detail_delay,
        retries=retries,
        checkpoint_every=checkpoint_every,
    )
    detail_csv_path = save_detail_csv(detail_results, list_items, year_dir)

    list_count = len(list_items)
    detail_count = len(detail_results)
    failed_count = len(detail_errors)
    success = detail_count == list_count and failed_count == 0

    status.update(
        {
            "finishedAt": datetime.now().isoformat(timespec="seconds"),
            "elapsedSeconds": round(time.monotonic() - started_monotonic, 1),
            "success": success,
            "apiTotalCount": list_result.get("totalCount", 0),
            "listCount": list_count,
            "detailCount": detail_count,
            "failedCount": failed_count,
            "files": {
                "listJson": str((year_dir / "list.json").resolve()),
                "listCsv": str((year_dir / "list.csv").resolve()),
                "detailJson": str(detail_json_path.resolve()),
                "detailCsv": str(detail_csv_path.resolve()),
            },
        }
    )
    write_json(year_dir / "status.json", status)

    if success:
        write_json(year_dir / "complete.json", status)
        core.log(
            f"[{year}] 완료: 목록 {list_count:,}건 / 상세 {detail_count:,}건 / "
            f"실패 0건 / 총 소요 "
            f"{core.format_seconds(time.monotonic() - started_monotonic)}"
        )
    else:
        core.log(
            f"[{year}] 일부 실패: 목록 {list_count:,}건 / "
            f"상세 {detail_count:,}건 / 실패 {failed_count:,}건"
        )
        core.log(f"[{year}] 다시 실행하면 누락된 상세부터 이어서 진행합니다.")
    return status


def save_summary(output_root: Path, statuses: list[dict[str, Any]]) -> None:
    summary = {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "startYear": min(item["year"] for item in statuses) if statuses else None,
        "endYear": max(item["year"] for item in statuses) if statuses else None,
        "successYears": [item["year"] for item in statuses if item.get("success")],
        "failedYears": [item["year"] for item in statuses if not item.get("success")],
        "totalListCount": sum(int(item.get("listCount") or 0) for item in statuses),
        "totalDetailCount": sum(int(item.get("detailCount") or 0) for item in statuses),
        "years": statuses,
    }
    write_json(output_root / "summary_2017_2025.json", summary)


async def async_main(args: argparse.Namespace) -> None:
    args.output_root.mkdir(parents=True, exist_ok=True)
    max_workers = max(args.list_workers, args.detail_workers)
    statuses: list[dict[str, Any]] = []
    overall_started_at = time.monotonic()
    total_years = args.end_year - args.start_year + 1

    core.log(
        f"수집 범위: {args.start_year}~{args.end_year} / "
        f"목록 worker {args.list_workers} / 상세 worker {args.detail_workers}"
    )
    core.log(f"저장 경로: {args.output_root.resolve()}")

    async with async_playwright() as playwright:
        context = await core.open_context(
            playwright,
            args.profile_dir,
            args.headless,
        )
        pages = await asyncio.gather(
            *(core.prepare_page(context) for _ in range(max_workers))
        )

        try:
            for year_index, year in enumerate(
                range(args.start_year, args.end_year + 1),
                start=1,
            ):
                core.log(
                    f"전체 연도 진행: {year_index}/{total_years} / "
                    f"현재 {year}년"
                )
                try:
                    status = await collect_year(
                        year,
                        pages=pages,
                        output_root=args.output_root,
                        page_size=args.page_size,
                        list_workers=args.list_workers,
                        detail_workers=args.detail_workers,
                        list_delay=args.list_delay,
                        detail_delay=args.detail_delay,
                        retries=args.retries,
                        checkpoint_every=args.checkpoint_every,
                        force=args.force,
                    )
                except Exception as error:
                    status = {
                        "year": year,
                        "startDate": f"{year}-01-01",
                        "endDate": f"{year}-12-31",
                        "finishedAt": datetime.now().isoformat(timespec="seconds"),
                        "success": False,
                        "error": f"{type(error).__name__}: {error}",
                    }
                    write_json(args.output_root / str(year) / "status.json", status)
                    core.log(f"[{year}] 연도 수집 실패: {status['error']}")

                statuses.append(status)
                save_summary(args.output_root, statuses)
                core.log(
                    f"전체 연도 진행: {year_index}/{total_years} 완료 | "
                    f"{core.progress_info(year_index, total_years, overall_started_at, '연도')}"
                )

                if year < args.end_year:
                    core.log(f"다음 연도 시작 전 {args.year_delay:.1f}초 대기")
                    await asyncio.sleep(args.year_delay)
        finally:
            await context.close()

    succeeded = [item for item in statuses if item.get("success")]
    failed = [item for item in statuses if not item.get("success")]
    core.log("=" * 72)
    core.log(
        f"전체 종료: 성공 {len(succeeded)}개 연도 / 미완료 {len(failed)}개 연도 / "
        f"총 소요 {core.format_seconds(time.monotonic() - overall_started_at)}"
    )
    core.log(f"요약: {(args.output_root / 'summary_2017_2025.json').resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="2017~2025년 빅카인즈 목록·상세를 연도별 병렬 수집합니다."
    )
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--page-size", type=int, default=100)

    # 2026년 6개 상세 worker가 안정적으로 끝났으므로 실용적인 고속값으로 확장한다.
    parser.add_argument("--list-workers", type=int, default=8)
    parser.add_argument("--detail-workers", type=int, default=12)
    parser.add_argument("--list-delay", type=float, default=0.15)
    parser.add_argument("--detail-delay", type=float, default=0.25)
    parser.add_argument("--year-delay", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("output") / "bigkinds",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".browser-profile-bigkinds"),
    )
    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year는 --end-year보다 클 수 없습니다.")
    if args.start_year < 1990 or args.end_year > 2025:
        parser.error("이 파일의 수집 범위는 2025년까지입니다.")
    if args.page_size < 1:
        parser.error("--page-size는 1 이상이어야 합니다.")
    if args.list_workers < 1 or args.detail_workers < 1:
        parser.error("worker 수는 1 이상이어야 합니다.")
    if args.list_workers > 16 or args.detail_workers > 16:
        parser.error("안정성을 위해 worker는 최대 16개까지만 허용합니다.")
    if args.retries < 1:
        parser.error("--retries는 1 이상이어야 합니다.")
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every는 1 이상이어야 합니다.")
    return args


def main() -> None:
    asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    main()
