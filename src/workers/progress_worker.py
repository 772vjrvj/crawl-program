from __future__ import annotations

import queue
from typing import Optional, Tuple
from queue import Queue

from PySide6.QtCore import QThread, Signal


class ProgressWorker(QThread):
    """
    작업 큐에서 (start, end) 값을 받아
    20단계로 나누어 progress를 emit 하는 Worker
    """

    # === Signal 정의 ===
    progress_signal: Signal = Signal(int)
    log_signal: Signal = Signal(str)

    def __init__(self, task_queue: Queue[Optional[Tuple[int, int]]]) -> None:
        super().__init__()
        self.task_queue: Queue[Optional[Tuple[int, int]]] = task_queue
        self.running: bool = True

    # =========================================================
    # Thread Main Loop
    # =========================================================
    def run(self) -> None:
        while self.running:
            try:
                task = self.task_queue.get(timeout=1)

                # 종료 신호
                if task is None:
                    break

                start_value, end_value = task
                self._process_task(start_value, end_value)

            except queue.Empty:
                if not self.running:
                    break

    # =========================================================
    # 내부 작업 처리
    # =========================================================
    def _process_task(self, start_value: int, end_value: int) -> None:
        diff_value: int = end_value - start_value
        inter_time: int = 20

        div_value: float = diff_value / inter_time
        millisecond: int = int(500 / inter_time)

        for i in range(1, inter_time + 1):
            if not self.running:
                break

            progress_value: int = int(start_value + (div_value * i))
            self.progress_signal.emit(progress_value)
            QThread.msleep(millisecond)

    # =========================================================
    # Stop
    # =========================================================
    def stop(self) -> None:
        """스레드 종료"""
        self.running = False
        self.task_queue.put(None)