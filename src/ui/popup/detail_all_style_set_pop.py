from __future__ import annotations

import copy
import json  # === 신규 ===
import os  # === 신규 ===
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.global_state import GlobalState  # === 신규 ===
from src.ui.style.style import create_common_button


class DetailAllStyleSetPop(QDialog):
    def __init__(
            self,
            parent: Optional[QWidget] = None,
            title: str = "필터 설정",
            setting_attr_name: str = "setting_detail_all_style",
    ) -> None:
        super().__init__(parent)

        self._parent: Optional[QWidget] = parent
        self.setting_attr_name: str = setting_attr_name

        self.setWindowTitle(title)
        self.resize(560, 760)
        self.setStyleSheet("background-color: white; color: #111;")

        self.setting_data: List[Dict[str, Any]] = self._load_setting_data()

        self.checkbox_widgets: List[tuple[QCheckBox, Dict[str, Any]]] = []
        self.single_group_widgets: List[tuple[List[QCheckBox], List[Dict[str, Any]]]] = []
        self.line_edit_widgets: List[tuple[QLineEdit, Dict[str, Any]]] = []

        self.init_ui()

    def _load_setting_data(self) -> List[Dict[str, Any]]:
        rows_any: Any = getattr(self._parent, self.setting_attr_name, None)
        if isinstance(rows_any, list):
            return copy.deepcopy(rows_any)
        return []

    # === 신규 === ColumnSetPop 방식 그대로 가져옴
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

    # === 신규 === setting_detail_all_style 통째로 저장
    def _save_setting_data_to_runtime_config(self) -> None:
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

            config_data[self.setting_attr_name] = copy.deepcopy(self.setting_data)

            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                return

        except Exception:
            return

    def init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title_label = QLabel(self.windowTitle())
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #111;")
        title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        root_layout.addWidget(title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
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
        
            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                border: none;
                background: transparent;
                width: 0px;
                height: 0px;
            }
        """)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(12)

        for idx, node in enumerate(self.setting_data):
            self._render_node(node, body_layout, parent_code=None, depth=0)

            if idx < len(self.setting_data) - 1:
                body_layout.addWidget(self._make_divider())

        body_layout.addStretch()
        scroll.setWidget(body)
        root_layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)

        cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)

        root_layout.addLayout(btn_layout)

    def _section_title_style(self, depth: int) -> str:
        if depth == 0:
            return "font-size: 17px; font-weight: bold; color: #111; padding: 10px 0 4px 0;"
        return "font-size: 14px; font-weight: bold; color: #222; padding: 6px 0 2px 0;"

    def _field_title_style(self, depth: int) -> str:
        if depth == 0:
            return "font-size: 17px; font-weight: bold; color: #111; padding: 10px 0 4px 0;"
        return "font-size: 14px; font-weight: bold; color: #222; padding: 4px 0 2px 0;"

    def _render_node(
            self,
            node: Dict[str, Any],
            parent_layout: QVBoxLayout,
            parent_code: Optional[str],
            depth: int = 0,
    ) -> None:
        node_type = str(node.get("type") or "")
        node_code = self._resolve_node_code(node, parent_code)
        node_name = str(node.get("name") or "").strip()

        if node_type == "title":
            section_wrap = QWidget()
            section_layout = QVBoxLayout(section_wrap)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(12 if depth == 0 else 10)

            if node_name:
                lb = QLabel(node_name)
                lb.setStyleSheet(self._section_title_style(depth))
                section_layout.addWidget(lb)

            children = node.get("children") or []
            items = node.get("items") or []

            for child in children:
                if isinstance(child, dict):
                    self._render_node(child, section_layout, node_code, depth + 1)

            if items:
                items_wrap = QWidget()
                items_layout = QGridLayout(items_wrap)
                items_layout.setContentsMargins(0, 4, 0, 0)
                items_layout.setHorizontalSpacing(10)
                items_layout.setVerticalSpacing(10)

                self._render_leaf_items_grid(
                    items=items,
                    grid_layout=items_layout,
                    col_count=3,
                )
                section_layout.addWidget(items_wrap)

            parent_layout.addWidget(section_wrap)
            return

        if node_type in ("checkbox_multi_group", "checkbox_single_group"):
            group_wrap = QWidget()
            group_layout = QVBoxLayout(group_wrap)
            group_layout.setContentsMargins(0, 6, 0, 6)
            group_layout.setSpacing(10)

            if node_name:
                lb = QLabel(node_name)
                lb.setStyleSheet(self._section_title_style(depth))
                group_layout.addWidget(lb)

            items = node.get("items") or []
            children = node.get("children") or []

            if items:
                grid_widget = QWidget()
                grid = QGridLayout(grid_widget)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(10)
                grid.setVerticalSpacing(10)

                if node_type == "checkbox_multi_group":
                    self._render_leaf_items_grid(
                        items=items,
                        grid_layout=grid,
                        col_count=3,
                    )
                else:
                    self._render_single_group_checkboxes(
                        items=items,
                        grid_layout=grid,
                        col_count=3,
                    )

                group_layout.addWidget(grid_widget)

            for child in children:
                if isinstance(child, dict):
                    self._render_node(child, group_layout, node_code, depth + 1)

            parent_layout.addWidget(group_wrap)
            return

        if node_type == "two_input":
            row_wrap = QWidget()
            row_layout = QVBoxLayout(row_wrap)
            row_layout.setContentsMargins(0, 6, 0, 6)
            row_layout.setSpacing(6)

            if node_name:
                lb = QLabel(node_name)
                lb.setStyleSheet(self._field_title_style(depth))
                row_layout.addWidget(lb)

            input_row = QHBoxLayout()
            input_row.setContentsMargins(0, 0, 0, 0)
            input_row.setSpacing(8)

            items = node.get("items") or []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue

                edit = QLineEdit(str(item.get("value") or ""))
                edit.setPlaceholderText(str(item.get("name") or ""))
                edit.setFixedHeight(34)
                edit.setStyleSheet(self.input_style())
                self.line_edit_widgets.append((edit, item))

                input_row.addWidget(edit)

                if idx == 0:
                    dash = QLabel("~")
                    dash.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    dash.setFixedWidth(18)
                    dash.setStyleSheet("font-size: 14px; color: #444;")
                    input_row.addWidget(dash)

            input_row.addStretch()
            row_layout.addLayout(input_row)
            parent_layout.addWidget(row_wrap)
            return

        if node_type == "input":
            row_wrap = QWidget()
            row_layout = QVBoxLayout(row_wrap)
            row_layout.setContentsMargins(0, 6, 0, 6)
            row_layout.setSpacing(6)

            if node_name:
                lb = QLabel(node_name)
                lb.setStyleSheet(self._field_title_style(depth))
                row_layout.addWidget(lb)

            edit = QLineEdit(str(node.get("value") or ""))
            edit.setFixedHeight(34)
            edit.setStyleSheet(self.input_style())
            self.line_edit_widgets.append((edit, node))

            row_layout.addWidget(edit)
            parent_layout.addWidget(row_wrap)
            return

        if node_type == "checkbox":
            cb = self._make_checkbox(node)
            parent_layout.addWidget(cb)
            return

        container_wrap = QWidget()
        container_layout = QVBoxLayout(container_wrap)
        container_layout.setContentsMargins(0, 6, 0, 6)
        container_layout.setSpacing(10)

        children = node.get("children") or []
        items = node.get("items") or []

        if node_name:
            lb = QLabel(node_name)
            lb.setStyleSheet(self._section_title_style(depth))
            container_layout.addWidget(lb)

        if items:
            items_wrap = QWidget()
            items_layout = QGridLayout(items_wrap)
            items_layout.setContentsMargins(0, 4, 0, 0)
            items_layout.setHorizontalSpacing(10)
            items_layout.setVerticalSpacing(10)

            self._render_leaf_items_grid(
                items=items,
                grid_layout=items_layout,
                col_count=3,
            )
            container_layout.addWidget(items_wrap)

        for child in children:
            if isinstance(child, dict):
                self._render_node(child, container_layout, node_code, depth + 1)

        parent_layout.addWidget(container_wrap)

    def _render_leaf_items_grid(
            self,
            items: List[Dict[str, Any]],
            grid_layout: QGridLayout,
            col_count: int = 3,
    ) -> None:
        row = 0
        col = 0

        for item in items:
            if not isinstance(item, dict):
                continue

            item_type = str(item.get("type") or "")

            if item_type == "checkbox":
                cb = self._make_checkbox(item)
                grid_layout.addWidget(cb, row, col)
                col += 1
                if col >= col_count:
                    col = 0
                    row += 1

            elif item_type == "input":
                wrap = QWidget()
                lay = QVBoxLayout(wrap)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(4)

                lb = QLabel(str(item.get("name") or ""))
                lb.setStyleSheet("font-size: 13px; color: #333;")

                edit = QLineEdit(str(item.get("value") or ""))
                edit.setFixedHeight(34)
                edit.setStyleSheet(self.input_style())

                self.line_edit_widgets.append((edit, item))

                lay.addWidget(lb)
                lay.addWidget(edit)
                grid_layout.addWidget(wrap, row, col)

                col += 1
                if col >= col_count:
                    col = 0
                    row += 1

    def _render_single_group_checkboxes(
            self,
            items: List[Dict[str, Any]],
            grid_layout: QGridLayout,
            col_count: int = 3,
    ) -> None:
        checkboxes: List[QCheckBox] = []
        checked_index = -1

        for idx, item in enumerate(items):
            if bool(item.get("value", False)) and checked_index < 0:
                checked_index = idx

        row = 0
        col = 0
        for idx, item in enumerate(items):
            cb = self._make_checkbox(item)
            cb.setChecked(idx == checked_index)
            cb.stateChanged.connect(
                lambda state, current_cb=cb, current_items=items: self._handle_single_group_checkbox(state, current_cb, current_items)
            )
            checkboxes.append(cb)

            grid_layout.addWidget(cb, row, col)
            col += 1
            if col >= col_count:
                col = 0
                row += 1

        self.single_group_widgets.append((checkboxes, items))

    @Slot(int)
    def _handle_single_group_checkbox(
            self,
            state: int,
            current_cb: QCheckBox,
            current_items: List[Dict[str, Any]],
    ) -> None:
        if state != Qt.CheckState.Checked.value:
            any_checked = False
            for checkboxes, items in self.single_group_widgets:
                if items is current_items:
                    any_checked = any(cb.isChecked() for cb in checkboxes)
                    break

            if not any_checked:
                current_cb.blockSignals(True)
                current_cb.setChecked(True)
                current_cb.blockSignals(False)
            return

        for checkboxes, items in self.single_group_widgets:
            if items is not current_items:
                continue

            for cb in checkboxes:
                if cb is current_cb:
                    continue
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            break

    def _resolve_node_code(self, node: Dict[str, Any], parent_code: Optional[str]) -> Optional[str]:
        code = str(node.get("code") or "").strip()
        if code:
            return code
        if parent_code:
            return parent_code
        return None

    def _make_checkbox(self, node: Dict[str, Any]) -> QCheckBox:
        cb = QCheckBox(str(node.get("name") or ""))
        cb.setChecked(bool(node.get("value", False)))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(self.checkbox_style())

        self.checkbox_widgets.append((cb, node))
        return cb

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #e5e5e5; background: #e5e5e5; min-height: 1px; max-height: 1px;")
        return line

    @Slot()
    def confirm_selection(self) -> None:
        for cb, node in self.checkbox_widgets:
            node["value"] = cb.isChecked()

        for edit, node in self.line_edit_widgets:
            node["value"] = edit.text().strip()

        if self._parent is not None:
            setattr(self._parent, self.setting_attr_name, self.setting_data)

        self._save_setting_data_to_runtime_config()  # === 신규 ===

        self.accept()

    def input_style(self) -> str:
        return """
            QLineEdit {
                border: 1px solid #d9d9d9;
                border-radius: 8px;
                padding: 0 10px;
                font-size: 13px;
                color: #222;
                background: white;
            }
            QLineEdit:focus {
                border: 1px solid black;
            }
        """

    def checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 13px;
                color: #222;
                padding: 8px 10px;
                spacing: 8px;
                border: 1px solid #dcdcdc;
                border-radius: 8px;
                background: #fafafa;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #888;
                background: white;
            }
            QCheckBox::indicator:checked {
                background: black;
                border: 1px solid black;
            }
        """