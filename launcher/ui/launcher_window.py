# launcher/ui/launcher_window.py
from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QWidget,
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


class LauncherWindow(QWidget):
    def __init__(
            self,
            paths: LauncherPaths,
    ) -> None:
        super().__init__()

        self.paths = paths

        self.worker: Optional[UpdateWorker] = None
        self.notice_worker: Optional[NoticeWorker] = None

        self.last_result: Optional[UpdateResult] = None

        # 긴급 공지를 다시 보기 위해 보관한다.
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

        self.lbl_title = QLabel("초기화 중…")
        self.lbl_title.setStyleSheet(
            "font-size: 16px;"
            "font-weight: 700;"
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

        self.lbl_sub = QLabel(
            "잠시만 기다려주세요."
        )
        self.lbl_sub.setStyleSheet(
            "color: #555;"
        )
        root.addWidget(self.lbl_sub)

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
        # ============================================================
        self.lbl_support = QLabel("")
        self.lbl_support.setTextFormat(
            Qt.TextFormat.RichText
        )
        self.lbl_support.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.lbl_support.setOpenExternalLinks(True)
        self.lbl_support.setStyleSheet(
            "color:#666;"
            "padding:6px 0;"
        )
        root.addWidget(self.lbl_support)

        # ============================================================
        # 하단 버튼 영역
        # ============================================================
        row = QHBoxLayout()
        row.setSpacing(8)

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
        row.addWidget(self.btn_toggle_log)

        row.addStretch(1)

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
        row.addWidget(self.btn_retry)

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
        row.addWidget(self.btn_run)

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
        row.addWidget(self.btn_close)

        root.addLayout(row)

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
    # UI 공통 함수
    # ================================================================
    def log(
            self,
            message: str,
    ) -> None:
        self.txt_log.append(message)

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

    def _msg_question_yesno(
            self,
            title: str,
            text: str,
    ) -> QMessageBox.StandardButton:
        box = QMessageBox(self)
        box.setIcon(
            QMessageBox.Icon.Question
        )
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(
            QMessageBox.StandardButton.Yes
        )
        box.setStyleSheet(
            msgbox_style(
                primary_color=BTN_GRAY
            )
        )

        return box.exec()

    # ================================================================
    # 지원 센터 링크
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
            self.lbl_support.setVisible(False)
            return

        params = {
            "program": program_id,
            "ver": version,
            "os": platform.system(),
            "osver": platform.version(),
        }

        self.lbl_support.setText(
            f'🛟 <b>지원 센터</b> &nbsp; '
            f'🌐 <a href="{config.site_url}">'
            f'공식 사이트'
            f'</a>'
            f' &nbsp; | &nbsp; '
            f'📨 <a href="{config.qna_url}">'
            f'문의/Q&amp;A'
            f'</a>'
        )

        self.lbl_support.setVisible(True)

    # ================================================================
    # 화면 이벤트
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

    def on_retry(self) -> None:
        self.txt_log.clear()

        self.last_result = None
        self.last_notice = None

        self.btn_notice_open.setVisible(False)

        self.start_notice_then_update()

    def on_run(self) -> None:
        if self.last_result is None:
            self._msg_info(
                "안내",
                "아직 준비되지 않았습니다.",
            )
            return

        if not self.last_result.exe_path:
            self._msg_warn(
                "실행 실패",
                "실행 파일 경로를 찾지 못했습니다.",
            )
            return

        ok, message = self.last_result.try_run(
            wait=False
        )

        if not ok:
            self._msg_warn(
                "실행 실패",
                message,
            )
            return

        QTimer.singleShot(
            300,
            self.close,
        )

    def closeEvent(
            self,
            event: QCloseEvent,
    ) -> None:
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
    # 긴급 공지
    # ================================================================
    def on_open_notice(
            self,
            _checked: bool = False,
    ) -> None:
        """
        긴급 공지 다시 보기 버튼 클릭 처리.
        """
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
        긴급 공지 팝업을 표시한다.

        오늘 하루 안보기를 체크하면
        오늘 자정까지 자동 팝업을 숨긴다.
        """
        dialog = NoticeDialog(
            self,
            notice,
            allow_hide_day=True,
        )

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
    # 긴급 공지 확인 후 업데이트 확인
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

    def on_notice_done(
            self,
            result: NoticeResult,
    ) -> None:
        """
        서버에서 받은 최신 공지를 처리한다.

        처리 정책:
        - force=true 또는 level=CRITICAL:
          긴급 공지로 처리한다.
        - 그 외 일반 공지:
          런처에서는 표시하지 않는다.
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

        # ============================================================
        # 긴급 공지 테스트 시작
        #
        # 테스트가 끝나면 아래 블록 전체를 주석 처리하거나 삭제한다.
        # ============================================================
        # notice = NoticeInfo(
        #     notice_id="TEST_CRITICAL_001",
        #     level="CRITICAL",
        #     force=True,
        #     title="긴급 공지 테스트",
        #     content=(
        #         "현재 긴급 공지 기능을 테스트하고 있습니다.\n\n"
        #         "로그인 서버 점검 또는 서비스 장애가 발생한 경우\n"
        #         "이곳에 긴급 안내 내용이 표시됩니다.\n\n"
        #         "오늘 하루 안보기를 체크하면 오늘 자정까지\n"
        #         "런처를 다시 실행해도 자동 팝업이 표시되지 않습니다.\n\n"
        #         "자동 팝업이 표시되지 않아도 런처 화면의\n"
        #         "'긴급 공지 다시 보기' 버튼으로 확인할 수 있습니다."
        #     ),
        # )

        # 공지가 없으면 바로 업데이트 확인을 시작한다.
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

        # 긴급 공지를 다시 볼 수 있도록 보관한다.
        self.last_notice = notice

        # 자동 팝업 여부와 관계없이 다시 보기 버튼은 표시한다.
        self.btn_notice_open.setText(
            "🚨 긴급 공지 다시 보기"
        )
        self.btn_notice_open.setVisible(True)

        # 오늘 하루 안보기 상태가 아니면 자동 팝업을 표시한다.
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

        self.start_worker(
            auto_update=False
        )

    # ================================================================
    # 업데이트 Worker
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
            "업데이트 확인 중…"
        )

        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="서버에 접속 중…",
            )
        )

        self.worker = UpdateWorker(
            paths=self.paths,
            auto_update=auto_update,
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

    def on_worker_done(
            self,
            result: UpdateResult,
    ) -> None:
        self.last_result = result

        # 새 버전이 있는 경우
        if (
                result.ok
                and getattr(
            result,
            "update_available",
            False,
        )
        ):
            latest_version = (
                    result.latest_version or "?"
            )

            answer = self._msg_question_yesno(
                "업데이트 안내",
                (
                    f"새 버전({latest_version})이 있습니다.\n"
                    f"업데이트를 진행하시겠습니까?\n\n"
                    f"- 예: 업데이트 후 실행 준비\n"
                    f"- 아니오: 현재 버전 실행 준비"
                ),
            )

            if (
                    answer
                    == QMessageBox.StandardButton.Yes
            ):
                self.txt_log.append(
                    "[launcher] "
                    "user accepted update"
                )

                self.start_worker(
                    auto_update=True
                )
                return

            self.txt_log.append(
                "[launcher] "
                "user skipped update"
            )

            if not result.exe_path:
                self._msg_warn(
                    "실행 실패",
                    "현재 버전 실행 파일을 찾지 못했습니다.",
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
                return

            self.lbl_title.setText(
                "준비 완료"
            )

            self.apply_state(
                UiState(
                    busy=False,
                    can_run=True,
                    can_retry=False,
                    percent=100,
                    status=(
                        "준비 완료. "
                        "'실행'을 눌러 시작하세요."
                    ),
                )
            )
            return

        # 최신 버전이거나 설치가 완료된 경우
        if result.ok:
            self.lbl_title.setText(
                "준비 완료"
            )

            self.apply_state(
                UiState(
                    busy=False,
                    can_run=bool(
                        result.exe_path
                    ),
                    can_retry=False,
                    percent=100,
                    status=(
                        "준비 완료. "
                        "'실행'을 눌러 시작하세요."
                    ),
                )
            )
            return

        # 업데이트 실패
        self.lbl_title.setText("실패")

        self.apply_state(
            UiState(
                busy=False,
                can_run=False,
                can_retry=True,
                percent=self.prog.value(),
                status=(
                        result.message
                        or "업데이트 실패"
                ),
            )
        )

        self._msg_warn(
            "업데이트 실패",
            (
                    result.message
                    or "업데이트 실패"
            )
            + "\n\n로그를 확인하세요.",
            )