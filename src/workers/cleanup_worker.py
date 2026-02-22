# src/workers/cleanup_worker.py
from __future__ import annotations

from typing import Optional, Any, cast
from requests import Session
from PySide6.QtCore import QThread, Signal

from src.core.global_state import GlobalState


class CleanupWorker(QThread):
    done: Signal = Signal(bool, str)  # ok, msg

    def __init__(
            self,
            api_worker: Optional[Any],
            on_demand_worker: Optional[Any],
            progress_worker: Optional[Any],
            session: Optional[Session],
    ) -> None:
        super().__init__()
        self.api_worker = api_worker
        self.on_demand_worker = on_demand_worker
        self.progress_worker = progress_worker
        self.session = session

    def run(self) -> None:
        ok = True
        msgs = []

        try:
            # 1) 크롤링 워커 stop
            try:
                if self.on_demand_worker is not None:
                    self.on_demand_worker.stop()
            except Exception as e:
                ok = False
                msgs.append(f"on_demand stop error: {str(e)}")

            # 2) 프로그레스 워커 stop
            try:
                if self.progress_worker is not None:
                    self.progress_worker.stop()
            except Exception as e:
                ok = False
                msgs.append(f"progress stop error: {str(e)}")

            # 3) 로그인 체크 워커 stop + wait (최대 3초)
            try:
                if self.api_worker is not None:
                    self.api_worker.stop()
                    try:
                        self.api_worker.wait(3000)  # QThread.wait(msecs) 기대
                    except TypeError:
                        # 일부 구현체에서 wait 시그니처가 다를 수 있어 방어
                        self.api_worker.wait()
            except Exception as e:
                ok = False
                msgs.append(f"api_worker stop/wait error: {str(e)}")

            # 4) 세션 정리
            try:
                st = GlobalState()
                sess = cast(Optional[Session], st.get("session"))
                if sess is None:
                    sess = self.session

                if sess is not None:
                    try:
                        sess.cookies.clear()
                    except Exception:
                        pass
                    try:
                        sess.close()
                    except Exception:
                        pass

                st.set("session", None)
            except Exception as e:
                ok = False
                msgs.append(f"session cleanup error: {str(e)}")

        except Exception as e:
            # === 신규 === 예상 못 한 최상위 예외도 흡수
            ok = False
            msgs.append(f"cleanup fatal error: {str(e)}")

        finally:
            # === 신규 === 어떤 상황에서도 done은 반드시 emit
            msg = "ok" if ok else (" / ".join(msgs) if msgs else "cleanup failed")
            try:
                self.done.emit(ok, msg)
            except Exception:
                # emit 자체가 예외나는 경우는 거의 없지만, 그래도 방어
                pass