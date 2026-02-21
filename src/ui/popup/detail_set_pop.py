# src/ui/popup/detail_set_pop.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TypedDict

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


class _DetailRow(TypedDict, total=False):
    row_type: str          # "section" or item
    id: str                # section id
    title: str             # section title
    col_per_row: int       # section column count

    parent_id: str         # item parent section id
    type: str              # legacy: treated as parent_id
    code: str              # item key
    value: str             # checkbox text
    checked: bool          # checkbox state


class DetailSetPop(QDialog):
    log_signal: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None, title: str = "상세세팅") -> None:
        super().__init__(parent)

        # NOTE: Qt 부모는 self.parent()로 접근 가능하지만,
        # 기존 코드 호환을 위해 parent 참조를 별도로 유지
        self._parent: Optional[QWidget] = parent

        self.setWindowTitle(title)
        self.resize(700, 520)
        self.setStyleSheet("background-color: white;")

        self.checkbox_map: Dict[Tuple[str, str], QCheckBox] = {}
        self.all_checkbox: Optional[QCheckBox] = None

        self.init_ui()

    def _get_rows(self) -> List[_DetailRow]:
        rows_any: Any = getattr(self._parent, "setting_detail", None)
        if not isinstance(rows_any, list):
            return []
        # list[dict] 형태라고 가정 (런타임에 TypedDict로 강제하진 않음)
        return rows_any  # type: ignore[return-value]

    # === 신규 === rows에서 section/item 분리 + legacy 호환 정리
    def _normalize_rows(self, rows: List[_DetailRow]) -> Tuple[List[_DetailRow], List[_DetailRow]]:
        sections: List[_DetailRow] = []
        items: List[_DetailRow] = []

        for r in rows:
            if r.get("row_type") == "section":
                sections.append(r)
            else:
                items.append(r)

        # === 신규 === 기존 구조 호환: parent_id 없고 type 있으면 type을 parent_id로 간주
        for it in items:
            if "parent_id" not in it:
                t = it.get("type")
                if t:
                    it["parent_id"] = str(t)

        # === 신규 === 섹션이 아예 없으면(기존 데이터) parent_id(type) 기준으로 섹션 자동 생성
        if not sections:
            seen: set[str] = set()
            for it in items:
                pid = str(it.get("parent_id") or "default")
                if pid in seen:
                    continue
                seen.add(pid)
                sections.append({"id": pid, "title": pid, "col_per_row": 5})

        return sections, items

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title_label = QLabel(self.windowTitle())
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(title_label)

        self.all_checkbox = QCheckBox("전체 선택")
        self.all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_checkbox.setStyleSheet(self.checkbox_style())
        self.all_checkbox.stateChanged.connect(self.handle_all_checkbox_click)
        layout.addWidget(self.all_checkbox)

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        rows = self._get_rows()
        sections, items = self._normalize_rows(rows)

        cur_row = 0
        for sec in sections:
            sec_id = str(sec.get("id") or "default")
            sec_title = str(sec.get("title") or sec_id)
            col_per_row = int(sec.get("col_per_row") or 5)

            grid_layout.addWidget(self._make_section_label(sec_title), cur_row, 0, 1, col_per_row)
            cur_row += 1

            sec_items = [x for x in items if str(x.get("parent_id") or "default") == sec_id]
            self._add_checkboxes(
                grid_layout=grid_layout,
                rows=sec_items,
                start_row=cur_row,
                col_per_row=col_per_row,
                sec_id=sec_id,
            )

            # 섹션이 차지한 행 수만큼 증가
            cur_row += (len(sec_items) + col_per_row - 1) // col_per_row
            cur_row += 1  # 섹션 간 여백

        layout.addWidget(grid_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 15, 0, 0)

        cancel_btn = create_common_button("취소", self.reject, "#cccccc", 140)
        confirm_btn = create_common_button("확인", self.confirm_selection, "black", 140)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        self.update_all_checkbox_state()

    def _make_section_label(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setStyleSheet("font-size: 15px; font-weight: bold; margin-top: 6px;")
        return lb

    def _make_key(self, sec_id: str, code: Any) -> Tuple[str, str]:
        return sec_id, str(code or "")

    def _add_checkboxes(
            self,
            grid_layout: QGridLayout,
            rows: List[_DetailRow],
            start_row: int,
            col_per_row: int = 5,
            sec_id: str = "default",
    ) -> None:
        for idx, row in enumerate(rows):
            text = str(row.get("value") or "")
            cb = QCheckBox(text)
            cb.setChecked(bool(row.get("checked", True)))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(self.checkbox_style())
            cb.stateChanged.connect(self.update_all_checkbox_state)

            key = self._make_key(sec_id, row.get("code"))
            self.checkbox_map[key] = cb

            r = start_row + (idx // col_per_row)
            c = idx % col_per_row
            grid_layout.addWidget(cb, r, c)

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
        if total == 0 or checked_count == 0:
            self.all_checkbox.setCheckState(Qt.CheckState.Unchecked)
        elif checked_count == total:
            self.all_checkbox.setCheckState(Qt.CheckState.Checked)
        else:
            self.all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        self.all_checkbox.blockSignals(False)

    @Slot()
    def confirm_selection(self) -> None:
        rows = self._get_rows()

        for row in rows:
            if row.get("row_type") == "section":
                continue

            # 호환: parent_id 없고 type 있으면 type을 parent_id로 봄
            pid = str(row.get("parent_id") or row.get("type") or "default")
            code = row.get("code")
            key = self._make_key(pid, code)

            cb = self.checkbox_map.get(key)
            if cb is not None:
                row["checked"] = cb.isChecked()

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