# src/ui/main_window.py
from __future__ import annotations  # === 신규 ===

from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Optional, Any, List, Tuple, Protocol, cast

from src.ui.popup.detail_all_style_set_pop import DetailAllStyleSetPop
from src.ui.popup.region_filter_favorite_set_pop import RegionFilterFavoriteSetPop
from src.utils.run_file_logger import RunFileLogger
import keyring
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QApplication
)
from requests import Session
from src.workers.logout_worker import LogoutWorker
from src.utils.config import server_name, server_url
from src.workers.check_worker import CheckWorker
from src.workers.worker_factory import create_worker_from_site_config
from src.workers.progress_worker import ProgressWorker
from src.workers.cleanup_worker import CleanupWorker

from src.core.global_state import GlobalState
from src.ui.popup.column_set_pop import ColumnSetPop
from src.ui.popup.countdown_pop import CountdownPop
from src.ui.popup.detail_set_pop import DetailSetPop
from src.ui.popup.excel_set_pop import ExcelSetPop
from src.ui.popup.db_set_pop import DbSetPop, ProcessingDialog
from src.ui.popup.param_set_pop import ParamSetPop
from src.ui.popup.region_set_pop import RegionSetPop
from src.ui.popup.site_set_pop import SiteSetPop
from src.ui.popup.closing_pop import ClosingPop
from src.ui.popup.user_info_pop import UserInfoPop
from src.ui.popup.program_info_pop import ProgramInfoPop
from src.utils.program_notice_read_store import ProgramNoticeReadStore
from src.workers.program_notice_worker import (
    ProgramNotice,
    ProgramNoticeWorker,
    ProgramNoticeListResult,
)
from src.ui.style.style import create_common_button, main_style, LOG_STYLE, HEADER_TEXT_STYLE

import sys

# =========================================================
# typing helpers (Protocol)
# =========================================================
class AppManagerProto(Protocol):
    def go_to_select(self) -> None: ...
    def go_to_login(self) -> None: ...


