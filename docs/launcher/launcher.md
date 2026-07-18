# GB7 Launcher

## 버전업 및 초기화 세팅 — 자주 보는 4단계

### 1. 로컬 버전 ZIP 파일 준비

다음 로컬 경로에 신규 버전 폴더를 생성하고 ZIP 파일을 넣는다.

```text
E:\나의 목록\cloudflare\version\NAVER_PLACE_LOC_ALL\v2_0_2
```

추가할 파일:

```text
v2_0_2.zip
```

최종 경로:

```text
E:\나의 목록\cloudflare\version\NAVER_PLACE_LOC_ALL\v2_0_2\v2_0_2.zip
```

---

### 2. Cloudflare R2에 ZIP 파일 업로드

Cloudflare R2 버킷에 다음 객체 경로를 생성하고 ZIP 파일을 업로드한다.

```text
NAVER_PLACE_LOC_ALL/v2_0_2/v2_0_2.zip
```

확인 항목:

```text
PROGRAM_ID : NAVER_PLACE_LOC_ALL
DIR_NAME   : v2_0_2
FILE_NAME  : v2_0_2.zip
```

---

### 3. 고객용 런처 키 발급 및 정리

다음 파일의 고객 및 프로그램 정보를 수정한 뒤 실행한다.

```text
launcher/etc/launcher_key_create.py
```

실행 후 다음 내용을 확인한다.

1. 콘솔 로그에서 발급된 원본 `launcherKey`를 확인한다.
2. DB의 `LAUNCHER_PROGRAM_KEY` 테이블에 키 정보가 등록되었는지 확인한다.
3. 발급된 원본 키를 고객 관리 엑셀에 정리한다.
4. 고객용 `data/current.json`의 `launcher_key`에 원본 키를 입력한다.

주의:

```text
DB에는 원본 키가 아닌 검증용 해시값이 저장될 수 있다.
실제 고객에게 전달할 원본 launcherKey는 발급 로그에서 확인하고 별도로 보관한다.
```

---

### 4. Cloudflare 파일 검증 및 릴리스 등록 확인

다음 파일의 배포 정보를 수정한 뒤 실행한다.

```text
launcher/etc/cloudflare.py
```

주로 수정하는 값:

```python
PROGRAM_ID = "NAVER_PLACE_LOC_ALL"
VERSION = "2.0.2"
DIR_NAME = "v2_0_2"
FILE_NAME = "v2_0_2.zip"
```

실행 후 다운로드 테스트 파일을 확인한다.

```text
E:\나의 목록\cloudflare\version\NAVER_PLACE_LOC_ALL\v2_0_2\test\v2_0_2.zip
```

마지막으로 다음 항목을 확인한다.

1. 원본 ZIP과 테스트 다운로드 ZIP의 파일 크기가 일치하는지 확인한다.
2. 원본 ZIP과 테스트 다운로드 ZIP의 SHA-256이 일치하는지 확인한다.
3. DB의 `LAUNCHER_RELEASE` 테이블에 신규 버전이 등록되었는지 확인한다.
4. `PROGRAM_ID`, `VERSION`, `DIR_NAME`, `FILE_NAME`, `SIZE_BYTES`, `SHA256` 값이 올바른지 확인한다.

전체 흐름:

```text
로컬 ZIP 준비
    ↓
Cloudflare R2 업로드
    ↓
launcher_key_create.py로 고객 키 발급
    ↓
LAUNCHER_PROGRAM_KEY 확인
    ↓
원본 키를 고객 관리 엑셀에 정리
    ↓
cloudflare.py 실행
    ↓
test 폴더 다운로드 파일 확인
    ↓
파일 크기 및 SHA-256 확인
    ↓
LAUNCHER_RELEASE 등록 확인
```

---

## 1. 문서 목적

GB7 Launcher는 고객 PC에서 다음 작업을 담당하는 전용 실행 프로그램이다.

```text
긴급 공지 확인
    ↓
최신 버전 확인
    ↓
업데이트 파일 다운로드
    ↓
파일 크기 및 SHA-256 검증
    ↓
압축 해제 및 설치
    ↓
프로그램 실행
```

이 문서는 현재 프리징 대상 소스코드를 기준으로 다음 내용을 정리한다.

- 관리자 PC에서 수행하는 런처 키 발급
- Cloudflare R2 배포 파일 검증
- 웹서버 릴리스 등록
- 고객 런처의 전체 실행 흐름
- 런처가 사용하는 설정 파일과 API
- 업데이트 실패 및 복구 정책
- 빌드·배포 전 확인 사항

각 Python 함수의 세부 구현보다는 전체 구조와 운영 흐름을 중심으로 정리한다.

---

## 2. 전체 시스템 구성

GB7 Launcher 업데이트 시스템은 크게 세 영역으로 나뉜다.

```text
관리자 PC
    ├─ launcher_key_create.py
    └─ cloudflare.py
            ↓
Spring Boot 웹서버
    ├─ 런처 키 발급 및 검증
    ├─ 최신 릴리스 정보 제공
    ├─ 긴급 공지 제공
    └─ 다운로드 이력 저장
            ↓
Cloudflare R2
    └─ 프로그램 버전별 ZIP 파일 보관
            ↓
고객 PC
    └─ GB7Launcher.exe
```

### 관리자 PC

고객에게 런처를 전달하기 전에 다음 작업을 수행한다.

1. 고객별·프로그램별 런처 키를 생성한다.
2. 프로그램 ZIP 파일을 Cloudflare R2에 업로드한다.
3. R2 파일의 크기와 SHA-256을 검증한다.
4. 검증된 파일 정보를 웹서버의 릴리스 테이블에 등록한다.
5. 고객용 `current.json`에 발급된 런처 키를 저장한다.

### Spring Boot 웹서버

웹서버는 다음 역할을 담당한다.

- 관리자용 런처 키 생성
- 고객 런처 키 검증
- 프로그램별 최신 버전 조회
- Cloudflare R2 다운로드 URL 발급
- 긴급 공지 조회
- 다운로드 성공·실패 이력 저장
- 관리자용 신규 릴리스 등록

### Cloudflare R2

