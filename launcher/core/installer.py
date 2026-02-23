# launcher/core/installer.py
from __future__ import annotations  # === 신규 ===

import shutil
import zipfile
from pathlib import Path
from typing import Tuple


def unzip_to_staging(zip_path: Path, staging_dir: Path) -> Tuple[bool, str]:
    if not zip_path.exists():
        return False, f"zip not found: {zip_path}"

    try:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(staging_dir)

        return True, "ok"
    except Exception as e:
        return False, f"unzip failed: {str(e)}"


def promote_staging(staging_dir: Path, target_dir: Path) -> Tuple[bool, str]:
    """
    staging_dir -> target_dir 로 원자적 교체(가능하면 rename)
    - target_dir 있으면 백업으로 밀어두고 교체
    """
    if not staging_dir.exists():
        return False, f"staging not found: {staging_dir}"

    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)

        backup_dir = target_dir.with_name(target_dir.name + "__bak")

        # 기존 백업 정리
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        # 기존 target 있으면 bak로 이동
        if target_dir.exists():
            target_dir.rename(backup_dir)

        # staging을 target으로 이동 (동일 드라이브면 rename이 매우 빠르고 안전)
        staging_dir.rename(target_dir)

        # 성공하면 backup 제거
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        return True, "ok"

    except Exception as e:
        return False, f"promote failed: {str(e)}"


def cleanup_paths(*targets: Path) -> None:
    """
    임시 파일/폴더 정리용. 실패해도 런처 흐름을 깨지 않도록 조용히 처리.
    """
    for p in targets:
        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass