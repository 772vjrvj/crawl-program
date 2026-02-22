# main.py
from __future__ import annotations

import json  # === 신규 ===
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QLockFile, QDir  # === 신규 ===
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
    - 개발: 프로젝트 기준
    - 빌드(frozen): exe 위치 기준. 개발 main.py 기준
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# =========================================================
# config helpers  # === 신규 ===
# =========================================================
def _read_runtime_app_json(base_path: Path) -> dict:
    """
    runtime/app.json을 원문(JSON)으로 읽어와 설정 분기용으로 사용.
    - AppConfigLoader/모델 구조에 의존하지 않기 위해 별도 구현.
    """
    runtime_dir = base_path / "runtime"
    app_json_path = runtime_dir / "app.json"

    if not app_json_path.exists():
        raise FileNotFoundError(f"runtime/app.json not found: {str(app_json_path)}")

    try:
        raw = app_json_path.read_text(encoding="utf-8")
    except Exception:
        # utf-8-sig(메모장 BOM) 케이스 대응
        raw = app_json_path.read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"runtime/app.json JSON 파싱 실패: {str(e)}")

    if not isinstance(data, dict):
        raise ValueError("runtime/app.json 최상위 구조는 object(dict)여야 합니다.")
    return data


def _get_allow_multi_instance(runtime_json: dict) -> bool:
    """
    allow_multi_instance:
      - true  => 중복 실행 허용(락 사용 안 함)
      - false => 중복 실행 차단(락 사용)
    기본값은 false(보수적으로 단일 인스턴스)
    """
    v = runtime_json.get("allow_multi_instance", False)
    return bool(v)


def _get_single_instance_key(runtime_json: dict) -> str:
    """
    앱별로 락 파일 키를 분리하고 싶을 때 사용.
    app.json에 instance_key를 두면 그걸 사용.
    기본값은 my_pyside_app
    """
    v = runtime_json.get("instance_key", "my_pyside_app")
    v = str(v).strip()
    return v or "my_pyside_app"


# =========================================================
# single instance guard  # === 신규 ===
# =========================================================
_SINGLE_INSTANCE_LOCK: Optional[QLockFile] = None  # === 신규 ===


def _acquire_single_instance_lock(app: QApplication, lock_key: str) -> bool:  # === 신규 ===
    """
    QLockFile 기반 단일 인스턴스 가드.
    - 이미 실행 중이면 경고창 후 False 반환
    - 성공 시 프로세스 생존 동안 락 유지
    """
    global _SINGLE_INSTANCE_LOCK

    # 잠금 파일은 임시 폴더에 두는 게 권장(권한/경로 이슈 최소화)
    base_dir = Path(QDir.tempPath()) / lock_key
    base_dir.mkdir(parents=True, exist_ok=True)

    lock_path = base_dir / f"{lock_key}.lock"
    lock = QLockFile(str(lock_path))

    # 크래시 후 stale lock(남은 락) 자동 정리용
    lock.setStaleLockTime(10_000)  # 10초

    # 즉시 락 시도(대기 0ms)
    if not lock.tryLock(0):
        show_already_running_alert(app)
        return False

    _SINGLE_INSTANCE_LOCK = lock
    return True


def _release_single_instance_lock() -> None:  # === 신규 ===
    global _SINGLE_INSTANCE_LOCK
    lock = _SINGLE_INSTANCE_LOCK
    _SINGLE_INSTANCE_LOCK = None
    if lock is None:
        return
    try:
        lock.unlock()
    except Exception:
        pass


def _bootstrap_runtime_config(state: GlobalState) -> None:
    base = _get_base_path()
    runtime_dir = base / "runtime"
    app_json_path = runtime_dir / "app.json"

    loader = AppConfigLoader(str(app_json_path))

    app_conf = loader.load_app_config()
    set_app_server_config(app_conf.server_url, app_conf.server_name)

    site_configs = loader.get_enabled_site_configs(app_conf)

    state.set(
        GlobalState.APP_CONFIG,
        {
            "site_list_use": app_conf.site_list_use,
            "runtime_dir": str(runtime_dir),
        },
    )
    state.set(GlobalState.SITE_CONFIGS, site_configs)

    site_configs_by_key = {}
    for d in (site_configs or []):
        k = str(d.get("key") or "").strip()
        if k:
            site_configs_by_key[k] = d
    state.set("site_configs_by_key", site_configs_by_key)


def main() -> int:
    app = QApplication(sys.argv)

    # =========================================================
    # === 신규 === app.json 설정에 따라 중복 실행 허용/차단
    # =========================================================
    base = _get_base_path()
    try:
        runtime_json = _read_runtime_app_json(base)
        allow_multi = _get_allow_multi_instance(runtime_json)
        lock_key = _get_single_instance_key(runtime_json)
    except Exception as e:
        # 설정 읽기 실패는 사용자에게 보여주고 종료(중요 설정이니까)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("설정 로드 실패")
        msg.setText(f"runtime/app.json을 읽는 중 오류가 발생했습니다.\n\n{str(e)}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        msg.exec()
        return 1

    # allow_multi_instance가 false면 단일 인스턴스 강제
    if not allow_multi:
        if not _acquire_single_instance_lock(app, lock_key):
            return 0

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
        _release_single_instance_lock()  # === 신규 ===
        return 1

    manager = AppManager(app)
    manager.start()

    rc = app.exec()

    _release_single_instance_lock()  # === 신규 ===
    return rc


if __name__ == "__main__":
    raise SystemExit(main())