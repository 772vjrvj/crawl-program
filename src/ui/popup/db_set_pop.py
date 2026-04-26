# ============================================================
# DB 목록/상세목록 조회 팝업
# ============================================================
# 공통 작업 이력 테이블(worker_job_hist)과 사이트별 상세 DB 테이블을
# 좌/우 2분할 테이블 형태로 조회하고 관리하는 PySide6 팝업이다.
#
# 주요 기능
# - 왼쪽: 작업 이력 목록 조회/선택/삭제
# - 오른쪽: 선택한 작업(job_id)의 상세 데이터 조회/삭제/엑셀 저장
# - 상세목록은 한 번에 전체를 불러오지 않고 page size 기준으로 추가 로딩
# - config.json의 db_name, columns, setting 정보를 기준으로
#   테이블명, 컬럼명, 엑셀 저장 경로를 동적으로 처리
# - 테이블 헤더/행 체크박스를 이용한 선택 삭제 지원
# ============================================================
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.global_state import GlobalState
from src.ui.style.style import create_common_button
from src.utils.excel_utils import ExcelUtils


class CheckBoxHeader(QHeaderView):
    toggled = Signal(bool)

    def __init__(self, orientation: Qt.Orientation, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation, parent)
        self.checked = False
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setSectionsClickable(True)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        super().paintSection(painter, rect, logical_index)

        if logical_index != 0:
            return

        size = 18
        box_rect = QRect(
            rect.x() + (rect.width() - size) // 2,
            rect.y() + (rect.height() - size) // 2,
            size,
            size,
            )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor("#888888"))
        pen.setWidth(2)

        painter.setPen(pen)
        painter.setBrush(QColor("black") if self.checked else QColor("white"))
        painter.drawRoundedRect(box_rect, 4, 4)

        painter.restore()

    def mouseMoveEvent(self, event) -> None:
        if self.logicalIndexAt(event.pos()) == 0:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.viewport().unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self.logicalIndexAt(event.pos()) == 0:
            self.set_checked(not self.checked)
            self.toggled.emit(self.checked)
            event.accept()
            return

        super().mousePressEvent(event)

    def set_checked(self, checked: bool) -> None:
        self.checked = bool(checked)
        self.viewport().update()


