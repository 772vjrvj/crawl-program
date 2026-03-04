# src/ui/main_window.py
from __future__ import annotations  # === 신규 ===

from datetime import datetime
from queue import Queue
from typing import Optional, Any, List, Tuple, Protocol, cast

import keyring
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCloseEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
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
from src.ui.popup.param_set_pop import ParamSetPop
from src.ui.popup.region_set_pop import RegionSetPop
from src.ui.popup.site_set_pop import SiteSetPop
from src.ui.popup.closing_pop import ClosingPop
from src.ui.style.style import create_common_button, main_style, LOG_STYLE, HEADER_TEXT_STYLE


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
    def wait(self) -> None: ...
    # 시그널은 런타임 객체라 타입을 강하게 못 박기 어렵습니다.
    # === 신규 === 최소한 connect 가능하다는 전제로 Any 처리
    api_failure: Any
    log_signal: Any


class ProgressWorkerProto(StoppableThreadProto, Protocol):
    progress_signal: Any
    log_signal: Any


class OnDemandWorkerProto(StoppableThreadProto, Protocol):
    log_signal: Any
    show_countdown_signal: Any
    progress_signal: Any
    msg_signal: Any
    progress_end_signal: Any

    def stop(self) -> None: ...

    def set_setting(self, setting: Any) -> None: ...
    def set_setting_detail(self, setting_detail: Any) -> None: ...
    def set_columns(self, columns: Any) -> None: ...
    def set_sites(self, sites: Any) -> None: ...
    def set_region(self, regions: List[Any]) -> None: ...
    def set_excel_data_list(self, excel_data_list: List[Any]) -> None: ...
    def set_user(self, user: Any) -> None: ...


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
        self.log_out_button: Optional[QWidget] = None

        self.setting_button: Optional[QWidget] = None
        self.detail_setting_button: Optional[QWidget] = None
        self.column_setting_button: Optional[QWidget] = None
        self.site_setting_button: Optional[QWidget] = None
        self.region_setting_button: Optional[QWidget] = None
        self.excel_setting_button: Optional[QWidget] = None

        self.progress_bar: Optional[QProgressBar] = None
        self.log_window: Optional[QTextEdit] = None
        self.logout_worker: Optional[LogoutWorker] = None

        # 팝업
        self.region_set_pop: Optional[RegionSetPop] = None
        self.column_set_pop: Optional[ColumnSetPop] = None
        self.site_set_pop: Optional[SiteSetPop] = None
        self.param_set_pop: Optional[ParamSetPop] = None
        self.excel_set_pop: Optional[ExcelSetPop] = None
        self.detail_set_pop: Optional[DetailSetPop] = None

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

    # 변경값 세팅
    def common_data_set(self) -> None:
        state = GlobalState()
        self.name = cast(Optional[str], state.get("name"))
        self.site = cast(Optional[str], state.get("site"))
        self.color = cast(Optional[str], state.get("color"))
        self.setting = state.get("setting")
        self.session = cast(Optional[Session], state.get("session"))
        self.columns = state.get("columns")
        self.sites = state.get("sites")
        self.region = state.get("region")
        self.popup = state.get("popup")
        self.setting_detail = state.get("setting_detail")   # === 신규 ===

    # 재 초기화
    def init_reset(self) -> None:
        self.common_data_set()
        self.api_worker_set()
        self.main_worker_set()
        self.ui_set()

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

            # === 신규 === site_configs에서 현재 site key config 찾기
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

            # 버튼/로그/진행바는 None 체크 후 접근
            if self.site_list_button is not None:
                self.site_list_button.setStyleSheet(main_style(self.color))
            if self.log_reset_button is not None:
                self.log_reset_button.setStyleSheet(main_style(self.color))
            if self.collect_button is not None:
                self.collect_button.setStyleSheet(main_style(self.color))
            if self.log_out_button is not None:
                self.log_out_button.setStyleSheet(main_style(self.color))

            # 🔧 기존 오른쪽 버튼 싹 제거 후 다시 구성
            self._clear_right_buttons()

            if self.right_button_layout is None:
                return

            if self.setting:
                self.setting_button = create_common_button("기본세팅", self.open_setting, self.color, 100)
                self.right_button_layout.addWidget(self.setting_button)

            if self.setting_detail:
                self.detail_setting_button = create_common_button("상세세팅", self.open_detail_setting, self.color, 100)
                self.right_button_layout.addWidget(self.detail_setting_button)

            if self.columns:
                self.column_setting_button = create_common_button("항목세팅", self.open_column_setting, self.color, 100)
                self.right_button_layout.addWidget(self.column_setting_button)

            if self.sites:
                self.site_setting_button = create_common_button("사이트세팅", self.open_site_setting, self.color, 100)
                self.right_button_layout.addWidget(self.site_setting_button)

            if self.region:
                self.region_setting_button = create_common_button("지역세팅", self.open_region_setting, self.color, 100)
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
        # 참조 리셋
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
        # UI 복구
        if self.collect_button is not None:
            self.collect_button.setStyleSheet(main_style(self.color))
            self.collect_button.repaint()

        if self.log_window is not None:
            self.log_window.setStyleSheet(LOG_STYLE)
            self.log_window.repaint()

        # ✅ 전환용 자원 정리
        self.cleanup_for_switch()

        # 로그 + 메시지
        self.add_log(f"동시사용자 접속으로 프로그램을 종료하겠습니다... {error_message}")
        self.show_message(
            "동시 사용자 접속이 감지되었습니다.\n다시 로그인 해주세요.",
            "warn",
            None
        )

        # ✅ 1) 창 숨김
        self.hide()

        # ✅ 2) 로그인 화면 전환 (이벤트 루프 한 틱 뒤 실행)
        QTimer.singleShot(0, self.app_manager.go_to_login)

        # ✅ 3) MainWindow 객체 완전 제거
        QTimer.singleShot(0, self.deleteLater)


    # 레이아웃 설정
    def set_layout(self) -> None:
        self.setWindowTitle("메인 화면")

        # 동그란 파란색 원을 그린 아이콘 생성
        icon_pixmap = QPixmap(32, 32)
        icon_pixmap.fill(QColor("transparent"))
        painter = QPainter(icon_pixmap)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#e0e0e0"))
        painter.drawRect(0, 0, 32, 32)
        painter.end()
        self.setWindowIcon(QIcon(icon_pixmap))

        # 메인화면 설졍
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet("background-color: white;")

        main_layout = QVBoxLayout()

        header_layout = QHBoxLayout()

        # 왼쪽 버튼들 레이아웃
        self.left_button_layout = QHBoxLayout()
        self.left_button_layout.setAlignment(Qt.AlignLeft)

        self.site_list_button = create_common_button("목록", self.go_site_list, self.color, 100)
        self.log_reset_button = create_common_button("로그리셋", self.log_reset, self.color, 100)
        self.collect_button = create_common_button("시작", self.start_on_demand_worker, self.color, 100)
        self.log_out_button = create_common_button("로그아웃", self.on_log_out, self.color, 100)

        self.left_button_layout.addWidget(self.site_list_button)
        self.left_button_layout.addWidget(self.log_reset_button)
        self.left_button_layout.addWidget(self.collect_button)
        self.left_button_layout.addWidget(self.log_out_button)

        # 오른쪽 버튼 레이아웃
        self.right_button_layout = QHBoxLayout()
        self.right_button_layout.setAlignment(Qt.AlignRight)

        if self.setting:
            self.setting_button = create_common_button("기본세팅", self.open_setting, self.color, 100)
            self.right_button_layout.addWidget(self.setting_button)

        if self.setting_detail:
            self.detail_setting_button = create_common_button("상세세팅", self.open_detail_setting, self.color, 100)
            self.right_button_layout.addWidget(self.detail_setting_button)

        if self.columns:
            self.column_setting_button = create_common_button("항목세팅", self.open_column_setting, self.color, 100)
            self.right_button_layout.addWidget(self.column_setting_button)

        if self.sites:
            self.site_setting_button = create_common_button("사이트세팅", self.open_site_setting, self.color, 100)
            self.right_button_layout.addWidget(self.site_setting_button)

        if self.region:
            self.region_setting_button = create_common_button("지역세팅", self.open_region_setting, self.color, 100)
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
            border: 2px solid #ccc;
            border-radius: 5px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #4caf50;
            margin: 0px;
        }
        """)

        self.log_window = QTextEdit(self)

        self.log_window.setObjectName("log_window")

        self.log_window.setReadOnly(True)

        self.log_window.setStyleSheet(f"""
        QTextEdit#log_window {{
            {LOG_STYLE}
        }}
        
        QTextEdit#log_window QScrollBar:vertical {{
            width: 8px;
        }}
        QTextEdit#log_window QScrollBar:horizontal {{
            height: 8px;
        }}
        
        QTextEdit#log_window QScrollBar::handle:vertical {{
            min-height: 20px;
            background: rgba(120, 120, 120, 160);
            border-radius: 4px;
        }}
        QTextEdit#log_window QScrollBar::handle:horizontal {{
            min-width: 20px;
            background: rgba(120, 120, 120, 160);
            border-radius: 4px;
        }}
        
        QTextEdit#log_window QScrollBar::add-line,
        QTextEdit#log_window QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
        }}
        """)

        self.log_window.setLineWrapMode(QTextEdit.NoWrap)
        self.log_window.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.log_window.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.header_label)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.log_window, stretch=2)

        self.setLayout(main_layout)
        self.center_window()

    # 로그
    def add_log(self, message: Any) -> None:
        if self.log_window is None:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.log_window.append(log_message)

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
                self.on_demand_worker.set_setting_detail(self.setting_detail)  # === 신규 ===

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

            self.on_demand_worker.start()

        else:
            self.collect_button.setText("시작")
            self.collect_button.setStyleSheet(main_style(self.color))
            self.collect_button.repaint()
            self.add_log("중지")
            self.stop()

    # 프로그램 중지
    def stop(self, *, show_popup: bool = True, reason: Optional[str] = None) -> None:
        # 1. 중복 호출 방지 및 버튼 텍스트 복구
        if self.collect_button:
            self.collect_button.setText("시작")
            self.collect_button.repaint()

        # 2. 크롤링 워커 중지 (참조 유지하며 stop만 호출)
        if self.on_demand_worker is not None:
            try:
                # 워커 내부의 destroy()가 실행되도록 유도
                self.on_demand_worker.stop()
            except Exception as e:
                self.add_log(f"워커 중지 중 오류: {e}")

        # 3. 프로그래스 워커 중지
        if self.progress_worker is not None:
            try:
                self.progress_worker.stop()
            except Exception:
                pass

        # 4. 중요: 상황별 UI 알림을 '메시지 큐'의 맨 뒤로 보냅니다 (SingleShot 사용)
        # 확인 버튼을 누를 때 발생하는 UI 스레드 충돌을 방지하기 위함입니다.
        if show_popup:
            msg_text = reason or "크롤링이 종료되었습니다."
            QTimer.singleShot(100, lambda: self.show_message(msg_text, "info", None))

        # 상황별 UI 알림 제어
        if show_popup:
            self.show_message(reason or "크롤링 종료", "info", None)

    # 프로그래스 큐 데이터 담기
    def set_progress(self, start_value: int, end_value: int) -> None:
        if self.task_queue:
            self.task_queue.put((start_value, end_value))

    # 프로그래스 UI 업데이트
    def update_progress(self, value: int) -> None:
        if self.progress_bar is not None:
            self.progress_bar.setValue(value)

    # 화면 중앙
    def center_window(self):
        if not self.screen():
            return

        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.frameGeometry()

        window_geometry.moveCenter(screen_geometry.center())
        self.move(window_geometry.topLeft())

    # 경고 alert창
    def show_message(self, message: str, type: str, event: Optional[Any]) -> None:
        """메시지 박스를 띄우고 OK 버튼이 눌리면 event.set() 호출"""
        try:
            msg = QMessageBox(self)
            if type == "warn":
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("경고")
            elif type == "info":
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("확인")

            msg.setText(message)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()  # PySide6: exec_ -> exec

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

        # 전환용 자원 정리(워커/세션 등)
        self.cleanup_for_switch()

        # 다음 화면 전환은 이벤트루프 한 틱 뒤
        QTimer.singleShot(0, self.app_manager.go_to_select)

        # 재 메인윈도우 객체 정리
        QTimer.singleShot(0, self.deleteLater)

    # 로그아웃
    def on_log_out(self) -> None:
        # 0) 실행 중 작업/스레드 정리
        try:
            self.stop(show_popup=False)
        except Exception:
            pass

        # 1) 로그인 체크 워커 중단
        try:
            if self.api_worker is not None:
                self.api_worker.stop()
                self.api_worker.wait(3000)
                self.api_worker = None
        except Exception:
            pass

        # 2) 자동 로그인 정보 삭제
        try:
            keyring.delete_password(server_name, "username")
            keyring.delete_password(server_name, "password")
        except Exception:
            pass

        # 3) 세션 가져오기
        st = GlobalState()
        session = cast(Optional[Session], st.get("session"))

        # ✅ 4) 화면 먼저 숨김 (close 금지)
        try:
            self.hide()
        except Exception:
            pass

        # 세션이 없으면 바로 전환
        if session is None:
            self.cleanup_for_switch()
            QTimer.singleShot(0, self.app_manager.go_to_login)
            QTimer.singleShot(0, self.deleteLater)
            return

        # 5) 서버 로그아웃 요청
        self.logout_worker = LogoutWorker(session)
        self.logout_worker.logout_success.connect(self._on_logout_success)
        self.logout_worker.logout_failed.connect(self._on_logout_failed)
        self.logout_worker.start()


    def _on_logout_success(self, msg: str) -> None:
        # ✅ 전환용 자원 정리(워커/세션 등)
        self.cleanup_for_switch()

        # ✅ 로그인 화면으로 전환
        self._switch_to_login()


    def _on_logout_failed(self, msg: str) -> None:
        # ✅ 전환용 자원 정리(워커/세션 등)
        self.cleanup_for_switch()

        # ✅ 로그인 화면으로 전환
        self._switch_to_login()


    def _switch_to_login(self) -> None:
        # === 신규 === 메인 -> 로그인 전환 공통 처리
        try:
            self.hide()
        except Exception:
            pass

        # UI 전환 안정화
        QTimer.singleShot(0, self.app_manager.go_to_login)

        # 메인윈도우 객체 정리
        QTimer.singleShot(0, self.deleteLater)

    # 세팅 버튼
    def open_setting(self) -> None:
        if self.param_set_pop is None:
            self.param_set_pop = ParamSetPop(self)
            self.param_set_pop.log_signal.connect(self.add_log)
        self.param_set_pop.exec()  # PySide6

    def open_detail_setting(self) -> None:
        if self.detail_set_pop is None:
            self.detail_set_pop = DetailSetPop(self)
            self.detail_set_pop.log_signal.connect(self.add_log)
        self.detail_set_pop.exec()

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
        self.add_log(f"엑셀 데이터 갯수 : {len(self.excel_data_list)}")
        for data in excel_data_list:
            self.add_log(data)

    def update_user(self, user: Any) -> None:
        self.user = user
        self.add_log(f"유저 : {self.user}")


    def cleanup_for_switch(self) -> None:
        # 1) 크롤링 워커 정지 및 대기
        try:
            if self.on_demand_worker is not None:
                self.on_demand_worker.stop()
                # 빌드 환경에서는 워커가 죽을 시간을 조금 주는 게 좋습니다.
                # self.on_demand_worker.wait(2000)
                self.on_demand_worker = None
        except Exception:
            pass

        # 2) 프로그래스 워커 정지
        try:
            if self.progress_worker is not None:
                self.progress_worker.stop()
                self.progress_worker = None
                self.task_queue = None
        except Exception:
            pass

        # 3) 로그인 체크 워커 정지
        try:
            if self.api_worker is not None:
                self.api_worker.stop()
                self.api_worker.wait(3000)
                self.api_worker = None
        except Exception:
            pass

        # 4) 세션 정리
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

        # 5) LogoutWorker 정리 (여기에 추가)
        try:
            if self.logout_worker is not None:
                self.logout_worker.quit()
                self.logout_worker.wait(2000)
        except Exception:
            pass
        self.logout_worker = None



    def closeEvent(self, event: QCloseEvent) -> None:
        # === 신규 === 우리가 강제 종료를 요청한 경우엔 닫힘 허용
        if self._force_close:
            event.accept()
            return

        # 이미 종료 시퀀스 들어갔으면 중복 방지
        if self._closing:
            event.ignore()
            return

        self._closing = True
        event.ignore()  # ✅ 일단 종료 막고, 정리 끝나면 우리가 종료시킴

        # 1) 종료 팝업 표시
        self._closing_pop = ClosingPop(self)
        self._closing_pop.show()

        # === 신규 === 타임아웃 걸어두기 (CleanupWorker가 멈추면 여기서라도 종료)
        QTimer.singleShot(self._close_timeout_ms, self._force_quit)

        # 2) 정리 워커 시작 (UI 멈춤 방지)
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
            # 내부 참조도 정리
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
        # 이미 종료 진행 중인데 또 호출되는 케이스 방지(타임아웃/정상완료 둘 다 호출될 수 있음)
        if self._force_close:
            return

        self._force_close = True  # === 신규 === 이제부터는 close를 허용

        try:
            if self._closing_pop is not None:
                self._closing_pop.close()
                self._closing_pop = None
        except Exception:
            pass

        # === 신규 === 1) 윈도우 먼저 닫기 시도 (closeEvent가 accept로 통과됨)
        try:
            self.close()
        except Exception:
            pass

        # === 신규 === 2) 앱 종료
        try:
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            try:
                self.hide()
            except Exception:
                pass