Cloudflare R2는 실제 업데이트 ZIP 파일을 저장한다.

런처가 R2의 Access Key나 Secret Key를 직접 가지지 않는다.  
웹서버가 최신 버전 API 응답으로 전달한 임시 다운로드 URL을 런처가 그대로 사용한다.

### 고객 PC

고객 PC의 런처는 다음 역할만 담당한다.

- 긴급 공지 확인
- 런처 키를 사용한 최신 버전 조회
- 다운로드 파일 저장
- 파일 크기와 SHA-256 검증
- 압축 해제와 설치
- 현재 버전 정보 갱신
- 프로그램 실행
- 다운로드 결과 이력 전송

---

## 3. 주요 디렉터리 구조

```text
crawl-program/
├─ launcher/
│  ├─ launcher_main.py
│  │
│  ├─ core/
│  │  ├─ api.py
│  │  ├─ app_config.py
│  │  ├─ downloader.py
│  │  ├─ installer.py
│  │  ├─ notice_store.py
│  │  ├─ paths.py
│  │  ├─ runner.py
│  │  ├─ state.py
│  │  └─ versioning.py
│  │
│  ├─ workers/
│  │  ├─ notice_worker.py
│  │  └─ update_worker.py
│  │
│  ├─ ui/
│  │  ├─ launcher_window.py
│  │  ├─ notice_dialog.py
│  │  ├─ splash_window.py
│  │  ├─ update_confirm_dialog.py
│  │  └─ style/
│  │     └─ style.py
│  │
│  ├─ etc/
│  │  ├─ cloudflare.py
│  │  └─ launcher_key_create.py
│  │
│  ├─ data/
│  │  ├─ app.json
│  │  ├─ current.json
│  │  └─ notice_ack.json
│  │
│  └─ img/
│     └─ gb7_main.png
│
├─ docs/
│  └─ launcher/
│     └─ launcher.md
│
├─ dist/
├─ build/
└─ build_launcher.ps1
```

---

## 4. 파일별 핵심 역할

| 파일 | 핵심 역할 |
|---|---|
| `launcher_main.py` | 런처 시작점, 경로 초기화, 스플래시 표시, 메인 화면 실행 |
| `ui/launcher_window.py` | 긴급 공지와 업데이트 흐름을 연결하고 화면 상태를 관리 |
| `ui/splash_window.py` | 시작 애니메이션과 메인 창 중앙 표시 전 단계 담당 |
| `ui/notice_dialog.py` | 긴급 공지 내용과 오늘 하루 안보기 제공 |
| `ui/update_confirm_dialog.py` | 업데이트, 현재 버전 실행, 취소 동작 구분 |
| `ui/style/style.py` | 버튼과 메시지 박스 공통 스타일 |
| `workers/notice_worker.py` | 긴급 공지 API를 별도 스레드에서 호출 |
| `workers/update_worker.py` | 최신 버전 조회, 다운로드, 검증, 설치, 이력 전송 |
| `core/api.py` | 최신 버전·긴급 공지·다운로드 이력 API 호출 |
| `core/downloader.py` | 스트리밍 다운로드, `.part` 파일, SHA-256 동시 계산 |
| `core/installer.py` | staging 압축 해제, 정식 버전 폴더 반영, 임시 경로 정리 |
| `core/state.py` | `current.json` 읽기·쓰기와 버전 폴더명 변환 |
| `core/versioning.py` | `x.y.z` 버전 파싱과 버전 비교 |
| `core/paths.py` | 개발·운영 환경의 기준 경로와 주요 파일 경로 생성 |
| `core/notice_store.py` | 긴급 공지 오늘 하루 안보기 상태 저장 |
| `core/app_config.py` | 공식 사이트와 문의 URL 읽기 |
| `core/runner.py` | 설치된 실제 프로그램을 독립 프로세스로 실행 |
| `etc/launcher_key_create.py` | 관리자 API를 호출하여 고객용 런처 키 발급 |
| `etc/cloudflare.py` | R2 파일 검증 후 웹서버에 신규 릴리스 등록 |

---

## 5. 실행 위치

런처 관련 명령은 프로젝트 최상위 경로에서 실행한다.

```text
E:\git\crawl-program
```

### 개발 환경 실행

```powershell
(venv) PS E:\git\crawl-program> python -m launcher.launcher_main
```

패키지 import 구조를 사용하므로 다음과 같이 파일을 직접 실행하지 않는다.

```powershell
python .\launcher\launcher_main.py
```

### 운영 환경 실행

PyInstaller 빌드 후 생성된 실행 파일을 직접 실행한다.

```text
GB7Launcher.exe
```

### 런처 빌드

```powershell
(venv) PS E:\git\crawl-program> .\build_launcher.ps1
```

---

## 6. 설정 파일

## 6.1 `data/current.json`

고객에게 설치된 프로그램과 업데이트 인증 정보를 관리한다.

```json
{
  "program_id": "NAVER_BAND_MEMBER",
  "version": "1.0.1",
  "server_url": "https://example.com",
  "launcher_key": "고객별-프로그램별-원본-런처-키"
}
```

| 항목 | 내용 |
|---|---|
| `program_id` | 서버에서 프로그램을 구분하는 ID |
| `version` | 고객 PC에 현재 설치된 프로그램 버전 |
| `server_url` | 런처 API를 제공하는 Spring Boot 서버 주소 |
| `launcher_key` | 고객별·프로그램별 최신 버전 조회 인증키 |

네 항목은 모두 필수 문자열이다.  
하나라도 없거나 빈 문자열이면 `current.json` 읽기가 실패한다.

`launcher_key`는 `app.json`이 아니라 **`current.json`에 저장한다.**

업데이트 설치가 완료되면 런처는 `version`만 새 버전으로 변경하고 나머지 값은 유지한다.

파일 저장은 임시 파일에 먼저 작성한 뒤 원본 파일로 교체한다.

```text
current.tmp 작성
    ↓
current.json으로 교체
```

---

## 6.2 `data/app.json`

런처 자체 버전과 지원 페이지 주소를 관리한다.

```json
{
  "support": {
    "site_url": "https://example.com",
    "qna_url": "https://example.com/faq"
  },
  "launcher_version": "1.0.1"
}
```

