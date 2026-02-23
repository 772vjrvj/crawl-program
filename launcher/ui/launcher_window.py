# launcher/ui/launcher_window.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QMessageBox
)

from launcher.core.paths import LauncherPaths
from launcher.workers.update_worker import UpdateWorker, UpdateResult
from PySide6.QtCore import QTimer  # 상단 import 추가


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
        self.last_result: Optional[UpdateResult] = None

        self.setWindowTitle("CrawlProgram Launcher")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)  # 고객 PC에서 묻히는거 방지(원하면 제거)

        # ---- UI ----
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.lbl_title = QLabel("업데이트 확인 중…")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(self.lbl_title)

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

        # 버튼 영역
        row = QHBoxLayout()
        row.setSpacing(8)

        self.btn_toggle_log = QPushButton("로그 보기")
        self.btn_toggle_log.clicked.connect(self.on_toggle_log)
        row.addWidget(self.btn_toggle_log)

        row.addStretch(1)

        self.btn_retry = QPushButton("재시도")
        self.btn_retry.clicked.connect(self.on_retry)
        row.addWidget(self.btn_retry)

        self.btn_run = QPushButton("실행")
        self.btn_run.clicked.connect(self.on_run)
        row.addWidget(self.btn_run)

        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)

        root.addLayout(row)

        # 초기 상태
        self.apply_state(UiState(
            busy=True,
            can_run=False,
            can_retry=False,
            percent=0,
            status="초기화…"
        ))

        # 자동 시작
        self.start_worker()

    # ---------------- UI helpers ----------------
    def log(self, msg: str) -> None:
        self.txt_log.append(msg)

    def apply_state(self, st: UiState) -> None:
        self.lbl_sub.setText(st.status)
        self.prog.setValue(max(0, min(100, st.percent)))

        self.btn_run.setEnabled(st.can_run and not st.busy)
        self.btn_retry.setEnabled(st.can_retry and not st.busy)
        self.btn_close.setEnabled(not st.busy)

        self.btn_toggle_log.setEnabled(True)

    # ---------------- events ----------------
    def on_toggle_log(self) -> None:
        vis = not self.txt_log.isVisible()
        self.txt_log.setVisible(vis)
        self.btn_toggle_log.setText("로그 숨기기" if vis else "로그 보기")

    def on_retry(self) -> None:
        self.txt_log.clear()
        self.last_result = None
        self.start_worker()

    def on_run(self) -> None:
        # 업데이트 워커가 run_exe까지 해주므로 보통은 필요 없음.
        # 그래도 실패/최신 상태에서 "수동 실행" 버튼을 둘 수 있게 훅만 유지.
        if self.last_result is None:
            QMessageBox.information(self, "안내", "아직 준비되지 않았습니다.")
            return

        if not self.last_result.exe_path:
            QMessageBox.warning(self, "실행 실패", "실행 파일 경로를 찾지 못했습니다.")
            return

        ok, msg = self.last_result.try_run(wait=False)
        if not ok:
            QMessageBox.warning(self, "실행 실패", msg)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 업데이트 중 닫기 막기(고객이 중간에 닫아버리면 골치아픔)
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "안내", "업데이트 중에는 닫을 수 없습니다.")
            event.ignore()
            return
        super().closeEvent(event)

    # ---------------- worker wiring ----------------
    def start_worker(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self.lbl_title.setText("업데이트 확인 중…")
        self.apply_state(UiState(busy=True, can_run=False, can_retry=False, percent=0, status="서버에 접속 중…"))

        self.worker = UpdateWorker(paths=self.paths)

        self.worker.sig_status.connect(self.on_worker_status)
        self.worker.sig_log.connect(self.on_worker_log)
        self.worker.sig_progress.connect(self.on_worker_progress)
        self.worker.sig_done.connect(self.on_worker_done)

        self.worker.start()

    def on_worker_status(self, text: str) -> None:
        self.apply_state(UiState(
            busy=True,
            can_run=False,
            can_retry=False,
            percent=self.prog.value(),
            status=text,
        ))

    def on_worker_log(self, text: str) -> None:
        self.log(text)

    def on_worker_progress(self, percent: int) -> None:
        self.prog.setValue(max(0, min(100, percent)))

    def on_worker_done(self, result: UpdateResult) -> None:
        self.last_result = result

        if result.ok:
            self.lbl_title.setText("완료")
            self.apply_state(UiState(
                busy=False,
                can_run=bool(result.exe_path),
                can_retry=False,
                percent=100,
                status="최신 버전 실행 완료" if result.did_run else "최신 버전 준비 완료",
            ))
            # === 신규 === 실행까지 성공했으면 런처 자동 종료
            if result.did_run:
                QTimer.singleShot(800, self.close)
            return
        else:
            self.lbl_title.setText("실패")
            self.apply_state(UiState(
                busy=False,
                can_run=False,
                can_retry=True,
                percent=self.prog.value(),
                status=result.message or "업데이트 실패",
            ))
            QMessageBox.warning(self, "업데이트 실패", (result.message or "업데이트 실패") + "\n\n로그를 확인하세요.")