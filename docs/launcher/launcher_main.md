# launcher_main.py

## 역할

GB7 런처 프로그램의 시작점이다.

런처 경로와 필수 폴더를 준비하고, PySide6 애플리케이션을 생성한 뒤 스플래시 화면과 메인 런처 화면을 순서대로 실행한다.

---

## 실행 흐름

```text
launcher_main.py 실행
        ↓
런처 경로 조회
        ↓
data, versions 폴더 생성
        ↓
QApplication 생성
        ↓
스플래시 화면 표시
        ↓
스플래시 애니메이션 실행
        ↓
애니메이션 종료
        ↓
LauncherWindow 생성
        ↓
화면 중앙에 배치
        ↓
메인 런처 화면 표시
```

---

## 주요 처리

### 런처 경로 준비

`get_paths()`로 개발 또는 운영 환경에 맞는 런처 경로를 조회한다.

`ensure_dirs()`를 호출하여 다음 필수 폴더가 없으면 자동으로 생성한다.

```text
data/
versions/
```

---

### PySide6 애플리케이션 생성

`QApplication`을 생성하고 Qt 이벤트 루프를 시작한다.

프로그램이 종료되면 Qt의 종료 코드를 반환한다.

---

### 스플래시 화면 실행

`launcher/img/gb7_main.png` 이미지를 사용하여 `SplashWindow`를 생성한다.

스플래시 화면을 먼저 표시한 뒤 로고 페이드 인과 텍스트 애니메이션을 시작한다.

---

### 메인 런처 화면 실행

스플래시 애니메이션의 `finished` 시그널이 발생하면 `LauncherWindow`를 생성한다.

메인 화면을 표시하기 전에 레이아웃과 실제 창 크기를 계산하고, 스플래시가 표시된 모니터의 중앙에 위치시킨다.

화면 위치를 먼저 적용한 후 `show()`를 호출하므로 창이 좌측 상단에서 중앙으로 이동하는 현상을 방지한다.

---

## 주요 객체

| 객체 | 역할 |
|---|---|
| `LauncherPaths` | 런처에서 사용할 폴더와 파일 경로 정보 |
| `QApplication` | PySide6 프로그램과 이벤트 루프 관리 |
| `SplashWindow` | 프로그램 시작 애니메이션 화면 |
| `LauncherWindow` | 공지 확인, 업데이트 확인, 프로그램 실행을 담당하는 메인 화면 |

---

## 실행 방법

개발 환경에서는 프로젝트 최상위 폴더에서 모듈 방식으로 실행한다.

```powershell
cd E:\git\crawl-program
.\venv\Scripts\Activate.ps1
python -m launcher.launcher_main
```

파일을 직접 실행하지 않는다.

```powershell
python .\launcher\launcher_main.py
```

운영 환경에서는 PyInstaller로 빌드된 런처 EXE 파일을 실행한다.

---

## 핵심 원칙

- 런처 실행에 필요한 경로와 폴더를 가장 먼저 준비한다.
- 스플래시 화면이 끝난 뒤 메인 런처 화면을 생성한다.
- 메인 화면은 표시 전에 위치를 계산하여 처음부터 화면 중앙에 나타나게 한다.
- `LauncherWindow` 객체를 지역 변수로 유지하여 실행 중 소멸되지 않게 한다.
- 개발 환경에서는 패키지 import를 위해 모듈 방식으로 실행한다.