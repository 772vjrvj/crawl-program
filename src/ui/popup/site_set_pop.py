# src/ui/popup/site_set_pop.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.style.style import create_common_button


class _SiteItem(TypedDict, total=False):
    code: str
    value: str
    checked: bool


class SiteSetPop(QDialog):
    log_signal: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._parent: Optional[QWidget] = parent

        self.setWindowTitle("사이트 선택")
        self.resize(700, 450)
        self.setMinimumWidth(700)
        self.setStyleSheet("background-color: white;")

        self.checkbox_map: Dict[str, QCheckBox] = {}
        self.all_checkbox: Optional[QCheckBox] = None

        self.init_ui()

    # =========================
    # data
    # =========================
    def _get_sites(self) -> List[_SiteItem]:
        p = self._parent
        if p is None:
            return []
        sites_any: Any = getattr(p, "sites", None)
        if not isinstance(sites_any, list):
            return []
        return cast(List[_SiteItem], sites_any)

    def _get_initial_all_state(self) -> Qt.CheckState:
        sites = self._get_sites()
        total = len(sites)
        if total == 0:
            return Qt.CheckState.Unchecked

        checked_count = sum(1 for it in sites if bool(it.get("checked", True)))
        if checked_count == 0:
            return Qt.CheckState.Unchecked
        if checked_count == total:
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    # =========================
    # UI
    # =========================
    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title_label = QLabel("사이트 선택", self)
        title_label.setStyleSheet(
            """
            font-size: 18px;
            font-weight: bold;
            """
        )
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(title_label)

        # ✅ 전체 선택 체크박스
        self.all_checkbox = QCheckBox("전체 선택", self)
        self.all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_checkbox.setStyleSheet(self.checkbox_style())
        self.all_checkbox.setCheckState(self._get_initial_all_state())
        self.all_checkbox.stateChanged.connect(self.handle_all_checkbox_click)
        layout.addWidget(self.all_checkbox)

        # ✅ 사이트 체크박스들을 그리드로 나열
        grid_widget = QWidget(self)
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        col_per_row = 5
        for idx, site in enumerate(self._get_sites()):
            code = str(site.get("code", "") or "")
            text = str(site.get("value", "") or "")
            checked = bool(site.get("checked", True))

            cb = QCheckBox(text, self)
            cb.setChecked(checked)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(self.checkbox_style())
            cb.stateChanged.connect(self.update_all_checkbox_state)

            if code:
                self.checkbox_map[code] = cb

            r = idx // col_per_row
            c = idx % col_per_row
            grid_layout.addWidget(cb, r, c)

        layout.addWidget(grid_widget)

        # ✅ 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 15, 0, 0)

        cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        self.update_all_checkbox_state()

    # =========================
    # slots
    # =========================
    @Slot(int)
    def handle_all_checkbox_click(self, _state: int) -> None:
        # 현재 전체가 다 체크면 -> 모두 해제, 아니면 -> 모두 체크
        all_checked = bool(self.checkbox_map) and all(cb.isChecked() for cb in self.checkbox_map.values())

        for cb in self.checkbox_map.values():
            cb.blockSignals(True)
            cb.setChecked(not all_checked)
            cb.blockSignals(False)

        self.update_all_checkbox_state()

    @Slot()
    def update_all_checkbox_state(self) -> None:
        if self.all_checkbox is None:
            return

        total = len(self.checkbox_map)
        checked_count = sum(1 for cb in self.checkbox_map.values() if cb.isChecked())

        self.all_checkbox.blockSignals(True)
        try:
            if total == 0 or checked_count == 0:
                self.all_checkbox.setCheckState(Qt.CheckState.Unchecked)
            elif checked_count == total:
                self.all_checkbox.setCheckState(Qt.CheckState.Checked)
            else:
                self.all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        finally:
            self.all_checkbox.blockSignals(False)

    @Slot()
    def confirm_selection(self) -> None:
        # ✅ checked 상태를 사이트 객체에 반영
        sites = self._get_sites()

        for it in sites:
            code = str(it.get("code", "") or "")
            if not code:
                continue

            cb = self.checkbox_map.get(code)
            if cb is not None:
                it["checked"] = cb.isChecked()

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

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.update_all_checkbox_state()