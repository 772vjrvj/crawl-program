# launcher/workers/update_worker.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Callable

from PySide6.QtCore import QThread, Signal

from core.api import fetch_latest
from core.downloader import probe_url, download_file
from core.installer import unzip_to_staging, promote_staging, cleanup_paths
from core.paths import LauncherPaths
from core.runner import run_exe
from core.state import read_current_state, write_current_state, version_to_dirname, CurrentState
from core.versioning import compare_versions


@dataclass
class UpdateResult:
    ok: bool
    message: str
    exe_path: Optional[Path] = None
    did_run: bool = False

    def try_run(self, wait: bool = False) -> Tuple[bool, str]:
        if not self.exe_path:
            return False, "exe_path is empty"
        ok, msg, _code = run_exe(self.exe_path, wait=wait)
        return ok, msg


def _find_exe(root: Path, exe_name: str) -> Optional[Path]:
    # zip 구조가 한 겹 더 들어가도 대응
    for p in root.rglob(exe_name):
        if p.is_file():
            return p
    return None


class UpdateWorker(QThread):
    sig_status: Signal = Signal(str)
    sig_log: Signal = Signal(str)
    sig_progress: Signal = Signal(int)
    sig_done: Signal = Signal(object)  # UpdateResult

    def __init__(self, paths: LauncherPaths) -> None:
        super().__init__()
        self.paths = paths

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

        # 서버가 더 오래됨 => 그대로 실행
        if cmpv > 0:
            self._log(f"[launcher] server older than local (skip): local={st.version} server={latest.latest_version}")
            exe = self._resolve_latest_exe_from_state(st)
            return self._run_latest(exe)

        # 최신 동일 => 그대로 실행
        if cmpv == 0:
            self._log(f"[launcher] up-to-date: {st.version}")
            exe = self._resolve_latest_exe_from_state(st)
            return self._run_latest(exe)

        # 업데이트 필요
        if latest.asset_url is None:
            return UpdateResult(False, "asset_url is empty")

        self._status("다운로드 준비(HEAD/GET) 확인 중…")
        ok2, msg2, hdrs = probe_url(latest.asset_url)
        self._log(f"[launcher] probe.ok={ok2}")
        self._log(f"[launcher] probe.msg={msg2}")

        # 다운로드
        self._status("다운로드 중…")
        downloads_dir = self.paths.base_dir / "downloads_tmp"
        zip_path = downloads_dir / f"{st.program_id}_{latest.latest_version}.zip"

        def on_dl_progress(written: int, total: int) -> None:
            if total > 0:
                pct = int((written / total) * 80)  # 다운로드는 0~80%
                self._progress(pct)

        ok3, msg3, nbytes = download_file(latest.asset_url, zip_path, progress_cb=on_dl_progress)
        self._log(f"[launcher] download.ok={ok3}")
        self._log(f"[launcher] download.msg={msg3}")
        self._log(f"[launcher] download.path={zip_path}")
        self._log(f"[launcher] download.bytes={nbytes}")

        if not ok3:
            return UpdateResult(False, f"download failed: {msg3}")

        # unzip
        self._status("압축 해제 중…")
        self._progress(85)

        dir_name = version_to_dirname(latest.latest_version)  # v1_0_1
        staging_dir = self.paths.versions_dir / "_staging" / st.program_id / dir_name

        ok4, msg4 = unzip_to_staging(zip_path, staging_dir)
        self._log(f"[launcher] unzip.ok={ok4}")
        self._log(f"[launcher] unzip.msg={msg4}")
        self._log(f"[launcher] unzip.dir={staging_dir}")

        if not ok4:
            return UpdateResult(False, f"unzip failed: {msg4}")

        # exe 찾기
        exe_name = "CrawlProgram.exe"
        found_exe = _find_exe(staging_dir, exe_name)
        self._log(f"[launcher] exe_found={found_exe}")

        if found_exe is None:
            return UpdateResult(False, f"exe not found in zip: {exe_name}")

        # promote
        self._status("설치 반영 중…")
        self._progress(92)

        target_dir = self.paths.versions_dir / dir_name
        ok5, msg5 = promote_staging(staging_dir, target_dir)
        self._log(f"[launcher] promote.ok={ok5}")
        self._log(f"[launcher] promote.msg={msg5}")
        self._log(f"[launcher] promote.target_dir={target_dir}")

        if not ok5:
            return UpdateResult(False, f"promote failed: {msg5}")

        # current.json 갱신
        self._status("버전 정보 저장 중…")
        self._progress(96)

        new_state = CurrentState(
            program_id=st.program_id,
            version=latest.latest_version,
            server_url=st.server_url,
        )
        write_current_state(self.paths.current_json, new_state)
        self._log(f"[launcher] current.json updated: version={latest.latest_version}")

        # cleanup
        self._status("정리 중…")
        self._progress(98)
        cleanup_paths(zip_path)
        cleanup_paths(self.paths.base_dir / "downloads_tmp")
        cleanup_paths(self.paths.versions_dir / "_staging")
        self._log("[launcher] cleanup done")

        # 실행
        self._progress(100)
        exe2 = _find_exe(target_dir, exe_name)
        return self._run_latest(exe2)

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