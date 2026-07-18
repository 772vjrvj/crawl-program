# launcher/workers/notice_worker.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QThread, Signal

from launcher.core.api import (
    fetch_latest_notice,
    NoticeInfo,
)


@dataclass
class NoticeResult:
    """
    긴급 공지 API 조회 결과.

    NoticeWorker가 API 호출을 마친 뒤
    이 객체를 메인 화면으로 전달한다.
    """

    # API 호출 성공 여부
    ok: bool

    # 성공 또는 실패에 대한 결과 메시지
    message: str

    # 조회된 공지 정보
    #
    # 공지가 없거나 조회에 실패하면 None
    notice: Optional[NoticeInfo] = None


class NoticeWorker(QThread):
    """
    긴급 공지 API를 별도 스레드에서 호출하는 작업 클래스.

    API 요청을 메인 UI 스레드에서 직접 실행하면
    서버 응답을 기다리는 동안 화면이 멈출 수 있다.

    QThread에서 API 요청을 실행하면
    메인 화면은 멈추지 않고 계속 동작한다.
    """

    # 작업 완료 시 결과를 전달하는 Qt 시그널이다.
    #
    # Signal(object):
    # Python 객체 하나를 전달할 수 있다는 의미다.
    #
    # 실제로 전달하는 객체:
    # NoticeResult
    #
    # LauncherWindow에서는 다음처럼 연결한다.
    #
    # notice_worker.sig_done.connect(
    #     self.on_notice_done
    # )
    #
    # 이후 sig_done.emit(result)가 실행되면
    # on_notice_done(result)가 호출된다.
    sig_done: Signal = Signal(object)

    def __init__(
            self,
            server_url: str,
            program_id: str,
    ) -> None:
        """
        긴급 공지 조회에 필요한 서버 주소와
        프로그램 ID를 전달받는다.
        """

        # QThread 초기화
        super().__init__()

        # Spring Boot API 서버 주소
        self.server_url = server_url

        # 공지를 조회할 프로그램 ID
        self.program_id = program_id

    def run(self) -> None:
        """
        QThread의 실제 작업을 수행한다.

        외부에서 다음 코드를 실행하면:

            worker.start()

        Qt가 별도 스레드를 생성한 뒤
        자동으로 이 run() 메서드를 호출한다.

        run()을 직접 호출하면 별도 스레드가 아니라
        현재 스레드에서 실행되므로 반드시 start()를 사용한다.
        """

        try:
            # 서버에서 최신 긴급 공지 1건을 조회한다.
            ok, message, notice = fetch_latest_notice(
                self.server_url,
                self.program_id,
            )

            # API 조회 결과를 NoticeResult 객체로 묶는다.
            result = NoticeResult(
                ok=ok,
                message=message,
                notice=notice,
            )

            # 작업 완료 결과를 메인 화면으로 전달한다.
            #
            # 이 시그널에 연결된 LauncherWindow의
            # on_notice_done(result)가 호출된다.
            self.sig_done.emit(result)

        except Exception as error:
            # 예상하지 못한 오류가 발생해도
            # 스레드에서 예외를 그대로 발생시키지 않는다.
            #
            # 실패 결과를 만들어 메인 화면에 전달한다.
            result = NoticeResult(
                ok=False,
                message=(
                    "unexpected error: "
                    f"{str(error)}"
                ),
                notice=None,
            )

            self.sig_done.emit(result)