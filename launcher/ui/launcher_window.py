import platform
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
from __future__ import annotations
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QSizePolicy,
)
from launcher.core.api import NoticeInfo
from launcher.core.app_config import load_support_config
from launcher.core.notice_store import hide_for_day, is_hidden
from launcher.core.paths import LauncherPaths
from launcher.core.state import read_current_state
from launcher.ui.notice_dialog import NoticeDialog
from launcher.ui.update_confirm_dialog import (
    UpdateConfirmAction,
    UpdateConfirmDialog,
)
from launcher.ui.style.style import (
    BTN_GRAY,
    btn_style,
    msgbox_style,
)
from launcher.workers.notice_worker import (
    NoticeWorker,
    NoticeResult,
)
from launcher.workers.update_worker import (
    UpdateWorker,
    UpdateResult,
)


@dataclass(frozen=True)
class UiState:
    busy: bool
    can_run: bool
    can_retry: bool
    percent: int
    status: str



def load_launcher_version(
        app_json_path: Path,
) -> Optional[str]:
    """
    data/app.json에서 런처 버전을 읽는다.
    """
    try:
        obj = json.loads(
            app_json_path.read_text(
                encoding="utf-8"
            )
        )
    except (
            OSError,
            json.JSONDecodeError,
    ):
        return None

    launcher_version = obj.get(
        "launcher_version"
    )

    if not isinstance(
            launcher_version,
            str,
    ):
        return None

    launcher_version = (
        launcher_version.strip()
    )

    return launcher_version or None