class DbTableWidget(QTableWidget):
    row_clicked_signal = Signal(int)

    CHECK_WIDTH = 42
    NO_WIDTH = 56
    DATA_WIDTH = 130

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.row_meta: list[dict[str, Any]] = []
        self.display_columns: list[str] = []

        header = CheckBoxHeader(Qt.Orientation.Horizontal, self)
        header.toggled.connect(self.toggle_all_checked)
        self.setHorizontalHeader(header)

        self.verticalHeader().setVisible(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setSortingEnabled(False)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setStyleSheet(self.table_style())

    @staticmethod
    def table_style() -> str:
        return """
        QTableWidget {
            background: white;
            color: #111;
            border: 1px solid #dcdcdc;
            border-radius: 0px;
            gridline-color: #ececec;
            selection-background-color: #eaf2ff;
            selection-color: #111;
            alternate-background-color: #fafafa;
            font-size: 12px;
        }

        QTableWidget::item:selected {
            background: #eaf2ff;
            color: #111;
        }

        QHeaderView::section {
            background: #f6f6f6;
            color: #111;
            font-weight: bold;
            border: none;
            border-right: 1px solid #ececec;
            border-bottom: 1px solid #ececec;
            padding: 8px 6px;
        }

        QTableCornerButton::section,
        QAbstractScrollArea::corner {
            background: white;
            border: none;
        }

        QScrollBar:vertical,
        QScrollBar:horizontal {
            background: #f3f3f3;
            border: none;
        }

        QScrollBar:vertical {
            width: 12px;
        }

        QScrollBar:horizontal {
            height: 12px;
        }

        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {
            background: #c9c9c9;
            border-radius: 5px;
            min-height: 24px;
            min-width: 24px;
        }

        QScrollBar::add-line,
        QScrollBar::sub-line {
            width: 0px;
            height: 0px;
            background: transparent;
            border: none;
        }

        QScrollBar::add-page,
        QScrollBar::sub-page {
            background: #f3f3f3;
            border: none;
        }
        """

    @staticmethod
    def checkbox_style() -> str:
        return """
        QCheckBox {
            padding: 0;
            margin: 0;
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

    def make_checkbox_cell(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cb = QCheckBox()
        cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(self.checkbox_style())
        cb.stateChanged.connect(self.sync_header_check_state)

        layout.addWidget(cb)

        return wrap

    def load_rows(self, rows: list[dict[str, Any]], display_columns: list[str], header_labels: list[str],) -> None:
        self.blockSignals(True)
        self.setUpdatesEnabled(False)

        try:
            self.display_columns = list(display_columns or [])
            self.row_meta = []

            self.clear()
            self.setRowCount(0)
            self.setColumnCount(2 + len(self.display_columns))
            self.setHorizontalHeaderLabels(["", "번호", *list(header_labels or [])])

            header = self.horizontalHeader()
            header.setMinimumSectionSize(40)
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

            self.setColumnWidth(0, self.CHECK_WIDTH)
            self.setColumnWidth(1, self.NO_WIDTH)

            for col in range(2, self.columnCount()):
                self.setColumnWidth(col, self.DATA_WIDTH)

            self.set_header_checked(False)
            self.append_rows(rows, start_no=1)

        finally:
            self.setUpdatesEnabled(True)
            self.blockSignals(False)

    def append_rows(self, rows: list[dict[str, Any]], start_no: Optional[int] = None) -> None:
        if not rows:
            return

        self.blockSignals(True)
        self.setUpdatesEnabled(False)

        try:
            start_row = self.rowCount()
            self.setRowCount(start_row + len(rows))

            for idx, row in enumerate(rows):
                row_idx = start_row + idx
                self.row_meta.append(row)

                self.setCellWidget(row_idx, 0, self.make_checkbox_cell())

                no_item = QTableWidgetItem(str((start_no + idx) if start_no else (row_idx + 1)))
                no_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row_idx, 1, no_item)

                for col_idx, key in enumerate(self.display_columns, start=2):
                    text = "" if row.get(key) is None else str(row.get(key))

                    item = QTableWidgetItem(text)
                    item.setToolTip(text)

                    if len(text) <= 12:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    self.setItem(row_idx, col_idx, item)

            self.set_header_checked(False)

        finally:
            self.setUpdatesEnabled(True)
            self.blockSignals(False)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())

        if item and item.column() != 0:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            super().mousePressEvent(event)
            self.row_clicked_signal.emit(item.row())
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        before_row = self.currentRow()

        super().keyPressEvent(event)

        key = event.key()
        move_keys = {
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
        }

        if key in move_keys:
            after_row = self.currentRow()

            if after_row >= 0 and after_row != before_row:
                self.row_clicked_signal.emit(after_row)

    def set_header_checked(self, checked: bool) -> None:
        header = self.horizontalHeader()

        if isinstance(header, CheckBoxHeader):
            header.set_checked(checked)

    def get_checkbox(self, row: int) -> Optional[QCheckBox]:
        wrap = self.cellWidget(row, 0)
        return wrap.findChild(QCheckBox) if wrap else None

    def checked_rows(self) -> list[int]:
        rows = []

        for row in range(self.rowCount()):
            cb = self.get_checkbox(row)

            if cb and cb.isChecked():
                rows.append(row)

        return rows

    def toggle_all_checked(self, checked: bool) -> None:
        for row in range(self.rowCount()):
            cb = self.get_checkbox(row)

            if cb:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)

        self.set_header_checked(checked)

    def sync_header_check_state(self) -> None:
        checked = self.rowCount() > 0 and len(self.checked_rows()) == self.rowCount()
        self.set_header_checked(checked)


class DbSetPop(QDialog):
    """
    DB 작업 이력과 상세 데이터를 좌/우 테이블로 조회/삭제/엑셀저장하는 팝업
    """
    log_signal = Signal(str)

    # 공통 이력 테이블(worker_job_hist)에 표시할 컬럼명 매핑
    HIST_HEADER_MAP = {
        "hist_id": "이력ID",
        "user_id": "사용자ID",
        "start_at": "시작시간",
        "end_at": "종료시간",
        "status": "상태",
        "success_count": "성공건수",
        "fail_count": "실패건수",
        "error_message": "오류메시지",
        "memo": "메모",
    }

    def __init__(
            self,
            parent: Optional[QWidget] = None,
            title: str = "DB목록",
            config_path: Optional[str] = None,
            config_data: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)

        self._parent = parent

        # 해당 site의 config 경로 runtime/customers/naver.../config.json
        self.config_path = config_path or self._resolve_site_config_path()

        # config_path에 있는 사이트 config.json 파일을 읽어서 dict로 반환한다.
        self.config_data = config_data or self._load_config_data()

        # site의 상세 테이블명 가져오기 "key": "NAVER_LAND_REAL_ESTATE_DETAIL"
        self.db_name = self._safe_table_name(self.config_data.get("db_name") or "")

        # 공통 이력 테이블명 가져오기
        self.db_common_name = self._safe_table_name(
            self.config_data.get("db_common_name") or "worker_job_hist"
        )

        # DB 경로 가져오기 runtime/customers/common/db/worker_hist.db
        self.db_path = self._resolve_db_path()

        # 공통 이력 테이블에서 화면에 보여줄 컬럼 목록
        self.hist_columns = list(self.HIST_HEADER_MAP.keys())

        # 상세 테이블에서 화면에 보여줄 컬럼 목록과 헤더명 매핑
        self.detail_columns, self.detail_header_map = self._build_detail_columns()

        # 왼쪽 테이블에 표시할 공통 작업 이력 데이터
        self.hist_rows: list[dict[str, Any]] = []

        # 오른쪽 테이블에 표시할 상세 데이터
        self.detail_rows: list[dict[str, Any]] = []

        # 현재 선택된 작업 이력 row
        self.current_hist_row: Optional[dict[str, Any]] = None

        # 현재 선택된 작업의 job_id
        self.current_job_id = ""

        # 상세 데이터 전체 건수
        self.detail_total_count = 0

        # 현재 화면에 로딩된 상세 데이터 건수
        self.detail_loaded_count = 0

        # 상세 데이터 추가 로딩 단위
        self.detail_page_size = 100

        # 상세 데이터 로딩 중 여부
        self.detail_loading = False

        # 왼쪽 작업목록 전체 건수 표시 라벨
        self.left_count_label: Optional[QLabel] = None

        # 오른쪽 상세목록 전체/표시 건수 표시 라벨
        self.right_count_label: Optional[QLabel] = None

        # 왼쪽 작업 이력 테이블
        self.left_table: Optional[DbTableWidget] = None

        # 오른쪽 상세 데이터 테이블
        self.right_table: Optional[DbTableWidget] = None

        # 오른쪽 상세 데이터 추가 로딩 개수 선택 콤보박스
        self.right_page_size_combo: Optional[QComboBox] = None

        # 팝업 기본 설정
        self.setWindowTitle(title)
        self.resize(1650, 860)
        self.setMinimumSize(1500, 760)
        self.setStyleSheet("background-color: white; color: #111;")

        # UI 생성 후 작업 이력 목록 로딩
        self.init_ui()
        self.load_hist_rows()


    def init_ui(self) -> None:
        """
        팝업의 전체 UI 레이아웃을 구성한다.
        화면 구조는 상단 제목 / 가운데 좌우 테이블 / 하단 확인 버튼으로 나뉜다.
        """
        # root
        # ├─ title_label        # 상단 제목
        # ├─ splitter           # 가운데 좌우 분할
        # │   ├─ left_panel     # 작업목록
        # │   └─ right_panel    # 상세목록
        # └─ btn_row            # 하단 확인 버튼
        # [상단 제목 title_label]
        # ↑
        # 6px 간격
        #
        # [가운데 splitter 영역]
        # ↑
        # 6px 간격
        #
        # [하단 확인 버튼 영역 btn_row]
        # ============================================================
        # 1. 최상위 레이아웃
        #    - 팝업 전체를 위에서 아래로 쌓는 세로 레이아웃
        # ============================================================
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)  # left, top, right, bottom
        root.setSpacing(6)                      # 위젯 간 세로 간격

        # ============================================================
        # 2. 상단 제목 영역
        #    - 팝업 제목(DB목록)을 가운데 정렬로 표시
        # ============================================================
        title_label = QLabel(self.windowTitle(), self)
        title_label.setFixedHeight(30)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #111; padding: 0;")
        root.addWidget(title_label)

        # ============================================================
        # 3. 가운데 본문 영역
        #    - 왼쪽 작업목록 / 오른쪽 상세목록을 좌우로 나누는 영역
        # ============================================================
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(8)              # 좌우 패널 사이 조절바 너비
        splitter.setChildrenCollapsible(False)  # 한쪽 패널이 완전히 접히지 않도록 설정

        # 왼쪽 패널: 작업 이력 목록
        splitter.addWidget(self.build_left_panel())

        # 오른쪽 패널: 선택한 작업의 상세 데이터 목록
        splitter.addWidget(self.build_right_panel())

        # 왼쪽/오른쪽 패널 비율 설정
        splitter.setStretchFactor(0, 4)         # 왼쪽 영역 비율
        splitter.setStretchFactor(1, 7)         # 오른쪽 영역 비율

        # 팝업 처음 열릴 때의 좌우 초기 크기
        splitter.setSizes([520, 1000])

        # 가운데 본문 영역을 남은 공간 전체에 채우기
        root.addWidget(splitter, 1)

        # ============================================================
        # 4. 하단 버튼 영역
        #    - 오른쪽 정렬된 확인 버튼
        # ============================================================
        btn_row = QHBoxLayout()
        btn_row.addStretch()  # 버튼을 오른쪽으로 밀기
        btn_row.addWidget(create_common_button("확인", self.accept, "black", 140))
        root.addLayout(btn_row)


    def build_left_panel(self) -> QWidget:
        wrap = QWidget()
        layout = self.make_panel_layout(wrap)

        layout.addWidget(self.make_title("작업목록"))

        top = QHBoxLayout()
        top.addWidget(self.make_button("삭제", self.delete_left_checked))
        top.addStretch()

        self.left_count_label = self.make_count_label()
        top.addWidget(self.left_count_label)

        layout.addLayout(top)

        self.left_table = DbTableWidget(self)
        self.left_table.row_clicked_signal.connect(self.on_left_row_clicked)
        layout.addWidget(self.left_table, 1)

        return wrap


    def build_right_panel(self) -> QWidget:
        wrap = QWidget()
        layout = self.make_panel_layout(wrap)

        layout.addWidget(self.make_title("상세목록"))

        top = QHBoxLayout()
        top.setSpacing(8)

        top.addWidget(self.make_button("삭제", self.delete_right_checked))
        top.addWidget(self.make_button("엑셀 저장", self.save_detail_to_excel, black=True, width=110))
        top.addStretch()

        self.right_page_size_combo = QComboBox()
        self.right_page_size_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.right_page_size_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.right_page_size_combo.setFixedSize(190, 34)
        self.right_page_size_combo.setStyleSheet(self.combo_style())

        for size in [100, 300, 500]:
            self.right_page_size_combo.addItem(f"{size}개씩 보기", size)

        self.right_page_size_combo.currentIndexChanged.connect(self.on_detail_page_size_changed)

        self.right_count_label = self.make_count_label()

        top.addWidget(self.right_page_size_combo)
        top.addWidget(self.right_count_label)

        layout.addLayout(top)

        self.right_table = DbTableWidget(self)
        self.right_table.verticalScrollBar().valueChanged.connect(self.on_right_scroll_changed)
        layout.addWidget(self.right_table, 1)

        return wrap


    @staticmethod
    def make_panel_layout(parent: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        return layout

    @staticmethod
    def make_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedHeight(30)
        label.setStyleSheet("font-size: 17px; font-weight: bold; color: #111; padding: 0;")
        return label

    @staticmethod
    def make_count_label() -> QLabel:
        label = QLabel("전체 row수 0")
        label.setStyleSheet("font-size: 13px; font-weight: bold; color: #333;")
        return label

    def make_button(self, text: str, callback, black: bool = False, width: int = 90) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(width, 34)
        btn.setStyleSheet(self.button_style(black))
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def button_style(black: bool = False) -> str:
        bg = "black" if black else "#efefef"
        fg = "white" if black else "#111"
        hover = "#222" if black else "#e4e4e4"

        return f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
        }}

        QPushButton:hover {{
            background: {hover};
        }}
        """

    @staticmethod
    def combo_style() -> str:
        return """
        QComboBox {
            background: white;
            color: #111;
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            padding: 0 12px;
            font-size: 13px;
            font-weight: bold;
        }

        QComboBox:hover {
            border: 1px solid #999;
        }
        """

    @staticmethod
    def _safe_table_name(name: str) -> str:
        """
        SQL에 직접 들어가는 테이블명이 안전한 형식인지 검사한다.
        테이블명은 파라미터 바인딩이 안 되기 때문에 영문/숫자/_ 만 허용한다.
        """
        name = str(name or "").strip()

        if not name:
            raise ValueError("테이블명이 없습니다.")

        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"잘못된 테이블명입니다: {name}")

        return name


    def _resolve_site_config_path(self) -> Optional[str]:
        """
        현재 선택된 사이트 key를 기준으로 app.json에서 해당 사이트의 config.json 경로를 찾는다.
        찾지 못하면 None을 반환한다.
        """
        try:
            state = GlobalState()
            app_config = state.get(GlobalState.APP_CONFIG) or {}

            # 현재 선택된 사이트 key
            # 예: "NAVER_LAND_REAL_ESTATE_DETAIL"
            site = str(state.get(GlobalState.SITE) or "").strip()

            # runtime 기준 경로
            runtime_dir = str(app_config.get("runtime_dir") or "").strip()

            if not runtime_dir or not site:
                return None

            app_json_path = os.path.join(runtime_dir, "app.json")

            if not os.path.exists(app_json_path):
                return None

            with open(app_json_path, "r", encoding="utf-8") as f:
                app_json = json.load(f)

            # app.json의 site_list에서 현재 site와 일치하는 config_path를 찾는다.
            for site_item in app_json.get("site_list") or []:
                if str(site_item.get("key") or "").strip() == site:
                    rel_path = str(site_item.get("config_path") or "").strip()
                    return os.path.normpath(os.path.join(runtime_dir, *rel_path.split("/")))

        except Exception:
            pass

        return None


    def _load_config_data(self) -> dict[str, Any]:
        """
        config_path에 있는 사이트 config.json 파일을 읽어서 dict로 반환한다.
        config_path가 없거나 파일이 없으면 빈 dict를 반환한다.
        """
        if self.config_path and os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


    def _resolve_db_path(self) -> str:
        """
        공통 작업 이력 DB(worker_hist.db)의 경로를 결정한다.
        여기서는 DB 파일을 열지 않고, 사용할 DB 경로 문자열만 만든다.
        실제 DB 파일 존재 여부는 _connect()에서 검사한다.
        """
        # config_path가 있으면 config.json 위치를 기준으로 runtime 경로를 역산한다.
        if self.config_path:
            runtime_dir = os.path.dirname(os.path.dirname(os.path.dirname(self.config_path)))
            return os.path.join(runtime_dir, "customers", "common", "db", "worker_hist.db")

        try:
            state = GlobalState()
            app_config = state.get(GlobalState.APP_CONFIG) or {}
            runtime_dir = str(app_config.get("runtime_dir") or "").strip()

            # GlobalState에 runtime_dir이 있으면 그 경로 기준으로 DB 경로를 만든다.
            if runtime_dir:
                return os.path.join(runtime_dir, "customers", "common", "db", "worker_hist.db")

        except Exception:
            pass

        # 위 방식으로 runtime 경로를 못 찾은 경우의 최후 fallback 경로
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()

        return os.path.join(base_dir, "runtime", "customers", "common", "db", "worker_hist.db")


    def _get_folder_path(self) -> str:
        for row in self.config_data.get("setting") or []:
            if not isinstance(row, dict):
                continue

            if str(row.get("code") or "").strip() == "folder_path":
                value = str(row.get("value") or "").strip()

                if value:
                    return value

        return os.path.dirname(self.db_path)

    def _build_detail_columns(self) -> tuple[list[str], dict[str, str]]:
        columns = []
        header_map = {}

        for row in self.config_data.get("columns") or []:
            if not isinstance(row, dict):
                continue

            code = str(row.get("code") or "").strip()

            if code:
                columns.append(code)
                header_map[code] = str(row.get("value") or code).strip()

        return columns, header_map

    def _connect(self) -> sqlite3.Connection:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"DB 파일이 없습니다: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        return conn

    def load_hist_rows(self) -> None:
        if not self.left_table or not self.left_count_label:
            return

        self.current_hist_row = None
        self.current_job_id = ""
        self.detail_rows = []

        try:
            with self._connect() as conn:
                cur = conn.execute(
                    f"""
                    SELECT
                        hist_id,
                        job_id,
                        user_id,
                        start_at,
                        end_at,
                        status,
                        success_count,
                        fail_count,
                        error_message,
                        memo
                    FROM {self.db_common_name}
                    WHERE UPPER(table_name) = UPPER(?)
                    ORDER BY hist_id DESC
                    """,
                    (self.db_name,),
                )

                self.hist_rows = [dict(row) for row in cur.fetchall()]

        except Exception as e:
            self.hist_rows = []
            QMessageBox.warning(self, "오류", f"작업목록 조회 실패\n{e}")

        self.left_table.load_rows(
            self.hist_rows,
            self.hist_columns,
            [self.HIST_HEADER_MAP[col] for col in self.hist_columns],
        )

        self.left_count_label.setText(f"전체 row수 {len(self.hist_rows)}")
        self.clear_detail_rows()

    def clear_detail_rows(self) -> None:
        self.current_hist_row = None
        self.current_job_id = ""
        self.detail_rows = []
        self.detail_total_count = 0
        self.detail_loaded_count = 0
        self.detail_loading = False

        if self.right_table:
            self.right_table.load_rows(
                [],
                self.detail_columns,
                [self.detail_header_map.get(col, col) for col in self.detail_columns],
            )

        self.update_detail_count_label()

    def update_detail_count_label(self) -> None:
        if not self.right_count_label:
            return

        self.right_count_label.setText(
            f"전체 row수 {self.detail_total_count:,} / 표시 {self.detail_loaded_count:,}"
        )

    def set_detail_loading(self, loading: bool) -> None:
        self.detail_loading = bool(loading)
        self.update_detail_count_label()

        if loading:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

        QApplication.processEvents()

    def on_left_row_clicked(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self.hist_rows):
            return

        self.current_hist_row = self.hist_rows[row_index]
        self.load_detail_rows_by_job_id(str(self.current_hist_row.get("job_id") or ""))

    def load_detail_rows_by_job_id(self, job_id: str) -> None:
        if not self.right_table:
            return

        self.current_job_id = str(job_id or "").strip()
        self.detail_rows = []
        self.detail_total_count = 0
        self.detail_loaded_count = 0
        self.detail_loading = False

        self.right_table.load_rows(
            [],
            self.detail_columns,
            [self.detail_header_map.get(col, col) for col in self.detail_columns],
        )

        self.update_detail_count_label()

        if not self.current_job_id:
            return

        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {self.db_name} WHERE job_id = ?",
                    (self.current_job_id,),
                ).fetchone()

                self.detail_total_count = int(row["cnt"] if row else 0)

        except Exception as e:
            QMessageBox.warning(self, "오류", f"상세목록 개수 조회 실패\n{e}")
            self.update_detail_count_label()
            return

        self.update_detail_count_label()
        self.load_next_detail_rows()

    def on_right_scroll_changed(self, value: int) -> None:
        if not self.right_table:
            return

        if self.detail_loading or not self.current_job_id:
            return

        if self.detail_loaded_count >= self.detail_total_count:
            return

        scrollbar = self.right_table.verticalScrollBar()

        if value >= scrollbar.maximum() - 30:
            self.load_next_detail_rows()

    def on_detail_page_size_changed(self) -> None:
        if self.right_page_size_combo:
            self.detail_page_size = int(self.right_page_size_combo.currentData() or 100)

        if self.current_hist_row:
            self.load_detail_rows_by_job_id(str(self.current_hist_row.get("job_id") or ""))

    def load_next_detail_rows(self) -> None:
        if not self.right_table:
            return

        if self.detail_loading or not self.current_job_id:
            return

        if self.detail_loaded_count >= self.detail_total_count:
            self.update_detail_count_label()
            return

        limit = int(self.detail_page_size or 100)
        offset = int(self.detail_loaded_count or 0)

        self.set_detail_loading(True)

        try:
            with self._connect() as conn:
                cur = conn.execute(
                    f"""
                    SELECT rowid AS __rowid__, *
                    FROM {self.db_name}
                    WHERE job_id = ?
                    ORDER BY rowid DESC
                    LIMIT ? OFFSET ?
                    """,
                    (self.current_job_id, limit, offset),
                )

                rows = [dict(row) for row in cur.fetchall()]

            if rows:
                self.detail_rows.extend(rows)
                self.right_table.append_rows(rows, start_no=offset + 1)
                self.detail_loaded_count += len(rows)

        except Exception as e:
            QMessageBox.warning(self, "오류", f"상세목록 조회 실패\n{e}")

        finally:
            self.set_detail_loading(False)
            self.update_detail_count_label()


    # 삭제 확인 팝업
    def confirm_delete(self) -> bool:
        """
        삭제 전 확인 팝업을 띄운다.
        Yes를 누르면 True, No를 누르면 False를 반환한다.
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("삭제 확인")
        msg.setText("선택한 항목을 삭제 하겠습니까?")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        # 제목이 잘리지 않도록 팝업 최소 너비 지정
        msg.setMinimumWidth(360)

        result = msg.exec()

        return result == QMessageBox.StandardButton.Yes


    # 왼쪽 공통 테이블에서 삭제 좌우 모두 삭제됨
    def delete_left_checked(self) -> None:
        if not self.left_table:
            return

        checked = self.left_table.checked_rows()

        if not checked:
            QMessageBox.information(self, "알림", "삭제할 항목을 선택해주세요.")
            return

        if not self.confirm_delete():
            return

        targets = [self.hist_rows[i] for i in checked if i < len(self.hist_rows)]

        try:
            with self._connect() as conn:
                for row in targets:
                    hist_id = row.get("hist_id")
                    job_id = row.get("job_id")

                    conn.execute(
                        f"DELETE FROM {self.db_name} WHERE hist_id = ? OR job_id = ?",
                        (hist_id, job_id),
                    )

                    conn.execute(
                        f"""
                        DELETE FROM {self.db_common_name}
                        WHERE hist_id = ?
                          AND UPPER(table_name) = UPPER(?)
                        """,
                        (hist_id, self.db_name),
                    )

            QMessageBox.information(self, "알림", "삭제되었습니다.")
            self.load_hist_rows()

        except Exception as e:
            QMessageBox.warning(self, "오류", f"삭제 실패\n{e}")


    def delete_right_checked(self) -> None:
        if not self.right_table:
            return

        checked = self.right_table.checked_rows()

        if not checked:
            QMessageBox.information(self, "알림", "삭제할 항목을 선택해주세요.")
            return

        if not self.confirm_delete():
            return

        targets = [self.detail_rows[i] for i in checked if i < len(self.detail_rows)]

        try:
            with self._connect() as conn:
                for row in targets:
                    conn.execute(
                        f"DELETE FROM {self.db_name} WHERE rowid = ?",
                        (row.get("__rowid__"),),
                    )

            QMessageBox.information(self, "알림", "삭제되었습니다.")

            if self.current_hist_row:
                self.refresh_current_hist()
            else:
                self.clear_detail_rows()

        except Exception as e:
            QMessageBox.warning(self, "오류", f"삭제 실패\n{e}")

    def refresh_current_hist(self) -> None:
        if not self.current_hist_row:
            self.load_hist_rows()
            return

        hist_id = self.current_hist_row.get("hist_id")
        job_id = str(self.current_hist_row.get("job_id") or "")

        try:
            with self._connect() as conn:
                success_count = conn.execute(
                    f"""
                    SELECT COUNT(*) AS cnt
                    FROM {self.db_name}
                    WHERE job_id = ?
                      AND UPPER(COALESCE(row_status, '')) = 'SUCCESS'
                    """,
                    (job_id,),
                ).fetchone()["cnt"]

                fail_count = conn.execute(
                    f"""
                    SELECT COUNT(*) AS cnt
                    FROM {self.db_name}
                    WHERE job_id = ?
                      AND UPPER(COALESCE(row_status, '')) = 'FAIL'
                    """,
                    (job_id,),
                ).fetchone()["cnt"]

                conn.execute(
                    f"""
                    UPDATE {self.db_common_name}
                    SET
                        total_count = ?,
                        success_count = ?,
                        fail_count = ?,
                        updated_at = ?
                    WHERE hist_id = ?
                      AND UPPER(table_name) = UPPER(?)
                    """,
                    (
                        int(success_count) + int(fail_count),
                        int(success_count),
                        int(fail_count),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        hist_id,
                        self.db_name,
                    ),
                )

        except Exception:
            pass

        self.load_hist_rows()

        if not self.left_table:
            return

        for row_index, row in enumerate(self.hist_rows):
            if row.get("hist_id") == hist_id:
                self.left_table.selectRow(row_index)
                self.current_hist_row = row
                self.load_detail_rows_by_job_id(job_id)
                break

    def fetch_all_detail_rows_for_current_job(self) -> list[dict[str, Any]]:
        if not self.current_job_id:
            return []

        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT rowid AS __rowid__, *
                FROM {self.db_name}
                WHERE job_id = ?
                ORDER BY rowid DESC
                """,
                (self.current_job_id,),
            )

            return [dict(row) for row in cur.fetchall()]

    def save_detail_to_excel(self) -> None:
        if not self.current_job_id:
            QMessageBox.information(self, "알림", "저장할게 없습니다.")
            return

        job_id = ""

        if self.current_hist_row:
            job_id = str(self.current_hist_row.get("job_id") or "").strip()

        filename = (
            f"{self.db_name.lower()}_"
            f"{job_id or 'detail'}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        self.set_detail_loading(True)

        try:
            excel_rows = self.fetch_all_detail_rows_for_current_job()

            if not excel_rows:
                QMessageBox.information(self, "알림", "저장할게 없습니다.")
                return

            column_widths = [
                {
                    "컬럼": self.detail_header_map.get(col, col),
                    "너비": 16,
                }
                for col in self.detail_columns
            ]

            excel = ExcelUtils(log_func=lambda msg: self.log_signal.emit(str(msg)))

            ok = excel.save_db_rows_to_excel(
                excel_filename=filename,
                row_list=excel_rows,
                columns=self.detail_columns,
                header_map=self.detail_header_map,
                sheet_name="상세목록",
                folder_path=self._get_folder_path(),
                sub_dir="output",
                column_widths=column_widths,
                default_width=16,
            )

            if ok:
                QMessageBox.information(self, "알림", "엑셀이 저장되었습니다.")
            else:
                QMessageBox.warning(self, "오류", "엑셀 저장에 실패했습니다.")

        except Exception as e:
            QMessageBox.warning(self, "오류", f"엑셀 저장 실패\n{e}")

        finally:
            self.set_detail_loading(False)