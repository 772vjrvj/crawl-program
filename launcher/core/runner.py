# launcher/core/runner.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def run_exe(
        exe_path: Path,
        workdir: Optional[Path] = None,
        wait: bool = False,
) -> Tuple[bool, str, Optional[int]]:
    """
    지정한 EXE 파일을 새로운 프로세스로 실행한다.

    Args:
        exe_path:
            실행할 EXE 파일의 전체 경로

        workdir:
            실행 프로그램이 사용할 작업 폴더

            값이 있으면:
                전달받은 workdir을 사용한다.

            값이 없으면:
                EXE 파일이 들어 있는 폴더를 사용한다.

        wait:
            실행한 프로그램이 종료될 때까지
            런처가 기다릴지 여부

            False:
                프로그램만 실행하고 즉시 반환한다.
                일반적인 런처 실행 방식이다.

            True:
                프로그램이 종료될 때까지 기다린 뒤
                종료 코드를 반환한다.
                디버깅이나 테스트 용도로 사용할 수 있다.

    Returns:
        성공 여부, 결과 메시지, 종료 코드 튜플

        성공 + wait=False:
            (True, "ok", None)

        성공 + wait=True:
            (True, "ok(wait)", 종료 코드)

        실패:
            (False, 오류 메시지, None)
    """

    # 실행하려는 EXE 파일이 실제로 존재하는지 확인한다.
    #
    # 파일이 없으면 subprocess를 실행하지 않고
    # 즉시 실패 결과를 반환한다.
    if not exe_path.exists():
        return (
            False,
            f"exe not found: {exe_path}",
            None,
        )

    # 실행 프로그램의 작업 폴더를 결정한다.
    #
    # workdir이 전달된 경우:
    #     해당 경로를 작업 폴더로 사용
    #
    # workdir이 None인 경우:
    #     EXE 파일이 있는 폴더를 작업 폴더로 사용
    #
    # 예:
    # exe_path =
    # E:\\GB7Launcher\\versions\\v1_0_2\\CrawlProgram.exe
    #
    # workdir이 없으면 cwd는:
    # E:\\GB7Launcher\\versions\\v1_0_2
    cwd = (
        str(workdir)
        if workdir is not None
        else str(exe_path.parent)
    )

    try:
        # 새로운 프로세스로 EXE 파일을 실행한다.
        #
        # subprocess.Popen():
        # 프로그램 실행을 시작한 뒤
        # 기본적으로 실행 완료를 기다리지 않고 바로 반환한다.
        #
        # [str(exe_path)]:
        # 실행할 명령어 목록이다.
        #
        # cwd=cwd:
        # 실행 프로그램이 기준으로 사용할 작업 폴더다.
        #
        # close_fds=True:
        # 런처가 사용 중인 불필요한 파일 핸들을
        # 새 프로그램이 그대로 상속하지 않도록 한다.
        #
        # 따라서 런처가 종료되더라도
        # 실행한 프로그램은 독립적으로 계속 실행할 수 있다.
        process = subprocess.Popen(
            [str(exe_path)],
            cwd=cwd,
            close_fds=True,
        )

        # wait=True이면 실행한 프로그램이 종료될 때까지 기다린다.
        if wait:
            # 프로그램이 종료되면 종료 코드를 반환한다.
            #
            # 일반적으로:
            # 0      → 정상 종료
            # 0 이외 → 프로그램별 오류 종료
            exit_code = process.wait()

            return (
                True,
                "ok(wait)",
                exit_code,
            )

        # wait=False이면 프로그램 실행 시작만 확인하고
        # 종료를 기다리지 않은 채 바로 성공 결과를 반환한다.
        #
        # 런처에서는 일반적으로 이 방식을 사용한다.
        return (
            True,
            "ok",
            None,
        )

    except Exception as error:
        # EXE 실행 중 발생한 예외를 실패 결과로 반환한다.
        #
        # 예:
        # - 실행 권한 부족
        # - 잘못된 실행 파일
        # - 작업 폴더 접근 실패
        # - 운영체제 프로세스 생성 실패
        return (
            False,
            f"run failed: {str(error)}",
            None,
        )