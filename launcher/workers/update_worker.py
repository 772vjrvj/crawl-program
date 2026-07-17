from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QThread, Signal

from launcher.core.api import fetch_latest
from launcher.core.downloader import download_file
from launcher.core.installer import (
    unzip_to_staging,
    promote_staging,
    cleanup_paths,
)
from launcher.core.paths import LauncherPaths
from launcher.core.runner import run_exe
from launcher.core.state import (
    read_current_state,
    write_current_state,
    version_to_dirname,
    CurrentState,
)
from launcher.core.versioning import (
    compare_versions,
    parse_semver,
)


@dataclass
class UpdateResult:
    ok: bool
    message: str
    exe_path: Optional[Path] = None
    did_run: bool = False

    # 새 버전이 있지만 아직 설치하지 않은 상태
    update_available: bool = False

    # 새 버전을 정상적으로 설치한 상태
    # LauncherWindow는 이 값이 True이면 프로그램을 자동 실행한다.
    update_installed: bool = False

    latest_version: Optional[str] = None
    asset_url: Optional[str] = None

    def try_run(
            self,
            wait: bool = False,
    ) -> Tuple[bool, str]:
        if not self.exe_path:
            return False, "exe_path is empty"

        ok, msg, _code = run_exe(
            self.exe_path,
            wait=wait,
        )
        return ok, msg


def _find_exe(
        root: Path,
        exe_name: str,
) -> Optional[Path]:
    """지정한 폴더 아래에서 실행 파일을 찾는다."""
    if not root.exists():
        return None

    for path in root.rglob(exe_name):
        if path.is_file():
            return path

    return None


def _version_dir_to_tuple(
        directory_name: str,
) -> Optional[Tuple[int, int, int]]:
    """
    버전 폴더명을 비교 가능한 숫자 튜플로 변환한다.

    예:
    v1_0_2 -> (1, 0, 2)

    버전 폴더가 아닌 이름은 None을 반환한다.
    따라서 _staging 같은 시스템 폴더는 정리 대상에서 제외된다.
    """
    try:
        version_text = directory_name.replace("_", ".")
        return parse_semver(version_text).to_tuple()
    except (TypeError, ValueError):
        return None


class UpdateWorker(QThread):
    sig_status: Signal = Signal(str)
    sig_log: Signal = Signal(str)
    sig_progress: Signal = Signal(int)
    sig_done: Signal = Signal(object)  # UpdateResult

    # 현재 버전과 직전 설치 버전만 보관한다.
    KEEP_VERSION_COUNT = 2

    def __init__(
            self,
            paths: LauncherPaths,
            auto_update: bool = True,
    ) -> None:
        super().__init__()

        self.paths = paths
        self.auto_update = auto_update

    def _status(self, message: str) -> None:
        self.sig_status.emit(message)

    def _log(self, message: str) -> None:
        self.sig_log.emit(message)

    def _progress(self, percent: int) -> None:
        self.sig_progress.emit(
            max(0, min(100, percent))
        )

    def run(self) -> None:
        try:
            result = self._run_impl()
        except Exception as error:
            result = UpdateResult(
                ok=False,
                message=(
                    "unexpected error: "
                    f"{str(error)}"
                ),
            )

        self.sig_done.emit(result)

    def _run_impl(self) -> UpdateResult:
        self._progress(0)
        self._status("current.json 읽는 중…")

        state = read_current_state(
            self.paths.current_json
        )

        self._log(
            f"[launcher] program_id={state.program_id}"
        )
        self._log(
            f"[launcher] local_version={state.version}"
        )
        self._log(
            f"[launcher] server_url={state.server_url}"
        )

        # 업데이트 조회나 다운로드에 실패해도
        # 기존 버전을 직접 실행할 수 있도록 미리 찾는다.
        exe_local = self._resolve_latest_exe_from_state(
            state
        )

        self._status("최신 버전 조회 중…")

        ok, message, latest = fetch_latest(
            state.server_url,
            state.program_id,
            state.launcher_key
        )

        self._log(
            f"[launcher] fetch_latest.ok={ok}"
        )
        self._log(
            f"[launcher] fetch_latest.msg={message}"
        )

        if not ok or latest is None:
            return UpdateResult(
                ok=False,
                message=(
                    "fetch_latest failed: "
                    f"{message}"
                ),
                exe_path=exe_local,
            )

        self._log(
            "[launcher] latest_version="
            f"{latest.latest_version}"
        )

        # ============================================================
        # 실제 ZIP 다운로드 URL
        #
        # 런처에서 URL을 만들지 않는다.
        # 서버 최신 버전 API 응답의 asset.url 값을 그대로 사용한다.
        # Cloudflare R2로 이전할 때도 서버 응답의 asset.url만
        # R2 공개 URL 또는 사용자 도메인 URL로 바꾸면 된다.
        # ============================================================
        self._log(
            f"[launcher] asset_url={latest.asset_url}"
        )

        compare_result = compare_versions(
            state.version,
            latest.latest_version,
        )

        # 서버 버전이 로컬보다 오래된 경우
        if compare_result > 0:
            self._log(
                "[launcher] server older than local (skip): "
                f"local={state.version} "
                f"server={latest.latest_version}"
            )

            if exe_local is None:
                return UpdateResult(
                    ok=False,
                    message="latest exe not found",
                )

            # 새 업데이트가 없어도 기존에 쌓인 버전 폴더를 정리한다.
            self._cleanup_old_version_dirs(
                current_version=state.version,
            )

            return UpdateResult(
                ok=True,
                message="ok(local newer)",
                exe_path=exe_local,
            )

        # 최신 버전과 동일한 경우
        if compare_result == 0:
            self._log(
                f"[launcher] up-to-date: {state.version}"
            )

            if exe_local is None:
                return UpdateResult(
                    ok=False,
                    message="latest exe not found",
                )

            # 새 업데이트가 없어도 기존에 쌓인 버전 폴더를 정리한다.
            self._cleanup_old_version_dirs(
                current_version=state.version,
            )

            return UpdateResult(
                ok=True,
                message="ok(up-to-date)",
                exe_path=exe_local,
            )

        # ============================================================
        # 새 버전이 있는 경우
        # ============================================================
        # auto_update=False이면 실제 다운로드를 시작하지 않고
        # 업데이트 가능 정보와 현재 버전 실행 경로만 반환한다.
        if not self.auto_update:
            return UpdateResult(
                ok=True,
                message="update available",
                exe_path=exe_local,
                update_available=True,
                latest_version=latest.latest_version,
                asset_url=latest.asset_url,
            )

        # ============================================================
        # 아래부터 실제 업데이트 수행
        # ============================================================
        if latest.asset_url is None:
            return UpdateResult(
                ok=False,
                message="asset_url is empty",
                exe_path=exe_local,
            )

        self._status("다운로드 중…")

        downloads_dir = (
                self.paths.base_dir
                / "downloads_tmp"
        )

        zip_path = (
                downloads_dir
                / (
                    f"{state.program_id}_"
                    f"{latest.latest_version}.zip"
                )
        )

        def on_download_progress(
                written: int,
                total: int,
        ) -> None:
            if total <= 0:
                return

            percent = int(
                (written / total) * 80
            )
            self._progress(percent)

        # latest.asset_url은 서버 API 응답의 asset.url 값이다.
        ok_download, download_message, byte_count = download_file(
            latest.asset_url,
            zip_path,
            progress_cb=on_download_progress,
        )

        self._log(
            f"[launcher] download.ok={ok_download}"
        )
        self._log(
            f"[launcher] download.msg={download_message}"
        )
        self._log(
            f"[launcher] download.path={zip_path}"
        )
        self._log(
            f"[launcher] download.bytes={byte_count}"
        )

        if not ok_download:
            return UpdateResult(
                ok=False,
                message=(
                    "download failed: "
                    f"{download_message}"
                ),
                exe_path=exe_local,
            )

        self._status("압축 해제 중…")
        self._progress(85)

        dir_name = version_to_dirname(
            latest.latest_version
        )

        staging_dir = (
                self.paths.versions_dir
                / "_staging"
                / state.program_id
                / dir_name
        )

        ok_unzip, unzip_message = unzip_to_staging(
            zip_path,
            staging_dir,
        )

        self._log(
            f"[launcher] unzip.ok={ok_unzip}"
        )
        self._log(
            f"[launcher] unzip.msg={unzip_message}"
        )
        self._log(
            f"[launcher] unzip.dir={staging_dir}"
        )

        if not ok_unzip:
            return UpdateResult(
                ok=False,
                message=(
                    "unzip failed: "
                    f"{unzip_message}"
                ),
                exe_path=exe_local,
            )

        exe_name = "CrawlProgram.exe"

        found_exe = _find_exe(
            staging_dir,
            exe_name,
        )

        self._log(
            f"[launcher] exe_found={found_exe}"
        )

        if found_exe is None:
            return UpdateResult(
                ok=False,
                message=(
                    "exe not found in zip: "
                    f"{exe_name}"
                ),
                exe_path=exe_local,
            )

        self._status("설치 반영 중…")
        self._progress(92)

        target_dir = (
                self.paths.versions_dir
                / dir_name
        )

        ok_promote, promote_message = promote_staging(
            staging_dir,
            target_dir,
        )

        self._log(
            f"[launcher] promote.ok={ok_promote}"
        )
        self._log(
            f"[launcher] promote.msg={promote_message}"
        )
        self._log(
            "[launcher] promote.target_dir="
            f"{target_dir}"
        )

        if not ok_promote:
            return UpdateResult(
                ok=False,
                message=(
                    "promote failed: "
                    f"{promote_message}"
                ),
                exe_path=exe_local,
            )

        # current.json을 변경하기 전에 설치 결과를 다시 검증한다.
        installed_exe = _find_exe(
            target_dir,
            exe_name,
        )

        if installed_exe is None:
            return UpdateResult(
                ok=False,
                message="installed but exe not found",
                exe_path=exe_local,
            )

        self._status("버전 정보 저장 중…")
        self._progress(96)

        new_state = CurrentState(
            program_id=state.program_id,
            version=latest.latest_version,
            server_url=state.server_url,
            launcher_key=state.launcher_key,
        )

        write_current_state(
            self.paths.current_json,
            new_state,
        )

        self._log(
            "[launcher] current.json updated: "
            f"version={latest.latest_version}"
        )

        self._status("정리 중…")
        self._progress(98)

        # 다운로드 ZIP과 설치 임시 폴더를 정리한다.
        cleanup_paths(zip_path)
        cleanup_paths(downloads_dir)
        cleanup_paths(
            self.paths.versions_dir
            / "_staging"
        )

        self._log(
            "[launcher] temporary cleanup done"
        )

        # ============================================================
        # 설치 버전 폴더 정리
        #
        # 현재 버전과 바로 이전에 설치된 버전만 남긴다.
        # 삭제에 실패하더라도 업데이트 성공 자체는 취소하지 않는다.
        # ============================================================
        self._cleanup_old_version_dirs(
            current_version=latest.latest_version,
        )

        self._progress(100)

        # update_installed=True를 받은 LauncherWindow가
        # 설치된 새 버전을 자동 실행하고 런처를 종료한다.
        return UpdateResult(
            ok=True,
            message="ok(installed)",
            exe_path=installed_exe,
            update_installed=True,
            latest_version=latest.latest_version,
            asset_url=latest.asset_url,
        )

    def _resolve_latest_exe_from_state(
            self,
            state: CurrentState,
    ) -> Optional[Path]:
        dir_name = version_to_dirname(
            state.version
        )

        root = (
                self.paths.versions_dir
                / dir_name
        )

        return _find_exe(
            root,
            "CrawlProgram.exe",
        )

    def _cleanup_old_version_dirs(
            self,
            current_version: str,
    ) -> None:
        """
        versions 폴더에서 현재 버전과 직전 설치 버전만 남긴다.

        예:
        현재 버전이 1.0.5이고 폴더가 아래와 같다면

        v1_0_1
        v1_0_2
        v1_0_3
        v1_0_5

        남김:
        v1_0_5  현재 버전
        v1_0_3  현재보다 낮은 버전 중 가장 높은 버전

        삭제:
        v1_0_1
        v1_0_2

        주의:
        - _staging 등 버전 형식이 아닌 폴더는 건드리지 않는다.
        - 삭제 실패는 로그만 남기고 업데이트 성공을 유지한다.
        """
        versions_dir = self.paths.versions_dir

        if not versions_dir.exists():
            return

        try:
            current_tuple = parse_semver(
                current_version
            ).to_tuple()
        except ValueError as error:
            self._log(
                "[launcher] version cleanup skipped: "
                f"invalid current version={current_version} / "
                f"{str(error)}"
            )
            return

        current_dir_name = version_to_dirname(
            current_version
        )

        version_dirs: list[
            tuple[Path, Tuple[int, int, int]]
        ] = []

        try:
            children = list(versions_dir.iterdir())
        except OSError as error:
            self._log(
                "[launcher] version cleanup scan failed: "
                f"{str(error)}"
            )
            return

        for child in children:
            if not child.is_dir():
                continue

            version_tuple = _version_dir_to_tuple(
                child.name
            )

            if version_tuple is None:
                continue

            version_dirs.append(
                (child, version_tuple)
            )

        # 현재 버전보다 낮은 설치 버전 중 가장 높은 버전 하나를
        # 직전 버전으로 보관한다.
        older_versions = [
            item
            for item in version_dirs
            if item[1] < current_tuple
        ]

        older_versions.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        keep_dir_names = {
            current_dir_name,
        }

        previous_keep_count = max(
            0,
            self.KEEP_VERSION_COUNT - 1,
            )

        for previous_path, _version_tuple in older_versions[
                                             :previous_keep_count
                                             ]:
            keep_dir_names.add(
                previous_path.name
            )

        kept_names = sorted(keep_dir_names)

        self._log(
            "[launcher] version cleanup keep="
            f"{kept_names}"
        )

        for version_path, _version_tuple in version_dirs:
            if version_path.name in keep_dir_names:
                continue

            try:
                shutil.rmtree(version_path)
                self._log(
                    "[launcher] old version removed: "
                    f"{version_path.name}"
                )
            except OSError as error:
                self._log(
                    "[launcher] old version remove failed: "
                    f"{version_path.name} / {str(error)}"
                )