import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

import xlsxwriter


class ExcelHybridUtils:
    """
    Excel 하이브리드 유틸.

    현재 구현 범위
    - 새 .xlsx 대량 생성: XlsxWriter

    추후 필요 시
    - 기존 .xlsx 읽기/수정: openpyxl 기반 기능을 이 클래스에 추가한다.

    기존 ExcelUtils는 다른 기능에서 계속 사용하므로 이 유틸과 완전히 분리한다.
    """

    HYPERLINK_PREFIX = "__HYPERLINK__"

    def __init__(self, log_func=None):
        self.log_func = log_func

    # =========================================================
    # 공통 경로
    # =========================================================
    def get_default_output_dir(self) -> str:
        return os.path.join(os.path.expanduser("~"), "Documents")

    def resolve_output_dir(self, folder_path=None) -> str:
        folder_path = str(folder_path or "").strip()
        output_dir = folder_path if folder_path else self.get_default_output_dir()
        os.makedirs(output_dir, exist_ok=True)

        if self.log_func:
            self.log_func(f"[EXCEL-XW] 저장 폴더: {output_dir}")

        return output_dir

    def build_file_path(self, filename, folder_path=None, sub_dir=None) -> str:
        output_dir = self.resolve_output_dir(folder_path)

        if sub_dir:
            output_dir = os.path.join(output_dir, str(sub_dir))

        os.makedirs(output_dir, exist_ok=True)

        filename = os.path.basename(str(filename or "").strip())
        if not filename:
            raise ValueError("filename 이 비어 있습니다.")

        if not filename.lower().endswith(".xlsx"):
            filename = os.path.splitext(filename)[0] + ".xlsx"

        full_path = os.path.join(output_dir, filename)

        if self.log_func:
            self.log_func(f"[EXCEL-XW] 저장 파일 경로: {full_path}")

        return full_path

    # =========================================================
    # 값 / 하이퍼링크 처리
    # =========================================================
    @staticmethod
    def _clean_cell_value(value: Any) -> str:
        if value is None:
            return ""

        text = str(value).strip()
        # Excel에 저장할 수 없는 제어문자 제거. \t, \n, \r은 허용한다.
        return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", text)

    def _parse_hyperlink_value(self, value: Any) -> Optional[Dict[str, str]]:
        text = self._clean_cell_value(value)
        if not text.startswith(self.HYPERLINK_PREFIX):
            return None

        raw_json = text[len(self.HYPERLINK_PREFIX):].strip()
        if not raw_json:
            return None

        try:
            obj = json.loads(raw_json)
        except Exception:
            return None

        url = self._clean_cell_value(obj.get("url"))
        display_text = self._clean_cell_value(obj.get("text"))

        if not url or not display_text:
            return None

        return {"url": url, "text": display_text}

    @staticmethod
    def _build_width_map(column_widths: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, float]:
        width_map: Dict[str, float] = {}

        for item in column_widths or []:
            col_name = str(item.get("컬럼") or "").strip()
            if not col_name:
                continue

            try:
                width_map[col_name] = float(item.get("너비"))
            except Exception:
                continue

        return width_map

    # =========================================================
    # XlsxWriter 대량 쓰기
    # =========================================================
    def save_db_sheets_to_excel(
            self,
            excel_filename,
            sheets,
            folder_path=None,
            sub_dir=None,
            return_path=False,
    ):
        """
        새 xlsx 파일을 XlsxWriter로 생성한다.

        핵심 원칙
        - 기존 파일을 읽거나 수정하지 않는다.
        - constant_memory 모드로 행 순서대로 직접 기록한다.
        - pandas DataFrame / openpyxl을 거치지 않는다.
        - 하이퍼링크는 지정된 컬럼만 검사한다.

        sheet_info 지원 키
        - sheet_name
        - row_list
        - columns
        - header_map
        - column_widths
        - default_width
        - hyperlink_columns
        """
        if not sheets:
            if self.log_func:
                self.log_func("⚠️ [EXCEL-XW] 저장할 시트가 없습니다.")
            return None if return_path else False

        try:
            excel_path = self.build_file_path(
                excel_filename,
                folder_path=folder_path,
                sub_dir=sub_dir,
            )
        except Exception as e:
            if self.log_func:
                self.log_func(f"❌ [EXCEL-XW] 저장 경로 생성 실패: {e}")
            return None if return_path else False

        workbook = None

        try:
            # 대량 데이터 신규 생성 전용 설정.
            # 문자열을 수식/URL로 자동 추정하지 않고 우리가 지정한 링크 컬럼만 처리한다.
            workbook = xlsxwriter.Workbook(
                excel_path,
                {
                    "constant_memory": True,
                    "strings_to_formulas": False,
                    "strings_to_urls": False,
                },
            )

            header_format = workbook.add_format({
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#BFBFBF",
            })
            hyperlink_format = workbook.get_default_url_format()

            written_sheet_count = 0

            for sheet_index, sheet_info in enumerate(sheets, start=1):
                row_list = sheet_info.get("row_list") or []
                if not row_list:
                    continue

                sheet_name = str(
                    sheet_info.get("sheet_name") or f"Sheet{sheet_index}"
                ).strip()
                columns: List[str] = list(sheet_info.get("columns") or [])

                if not columns:
                    first_row = row_list[0] if row_list else {}
                    if isinstance(first_row, dict):
                        columns = list(first_row.keys())

                if not columns:
                    if self.log_func:
                        self.log_func(f"⚠️ [EXCEL-XW] 컬럼 없음 - 시트 스킵: {sheet_name}")
                    continue

                if len(row_list) + 1 > 1_048_576:
                    raise ValueError(
                        f"Excel 최대 행 수 초과: {sheet_name} | rows={len(row_list)}"
                    )

                header_map = sheet_info.get("header_map") or {}
                display_headers = [
                    str(header_map.get(col) or col)
                    for col in columns
                ]

                hyperlink_columns = {
                    str(name or "").strip()
                    for name in (sheet_info.get("hyperlink_columns") or [])
                    if str(name or "").strip()
                }
                hyperlink_indexes = {
                    idx
                    for idx, header in enumerate(display_headers)
                    if str(header).strip() in hyperlink_columns
                }

                default_width = float(sheet_info.get("default_width", 16) or 16)
                width_map = self._build_width_map(sheet_info.get("column_widths"))

                if self.log_func:
                    self.log_func(
                        f"[EXCEL-XW] 시트 작성 시작: {sheet_name} | "
                        f"rows={len(row_list)} | cols={len(columns)}"
                    )

                worksheet = workbook.add_worksheet(sheet_name[:31])
                worksheet.freeze_panes(1, 0)

                # 컬럼 너비는 실제 표시 헤더명을 기준으로 설정한다.
                for col_idx, header in enumerate(display_headers):
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        width_map.get(str(header), default_width),
                    )

                # 헤더도 셀별 write() 대신 한 행으로 기록한다.
                worksheet.write_row(0, 0, display_headers, header_format)

                # 일반 데이터는 write_row()로 한 번에 기록하고,
                # 링크 컬럼만 같은 행에서 write_url()로 덮어쓴다.
                # 스타일/필터/틀고정 구조는 그대로 유지하면서 Python 호출 횟수를 줄인다.
                hyperlink_index_list = sorted(hyperlink_indexes)

                for row_idx, row in enumerate(row_list, start=1):
                    row_dict = row if isinstance(row, dict) else {}

                    values = [
                        self._clean_cell_value(row_dict.get(column, ""))
                        for column in columns
                    ]

                    worksheet.write_row(row_idx, 0, values)

                    for col_idx in hyperlink_index_list:
                        raw_value = row_dict.get(columns[col_idx], "")
                        parsed = self._parse_hyperlink_value(raw_value)

                        if parsed:
                            worksheet.write_url(
                                row_idx,
                                col_idx,
                                parsed["url"],
                                hyperlink_format,
                                parsed["text"],
                            )
                            continue

                        text = values[col_idx]
                        if text.startswith("http://") or text.startswith("https://"):
                            worksheet.write_url(
                                row_idx,
                                col_idx,
                                text,
                                hyperlink_format,
                                text,
                            )

                worksheet.autofilter(
                    0,
                    0,
                    len(row_list),
                    len(columns) - 1,
                    )

                written_sheet_count += 1

                if self.log_func:
                    self.log_func(f"✅ [EXCEL-XW] 시트 작성 완료: {sheet_name}")

            if written_sheet_count == 0:
                if workbook:
                    workbook.close()
                    workbook = None
                try:
                    if os.path.exists(excel_path):
                        os.remove(excel_path)
                except Exception:
                    pass

                if self.log_func:
                    self.log_func("⚠️ [EXCEL-XW] 실제 저장할 데이터가 없습니다.")
                return None if return_path else False

            # 실제 xlsx ZIP 생성/압축은 close()에서 한 번 수행된다.
            if self.log_func:
                self.log_func("[EXCEL-XW] 파일 최종 저장 중...")

            workbook.close()
            workbook = None

            if self.log_func:
                self.log_func(f"✅ [EXCEL-XW] 다중 시트 저장 완료: {excel_path}")

            return excel_path if return_path else True

        except PermissionError as e:
            if self.log_func:
                self.log_func(f"❌ [EXCEL-XW] 파일 열림/권한 오류: {e}")
            return None if return_path else False

        except Exception as e:
            if self.log_func:
                self.log_func(f"❌ [EXCEL-XW] 저장 실패: {type(e).__name__}: {e}")
            return None if return_path else False

        finally:
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:
                    pass

    def close(self) -> None:
        """현재는 상태를 보유하지 않으므로 호환용 no-op."""
        return None
