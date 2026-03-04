# /src/utils/excel_utils.py

import pandas as pd
import os
from openpyxl import load_workbook, Workbook   # ✅ 이렇게 맨 위로
from openpyxl.utils import get_column_letter
import csv

class ExcelUtils:
    def __init__(self, log_func=None):
        self.log_func = log_func

    def init_csv(self, filename, columns):
        df = pd.DataFrame(columns=columns)
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        if self.log_func:
            self.log_func(f"CSV 초기화 완료: {filename}")

    def append_to_csv(self, filename, data_list, columns):

        if not data_list:
            return

        df = pd.DataFrame(data_list, columns=columns)
        df.to_csv(filename, mode='a', header=False, index=False, encoding="utf-8-sig")
        data_list.clear()
        if self.log_func:
            self.log_func("csv 저장완료")

    def append_to_excel(self, filename, data_list, columns, sheet_name="Sheet1"):
        if not data_list:
            return

        df = pd.DataFrame(data_list, columns=columns)

        if os.path.exists(filename):
            with pd.ExcelWriter(filename, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                start_row = writer.sheets[sheet_name].max_row if sheet_name in writer.sheets else 0
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=start_row)
        else:
            with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=True)

        data_list.clear()
        if self.log_func:
            self.log_func("excel 저장완료")

    def convert_csv_to_excel_and_delete(self, csv_filename, sheet_name="Sheet1"):
        """
        CSV 파일을 엑셀 파일로 변환 후 CSV 삭제.
        numeric_columns: 숫자로 변환하고 싶은 컬럼 이름 리스트
        """
        if not os.path.exists(csv_filename):
            if self.log_func:
                self.log_func(f"❌ CSV 파일이 존재하지 않습니다: {csv_filename}")
            return

        try:
            df = pd.read_csv(csv_filename, encoding="utf-8-sig", dtype=str)

            if df.empty:
                if self.log_func:
                    self.log_func(f"⚠️ CSV에 데이터가 없습니다: {csv_filename}")
                return

            # === 모든 컬럼을 문자열(str)로 강제 ===
            for col in df.columns:
                df[col] = df[col].apply(
                    lambda v: "" if pd.isna(v) else str(v).strip()
                )

            excel_filename = os.path.splitext(csv_filename)[0] + ".xlsx"

            # 문자열 그대로 저장
            with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)

                ws = writer.sheets[sheet_name]
                # === 엑셀 셀에 문자열 그대로 넣기 (숫자 자동 변환 방지) ===
                for r in ws.iter_rows(min_row=2, max_row=len(df) + 1):
                    for cell in r:
                        if cell.value is not None:
                            cell.value = str(cell.value)  # 무조건 문자열로 기록

            os.remove(csv_filename)

            if self.log_func:
                self.log_func(f"✅ 엑셀 파일 저장 완료: {excel_filename}")
                self.log_func(f"🗑️ CSV 파일 삭제 완료: {csv_filename}")

        except Exception as e:
            if self.log_func:
                self.log_func(f"❌ 변환 중 오류 발생: {e}")

    def obj_to_row(self, o, cols):
        if isinstance(o, dict):
            return {c: o.get(c) for c in cols}
        # 객체 속성에서 추출
        return {c: getattr(o, c, None) for c in cols}

    def obj_list_to_dataframe(self, obj_list, columns=None):
        """
        obj_list 를 pandas.DataFrame 으로 변환
        - obj_list 가 dict 리스트면 그대로 사용
        - 일반 객체 리스트면 __dict__ 또는 지정 columns 기준으로 추출
        """
        if not obj_list:
            return None

        # dict 리스트인 경우
        if isinstance(obj_list[0], dict):
            if columns:
                rows = [{col: obj.get(col) for col in columns} for obj in obj_list]
                return pd.DataFrame(rows, columns=columns)
            return pd.DataFrame(obj_list)

        if columns:
            rows = [self.obj_to_row(o, columns) for o in obj_list]
            return pd.DataFrame(rows, columns=columns)

        # columns 미지정이면 첫 객체의 __dict__ 키 사용
        first = obj_list[0]
        if hasattr(first, "__dict__") and first.__dict__:
            cols = list(first.__dict__.keys())
            rows = [self.obj_to_row(o, cols) for o in obj_list]
            return pd.DataFrame(rows, columns=cols)

        # 마지막 fallback: dir 기반(언더스코어/콜러블 제외)
        cols = [k for k in dir(first) if not k.startswith("_") and not callable(getattr(first, k, None))]
        rows = [self.obj_to_row(o, cols) for o in obj_list]
        return pd.DataFrame(rows, columns=cols)

    def save_obj_list_to_excel(self, filename, obj_list, columns=None, sheet_name="Sheet1"):
        """
        obj_list(객체/딕셔너리 리스트)를 엑셀 파일에 저장합니다.
        - 파일이 존재하면 같은 시트에 '이어쓰기'(header 없이)
        - 파일이 없거나 시트가 없으면 시트를 새로 만들고 header 포함 저장
        - columns 지정 시 해당 컬럼 순서/이름으로 저장
        - URL 포함된 값은 하이퍼링크로 변환
        """
        if not obj_list:
            return

        df = self.obj_list_to_dataframe(obj_list, columns=columns)
        if df is None or df.empty:
            if self.log_func:
                self.log_func("⚠️ 저장할 데이터가 없습니다.")
            return

        # 이어쓰기/신규 작성 처리
        if os.path.exists(filename):
            with pd.ExcelWriter(filename, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                ws = writer.sheets.get(sheet_name)
                if ws is not None:
                    start_row = ws.max_row if ws.max_row is not None else 0
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=start_row)
                else:
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=True)
        else:
            with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=True)

        # === URL 컬럼을 하이퍼링크로 변환 ===
        wb = load_workbook(filename)
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]

            for row in ws.iter_rows(min_row=2):  # 1행은 header라 skip
                for cell in row:
                    val = str(cell.value) if cell.value else ""
                    if val.startswith("http://") or val.startswith("https://"):
                        cell.hyperlink = val
                        cell.style = "Hyperlink"

        wb.save(filename)

        # 원본 리스트 정리 및 로그
        obj_list.clear()
        if self.log_func:
            self.log_func("excel(객체 리스트) 저장완료 (URL 하이퍼링크 처리)")

    def append_rows_text_excel(self, filename, rows, columns, sheet_name="Sheet1"):
        if not rows:
            if self.log_func:
                self.log_func("[EXCEL] 저장할 데이터 없음")
            return

        if os.path.exists(filename):
            wb = load_workbook(filename)

            # === 신규 === sheet_name 없으면 생성해서 그 시트를 사용
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            else:
                ws = wb.create_sheet(title=sheet_name)
                ws.append(columns)  # === 신규 === 새 시트는 헤더부터

            if self.log_func:
                self.log_func(f"[EXCEL] 기존 파일 로드: {filename}")
                self.log_func(f"[EXCEL] 대상 시트: {sheet_name}")  # === 신규 === 디버깅용

        else:
            wb = Workbook()
            ws = wb.active
            ws.title = sheet_name
            ws.append(columns)
            if self.log_func:
                self.log_func(f"[EXCEL] 신규 파일 생성: {filename}")
                self.log_func(f"[EXCEL] 대상 시트: {sheet_name}")  # === 신규 ===

        saved = 0
        for r in rows:
            out = {}
            for c in columns:
                out[c] = r.get(c, "")

            # (기존 유지) 텍스트로 저장
            ws.append([str(out.get(c, "")) for c in columns])

            for col in range(1, len(columns) + 1):
                ws.cell(ws.max_row, col).number_format = "@"

            saved += 1

        wb.save(filename)
        if self.log_func:
            self.log_func(f"[EXCEL] 저장 완료 ({sheet_name}) (추가 {saved}건)")  # === 신규 ===

    def append_row_to_csv(self, csv_filename, item, columns):
        if not columns:
            return

        row = {}
        for c in columns:
            v = item.get(c)
            row[c] = "" if v is None else str(v)

        with open(csv_filename, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writerow(row)

        if self.log_func:
            self.log_func("csv 1행 저장완료")

    def close(self):
        if self.log_func:
            self.log_func("[ExcelUtils] close 호출 (정리할 자원 없음)")