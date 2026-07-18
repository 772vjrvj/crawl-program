# launcher/core/downloader.py
from __future__ import annotations  # === 신규 ===

import hashlib
from pathlib import Path
from typing import Optional, Tuple, Callable

import requests


def download_file(
        url: str,
        dst_path: Path,
        timeout_sec: int = 60,
        progress_cb: Optional[Callable[[int, int], None]] = None,  # === 신규 === (written, total)
) -> Tuple[bool, str, int, Optional[str]]:
    """
    URL -> dst_path로 스트리밍 다운로드
    - dst_path는 파일 경로
    - 성공 시 (True, "ok", bytes_written, sha256)
    - 실패 시에도 다운로드된 bytes_written을 반환한다.
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dst_path.with_suffix(dst_path.suffix + ".part")
    headers = {"Accept": "*/*"}

    # 다운로드 실패 시에도 실제 받은 크기를 반환하기 위해
    # try 블록 밖에서 먼저 초기화한다.
    bytes_written = 0

    # 파일을 다시 읽지 않고 다운로드와 동시에
    # SHA-256 값을 계산한다.
    sha256 = hashlib.sha256()

    try:
        with requests.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True, stream=True) as res:
            if res.status_code != 200:
                return False, f"bad status: {res.status_code}", 0, None

            total = 0
            try:
                total = int((res.headers.get("Content-Length") or "0").strip() or "0")
            except Exception:
                total = 0

            with open(tmp_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 1024):  # 1MB
                    if not chunk:
                        continue

                    f.write(chunk)
                    bytes_written += len(chunk)

                    # 저장한 동일한 바이트로 SHA-256을 계산한다.
                    sha256.update(chunk)

                    if progress_cb is not None:
                        try:
                            progress_cb(bytes_written, total)
                        except Exception:
                            pass

        # 완료되면 원자적으로 rename
        if dst_path.exists():
            try:
                dst_path.unlink()
            except Exception:
                pass

        tmp_path.rename(dst_path)

        return (
            True,
            "ok",
            bytes_written,
            sha256.hexdigest(),
        )

    except Exception as e:
        # 실패 시 part 파일 정리
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass

        return (
            False,
            f"download failed: {str(e)}",
            bytes_written,
            None,
        )