class LauncherWindow(QWidget):
    def __init__(
            self,
            paths: LauncherPaths,
    ) -> None:
        super().__init__()

        self.paths = paths

        self.paths = paths

        self.launcher_version = load_launcher_version(
            self.paths.app_json
        )

        self.worker: Optional[UpdateWorker] = None

        self.notice_worker: Optional[NoticeWorker] = None

        self.last_result: Optional[UpdateResult] = None
        self.last_notice: Optional[NoticeInfo] = None

        self.setWindowTitle("GB7 Launcher")
        self.setWindowIcon(self._make_window_icon())
        self.setMinimumWidth(520)

        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint,
            True,
        )

        self.setStyleSheet(
            "background-color: #ffffff;"
        )

        # ============================================================
        # 전체 레이아웃
        # ============================================================
        root = QVBoxLayout(self)
        root.setContentsMargins(
            14,
            14,
            14,
            14,
        )
        root.setSpacing(10)

        # ============================================================
        # 제목
        # ============================================================
        self.lbl_title = QLabel("초기화 중…")
        self.lbl_title.setStyleSheet(
            """
            font-size: 16px;
            font-weight: 700;
            """
        )
        root.addWidget(self.lbl_title)

        # ============================================================
        # 긴급 공지 다시 보기
        # ============================================================
        notice_row = QHBoxLayout()
        notice_row.setSpacing(6)

        self.btn_notice_open = QPushButton(
            "🚨 긴급 공지 다시 보기"
        )
        self.btn_notice_open.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_notice_open.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_notice_open.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_notice_open.setMinimumWidth(160)

        # 긴급 공지가 있을 때만 표시한다.
        self.btn_notice_open.setVisible(False)

        self.btn_notice_open.clicked.connect(
            self.on_open_notice
        )

        notice_row.addWidget(
            self.btn_notice_open
        )
        notice_row.addStretch(1)

        root.addLayout(notice_row)

        # ============================================================
        # 상태 문구
        # ============================================================
        self.lbl_sub = QLabel(
            "잠시만 기다려주세요."
        )
        self.lbl_sub.setStyleSheet(
            "color: #555;"
        )
        root.addWidget(self.lbl_sub)

        # ============================================================
        # 진행률
        # ============================================================
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        root.addWidget(self.prog)

        # ============================================================
        # 로그 영역
        # ============================================================
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setVisible(False)
        self.txt_log.setMinimumHeight(180)
        root.addWidget(self.txt_log)

        # ============================================================
        # 지원 센터
        #
        # 첫째 줄: 공식 사이트 / 문의 버튼
        # 둘째 줄: 안내 문구
        # ============================================================
        self._support_site_url: Optional[str] = None
        self._support_qna_url: Optional[str] = None

        self.support_box = QFrame()
        self.support_box.setObjectName("supportBox")
        self.support_box.setVisible(False)
        self.support_box.setStyleSheet(
            """
            QFrame#supportBox {
                background-color: #ffffff;
                border: 1px solid #e1e5ea;
                border-radius: 8px;
            }

            QPushButton#supportSiteButton,
            QPushButton#supportQnaButton {
                background-color: transparent;
                border: 0;
                border-radius: 6px;
                padding: 6px 9px;
                font-size: 13px;
                font-weight: 600;
                text-align: left;
            }

            QPushButton#supportSiteButton {
                color: #2F80ED;
            }

            QPushButton#supportQnaButton {
                color: #E64980;
            }

            QPushButton#supportSiteButton:hover,
            QPushButton#supportQnaButton:hover {
                background-color: #f1f3f5;
            }

            QPushButton#supportSiteButton:pressed,
            QPushButton#supportQnaButton:pressed {
                background-color: #e5e7eb;
            }

            QLabel#supportDivider {
                color: #c3c8ce;
                background-color: transparent;
                font-size: 13px;
            }

            QLabel#supportDescription {
                color: #7b8794;
                background-color: transparent;
                font-size: 11px;
            }
            """
        )

        support_layout = QVBoxLayout(
            self.support_box
        )
        support_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        # 첫째 줄과 둘째 줄 사이 간격
        support_layout.setSpacing(9)

        support_link_row = QHBoxLayout()
        support_link_row.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        support_link_row.setSpacing(5)

        self.btn_support_site = QPushButton(
            "●  공식 사이트"
        )
        self.btn_support_site.setObjectName(
            "supportSiteButton"
        )
        self.btn_support_site.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_support_site.clicked.connect(
            self._open_support_site
        )
        support_link_row.addWidget(
            self.btn_support_site
        )

        support_divider = QLabel("|")
        support_divider.setObjectName(
            "supportDivider"
        )
        support_divider.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        support_link_row.addWidget(
            support_divider
        )

        self.btn_support_qna = QPushButton(
            "●  문의/Q&&A"
        )
        self.btn_support_qna.setObjectName(
            "supportQnaButton"
        )
        self.btn_support_qna.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_support_qna.clicked.connect(
            self._open_support_qna
        )
        support_link_row.addWidget(
            self.btn_support_qna
        )

        support_link_row.addStretch(1)
        support_layout.addLayout(
            support_link_row
        )

        self.lbl_support_description = QLabel(
            "※ 도움이 필요하면 공식 사이트 또는 "
            "문의/Q&A를 이용해 주세요."
        )
        self.lbl_support_description.setObjectName(
            "supportDescription"
        )
        support_layout.addWidget(
            self.lbl_support_description
        )

        root.addWidget(self.support_box)

        # ============================================================
        # 하단 버튼
        # ============================================================
        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.btn_toggle_log = QPushButton(
            "로그 보기"
        )
        self.btn_toggle_log.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_toggle_log.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_toggle_log.clicked.connect(
            self.on_toggle_log
        )
        button_row.addWidget(
            self.btn_toggle_log
        )

        button_row.addStretch(1)

        self.btn_retry = QPushButton("재시도")
        self.btn_retry.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_retry.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_retry.clicked.connect(
            self.on_retry
        )
        button_row.addWidget(
            self.btn_retry
        )

        self.btn_run = QPushButton("실행")
        self.btn_run.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_run.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_run.clicked.connect(
            self.on_run
        )
        button_row.addWidget(
            self.btn_run
        )

        self.btn_close = QPushButton("닫기")
        self.btn_close.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_close.setStyleSheet(
            btn_style(BTN_GRAY)
        )
        self.btn_close.clicked.connect(
            self.close
        )
        button_row.addWidget(
            self.btn_close
        )

        root.addLayout(button_row)

        # ============================================================
        # 초기 상태
        # ============================================================
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="초기화…",
            )
        )

        # 화면 생성 후 긴급 공지 및 업데이트 확인 시작
        QTimer.singleShot(
            0,
            self.start_notice_then_update,
        )

    # ================================================================
    # 창 아이콘
    # ================================================================
    def _make_window_icon(self) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(
            QColor("transparent")
        )

        painter = QPainter(pixmap)
        painter.setBrush(
            QColor("#e0e0e0")
        )
        painter.setPen(
            QColor("#e0e0e0")
        )
        painter.drawRect(
            0,
            0,
            32,
            32,
        )
        painter.end()

        return QIcon(pixmap)

    # ================================================================
    # UI 공통
    # ================================================================
    def log(
            self,
            message: str,
    ) -> None:
        """
        모든 로그 앞에 사용자 PC의 현재 시간을 붙여 표시한다.

        출력 예:
        [2026-07-16 11:06:04] [launcher] program_id=NAVER_BAND_MEMBER

        여러 줄 메시지가 들어오면 각 줄마다 시간을 붙인다.
        """
        log_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        lines = str(message).splitlines()

        if not lines:
            lines = [""]

        for line in lines:
            self.txt_log.append(
                f"[{log_time}] {line}"
            )

    def apply_state(
            self,
            state: UiState,
    ) -> None:
        self.lbl_sub.setText(
            state.status
        )

        self.prog.setValue(
            max(
                0,
                min(100, state.percent),
            )
        )

        self.btn_run.setEnabled(
            state.can_run
            and not state.busy
        )

        self.btn_retry.setEnabled(
            state.can_retry
            and not state.busy
        )

        self.btn_close.setEnabled(
            not state.busy
        )

        self.btn_toggle_log.setEnabled(True)

    def _show_ready_state(
            self,
            result: UpdateResult,
            status: str,
            can_retry: bool = False,
    ) -> None:
        """런처에서 직접 실행할 수 있는 준비 상태를 표시한다."""
        self.last_result = result
        self.lbl_title.setText("준비 완료")

        self.apply_state(
            UiState(
                busy=False,
                can_run=bool(result.exe_path),
                can_retry=can_retry,
                percent=self.prog.value(),
                status=status,
            )
        )

    # ================================================================
    # 메시지 박스
    # ================================================================
    def _msg_info(
            self,
            title: str,
            text: str,
    ) -> None:
        box = QMessageBox(self)
        box.setIcon(
            QMessageBox.Icon.Information
        )
        box.setWindowTitle(title)
        box.setText(text)
        box.setStyleSheet(
            msgbox_style(
                primary_color=BTN_GRAY
            )
        )
        box.exec()

    def _msg_warn(
            self,
            title: str,
            text: str,
    ) -> None:
        box = QMessageBox(self)
        box.setIcon(
            QMessageBox.Icon.Warning
        )
        box.setWindowTitle(title)
        box.setText(text)
        box.setStyleSheet(
            msgbox_style(
                primary_color=BTN_GRAY
            )
        )
        box.exec()

    # ================================================================
    # 업데이트 확인창
    # ================================================================
    def _show_update_confirm(
            self,
            current_version: str,
            latest_version: str,
    ) -> UpdateConfirmAction:
        """
        업데이트 전용 확인창을 표시한다.

        반환값:
        UPDATE:
            지금 업데이트를 선택했다.

        RUN_CURRENT:
            현재 버전 실행을 선택했다.

        CANCEL:
            X 버튼 또는 Esc로 팝업을 닫았다.
        """
        dialog = UpdateConfirmDialog(
            parent=self,
            current_version=current_version,
            latest_version=latest_version,
        )

        dialog.exec()
        return dialog.selected_action()

    # ================================================================
    # 지원 센터
    # ================================================================
    def _set_support_links(
            self,
            program_id: str,
            version: str,
    ) -> None:
        config = load_support_config(
            self.paths.data_dir
        )

        if config is None:
            self._support_site_url = None
            self._support_qna_url = None
            self.support_box.setVisible(False)
            return

        params = {
            "program": program_id,
            "ver": version,
            "os": platform.system(),
            "osver": platform.version(),
        }

        query_string = urlencode(params)

        self._support_site_url = (
            f"{config.site_url}"
            f"?{query_string}"
        )

        self._support_qna_url = (
            f"{config.qna_url}"
            f"?{query_string}"
        )

        self.btn_support_site.setToolTip(
            "공식 사이트를 브라우저에서 엽니다."
        )
        self.btn_support_qna.setToolTip(
            "문의 페이지를 브라우저에서 엽니다."
        )

        self.support_box.setVisible(True)

    def _open_support_site(self) -> None:
        if not self._support_site_url:
            return

        QDesktopServices.openUrl(
            QUrl(self._support_site_url)
        )

    def _open_support_qna(self) -> None:
        if not self._support_qna_url:
            return

        QDesktopServices.openUrl(
            QUrl(self._support_qna_url)
        )

    # ================================================================
    # 로그 표시/숨김
    # ================================================================
    def on_toggle_log(self) -> None:
        visible = not self.txt_log.isVisible()

        if visible:
            self.txt_log.setVisible(True)
            self.btn_toggle_log.setText(
                "로그 숨기기"
            )
            self.txt_log.setMinimumHeight(180)
            self.adjustSize()
            return

        self.txt_log.setVisible(False)
        self.btn_toggle_log.setText(
            "로그 보기"
        )
        self.txt_log.setMinimumHeight(0)

        self.adjustSize()

        self.resize(
            self.width(),
            self.minimumSizeHint().height(),
        )

    # ================================================================
    # 재시도
    # ================================================================
    def on_retry(self) -> None:
        self.txt_log.clear()

        self.last_result = None
        self.last_notice = None

        self.btn_notice_open.setVisible(False)

        self.start_notice_then_update()

    # ================================================================
    # 프로그램 실행
    # ================================================================
    def _run_result_exe(
            self,
            result: UpdateResult,
    ) -> bool:
        """
        UpdateResult에 들어 있는 실행 파일을 실행한다.

        성공:
            프로그램 실행 후 런처를 닫는다.

        실패:
            런처를 유지하고 재시도 및 실행 버튼을 제공한다.
        """
        self.last_result = result

        if not result.exe_path:
            self._msg_warn(
                "실행 실패",
                "실행 파일 경로를 찾지 못했습니다.",
            )

            self.lbl_title.setText("실패")

            self.apply_state(
                UiState(
                    busy=False,
                    can_run=False,
                    can_retry=True,
                    percent=self.prog.value(),
                    status="실행 파일 없음",
                )
            )
            return False

        ok, message = result.try_run(
            wait=False
        )

        if not ok:
            self._msg_warn(
                "실행 실패",
                message,
            )

            self.lbl_title.setText("실행 실패")

            self.apply_state(
                UiState(
                    busy=False,
                    can_run=True,
                    can_retry=True,
                    percent=self.prog.value(),
                    status="프로그램 실행에 실패했습니다.",
                )
            )
            return False

        # 프로그램 실행 후 런처 종료
        QTimer.singleShot(
            300,
            self.close,
        )
        return True

    def on_run(self) -> None:
        if self.last_result is None:
            self._msg_info(
                "안내",
                "아직 준비되지 않았습니다.",
            )
            return

        self._run_result_exe(
            self.last_result
        )

    # ================================================================
    # 창 닫기
    # ================================================================
    def closeEvent(
            self,
            event: QCloseEvent,
    ) -> None:
        # 업데이트 작업 중에는 종료하지 못하게 한다.
        if (
                self.worker is not None
                and self.worker.isRunning()
        ):
            self._msg_info(
                "안내",
                "업데이트 중에는 닫을 수 없습니다.",
            )
            event.ignore()
            return

        super().closeEvent(event)

    # ================================================================
    # 긴급 공지 다시 보기
    # ================================================================
    def on_open_notice(
            self,
            _checked: bool = False,
    ) -> None:
        if self.last_notice is None:
            return

        self.show_notice_dialog(
            notice=self.last_notice,
            modal=False,
        )

    def show_notice_dialog(
            self,
            notice: NoticeInfo,
            modal: bool,
    ) -> None:
        """
        긴급 공지창을 표시한다.

        오늘 하루 안보기를 선택하면
        사용자 PC 시간 기준 오늘 자정까지 자동 팝업을 숨긴다.
        """
        dialog = NoticeDialog(
            self,
            notice,
            allow_hide_day=True,
        )

        # 이 코드는 modal=True일 때 해당 다이얼로그를 닫기 전까지 프로그램의 다른 창을 조작하지 못하게 막는 설정입니다.
        if modal:
            dialog.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )

        dialog.exec()

        if dialog.hide_day_checked():
            hide_for_day(
                self.paths.notice_ack_json,
                notice.notice_id,
            )

            self.log(
                "[launcher] "
                "critical notice hidden until midnight: "
                f"{notice.notice_id}"
            )

    # ================================================================
    # 긴급 공지 확인 시작
    # ================================================================
    def start_notice_then_update(self) -> None:
        try:
            state = read_current_state(
                self.paths.current_json
            )
        except Exception as error:
            self.log(
                "[launcher] "
                "read_current_state failed: "
                f"{str(error)}"
            )

            self.start_worker(
                auto_update=False
            )
            return

        self._set_support_links(
            program_id=state.program_id,
            version=state.version,
        )

        self.lbl_title.setText(
            "긴급 공지 확인 중…"
        )

        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="긴급 공지 확인 중…",
            )
        )

        self.notice_worker = NoticeWorker(
            server_url=state.server_url,
            program_id=state.program_id,
        )

        self.notice_worker.sig_done.connect(
            self.on_notice_done
        )

        self.notice_worker.start()

    # ================================================================
    # 긴급 공지 조회 완료
    # ================================================================
    def on_notice_done(
            self,
            result: NoticeResult,
    ) -> None:
        """
        런처에서는 긴급 공지만 표시한다.

        긴급 공지 조건:
        - level == CRITICAL
        - force == True
        """
        if not result.ok:
            self.log(
                "[launcher] "
                "notice fetch failed: "
                f"{result.message}"
            )

            self.start_worker(
                auto_update=False
            )
            return

        notice = result.notice

        # 공지가 없으면 업데이트 확인으로 이동
        if notice is None:
            self.last_notice = None
            self.btn_notice_open.setVisible(False)

            self.start_worker(
                auto_update=False
            )
            return

        is_critical = (
                notice.force is True
                or notice.level == "CRITICAL"
        )

        # 일반 공지는 런처에서 표시하지 않는다.
        if not is_critical:
            self.log(
                "[launcher] "
                "normal notice skipped: "
                f"{notice.notice_id}"
            )

            self.last_notice = None
            self.btn_notice_open.setVisible(False)

            self.start_worker(
                auto_update=False
            )
            return

        # 긴급 공지를 다시 볼 수 있도록 저장
        self.last_notice = notice

        # 자동 팝업을 숨긴 상태여도 버튼은 항상 표시
        self.btn_notice_open.setText(
            "🚨 긴급 공지 다시 보기"
        )
        self.btn_notice_open.setVisible(True)

        # 오늘 하루 안보기 상태가 아니라면 자동 표시
        if not is_hidden(
                self.paths.notice_ack_json,
                notice.notice_id,
        ):
            self.show_notice_dialog(
                notice=notice,
                modal=True,
            )
        else:
            self.log(
                "[launcher] "
                "critical notice auto popup skipped: "
                f"{notice.notice_id}"
            )

        # 공지 처리 후 업데이트 확인
        self.start_worker(
            auto_update=False
        )

    # ================================================================
    # 업데이트 확인 시작
    # ================================================================
    def start_worker(
        self,
        auto_update: bool,
    ) -> None:
        if (
            self.worker is not None
            and self.worker.isRunning()
        ):
            return

        self.lbl_title.setText(
            "업데이트 중…"
            if auto_update
            else "업데이트 확인 중…"
        )

        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status=(
                    "업데이트를 시작합니다…"
                    if auto_update
                    else "서버에 접속 중…"
                ),
            )
        )

        self.log(
            "[launcher] launcher_version="
            f"{self.launcher_version}"
        )

        self.worker = UpdateWorker(
            paths=self.paths,
            auto_update=auto_update,
            launcher_version=self.launcher_version,
        )

        self.worker.sig_status.connect(
            self.on_worker_status
        )
        self.worker.sig_log.connect(
            self.on_worker_log
        )
        self.worker.sig_progress.connect(
            self.on_worker_progress
        )
        self.worker.sig_done.connect(
            self.on_worker_done
        )

        self.worker.start()

    def _start_worker_after_current_finishes(
            self,
            auto_update: bool,
    ) -> None:
        """
        현재 UpdateWorker가 sig_done을 보낸 뒤 완전히 종료되면
        다음 UpdateWorker를 시작한다.

        업데이트 확인 Worker에서 바로 실제 업데이트 Worker로
        넘어갈 때 QThread 중복 실행을 방지한다.
        """
        current_worker = self.worker

        if (
                current_worker is None
                or not current_worker.isRunning()
        ):
            self.start_worker(auto_update)
            return

        def start_next_worker() -> None:
            if self.worker is current_worker:
                self.worker = None

            self.start_worker(auto_update)

        current_worker.finished.connect(
            start_next_worker
        )

    # ================================================================
    # 업데이트 상태
    # ================================================================
    def on_worker_status(
            self,
            text: str,
    ) -> None:
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=self.prog.value(),
                status=text,
            )
        )

    def on_worker_log(
            self,
            text: str,
    ) -> None:
        self.log(text)

    def on_worker_progress(
            self,
            percent: int,
    ) -> None:
        self.prog.setValue(
            max(
                0,
                min(100, percent),
            )
        )

    # ================================================================
    # 업데이트 완료
    # ================================================================
    def on_worker_done(
            self,
            result: UpdateResult,
    ) -> None:
        self.last_result = result

        # ============================================================
        # 1. 새 버전이 있지만 아직 설치하지 않은 상태
        # ============================================================
        if result.ok and result.update_available:
            latest_version = (
                    result.latest_version or "?"
            )

            current_version = "?"

            try:
                state = read_current_state(
                    self.paths.current_json
                )
                current_version = state.version
            except Exception as error:
                self.log(
                    "[launcher] "
                    "current version read failed: "
                    f"{str(error)}"
                )

            action = self._show_update_confirm(
                current_version=current_version,
                latest_version=latest_version,
            )

            # --------------------------------------------------------
            # 지금 업데이트
            # 업데이트 완료 후 자동 실행한다.
            # --------------------------------------------------------
            if action == UpdateConfirmAction.UPDATE:
                self.log(
                    "[launcher] "
                    "user accepted update"
                )

                self._start_worker_after_current_finishes(
                    auto_update=True
                )
                return

            # --------------------------------------------------------
            # 현재 버전 실행
            # 버튼을 선택한 즉시 현재 버전을 실행한다.
            # --------------------------------------------------------
            if action == UpdateConfirmAction.RUN_CURRENT:
                self.log(
                    "[launcher] "
                    "user selected current version"
                )

                self._run_result_exe(result)
                return

            # --------------------------------------------------------
            # 팝업 X 또는 Esc
            # 자동 실행하지 않고 런처 화면에서 직접 실행하도록 한다.
            # --------------------------------------------------------
            self.log(
                "[launcher] "
                "update dialog canceled"
            )

            self._show_ready_state(
                result=result,
                status=(
                    "업데이트 선택을 취소했습니다. "
                    "'실행'을 누르면 현재 버전이 실행됩니다."
                ),
            )
            return

        # ============================================================
        # 2. 새 버전 설치 완료
        # ============================================================
        if result.ok and result.update_installed:
            self.lbl_title.setText("업데이트 완료")

            self.apply_state(
                UiState(
                    busy=False,
                    can_run=False,
                    can_retry=False,
                    percent=100,
                    status=(
                        "업데이트가 완료되었습니다. "
                        "프로그램을 실행합니다."
                    ),
                )
            )

            # 완료 문구가 잠깐 보인 뒤 새 버전을 자동 실행한다.
            QTimer.singleShot(
                500,
                lambda: self._run_result_exe(result),
            )
            return

        # ============================================================
        # 3. 이미 최신 버전이거나 로컬 버전이 더 최신인 경우
        # ============================================================
        if result.ok:
            self.prog.setValue(100)

            self._show_ready_state(
                result=result,
                status=(
                    "준비 완료. "
                    "'실행'을 눌러 시작하세요."
                ),
            )
            return

        # ============================================================
        # 4. 업데이트 확인 또는 업데이트 실패
        # ============================================================
        self.lbl_title.setText("실패")

        can_run_current = bool(result.exe_path)

        if can_run_current:
            status = (
                f"{result.message or '업데이트 실패'} "
                "현재 버전을 실행하거나 재시도할 수 있습니다."
            )
        else:
            status = (
                    result.message
                    or "업데이트 실패"
            )

        self.apply_state(
            UiState(
                busy=False,
                can_run=can_run_current,
                can_retry=True,
                percent=self.prog.value(),
                status=status,
            )
        )

        warning_text = (
                result.message
                or "업데이트 실패"
        )

        if can_run_current:
            warning_text += (
                "\n\n기존 버전은 '실행' 버튼으로 "
                "실행할 수 있습니다."
            )

        warning_text += "\n\n로그를 확인하세요."

        self._msg_warn(
            "업데이트 실패",
            warning_text,
        )


