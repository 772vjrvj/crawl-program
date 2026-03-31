# src/ui/popup/excel_set_pop.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
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

    # === 신규 === 팝업 재오픈 시 복원용 캐시
    _cached_file_paths: ClassVar[List[str]] = []
    _cached_data_list: ClassVar[List[Dict[str, Any]]] = []
    _cached_user: ClassVar[Optional[UserCred]] = None
    _cached_headers: ClassVar[List[str]] = []
    _cached_rows: ClassVar[List[List[str]]] = []

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("엑셀 파일 드래그 앤 드롭")
        self.resize(800, 600)
        self.setStyleSheet("background-color: white; color: #111;")

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

        # === 신규 === 파일첨부 버튼
        self.attach_button = self._create_action_button(
            text="파일첨부",
            bg_color="white",
            text_color="black",
        )
        self.attach_button.clicked.connect(self.on_attach_file)
        button_layout.addWidget(self.attach_button)

        # === 신규 === 초기화 버튼
        self.reset_button = self._create_action_button(
            text="초기화",
            bg_color="white",
            text_color="black",
        )
        self.reset_button.clicked.connect(self.on_reset)
        button_layout.addWidget(self.reset_button)

        self.confirm_button = self._create_action_button(
            text="확인",
            bg_color="black",
            text_color="white",
        )
        self.confirm_button.clicked.connect(self.on_confirm)
        button_layout.addWidget(self.confirm_button)

        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(button_layout)

        self._center_on_screen()
        self._restore_cache()

    # =========================
    # core
    # =========================
    def _create_action_button(
            self,
            text: str,
            bg_color: str = "black",
            text_color: str = "white",
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setStyleSheet(
            f"""
            background-color: {bg_color};
            color: {text_color};
            border: 1px solid black;
            border-radius: 20px;
            font-size: 14px;
            padding: 10px;
            """
        )
        button.setFixedHeight(40)
        button.setFixedWidth(140)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _center_on_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(avail.center())
        self.move(geo.topLeft())

    def _label_base_style(self) -> str:
        return """
        border: 2px dashed #999;
        border-radius: 10px;
        padding: 20px;
        background-color: white;
        color: #111;
        """

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
        self.drag_drop_label.setStyleSheet(
            self._label_base_style() + "background-color: lightgreen;"
        )

    def _set_error_hint(self, msg: str) -> None:
        self.drag_drop_label.setText(f"파일 로드 중 오류 발생: {msg}")
        self.drag_drop_label.setStyleSheet(
            self._label_base_style() + "background-color: #ffeaea;"
        )

    def _set_default_hint(self) -> None:
        self.drag_drop_label.setText("엑셀 파일을 드래그 앤 드롭 해주세요")
        self.drag_drop_label.setStyleSheet(self._label_base_style())

    # === 신규 === 캐시 저장
    def _save_cache(
            self,
            file_paths: List[str],
            headers: List[str],
            rows: List[List[str]],
            data_list: List[Dict[str, Any]],
            user: Optional[UserCred],
    ) -> None:
        self.__class__._cached_file_paths = list(file_paths)
        self.__class__._cached_headers = list(headers)
        self.__class__._cached_rows = [list(row) for row in rows]
        self.__class__._cached_data_list = [dict(row) for row in data_list]
        self.__class__._cached_user = user

    # === 신규 === 캐시 초기화
    def _clear_cache(self) -> None:
        self.__class__._cached_file_paths = []
        self.__class__._cached_headers = []
        self.__class__._cached_rows = []
        self.__class__._cached_data_list = []
        self.__class__._cached_user = None

    # === 신규 === 캐시 복원
    def _restore_cache(self) -> None:
        if not self.__class__._cached_data_list:
            self._set_default_hint()
            return

        self.data_list = [dict(row) for row in self.__class__._cached_data_list]
        self.user = self.__class__._cached_user

        headers = list(self.__class__._cached_headers)
        rows = [list(row) for row in self.__class__._cached_rows]

        self._render_table(headers=headers, rows=rows)
        self._set_success_hint(
            file_count=len(self.__class__._cached_file_paths),
            row_count=len(rows),
            col_count=len(headers),
        )

    # =========================
    # slots
    # =========================
    @Slot()
    def on_attach_file(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "엑셀 파일 선택",
            "",
            "Excel Files (*.xlsx *.xls *.csv)",
        )
        if file_paths:
            self.load_excel(file_paths)

    @Slot(list)
    def load_excel(self, file_paths: List[str]) -> None:
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
                self.user = cred

        if not dfs:
            self._render_table(headers=[], rows=[])
            self.data_list = []
            self.user = None
            self._clear_cache()
            self._set_error_hint("로드할 수 있는 파일이 없습니다.")
            return

        combined_df = pd.concat(dfs, ignore_index=True, sort=False).fillna("")
        combined_df = combined_df.astype(str)

        headers = [str(c) for c in combined_df.columns]
        rows = combined_df.values.tolist()

        self._render_table(headers=headers, rows=rows)
        self._set_success_hint(file_count=len(file_paths), row_count=len(rows), col_count=len(headers))

        self.data_list = combined_df.to_dict(orient="records")
        self._save_cache(
            file_paths=file_paths,
            headers=headers,
            rows=rows,
            data_list=self.data_list,
            user=self.user,
        )

    @Slot()
    def on_reset(self) -> None:
        self._render_table(headers=[], rows=[])
        self.data_list = []
        self.user = None
        self._clear_cache()
        self._set_default_hint()

    @Slot()
    def on_confirm(self) -> None:
        self.updateList.emit(self.data_list)

        if self.user is not None:
            self.updateUser.emit({"id": self.user.id, "pw": self.user.pw})

        self.accept()