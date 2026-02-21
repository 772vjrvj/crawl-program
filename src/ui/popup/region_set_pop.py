# src/ui/popup/region_set_pop.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.style.style import create_common_button
from src.utils.file_utils import FileUtils


class _Region(TypedDict):
    시도: str
    시군구: str
    읍면동: str


class RegionSetPop(QDialog):
    log_signal: Signal = Signal(str)
    confirm_signal: Signal = Signal(list)

    def __init__(self, selected_regions: Optional[List[_Region]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._parent: Optional[QWidget] = parent
        self.setWindowTitle("지역 선택")
        self.resize(800, 600)
        self.setMinimumSize(800, 600)
        self.setStyleSheet("background-color: white;")

        self.selected_regions: List[_Region] = selected_regions or []

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(self.tree_style())
        self.tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.select_all_checkbox = QCheckBox("전체 선택", self)
        self.select_all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_checkbox.setStyleSheet(self.checkbox_style())
        self.select_all_checkbox.stateChanged.connect(self.on_select_all_changed)

        # 기존 코드의 _is_select_all_action은 실제 로직에서 크게 쓰이지 않아 제거 가능하지만,
        # 현재 흐름 보존을 위해 플래그는 남기고 사용은 최소화
        self._is_select_all_action: bool = False

        # FileUtils: logger로 signal emit 넘기는 패턴 유지
        self.file_driver = FileUtils(self.log_signal.emit)

        loc_any: Any = self.file_driver.read_json_array_from_resources("naver_loc_all_real.json")
        self.loc_all: List[_Region] = cast(List[_Region], loc_any or [])

        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        info_label = QLabel("지역을 선택하세요", self)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(info_label)

        layout.addWidget(self.select_all_checkbox)
        layout.addWidget(self.tree)

        self.populate_tree()

        # tree itemChanged는 populate 이후 연결(초기 setCheckState 이벤트 잡음 최소화)
        self.tree.itemChanged.connect(self.on_item_changed)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 15, 0, 0)

        cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

    # =========================
    # tree build
    # =========================
    def populate_tree(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()

            region_dict: Dict[str, Dict[str, Any]] = {}
            selected_set: Set[Tuple[str, str, str]] = set(
                (r["시도"], r["시군구"], r["읍면동"]) for r in self.selected_regions
            )

            for item in self.loc_all:
                sido = item["시도"]
                sigungu = item["시군구"]
                dong = item["읍면동"]

                if sido not in region_dict:
                    sido_item = QTreeWidgetItem([sido])
                    sido_item.setFlags(sido_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    sido_item.setCheckState(0, Qt.CheckState.Unchecked)
                    sido_item.setData(0, Qt.ItemDataRole.UserRole, "sido")
                    self.tree.addTopLevelItem(sido_item)
                    region_dict[sido] = {"item": sido_item, "children": {}}

                children = region_dict[sido]["children"]
                if sigungu not in children:
                    sigungu_item = QTreeWidgetItem([sigungu])
                    sigungu_item.setFlags(sigungu_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    sigungu_item.setCheckState(0, Qt.CheckState.Unchecked)
                    sigungu_item.setData(0, Qt.ItemDataRole.UserRole, "sigungu")
                    children[sigungu] = {"item": sigungu_item}
                    region_dict[sido]["item"].addChild(sigungu_item)

                dong_item = QTreeWidgetItem([dong])
                dong_item.setFlags(dong_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                dong_item.setData(0, Qt.ItemDataRole.UserRole, "eupmyeondong")

                checked = (sido, sigungu, dong) in selected_set
                dong_item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

                children[sigungu]["item"].addChild(dong_item)

        finally:
            self.tree.blockSignals(False)

        self.update_all_check_states()

        # ✅ 전체 선택 체크박스는 기본 해제
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setCheckState(Qt.CheckState.Unchecked)
        self.select_all_checkbox.blockSignals(False)

    # =========================
    # events
    # =========================
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

    def update_parent_check_state(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent is not None:
            child_count = parent.childCount()
            checked_count = sum(
                1 for i in range(child_count) if parent.child(i).checkState(0) == Qt.CheckState.Checked
            )

            if checked_count == child_count and child_count > 0:
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif checked_count == 0:
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

            item = parent
            parent = item.parent()

    @Slot(int)
    def on_select_all_changed(self, state: int) -> None:
        # PartiallyChecked 클릭 → Checked로 취급
        check_state = Qt.CheckState(state)
        if check_state == Qt.CheckState.PartiallyChecked:
            check_state = Qt.CheckState.Checked

        self._is_select_all_action = True
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                sido_item = self.tree.topLevelItem(i)
                if sido_item is None:
                    continue
                self.set_check_state_recursive(sido_item, check_state)
        finally:
            self.tree.blockSignals(False)
            self._is_select_all_action = False

        # select_all 자체도 동기화
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
        # leaf면 패스
        for i in range(item.childCount()):
            self.update_check_state_recursive(item.child(i))

        child_count = item.childCount()
        if child_count == 0:
            return

        checked_count = sum(
            1 for i in range(child_count) if item.child(i).checkState(0) == Qt.CheckState.Checked
        )

        if checked_count == child_count:
            item.setCheckState(0, Qt.CheckState.Checked)
        elif checked_count == 0:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def update_all_checkbox_state(self) -> None:
        total = self.tree.topLevelItemCount()
        checked = sum(
            1
            for i in range(total)
            if self.tree.topLevelItem(i) is not None
            and self.tree.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        )

        self.select_all_checkbox.blockSignals(True)
        try:
            if total > 0 and checked == total:
                self.select_all_checkbox.setCheckState(Qt.CheckState.Checked)
            elif checked == 0:
                self.select_all_checkbox.setCheckState(Qt.CheckState.Unchecked)
            else:
                self.select_all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        finally:
            self.select_all_checkbox.blockSignals(False)

    def set_check_state_recursive(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self.set_check_state_recursive(item.child(i), state)

    # =========================
    # confirm
    # =========================
    @Slot()
    def confirm_selection(self) -> None:
        selected: List[_Region] = []

        for i in range(self.tree.topLevelItemCount()):
            sido_item = self.tree.topLevelItem(i)
            if sido_item is None:
                continue

            for j in range(sido_item.childCount()):
                sigungu_item = sido_item.child(j)

                for k in range(sigungu_item.childCount()):
                    dong_item = sigungu_item.child(k)
                    if dong_item.checkState(0) == Qt.CheckState.Checked:
                        selected.append(
                            {"시도": sido_item.text(0), "시군구": sigungu_item.text(0), "읍면동": dong_item.text(0)}
                        )

        self.log_signal.emit(f"선택된 지역 {len(selected)}개")
        self.confirm_signal.emit(selected)
        self.accept()

    # =========================
    # styles
    # =========================
    def tree_style(self) -> str:
        return """
            QTreeView {
                font-size: 14px;
                padding: 4px 12px;
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
        """

    def checkbox_style(self) -> str:
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