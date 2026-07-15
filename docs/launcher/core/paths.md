# paths.py

## 역할

런처에서 사용하는 주요 폴더와 파일 경로를 한곳에서 관리한다.

개발 환경과 PyInstaller로 빌드된 운영 환경을 자동으로 구분하여 기준 경로를 설정한다.

---

## 주요 경로

`LauncherPaths`는 다음 경로를 관리한다.

| 항목                | 설명                   |
| ----------------- | -------------------- |
| `base_dir`        | 런처 기준 폴더             |
| `data_dir`        | 설정 및 상태 파일 저장 폴더     |
| `versions_dir`    | 프로그램 버전별 실행 파일 저장 폴더 |
| `current_json`    | 현재 설치 버전 정보 파일       |
| `notice_ack_json` | 공지 숨김 상태 저장 파일       |

기본 폴더 구조는 다음과 같다.

```text
launcher
├─ data
│  ├─ current.json
│  └─ notice_ack.json
└─ versions
```

---

## 개발 환경

개발 중에는 `paths.py`가 위치한 경로를 기준으로 `launcher` 폴더를 찾는다.

```text
crawl-program
└─ launcher
   ├─ launcher_main.py
   ├─ core
   │  └─ paths.py
   ├─ data
   └─ versions
```

실행은 프로젝트 최상위 폴더에서 모듈 방식으로 한다.

```powershell
cd E:\git\crawl-program
python -m launcher.launcher_main
```

개발 환경의 기준 경로는 다음과 같다.

```text
base_dir = E:\git\crawl-program\launcher
```

---

## 운영 환경

PyInstaller로 빌드된 실행 파일에서는 `sys.frozen` 여부를 확인한다.

운영 환경에서는 실행 중인 EXE 파일이 있는 폴더를 기준 경로로 사용한다.

```text
C:\GB7Launcher
├─ GB7Launcher.exe
├─ data
└─ versions
```

운영 시에는 사용자가 EXE 파일을 직접 실행하면 된다.

```text
GB7Launcher.exe
```

---

## 폴더 생성

`ensure_dirs()`는 런처 시작 시 다음 폴더가 없으면 자동으로 생성한다.

```text
data
versions
```

따라서 최초 실행 시 해당 폴더를 사용자가 직접 만들 필요는 없다.

---

## 핵심 정리

```text
개발 실행:
python -m launcher.launcher_main

개발 기준 폴더:
crawl-program/launcher

운영 실행:
GB7Launcher.exe 직접 실행

운영 기준 폴더:
GB7Launcher.exe가 위치한 폴더
```
