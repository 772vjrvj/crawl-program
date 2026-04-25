# -*- coding: utf-8 -*-
from pathlib import Path
from openpyxl import load_workbook


def normalize_excel_folder_link(path_text: str) -> str:
    path_text = (path_text or "").strip()

    # 역슬래시를 엑셀에서 잘 먹는 슬래시로 변경
    path_text = path_text.replace("\\", "/")

    # 앞에 ./ 붙이면 "엑셀 파일 위치 기준" 상대경로 의미가 더 명확함
    if not path_text.startswith("./"):
        path_text = "./" + path_text

    # 폴더 링크는 끝에 / 붙이는 게 안전함
    if not path_text.endswith("/"):
        path_text += "/"

    return path_text


def fix_excel_links(excel_path: str):
    excel_path = Path(excel_path)

    backup_path = excel_path.with_name(excel_path.stem + "_backup" + excel_path.suffix)
    fixed_path = excel_path.with_name(excel_path.stem + "_fixed" + excel_path.suffix)

    wb = load_workbook(excel_path)

    for ws in wb.worksheets:
        header_map = {}

        for cell in ws[1]:
            if cell.value:
                header_map[str(cell.value).strip()] = cell.column

        if "경로" not in header_map:
            continue

        path_col = header_map["경로"]
        fixed_count = 0

        for row in range(2, ws.max_row + 1):
            cell = ws.cell(row=row, column=path_col)
            path_text = str(cell.value or "").strip()

            if not path_text:
                continue

            # hiwork_email 로 시작하는 경로만 수정
            if not path_text.replace("/", "\\").startswith("hiwork_email\\"):
                continue

            link = normalize_excel_folder_link(path_text)

            cell.hyperlink = link
            cell.style = "Hyperlink"

            fixed_count += 1

        print(f"[OK] sheet={ws.title}, 수정={fixed_count}개")

    # 원본 백업
    if not backup_path.exists():
        wb.save(backup_path)

    # 수정본 저장
    wb.save(fixed_path)

    print(f"[DONE] 백업파일: {backup_path}")
    print(f"[DONE] 수정파일: {fixed_path}")


if __name__ == "__main__":
    fix_excel_links("hiwork_email_attachment_list.xlsx")