| 항목 | 내용 |
|---|---|
| `support.site_url` | 공식 사이트 주소 |
| `support.qna_url` | 문의/Q&A 주소 |
| `launcher_version` | 다운로드 이력에 함께 저장할 런처 버전 |

`launcher_version`을 읽지 못하면 `None`으로 처리하며, 프로그램 업데이트 자체는 계속 진행한다.

지원 페이지를 열 때 다음 정보가 쿼리 파라미터로 추가된다.

| 파라미터 | 내용 |
|---|---|
| `program` | 프로그램 ID |
| `ver` | 현재 프로그램 버전 |
| `os` | 운영체제 이름 |
| `osver` | 운영체제 버전 |

예:

```text
https://example.com/faq
?program=NAVER_BAND_MEMBER
&ver=1.0.1
&os=Windows
&osver=...
```

---

## 6.3 `data/notice_ack.json`

긴급 공지의 오늘 하루 안보기 상태를 저장한다.

```json
{
  "NOTICE-20260718-001": 1784386800
}
```

| Key | Value |
|---|---|
| 공지 ID | 사용자 PC 기준 다음 날 00:00의 epoch 값 |

24시간을 단순히 더하는 방식이 아니다.

```text
사용자가 오늘 하루 안보기 선택
    ↓
사용자 PC 현지 시간 확인
    ↓
다음 날 00:00까지 자동 팝업 숨김
```

숨김 상태여도 `긴급 공지 다시 보기` 버튼은 유지된다.

---

## 7. 관리자 사전 준비 흐름

고객이 런처에서 새 버전을 받을 수 있으려면 관리자 측 작업이 먼저 완료되어야 한다.

```text
1. 프로그램 신규 버전 빌드
    ↓
2. 버전 ZIP 파일 생성
    ↓
3. ZIP 파일을 Cloudflare R2에 업로드
    ↓
4. cloudflare.py 설정 변경
    ↓
5. R2 객체 크기 및 SHA-256 검증
    ↓
6. 웹서버 릴리스 등록
    ↓
7. launcher_key_create.py로 고객용 키 발급
    ↓
8. 고객 current.json에 키와 현재 버전 저장
    ↓
9. 고객에게 런처 전달
```

키 발급과 릴리스 등록의 순서는 운영 상황에 따라 바꿀 수 있다.  
다만 고객이 런처를 실행하기 전에는 다음 두 조건이 모두 충족되어야 한다.

- 해당 `program_id`에 활성화된 릴리스가 웹서버에 등록되어 있어야 한다.
- 해당 고객의 유효한 `launcher_key`가 발급되어 있어야 한다.

---

## 8. 고객용 런처 키 생성

사용 파일:

```text
launcher/etc/launcher_key_create.py
```

이 스크립트는 Spring Boot 관리자 API를 호출하여 고객별·프로그램별 원본 런처 키를 생성한다.

### 직접 수정하는 설정

```python
BASE_URL = "https://example.com"
ADMIN_KEY = "관리자-API-키"
PROGRAM_ID = "NAVER_BAND_MEMBER"
KEY_NAME = "고객 A"
EXPIRE_AT = "9999-12-31T23:59:59"
```

| 설정 | 내용 |
|---|---|
| `BASE_URL` | Spring Boot 웹서버 주소 |
| `ADMIN_KEY` | 관리자 API 인증키 |
| `PROGRAM_ID` | 키 사용을 허용할 프로그램 ID |
| `KEY_NAME` | 관리자 확인용 고객 또는 키 이름 |
| `EXPIRE_AT` | 키 만료 일시, 만료 없음은 `None` |

### 호출 API

```http
POST /launcher/admin/api/v1/program-keys
X-Admin-Key: {ADMIN_KEY}
Content-Type: application/json
```

요청 Body:

```json
{
  "programId": "NAVER_BAND_MEMBER",
  "keyName": "고객 A",
  "expireAt": "9999-12-31T23:59:59"
}
```

정상 응답:

```text
HTTP 201 Created
```

응답에는 생성된 원본 `launcherKey`가 포함된다.

### 중요한 운영 기준

생성된 원본 런처 키는 응답에서 한 번만 확인하는 구조로 운영한다.

```text
원본 launcherKey 발급
    ↓
고객용 current.json에 저장
    ↓
웹서버 DB에는 원본 대신 검증용 해시 저장
```

발급받은 원본 키는 고객용 `current.json`의 `launcher_key`에 입력한다.

```json
{
  "launcher_key": "발급받은-원본-키"
}
```

---

## 9. Cloudflare R2 파일 검증 및 릴리스 등록

사용 파일:

```text
launcher/etc/cloudflare.py
```

이 파일은 R2 업로드 프로그램이 아니다.

관리자가 별도로 R2에 올린 ZIP 파일을 다시 확인한 뒤, 검증이 성공한 경우에만 웹서버에 릴리스를 등록한다.

### 직접 수정하는 주요 설정

```python
R2_ENDPOINT = "R2 Endpoint"
R2_ACCESS_KEY = "R2 Access Key"
R2_SECRET_KEY = "R2 Secret Key"

WEB_SERVER_URL = "https://example.com"
RELEASE_KEY = "릴리스-등록-API-키"

PROGRAM_ID = "NAVER_BAND_MEMBER"
VERSION = "1.0.2"
DIR_NAME = "v1_0_2"
FILE_NAME = "v1_0_2.zip"
ENABLED = True

BUCKET_NAME = "gb7-launcher-files"
SOURCE_PATH = Path(r"로컬 원본 ZIP 경로")
DOWNLOAD_DIR = Path(r"검증용 다운로드 폴더")
```

### R2 객체 경로

```text
{PROGRAM_ID}/{DIR_NAME}/{FILE_NAME}
```

예:

```text
NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip
```

버킷 이름은 `OBJECT_KEY`에 포함하지 않는다.

### 실행 전 필수 일치 조건

```text
VERSION   = 1.0.2
DIR_NAME  = v1_0_2
FILE_NAME = v1_0_2.zip
```

`DIR_NAME`은 `VERSION`으로 계산한 값과 같아야 한다.

```text
1.0.2
→ v1_0_2
```

