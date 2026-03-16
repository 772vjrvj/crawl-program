# src/ui/popup/column_set_pop.py
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, TypedDict, Any

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
    QGridLayout,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent

from src.core.global_state import GlobalState
from src.ui.style.style import create_common_button


class ColumnItem(TypedDict, total=False):
    """
    columns 원소 타입(실용 고정).
    - code/value는 사실상 필수로 쓰지만, 기존 데이터가 불완전할 수 있어 total=False
    - checked는 없으면 True로 취급
    """
    code: str
    value: str
    checked: bool


class ColumnSetPop(QDialog):
    log_signal = Signal(str)

    confirm_btn: Optional[QPushButton]
    cancel_btn: Optional[QPushButton]
    all_checkbox: Optional[QCheckBox]
    checkbox_map: Dict[str, QCheckBox]

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)

        self.confirm_btn = None
        self.cancel_btn = None
        self.all_checkbox = None
        self.checkbox_map = {}

        self.setWindowTitle("컬럼 선택")
        self.resize(600, 450)
        self.setMinimumWidth(700)
        self.setStyleSheet("background-color: white; color: #111;")

        self.init_ui(parent)

    def init_ui(self, parent: Optional[Any]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title_label = QLabel("출력할 컬럼 선택")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #111;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(title_label)

        # parent.columns 확보 (없으면 안내만 표시하고 종료)
        cols: List[ColumnItem] = []
        if parent is not None and hasattr(parent, "columns"):
            try:
                cols = list(parent.columns)  # type: ignore[attr-defined]
            except Exception:
                cols = []

        if not cols:
            layout.addWidget(QLabel("컬럼 정보가 없습니다."))
            return

        # 전체 선택 체크박스
        self.all_checkbox = QCheckBox("전체 선택")
        self.all_checkbox.setCursor(Qt.PointingHandCursor)
        self.all_checkbox.setStyleSheet(self.checkbox_style())
        self.all_checkbox.stateChanged.connect(self.handle_all_checkbox_click)

        total = len(cols)
        checked_count = sum(1 for c in cols if c.get("checked", True))

        if total > 0 and checked_count == total:
            self.all_checkbox.setCheckState(Qt.Checked)
        elif checked_count == 0:
            self.all_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.all_checkbox.setCheckState(Qt.PartiallyChecked)

        layout.addWidget(self.all_checkbox)

        # 컬럼 체크박스 그리드
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        col_per_row = 5
        for idx, col in enumerate(cols):
            code = str(col.get("code", ""))
            label = str(col.get("value", ""))

            checkbox = QCheckBox(label)
            checkbox.setChecked(col.get("checked", True))
            checkbox.setCursor(Qt.PointingHandCursor)
            checkbox.setStyleSheet(self.checkbox_style())
            checkbox.stateChanged.connect(self.update_all_checkbox_state)

            if code:
                self.checkbox_map[code] = checkbox

            row = idx // col_per_row
            col_in_row = idx % col_per_row
            grid_layout.addWidget(checkbox, row, col_in_row)

        layout.addWidget(grid_widget)

        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 15, 0, 0)

        self.cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        self.confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)

    def handle_all_checkbox_click(self) -> None:
        all_checked = all(cb.isChecked() for cb in self.checkbox_map.values())

        for checkbox in self.checkbox_map.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(not all_checked)
            checkbox.blockSignals(False)

        self.update_all_checkbox_state()

    def update_all_checkbox_state(self) -> None:
        if self.all_checkbox is None:
            return

        total = len(self.checkbox_map)
        checked_count = sum(1 for cb in self.checkbox_map.values() if cb.isChecked())

        self.all_checkbox.blockSignals(True)
        if total > 0 and checked_count == total:
            self.all_checkbox.setCheckState(Qt.Checked)
        elif checked_count == 0:
            self.all_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.all_checkbox.setCheckState(Qt.PartiallyChecked)
        self.all_checkbox.blockSignals(False)

    def _resolve_site_config_path(self) -> Optional[str]:
        try:
            state = GlobalState()
            app_config = state.get(GlobalState.APP_CONFIG) or {}
            site = str(state.get(GlobalState.SITE) or "").strip()
            runtime_dir = str(app_config.get("runtime_dir") or "").strip()

            if not runtime_dir:
                return None

            if not site:
                return None

            app_json_path = os.path.join(runtime_dir, "app.json")
            if not os.path.exists(app_json_path):
                return None

            try:
                with open(app_json_path, "r", encoding="utf-8") as f:
                    app_json = json.load(f)
            except Exception:
                return None

            site_list = app_json.get("site_list") or []
            if not isinstance(site_list, list):
                return None

            config_rel_path = ""
            for site_item in site_list:
                if not isinstance(site_item, dict):
                    continue

                key = str(site_item.get("key") or "").strip()
                if key == site:
                    config_rel_path = str(site_item.get("config_path") or "").strip()
                    break

            if not config_rel_path:
                return None

            config_path = os.path.join(runtime_dir, *config_rel_path.split("/"))
            return os.path.normpath(config_path)

        except Exception:
            return None

    def _save_columns_to_runtime_config(self, cols: List[ColumnItem]) -> None:
        try:
            config_path = self._resolve_site_config_path()
            if not config_path:
                return

            if not os.path.exists(config_path):
                return

            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                return

            config_columns = config_data.get("columns") or []
            if not isinstance(config_columns, list):
                return

            checked_map_by_code: Dict[str, bool] = {}
            checked_map_by_value: Dict[str, bool] = {}

            for col in cols:
                code = str(col.get("code", "") or "").strip()
                value = str(col.get("value", "") or "").strip()
                checked = bool(col.get("checked", False))

                if code:
                    checked_map_by_code[code] = checked

                if value:
                    checked_map_by_value[value] = checked

            for cfg_col in config_columns:
                if not isinstance(cfg_col, dict):
                    continue

                code = str(cfg_col.get("code", "") or "").strip()
                value = str(cfg_col.get("value", "") or "").strip()

                if code in checked_map_by_code:
                    new_checked = checked_map_by_code[code]
                elif value in checked_map_by_value:
                    new_checked = checked_map_by_value[value]
                else:
                    new_checked = False

                cfg_col["checked"] = new_checked

            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                return

        except Exception:
            return

    def confirm_selection(self) -> None:
        """
        parent.columns에 checked 반영.
        - parent가 columns를 가진다고 가정(없으면 그냥 accept)
        """
        parent = self.parent()
        if parent is None or not hasattr(parent, "columns"):
            self.accept()
            return

        try:
            cols = parent.columns  # type: ignore[attr-defined]
        except Exception:
            self.accept()
            return

        for col in cols:
            code = str(col.get("code", ""))
            checkbox = self.checkbox_map.get(code)
            if checkbox is not None:
                col["checked"] = checkbox.isChecked()

        # runtime config.json columns.checked 동기화
        self._save_columns_to_runtime_config(cols)

        self.accept()

    def checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 14px;
                color: #333;
                padding: 4px 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #888888;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: black;
            }
        """

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.update_all_checkbox_state()