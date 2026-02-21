# main.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_manager import AppManager
from src.core.global_state import GlobalState
from src.utils.app_config_loader import AppConfigLoader
from src.utils.config import set_app_server_config


def show_already_running_alert(existing_app: Optional[QApplication] = None) -> None:
    app_created = False
    app = existing_app or QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app_created = True

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle("이미 실행 중")
    msg.setText("프로그램이 이미 실행 중입니다.\n기존 실행 중인 창을 확인해 주세요.")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    msg.exec()

    if app_created:
        try:
            app.exit(0)
        except Exception:
            pass


# =========================================================
# runtime path helpers
# =========================================================
def _get_base_path() -> Path:
    """
    === 신규 ===
    - 개발: 프로젝트 기준
    - 빌드(frozen): exe 위치 기준
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bootstrap_runtime_config(state: GlobalState) -> None:
    base = _get_base_path()
    runtime_dir = base / "runtime"
    app_json_path = runtime_dir / "app.json"

    loader = AppConfigLoader(str(app_json_path))

    app_conf = loader.load_app_config()
    set_app_server_config(app_conf.server_url, app_conf.server_name)

    site_configs = loader.get_enabled_site_configs()

    # 4) GlobalState 저장
    state.set(
        GlobalState.APP_CONFIG,   # 네가 상수화 했으면 이걸로
        {
            "server_url": app_conf.server_url,
            "server_name": app_conf.server_name,
            "site_list_use": app_conf.site_list_use,
            "runtime_dir": str(runtime_dir),
        },
    )
    state.set(GlobalState.SITE_CONFIGS, site_configs)

    # === 신규(선택) === key → config dict 맵도 저장(빠른 조회용)
    site_configs_by_key = {}
    for d in (site_configs or []):
        k = str(d.get("key") or "").strip()
        if k:
            site_configs_by_key[k] = d
    state.set("site_configs_by_key", site_configs_by_key)


def main() -> int:
    app = QApplication(sys.argv)

    state = GlobalState()
    state.initialize()

    try:
        _bootstrap_runtime_config(state)
    except Exception as e:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("설정 로드 실패")
        msg.setText(f"runtime 설정을 읽는 중 오류가 발생했습니다.\n\n{str(e)}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        msg.exec()
        return 1

    manager = AppManager(app)
    manager.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())