`FILE_NAME`은 `.zip` 확장자여야 한다.

### 검증 흐름

```text
로컬 원본 ZIP 존재 확인
    ↓
원본 파일 크기 계산
    ↓
원본 SHA-256 계산
    ↓
R2 head_object 호출
    ↓
R2 객체 존재 여부 확인
    ↓
원본 크기와 R2 ContentLength 비교
    ↓
10분 유효 Presigned URL 생성
    ↓
Presigned URL로 파일 재다운로드
    ↓
다운로드 파일 크기 계산
    ↓
다운로드 파일 SHA-256 계산
    ↓
원본·R2·다운로드 파일 크기 비교
    ↓
원본과 다운로드 SHA-256 비교
    ↓
모든 검증 성공
    ↓
웹서버 릴리스 등록 API 호출
```

### SHA-256 검증 목적

파일명이 같아도 내부 바이트가 다르면 SHA-256 값이 달라진다.

따라서 크기와 SHA-256을 함께 확인하면 다음 문제를 탐지할 수 있다.

- 업로드 중 파일 손상
- 다른 ZIP 파일을 잘못 업로드
- 일부 바이트 누락
- 다운로드 중 변조 또는 손상
- 같은 파일명으로 잘못된 파일 교체

### 릴리스 등록 API

```http
POST /launcher/api/v1/programs/{programId}/releases
X-Release-Key: {RELEASE_KEY}
Content-Type: application/json
```

요청 Body:

```json
{
  "version": "1.0.2",
  "dirName": "v1_0_2",
  "fileName": "v1_0_2.zip",
  "sha256": "64자리 SHA-256",
  "sizeBytes": 157286400,
  "enabled": true
}
```

응답 처리:

| 상태 | 의미 |
|---|---|
| `201 Created` | 신규 릴리스 등록 성공 |
| `409 Conflict` | 같은 프로그램과 버전이 이미 등록됨 |
| 그 외 | 릴리스 등록 실패 |

R2 검증이 하나라도 실패하면 릴리스 등록 API는 호출하지 않는다.

---

## 10. 관리자 사전 배포 전체 흐름

```text
신규 프로그램 버전 빌드
    ↓
CrawlProgram.exe 포함 여부 확인
    ↓
v1_0_2.zip 생성
    ↓
Cloudflare R2에 직접 업로드
    ↓
cloudflare.py의 버전·경로 설정 변경
    ↓
cloudflare.py 실행
    ↓
R2 객체 존재 확인
    ↓
파일 크기 검증
    ↓
Presigned URL 다운로드 검증
    ↓
SHA-256 검증
    ↓
웹서버 LAUNCHER_RELEASE 등록
    ↓
필요 시 launcher_key_create.py 실행
    ↓
고객별·프로그램별 launcherKey 발급
    ↓
고객 current.json 구성
    ↓
런처 빌드 및 고객 전달
```

---

## 11. 런처가 사용하는 API

| 구분 | 방식 | 주소 | 인증 | 역할 |
|---|---|---|---|---|
| 관리자 런처 키 생성 | `POST` | `/launcher/admin/api/v1/program-keys` | `X-Admin-Key` | 고객별·프로그램별 키 생성 |
| 관리자 릴리스 등록 | `POST` | `/launcher/api/v1/programs/{programId}/releases` | `X-Release-Key` | 검증 완료된 신규 버전 등록 |
| 긴급 공지 조회 | `GET` | `/launcher/api/v1/programs/{programId}/notices/latest/critical` | 현재 없음 | 최신 긴급 공지 1건 조회 |
| 최신 버전 조회 | `GET` | `/launcher/api/v1/programs/{programId}/latest` | `X-Launcher-Key` | 최신 버전과 R2 다운로드 URL 조회 |
| 다운로드 이력 저장 | `POST` | `/launcher/api/v1/programs/{programId}/download-histories` | `X-Launcher-Key` | 다운로드 성공·실패 결과 저장 |
| 업데이트 ZIP 다운로드 | `GET` | 최신 버전 응답의 `asset.url` | Presigned URL 자체 인증 | Cloudflare R2 ZIP 다운로드 |

---

## 12. 최신 버전 조회 API

```http
GET /launcher/api/v1/programs/{programId}/latest
Accept: application/json
X-Launcher-Key: {launcherKey}
```

예:

```text
GET https://example.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/latest
```

정상 응답은 camelCase와 snake_case를 모두 처리한다.

```json
{
  "programId": "NAVER_BAND_MEMBER",
  "latestVersion": "1.0.2",
  "asset": {
    "url": "Cloudflare R2 Presigned URL",
    "sha256": "64자리 SHA-256",
    "size": 157286400
  }
}
```

또는:

```json
{
  "program_id": "NAVER_BAND_MEMBER",
  "latest_version": "1.0.2",
  "asset": {
    "url": "Cloudflare R2 Presigned URL",
    "sha256": "64자리 SHA-256",
    "size": 157286400
  }
}
```

| 응답 항목 | 내용 |
|---|---|
| `programId` | 조회한 프로그램 ID |
| `latestVersion` | 서버에 등록된 최신 활성 버전 |
| `asset.url` | 실제 ZIP 파일을 받을 Presigned URL |
| `asset.sha256` | 서버 릴리스 정보에 저장된 SHA-256 |
| `asset.size` | 서버 릴리스 정보에 저장된 파일 크기 |

런처는 다운로드 URL을 직접 조합하지 않는다.

```text
서버가 반환한 asset.url
    ↓
런처가 그대로 다운로드
```

현재 소스는 `programId` 필드가 존재하는지는 확인하지만, 요청한 `program_id`와 응답값이 같은지 별도로 비교하지는 않는다.

---

## 13. 긴급 공지 조회 API

```http
GET /launcher/api/v1/programs/{programId}/notices/latest/critical
Accept: application/json
```

긴급 공지가 있는 경우:

```json
{
  "id": "NOTICE-20260718-001",
  "level": "CRITICAL",
  "force": true,
  "title": "긴급 점검 안내",
  "content": "공지 내용"
}
```

서버가 `notice` 객체로 감싸도 처리한다.

