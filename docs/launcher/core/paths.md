# paths.py

## 역할

런처에서 사용하는 폴더와 파일 경로를 통합 관리한다.

개발 환경과 PyInstaller로 빌드된 운영 환경을 구분하여 `base_dir`을 결정하고, 이를 기준으로 `data`, `versions`, 설정 파일 경로를 생성한다.

---

## 기준 경로

### 개발 환경

개발 환경에서는 `paths.py`의 위치를 기준으로 `launcher` 폴더를 찾아 `base_dir`로 사용한다.

```text
crawl-program/
└─ launcher/              ← base_dir
   ├─ core/
   │  └─ paths.py
   ├─ data/
   └─ versions/
```

### 운영 환경

PyInstaller로 빌드된 EXE로 실행할 때는 런처 실행 파일이 위치한 폴더를 `base_dir`로 사용한다.

```text
GB7Launcher/
├─ GB7Launcher.exe        ← 실행 파일
├─ data/
└─ versions/
```

---

## 관리 경로

`LauncherPaths` 객체는 다음 경로를 관리한다.

| 항목                | 설명                 |
|-------------------| ------------------ |
| `base_dir`        | 런처 기준 폴더           |
| `data_dir`        | 설정 및 상태 JSON 저장 폴더 |
| `versions_dir`    | 프로그램 버전별 설치 폴더     |
| `current.json`    | 현재 프로그램과 버전 정보     |
| `notice_ack.json` | 긴급 공지 하루 숨김 정보     |

기본 구조는 다음과 같다.

```text
launcher/
├─ data/
│  ├─ current.json
│  └─ notice_ack.json
└─ versions/
   ├─ v1_0_1/
   └─ v1_0_2/
```

---

## 주요 함수

### `get_base_dir()`

현재 실행 환경을 확인하여 런처 기준 폴더를 반환한다.

* PyInstaller EXE 실행: 실행 파일이 있는 폴더
* Python 개발 실행: `launcher` 폴더

---

### `get_paths()`

`base_dir`을 기준으로 런처에서 사용하는 전체 경로를 생성하고 `LauncherPaths` 객체로 반환한다.

다른 파일에서는 경로를 직접 조합하지 않고 이 객체를 전달받아 사용한다.

---

### `ensure_dirs()`

런처 실행에 필요한 다음 폴더가 없으면 자동으로 생성한다.

```text
data/
versions/
```

런처 시작 시 `launcher_main.py`에서 호출한다.

---

## 사용 흐름

```text
launcher_main.py 실행
        ↓
get_paths()
        ↓
개발 또는 운영 환경의 base_dir 결정
        ↓
data 및 versions 경로 생성
        ↓
ensure_dirs()
        ↓
필수 폴더 자동 생성
        ↓
LauncherWindow와 UpdateWorker에 경로 전달
```

---

## 핵심 원칙

* 개발 환경과 운영 환경에서 동일한 경로 구조를 사용한다.
* 각 모듈이 경로를 직접 계산하지 않는다.
* 모든 주요 경로는 `LauncherPaths`를 통해 전달한다.
* 필요한 폴더는 런처 시작 시 자동으로 생성한다.
