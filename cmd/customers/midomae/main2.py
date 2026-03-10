import csv
import html
import os
from typing import Any, Dict, List


# === 실행 파일(main.py) 기준 ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(ROOT_DIR, "여성의류")

INPUT_CSV = os.path.join(BASE_DIR, "midomae_270_recent_detail.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "midomae_270_recent_detail_with_raw_html.csv")


def read_csv_rows(csv_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    return rows


def write_csv_rows(csv_path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resolve_html_path(html_path: str) -> str:
    html_path = (html_path or "").strip()
    if not html_path:
        return ""

    html_path = html_path.replace("/", os.sep).replace("\\", os.sep)

    # 1) 절대경로면 그대로
    if os.path.isabs(html_path):
        return html_path

    candidates = []

    # 2) 여성의류 기준 그대로
    candidates.append(os.path.join(BASE_DIR, html_path))

    # 3) 파일명만 떼서 여성의류\midomae_html 기준
    filename = os.path.basename(html_path)
    candidates.append(os.path.join(BASE_DIR, "midomae_html", filename))

    # 4) ROOT_DIR 기준
    candidates.append(os.path.join(ROOT_DIR, html_path))

    # 5) 여성의류 바로 아래
    candidates.append(os.path.join(BASE_DIR, filename))

    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        if os.path.exists(candidate):
            return candidate

    return os.path.normpath(candidates[0])


def read_text_file_safely(path: str) -> str:
    encodings = ["utf-8", "utf-8-sig", "cp949", "euc-kr"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue

    return ""


def extract_raw_html_from_file(html_path: str) -> str:
    real_path = resolve_html_path(html_path)

    if not real_path:
        print("    [DEBUG] html_path 비어있음")
        return ""

    if not os.path.exists(real_path):
        print(f"    [DEBUG] 파일 없음: {real_path}")
        return ""

    raw_html = read_text_file_safely(real_path)
    if not raw_html:
        print(f"    [DEBUG] 파일 읽기 실패 또는 빈 파일: {real_path}")
        return ""

    # 저장된 html이 escape 되어 있을 수 있으니 최소 보정
    raw_html = raw_html.replace('\\"', '"')
    raw_html = html.unescape(raw_html)

    print(f"    [DEBUG] 파일 읽음: {real_path} / raw_len={len(raw_html)}")
    return raw_html.strip()


def add_detail_raw_html_column(input_csv: str, output_csv: str) -> None:
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"입력 CSV 파일이 없습니다: {input_csv}")

    rows = read_csv_rows(input_csv)
    result_rows: List[Dict[str, Any]] = []
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        new_row = dict(row)

        html_path = (row.get("detail_html_path") or "").strip()
        raw_html = extract_raw_html_from_file(html_path)

        new_row["detail"] = raw_html
        result_rows.append(new_row)

        print(
            f"[{idx}/{total}] "
            f"html_path={html_path} | "
            f"detail_len={len(raw_html)}"
        )

    write_csv_rows(output_csv, result_rows)
    print(f"[DONE] 저장 완료: {output_csv}")


def main() -> None:
    print(f"ROOT_DIR   : {ROOT_DIR}")
    print(f"BASE_DIR   : {BASE_DIR}")
    print(f"INPUT_CSV  : {INPUT_CSV}")
    print(f"OUTPUT_CSV : {OUTPUT_CSV}")

    add_detail_raw_html_column(
        input_csv=INPUT_CSV,
        output_csv=OUTPUT_CSV,
    )


if __name__ == "__main__":
    main()