# launcher/core/runner.py
from __future__ import annotations  # === 신규 ===

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def run_exe(exe_path: Path, workdir: Optional[Path] = None, wait: bool = False) -> Tuple[bool, str, Optional[int]]:
    """
    exe 실행
    - wait=False: 런처는 바로 반환(보통 이게 정석)
    - wait=True: exe 종료코드까지 대기(디버그용)
    """
    if not exe_path.exists():
        return False, f"exe not found: {exe_path}", None

    cwd = str(workdir) if workdir is not None else str(exe_path.parent)

    try:
        # Windows에서 새 프로세스로 독립 실행 (런처 종료해도 프로그램 유지)
        p = subprocess.Popen(
            [str(exe_path)],
            cwd=cwd,
            close_fds=True,
        )

        if wait:
            code = p.wait()
            return True, "ok(wait)", code

        return True, "ok", None

    except Exception as e:
        return False, f"run failed: {str(e)}", None