```json
{
  "notice": {
    "id": "NOTICE-20260718-001",
    "level": "CRITICAL",
    "force": true,
    "title": "긴급 점검 안내",
    "content": "공지 내용"
  }
}
```

긴급 공지가 없는 경우:

```text
HTTP 204 No Content
```

런처 표시 조건:

```text
force == true
또는
level == "CRITICAL"
```

일반 공지는 런처에서 표시하지 않는다.

공지 조회에 실패해도 업데이트 확인은 계속 진행한다.

현재 공지 조회 API 요청에는 `X-Launcher-Key`가 포함되지 않는다.

---

## 14. 다운로드 이력 저장 API

```http
POST /launcher/api/v1/programs/{programId}/download-histories
Accept: application/json
X-Launcher-Key: {launcherKey}
Content-Type: application/json
```

요청 예:

```json
{
  "downloadId": "UUID",
  "version": "1.0.2",
  "status": "SUCCESS",
  "downloadSizeBytes": 157286400,
  "sha256Verified": true,
  "startedAt": "2026-07-18T19:00:00.123456",
  "completedAt": "2026-07-18T19:01:10.654321",
  "errorCode": null,
  "errorMessage": null,
  "launcherVersion": "1.0.1",
  "clientOs": "Windows-..."
}
```

| 항목 | 내용 |
|---|---|
| `downloadId` | 다운로드 시도마다 생성하는 UUID |
| `version` | 다운로드한 프로그램 버전 |
| `status` | `SUCCESS` 또는 `FAIL` |
| `downloadSizeBytes` | 실제 받은 바이트 수 |
| `sha256Verified` | SHA-256 일치 여부 |
| `startedAt` | 다운로드 시작 일시 |
| `completedAt` | 다운로드 종료 일시 |
| `errorCode` | 실패 유형 |
| `errorMessage` | 실패 상세 |
| `launcherVersion` | `app.json`의 런처 버전 |
| `clientOs` | 고객 PC 운영체제 정보 |

응답 처리:

| 상태 | 의미 |
|---|---|
| `201 Created` | 신규 다운로드 이력 생성 |
| `200 OK` | 같은 `downloadId` 이력이 이미 존재 |
| 그 외 | 이력 저장 실패 |

이력 API 실패는 실제 업데이트 결과를 바꾸지 않는다.  
로그만 남기고 기존 다운로드·설치 결과를 유지한다.

### 현재 기록되는 실패 코드

| 오류 코드 | 의미 |
|---|---|
| `DOWNLOAD_FAILED` | R2 다운로드 자체 실패 |
| `SIZE_MISMATCH` | 서버 등록 크기와 실제 다운로드 크기 불일치 |
| `SHA256_MISSING` | 최신 버전 응답에 SHA-256이 없음 |
| `SHA256_MISMATCH` | 서버 SHA-256과 실제 다운로드 SHA-256 불일치 |

### 기록 시점 주의

`SUCCESS`는 **다운로드와 SHA-256 검증이 완료된 시점**에 저장된다.

그 이후 발생하는 다음 오류는 다운로드 이력의 `SUCCESS`를 취소하지 않는다.

- 압축 해제 실패
- ZIP 내부 EXE 없음
- 정식 버전 폴더 반영 실패
- `current.json` 저장 실패

따라서 이 테이블은 설치 성공 이력이 아니라 **다운로드 검증 이력**이다.

---

## 15. 런처 전체 실행 흐름

```text
GB7Launcher.exe 실행
    ↓
개발 또는 운영 기준 경로 계산
    ↓
data, versions 폴더 생성
    ↓
QApplication 생성
    ↓
스플래시 화면 표시
    ↓
로고 이미지 페이드 인
    ↓
GB7 표시
    ↓
GoodBye772 타이핑
    ↓
저작권 문구 표시
    ↓
스플래시 페이드 아웃
    ↓
메인 런처 창을 화면 중앙에 표시
    ↓
current.json 읽기
    ↓
지원 센터 URL 구성
    ↓
긴급 공지 확인
    ↓
최신 버전 확인
    ↓
버전 비교
    ↓
현재 버전 실행 또는 업데이트
```

---

## 16. 스플래시 화면 흐름

```text
흰색 스플래시 표시
    ↓
원본 비율을 유지한 이미지 표시
    ↓
둥근 카드 테두리 표시
    ↓
GB7 페이드 인
    ↓
GB7 페이드 아웃
    ↓
GoodBye772 한 글자씩 표시
    ↓
© 2026–현재연도 GB7 표시
    ↓
전체 화면 페이드 아웃
    ↓
메인 런처 화면 생성
```

이미지, 이름, 저작권 문구는 처음부터 각각 고정된 레이아웃 공간을 가진다.  
문구가 나타나도 이미지 위치가 밀리지 않는다.

메인 화면은 `show()` 전에 실제 프레임 크기와 중앙 좌표를 계산하므로 좌측 상단에 잠깐 나타났다 이동하지 않는다.

---

## 17. 긴급 공지 흐름

```text
current.json 읽기
    ↓
NoticeWorker 시작
    ↓
긴급 공지 API 호출
    ↓
공지 없음 또는 일반 공지
    └─ 업데이트 확인 시작

긴급 공지 있음
    ↓
마지막 긴급 공지로 보관
    ↓
긴급 공지 다시 보기 버튼 표시
    ↓
오늘 하루 안보기 확인
    ├─ 숨김 상태: 자동 팝업 생략
    └─ 숨김 아님: 모달 팝업 표시
    ↓
업데이트 확인 시작
```

자동 팝업은 Application Modal로 표시한다.  
팝업을 닫기 전까지 메인 런처 창을 조작할 수 없다.

사용자가 직접 `긴급 공지 다시 보기` 버튼을 누른 경우에도 다이얼로그를 실행하지만, 현재 구현은 `exec()`를 사용하므로 표시 중 메인 흐름은 대기한다.

---

## 18. 업데이트 확인 흐름

업데이트 확인 단계에서는 `UpdateWorker`를 다음 설정으로 실행한다.

```python
auto_update=False
```

