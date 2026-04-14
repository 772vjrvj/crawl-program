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
    QFrame,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent

from src.core.global_state import GlobalState
from src.ui.style.style import create_common_button


class ColumnItem(TypedDict, total=False):
    code: str
    value: str
    checked: bool
    title: str
    content: str


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
        self.resize(850, 760)
        self.setMinimumSize(760, 560)
        self.setStyleSheet("background-color: white; color: #111;")

        self.init_ui(parent)

    def init_ui(self, parent: Optional[Any]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        title_label = QLabel("출력할 컬럼 선택")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #111;
            padding: 2px 0 4px 0;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(title_label)

        cols: List[ColumnItem] = []
        if parent is not None and hasattr(parent, "columns"):
            try:
                cols = list(parent.columns)  # type: ignore[attr-defined]
            except Exception:
                cols = []

        if not cols:
            empty_label = QLabel("컬럼 정보가 없습니다.")
            empty_label.setStyleSheet("font-size: 14px; color: #666; padding: 12px 0;")
            empty_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty_label)
            return

        selectable_cols = [
            col for col in cols
            if not self._is_title_item(col) and not self._is_content_item(col)
        ]

        self.all_checkbox = QCheckBox("전체 선택")
        self.all_checkbox.setCursor(Qt.PointingHandCursor)
        self.all_checkbox.setStyleSheet(self.checkbox_style())
        self.all_checkbox.stateChanged.connect(self.handle_all_checkbox_click)

        total = len(selectable_cols)
        checked_count = sum(1 for c in selectable_cols if c.get("checked", True))

        if total > 0 and checked_count == total:
            self.all_checkbox.setCheckState(Qt.Checked)
        elif checked_count == 0:
            self.all_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.all_checkbox.setCheckState(Qt.PartiallyChecked)

        layout.addWidget(self.all_checkbox)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(self.scroll_style())

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        grid_widget = QWidget()
        grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(6)

        col_per_row = 5
        item_min_width = 150

        row = 0
        col_idx = 0

        for idx in range(col_per_row):
            grid_layout.setColumnStretch(idx, 1)
            grid_layout.setColumnMinimumWidth(idx, item_min_width)

        for col in cols:
            if self._is_title_item(col):
                title_text = str(col.get("title", "") or "").strip()
                if not title_text:
                    continue

                if col_idx != 0:
                    row += 1
                    col_idx = 0

                section_widget = self.make_section_title_widget(title_text)
                grid_layout.addWidget(section_widget, row, 0, 1, col_per_row)
                row += 1
                continue

            if self._is_content_item(col):
                content_text = str(col.get("content", "") or "").strip()
                if not content_text:
                    continue

                if col_idx != 0:
                    row += 1
                    col_idx = 0

                content_widget = self.make_section_content_widget(content_text)
                grid_layout.addWidget(content_widget, row, 0, 1, col_per_row)
                row += 1
                continue

            code = str(col.get("code", "") or "").strip()
            label = str(col.get("value", "") or "").strip()

            checkbox = QCheckBox(label)
            checkbox.setChecked(col.get("checked", True))
            checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
            checkbox.setStyleSheet(self.checkbox_style())
            checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            checkbox.setMinimumWidth(0)
            checkbox.stateChanged.connect(self.update_all_checkbox_state)

            if code:
                self.checkbox_map[code] = checkbox

            grid_layout.addWidget(checkbox, row, col_idx)
            col_idx += 1

            if col_idx >= col_per_row:
                col_idx = 0
                row += 1

        body_layout.addWidget(grid_widget)

        scroll.setWidget(body)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)

        self.cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        self.confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)

    def _is_title_item(self, col: ColumnItem) -> bool:
        return bool(str(col.get("title", "") or "").strip())

    def _is_content_item(self, col: ColumnItem) -> bool:
        return bool(str(col.get("content", "") or "").strip())

    def make_section_title_widget(self, title: str) -> QWidget:
        wrap = QWidget()

        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 10, 0, 2)
        layout.setSpacing(0)

        label = QLabel(title)
        label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #111;
            padding: 4px 2px 6px 2px;
        """)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addWidget(label)
        return wrap

    def make_section_content_widget(self, content: str) -> QWidget:
        wrap = QWidget()

        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(content)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setStyleSheet("""
            font-size: 12px;
            font-weight: normal;
            color: #666666;
            background: #f5f5f5;
            border: 1px solid #e3e3e3;
            border-radius: 4px;
            padding: 2px 10px;
            line-height: 1.2;
        """)

        layout.addWidget(label)
        return wrap

    def handle_all_checkbox_click(self) -> None:
        if not self.checkbox_map:
            return

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
            self.all_checkbox.setCheckState(Qt.CheckState.Checked)
        elif checked_count == 0:
            self.all_checkbox.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
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
                if self._is_title_item(col) or self._is_content_item(col):
                    continue

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

                if self._is_title_item(cfg_col) or self._is_content_item(cfg_col):
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
            if self._is_title_item(col) or self._is_content_item(col):
                continue

            code = str(col.get("code", "") or "").strip()
            checkbox = self.checkbox_map.get(code)

            if checkbox is not None:
                col["checked"] = checkbox.isChecked()

        self._save_columns_to_runtime_config(cols)
        self.accept()

    def checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 14px;
                color: #333;
                padding: 6px 8px;
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

    def scroll_style(self) -> str:
        return """
            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }

            QScrollBar:horizontal {
                height: 8px;
                background: transparent;
            }

            QScrollBar::handle:vertical {
                min-height: 20px;
                background: rgba(120, 120, 120, 160);
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal {
                min-width: 20px;
                background: rgba(120, 120, 120, 160);
                border-radius: 4px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                border: none;
                background: transparent;
                width: 0px;
                height: 0px;
            }
        """

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.update_all_checkbox_state()