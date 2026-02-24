# launcher/workers/update_worker.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QThread, Signal

from launcher.core.api import fetch_latest
from launcher.core.downloader import probe_url, download_file
from launcher.core.installer import unzip_to_staging, promote_staging, cleanup_paths
from launcher.core.paths import LauncherPaths
from launcher.core.runner import run_exe
from launcher.core.state import read_current_state, write_current_state, version_to_dirname, CurrentState
from launcher.core.versioning import compare_versions


@dataclass
class UpdateResult:
    ok: bool
    message: str
    exe_path: Optional[Path] = None
    did_run: bool = False

    update_available: bool = False
    latest_version: Optional[str] = None
    asset_url: Optional[str] = None

    def try_run(self, wait: bool = False) -> Tuple[bool, str]:
        if not self.exe_path:
            return False, "exe_path is empty"
        ok, msg, _code = run_exe(self.exe_path, wait=wait)
        return ok, msg


def _find_exe(root: Path, exe_name: str) -> Optional[Path]:
    for p in root.rglob(exe_name):
        if p.is_file():
            return p
    return None


class UpdateWorker(QThread):
    sig_status: Signal = Signal(str)
    sig_log: Signal = Signal(str)
    sig_progress: Signal = Signal(int)
    sig_done: Signal = Signal(object)  # UpdateResult

    def __init__(self, paths: LauncherPaths, auto_update: bool = True) -> None:  # === 신규 ===
        super().__init__()
        self.paths = paths
        self.auto_update = auto_update  # === 신규 ===

    def _status(self, s: str) -> None:
        self.sig_status.emit(s)

    def _log(self, s: str) -> None:
        self.sig_log.emit(s)

    def _progress(self, p: int) -> None:
        self.sig_progress.emit(max(0, min(100, p)))

    def run(self) -> None:
        try:
            result = self._run_impl()
        except Exception as e:
            result = UpdateResult(False, f"unexpected error: {str(e)}", None, False)
        self.sig_done.emit(result)

    def _run_impl(self) -> UpdateResult:
        self._progress(0)
        self._status("current.json 읽는 중…")

        st = read_current_state(self.paths.current_json)
        self._log(f"[launcher] program_id={st.program_id}")
        self._log(f"[launcher] local_version={st.version}")
        self._log(f"[launcher] server_url={st.server_url}")

        self._status("최신 버전 조회 중…")
        ok, msg, latest = fetch_latest(st.server_url, st.program_id)
        self._log(f"[launcher] fetch_latest.ok={ok}")
        self._log(f"[launcher] fetch_latest.msg={msg}")

        if not ok or latest is None:
            return UpdateResult(False, f"fetch_latest failed: {msg}")

        self._log(f"[launcher] latest_version={latest.latest_version}")
        self._log(f"[launcher] asset_url={latest.asset_url}")

        cmpv = compare_versions(st.version, latest.latest_version)

        # 서버가 더 오래됨 => 그냥 exe 경로만 반환
        if cmpv > 0:
            self._log(f"[launcher] server older than local (skip): local={st.version} server={latest.latest_version}")
            exe = self._resolve_latest_exe_from_state(st)
            if exe is None:
                return UpdateResult(False, "latest exe not found", None, False)
            return UpdateResult(True, "ok(local newer)", exe, False)

        # 최신 동일 => exe 경로만 반환
        if cmpv == 0:
            self._log(f"[launcher] up-to-date: {st.version}")
            exe = self._resolve_latest_exe_from_state(st)
            if exe is None:
                return UpdateResult(False, "latest exe not found", None, False)
            return UpdateResult(True, "ok(up-to-date)", exe, False)


        # 업데이트 필요 & auto_update=False => 업데이트 가능 정보만 반환(기존 유지)
        exe_local = self._resolve_latest_exe_from_state(st)

        if not self.auto_update:
            return UpdateResult(
                True,
                "update available",
                exe_path=exe_local,
                did_run=False,
                update_available=True,
                latest_version=latest.latest_version,
                asset_url=latest.asset_url,
            )

        # 아래부터는 실제 업데이트 수행
        if latest.asset_url is None:
            return UpdateResult(False, "asset_url is empty", exe_local, False)

        self._status("다운로드 준비(HEAD/GET) 확인 중…")
        ok2, msg2, hdrs = probe_url(latest.asset_url)
        self._log(f"[launcher] probe.ok={ok2}")
        self._log(f"[launcher] probe.msg={msg2}")

        self._status("다운로드 중…")
        downloads_dir = self.paths.base_dir / "downloads_tmp"
        zip_path = downloads_dir / f"{st.program_id}_{latest.latest_version}.zip"

        def on_dl_progress(written: int, total: int) -> None:
            if total > 0:
                pct = int((written / total) * 80)
                self._progress(pct)

        ok3, msg3, nbytes = download_file(latest.asset_url, zip_path, progress_cb=on_dl_progress)
        self._log(f"[launcher] download.ok={ok3}")
        self._log(f"[launcher] download.msg={msg3}")
        self._log(f"[launcher] download.path={zip_path}")
        self._log(f"[launcher] download.bytes={nbytes}")

        if not ok3:
            return UpdateResult(False, f"download failed: {msg3}", exe_local, False)

        self._status("압축 해제 중…")
        self._progress(85)

        dir_name = version_to_dirname(latest.latest_version)
        staging_dir = self.paths.versions_dir / "_staging" / st.program_id / dir_name

        ok4, msg4 = unzip_to_staging(zip_path, staging_dir)
        self._log(f"[launcher] unzip.ok={ok4}")
        self._log(f"[launcher] unzip.msg={msg4}")
        self._log(f"[launcher] unzip.dir={staging_dir}")

        if not ok4:
            return UpdateResult(False, f"unzip failed: {msg4}", exe_local, False)

        exe_name = "CrawlProgram.exe"
        found_exe = _find_exe(staging_dir, exe_name)
        self._log(f"[launcher] exe_found={found_exe}")

        if found_exe is None:
            return UpdateResult(False, f"exe not found in zip: {exe_name}", exe_local, False)

        self._status("설치 반영 중…")
        self._progress(92)

        target_dir = self.paths.versions_dir / dir_name
        ok5, msg5 = promote_staging(staging_dir, target_dir)
        self._log(f"[launcher] promote.ok={ok5}")
        self._log(f"[launcher] promote.msg={msg5}")
        self._log(f"[launcher] promote.target_dir={target_dir}")

        if not ok5:
            return UpdateResult(False, f"promote failed: {msg5}", exe_local, False)

        self._status("버전 정보 저장 중…")
        self._progress(96)

        new_state = CurrentState(
            program_id=st.program_id,
            version=latest.latest_version,
            server_url=st.server_url,
        )
        write_current_state(self.paths.current_json, new_state)
        self._log(f"[launcher] current.json updated: version={latest.latest_version}")

        self._status("정리 중…")
        self._progress(98)
        cleanup_paths(zip_path)
        cleanup_paths(self.paths.base_dir / "downloads_tmp")
        cleanup_paths(self.paths.versions_dir / "_staging")
        self._log("[launcher] cleanup done")

        self._progress(100)
        exe2 = _find_exe(target_dir, exe_name)

        if exe2 is None:
            return UpdateResult(False, "installed but exe not found", exe_local, False)

        return UpdateResult(True, "ok(installed)", exe2, False)

    def _resolve_latest_exe_from_state(self, st: CurrentState) -> Optional[Path]:
        dir_name = version_to_dirname(st.version)
        root = self.paths.versions_dir / dir_name
        return _find_exe(root, "CrawlProgram.exe")


    def _run_latest(self, exe_path: Optional[Path]) -> UpdateResult:
        if exe_path is None:
            return UpdateResult(False, "latest exe not found", None, False)

        self._status("프로그램 실행 중…")
        ok_run, msg_run, _code = run_exe(exe_path, wait=False)
        self._log(f"[launcher] run.ok={ok_run}")
        self._log(f"[launcher] run.msg={msg_run}")

        if not ok_run:
            return UpdateResult(False, f"run failed: {msg_run}", exe_path, False)

        return UpdateResult(True, "ok", exe_path, True)