```text
current.json 읽기
    ↓
현재 버전 EXE 경로 미리 확인
    ↓
X-Launcher-Key로 최신 버전 API 호출
    ↓
최신 버전 응답 파싱
    ↓
로컬 버전과 서버 버전 비교
```

버전은 `major.minor.patch` 형식만 허용한다.

```text
1.0.2
v1.0.2
```

비교 결과:

| 결과 | 의미 |
|---|---|
| `local < server` | 새 버전 있음 |
| `local == server` | 최신 버전 |
| `local > server` | 로컬 버전이 더 높음, 다운그레이드하지 않음 |

---

## 19. 새 버전이 있는 경우

`auto_update=False`이면 바로 다운로드하지 않는다.

다음 정보를 메인 화면에 반환한다.

- 현재 버전 EXE 경로
- 최신 버전
- `asset.url`
- 업데이트 가능 여부

그 후 업데이트 확인창을 표시한다.

| 사용자 동작 | 결과 |
|---|---|
| `지금 업데이트` | 실제 업데이트 Worker 시작 |
| `현재 버전 실행` | 현재 설치된 프로그램 즉시 실행 |
| `X` 또는 `Esc` | 자동 실행하지 않고 런처 화면 유지 |

업데이트 확인 Worker가 완전히 종료된 뒤 실제 업데이트 Worker를 새로 시작한다.  
이를 통해 같은 `QThread`가 중복 실행되는 문제를 방지한다.

---

## 20. 실제 다운로드 흐름

실제 업데이트 단계에서는 다음 설정으로 Worker를 다시 실행한다.

```python
auto_update=True
```

```text
최신 버전 API 재호출
    ↓
다운로드 ID UUID 생성
    ↓
다운로드 시작 시각 기록
    ↓
asset.url 스트리밍 GET 요청
    ↓
1MB 단위로 파일 저장
    ↓
저장한 동일 바이트로 SHA-256 동시 계산
    ↓
진행률 표시
    ↓
다운로드 종료 시각 기록
```

### 다운로드 임시 파일

```text
downloads_tmp/{PROGRAM_ID}_{VERSION}.zip.part
```

다운로드가 정상 완료된 경우에만 정식 ZIP 파일명으로 변경한다.

```text
.part
    ↓
.zip
```

다운로드 실패 시 `.part` 파일을 삭제한다.

### 진행률

다운로드는 전체 진행률의 약 80%까지 사용한다.

```text
다운로드: 0~80%
압축 해제: 85%
설치 반영: 92%
버전 저장: 96%
정리: 98%
완료: 100%
```

---

## 21. 다운로드 파일 검증

다운로드 완료 후 다음 순서로 검증한다.

```text
다운로드 성공 여부
    ↓
서버 asset.size 존재 시 실제 크기 비교
    ↓
서버 asset.sha256 존재 확인
    ↓
실제 SHA-256과 서버 SHA-256 비교
```

### 파일 크기 검증

서버 응답에 `asset.size`가 존재하면 실제 다운로드 바이트 수와 비교한다.

```text
expected size == actual size
```

다르면 ZIP 파일을 삭제하고 설치하지 않는다.

### SHA-256 필수 정책

최신 버전 응답에 SHA-256이 없으면 안전을 위해 설치하지 않는다.

```text
asset.sha256 없음
    ↓
SHA256_MISSING
    ↓
ZIP 삭제
    ↓
업데이트 중단
```

### SHA-256 비교

비교 전에 양쪽 값을 소문자로 정규화한다.

```text
서버 SHA-256
    ==
다운로드 중 계산한 SHA-256
```

일치한 경우에만 설치 단계로 넘어간다.

---

## 22. 설치 흐름

```text
SHA-256 검증 성공
    ↓
다운로드 SUCCESS 이력 전송
    ↓
versions/_staging에 압축 해제
    ↓
CrawlProgram.exe 재귀 검색
    ↓
정식 버전 폴더로 이동
    ↓
정식 폴더에서 EXE 다시 확인
    ↓
current.json 버전 갱신
    ↓
ZIP·staging 임시 파일 정리
    ↓
오래된 버전 폴더 정리
    ↓
새 프로그램 자동 실행
    ↓
런처 종료
```

### staging 경로

```text
versions/_staging/{program_id}/{version_dir}/
```

예:

```text
versions/_staging/NAVER_BAND_MEMBER/v1_0_2/
```

### 정식 설치 경로

```text
versions/{version_dir}/
```

예:

```text
versions/v1_0_2/
```

### 실행 파일 검증

ZIP 내부에서 다음 파일을 재귀적으로 찾는다.

```text
CrawlProgram.exe
```

ZIP 최상위가 아니라 하위 폴더에 있어도 찾을 수 있다.

### 정식 반영

기존 대상 버전 폴더가 있으면 임시 백업 폴더로 이동한다.

```text
v1_0_2
    ↓
v1_0_2__bak
```

그 후 staging 폴더를 정식 폴더명으로 변경하고, 성공하면 백업을 삭제한다.

---

## 23. 버전 보관 정책

고객 PC에는 현재 버전과 현재보다 낮은 버전 중 가장 높은 버전 하나만 보관한다.

```text
KEEP_VERSION_COUNT = 2
```

예:

```text
현재 버전: 1.0.5

versions/
├─ v1_0_1
├─ v1_0_2
├─ v1_0_3
└─ v1_0_5
```

정리 결과:

```text
versions/
├─ v1_0_3
└─ v1_0_5
```

다음 폴더는 버전 형식이 아니므로 정리 대상에서 제외된다.

```text
_staging
기타 시스템 폴더
```

버전 폴더 삭제 실패는 업데이트 전체 실패로 처리하지 않고 로그만 남긴다.

최신 버전 상태이거나 로컬 버전이 더 높은 경우에도 버전 폴더 정리를 수행한다.

---

## 24. 프로그램 실행 정책

실제 프로그램은 `subprocess.Popen`으로 독립 실행한다.

```text
CrawlProgram.exe 실행
    ↓
300ms 후 런처 종료
    ↓
CrawlProgram.exe는 계속 실행
```

