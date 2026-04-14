# src/ui/popup/region_filter_favorite_pop.py
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.global_state import GlobalState
from src.ui.style.style import create_common_button
from src.utils.file_utils import FileUtils


class RegionFilterFavoriteSetPop(QDialog):
    log_signal: Signal = Signal(str)
    confirm_signal: Signal = Signal(list, list, list)

    def __init__(
            self,
            parent: Optional[QWidget] = None,
            title: str = "지역 | 필터 | 즐겨찾기",
            setting_attr_name: str = "setting_detail_all_style",
            favorite_attr_name: str = "setting_detail_all_style_favorites",
            selected_regions: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(parent)

        self._parent = parent
        self.setting_attr_name = setting_attr_name
        self.favorite_attr_name = favorite_attr_name
        self.selected_regions = selected_regions or []

        self.setWindowTitle(title)
        self.resize(1540, 820)
        self.setMinimumSize(1450, 760)
        self.setStyleSheet("background-color: white; color: #111;")

        self.file_driver = FileUtils(self.log_signal.emit)
        self.json_name = "naver_loc_all_real.json"
        self.resource_sub_dir = "customers/naver_place_loc_all"

        self.loc_all: list[dict[str, Any]] = self.load_region_data()
        self.setting_data: list[dict[str, Any]] = self._load_setting_data()
        self.favorite_data: list[dict[str, Any]] = self._load_favorite_data()

        self.checkbox_widgets: list[tuple[QCheckBox, dict[str, Any]]] = []
        self.single_group_widgets: list[tuple[list[QCheckBox], list[dict[str, Any]]]] = []
        self.line_edit_widgets: list[tuple[QLineEdit, dict[str, Any]]] = []

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(self.tree_style())
        self.tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.select_all_checkbox = QCheckBox("전체 선택", self)
        self.select_all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_checkbox.setStyleSheet(self.left_checkbox_style())
        self.select_all_checkbox.stateChanged.connect(self.on_select_all_changed)

        self.filter_scroll: Optional[QScrollArea] = None
        self.filter_body: Optional[QWidget] = None
        self.filter_body_layout: Optional[QVBoxLayout] = None

        self.favorite_scroll: Optional[QScrollArea] = None
        self.favorite_body: Optional[QWidget] = None
        self.favorite_list_layout: Optional[QVBoxLayout] = None

        self.init_ui()

    # =========================
    # init ui
    # =========================
    def init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title_label = QLabel(self.windowTitle(), self)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #111; padding: 4px 0;")
        root_layout.addWidget(title_label)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        left_wrap = self.build_region_panel()
        center_wrap = self.build_filter_panel()
        right_wrap = self.build_favorite_panel()

        content_layout.addWidget(left_wrap, 4)
        content_layout.addWidget(self.make_vertical_divider())
        content_layout.addWidget(center_wrap, 5)
        content_layout.addWidget(self.make_vertical_divider())
        content_layout.addWidget(right_wrap, 4)

        root_layout.addLayout(content_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)

        confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)
        root_layout.addLayout(btn_layout)

        self.populate_tree()
        self.tree.itemChanged.connect(self.on_item_changed)
        self.render_filter_panel_body()
        self.render_favorite_list()

    def build_region_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("지역 선택")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #111; padding: 4px 0;")
        layout.addWidget(title)

        layout.addWidget(self.select_all_checkbox)
        layout.addWidget(self.tree)

        return wrap

    def build_filter_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        title = QLabel("필터 설정")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #111; padding: 4px 0;")

        reset_btn = QPushButton("초기화")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFixedHeight(34)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #efefef;
                color: #111;
                border: none;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e3e3e3;
            }
        """)
        reset_btn.clicked.connect(self.reset_filter_to_default)

        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(reset_btn)

        layout.addLayout(top_row)

        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.filter_scroll.setStyleSheet(self.scroll_style())

        self.filter_body = QWidget()
        self.filter_body_layout = QVBoxLayout(self.filter_body)
        self.filter_body_layout.setContentsMargins(4, 4, 4, 10)
        self.filter_body_layout.setSpacing(12)

        self.filter_scroll.setWidget(self.filter_body)
        layout.addWidget(self.filter_scroll)

        return wrap

    def render_filter_panel_body(self) -> None:
        if self.filter_body_layout is None:
            return

        self.checkbox_widgets = []
        self.single_group_widgets = []
        self.line_edit_widgets = []

        while self.filter_body_layout.count():
            item = self.filter_body_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

        for idx, node in enumerate(self.setting_data):
            self._render_node(node, self.filter_body_layout, parent_code=None, depth=0)
            if idx < len(self.setting_data) - 1:
                self.filter_body_layout.addWidget(self._make_divider())

        self.filter_body_layout.addStretch()

    def build_favorite_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)  # 8 -> 6, 위아래 간격 살짝 줄임

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, -2, 0, 0)  # 살짝 위로
        top_row.setSpacing(8)

        title = QLabel("즐겨찾기")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #111; padding: 0;")

        add_btn = QPushButton("즐겨찾기 추가")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(32)  # 34 -> 32, 제목이랑 높이 더 잘 맞음
        add_btn.setStyleSheet("""
            QPushButton {
                background: black;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #222;
            }
        """)
        add_btn.clicked.connect(self.add_favorite)

        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(add_btn)

        layout.addLayout(top_row)

        self.favorite_scroll = QScrollArea()
        self.favorite_scroll.setWidgetResizable(True)
        self.favorite_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.favorite_scroll.setStyleSheet(self.scroll_style())
        self.favorite_scroll.setMinimumHeight(640)   # 560 -> 640
        self.favorite_scroll.setMaximumHeight(16777215)  # 고정 높이 제거

        self.favorite_body = QWidget()
        self.favorite_list_layout = QVBoxLayout(self.favorite_body)
        self.favorite_list_layout.setContentsMargins(4, 2, 4, 16)  # 6 -> 2
        self.favorite_list_layout.setSpacing(12)
        self.favorite_list_layout.addStretch()

        self.favorite_scroll.setWidget(self.favorite_body)
        layout.addWidget(self.favorite_scroll)

        return wrap

    def _clear_layout(self, layout: QVBoxLayout | QHBoxLayout | QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    # =========================
    # region
    # =========================
    def get_json_file_path(self) -> Path:
        base_dir = Path(__file__).resolve().parents[3]
        return base_dir / "resources" / self.resource_sub_dir / self.json_name

    def load_region_data(self) -> list[dict[str, Any]]:
        loc_all = self.file_driver.read_json_array_from_resources(
            self.json_name,
            self.resource_sub_dir
        ) or []

        for item in loc_all:
            if "value" not in item:
                item["value"] = False

        return loc_all

    def populate_tree(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()

            region_dict: dict[str, Any] = {}
            selected_set = set()

            for r in self.selected_regions:
                sido = str(r.get("시도", "")).strip()
                sigungu = str(r.get("시군구", "")).strip()
                dong = str(r.get("읍면동", "")).strip()
                selected_set.add((sido, sigungu, dong))

            expand_sido_names = set()
            expand_sigungu_keys = set()

            for item in self.loc_all:
                sido = str(item.get("시도", "")).strip()
                sigungu = str(item.get("시군구", "")).strip()
                dong = str(item.get("읍면동", "")).strip()

                if sido not in region_dict:
                    sido_item = QTreeWidgetItem([sido])
                    sido_item.setFlags(sido_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    sido_item.setCheckState(0, Qt.CheckState.Unchecked)
                    self.tree.addTopLevelItem(sido_item)
                    region_dict[sido] = {"item": sido_item, "children": {}}

                if sigungu not in region_dict[sido]["children"]:
                    sigungu_item = QTreeWidgetItem([sigungu])
                    sigungu_item.setFlags(sigungu_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    sigungu_item.setCheckState(0, Qt.CheckState.Unchecked)
                    region_dict[sido]["item"].addChild(sigungu_item)
                    region_dict[sido]["children"][sigungu] = {"item": sigungu_item}

                dong_item = QTreeWidgetItem([dong])
                dong_item.setFlags(dong_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

                checked = bool(item.get("value", False))
                if not checked and (sido, sigungu, dong) in selected_set:
                    checked = True

                if checked:
                    expand_sido_names.add(sido)
                    expand_sigungu_keys.add((sido, sigungu))

                dong_item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                region_dict[sido]["children"][sigungu]["item"].addChild(dong_item)

            for sido in region_dict:
                sido_item = region_dict[sido]["item"]

                for sigungu in region_dict[sido]["children"]:
                    sigungu_item = region_dict[sido]["children"][sigungu]["item"]
                    if (sido, sigungu) in expand_sigungu_keys:
                        sigungu_item.setExpanded(True)

                if sido in expand_sido_names:
                    sido_item.setExpanded(True)

        finally:
            self.tree.blockSignals(False)

        self.update_all_check_states()

    @Slot(QTreeWidgetItem, int)
    def on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self.tree.signalsBlocked():
            return

        self.tree.blockSignals(True)
        try:
            state = item.checkState(0)
            self.set_check_state_recursive(item, state)
            self.update_parent_check_state(item)
        finally:
            self.tree.blockSignals(False)

        self.update_all_checkbox_state()

    def set_check_state_recursive(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self.set_check_state_recursive(item.child(i), state)

    def update_parent_check_state(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent is not None:
            child_count = parent.childCount()
            checked_count = 0
            partial_count = 0

            for i in range(child_count):
                child_state = parent.child(i).checkState(0)
                if child_state == Qt.CheckState.Checked:
                    checked_count += 1
                elif child_state == Qt.CheckState.PartiallyChecked:
                    partial_count += 1

            if child_count > 0 and checked_count == child_count:
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif checked_count == 0 and partial_count == 0:
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

            item = parent
            parent = item.parent()

    @Slot(int)
    def on_select_all_changed(self, state: int) -> None:
        check_state = Qt.CheckState(state)
        if check_state == Qt.CheckState.PartiallyChecked:
            check_state = Qt.CheckState.Checked

        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item is not None:
                    self.set_check_state_recursive(item, check_state)
        finally:
            self.tree.blockSignals(False)

        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setCheckState(check_state)
        self.select_all_checkbox.blockSignals(False)

    def update_all_check_states(self) -> None:
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                if top is not None:
                    self.update_check_state_recursive(top)
        finally:
            self.tree.blockSignals(False)

        self.update_all_checkbox_state()

    def update_check_state_recursive(self, item: QTreeWidgetItem) -> None:
        for i in range(item.childCount()):
            self.update_check_state_recursive(item.child(i))

        if item.childCount() == 0:
            return

        checked_count = 0
        partial_count = 0

        for i in range(item.childCount()):
            child_state = item.child(i).checkState(0)
            if child_state == Qt.CheckState.Checked:
                checked_count += 1
            elif child_state == Qt.CheckState.PartiallyChecked:
                partial_count += 1

        if checked_count == item.childCount():
            item.setCheckState(0, Qt.CheckState.Checked)
        elif checked_count == 0 and partial_count == 0:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def update_all_checkbox_state(self) -> None:
        total = self.tree.topLevelItemCount()
        checked = 0
        partial = 0

        for i in range(total):
            item = self.tree.topLevelItem(i)
            if item is None:
                continue

            state = item.checkState(0)
            if state == Qt.CheckState.Checked:
                checked += 1
            elif state == Qt.CheckState.PartiallyChecked:
                partial += 1

        self.select_all_checkbox.blockSignals(True)
        try:
            if total > 0 and checked == total:
                self.select_all_checkbox.setCheckState(Qt.CheckState.Checked)
            elif checked == 0 and partial == 0:
                self.select_all_checkbox.setCheckState(Qt.CheckState.Unchecked)
            else:
                self.select_all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        finally:
            self.select_all_checkbox.blockSignals(False)

    def collect_selected_regions(self) -> list[dict[str, Any]]:
        selected = []

        for i in range(self.tree.topLevelItemCount()):
            sido_item = self.tree.topLevelItem(i)
            if sido_item is None:
                continue

            for j in range(sido_item.childCount()):
                sigungu_item = sido_item.child(j)

                for k in range(sigungu_item.childCount()):
                    dong_item = sigungu_item.child(k)
                    if dong_item.checkState(0) == Qt.CheckState.Checked:
                        selected.append({
                            "시도": sido_item.text(0),
                            "시군구": sigungu_item.text(0),
                            "읍면동": dong_item.text(0),
                        })

        return selected

    # =========================
    # filter
    # =========================
    def _load_setting_data(self) -> list[dict[str, Any]]:
        rows = getattr(self._parent, self.setting_attr_name, None)
        if rows and type(rows) is list:
            return copy.deepcopy(rows)
        return []

    def _load_favorite_data(self) -> list[dict[str, Any]]:
        rows = getattr(self._parent, self.favorite_attr_name, None)
        if rows and type(rows) is list:
            return copy.deepcopy(rows)

        config_path = self._resolve_site_config_path()
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)

                favorites = config_data.get(self.favorite_attr_name) or []
                if type(favorites) is list:
                    return copy.deepcopy(favorites)
            except Exception:
                pass

        return []

    @Slot()
    def reset_filter_to_default(self) -> None:
        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                if type(node) is not dict:
                    continue

                node_type = str(node.get("type") or "")
                node_code = str(node.get("code") or "").strip()

                if node_type == "input":
                    node["value"] = ""

                elif node_type == "two_input":
                    items = node.get("items") or []
                    for item in items:
                        if type(item) is dict:
                            item["value"] = ""

                elif node_type in ("checkbox_multi_group", "checkbox_single_group"):
                    items = node.get("items") or []
                    for item in items:
                        if type(item) is not dict:
                            continue

                        code = str(item.get("code") or "").strip()

                        if node_code == "tradeTypes":
                            item["value"] = code in {"A1", "B1"}
                        elif node_code == "realEstateTypes":
                            item["value"] = code in {"A01", "A04", "B01"}
                        else:
                            item["value"] = False

                elif node_type == "checkbox":
                    node["value"] = False

                items = node.get("items") or []
                for item in items:
                    if type(item) is not dict:
                        continue

                    item_type = str(item.get("type") or "")
                    if item_type == "checkbox":
                        item["value"] = False
                    elif item_type == "input":
                        item["value"] = ""

                children = node.get("children") or []
                if children:
                    walk(children)

        walk(self.setting_data)
        self.render_filter_panel_body()

    def _render_node(
            self,
            node: dict[str, Any],
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
                if type(child) is dict:
                    self._render_node(child, section_layout, node_code, depth + 1)

            if items:
                items_wrap = QWidget()
                items_layout = QGridLayout(items_wrap)
                items_layout.setContentsMargins(0, 4, 0, 0)
                items_layout.setHorizontalSpacing(10)
                items_layout.setVerticalSpacing(10)

                self._render_leaf_items_grid(items, items_layout, 3)
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
                    self._render_leaf_items_grid(items, grid, 3)
                else:
                    self._render_single_group_checkboxes(items, grid, 3)

                group_layout.addWidget(grid_widget)

            for child in children:
                if type(child) is dict:
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
                if type(item) is not dict:
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
            self._render_leaf_items_grid(items, items_layout, 3)
            container_layout.addWidget(items_wrap)

        for child in children:
            if type(child) is dict:
                self._render_node(child, container_layout, node_code, depth + 1)

        parent_layout.addWidget(container_wrap)

    def _render_leaf_items_grid(
            self,
            items: list[dict[str, Any]],
            grid_layout: QGridLayout,
            col_count: int = 3,
    ) -> None:
        row = 0
        col = 0

        for item in items:
            if type(item) is not dict:
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
            items: list[dict[str, Any]],
            grid_layout: QGridLayout,
            col_count: int = 3,
    ) -> None:
        checkboxes = []
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
                lambda state, current_cb=cb, current_items=items: self._handle_single_group_checkbox(
                    state,
                    current_cb,
                    current_items
                )
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
            current_items: list[dict[str, Any]],
    ) -> None:
        if state != Qt.CheckState.Checked.value:
            any_checked = False
            for checkboxes, items in self.single_group_widgets:
                if items is current_items:
                    for cb in checkboxes:
                        if cb.isChecked():
                            any_checked = True
                            break
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

    def _resolve_node_code(self, node: dict[str, Any], parent_code: Optional[str]) -> Optional[str]:
        code = str(node.get("code") or "").strip()
        if code:
            return code
        if parent_code:
            return parent_code
        return None

    def _make_checkbox(self, node: dict[str, Any]) -> QCheckBox:
        cb = QCheckBox(str(node.get("name") or ""))
        cb.setChecked(bool(node.get("value", False)))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(self.filter_checkbox_style())
        self.checkbox_widgets.append((cb, node))
        return cb

    def apply_filter_widget_values_to_setting_data(self) -> None:
        for cb, node in self.checkbox_widgets:
            node["value"] = cb.isChecked()

        for edit, node in self.line_edit_widgets:
            node["value"] = edit.text().strip()

    # =========================
    # favorite
    # =========================
    @Slot()
    def add_favorite(self) -> None:
        self.apply_filter_widget_values_to_setting_data()

        regions = self.collect_selected_regions()
        filters = copy.deepcopy(self.setting_data)

        favorite_row = {
            "regions": regions,
            "filters": filters,
            "checked": True,
        }

        self.favorite_data.append(favorite_row)
        self.render_favorite_list()

    def render_favorite_list(self) -> None:
        if self.favorite_list_layout is None:
            return

        while self.favorite_list_layout.count():
            item = self.favorite_list_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

        for idx, favorite in enumerate(self.favorite_data):
            card = self.build_favorite_card(idx, favorite)
            self.favorite_list_layout.addWidget(card)

        self.favorite_list_layout.addStretch()

    def build_favorite_card(self, index: int, favorite: dict[str, Any]) -> QWidget:
        wrap = QFrame()
        wrap.setFixedHeight(250)
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wrap.setStyleSheet("""
            QFrame {
                border: 1px solid #dddddd;
                border-radius: 10px;
                background: #fafafa;
            }
        """)

        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 6)
        top_row.setSpacing(8)   # 이 줄 추가

        title = QLabel(f"즐겨찾기 {index + 1}")
        title.setFixedHeight(32)
        title.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: #111;
                background: white;
                border: 1px solid #d9d9d9;
                border-radius: 10px;
                padding: 2px 12px;
            }
        """)

        top_row.addWidget(title)
        top_row.addStretch()

        summary_label = QLabel(self.build_favorite_summary_text(favorite))
        summary_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        summary_label.setWordWrap(True)
        summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_label.setStyleSheet("""
            QLabel {
                border: 1px solid #d9d9d9;
                border-radius: 8px;
                background: white;
                color: #222;
                font-size: 12px;
                padding: 12px;
            }
        """)
        summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        summary_scroll = QScrollArea()
        summary_scroll.setWidgetResizable(True)
        summary_scroll.setFrameShape(QFrame.Shape.NoFrame)
        summary_scroll.setStyleSheet(self.scroll_style())
        summary_scroll.setFixedHeight(145)

        summary_body = QWidget()
        summary_body.setStyleSheet("background: #fafafa;")
        summary_body_layout = QVBoxLayout(summary_body)
        summary_body_layout.setContentsMargins(0, 0, 0, 0)
        summary_body_layout.setSpacing(0)
        summary_body_layout.addWidget(summary_label)

        summary_scroll.setWidget(summary_body)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 10, 0, 0)
        bottom_row.setSpacing(8)

        use_checkbox = QCheckBox("사용")
        use_checkbox.setFixedHeight(32)
        use_checkbox.setChecked(bool(favorite.get("checked", False)))
        use_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        use_checkbox.setStyleSheet(self.favorite_use_checkbox_style())
        use_checkbox.stateChanged.connect(lambda state, row=favorite: self.on_favorite_checked_changed(state, row))

        delete_btn = QPushButton("삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFixedSize(70, 32)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #e9e9e9;
                color: #111;
                border: none;
                border-radius: 7px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #dcdcdc;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_favorite(index))

        bottom_row.addStretch()
        bottom_row.addWidget(use_checkbox)
        bottom_row.addWidget(delete_btn)

        layout.addLayout(top_row)
        layout.addWidget(summary_scroll)
        layout.addSpacing(6)
        layout.addLayout(bottom_row)

        return wrap


    @Slot(int)
    def on_favorite_checked_changed(self, state: int, favorite_row: dict[str, Any]) -> None:
        favorite_row["checked"] = state == Qt.CheckState.Checked.value

    @Slot()
    def delete_favorite(self, index: int) -> None:
        if index < 0 or index >= len(self.favorite_data):
            return

        del self.favorite_data[index]
        self.render_favorite_list()

    def build_favorite_summary_text(self, favorite: dict[str, Any]) -> str:
        regions = favorite.get("regions") or []
        filters = favorite.get("filters") or []

        region_text = self.build_region_summary(regions)
        filter_text = self.build_filter_summary(filters)

        lines = [f"지역 : {region_text}"]

        if filter_text:
            lines.append("")
            lines.append(filter_text)

        return "\n".join(lines)

    def build_region_summary(self, regions: list[dict[str, Any]]) -> str:
        names = []

        for row in regions:
            sido = str(row.get("시도", "")).strip()
            sigungu = str(row.get("시군구", "")).strip()
            dong = str(row.get("읍면동", "")).strip()
            names.append(f"{sido} {sigungu} {dong}".strip())

        if not names:
            return "-"

        return ", ".join(names)

    def build_filter_summary(self, filters: list[dict[str, Any]]) -> str:
        lines = []

        def append_checkbox_items(label: str, items: list[dict[str, Any]]) -> None:
            checked_names = []
            for item in items:
                if type(item) is not dict:
                    continue
                if str(item.get("type") or "") == "checkbox" and bool(item.get("value", False)):
                    checked_names.append(str(item.get("name") or "").strip())

            if label and checked_names:
                lines.append(f"{label} : {', '.join(checked_names)}")

        def append_input_items(label: str, items: list[dict[str, Any]]) -> None:
            values = []
            for item in items:
                if type(item) is not dict:
                    continue
                if str(item.get("type") or "") == "input":
                    value = str(item.get("value") or "").strip()
                    if value:
                        values.append(value)

            if label and values:
                if len(values) >= 2:
                    lines.append(f"{label} : {values[0]} ~ {values[1]}")
                else:
                    lines.append(f"{label} : {values[0]}")

        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                if type(node) is not dict:
                    continue

                node_type = str(node.get("type") or "")
                node_name = str(node.get("name") or "").strip()
                items = node.get("items") or []
                children = node.get("children") or []

                if node_type in ("checkbox_multi_group", "checkbox_single_group"):
                    append_checkbox_items(node_name, items)

                elif node_type == "two_input":
                    append_input_items(node_name, items)

                elif node_type == "input":
                    value = str(node.get("value") or "").strip()
                    if node_name and value:
                        lines.append(f"{node_name} : {value}")

                elif node_type == "checkbox":
                    if node_name and bool(node.get("value", False)):
                        lines.append(f"{node_name} : 선택")

                else:
                    has_checkbox_item = False
                    has_input_item = False

                    for item in items:
                        if type(item) is not dict:
                            continue
                        item_type = str(item.get("type") or "")
                        if item_type == "checkbox":
                            has_checkbox_item = True
                        elif item_type == "input":
                            has_input_item = True

                    if has_checkbox_item:
                        append_checkbox_items(node_name, items)
                    elif has_input_item:
                        append_input_items(node_name, items)

                if children:
                    walk(children)

        walk(filters)
        return "\n".join(lines)

    def get_checked_favorites(self) -> list[dict[str, Any]]:
        result = []

        for favorite in self.favorite_data:
            if bool(favorite.get("checked", False)):
                result.append(favorite)

        return result

    # =========================
    # save
    # =========================
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

            with open(app_json_path, "r", encoding="utf-8") as f:
                app_json = json.load(f)

            site_list = app_json.get("site_list") or []
            config_rel_path = ""

            for site_item in site_list:
                if type(site_item) is not dict:
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

    def _save_to_runtime_config(
            self,
            setting_data: Optional[list[dict[str, Any]]] = None,
            favorite_data: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        try:
            config_path = self._resolve_site_config_path()
            if not config_path:
                return

            if not os.path.exists(config_path):
                return

            save_setting_data = copy.deepcopy(setting_data if setting_data is not None else self.setting_data)
            save_favorite_data = copy.deepcopy(favorite_data if favorite_data is not None else self.favorite_data)

            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            config_data[self.setting_attr_name] = save_setting_data
            config_data[self.favorite_attr_name] = save_favorite_data

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
                f.write("\n")

            self.log_signal.emit("변경사항이 저장되었습니다.")

        except Exception as e:
            self.log_signal.emit(f"설정 저장 실패: {e}")

    def _save_to_runtime_config_async(
            self,
            setting_data: list[dict[str, Any]],
            favorite_data: list[dict[str, Any]],
    ) -> None:
        thread = threading.Thread(
            target=self._save_to_runtime_config,
            args=(setting_data, favorite_data),
            daemon=True,
        )
        thread.start()

    # =========================
    # confirm
    # =========================
    @Slot()
    def confirm_selection(self) -> None:
        self.apply_filter_widget_values_to_setting_data()

        selected_regions = self.collect_selected_regions()
        setting_snapshot = copy.deepcopy(self.setting_data)
        favorite_snapshot = copy.deepcopy(self.favorite_data)

        if self._parent is not None:
            setattr(self._parent, "selected_regions", selected_regions)
            setattr(self._parent, self.setting_attr_name, setting_snapshot)
            setattr(self._parent, self.favorite_attr_name, favorite_snapshot)

        self.log_signal.emit(f"선택된 지역 {len(selected_regions)}개")
        self.log_signal.emit(f"선택된 즐겨찾기 {len(self.get_checked_favorites())}개")

        self.accept()

        QTimer.singleShot(
            0,
            lambda: self._after_confirm(selected_regions, setting_snapshot, favorite_snapshot)
        )

    def _after_confirm(
            self,
            selected_regions: list[dict[str, Any]],
            setting_snapshot: list[dict[str, Any]],
            favorite_snapshot: list[dict[str, Any]],
    ) -> None:
        self.confirm_signal.emit(selected_regions, setting_snapshot, favorite_snapshot)
        self._save_to_runtime_config_async(setting_snapshot, favorite_snapshot)

    # =========================
    # styles
    # =========================
    def _section_title_style(self, depth: int) -> str:
        if depth == 0:
            return "font-size: 16px; font-weight: bold; color: #111; padding: 8px 0 4px 0;"
        return "font-size: 14px; font-weight: bold; color: #222; padding: 6px 0 2px 0;"

    def _field_title_style(self, depth: int) -> str:
        if depth == 0:
            return "font-size: 16px; font-weight: bold; color: #111; padding: 8px 0 4px 0;"
        return "font-size: 14px; font-weight: bold; color: #222; padding: 4px 0 2px 0;"

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #e5e5e5; background: #e5e5e5; min-height: 1px; max-height: 1px;")
        return line

    def make_vertical_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color: #e5e5e5; background: #e5e5e5; min-width: 1px; max-width: 1px;")
        return line

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

            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                border: none;
                background: transparent;
                width: 0px;
                height: 0px;
            }
        """

    def tree_style(self) -> str:
        return """
            QTreeView {
                font-size: 14px;
                padding: 4px 12px;
                outline: none;
                color: #111;
                selection-color: black;
            }
            QTreeView::item {
                padding: 8px 0px;
            }
            QTreeView::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #888888;
                background-color: white;
                margin-right: 12px;
            }
            QTreeView::indicator:checked {
                background-color: black;
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
        """

    def left_checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 14px;
                color: #333;
                padding: 8px 12px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #888888;
                background-color: white;
                margin-right: 10px;
            }
            QCheckBox::indicator:checked {
                background-color: black;
            }
        """

    def filter_checkbox_style(self) -> str:
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

    def favorite_use_checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 12px;
                font-weight: bold;
                color: #111;
                padding: 0 10px;
                spacing: 6px;
                background: #e9e9e9;
                border-radius: 7px;
                min-height: 32px;
            }
            QCheckBox:hover {
                background: #dcdcdc;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #888;
                background: #fff;
            }
            QCheckBox::indicator:checked {
                background: black;
                border: 1px solid black;
            }

        """

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