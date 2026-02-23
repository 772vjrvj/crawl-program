# launcher/core/versioning.py
from __future__ import annotations  # === 신규 ===

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int

    def to_tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def parse_semver(v: str) -> SemVer:
    """
    "1.0.0" -> SemVer(1,0,0)
    "v1.0.0"도 허용
    """
    s = (v or "").strip()
    if not s:
        raise ValueError("version is empty")

    if s.startswith(("v", "V")):
        s = s[1:].strip()

    parts = s.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semver (expected x.y.z): {v}")

    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except Exception:
        raise ValueError(f"invalid semver (not int): {v}")

    if major < 0 or minor < 0 or patch < 0:
        raise ValueError(f"invalid semver (negative): {v}")

    return SemVer(major, minor, patch)


def compare_versions(local_v: str, server_v: str) -> int:
    """
    return:
      -1 => local < server (update needed)
       0 => same
      +1 => local > server (downgrade situation)
    """
    l = parse_semver(local_v).to_tuple()
    s = parse_semver(server_v).to_tuple()
    if l < s:
        return -1
    if l > s:
        return 1
    return 0