| 상태 | 실행 방식 |
|---|---|
| 업데이트 설치 성공 | 500ms 후 새 버전 자동 실행 |
| 현재 버전 실행 선택 | 즉시 현재 버전 실행 |
| 이미 최신 버전 | 사용자가 실행 버튼 클릭 |
| 업데이트 창 취소 | 사용자가 실행 버튼 클릭 |
| 업데이트 실패 | 기존 EXE가 있으면 실행 버튼 사용 |

실행 작업 디렉터리는 EXE가 있는 폴더이다.

---

## 25. 실패 및 복구 정책

| 실패 상황 | 처리 |
|---|---|
| `current.json` 읽기 실패 | 공지 단계에서는 업데이트 확인을 시도하지만 UpdateWorker에서 다시 실패 가능 |
| 긴급 공지 API 실패 | 로그만 남기고 업데이트 확인 계속 |
| 최신 버전 API 실패 | 기존 EXE가 있으면 실행 가능, 재시도 가능 |
| 다운로드 실패 | `.part` 삭제, 실패 이력 전송 |
| 파일 크기 불일치 | ZIP 삭제, 실패 이력 전송 |
| SHA-256 없음 | ZIP 삭제, 실패 이력 전송 |
| SHA-256 불일치 | ZIP 삭제, 실패 이력 전송 |
| 압축 해제 실패 | 기존 버전 유지 |
| ZIP 내부 EXE 없음 | 설치 중단, 기존 버전 유지 |
| 정식 폴더 반영 실패 | 기존 버전 유지 |
| 설치 후 EXE 없음 | `current.json` 변경 전 중단 |
| `current.json` 저장 실패 | 예외 처리되어 업데이트 실패 |
| 버전 정리 실패 | 로그만 남기고 업데이트 성공 유지 |
| 다운로드 이력 API 실패 | 로그만 남기고 업데이트 결과 유지 |
| 프로그램 실행 실패 | 런처 유지, 실행·재시도 버튼 제공 |

업데이트 실패 시 기존 프로그램 폴더를 자동 삭제하지 않는다.

---

## 26. 런처 UI 상태 관리

`UiState`는 다음 값을 관리한다.

```text
busy
can_run
can_retry
percent
status
```

| 상태 | 실행 버튼 | 재시도 버튼 | 닫기 버튼 |
|---|---|---|---|
| 공지·업데이트 작업 중 | 비활성 | 비활성 | 비활성 |
| 최신 버전 준비 완료 | 활성 | 필요 시 활성 | 활성 |
| 업데이트 실패 + 기존 EXE 있음 | 활성 | 활성 | 활성 |
| 업데이트 실패 + 기존 EXE 없음 | 비활성 | 활성 | 활성 |
| 업데이트 설치 완료 직후 | 비활성 | 비활성 | 활성 후 자동 실행 |

작업 중에는 사용자가 런처를 닫을 수 없다.

```text
업데이트 중 닫기
    ↓
"업데이트 중에는 닫을 수 없습니다."
    ↓
닫기 취소
```

---

## 27. 로그

런처 화면의 각 로그 줄 앞에는 고객 PC의 현재 시간이 붙는다.

```text
[2026-07-18 19:00:00] [launcher] program_id=NAVER_BAND_MEMBER
[2026-07-18 19:00:00] [launcher] local_version=1.0.1
[2026-07-18 19:00:00] [launcher] launcher_version=1.0.1
[2026-07-18 19:00:01] [launcher] latest_version=1.0.2
```

주요 확인 항목:

- 프로그램 ID
- 현재 프로그램 버전
- 런처 버전
- API 서버 주소
- 최신 버전 조회 성공 여부
- 최신 버전
- R2 Presigned URL
- 다운로드 ID
- 다운로드 시작·종료 시각
- 다운로드 바이트 수
- 실제 SHA-256
- SHA-256 검증 결과
- 다운로드 이력 API 결과
- staging 경로
- 설치 대상 폴더
- `current.json` 갱신
- 오래된 버전 삭제
- 프로그램 실행 결과

Presigned URL에는 임시 인증 정보가 포함될 수 있다.  
운영 로그를 외부에 공유할 때는 `asset_url` 전체가 노출되지 않도록 주의한다.

---

## 28. 빌드 후 기본 구조

```text
dist/
└─ GB7Launcher/
   ├─ GB7Launcher.exe
   ├─ _internal/
   ├─ data/
   │  ├─ app.json
   │  ├─ current.json
   │  └─ notice_ack.json
   └─ versions/
      └─ v1_0_1/
         └─ CrawlProgram.exe
```

런처 실행 중 필요에 따라 다음 폴더가 추가된다.

```text
GB7Launcher/
├─ downloads_tmp/
└─ versions/
   └─ _staging/
```

---

## 29. 고객 전달 전 확인

### 고객별 설정

- `current.json`의 `program_id`가 구매 프로그램과 일치하는가
- `current.json`의 `version`이 포함된 프로그램 버전과 일치하는가
- `current.json`의 `server_url`이 운영 서버를 가리키는가
- `current.json`의 `launcher_key`가 해당 고객·프로그램용 키인가
- `app.json`의 `launcher_version`이 현재 런처 버전인가
- 공식 사이트와 문의 URL이 정상인가

### 프로그램 파일

- `versions/{현재 버전}`에 `CrawlProgram.exe`가 존재하는가
- 현재 프로그램이 런처에서 정상 실행되는가
- ZIP 내부에 `CrawlProgram.exe`가 존재하는가
- ZIP 파일명이 버전 규칙과 일치하는가

### 서버와 R2

- R2 객체 경로가 프로그램 ID와 버전 규칙에 맞는가
- `cloudflare.py` 검증이 모두 성공했는가
- 원본과 다운로드 파일 크기가 일치하는가
- 원본과 다운로드 SHA-256이 일치하는가
- 웹서버에 신규 릴리스가 등록되었는가
- 최신 버전 API가 올바른 버전과 `asset.url`을 반환하는가
- 발급된 런처 키로 최신 버전 API가 정상 호출되는가

### 실제 업데이트 테스트

- 구버전 고객 폴더에서 새 버전 안내가 표시되는가
- `지금 업데이트` 선택 시 다운로드가 시작되는가
- 진행률이 정상 표시되는가
- SHA-256 검증 후 설치되는가
- `current.json` 버전이 갱신되는가
- 새 버전이 자동 실행되는가
- 최신 2개 버전만 유지되는가
- 실패 시 기존 버전을 실행할 수 있는가
- 다운로드 성공·실패 이력이 서버에 저장되는가

