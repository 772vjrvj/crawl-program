# src/workers/cleanup_worker.py
from __future__ import annotations

from typing import Optional, Any
from requests import Session
from PySide6.QtCore import QThread, Signal

from src.core.global_state import GlobalState


class CleanupWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, api_worker: Optional[Any], on_demand_worker: Optional[Any],
                 progress_worker: Optional[Any], session: Optional[Session]) -> None:
        super().__init__()
        self.api_worker = api_worker
        self.on_demand_worker = on_demand_worker
        self.progress_worker = progress_worker
        self.session = session

    def run(self) -> None:
        errors: list[str] = []
        workers = (
            ("on_demand_worker", self.on_demand_worker),
            ("progress_worker", self.progress_worker),
            ("api_worker", self.api_worker),
        )
        try:
            # 먼저 모든 Worker에 정지 요청을 보낸다.
            for name, worker in workers:
                if worker is not None:
                    try:
                        worker.stop()
                        worker.quit()
                    except Exception as exc:
                        errors.append(f"{name} stop error: {type(exc).__name__}")

            # GUI가 아닌 종료 전용 스레드에서 실제 종료까지 기다린다.
            # main_window의 기존 강제 종료 타이머는 그대로 이용한다.
            for name, worker in workers:
                if worker is not None:
                    try:
                        while not worker.wait(1000):
                            pass
                    except Exception as exc:
                        errors.append(f"{name} wait error: {type(exc).__name__}")

            # 종료 확인에 실패하면 사용 중인 Session을 변경하지 않는다.
            if not errors:
                sess = self.session
                if sess is not None:
                    sess.cookies.clear()
                    sess.close()
                state = GlobalState()
                if state.get(GlobalState.SESSION) is sess:
                    state.set(GlobalState.SESSION, None)
        except Exception as exc:
            errors.append(f"session cleanup error: {type(exc).__name__}")
        finally:
            self.done.emit(not errors, " / ".join(errors) if errors else "ok")
