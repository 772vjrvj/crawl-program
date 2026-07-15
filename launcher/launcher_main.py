# launcher/launcher_main.py
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# 런처에서 사용하는 폴더 및 파일 경로 관리
from launcher.core.paths import ensure_dirs, get_paths

# 런처 메인 화면
from launcher.ui.launcher_window import LauncherWindow

# 메인 애니메이션
from launcher.ui.splash_window import SplashWindow


def main() -> int:
    """
    런처 프로그램의 시작 함수.

    실행 순서:
    1. 런처 기준 경로 조회
    2. data, versions 폴더 생성
    3. QApplication 생성
    4. 스플래시 애니메이션 표시
    5. 애니메이션 종료 후 런처 메인 화면을 중앙에 표시
    6. Qt 이벤트 루프 실행
    """

    # 개발 환경 또는 EXE 실행 환경에 맞는 경로를 조회한다.
    paths = get_paths()

    # data, versions 폴더가 없으면 자동으로 생성한다.
    ensure_dirs(paths)

    # PySide6 프로그램 실행에 필요한 QApplication을 생성한다.
    app = QApplication(sys.argv)

    # launcher_main.py 파일이 들어 있는 launcher 폴더 경로를 구한다.
    launcher_dir = Path(__file__).resolve().parent

    # 스플래시 화면에서 사용할 로고 이미지 경로를 생성한다.
    #
    # 개발 환경 기준:
    # E:\git\crawl-program\launcher\img\gb7_main.png
    splash_image_path = launcher_dir / "img" / "gb7_main.png"

    # 스플래시 애니메이션 화면을 생성한다.
    splash = SplashWindow(image_path=splash_image_path)

    # 메인 화면 객체가 지역 변수 소멸로 종료되지 않도록 보관한다.
    window: LauncherWindow | None = None

    def open_launcher() -> None:
        """
        스플래시 애니메이션이 끝나면
        런처 메인 화면을 처음부터 화면 중앙에 표시한다.
        """

        nonlocal window

        # 런처 메인 화면에 경로 정보를 전달하여 생성한다.
        window = LauncherWindow(paths=paths)

        # 화면에 표시하기 전에 스타일과 레이아웃 크기를 계산한다.
        window.ensurePolished()

        if window.layout() is not None:
            window.layout().activate()

        window.adjustSize()

        # 네이티브 창을 미리 생성하여
        # 제목 표시줄과 창 테두리를 포함한 실제 크기를 계산한다.
        window.winId()

        # 스플래시가 표시된 모니터를 기준으로 중앙 위치를 계산한다.
        screen = splash.screen()

        if screen is None:
            screen = app.primaryScreen()

        if screen is not None:
            screen_rect = screen.availableGeometry()
            window_rect = window.frameGeometry()

            # 창의 중심점을 모니터 사용 가능 영역의 중심점에 맞춘다.
            window_rect.moveCenter(screen_rect.center())

            # 아직 화면에 표시되지 않은 상태에서 위치를 먼저 적용한다.
            window.move(window_rect.topLeft())

        # 중앙 위치가 적용된 뒤 처음으로 화면을 표시한다.
        window.show()
        window.raise_()
        window.activateWindow()

    # 스플래시 애니메이션이 끝나면 기존 런처 화면을 실행한다.
    splash.finished.connect(open_launcher)

    # 스플래시 화면을 먼저 표시한다.
    splash.show()

    # 로고 페이드 인 및 글자 애니메이션을 시작한다.
    splash.start_animation()

    # Qt 이벤트 루프를 실행하고 종료 코드를 반환한다.
    return app.exec()


# 이 파일이 프로그램의 시작점으로 실행된 경우에만 main()을 호출한다.
if __name__ == "__main__":
    raise SystemExit(main())


# ============================================================
# 개발 환경 실행 방법
# ============================================================
#
# 1. 프로젝트 최상위 폴더로 이동
#
#    E:\git\crawl-program
#
# 2. 가상환경 활성화
#
#    .\venv\Scripts\Activate.ps1
#
# 3. 모듈 방식으로 런처 실행
#
#    python -m launcher.launcher_main
#
# 실행 예시:
#
#    (venv) PS E:\git\crawl-program> python -m launcher.launcher_main
#
# 주의:
# 패키지 import를 사용하므로 아래처럼 파일을 직접 실행하지 않는다.
#
#    python .\launcher\launcher_main.py
#
# 운영 환경에서는 PyInstaller로 빌드된 EXE 파일을 직접 실행한다.