---

## 30. 운영 배포 순서

```text
[관리자]
신규 프로그램 빌드
    ↓
버전 ZIP 생성
    ↓
Cloudflare R2 업로드
    ↓
cloudflare.py 설정 변경
    ↓
R2 크기·SHA-256 검증
    ↓
웹서버 릴리스 등록
    ↓
최신 버전 API 확인

[고객 신규 발급]
launcher_key_create.py 설정 변경
    ↓
고객별·프로그램별 키 발급
    ↓
current.json에 원본 키 저장
    ↓
런처 빌드 또는 고객 설정 반영
    ↓
고객 전달

[고객 실행]
GB7Launcher.exe 실행
    ↓
긴급 공지 확인
    ↓
런처 키 검증
    ↓
최신 버전 조회
    ↓
R2 Presigned URL 다운로드
    ↓
크기·SHA-256 검증
    ↓
설치 및 실행
    ↓
다운로드 이력 저장
```

---

## 31. 보안 운영 원칙

### 고객 런처에 포함해도 되는 값

- 고객에게 발급된 해당 프로그램용 `launcher_key`
- 공개 웹서버 주소
- 프로그램 ID
- 현재 프로그램 버전
- 런처 버전
- 공식 사이트와 문의 URL

### 고객 런처에 포함하면 안 되는 값

- R2 Access Key
- R2 Secret Key
- 관리자 API 키
- 릴리스 등록 API 키
- 다른 고객의 런처 키
- 서버 DB 접속 정보

### 관리자 전용 파일

다음 파일은 고객 배포물에 포함하지 않는다.

```text
launcher/etc/cloudflare.py
launcher/etc/launcher_key_create.py
```

### 소스 저장소 기준

관리자 키와 R2 자격 증명은 Python 파일에 직접 작성하지 않는 것이 원칙이다.

권장 방식:

```text
환경 변수
관리자 PC 전용 JSON
Git에서 제외한 로컬 설정 파일
비밀 관리 서비스
```

현재 소스 파일에 실제 사용 중인 자격 증명이 들어 있다면 다음 조치가 필요하다.

1. 노출된 키를 폐기하고 새 키로 교체한다.
2. Git 기록에 올라갔다면 기록에서도 제거한다.
3. 소스에는 예시값이나 환경 변수 이름만 남긴다.
4. 고객 배포 폴더에 `etc` 디렉터리가 포함되지 않는지 확인한다.

---

## 32. 현재 구현 기준 주의 사항

### `launcher_key_create.py` 안내 문구

현재 스크립트 출력에는 생성된 키를 `app.json`에 입력하라는 문구가 있을 수 있다.

실제 런처 소스가 읽는 위치는 다음과 같다.

```text
data/current.json
```

따라서 원본 키는 반드시 `current.json`의 `launcher_key`에 저장한다.

### 공지 API 인증

최신 버전 조회와 다운로드 이력 저장은 `X-Launcher-Key`를 사용한다.

현재 긴급 공지 API는 인증 헤더 없이 호출한다.

공지까지 고객별 접근 제한이 필요하면 공지 API에도 런처 키를 전달하도록 별도 수정해야 한다.

### 프로그램 ID 응답 비교

최신 버전 응답의 `programId` 필수 여부는 검사한다.

현재는 요청한 프로그램 ID와 응답의 프로그램 ID가 동일한지 비교하지 않는다.

### ZIP 압축 해제 보안

현재 압축 해제는 `ZipFile.extractall()`을 사용한다.

관리자가 직접 생성하고 SHA-256까지 검증한 신뢰된 ZIP만 등록한다는 운영 전제가 필요하다.

### 다운로드와 설치 이력 구분

현재 서버로 보내는 이력은 다운로드 검증 결과다.

설치 완료 여부까지 별도로 관리하려면 설치 이력 API 또는 추가 상태 필드가 필요하다.

---

## 33. 소스 프리징 기준

다음 조건을 만족한 버전을 프리징 대상으로 본다.

- 관리자 키 발급 API가 정상 동작한다.
- R2 검증과 릴리스 등록이 정상 동작한다.
- 최신 버전 API가 런처 키를 검증한다.
- 고객 런처가 최신 버전을 조회한다.
- R2 파일 다운로드가 정상 동작한다.
- 파일 크기와 SHA-256 검증이 정상 동작한다.
- staging 설치와 정식 폴더 반영이 정상 동작한다.
- `current.json` 갱신이 정상 동작한다.
- 현재 및 이전 버전 두 개만 유지된다.
- 업데이트 성공 후 새 프로그램이 자동 실행된다.
- 업데이트 실패 후 기존 프로그램을 실행할 수 있다.
- 긴급 공지와 오늘 하루 안보기가 정상 동작한다.
- 다운로드 이력이 서버에 저장된다.
- 관리자 전용 자격 증명이 고객 배포물에 포함되지 않는다.
- 실제 비밀키가 소스 저장소에 남아 있지 않다.

---

## 34. 최종 핵심 흐름

```text
관리자가 고객용 런처 키 생성
    ↓
관리자가 신규 프로그램 ZIP을 R2에 업로드
    ↓
관리자 도구가 R2 파일 크기와 SHA-256 검증
    ↓
검증 성공 후 웹서버에 릴리스 등록
    ↓
고객이 GB7Launcher.exe 실행
    ↓
긴급 공지 확인
    ↓
current.json의 launcher_key로 최신 버전 조회
    ↓
웹서버가 최신 활성 릴리스와 R2 Presigned URL 반환
    ↓
런처가 ZIP 다운로드
    ↓
파일 크기와 SHA-256 검증
    ↓
다운로드 결과 이력 전송
    ↓
staging 압축 해제
    ↓
CrawlProgram.exe 확인
    ↓
정식 버전 폴더 반영
    ↓
current.json 버전 갱신
    ↓
현재 버전과 직전 버전만 유지
    ↓
새 버전 자동 실행
    ↓
런처 종료
```