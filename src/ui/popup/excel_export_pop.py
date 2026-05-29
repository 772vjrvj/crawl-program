# src/ui/popup/excel_export_pop.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.style.style import create_common_button


class ExcelExportPop(QDialog):
    """
    엑셀 저장 시 출력할 컬럼과 저장 경로를 선택하는 팝업
    """
    def __init__(
            self,
            columns: List[Dict[str, Any]],
            default_folder: str,
            parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)

        self.columns = columns
        self.default_folder = default_folder

        self.checkbox_map: Dict[str, QCheckBox] = {}
        self.all_checkbox: Optional[QCheckBox] = None
        self.folder_input: Optional[QLineEdit] = None

        # 팝업 결과 데이터
        self.selected_columns: List[str] = []
        self.selected_folder: str = ""

        self.setWindowTitle("엑셀 저장 설정")
        self.resize(650, 400)
        self.setStyleSheet("background-color: white; color: #111;")

        self.init_ui()

    def init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        # ==========================================
        # 1. 상단: 컬럼 선택 섹션
        # ==========================================
        col_section = QWidget()
        col_layout = QVBoxLayout(col_section)
        col_layout.setContentsMargins(0, 0, 0, 0)

        col_title = QLabel("출력할 컬럼 선택")
        col_title.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 8px;")
        col_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_layout.addWidget(col_title)

        # 컬럼 그리드를 좌우 중앙 정렬하기 위한 래퍼
        center_col_layout = QHBoxLayout()
        center_col_layout.addStretch()

        # 스크롤 가능한 영역 구성
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(self.scroll_style())
        scroll.setMinimumWidth(550)

        inner_widget = QWidget()
        inner_layout = QVBoxLayout(inner_widget)
        inner_layout.setContentsMargins(10, 10, 10, 10)

        self.all_checkbox = QCheckBox("전체 선택")
        self.all_checkbox.setChecked(True)
        self.all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_checkbox.setStyleSheet(self.checkbox_style())
        self.all_checkbox.stateChanged.connect(self.handle_all_checkbox_click)
        inner_layout.addWidget(self.all_checkbox)

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 10, 0, 0)
        grid_layout.setHorizontalSpacing(15)
        grid_layout.setVerticalSpacing(10)

        col_per_row = 4
        row, col_idx = 0, 0

        for col in self.columns:
            code = str(col.get("code", ""))
            value = str(col.get("value", ""))
            if not code:
                continue

            cb = QCheckBox(value)
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(self.checkbox_style())
            cb.stateChanged.connect(self.update_all_checkbox_state)

            self.checkbox_map[code] = cb
            grid_layout.addWidget(cb, row, col_idx)

            col_idx += 1
            if col_idx >= col_per_row:
                col_idx = 0
                row += 1

        inner_layout.addWidget(grid_widget)
        inner_layout.addStretch()

        scroll.setWidget(inner_widget)
        center_col_layout.addWidget(scroll)
        center_col_layout.addStretch()

        col_layout.addLayout(center_col_layout)
        root_layout.addWidget(col_section)

        # ==========================================
        # 2. 하단: 파일 저장 경로 섹션
        # ==========================================
        folder_section = QWidget()
        folder_layout = QVBoxLayout(folder_section)
        folder_layout.setContentsMargins(0, 25, 0, 0)
        folder_layout.setSpacing(10)

        folder_title = QLabel("파일 저장 경로")
        folder_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        folder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_layout.addWidget(folder_title)

        # 인풋과 버튼 너비 고정 및 좌우 중앙 정렬
        folder_input_layout = QHBoxLayout()
        folder_input_layout.addStretch()

        self.folder_input = QLineEdit()
        self.folder_input.setText(self.default_folder)
        self.folder_input.setPlaceholderText("폴더를 선택하세요")
        self.folder_input.setFixedSize(380, 38)
        self.folder_input.setStyleSheet(self.input_style())
        folder_input_layout.addWidget(self.folder_input)

        folder_btn = QPushButton("폴더 선택")
        folder_btn.setFixedSize(90, 38)
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.setStyleSheet(self.button_style())
        folder_btn.clicked.connect(self.on_folder_pick)
        folder_input_layout.addWidget(folder_btn)

        folder_input_layout.addStretch()
        folder_layout.addLayout(folder_input_layout)

        root_layout.addWidget(folder_section)

        root_layout.addStretch(1)

        # ==========================================
        # 3. 최하단: 확인/취소 버튼
        # ==========================================
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)

        cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        confirm_btn = create_common_button("확인", self.on_confirm, "black", 140)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        btn_layout.addStretch()

        root_layout.addLayout(btn_layout)

    # --- 이벤트 핸들러 ---
    def handle_all_checkbox_click(self) -> None:
        if not self.checkbox_map or not self.all_checkbox:
            return

        all_checked = self.all_checkbox.isChecked()
        for cb in self.checkbox_map.values():
            cb.blockSignals(True)
            cb.setChecked(all_checked)
            cb.blockSignals(False)

    def update_all_checkbox_state(self) -> None:
        if not self.all_checkbox:
            return

        total = len(self.checkbox_map)
        checked = sum(1 for cb in self.checkbox_map.values() if cb.isChecked())

        self.all_checkbox.blockSignals(True)
        if total > 0 and checked == total:
            self.all_checkbox.setCheckState(Qt.CheckState.Checked)
        elif checked == 0:
            self.all_checkbox.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        self.all_checkbox.blockSignals(False)

    def on_folder_pick(self) -> None:
        start_dir = self.folder_input.text() if self.folder_input else ""
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")

        path = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", start_dir)
        if path and self.folder_input:
            self.folder_input.setText(path)

    def on_confirm(self) -> None:
        self.selected_columns = [
            code for code, cb in self.checkbox_map.items() if cb.isChecked()
        ]
        self.selected_folder = self.folder_input.text().strip() if self.folder_input else ""
        self.accept()

    # --- 스타일 지정 ---
    def checkbox_style(self) -> str:
        return """
            QCheckBox { font-size: 14px; color: #333; padding: 4px; }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border-radius: 4px; border: 2px solid #888;
                background-color: white;
            }
            QCheckBox::indicator:checked { background-color: black; }
        """

    def scroll_style(self) -> str:
        return """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 8px; background: transparent; }
            QScrollBar::handle:vertical {
                background: rgba(120, 120, 120, 160); border-radius: 4px;
            }
        """

    def input_style(self) -> str:
        return """
            QLineEdit {
                border-radius: 6px;
                border: 1px solid #c0c0c0;
                padding: 0 10px;
                font-size: 13px;
                color: #111;
            }
            QLineEdit:focus { border: 1px solid #111; }
        """

    def button_style(self) -> str:
        return """
            QPushButton {
                background-color: black;
                color: white;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #333; }
        """