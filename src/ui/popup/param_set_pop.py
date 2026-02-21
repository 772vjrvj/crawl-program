# src/ui/popup/param_set_pop.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.style.style import create_common_button


# =========================
# typed models
# =========================
class _SelectOpt(TypedDict, total=False):
    key: str
    value: str


class _SettingItem(TypedDict, total=False):
    code: str
    name: str
    type: str  # input|select|button|check|file
    value: Any

    options: List[_SelectOpt]  # for select
    placeholder: str           # for file
    button_text: str           # for file
    dialog_title: str          # for file
    filter: str                # for file
    start_dir: str             # for file


@dataclass(frozen=True)
class _FilePickSpec:
    dialog_title: str
    file_filter: str
    start_dir: str


_InputWidget = Union[QLineEdit, QComboBox, QCheckBox]


class ParamSetPop(QDialog):
    log_signal: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._parent: Optional[QWidget] = parent
        self.input_fields: Dict[str, _InputWidget] = {}

        self.confirm_button: Optional[QPushButton] = None
        self.cancel_button: Optional[QPushButton] = None

        self.set_layout()

    # =========================
    # helpers
    # =========================
    def _get_setting(self) -> List[_SettingItem]:
        p = self._parent
        if p is None:
            return []
        setting_any: Any = getattr(p, "setting", None)
        if not isinstance(setting_any, list):
            return []
        return cast(List[_SettingItem], setting_any)

    def _get_on_demand_worker(self) -> Any:
        p = self._parent
        if p is None:
            return None
        return getattr(p, "on_demand_worker", None)

    def _emit_log(self, msg: str) -> None:
        self.log_signal.emit(msg)

    def _make_window_icon(self) -> QIcon:
        # 회색 정사각형 아이콘 생성
        pix = QPixmap(32, 32)
        pix.fill(QColor("transparent"))
        painter = QPainter(pix)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, 32, 32)
        painter.end()
        return QIcon(pix)

    def _line_edit_style(self) -> str:
        return """
            border-radius: 10%;
            border: 2px solid #888888;
            padding: 10px;
            font-size: 14px;
            color: #333333;
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                border-radius: 10%;
                border: 2px solid #888888;
                padding: 10px;
                font-size: 14px;
                color: #333333;
            }
            QComboBox::drop-down { border: none; }
        """

    def _button_style(self) -> str:
        return """
            background-color: black;
            color: white;
            border-radius: 10%;
            font-size: 14px;
        """

    def _checkbox_style(self) -> str:
        return """
            QCheckBox {
                font-size: 14px;
                color: #333333;
                padding: 5px;
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

    def _center_window(self) -> None:
        frame = self.frameGeometry()
        screen = self.screen()
        if screen is None:
            return

        center = screen.availableGeometry().center()
        frame.moveCenter(center)

        # === 신규 === 중앙에서 위로 200px 이동 (기존 유지)
        frame.moveTop(frame.top() - 200)

        self.move(frame.topLeft())

    # =========================
    # UI
    # =========================
    def set_layout(self) -> None:
        self.setWindowTitle("설정")
        self.resize(400, 100)  # 초기 크기 (자동 확장 허용)
        self.setMinimumWidth(400)
        self.setStyleSheet("background-color: white;")
        self.setWindowIcon(self._make_window_icon())

        popup_layout = QVBoxLayout(self)
        popup_layout.setContentsMargins(10, 10, 10, 10)
        popup_layout.setSpacing(5)

        title_label = QLabel("설정 파라미터 세팅")
        title_label.setStyleSheet(
            """
            font-size: 18px;
            font-weight: bold;
            """
        )
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        popup_layout.addWidget(title_label)

        for item in self._get_setting():
            item_type = str(item.get("type", "input") or "input")
            code = str(item.get("code", "") or "")
            name = str(item.get("name", "") or "")

            # ✅ 개별 항목 레이아웃 (간격 포함용)
            item_layout = QVBoxLayout()
            item_layout.setContentsMargins(0, 12, 0, 0)
            item_layout.setSpacing(5)

            label = QLabel(name)
            label.setStyleSheet("font-weight: bold; font-size: 13px;")
            item_layout.addWidget(label)

            if item_type == "input":
                w = QLineEdit(self)
                w.setText(str(item.get("value", "") or ""))
                w.setFixedHeight(40)
                w.setStyleSheet(self._line_edit_style())
                self.input_fields[code] = w
                item_layout.addWidget(w)

            elif item_type == "select":
                w = QComboBox(self)
                w.setFixedHeight(40)
                w.setStyleSheet(self._combo_style())

                opts = item.get("options") or []
                w.addItem("▼ 선택 ▼", "")

                selected_value = str(item.get("value", "") or "")
                selected_index = 0

                for i, opt in enumerate(opts, start=1):
                    k = str(opt.get("key", "") or "")
                    v = str(opt.get("value", "") or "")
                    w.addItem(k, v)
                    if v == selected_value:
                        selected_index = i

                w.setCurrentIndex(selected_index)
                self.input_fields[code] = w
                item_layout.addWidget(w)

            elif item_type == "button":
                # line edit
                le = QLineEdit(self)
                le.setText(str(item.get("value", "") or ""))
                le.setFixedHeight(40)
                le.setStyleSheet(self._line_edit_style())
                self.input_fields[code] = le
                item_layout.addWidget(le)

                # action button
                btn = QPushButton("조회", self)
                btn.setFixedHeight(40)
                btn.setStyleSheet(self._button_style())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # lambda 캡처 안정화(기존 유지)
                btn.clicked.connect(lambda _checked=False, c=code: self.on_button_clicked(c))
                item_layout.addWidget(btn)

            elif item_type == "check":
                cb = QCheckBox(self)
                cb.setChecked(bool(item.get("value")))
                cb.setStyleSheet(self._checkbox_style())
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                self.input_fields[code] = cb
                item_layout.addWidget(cb)

            elif item_type == "file":
                le = QLineEdit(self)
                le.setText(str(item.get("value", "") or ""))
                le.setPlaceholderText(str(item.get("placeholder", "파일을 선택하세요") or "파일을 선택하세요"))
                le.setFixedHeight(40)
                le.setStyleSheet(self._line_edit_style())
                self.input_fields[code] = le
                item_layout.addWidget(le)

                btn_text = str(item.get("button_text", "파일 선택") or "파일 선택")
                btn = QPushButton(btn_text, self)
                btn.setFixedHeight(40)
                btn.setStyleSheet(self._button_style())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _checked=False, c=code, it=item: self.on_file_pick_clicked(c, it))
                item_layout.addWidget(btn)

            popup_layout.addLayout(item_layout)

        # 버튼 레이아웃
        button_layout = QHBoxLayout()

        self.cancel_button = create_common_button("취소", self.reject, "#cccccc", 140)
        self.confirm_button = create_common_button("확인", self.on_confirm, "black", 140)

        button_layout.setContentsMargins(0, 15, 0, 0)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.confirm_button)
        popup_layout.addLayout(button_layout)

        self._center_window()

    # =========================
    # actions
    # =========================
    @Slot(str)
    def on_button_clicked(self, code: str) -> None:
        input_widget = self.input_fields.get(code)
        if not isinstance(input_widget, QLineEdit):
            self._emit_log(f"[{code}] 입력 필드를 찾을 수 없습니다.")
            return

        value = input_widget.text()

        worker = self._get_on_demand_worker()
        if worker is None:
            # 기존 코드의 self.site는 정의가 없어 런타임 에러 가능 → code로 대체
            self._emit_log(f"[{code}] on_demand_worker가 없습니다.")
            return

        try:
            # get_list(value) 호출 규약 유지
            result_list: Any = worker.get_list(value)
            self._emit_log(f"[{code}] 결과 수신 완료: {result_list}")

            # 결과를 select(QComboBox)에 반영할 대상 코드 추정 (예: "{code}_select")
            select_code = f"{code}_select"
            select_widget = self.input_fields.get(select_code)

            if isinstance(select_widget, QComboBox):
                select_widget.blockSignals(True)
                select_widget.clear()
                select_widget.addItem("▼ 선택 ▼", "")

                if isinstance(result_list, list):
                    for it in result_list:
                        if not isinstance(it, dict):
                            continue
                        name = str(it.get("key", "") or "")
                        val = str(it.get("value", "") or "")
                        select_widget.addItem(name, val)

                select_widget.setCurrentIndex(0)
                select_widget.blockSignals(False)
            else:
                self._emit_log(f"[{select_code}] select 위젯이 없습니다.")

        except Exception as e:
            self._emit_log(f"[{code}] 실행 중 오류: {e}")

    @Slot(str, object)
    def on_file_pick_clicked(self, code: str, item: _SettingItem) -> None:
        w = self.input_fields.get(code)
        if not isinstance(w, QLineEdit):
            self._emit_log(f"[{code}] 파일 경로 입력 필드를 찾을 수 없습니다.")
            return

        spec = _FilePickSpec(
            dialog_title=str(item.get("dialog_title", "파일 선택") or "파일 선택"),
            file_filter=str(item.get("filter", "All Files (*);;PNG (*.png);;JPG (*.jpg *.jpeg);;WEBP (*.webp)") or ""),
            start_dir=str(item.get("start_dir", os.getcwd()) or os.getcwd()),
        )

        path, _ = QFileDialog.getOpenFileName(self, spec.dialog_title, spec.start_dir, spec.file_filter)
        if not path:
            return

        w.setText(path)
        self._emit_log(f"[{code}] 파일 선택: {path}")

    @Slot()
    def on_confirm(self) -> None:
        setting = self._get_setting()

        for item in setting:
            code = str(item.get("code", "") or "")
            if not code:
                continue

            widget = self.input_fields.get(code)
            if widget is None:
                continue

            item_type = str(item.get("type", "input") or "input")

            # QLineEdit
            if isinstance(widget, QLineEdit):
                text = widget.text()

                # === 신규 === file 타입은 무조건 문자열로 저장
                if item_type == "file":
                    item["value"] = text
                else:
                    # 기존 로직 유지: int 변환 시도 후 실패하면 문자열
                    try:
                        item["value"] = int(text)
                    except ValueError:
                        item["value"] = text

            # QComboBox
            elif isinstance(widget, QComboBox):
                item["value"] = widget.currentData()

            # QCheckBox
            elif isinstance(widget, QCheckBox):
                item["value"] = widget.isChecked()

        self._emit_log(f"setting : {setting}")
        self.accept()