# tools/print_tree.py
from __future__ import annotations

import argparse
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence, Set, List


@dataclass(frozen=True)
class TreeConfig:
    max_depth: int = 4
    # ✅ json / md 추가
    include_exts: Set[str] = field(default_factory=lambda: {
        ".py", ".bat", ".log", ".exe", ".json", ".md"
    })
    exclude_dirs: Set[str] = field(default_factory=lambda: {
        ".idea", "build", "image", "test", "seleniumwire", "__pycache__",
        ".git", ".venv", "venv", "dist"
    })
    exclude_files: Set[str] = field(default_factory=lambda: {".env", "main.spec"})
    exclude_patterns: List[str] = field(default_factory=lambda: ["*.txt"])
    show_hidden: bool = False


def _is_hidden(p: Path) -> bool:
    return p.name.startswith(".")


def is_excluded(p: Path, cfg: TreeConfig) -> bool:
    name = p.name

    if not cfg.show_hidden and _is_hidden(p):
        return True

    if p.is_dir() and name in cfg.exclude_dirs:
        return True

    if p.is_file() and name in cfg.exclude_files:
        return True

    for pattern in cfg.exclude_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True

    return False


def _iter_children(dir_path: Path, cfg: TreeConfig) -> tuple[list[Path], list[Path]]:
    folders: list[Path] = []
    files: list[Path] = []

    try:
        entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return folders, files

    for p in entries:
        if is_excluded(p, cfg):
            continue

        if p.is_dir():
            folders.append(p)
        elif p.is_file():
            if p.suffix.lower() in cfg.include_exts:
                files.append(p)

    return folders, files


def print_dir_tree(root: Path, cfg: TreeConfig) -> None:
    root = root.resolve()
    print(f"{root.name}/")

    def walk(current: Path, depth: int, prefix: str) -> None:
        if depth >= cfg.max_depth:
            return

        folders, files = _iter_children(current, cfg)
        items: list[tuple[Path, bool]] = [(p, True) for p in folders] + [(p, False) for p in files]

        for idx, (p, is_dir) in enumerate(items):
            last = (idx == len(items) - 1)
            branch = "└─ " if last else "├─ "
            next_prefix = prefix + ("   " if last else "│  ")

            if is_dir:
                print(f"{prefix}{branch}{p.name}/")
                walk(p, depth + 1, next_prefix)
            else:
                print(f"{prefix}{branch}{p.name}")

    walk(root, depth=0, prefix="")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print project tree with filters.")
    parser.add_argument("--root", default=".", help="Root directory (default: current dir)")
    parser.add_argument("--depth", type=int, default=4, help="Max depth (default: 4)")
    parser.add_argument(
        "--include",
        nargs="*",
        # ✅ json / md 추가
        default=[".py", ".js", ".ts", ".bat", ".log", ".exe", ".json", ".md"],
        help="Include file extensions (e.g. .py .js .ts .json .md).",
    )
    parser.add_argument("--show-hidden", action="store_true", help="Show dotfiles and dotfolders")
    parser.add_argument("--exclude-dir", nargs="*", default=None, help="Extra exclude dir names")
    parser.add_argument("--exclude-file", nargs="*", default=None, help="Extra exclude file names")
    parser.add_argument("--exclude-pattern", nargs="*", default=None, help="Extra exclude patterns (glob)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    cfg = TreeConfig(
        max_depth=int(args.depth),
        include_exts={
            (str(x).lower() if str(x).startswith(".") else f".{str(x).lower()}")
            for x in args.include
        },
        show_hidden=bool(args.show_hidden),
    )

    if args.exclude_dir:
        object.__setattr__(cfg, "exclude_dirs", set(cfg.exclude_dirs) | set(args.exclude_dir))  # type: ignore[misc]
    if args.exclude_file:
        object.__setattr__(cfg, "exclude_files", set(cfg.exclude_files) | set(args.exclude_file))  # type: ignore[misc]
    if args.exclude_pattern:
        object.__setattr__(cfg, "exclude_patterns", list(cfg.exclude_patterns) + list(args.exclude_pattern))  # type: ignore[misc]

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"❌ invalid root: {root}")
        return 1

    print_dir_tree(root, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# python tools/tree/print_tree.py --include .py .js .ts .json .md --depth 6