# launcher/core/paths.py
from __future__ import annotations  # === 신규 ===

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LauncherPaths:
    base_dir: Path
    data_dir: Path
    versions_dir: Path
    current_json: Path


def get_base_dir() -> Path:
    """
    행님 구조 기준:
    - 개발: crawl-program/launcher 가 base_dir
    - 운영(Python/PyInstaller): launcher.exe가 있는 폴더가 base_dir
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # .../crawl-program/launcher/core/paths.py -> 부모의 부모 = launcher/
    return Path(__file__).resolve().parents[1]


def get_paths() -> LauncherPaths:
    base = get_base_dir()
    data = base / "data"
    versions = base / "versions"
    current = data / "current.json"
    return LauncherPaths(
        base_dir=base,
        data_dir=data,
        versions_dir=versions,
        current_json=current,
    )


def ensure_dirs(p: LauncherPaths) -> None:
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p.versions_dir.mkdir(parents=True, exist_ok=True)