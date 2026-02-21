# src/ui/popup/excel_set_pop.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.ui.popup.excel_drag_drop_label import ExcelDragDropLabel


# =========================
# typed models
# =========================
@dataclass(frozen=True)
class UserCred:
    id: str
    pw: str


# =========================
# dialog
# =========================
class ExcelSetPop(QDialog):
    updateList: Signal = Signal(object)  # list[dict] 전달 (기존 시그니처 유지)
    updateUser: Signal = Signal(object)  # dict 전달 (기존 시그니처 유지)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("엑셀 파일 드래그 앤 드롭")
        self.resize(800, 600)
        self.setStyleSheet("background-color: white;")

        self.data_list: List[Dict[str, Any]] = []
        self.user: Optional[UserCred] = None

        layout = QVBoxLayout(self)

        self.drag_drop_label = ExcelDragDropLabel(self)
        self.drag_drop_label.fileDropped.connect(self.load_excel)
        layout.addWidget(self.drag_drop_label)

        self.table_widget = QTableWidget(self)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        layout.addWidget(self.table_widget)

        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("확인", self)
        self.confirm_button.setStyleSheet(
            """
            background-color: black;
            color: white;
            border-radius: 20px;
            font-size: 14px;
            padding: 10px;
            """
        )
        self.confirm_button.setFixedHeight(40)
        self.confirm_button.setFixedWidth(140)
        self.confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_button.clicked.connect(self.on_confirm)
        button_layout.addWidget(self.confirm_button)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(button_layout)

        # === 신규 === QDesktopWidget 제거(Deprecated) → Qt 스크린으로 중앙 배치
        self._center_on_screen()

    # =========================
    # core
    # =========================
    def _center_on_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(avail.center())
        self.move(geo.topLeft())

    def _read_csv(self, path: str) -> pd.DataFrame:
        base = Path(path).stem
        df = pd.read_csv(path, dtype=str).fillna("")
        df["file"] = base

        # === 신규 === 원본 파일 경로/행번호 저장(원본 반영용)
        df["__excel_path"] = path
        df["__sheet_idx"] = 0
        df["__row_idx"] = df.index + 2  # 1행 헤더 가정
        return df

    def _read_xlsx_first_sheet(self, path: str) -> Tuple[pd.DataFrame, Optional[UserCred]]:
        base = Path(path).stem
        excel_file = pd.ExcelFile(path)

        # 시트1: 데이터
        df1 = excel_file.parse(sheet_name=0, dtype=str).fillna("")
        df1["file"] = base

        # === 신규 === 원본 파일 경로/행번호 저장(원본 반영용)
        df1["__excel_path"] = path
        df1["__sheet_idx"] = 0
        df1["__row_idx"] = df1.index + 2  # 1행 헤더 가정

        # 시트2: 사용자(ID/PW) (기존 유지)
        cred: Optional[UserCred] = None
        if len(excel_file.sheet_names) >= 2:
            df2 = excel_file.parse(sheet_name=1, dtype=str).fillna("")
            if not df2.empty and "ID" in df2.columns and "PW" in df2.columns:
                # NaN은 fillna("") 했지만 안전하게 str 처리
                cred = UserCred(id=str(df2.iloc[0]["ID"]), pw=str(df2.iloc[0]["PW"]))

        return df1, cred

    def _render_table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        self.table_widget.setUpdatesEnabled(False)
        try:
            self.table_widget.clear()
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)

            self.table_widget.setColumnCount(len(headers))
            self.table_widget.setHorizontalHeaderLabels(list(headers))
            self.table_widget.setRowCount(len(rows))

            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    self.table_widget.setItem(r, c, QTableWidgetItem(val))

            header = self.table_widget.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
        finally:
            self.table_widget.setUpdatesEnabled(True)

    def _set_success_hint(self, file_count: int, row_count: int, col_count: int) -> None:
        self.drag_drop_label.setText(f"총 {file_count}개 파일, {row_count}행 {col_count}열 로드 완료")
        self.drag_drop_label.setStyleSheet("background-color: lightgreen;")

    def _set_error_hint(self, msg: str) -> None:
        self.drag_drop_label.setStyleSheet("")  # 기존 성공 배경 제거
        self.drag_drop_label.setText(f"파일 로드 중 오류 발생: {msg}")

    # =========================
    # slots
    # =========================
    @Slot(list)
    def load_excel(self, file_paths: List[str]) -> None:
        # 기존 시그니처 유지: DragDropLabel에서 list[str] emit
        try:
            dfs: List[pd.DataFrame] = []
            self.user = None

            for file in file_paths:
                lower = file.lower()
                if lower.endswith(".csv"):
                    dfs.append(self._read_csv(file))
                    continue

                df1, cred = self._read_xlsx_first_sheet(file)
                dfs.append(df1)
                if cred is not None:
                    # 마지막 파일의 creds로 덮어쓰기 (기존 로직과 동일한 효과)
                    self.user = cred

            if not dfs:
                raise ValueError("로드할 수 있는 파일이 없습니다.")

            combined_df = pd.concat(dfs, ignore_index=True, sort=False).fillna("")
            combined_df = combined_df.astype(str)

            headers = [str(c) for c in combined_df.columns]
            rows = combined_df.values.tolist()  # list[list[str]]

            self._render_table(headers=headers, rows=rows)
            self._set_success_hint(file_count=len(file_paths), row_count=len(rows), col_count=len(headers))

            self.data_list = combined_df.to_dict(orient="records")

        except Exception as e:
            self._render_table(headers=[], rows=[])
            self.data_list = []
            self.user = None
            self._set_error_hint(str(e))

    @Slot()
    def on_confirm(self) -> None:
        self.updateList.emit(self.data_list)

        if self.user is not None:
            # 기존 소비처 호환: dict로 전달
            self.updateUser.emit({"id": self.user.id, "pw": self.user.pw})

        self.accept()