class StoppableThreadProto(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class ApiWorkerProto(StoppableThreadProto, Protocol):
    def wait(self, msecs: int = 30000) -> bool: ...
    api_failure: Any
    log_signal: Any


class ProgressWorkerProto(StoppableThreadProto, Protocol):
    def quit(self) -> None: ...
    def wait(self, msecs: int = 30000) -> bool: ...
    progress_signal: Any
    log_signal: Any


class OnDemandWorkerProto(StoppableThreadProto, Protocol):
    log_signal: Any
    show_countdown_signal: Any
    progress_signal: Any
    msg_signal: Any
    progress_end_signal: Any
    def quit(self) -> None: ...
    def wait(self, msecs: int = 30000) -> bool: ...
    def stop(self) -> None: ...
    def set_setting(self, setting: Any) -> None: ...
    def set_setting_detail(self, setting_detail: Any) -> None: ...
    def set_setting_detail_all_style(self, set_setting_detail_all_style: Any) -> None: ...
    def set_setting_region_filter_favorite(self, setting_region_filter_favorite: Any) -> None: ...
    def set_columns(self, columns: Any) -> None: ...
    def set_sites(self, sites: Any) -> None: ...
    def set_region(self, regions: List[Any]) -> None: ...
    def set_excel_data_list(self, excel_data_list: List[Any]) -> None: ...
    def set_user(self, user: Any) -> None: ...
    def set_session(self, session: Optional[Session]) -> None: ...



# =========================================================
# MainWindow
# =========================================================
class MainWindow(QWidget):

    # 초기화
    def __init__(self, app_manager: AppManagerProto):
        super().__init__()

        # 상태값

        self.user: Optional[Any] = None
        self.excel_data_list: Optional[List[Any]] = None

        self.selected_regions: List[Any] = []

        self.columns: Optional[Any] = None
        self.sites: Optional[Any] = None
        self.region: Optional[Any] = None
        self.popup: Optional[Any] = None
        self.setting: Optional[Any] = None
        self.setting_detail: Optional[Any] = None
        self.setting_detail_all_style: Optional[Any] = None
        self.setting_detail_all_style_flag: Optional[Any] = None
        self.setting_region_filter_favorite_flag: Optional[Any] = None
        self.setting_region_filter_favorite: Optional[Any] = None

        self.name: Optional[str] = None
        self.site: Optional[str] = None
        self.color: Optional[str] = None
        self.session: Optional[Session] = None

        # UI 레퍼런스
        self.header_label: Optional[QLabel] = None

        self.left_button_layout: Optional[QHBoxLayout] = None
        self.right_button_layout: Optional[QHBoxLayout] = None

        self.site_list_button: Optional[QWidget] = None
        self.log_reset_button: Optional[QWidget] = None
        self.collect_button: Optional[QWidget] = None
        self.user_info_button: Optional[QWidget] = None
        self.log_out_button: Optional[QWidget] = None

        self.setting_button: Optional[QWidget] = None
        self.detail_setting_button: Optional[QWidget] = None
        self.detail_all_style_setting_button = None
        self.region_filter_favorite_setting_button = None
        self.column_setting_button: Optional[QWidget] = None
        self.site_setting_button: Optional[QWidget] = None
        self.region_setting_button: Optional[QWidget] = None
        self.excel_setting_button: Optional[QWidget] = None

        self.bottom_left_button: Optional[QWidget] = None
        self.program_info_wrap: Optional[QWidget] = None
        self.bottom_center_wrap: Optional[QWidget] = None
        self.bottom_logo_label: Optional[QLabel] = None
        self.bottom_title_label: Optional[QLabel] = None
        self.bottom_url_label: Optional[QLabel] = None
        self.bottom_right_button: Optional[QWidget] = None

        self.progress_bar: Optional[QProgressBar] = None
        self.log_window: Optional[QPlainTextEdit] = None
        self.logout_worker: Optional[LogoutWorker] = None

        # 팝업
        self.region_set_pop: Optional[RegionSetPop] = None
        self.column_set_pop: Optional[ColumnSetPop] = None
        self.site_set_pop: Optional[SiteSetPop] = None
        self.param_set_pop: Optional[ParamSetPop] = None
        self.db_set_pop: Optional[DbSetPop] = None
        self.excel_set_pop: Optional[ExcelSetPop] = None
        self.detail_set_pop: Optional[DetailSetPop] = None
        self.detail_all_style_set_pop = None
        self.region_filter_favorite_set_pop = None

        # 워커/큐
        self.task_queue: Optional[Queue[Tuple[int, int]]] = None
        self.progress_worker: Optional[ProgressWorkerProto] = None
        self.on_demand_worker: Optional[OnDemandWorkerProto] = None
        self.api_worker: Optional[ApiWorkerProto] = None

        self.app_manager: AppManagerProto = app_manager

        self._closing: bool = False
        self._closing_pop: Optional[ClosingPop] = None
        self._cleanup_worker: Optional[CleanupWorker] = None

        self._force_close = False
        self._close_timeout_ms = 8000

        # 프로그램 정보 / 공지 선조회 / 읽음 상태
        self.program_info_pop: Optional[ProgramInfoPop] = None
        self.program_notice_badge: Optional[QLabel] = None
        self.program_notice_worker: Optional[ProgramNoticeWorker] = None
        self.program_notices: list[ProgramNotice] = []
        self.program_notices_loaded: bool = False
        self.program_notice_read_store: Optional[ProgramNoticeReadStore] = None

        self.file_logger: Optional[RunFileLogger] = None


    def ensure_file_logger(self) -> None:
        if self.file_logger is None and self.site:
            try:
                self.file_logger = RunFileLogger(
                    site=str(self.site),
                    logs_dir="logs",
                    retention_days=30,
                )
            except Exception as e:
                if self.log_window is not None:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.log_window.appendPlainText(f"[{timestamp}] [오류] 파일 로그 초기화 실패: {e}")

    # 변경값 세팅
    def common_data_set(self) -> None:
        state = GlobalState()
        self.user = state.get(GlobalState.USER_ID)
        self.name = state.get(GlobalState.NAME)
        self.site = state.get(GlobalState.SITE)
        self.color = state.get(GlobalState.COLOR)
        self.setting = state.get(GlobalState.SETTING)
        self.session = cast(Optional[Session], state.get(GlobalState.SESSION))
        self.columns = state.get(GlobalState.COLUMNS)
        self.sites = state.get(GlobalState.SITES)
        self.region = state.get(GlobalState.REGION)
        self.popup = state.get(GlobalState.POPUP)

        self.setting_detail = state.get(GlobalState.SETTING_DETAIL)
        self.setting_detail_all_style = state.get(GlobalState.SETTING_DETAIL_ALL_STYLE)
        self.setting_detail_all_style_flag = state.get(GlobalState.SETTING_DETAIL_ALL_STYLE_FLAG)

        self.setting_region_filter_favorite = state.get(GlobalState.SETTING_REGION_FILTER_FAVORITE)
        self.setting_region_filter_favorite_flag = state.get(GlobalState.SETTING_REGION_FILTER_FAVORITE_FLAG)



    # 재 초기화
    def init_reset(self) -> None:
        self.common_data_set()
        self.api_worker_set()
        self.main_worker_set()
        self.ui_set()
        self.ensure_file_logger()

        # 메인 화면이 뜬 직후 공지 전체를 미리 조회한다.
        # 팝업에서는 이 데이터를 즉시 사용하므로 공지 카드가 늦게 나타나는 현상을 없앤다.
        QTimer.singleShot(0, self.preload_program_notices)

    # 로그인 확인 체크
    def api_worker_set(self) -> None:
        if self.api_worker is None:
            if self.session is None:  # === 신규 ===
                self.add_log("[오류] session이 없습니다. 다시 로그인 해주세요.")
                self.app_manager.go_to_login()
                return

            w = CheckWorker(self.session, server_url)
            w.api_failure.connect(self.handle_api_failure)
            w.log_signal.connect(self.add_log)
            w.start()
            self.api_worker = cast(ApiWorkerProto, w)

    # 메인 워커 세팅
    def main_worker_set(self) -> None:
        if self.progress_worker is None:
            self.task_queue = Queue()
            pw = ProgressWorker(self.task_queue)
            pw.progress_signal.connect(self.update_progress)
            pw.log_signal.connect(self.add_log)
            self.progress_worker = cast(ProgressWorkerProto, pw)

        if self.on_demand_worker is None:
            if not self.site:
                self.add_log("[오류] site가 비어있습니다.")
                return

            st = GlobalState()

            site_conf = (st.get("site_configs_by_key", {}) or {}).get(str(self.site))
            if not site_conf:
                self.add_log(f"[오류] site_configs_by_key에서 '{self.site}' 설정을 찾지 못했습니다.")
                return

            try:
                w = create_worker_from_site_config(site_conf)
                w.log_signal.connect(self.add_log)
                w.show_countdown_signal.connect(self.show_countdown_popup)
                w.progress_signal.connect(self.set_progress)
                w.msg_signal.connect(self.show_message)
                w.progress_end_signal.connect(self.stop)
                self.on_demand_worker = cast(OnDemandWorkerProto, w)
            except Exception as e:
                self.add_log(f"[오류] 워커 생성 실패: {str(e)}")
                return


    # 화면 업데이트
    def ui_set(self) -> None:
        if self.layout():
            if self.header_label is not None:
                self.header_label.setText(f"{self.name}")

            if self.site_list_button is not None:
                self.site_list_button.setStyleSheet(main_style(self.color))
            if self.log_reset_button is not None:
                self.log_reset_button.setStyleSheet(main_style(self.color))
            if self.collect_button is not None:
                self.collect_button.setStyleSheet(main_style(self.color))
            if self.user_info_button is not None:
                self.user_info_button.setStyleSheet(main_style(self.color))
            if self.log_out_button is not None:
                self.log_out_button.setStyleSheet(main_style(self.color))

            if self.bottom_left_button is not None:
                self.bottom_left_button.setStyleSheet(main_style(self.color))
            if self.bottom_right_button is not None:
                self.bottom_right_button.setStyleSheet(main_style(self.color))

            self._clear_right_buttons()

            if self.right_button_layout is None:
                return

            if self.setting:
                self.setting_button = create_common_button("기본설정", self.open_setting, self.color, 100)
                self.right_button_layout.addWidget(self.setting_button)

            if self.setting_detail:
                self.detail_setting_button = create_common_button("상세세팅", self.open_detail_setting, self.color, 100)
                self.right_button_layout.addWidget(self.detail_setting_button)

            if self.setting_detail_all_style_flag:
                self.detail_all_style_setting_button = create_common_button("상세세팅", self.open_detail_all_style_setting, self.color, 100)
                self.right_button_layout.addWidget(self.detail_all_style_setting_button)

            if self.setting_region_filter_favorite_flag:
                self.region_filter_favorite_setting_button = create_common_button("전체세팅", self.open_region_filter_favorite_setting, self.color, 100)
                self.right_button_layout.addWidget(self.region_filter_favorite_setting_button)

            if self.columns:
                self.column_setting_button = create_common_button("출력항목", self.open_column_setting, self.color, 100)
                self.right_button_layout.addWidget(self.column_setting_button)

            if self.sites:
                self.site_setting_button = create_common_button("사이트세팅", self.open_site_setting, self.color, 100)
                self.right_button_layout.addWidget(self.site_setting_button)

            if self.region:
                self.region_setting_button = create_common_button("지역설정", self.open_region_setting, self.color, 100)
                self.right_button_layout.addWidget(self.region_setting_button)

            if self.popup:
                self.excel_setting_button = create_common_button("엑셀세팅", self.open_excel_setting, self.color, 100)
                self.right_button_layout.addWidget(self.excel_setting_button)

        else:
            self.set_layout()

    # ─────────────────────────────────────────────────────────
    # 기존 오른쪽 버튼들 제거 유틸
    # ─────────────────────────────────────────────────────────
    def _clear_right_buttons(self) -> None:
        if self.right_button_layout is None:
            return
        while self.right_button_layout.count():
            item = self.right_button_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.setting_button = None
        self.column_setting_button = None
        self.site_setting_button = None
        self.region_setting_button = None
        self.excel_setting_button = None
        self.detail_setting_button = None

    # ui 속성 변경
    def update_style_prop(self, item_name: str, prop: str, value: str) -> None:
        widget = getattr(self, item_name, None)
        if widget is None:
            raise AttributeError(f"No widget found with name '{item_name}'")

        current_stylesheet = widget.styleSheet()
        new_stylesheet = f"{current_stylesheet}{prop}: {value};"
        widget.setStyleSheet(new_stylesheet)

    # 프로그램 일시 중지 (동일한 아이디로 로그인시)
    def handle_api_failure(self, error_message: str) -> None:
        if self.collect_button is not None:
            self.collect_button.setStyleSheet(main_style(self.color))
            self.collect_button.repaint()

        if self.log_window is not None:
            self.log_window.setStyleSheet(LOG_STYLE)
            self.log_window.repaint()

        self.cleanup_for_switch()

        self.add_log(f"동시사용자 접속으로 프로그램을 종료하겠습니다... {error_message}")
        self.show_message(
            "동시 사용자 접속이 감지되었습니다.\n다시 로그인 해주세요.",
            "warn",
            None
        )

        self.hide()

        QTimer.singleShot(0, self.app_manager.go_to_login)

        QTimer.singleShot(0, self.deleteLater)


    # 레이아웃 설정
    def set_layout(self) -> None:
        self.setWindowTitle("메인 화면")

        icon_pixmap = QPixmap(32, 32)
        icon_pixmap.fill(QColor("transparent"))
        painter = QPainter(icon_pixmap)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#e0e0e0"))
        painter.drawRect(0, 0, 32, 32)
        painter.end()
        self.setWindowIcon(QIcon(icon_pixmap))

        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet("QWidget{background:#fff;color:#111;} QLabel{color:#111;} QTextEdit{background:#fff;color:#111;}")

        main_layout = QVBoxLayout()

        header_layout = QHBoxLayout()

        self.left_button_layout = QHBoxLayout()
        self.left_button_layout.setAlignment(Qt.AlignLeft)

        self.site_list_button = create_common_button("목록", self.go_site_list, self.color, 100)
        self.log_reset_button = create_common_button("로그리셋", self.log_reset, self.color, 100)
        self.collect_button = create_common_button("시작", self.start_on_demand_worker, self.color, 100)
        self.user_info_button = create_common_button("유저정보", self.open_user_info, self.color, 100)
        self.log_out_button = create_common_button("로그아웃", self.on_log_out, self.color, 100)

        self.left_button_layout.addWidget(self.site_list_button)
        self.left_button_layout.addWidget(self.log_reset_button)
        self.left_button_layout.addWidget(self.collect_button)
        self.left_button_layout.addWidget(self.user_info_button)
        self.left_button_layout.addWidget(self.log_out_button)

        self.right_button_layout = QHBoxLayout()
        self.right_button_layout.setAlignment(Qt.AlignRight)

        if self.setting:
            self.setting_button = create_common_button("기본설정", self.open_setting, self.color, 100)
            self.right_button_layout.addWidget(self.setting_button)

        if self.setting_detail:
            self.detail_setting_button = create_common_button("상세세팅", self.open_detail_setting, self.color, 100)
            self.right_button_layout.addWidget(self.detail_setting_button)

        if self.setting_detail_all_style_flag:
            self.detail_all_style_setting_button = create_common_button("상세세팅", self.open_detail_all_style_setting, self.color, 100)
            self.right_button_layout.addWidget(self.detail_all_style_setting_button)

        if self.setting_region_filter_favorite_flag:
            self.region_filter_favorite_setting_button = create_common_button("전체세팅", self.open_region_filter_favorite_setting, self.color, 100)
            self.right_button_layout.addWidget(self.region_filter_favorite_setting_button)

        if self.columns:
            self.column_setting_button = create_common_button("출력항목", self.open_column_setting, self.color, 100)
            self.right_button_layout.addWidget(self.column_setting_button)

        if self.sites:
            self.site_setting_button = create_common_button("사이트세팅", self.open_site_setting, self.color, 100)
            self.right_button_layout.addWidget(self.site_setting_button)

        if self.region:
            self.region_setting_button = create_common_button("지역설정", self.open_region_setting, self.color, 100)
            self.right_button_layout.addWidget(self.region_setting_button)

        if self.popup:
            self.excel_setting_button = create_common_button("엑셀세팅", self.open_excel_setting, self.color, 100)
            self.right_button_layout.addWidget(self.excel_setting_button)

        header_layout.addLayout(self.left_button_layout)
        header_layout.addStretch()
        header_layout.addLayout(self.right_button_layout)

        self.header_label = QLabel(f"{self.name} 데이터 추출")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet(HEADER_TEXT_STYLE)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1000000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #f5f5f5;
                color: #111111;
                border: 2px solid #ccc;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                margin: 0px;
            }
        """)

        self.log_window = QPlainTextEdit(self)

        self.log_window.setObjectName("log_window")

        self.log_window.setReadOnly(True)
        self.log_window.document().setMaximumBlockCount(2000)

        self.log_window.setStyleSheet(f"""
        QPlainTextEdit#log_window {{
            {LOG_STYLE}
        }}
        
        QPlainTextEdit#log_window QScrollBar:vertical {{
            width: 8px;
        }}
        QPlainTextEdit#log_window QScrollBar:horizontal {{
            height: 8px;
        }}
        
        QPlainTextEdit#log_window QScrollBar::handle:vertical {{
            min-height: 20px;
            background: rgba(120, 120, 120, 160);
            border-radius: 4px;
        }}
        QPlainTextEdit#log_window QScrollBar::handle:horizontal {{
            min-width: 20px;
            background: rgba(120, 120, 120, 160);
            border-radius: 4px;
        }}
        
        QPlainTextEdit#log_window QScrollBar::add-line,
        QPlainTextEdit#log_window QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
        }}
        """)

        self.log_window.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_window.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.log_window.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)

        # 프로그램 정보 버튼과 배지를 하나의 wrapper 안에 겹쳐 배치한다.
        # 배지는 버튼의 우측 상단 모서리에 절반 정도 걸치도록 위치시킨다.
        self.program_info_wrap = QWidget()
        self.program_info_wrap.setFixedSize(152, 62)
        self.program_info_wrap.setStyleSheet("background: transparent;")

        self.bottom_left_button = create_common_button(
            "프로그램 정보",
            self.open_program_info,
            self.color,
            140,
        )
        self.bottom_left_button.setParent(self.program_info_wrap)
        self.bottom_left_button.move(0, 11)

        # 숫자는 전체 공지 수가 아니라 '아직 읽지 않은 공지 수'다.
        self.program_notice_badge = QLabel(self.program_info_wrap)
        self.program_notice_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.program_notice_badge.setFixedSize(22, 22)
        self.program_notice_badge.setStyleSheet(
            """
            QLabel {
                background-color: #e53935;
                color: white;
                border: 2px solid white;
                border-radius: 11px;
        
                padding-top: 0px;
                padding-bottom: 2px;
        
                font-size: 11px;
                font-weight: bold;
            }
            """
        )
        # 140px 버튼의 우측 상단 모서리에 약 50% 걸치게 둔다.
        self.program_notice_badge.move(129, 0)
        self.program_notice_badge.hide()
        self.program_notice_badge.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self.bottom_center_wrap = QWidget()
        self.bottom_center_wrap.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 12px;
            }
            QLabel {
                border: none;
                background: transparent;
                color: #111111;
            }
        """)

        bottom_center_layout = QHBoxLayout(self.bottom_center_wrap)
        bottom_center_layout.setContentsMargins(18, 10, 18, 10)
        bottom_center_layout.setSpacing(14)
        bottom_center_layout.setAlignment(Qt.AlignCenter)

        self.bottom_logo_label = QLabel()
        self.bottom_logo_label.setFixedSize(64, 64)
        self.bottom_logo_label.setAlignment(Qt.AlignCenter)
        self.set_bottom_logo()

        bottom_text_layout = QVBoxLayout()
        bottom_text_layout.setSpacing(2)
        bottom_text_layout.setAlignment(Qt.AlignCenter)

        self.bottom_title_label = QLabel("프로그램 개발 · 수정 문의")
        self.bottom_title_label.setAlignment(Qt.AlignCenter)
        self.bottom_title_label.setStyleSheet("""
            font-size: 15px;
            font-weight: 700;
            color: #111111;
        """)

        self.bottom_url_label = QLabel(
            f'<a href="{server_url}" style="color:#1a73e8; text-decoration:none;">{server_url}</a>'
        )
        self.bottom_url_label.setAlignment(Qt.AlignCenter)
        self.bottom_url_label.setOpenExternalLinks(True)
        self.bottom_url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.bottom_url_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 500;
            color: #1a73e8;
        """)

        bottom_text_layout.addWidget(self.bottom_title_label, 0, Qt.AlignCenter)
        bottom_text_layout.addWidget(self.bottom_url_label, 0, Qt.AlignCenter)

        bottom_center_layout.addStretch()
        bottom_center_layout.addWidget(self.bottom_logo_label, 0, Qt.AlignCenter)
        bottom_center_layout.addLayout(bottom_text_layout, 0)
        bottom_center_layout.addStretch()

        self.bottom_right_button = create_common_button("DB 목록", self.open_db_info, self.color, 120)

        bottom_layout.addWidget(self.program_info_wrap, 0, Qt.AlignVCenter)
        bottom_layout.addWidget(self.bottom_center_wrap, 1)
        bottom_layout.addWidget(self.bottom_right_button, 0)

        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.header_label)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.log_window, stretch=2)
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)
        self.center_window()




    def set_bottom_logo(self) -> None:
        if self.bottom_logo_label is None:
            return

        base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        logo_candidates = [
            base_path / "resources" / "icons" / "crawling.ico",
            Path.cwd() / "resources" / "icons" / "crawling.ico",
            Path(sys.executable).resolve().parent / "resources" / "icons" / "crawling.ico",
            Path(sys.executable).resolve().parent / "_internal" / "resources" / "icons" / "crawling.ico",
            ]

        logo_pixmap = QPixmap()

        for logo_path in logo_candidates:
            if logo_path.exists():
                logo_pixmap = QPixmap(str(logo_path))
                if not logo_pixmap.isNull():
                    break

        if not logo_pixmap.isNull():
            scaled = logo_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.bottom_logo_label.setPixmap(scaled)
            self.bottom_logo_label.setText("")
        else:
            self.bottom_logo_label.setPixmap(QPixmap())
            self.bottom_logo_label.setText("GB7")
            self.bottom_logo_label.setStyleSheet("""
                font-size: 22px;
                font-weight: 800;
                color: #111111;
            """)

    # 로그
    def add_log(self, message: Any) -> None:
        self.ensure_file_logger()

        if self.file_logger is not None:
            log_message = self.file_logger.log(message)
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] {message}"

        if self.log_window is None:
            return

        self.log_window.appendPlainText(log_message)

    # 프로그램 시작 중지
    def start_on_demand_worker(self) -> None:
        if self.collect_button is None:
            return

        if self.collect_button.text() == "시작":
            self.collect_button.setText("중지")
            self.collect_button.setStyleSheet(main_style(self.color))
            self.collect_button.repaint()

            if self.on_demand_worker is None or self.progress_worker is None:
                self.main_worker_set()

            if self.progress_bar is not None:
                self.progress_bar.setValue(0)

            if self.progress_worker is not None:
                self.progress_worker.start()

            if self.on_demand_worker is None:
                self.add_log("[오류] on_demand_worker 생성 실패")
                self.collect_button.setText("시작")
                return

            if self.setting:
                self.on_demand_worker.set_setting(self.setting)

            if self.setting_detail:
                self.on_demand_worker.set_setting_detail(self.setting_detail)

            if self.setting_detail_all_style_flag:
                self.on_demand_worker.set_setting_detail_all_style(self.setting_detail_all_style)

            if self.setting_region_filter_favorite_flag:
                self.on_demand_worker.set_setting_detail_all_style(self.setting_detail_all_style)
                self.on_demand_worker.set_setting_region_filter_favorite(self.setting_region_filter_favorite)

            if self.columns:
                self.on_demand_worker.set_columns(self.columns)

            if self.sites:
                self.on_demand_worker.set_sites(self.sites)

            if self.selected_regions:
                self.on_demand_worker.set_region(self.selected_regions)

            if self.excel_data_list:
                self.on_demand_worker.set_excel_data_list(self.excel_data_list)

            if self.user:
                self.on_demand_worker.set_user(self.user)

            if self.session:
                self.on_demand_worker.set_session(self.session)

            self.on_demand_worker.start()

        else:
            self.add_log("중지")
            self.stop()


    # 프로그램 중지
    def stop(self, *, show_popup: bool = True, reason: Optional[str] = None) -> None:
        # 워커 정상 종료(destroy) / 사용자 중지 시 DB 팝업과 동일한 작업중 모달 표시
        working_popup = ProcessingDialog(
            self,
            "⏳ 작업중입니다.\n잠시만 기다려주세요."
        )
        working_popup.show()
        QApplication.processEvents()

        try:
            ok = self.cleanup_for_nav()
        finally:
            working_popup.hide()
            working_popup.deleteLater()
            QApplication.processEvents()

        if ok and self.collect_button:
            self.collect_button.setText("시작")
            self.collect_button.repaint()

        if not ok:
            self.add_log("⚠️ 정리 중입니다. 3초 후 다시 시도해주세요.")

        if show_popup:
            if ok:
                msg_text = reason or "크롤링이 종료되었습니다."
                QTimer.singleShot(100, lambda: self.show_message(msg_text, "info", None))
            else:
                QTimer.singleShot(100, lambda: self.show_message(
                    "정리 작업이 아직 진행 중입니다.\n3초 후 다시 시도해주세요.",
                    "warn",
                    None
                ))


    # 프로그래스 큐 데이터 담기
    def set_progress(self, start_value: int, end_value: int) -> None:
        if self.task_queue:
            self.task_queue.put((start_value, end_value))

    # 프로그래스 UI 업데이트
    def update_progress(self, value: int) -> None:
        if self.progress_bar is not None:
            self.progress_bar.setValue(value)

    # 화면 중앙
    def center_window(self) -> None:
        if not self.screen():
            return

        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.frameGeometry()

        window_geometry.moveCenter(screen_geometry.center())
        self.move(window_geometry.topLeft())

    # 경고 alert창
    def show_message(self, message: str, type: str, event: Optional[Any]) -> None:
        try:
            msg = QMessageBox(self)
            msg.setStyleSheet("QMessageBox{background:#fff;color:#111;} QLabel{color:#111;}")
            if type == "warn":
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("경고")
            elif type == "info":
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("확인")

            msg.setText(message)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

            if event:
                event.set()
        except Exception as e:
            self.add_log(f"⚠️ 메시지 박스 오류 발생: {e}")
            if event:
                event.set()

    # 로그 리셋
    def log_reset(self) -> None:
        if self.log_window is not None:
            self.log_window.clear()

    # 사이트 이동
    def go_site_list(self) -> None:
        try:
            self.hide()
        except Exception:
            pass

        self.cleanup_for_nav()

        try:
            if self.file_logger is not None:
                self.file_logger.close()
        except Exception:
            pass
        self.file_logger = None

        QTimer.singleShot(0, self.app_manager.go_to_select)

        QTimer.singleShot(0, self.deleteLater)

    # 로그아웃
    def on_log_out(self) -> None:
        try:
            self.stop(show_popup=False)
        except Exception:
            pass

        try:
            if self.api_worker is not None:
                self.api_worker.stop()
                self.api_worker.wait(3000)
                self.api_worker = None
        except Exception:
            pass

        try:
            keyring.delete_password(server_name, "username")
            keyring.delete_password(server_name, "password")
        except Exception:
            pass

        st = GlobalState()
        session = cast(Optional[Session], st.get("session"))

        try:
            self.hide()
        except Exception:
            pass

        if session is None:
            self.cleanup_for_switch()
            QTimer.singleShot(0, self.app_manager.go_to_login)
            QTimer.singleShot(0, self.deleteLater)
            return

        self.logout_worker = LogoutWorker(session)
        self.logout_worker.logout_success.connect(self._on_logout)
        self.logout_worker.logout_failed.connect(self._on_logout)
        self.logout_worker.start()


    def _on_logout(self, msg: str) -> None:
        self.cleanup_for_switch()

        self._switch_to_login()


    def _switch_to_login(self) -> None:
        try:
            self.hide()
        except Exception:
            pass

        QTimer.singleShot(0, self.app_manager.go_to_login)

        QTimer.singleShot(0, self.deleteLater)

    def open_user_info(self) -> None:
        pop = UserInfoPop(self)
        pop.exec()

    def get_program_info_program_id(self) -> str:
        """프로그램 정보 API에서 사용할 PROGRAM_ID를 반환한다."""
        return str(self.site or "").strip()

    def get_program_notice_read_store(self) -> Optional[ProgramNoticeReadStore]:
        """현재 프로그램의 notice_read.json 저장소를 한 번만 생성한다."""
        site = str(self.site or "").strip()
        if not site:
            return None

        if self.program_notice_read_store is None:
            self.program_notice_read_store = ProgramNoticeReadStore(site=site)

        return self.program_notice_read_store

    def preload_program_notices(self) -> None:
        """
        MainWindow 시작 시 공지 전체를 미리 조회한다.

        이 결과를 메모리에 보관하고 프로그램 정보 팝업에 그대로 넘긴다.
        """
        program_id = self.get_program_info_program_id()
        if not program_id:
            self.program_notices = []
            self.program_notices_loaded = True
            self.update_program_notice_badge()
            return

        if (
                self.program_notice_worker is not None
                and self.program_notice_worker.isRunning()
        ):
            return

        self.program_notices_loaded = False

        worker = ProgramNoticeWorker(
            server_url=server_url,
            program_id=program_id,
            parent=self,
        )
        self.program_notice_worker = worker
        worker.sig_done.connect(self.on_program_notices_loaded)
        worker.finished.connect(self.on_program_notice_worker_finished)
        worker.start()

    def on_program_notices_loaded(
            self,
            result: ProgramNoticeListResult,
    ) -> None:
        """공지 선조회 결과를 저장하고 미확인 배지를 갱신한다."""
        self.program_notices_loaded = True

        if not result.ok:
            self.program_notices = []
            self.update_program_notice_badge()
            self.add_log(
                "[공지사항] 공지 조회 실패: "
                f"{result.message}"
            )

            # 사용자가 매우 빨리 팝업을 연 경우에도 로딩 상태를 끝낸다.
            if self.program_info_pop is not None:
                self.program_info_pop.set_notices([], loaded=True)
            return

        self.program_notices = list(result.notices)
        self.update_program_notice_badge()

        # 메인 조회가 끝나기 전에 사용자가 팝업을 열었을 때도 즉시 반영한다.
        if self.program_info_pop is not None:
            self.program_info_pop.set_notices(
                self.program_notices,
                loaded=True,
            )

    def on_program_notice_worker_finished(self) -> None:
        self.program_notice_worker = None

    def update_program_notice_badge(self) -> None:
        """로컬 읽음 캐시와 비교해 미확인 공지 수만 빨간 배지로 표시한다."""
        if self.program_notice_badge is None:
            return

        store = self.get_program_notice_read_store()
        if store is None:
            self.program_notice_badge.hide()
            return

        unread_count = store.get_unread_count(self.program_notices)

        if unread_count <= 0:
            self.program_notice_badge.hide()
            return

        if unread_count > 99:
            text = "99+"
            badge_width = 28
            badge_x = 126
        else:
            text = str(unread_count)
            badge_width = 22
            badge_x = 129

        self.program_notice_badge.setText(text)
        self.program_notice_badge.setFixedSize(badge_width, 22)
        self.program_notice_badge.move(badge_x, 0)
        self.program_notice_badge.show()
        self.program_notice_badge.raise_()

    def on_program_notice_read(self, _notice_id: str) -> None:
        """상세 팝업에서 공지를 읽는 즉시 MainWindow 숫자를 다시 계산한다."""
        self.update_program_notice_badge()

    def open_program_info(self) -> None:
        """프로그램 정보 팝업을 열고 선조회한 공지를 즉시 전달한다."""
        program_id = self.get_program_info_program_id()

        if not program_id:
            self.show_message(
                "프로그램 정보를 확인할 수 없습니다.",
                "warn",
                None,
            )
            return

        try:
            if self.program_info_pop is not None:
                self.program_info_pop.close()
                self.program_info_pop.deleteLater()
        except Exception:
            pass

        self.program_info_pop = None

        store = self.get_program_notice_read_store()
        if store is None:
            return

        pop = ProgramInfoPop(
            parent=self,
            server_url=server_url,
            program_id=program_id,
            site=str(self.site or ""),
            notices=self.program_notices,
            read_store=store,
            color=self.color,
            notice_loaded=self.program_notices_loaded,
        )
        pop.notice_read.connect(self.on_program_notice_read)
        self.program_info_pop = pop
        pop.exec()

        # 상세에서 읽은 상태가 반영되어 있으므로 서버 재호출 없이 로컬 계산만 한다.
        self.update_program_notice_badge()

    def open_db_info(self) -> None:
        # DB 팝업은 열 때마다 새로 생성한다.
        # DbSetPop 내부에서 현재 site의 config.json을 읽고
        # db_tabs가 있으면 동적 탭, 없으면 기존 단일 상세목록으로 표시한다.
        try:
            if self.db_set_pop is not None:
                self.db_set_pop.close()
                self.db_set_pop.deleteLater()
        except Exception:
            pass

        self.db_set_pop = None

        pop = DbSetPop(parent=self, title="DB목록")
        pop.log_signal.connect(self.add_log)
        self.db_set_pop = pop
        pop.exec()

    def open_my_site(self) -> None:
        QDesktopServices.openUrl(QUrl(server_url))

    # 세팅 버튼
    def open_setting(self) -> None:
        if self.param_set_pop is None:
            self.param_set_pop = ParamSetPop(self)
            self.param_set_pop.log_signal.connect(self.add_log)
        self.param_set_pop.exec()

    def open_detail_setting(self) -> None:
        if self.detail_set_pop is None:
            self.detail_set_pop = DetailSetPop(self)
        self.detail_set_pop.exec()

    def open_detail_all_style_setting(self) -> None:
        if self.detail_all_style_set_pop is None:
            self.detail_all_style_set_pop = DetailAllStyleSetPop(self)
        self.detail_all_style_set_pop.exec()


    def on_confirm(self, regions, filters, favorites):
        self.selected_regions = regions
        self.setting_detail_all_style = filters
        self.setting_region_filter_favorite = favorites
        self.add_log(f"변경사항이 저장되었습니다.")

    def open_region_filter_favorite_setting(self) -> None:

        if self.region_filter_favorite_set_pop is None:
            self.region_filter_favorite_set_pop = RegionFilterFavoriteSetPop(
                parent=self,
                selected_regions=getattr(self, "selected_regions", []),
                setting_attr_name="setting_detail_all_style",
                favorite_attr_name="setting_region_filter_favorite",
            )
            self.region_filter_favorite_set_pop.confirm_signal.connect(self.on_confirm)

        self.region_filter_favorite_set_pop.exec()

    def open_column_setting(self) -> None:
        try:
            if self.column_set_pop is not None:
                self.column_set_pop.close()
                self.column_set_pop.deleteLater()
        except Exception:
            pass
        self.column_set_pop = None

        self.column_set_pop = ColumnSetPop(self)
        self.column_set_pop.log_signal.connect(self.add_log)
        self.column_set_pop.exec()

    def open_site_setting(self) -> None:
        if self.site_set_pop is None:
            self.site_set_pop = SiteSetPop(self)
            self.site_set_pop.log_signal.connect(self.add_log)
        self.site_set_pop.exec()

    def open_region_setting(self) -> None:
        if self.region_set_pop is None:
            self.region_set_pop = RegionSetPop(parent=self)
            self.region_set_pop.log_signal.connect(self.add_log)
            self.region_set_pop.confirm_signal.connect(self.save_selected_regions)
        self.region_set_pop.exec()

    def save_selected_regions(self, selected: List[Any]) -> None:
        self.selected_regions = selected
        self.add_log(f"{len(selected)}개 지역이 선택되었습니다.")

    # 카운트 다운 팝업
    def show_countdown_popup(self, seconds: int) -> None:
        popup = CountdownPop(seconds)
        popup.exec()

    # 전체 등록 팝업
    def open_excel_setting(self) -> None:
        self.excel_set_pop = ExcelSetPop(parent=self)
        self.excel_set_pop.updateList.connect(self.excel_data_set_list)
        self.excel_set_pop.updateUser.connect(self.update_user)
        self.excel_set_pop.exec()

    # url list 업데이트
    def excel_data_set_list(self, excel_data_list: List[Any]) -> None:
        self.excel_data_list = excel_data_list
        total = len(self.excel_data_list)
        self.add_log(f"엑셀 데이터 갯수 : {total}")

        preview_count = min(10, total)
        for i, data in enumerate(excel_data_list[:preview_count], start=1):
            self.add_log(f"[미리보기 {i}/{preview_count}] {data}")

        if total > preview_count:
            self.add_log(f"... 외 {total - preview_count}건 생략")

    def update_user(self, user: Any) -> None:
        self.user = user
        self.add_log(f"유저 : {self.user}")


    def cleanup_for_nav(self) -> bool:
        self.add_log("정리 중입니다. 최대 10초까지 소요될 수 있습니다. 잠시만 기다려주세요.")

        try:
            if self.on_demand_worker is not None:
                self.on_demand_worker.stop()
                self.on_demand_worker.quit()

                ok = self.on_demand_worker.wait(3000)
                if not ok:
                    self.add_log("[경고] on_demand_worker가 아직 종료되지 않았습니다. (wait timeout)")
                    return False

                self.on_demand_worker = None
        except Exception as e:
            self.add_log(f"[오류] on_demand_worker 정리 실패: {e}")
            return False

        try:
            if self.progress_worker is not None:
                self.progress_worker.stop()
                self.progress_worker.quit()

                ok = self.progress_worker.wait(3000)
                if not ok:
                    self.add_log("[경고] progress_worker가 아직 종료되지 않았습니다. (wait timeout)")
                    return False

                self.progress_worker = None
                self.task_queue = None
        except Exception as e:
            self.add_log(f"[오류] progress_worker 정리 실패: {e}")
            return False

        return True



    def cleanup_for_switch(self) -> None:

        self.cleanup_for_nav()

        try:
            if self.api_worker is not None:
                self.api_worker.stop()
                self.api_worker.wait(3000)
                self.api_worker = None
        except Exception:
            pass

        try:
            if self.session is not None:
                try:
                    self.session.cookies.clear()
                except Exception:
                    pass

            st = GlobalState()
            st.set("session", None)
            self.session = None
        except Exception:
            pass

        try:
            if self.logout_worker is not None:
                self.logout_worker.quit()
                self.logout_worker.wait(2000)
        except Exception:
            pass
        self.logout_worker = None

        try:
            if self.file_logger is not None:
                self.file_logger.close()
        except Exception:
            pass
        self.file_logger = None




    def closeEvent(self, event: QCloseEvent) -> None:
        if self._force_close:
            event.accept()
            return

        if self._closing:
            event.ignore()
            return

        self._closing = True
        event.ignore()

        self._closing_pop = ClosingPop(self)
        self._closing_pop.show()

        QTimer.singleShot(self._close_timeout_ms, self._force_quit)

        self._cleanup_worker = CleanupWorker(
            api_worker=self.api_worker,
            on_demand_worker=self.on_demand_worker,
            progress_worker=self.progress_worker,
            session=self.session,
        )
        self._cleanup_worker.done.connect(self._on_cleanup_done)
        self._cleanup_worker.start()

    def _on_cleanup_done(self, ok: bool, msg: str) -> None:
        try:
            self.api_worker = None
            self.on_demand_worker = None
            self.progress_worker = None
            self.task_queue = None
            self.session = None

            if self._closing_pop is not None:
                self._closing_pop.set_done(ok)

            QTimer.singleShot(2000, self._force_quit)
        except Exception:
            QTimer.singleShot(2000, self._force_quit)


    def _force_quit(self) -> None:
        if self._force_close:
            return

        self._force_close = True

        try:
            if self.file_logger is not None:
                self.file_logger.close()
        except Exception:
            pass
        self.file_logger = None

        try:
            if self._closing_pop is not None:
                self._closing_pop.close()
                self._closing_pop = None
        except Exception:
            pass

        try:
            self.close()
        except Exception:
            pass

        try:
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            try:
                self.hide()
            except Exception:
                pass