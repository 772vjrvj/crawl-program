# src/ui/popup/param_set_pop.py
from __future__ import annotations

import json  # === 신규 ===
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.global_state import GlobalState
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
    type: str  # input|select|button|check|file|folder
    value: Any

    options: List[_SelectOpt]  # for select
    placeholder: str           # for file/folder
    button_text: str           # for file/folder
    dialog_title: str          # for file/folder
    filter: str                # for file


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
            padding: 8px;
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

    def _scroll_style(self) -> str:
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

    # === 신규 === 현재 site의 config_old.json 경로 해석
    def _resolve_site_config_path(self) -> Optional[str]:
        try:
            state = GlobalState()
            app_config = state.get(GlobalState.APP_CONFIG) or {}
            site = str(state.get(GlobalState.SITE) or "").strip()
            runtime_dir = str(app_config.get("runtime_dir") or "").strip()

            if not runtime_dir:
                self._emit_log("[설정저장] runtime_dir 값이 없습니다.")
                return None

            if not site:
                self._emit_log("[설정저장] site 값이 없습니다.")
                return None

            app_json_path = os.path.join(runtime_dir, "app.json")
            if not os.path.exists(app_json_path):
                self._emit_log(f"[설정저장] app.json 파일이 없습니다: {app_json_path}")
                return None

            try:
                with open(app_json_path, "r", encoding="utf-8") as f:
                    app_json = json.load(f)
            except Exception as e:
                self._emit_log(f"[설정저장] app.json 읽기 실패: {str(e)}")
                return None

            site_list = app_json.get("site_list") or []
            if not isinstance(site_list, list):
                self._emit_log("[설정저장] app.json의 site_list 형식이 올바르지 않습니다.")
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
                self._emit_log(f"[설정저장] site_list에서 '{site}' 설정을 찾지 못했습니다.")
                return None

            config_path = os.path.join(runtime_dir, *config_rel_path.split("/"))
            config_path = os.path.normpath(config_path)

            self._emit_log(f"[설정저장] config 경로 확인: {config_path}")
            return config_path

        except Exception as e:
            self._emit_log(f"[설정저장] config 경로 해석 중 오류: {str(e)}")
            return None

    # === 신규 === runtime config.json의 setting.value 동기화
    def _save_setting_to_runtime_config(self, setting: List[_SettingItem]) -> None:
        try:
            config_path = self._resolve_site_config_path()
            if not config_path:
                return

            if not os.path.exists(config_path):
                self._emit_log(f"[설정저장] config_old.json 파일이 없습니다: {config_path}")
                return

            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                self._emit_log(f"[설정저장] config_old.json 읽기 실패: {str(e)}")
                return

            config_setting = config_data.get("setting") or []
            if not isinstance(config_setting, list):
                self._emit_log("[설정저장] config.json의 setting 형식이 올바르지 않습니다.")
                return

            value_map_by_code: Dict[str, Any] = {}
            for item in setting:
                code = str(item.get("code", "") or "").strip()
                if code:
                    value_map_by_code[code] = item.get("value")

            changed_count = 0

            for cfg_item in config_setting:
                if not isinstance(cfg_item, dict):
                    continue

                code = str(cfg_item.get("code", "") or "").strip()
                if not code:
                    continue

                if code not in value_map_by_code:
                    continue

                old_value = cfg_item.get("value")
                new_value = value_map_by_code.get(code)

                if old_value != new_value:
                    cfg_item["value"] = new_value
                    changed_count += 1
                else:
                    cfg_item["value"] = new_value

            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception as e:
                self._emit_log(f"[설정저장] config_old.json 저장 실패: {str(e)}")
                return

            self._emit_log(
                f"[설정저장] 저장 완료 / 변경건수={changed_count} / path={config_path}"
            )

        except Exception as e:
            self._emit_log(f"[설정저장] 처리 중 오류: {str(e)}")

    def _get_default_start_dir(self, item: Optional[_SettingItem] = None) -> str:
        path_type = str((item or {}).get("path_type", "doc") or "doc").strip().lower()

        if path_type == "main":
            return self._get_main_start_dir()

        documents_dir = os.path.join(os.path.expanduser("~"), "Documents")
        if os.path.isdir(documents_dir):
            return documents_dir

        home_dir = os.path.expanduser("~")
        if os.path.isdir(home_dir):
            return home_dir

        return os.getcwd()

    def _get_main_start_dir(self) -> str:
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(exe_dir):
                return exe_dir

        argv0 = os.path.dirname(os.path.abspath(sys.argv[0]))
        if os.path.isdir(argv0):
            return argv0

        cwd = os.getcwd()
        if os.path.isdir(cwd):
            return cwd

        return os.path.expanduser("~")

    def _center_window(self) -> None:
        frame = self.frameGeometry()
        screen = self.screen()
        if screen is None:
            return

        center = screen.availableGeometry().center()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    # =========================
    # UI
    # =========================
    def set_layout(self) -> None:
        self.setWindowTitle("설정")
        self.resize(400, 500)
        self.setMinimumSize(400, 500)
        self.setStyleSheet("QDialog { background: white; color: #111; } QLabel { color: #111; }")
        self.setWindowIcon(self._make_window_icon())

        popup_layout = QVBoxLayout(self)
        popup_layout.setContentsMargins(10, 10, 10, 10)
        popup_layout.setSpacing(8)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(self._scroll_style())

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 10, 0)
        body_layout.setSpacing(0)

        for item in self._get_setting():
            item_type = str(item.get("type", "input") or "input")
            code = str(item.get("code", "") or "")
            name = str(item.get("name", "") or "")

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
                le = QLineEdit(self)
                le.setText(str(item.get("value", "") or ""))
                le.setFixedHeight(40)
                le.setStyleSheet(self._line_edit_style())
                self.input_fields[code] = le
                item_layout.addWidget(le)

                btn = QPushButton("조회", self)
                btn.setFixedHeight(40)
                btn.setStyleSheet(self._button_style())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
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

            elif item_type == "folder":
                le = QLineEdit(self)

                folder_value = str(item.get("value", "") or "").strip()
                if not folder_value:
                    folder_value = self._get_default_start_dir(item)

                le.setText(folder_value)
                le.setPlaceholderText(str(item.get("placeholder", "폴더를 선택하세요") or "폴더를 선택하세요"))
                le.setFixedHeight(40)
                le.setStyleSheet(self._line_edit_style())
                self.input_fields[code] = le
                item_layout.addWidget(le)

                btn_text = str(item.get("button_text", "폴더 선택") or "폴더 선택")
                btn = QPushButton(btn_text, self)
                btn.setFixedHeight(40)
                btn.setStyleSheet(self._button_style())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _checked=False, c=code, it=item: self.on_folder_pick_clicked(c, it))
                item_layout.addWidget(btn)

            body_layout.addLayout(item_layout)

        body_layout.addStretch()
        scroll.setWidget(body)
        popup_layout.addWidget(scroll)

        button_layout = QHBoxLayout()

        self.cancel_button = create_common_button("취소", self.reject, "#cccccc", 140)
        self.confirm_button = create_common_button("확인", self.on_confirm, "black", 140)

        button_layout.setContentsMargins(0, 12, 0, 0)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.confirm_button)
        popup_layout.addLayout(button_layout)

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
            self._emit_log(f"[{code}] on_demand_worker가 없습니다.")
            return

        try:
            result_list: Any = worker.get_list(value)
            self._emit_log(f"[{code}] 결과 수신 완료: {result_list}")

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
            self._emit_log(f"[{code}] 실행 중 오류: {str(e)}")

    @Slot(str, object)
    def on_file_pick_clicked(self, code: str, item: _SettingItem) -> None:
        w = self.input_fields.get(code)
        if not isinstance(w, QLineEdit):
            self._emit_log(f"[{code}] 파일 경로 입력 필드를 찾을 수 없습니다.")
            return

        spec = _FilePickSpec(
            dialog_title=str(item.get("dialog_title", "파일 선택") or "파일 선택"),
            file_filter=str(item.get("filter", "All Files (*);;PNG (*.png);;JPG (*.jpg *.jpeg);;WEBP (*.webp)") or ""),
            start_dir=self._get_default_start_dir(item)
        )

        path, _ = QFileDialog.getOpenFileName(self, spec.dialog_title, spec.start_dir, spec.file_filter)
        if not path:
            return

        w.setText(path)
        self._emit_log(f"[{code}] 파일 선택: {path}")

    @Slot(str, object)
    def on_folder_pick_clicked(self, code: str, item: _SettingItem) -> None:
        w = self.input_fields.get(code)
        if not isinstance(w, QLineEdit):
            self._emit_log(f"[{code}] 폴더 경로 입력 필드를 찾을 수 없습니다.")
            return

        dialog_title = str(item.get("dialog_title", "폴더 선택") or "폴더 선택")
        start_dir = self._get_default_start_dir(item)

        path = QFileDialog.getExistingDirectory(self, dialog_title, start_dir)
        if not path:
            return

        w.setText(path)
        self._emit_log(f"[{code}] 폴더 선택: {path}")

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

            if isinstance(widget, QLineEdit):
                text = widget.text()

                if item_type in ("file", "folder"):
                    item["value"] = text
                else:
                    try:
                        item["value"] = int(text)
                    except ValueError:
                        item["value"] = text

            elif isinstance(widget, QComboBox):
                item["value"] = widget.currentData()

            elif isinstance(widget, QCheckBox):
                item["value"] = widget.isChecked()

        self._save_setting_to_runtime_config(setting)
        self._emit_log(f"setting : {setting}")
        self.accept()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._center_window()