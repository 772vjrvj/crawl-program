# launcher/ui/launcher_window.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import platform  # === 신규 ===
from urllib.parse import urlencode  # === 신규 ===

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QMessageBox
)
from PySide6.QtWidgets import QSizePolicy  # 상단 import에 추가
from launcher.core.paths import LauncherPaths
from launcher.core.state import read_current_state  # === 신규 ===
from launcher.core.notice_store import is_hidden, hide_for_day  # === 신규 ===
from launcher.workers.notice_worker import NoticeWorker, NoticeResult  # === 신규 ===
from launcher.core.api import NoticeInfo  # === 신규 ===
from launcher.workers.update_worker import UpdateWorker, UpdateResult
from launcher.core.app_config import load_support_config  # === 신규 ===

# === 신규 === NoticeDialog 분리
from launcher.ui.notice_dialog import NoticeDialog

# === 신규 === 공통 스타일 (ui/style로 통일)
from launcher.ui.style.style import (
    BTN_GRAY,
    BTN_PRIMARY,
    btn_style,
    msgbox_style,
    notice_banner_style,
)


@dataclass(frozen=True)
class UiState:
    busy: bool
    can_run: bool
    can_retry: bool
    percent: int
    status: str


class LauncherWindow(QWidget):
    def __init__(self, paths: LauncherPaths) -> None:
        super().__init__()
        self.paths = paths

        self.worker: Optional[UpdateWorker] = None
        self.notice_worker: Optional[NoticeWorker] = None  # === 신규 ===

        self.last_result: Optional[UpdateResult] = None
        self.last_notice: Optional[NoticeInfo] = None  # === 신규 ===

        self.setWindowTitle("GB7 Launcher")
        self.setWindowIcon(self._make_window_icon())
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet("background-color: #ffffff;")

        # ---- UI ----
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.lbl_title = QLabel("초기화 중…")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(self.lbl_title)

        # =========================
        # 공지 배너(🔔) (Label + Button)
        # =========================
        notice_row = QHBoxLayout()
        notice_row.setSpacing(6)

        self.lbl_notice = QLabel("")
        self.lbl_notice.setVisible(False)
        self.lbl_notice.setStyleSheet(notice_banner_style(BTN_GRAY))

        self.btn_notice_open = QPushButton("보기")
        self.btn_notice_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_notice_open.setStyleSheet(btn_style(BTN_GRAY))
        self.btn_notice_open.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)  # ✅ 세로로 맞춤
        self.btn_notice_open.setMinimumWidth(64)  # (선택) 버튼 폭 통일
        self.btn_notice_open.setVisible(False)
        self.btn_notice_open.clicked.connect(lambda: self.on_open_notice("open"))

        notice_row.addWidget(self.lbl_notice)
        notice_row.addWidget(self.btn_notice_open)
        notice_row.addStretch(1)

        root.addLayout(notice_row)

        self.lbl_sub = QLabel("잠시만 기다려주세요.")
        self.lbl_sub.setStyleSheet("color: #555;")
        root.addWidget(self.lbl_sub)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        root.addWidget(self.prog)

        # 로그 영역(기본은 숨김)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setVisible(False)
        self.txt_log.setMinimumHeight(180)
        root.addWidget(self.txt_log)

        # 지원 센터(공식 사이트/문의/Q&A) 링크 (버튼 영역 바로 위)
        self.lbl_support = QLabel("")
        self.lbl_support.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_support.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.lbl_support.setOpenExternalLinks(True)
        self.lbl_support.setStyleSheet("color:#666; padding:6px 0;")
        root.addWidget(self.lbl_support)

        # 버튼 영역
        row = QHBoxLayout()
        row.setSpacing(8)

        self.btn_toggle_log = QPushButton("로그 보기")
        self.btn_toggle_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_log.setStyleSheet(btn_style(BTN_GRAY))  # === 신규 ===
        self.btn_toggle_log.clicked.connect(self.on_toggle_log)
        row.addWidget(self.btn_toggle_log)

        row.addStretch(1)

        self.btn_retry = QPushButton("재시도")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.setStyleSheet(btn_style(BTN_GRAY))  # === 신규 ===
        self.btn_retry.clicked.connect(self.on_retry)
        row.addWidget(self.btn_retry)

        self.btn_run = QPushButton("실행")
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setStyleSheet(btn_style(BTN_GRAY))  # === 신규 ===
        self.btn_run.clicked.connect(self.on_run)
        row.addWidget(self.btn_run)

        self.btn_close = QPushButton("닫기")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(btn_style(BTN_GRAY))  # === 신규 ===
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)

        root.addLayout(row)

        # 초기 상태
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="초기화…",
            )
        )

        # === 신규 === 시작 순서: 공지(긴급은 업데이트 전에) → 업데이트 체크(자동 실행 X)
        QTimer.singleShot(0, self.start_notice_then_update)

    def _make_window_icon(self) -> QIcon:
        pix = QPixmap(32, 32)
        pix.fill(QColor("transparent"))

        painter = QPainter(pix)
        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QColor("#e0e0e0"))
        painter.drawRect(0, 0, 32, 32)
        painter.end()

        return QIcon(pix)

    # ---------------- UI helpers ----------------
    def log(self, msg: str) -> None:
        self.txt_log.append(msg)

    def apply_state(self, st: UiState) -> None:
        self.lbl_sub.setText(st.status)
        self.prog.setValue(max(0, min(100, st.percent)))

        self.btn_run.setEnabled(st.can_run and (not st.busy))
        self.btn_retry.setEnabled(st.can_retry and (not st.busy))
        self.btn_close.setEnabled(not st.busy)

        self.btn_toggle_log.setEnabled(True)

    # === 신규 === QMessageBox 래퍼(버튼 스타일 포함)
    def _msg_info(self, title: str, text: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStyleSheet(msgbox_style(primary_color=BTN_GRAY))
        box.exec()

    def _msg_warn(self, title: str, text: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStyleSheet(msgbox_style(primary_color=BTN_GRAY))
        box.exec()

    def _msg_question_yesno(self, title: str, text: str) -> QMessageBox.StandardButton:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        box.setStyleSheet(msgbox_style(primary_color=BTN_GRAY))
        return box.exec()

    # === 신규 === 지원 링크 세팅
    def _set_support_links(self, program_id: str, version: str) -> None:
        cfg = load_support_config(self.paths.data_dir)

        if cfg is None:
            self.lbl_support.setVisible(False)
            return

        params = {
            "program": program_id,
            "ver": version,
            "os": platform.system(),
            "osver": platform.version(),
        }
        qs = urlencode(params)

        site_url = f"{cfg.site_url}?{qs}"
        qna_url = f"{cfg.qna_url}?{qs}"

        self.lbl_support.setText(
            f'🛟 <b>지원 센터</b> &nbsp; '
            f'🌐 <a href="{site_url}">공식 사이트</a>'
            f' &nbsp; | &nbsp; '
            f'📨 <a href="{qna_url}">문의/Q&amp;A</a>'
        )
        self.lbl_support.setVisible(True)

    # ---------------- events ----------------
    def on_toggle_log(self) -> None:
        vis = not self.txt_log.isVisible()

        if vis:
            self.txt_log.setVisible(True)
            self.btn_toggle_log.setText("로그 숨기기")
            self.txt_log.setMinimumHeight(180)
            self.adjustSize()
        else:
            self.txt_log.setVisible(False)
            self.btn_toggle_log.setText("로그 보기")
            self.txt_log.setMinimumHeight(0)
            self.adjustSize()
            self.resize(self.width(), self.minimumSizeHint().height())

    def on_retry(self) -> None:
        self.txt_log.clear()
        self.last_result = None
        self.last_notice = None

        self.lbl_notice.setVisible(False)
        self.btn_notice_open.setVisible(False)  # ✅ 버튼도 같이 숨김

        self.start_notice_then_update()

    def on_run(self) -> None:
        if self.last_result is None:
            self._msg_info("안내", "아직 준비되지 않았습니다.")  # === 신규 ===
            return

        if not self.last_result.exe_path:
            self._msg_warn("실행 실패", "실행 파일 경로를 찾지 못했습니다.")  # === 신규 ===
            return

        ok, msg = self.last_result.try_run(wait=False)
        if not ok:
            self._msg_warn("실행 실패", msg)  # === 신규 ===
            return

        QTimer.singleShot(300, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 업데이트 중 닫기 막기
        if self.worker is not None and self.worker.isRunning():
            self._msg_info("안내", "업데이트 중에는 닫을 수 없습니다.")  # === 신규 ===
            event.ignore()
            return
        super().closeEvent(event)

    # === 신규 === 공지 배너 클릭 시 공지창 열기
    def on_open_notice(self, _href: str) -> None:
        if self.last_notice is None:
            return
        self.show_notice_dialog(self.last_notice, modal=False)

    # === 신규 === 공지 다이얼로그 표시
    def show_notice_dialog(self, notice: NoticeInfo, modal: bool) -> None:
        # CRITICAL/force는 숨김 불가 정책
        allow_hide_day = (not notice.force) and (notice.level != "CRITICAL")

        dlg = NoticeDialog(self, notice, allow_hide_day=allow_hide_day)
        if modal:
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.exec()

        # 오늘 하루 안보기 체크 시 로컬 저장
        if dlg.hide_day_checked():
            hide_for_day(self.paths.notice_ack_json, notice.notice_id)

    # ---------------- notice then update ----------------
    def start_notice_then_update(self) -> None:
        try:
            st = read_current_state(self.paths.current_json)
        except Exception as e:
            self.log(f"[launcher] read_current_state failed: {str(e)}")
            self.start_worker(auto_update=False)
            return

        # === 신규 === 지원센터 링크 세팅(여기가 제일 적절한 위치)
        self._set_support_links(program_id=st.program_id, version=st.version)

        self.lbl_title.setText("공지 확인 중…")
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="공지 확인 중…",
            )
        )

        self.notice_worker = NoticeWorker(server_url=st.server_url, program_id=st.program_id)
        self.notice_worker.sig_done.connect(self.on_notice_done)
        self.notice_worker.start()

    def on_notice_done(self, result: NoticeResult) -> None:
        if not result.ok:
            self.log(f"[launcher] notice fetch failed: {result.message}")
            self.start_worker(auto_update=False)
            return

        notice = result.notice
        if notice is None:
            self.start_worker(auto_update=False)
            return

        self.last_notice = notice

        # === 긴급 판단 ===
        is_modal = (notice.force is True) or (notice.level == "CRITICAL")

        # === 오늘 하루 안보기 적용: 긴급은 무시, 일반만 적용 ===
        if (not is_modal) and is_hidden(self.paths.notice_ack_json, notice.notice_id):
            self.log(f"[launcher] notice hidden by ack: {notice.notice_id}")
            self.start_worker(auto_update=False)
            return

        # === 긴급 공지는 업데이트 전에 모달로 바로 ===
        if is_modal:
            self.show_notice_dialog(notice, modal=True)

            # 모달 공지는 배너를 굳이 띄우지 않음(원하면 아래 2줄 주석 해제)
            self.lbl_notice.setVisible(False)
            self.btn_notice_open.setVisible(False)
        else:
            safe_title = notice.title if notice.title else "새 공지"
            self.lbl_notice.setText(f"🔔  {safe_title}")
            self.lbl_notice.setVisible(True)
            self.btn_notice_open.setVisible(True)

        # 공지 처리 후 업데이트 체크로
        self.start_worker(auto_update=False)

    # ---------------- update worker wiring ----------------
    def start_worker(self, auto_update: bool) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self.lbl_title.setText("업데이트 확인 중…")
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=0,
                status="서버에 접속 중…",
            )
        )

        self.worker = UpdateWorker(paths=self.paths, auto_update=auto_update)
        self.worker.sig_status.connect(self.on_worker_status)
        self.worker.sig_log.connect(self.on_worker_log)
        self.worker.sig_progress.connect(self.on_worker_progress)
        self.worker.sig_done.connect(self.on_worker_done)
        self.worker.start()

    def on_worker_status(self, text: str) -> None:
        self.apply_state(
            UiState(
                busy=True,
                can_run=False,
                can_retry=False,
                percent=self.prog.value(),
                status=text,
            )
        )

    def on_worker_log(self, text: str) -> None:
        self.log(text)

    def on_worker_progress(self, percent: int) -> None:
        self.prog.setValue(max(0, min(100, percent)))

    def on_worker_done(self, result: UpdateResult) -> None:
        self.last_result = result

        # 업데이트가 있으면 "진행할까요?" (자동 실행 X)
        if result.ok and getattr(result, "update_available", False):
            latest_v = result.latest_version or "?"
            q = self._msg_question_yesno(
                "업데이트 안내",
                f"새 버전({latest_v})이 있습니다.\n업데이트를 진행하시겠습니까?\n\n"
                f"- 예: 업데이트 후 실행(준비)\n"
                f"- 아니오: 현재 버전 실행(준비)",
            )  # === 신규 ===

            if q == QMessageBox.StandardButton.Yes:
                self.txt_log.append("[launcher] user accepted update")
                self.start_worker(auto_update=True)
                return

            self.txt_log.append("[launcher] user skipped update")
            if not result.exe_path:
                self._msg_warn("실행 실패", "현재 버전 실행 파일을 찾지 못했습니다.")  # === 신규 ===
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

            self.lbl_title.setText("준비 완료")
            self.apply_state(
                UiState(
                    busy=False,
                    can_run=True,
                    can_retry=False,
                    percent=100,
                    status="준비 완료. '실행'을 눌러 시작하세요.",
                )
            )
            return

        # 성공(최신이거나 설치 완료) => 실행은 버튼으로만
        if result.ok:
            self.lbl_title.setText("준비 완료")
            self.apply_state(
                UiState(
                    busy=False,
                    can_run=bool(result.exe_path),
                    can_retry=False,
                    percent=100,
                    status="준비 완료. '실행'을 눌러 시작하세요.",
                )
            )
            return

        # 실패
        self.lbl_title.setText("실패")
        self.apply_state(
            UiState(
                busy=False,
                can_run=False,
                can_retry=True,
                percent=self.prog.value(),
                status=result.message or "업데이트 실패",
            )
        )
        self._msg_warn("업데이트 실패", (result.message or "업데이트 실패") + "\n\n로그를 확인하세요.")  # === 신규 ===