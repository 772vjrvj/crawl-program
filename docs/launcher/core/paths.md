# paths.py

## 핵심 정의

`paths.py`는 런처에서 사용하는 기준 경로와 주요 파일 경로를 한곳에서 관리한다.

개발 환경과 PyInstaller로 빌드된 운영 환경을 구분하여 런처의 기준 폴더를 자동으로 결정한다.

---

## 핵심 흐름

```text
런처 실행
    ↓
개발 환경 또는 운영 환경 확인
    ↓
런처 기준 폴더 결정
    ↓
data, versions 경로 생성
    ↓
설정 파일 경로 생성
    ↓
LauncherPaths 객체로 반환
```

---

## LauncherPaths

런처에서 사용하는 경로 정보를 하나의 객체로 관리한다.

| 항목                | 내용                   |
| ----------------- | -------------------- |
| `base_dir`        | 런처 기준 폴더             |
| `data_dir`        | 설정 파일 저장 폴더          |
| `versions_dir`    | 프로그램 버전별 설치 폴더       |
| `app_json`        | 런처 설정 파일             |
| `current_json`    | 현재 프로그램 버전과 인증 정보 파일 |
| `notice_ack_json` | 긴급 공지 숨김 상태 파일       |

---

## 기준 폴더 결정

### 개발 환경

현재 `paths.py` 파일 위치를 기준으로 `launcher` 폴더를 사용한다.

```text
crawl-program/
└─ launcher/
   ├─ core/
   │  └─ paths.py
   ├─ data/
   └─ versions/
```

```text
base_dir = crawl-program/launcher
```

### 운영 환경

PyInstaller로 빌드된 경우 실행 중인 런처 EXE가 위치한 폴더를 사용한다.

```text
GB7Launcher/
├─ GB7Launcher.exe
├─ data/
└─ versions/
```

```text
base_dir = GB7Launcher.exe가 있는 폴더
```

---

## 생성되는 주요 경로

```text
base_dir/
├─ data/
│  ├─ app.json
│  ├─ current.json
│  └─ notice_ack.json
└─ versions/
```

`get_paths()`는 위 경로를 생성하는 것이 아니라 경로 정보만 만들어 반환한다.

실제 폴더 생성은 `ensure_dirs()`가 담당한다.

---

## 폴더 자동 생성

런처 시작 시 다음 폴더가 없으면 자동으로 생성한다.

```text
data/
versions/
```

```python
ensure_dirs(paths)
```

이미 폴더가 존재해도 오류 없이 그대로 사용한다.

---

## 핵심 역할 정리

```text
get_base_dir()
    → 개발·운영 환경에 맞는 기준 폴더 결정

get_paths()
    → 런처에서 사용할 전체 경로 구성

ensure_dirs()
    → data, versions 폴더가 없으면 생성
```

`paths.py`를 통해 다른 파일에서 경로를 직접 조합하지 않고 동일한 경로 구조를 사용할 수 있다.
