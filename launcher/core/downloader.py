# launcher/core/downloader.py
from __future__ import annotations  # === 신규 ===

from pathlib import Path
from typing import Dict, Optional, Tuple, Callable

import requests


def probe_url(url: str, timeout_sec: int = 15) -> Tuple[bool, str, Optional[Dict[str, str]]]:
    headers = {"Accept": "*/*"}

    try:
        res = requests.head(url, headers=headers, timeout=timeout_sec, allow_redirects=True)
        if res.status_code == 200:
            return True, "ok(head)", dict(res.headers)
    except Exception:
        pass

    try:
        res2 = requests.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True, stream=True)
        if res2.status_code != 200:
            return False, f"bad status(get): {res2.status_code}", None
        res2.close()
        return True, "ok(get)", dict(res2.headers)
    except Exception as e:
        return False, f"request failed: {str(e)}", None


def download_file(
        url: str,
        dst_path: Path,
        timeout_sec: int = 60,
        progress_cb: Optional[Callable[[int, int], None]] = None,  # === 신규 === (written, total)
) -> Tuple[bool, str, int]:
    """
    URL -> dst_path로 스트리밍 다운로드
    - dst_path는 파일 경로
    - 성공 시 (True, "ok", bytes_written)
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dst_path.with_suffix(dst_path.suffix + ".part")
    headers = {"Accept": "*/*"}

    try:
        with requests.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True, stream=True) as res:
            if res.status_code != 200:
                return False, f"bad status: {res.status_code}", 0

            total = 0
            try:
                total = int((res.headers.get("Content-Length") or "0").strip() or "0")
            except Exception:
                total = 0

            bytes_written = 0
            with open(tmp_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 1024):  # 1MB
                    if not chunk:
                        continue
                    f.write(chunk)
                    bytes_written += len(chunk)

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
        return True, "ok", bytes_written

    except Exception as e:
        # 실패 시 part 파일 정리
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False, f"download failed: {str(e)}", 0