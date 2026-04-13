import re
from pathlib import Path

import pandas as pd


DOWNLOAD_DIR = Path("seongnam_downloads")
OUTPUT_FILE = Path("민원현황_통합.xlsx")

FILE_PATTERN = re.compile(r"^민원현황_(\d{4})-(\d{2})\.(xlsx|xls|xlsm|xlsb)$", re.IGNORECASE)


def find_excel_files(folder: Path) -> list[tuple[int, int, Path]]:
    results: list[tuple[int, int, Path]] = []

    if not folder.exists():
        raise FileNotFoundError(f"폴더가 없습니다: {folder.resolve()}")

    for path in folder.iterdir():
        if not path.is_file():
            continue

        match = FILE_PATTERN.match(path.name)
        if not match:
            continue

        year = int(match.group(1))
        month = int(match.group(2))
        results.append((year, month, path))

    results.sort(key=lambda x: (x[0], x[1]))
    return results


def read_excel_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()

    if suffix in [".xlsx", ".xlsm"]:
        return pd.read_excel(path, engine="openpyxl")

    if suffix == ".xls":
        return pd.read_excel(path)

    if suffix == ".xlsb":
        return pd.read_excel(path, engine="pyxlsb")

    return pd.read_excel(path)


def merge_excels(download_dir: Path, output_file: Path) -> Path:
    excel_files = find_excel_files(download_dir)

    if not excel_files:
        raise FileNotFoundError(
            f"'{download_dir}' 폴더 안에서 '민원현황_YYYY-MM.xlsx' 형식의 파일을 찾지 못했습니다."
        )

    frames: list[pd.DataFrame] = []
    file_rows: list[dict] = []

    for year, month, path in excel_files:
        print(f"[읽는중] {path.name}")

        df = read_excel_file(path)
        df["년"] = year
        df["월"] = month
        df["기준년월"] = f"{year:04d}-{month:02d}"
        df["원본파일명"] = path.name

        frames.append(df)

        file_rows.append(
            {
                "년": year,
                "월": month,
                "기준년월": f"{year:04d}-{month:02d}",
                "파일명": path.name,
                "행수": len(df),
                "열수": len(df.columns),
            }
        )

    merged_df = pd.concat(frames, ignore_index=True, sort=False)
    file_list_df = pd.DataFrame(file_rows)

    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        merged_df.to_excel(writer, sheet_name="통합데이터", index=False)
        file_list_df.to_excel(writer, sheet_name="파일목록", index=False)

        ws1 = writer.sheets["통합데이터"]
        ws2 = writer.sheets["파일목록"]

        ws1.freeze_panes = "A2"
        ws2.freeze_panes = "A2"

        for ws in [ws1, ws2]:
            for col_cells in ws.columns:
                max_length = 0
                col_letter = col_cells[0].column_letter
                for cell in col_cells:
                    value = "" if cell.value is None else str(cell.value)
                    if len(value) > max_length:
                        max_length = len(value)
                ws.column_dimensions[col_letter].width = min(max(max_length + 2, 10), 40)

    return output_file.resolve()


def main():
    output_path = merge_excels(DOWNLOAD_DIR, OUTPUT_FILE)
    print(f"\n[완료] 통합 파일 저장: {output_path}")


if __name__ == "__main__":
    main()
