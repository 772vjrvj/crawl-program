# launcher/launcher_main.py
from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from core.paths import get_paths, ensure_dirs
from ui.launcher_window import LauncherWindow


def main() -> int:
    paths = get_paths()
    ensure_dirs(paths)

    app = QApplication(sys.argv)

    w = LauncherWindow(paths=paths)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())