"""기존 지역/즐겨찾기 팝업에 디스코 필터만 추가합니다."""
import copy
import json
import os
from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from src.ui.popup.region_filter_favorite_set_pop import RegionFilterFavoriteSetPop
from src.utils.disco_filters import (
    PYEONG_TO_SQM, build_disco_form, default_disco_filters, filter_summary,
    select_property_group,
)


class DiscoRegionFilterFavoriteSetPop(RegionFilterFavoriteSetPop):
    def _load_setting_data(self):
        rows = super()._load_setting_data()
        if not any(row.get("type") == "disco_property" for row in rows):
            return default_disco_filters()
        return rows

    def load_region_data(self):
        self.json_name = "korea_eup_myeon_dong.json"
        self.resource_sub_dir = "customers/disco_re_detail/region"
        rows = super().load_region_data()
        selected = {
            (r.get("시도"), r.get("시군구"), r.get("읍면동"))
            for r in self.selected_regions
        }
        for row in rows:
            row["value"] = (row.get("시도"), row.get("시군구"), row.get("읍면동")) in selected
        return rows

    def reset_filter_to_default(self):
        self.setting_data = default_disco_filters()
        self.render_filter_panel_body()

    def _button(self, text):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(32)
        button.setStyleSheet("""
            QPushButton { border: 1px solid #d9dfe6; border-radius: 7px;
                          background: #f5f6f8; padding: 7px 9px; color: #333; }
            QPushButton:checked { background: #e8f1ff; color: #0969da;
                                  border: 1px solid #80b5ff; }
        """)
        return button

    @staticmethod
    def _checkbox_style():
        """컬럼/DB 팝업과 같은 검정 체크박스 스타일입니다."""
        return """
            QCheckBox {
                font-size: 13px;
                color: #333;
                padding: 6px 8px;
                background: transparent;
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

    def _style_checkbox(self, checkbox):
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        checkbox.setStyleSheet(self._checkbox_style())
        return checkbox

    def _section(self, name, parent_layout):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(9)
        label = QLabel(name)
        label.setStyleSheet("font-size: 15px; font-weight: bold; color: #194e76;")
        layout.addWidget(label)
        parent_layout.addWidget(widget)
        return layout

    def _render_node(self, node, parent_layout, parent_code=None, depth=0):
        kind = node.get("type")
        if kind == "disco_property":
            self._render_property(node, parent_layout)
        elif kind == "disco_multi":
            layout = self._section(node["name"], parent_layout)
            self._render_multi(node["items"], layout)
        elif kind == "disco_use_area":
            self._render_use_area(node, parent_layout)
        elif kind == "disco_area":
            self._render_area(node, parent_layout)
        else:
            super()._render_node(node, parent_layout, parent_code, depth)

    def _render_property(self, node, parent_layout):
        layout = self._section(node["name"], parent_layout)
        tab_grid = QGridLayout()
        tabs = QButtonGroup(self)
        stack = QStackedWidget()
        groups = node["children"]
        # 전체 유형에는 별도 하위 선택지가 없으므로 빈 페이지로 두고 스택도 숨깁니다.
        stack.addWidget(QWidget())
        all_checkbox_rows = []

        for index, group in enumerate(groups, 1):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            boxes, all_button = self._render_multi(group["items"], panel_layout, property_group=True)
            all_checkbox_rows.append((boxes, all_button))
            stack.addWidget(panel)

        active_index = next((i for i, g in enumerate(groups, 1)
                             if g["code"] == node.get("selectedGroup")), 0)

        def switch(index):
            group_code = "all" if index == 0 else groups[index - 1]["code"]
            if node.get("selectedGroup") == group_code:
                return
            self.apply_filter_widget_values_to_setting_data()
            select_property_group(node, group_code)
            for boxes, all_button in all_checkbox_rows:
                for cb, item in boxes:
                    cb.blockSignals(True)
                    cb.setChecked(item["value"])
                    cb.blockSignals(False)
                # 전체 버튼은 개별 체크값에서 다시 계산
                all_selected = all(cb.isChecked() for cb, _ in boxes)
                all_button.setChecked(all_selected)
                all_button.setText("전체 해제" if all_selected else "전체 선택")
            stack.setCurrentIndex(index)
            stack.setVisible(index != 0)

        for index, name in enumerate(["전체"] + [g["name"] for g in groups]):
            button = self._button(name)
            tabs.addButton(button, index)
            tab_grid.addWidget(button, index // 2, index % 2)
            button.setChecked(index == active_index)
        tabs.idClicked.connect(switch)
        layout.addLayout(tab_grid)
        stack.setCurrentIndex(active_index)
        stack.setVisible(active_index != 0)
        layout.addWidget(stack)

    def _render_multi(self, items, layout, property_group=False):
        all_button = self._button("전체 선택")
        all_button.setObjectName("group_all")
        layout.addWidget(all_button)
        grid = QGridLayout()
        boxes = []
        for index, item in enumerate(items):
            cb = self._style_checkbox(self._make_checkbox(item))
            cb.setFixedHeight(40)
            boxes.append((cb, item))
            grid.addWidget(cb, index // 2, index % 2)
        layout.addLayout(grid)

        def sync():
            all_selected = all(cb.isChecked() for cb, _ in boxes)
            all_button.setChecked(all_selected)
            all_button.setText("전체 해제" if all_selected else "전체 선택")

        def choose_all():
            # 하위 그룹의 전체 버튼은 한 번 누르면 전체 선택,
            # 전체 선택 상태에서 다시 누르면 전체 해제합니다.
            target_checked = not all(cb.isChecked() for cb, _ in boxes)
            for cb, item in boxes:
                cb.blockSignals(True)
                cb.setChecked(target_checked)
                cb.blockSignals(False)
                item["value"] = target_checked
            sync()

        for cb, _ in boxes:
            cb.toggled.connect(sync)
        all_button.clicked.connect(choose_all)
        sync()
        return boxes, all_button

    def _render_use_area(self, node, parent_layout):
        layout = self._section(node["name"], parent_layout)
        top_all = self._button("전체 용도지역")
        layout.addWidget(top_all)
        groups = []
        for group in node["children"]:
            group_layout = self._section(group["name"], layout)
            # 하위 전체는 해당 그룹의 모든 useArea 코드를 선택
            groups.append(self._render_multi(group["items"], group_layout, property_group=True))

        def sync():
            top_all.setChecked(not any(cb.isChecked() for boxes, _ in groups for cb, _ in boxes))

        def choose_all():
            for boxes, _ in groups:
                for cb, item in boxes:
                    cb.setChecked(False)
                    item["value"] = False
            sync()

        for boxes, all_button in groups:
            for cb, _ in boxes:
                cb.toggled.connect(sync)
            all_button.clicked.connect(sync)
        top_all.clicked.connect(choose_all)
        sync()

    def _render_area(self, node, parent_layout):
        layout = self._section("면적", parent_layout)
        unit_row = QHBoxLayout()
        unit_group = QButtonGroup(self)
        for index, text in enumerate(["평", "㎡"]):
            button = self._button(text)
            unit_group.addButton(button, index)
            button.setChecked(node["areaUnit"] == ("pyeong" if index == 0 else "sqm"))
            unit_row.addWidget(button)
        layout.addLayout(unit_row)
        old_count = len(self.line_edit_widgets)
        super()._render_node({**node, "type": "two_input"}, layout, None)
        edits = self.line_edit_widgets[old_count:]

        def switch(index):
            unit = "pyeong" if index == 0 else "sqm"
            if unit == node["areaUnit"]:
                return
            # 단위 전환 시 입력한 실제 면적을 유지합니다.
            for edit, item in edits:
                try:
                    value = Decimal(edit.text().strip().replace(",", ""))
                    if not value.is_finite() or value < 0:
                        continue
                    value = value * PYEONG_TO_SQM if unit == "sqm" else value / PYEONG_TO_SQM
                    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    edit.setText(format(value, "f").rstrip("0").rstrip("."))
                    item["value"] = edit.text()
                except ArithmeticError:
                    pass
            node["areaUnit"] = unit

        unit_group.idClicked.connect(switch)
        exclusive = QCheckBox("전용면적 기준으로 찾기")
        self._style_checkbox(exclusive)
        exclusive.setChecked(node["exclusiveAreaOnly"])
        exclusive.toggled.connect(lambda checked: node.update(exclusiveAreaOnly=checked))
        layout.addWidget(exclusive)

    def build_filter_summary(self, filters):
        return filter_summary(filters)

    def _validate_current(self):
        self.apply_filter_widget_values_to_setting_data()
        try:
            build_disco_form(self.setting_data)
        except ValueError as error:
            QMessageBox.warning(self, "설정 확인", str(error))
            return False
        return True

    def add_favorite(self):
        if self._validate_current():
            super().add_favorite()

    def confirm_selection(self):
        if not self._validate_current():
            return
        regions = self.collect_selected_regions()
        filters = copy.deepcopy(self.setting_data)
        favorites = copy.deepcopy(self.favorite_data)
        config_path = self._resolve_site_config_path()
        if not config_path or not os.path.exists(config_path):
            QMessageBox.warning(self, "설정 저장 실패", "현재 프로그램의 config.json을 찾을 수 없습니다.")
            return
        try:
            with open(config_path, encoding="utf-8") as file:
                config = json.load(file)
            config[self.setting_attr_name] = filters
            config[self.favorite_attr_name] = favorites
            config["selected_regions"] = regions
            # 선택 지역은 이 프로그램 설정에만 저장합니다.
            with open(config_path + ".tmp", "w", encoding="utf-8") as file:
                json.dump(config, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(config_path + ".tmp", config_path)
        except OSError as error:
            QMessageBox.warning(self, "설정 저장 실패", str(error))
            return
        self.confirm_signal.emit(regions, filters, favorites)
        self.accept()
