# Launcher

## 1. 목적

GB7 Launcher는 고객 PC에서 프로그램의 공지와 최신 버전을 확인하고, 필요한 경우 새 버전을 내려받아 설치한 뒤 프로그램을 실행하는 전용 런처이다.

이 문서는 런처 전체 구조와 실행 흐름, 빌드 및 운영 기준만 정리한다.  
각 Python 파일의 세부 구현은 파일별 문서에서 관리한다.

---

## 2. 실행 위치

런처 관련 명령은 프로젝트 최상위 경로에서 실행한다.

```text
E:\git\crawl-program
```

### 로컬 실행

```powershell
(venv) PS E:\git\crawl-program> python -m launcher.launcher_main
```

패키지 import 구조를 사용하므로 아래처럼 파일을 직접 실행하지 않는다.

```powershell
python .\launcher\launcher_main.py
```

### 런처 빌드

```powershell
(venv) PS E:\git\crawl-program> .\build_launcher.ps1
```

빌드 스크립트는 프로젝트 최상위 경로를 기준으로 런처와 현재 프로그램 파일을 구성한다.

---

## 3. 주요 디렉터리 구조

```text
crawl-program/
├─ launcher/
│  ├─ launcher_main.py
│  ├─ core/
│  ├─ ui/
│  ├─ workers/
│  ├─ data/
│  │  ├─ app.json
│  │  ├─ current.json
│  │  └─ notice_ack.json
│  └─ img/
├─ dist/
├─ build/
└─ build_launcher.ps1
```

빌드 완료 후 기본 구조는 다음과 같다.

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

---

## 4. 설정 파일

### `data/current.json`

현재 실행 대상과 버전 API 정보를 관리한다.

```json
{
  "version": "1.0.1",
  "program_id": "NAVER_BAND_MEMBER",
  "server_url": "https://goodbye772.com"
}
```

| 항목 | 내용 |
|---|---|
| `version` | 현재 고객 PC에 설치된 프로그램 버전 |
| `program_id` | 서버에서 프로그램을 구분하는 ID |
| `server_url` | 최신 버전 및 공지 정보를 조회할 API 서버 주소 |

`server_url`은 ZIP 파일 주소가 아니다.  
실제 ZIP 다운로드 주소는 최신 버전 API 응답의 `asset.url`에서 전달받는다.

### `data/app.json`

공식 사이트와 문의 페이지 주소를 관리한다.

```json
{
  "support": {
    "site_url": "https://goodbye772.com",
    "qna_url": "https://goodbye772.com/faq"
  }
}
```

### `data/notice_ack.json`

긴급 공지의 `오늘 하루 안보기` 상태를 저장한다.

빌드 시에는 빈 JSON으로 다시 생성한다.

```json
{
  "N-20260716-001": 1784214000
}
```

---

## 5. 런처 사용 API 목록

현재 런처가 직접 사용하는 서버 통신은 다음과 같다.

| 구분 | 방식 | 주소 | 용도 |
|---|---|---|---|
| 최신 버전 조회 | `GET` | `{server_url}/launcher/api/v1/programs/{program_id}/latest` | 최신 버전과 다운로드 파일 정보 조회 |
| 긴급 공지 조회 | `GET` | `{server_url}/launcher/api/v1/programs/{program_id}/notices/latest/critical` | 최신 긴급 공지 1건 조회 |
| 업데이트 파일 확인 | `HEAD` 또는 `GET` | 최신 버전 응답의 `asset.url` | ZIP 파일 접근 가능 여부 확인 |
| 업데이트 파일 다운로드 | `GET` | 최신 버전 응답의 `asset.url` | ZIP 파일 다운로드 |

`asset.url`은 고정된 런처 API 주소가 아니다.  
최신 버전 조회 API가 반환한 주소를 그대로 사용한다.

### 5.1 최신 버전 조회 API

```text
GET {server_url}/launcher/api/v1/programs/{program_id}/latest
```

실제 예:

```text
GET https://goodbye772.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/latest
```

PowerShell 확인:

```powershell
curl.exe `
  -H "Accept: application/json" `
  "https://goodbye772.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/latest"
```

정상 응답 예:

```json
{
  "program_id": "NAVER_BAND_MEMBER",
  "latest_version": "1.0.2",
  "asset": {
    "url": "https://goodbye772.com/downloads/NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip",
    "sha256": "파일 SHA-256 값",
    "size": 157286400
  }
}
```

| 응답 항목 | 내용 |
|---|---|
| `program_id` | 조회한 프로그램 ID |
| `latest_version` | 서버의 최신 버전 |
| `asset.url` | 실제 ZIP 다운로드 주소 |
| `asset.sha256` | ZIP 파일 무결성 검증 값 |
| `asset.size` | ZIP 파일 크기 |

필수 확인 항목:

- HTTP 상태가 `200`인지 확인
- `program_id`가 요청한 프로그램과 일치하는지 확인
- `latest_version`이 `x.y.z` 형식인지 확인
- 새 버전인 경우 `asset.url`이 존재하는지 확인
- `asset.url`이 실제 ZIP 파일에 접근 가능한지 확인

### 5.2 긴급 공지 조회 API

```text
GET {server_url}/launcher/api/v1/programs/{program_id}/notices/latest/critical
```

실제 예:

```text
GET https://goodbye772.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/notices/latest/critical
```

PowerShell 확인:

```powershell
curl.exe `
  -H "Accept: application/json" `
  "https://goodbye772.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/notices/latest/critical"
```

긴급 공지가 있는 경우 응답 예:

```json
{
  "id": "N-20260716-001",
  "level": "CRITICAL",
  "force": true,
  "title": "긴급 점검 안내",
  "content": "서비스 점검 관련 안내 내용입니다."
}
```

서버에서 `notice` 객체로 한 번 감싸서 반환해도 처리할 수 있다.

```json
{
  "notice": {
    "id": "N-20260716-001",
    "level": "CRITICAL",
    "force": true,
    "title": "긴급 점검 안내",
    "content": "서비스 점검 관련 안내 내용입니다."
  }
}
```

긴급 공지가 없는 경우:

```text
HTTP 204 No Content
```

| 응답 항목 | 내용 |
|---|---|
| `id` | 공지 고유 ID |
| `level` | `CRITICAL`, `IMPORTANT`, `INFO` |
| `force` | 강제 또는 긴급 표시 여부 |
| `title` | 공지 제목 |
| `content` | 공지 내용 |

런처는 다음 조건 중 하나를 만족하면 긴급 공지로 표시한다.

- `force == true`
- `level == CRITICAL`

### 5.3 업데이트 파일 확인

최신 버전 API 응답의 `asset.url`이 실제로 접근 가능한지 확인한다.

```powershell
curl.exe -I `
  "https://goodbye772.com/downloads/NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip"
```

서버가 `HEAD` 요청을 지원하지 않는 경우 런처는 실제 `GET` 다운로드 단계에서 다시 확인한다.

확인 항목:

- HTTP 상태가 정상인지 확인
- 파일 주소가 로그인 페이지나 오류 페이지로 연결되지 않는지 확인
- 응답 파일이 실제 ZIP인지 확인
- 서버 응답 크기와 `asset.size`가 일치하는지 확인

### 5.4 업데이트 파일 다운로드

PowerShell 수동 다운로드 예:

```powershell
curl.exe -L `
  -o v1_0_2.zip `
  "https://goodbye772.com/downloads/NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip"
```

런처에서는 다운로드 중 다음 임시 파일을 사용한다.

```text
downloads_tmp/{다운로드 파일명}.part
```

다운로드가 정상 완료된 경우에만 `.part`를 정식 ZIP 파일명으로 변경한다.

### 5.5 지원 페이지 주소

공식 사이트와 문의 페이지는 API가 아니라 사용자의 기본 브라우저로 여는 운영 URL이다.

설정 위치:

```text
launcher/data/app.json
```

런처는 다음 정보를 쿼리 파라미터로 추가한다.

| 항목 | 내용 |
|---|---|
| `program` | 프로그램 ID |
| `ver` | 현재 버전 |
| `os` | 운영체제 이름 |
| `osver` | 운영체제 버전 |

예:

```text
https://goodbye772.com?program=NAVER_BAND_MEMBER&ver=1.0.1&os=Windows&osver=...
```

```text
https://goodbye772.com/faq?program=NAVER_BAND_MEMBER&ver=1.0.1&os=Windows&osver=...
```

### 5.6 API 문제 확인 순서

API 또는 다운로드 오류가 발생하면 다음 순서로 확인한다.

```text
current.json의 server_url 확인
    ↓
program_id 확인
    ↓
최신 버전 API 직접 호출
    ↓
공지 API 직접 호출
    ↓
최신 버전 응답의 asset.url 확인
    ↓
asset.url HEAD 또는 GET 확인
    ↓
ZIP 파일 직접 다운로드
    ↓
ZIP 내부 CrawlProgram.exe 확인
```

---

## 6. 전체 실행 흐름

```text
GB7Launcher.exe 실행
        ↓
스플래시 화면 표시
        ↓
런처 메인 화면 표시
        ↓
current.json 읽기
        ↓
긴급 공지 조회
        ↓
최신 버전 조회
        ↓
버전 비교
        ↓
현재 버전 실행 또는 업데이트
```

---

## 7. 긴급 공지 흐름

런처 시작 시 최신 긴급 공지를 먼저 확인한다.

```text
공지 API 조회
    ↓
긴급 공지 없음
    └─ 업데이트 확인으로 이동

긴급 공지 있음
    ↓
오늘 하루 안보기 여부 확인
    ↓
공지 팝업 표시 또는 자동 표시 생략
    ↓
업데이트 확인으로 이동
```

긴급 공지는 다음 조건 중 하나를 만족하면 표시한다.

- `force == true`
- `level == CRITICAL`

자동 팝업을 숨긴 경우에도 런처의 `긴급 공지 다시 보기` 버튼으로 다시 열 수 있다.

---

## 8. 최신 버전 조회 흐름

런처는 다음 API를 호출하여 최신 버전 정보를 조회한다.

```text
{server_url}/launcher/api/v1/programs/{program_id}/latest
```

예:

```text
https://goodbye772.com/launcher/api/v1/programs/NAVER_BAND_MEMBER/latest
```

서버 응답 예:

```json
{
  "program_id": "NAVER_BAND_MEMBER",
  "latest_version": "1.0.2",
  "asset": {
    "url": "https://goodbye772.com/downloads/NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip",
    "sha256": "...",
    "size": 157286400
  }
}
```

런처는 `asset.url`을 그대로 사용하여 ZIP 파일을 내려받는다.

Cloudflare R2를 사용하는 경우에도 런처 코드는 변경하지 않고 서버가 반환하는 `asset.url`만 R2 주소로 변경한다.

---

## 9. 버전 비교 결과

### 현재 버전과 최신 버전이 동일한 경우

```text
준비 완료
→ 사용자가 실행 버튼 클릭
→ 현재 프로그램 실행
→ 런처 종료
```

### 로컬 버전이 서버 버전보다 높은 경우

다운그레이드는 하지 않고 현재 설치된 버전을 실행 대상으로 사용한다.

### 새 버전이 있는 경우

업데이트 안내 팝업을 표시한다.

| 사용자 동작 | 결과 |
|---|---|
| `지금 업데이트` | 업데이트 완료 후 새 버전 자동 실행 |
| `현재 버전 실행` | 현재 설치된 버전 즉시 실행 |
| 팝업 `X` 또는 `Esc` | 자동 실행하지 않고 런처 화면 유지 |

---

## 10. 업데이트 설치 흐름

```text
최신 버전 확인
    ↓
asset.url 접근 확인
    ↓
ZIP 다운로드
    ↓
staging 폴더에 압축 해제
    ↓
CrawlProgram.exe 존재 확인
    ↓
정식 버전 폴더로 이동
    ↓
current.json 버전 갱신
    ↓
임시 파일 정리
    ↓
이전 버전 정리
    ↓
새 버전 자동 실행
    ↓
런처 종료
```

### 임시 다운로드 위치

```text
GB7Launcher/downloads_tmp/
```

다운로드 중에는 `.part` 파일을 사용하고, 다운로드가 성공한 경우에만 정식 ZIP 파일로 변경한다.

### 압축 해제 위치

```text
GB7Launcher/versions/_staging/{program_id}/{version}/
```

압축 해제와 실행 파일 검증이 끝난 후 정식 버전 폴더로 이동한다.

### 정식 설치 위치

```text
GB7Launcher/versions/v1_0_2/
```

---

## 11. 버전 보관 정책

고객 PC에는 최신 버전과 바로 이전 버전, 총 2개만 유지한다.

```text
versions/
├─ v1_0_4
└─ v1_0_5
```

새 버전 설치와 `current.json` 갱신이 성공한 뒤 오래된 버전을 삭제한다.

버전 정리 실패는 업데이트 전체 실패로 처리하지 않고 로그만 남긴다.

---

## 12. 실패 및 재시도 정책

업데이트 실패 시 기존 프로그램 파일은 유지한다.

| 상황 | 처리 |
|---|---|
| 최신 버전 API 실패 | 재시도 가능 |
| ZIP URL 접근 실패 | 재시도 가능 |
| 다운로드 실패 | `.part` 파일 정리 후 재시도 가능 |
| 압축 해제 실패 | 다음 재시도 시 기존 staging 제거 |
| ZIP 안에 실행 파일 없음 | 설치 중단 후 기존 버전 유지 |
| 설치 반영 실패 | 기존 버전 유지 |
| 업데이트 실패 + 기존 EXE 존재 | `재시도`, `실행` 버튼 활성화 |
| 기존 EXE도 없음 | `재시도`만 활성화 |

오류가 발생한 경우 자동으로 기존 프로그램을 실행하지 않는다.  
사용자가 로그를 확인한 뒤 직접 재시도하거나 현재 버전을 실행한다.

---

## 13. 프로그램 실행 정책

| 상태 | 실행 방식 |
|---|---|
| 업데이트 설치 성공 | 새 버전 자동 실행 |
| `현재 버전 실행` 선택 | 현재 버전 즉시 실행 |
| 최신 버전 상태 | 실행 버튼을 눌러 실행 |
| 업데이트 팝업 취소 | 실행 버튼을 눌러 실행 |
| 업데이트 오류 | 기존 EXE가 있으면 실행 버튼으로 실행 |

프로그램 실행이 성공하면 런처는 종료되고 실제 프로그램 프로세스는 독립적으로 유지된다.

---

## 14. 로그

런처 화면의 로그는 각 줄 앞에 시간을 표시한다.

```text
[2026-07-16 11:06:04] [launcher] program_id=NAVER_BAND_MEMBER
[2026-07-16 11:06:04] [launcher] local_version=1.0.1
[2026-07-16 11:06:05] [launcher] latest_version=1.0.2
```

로그는 다음 내용을 확인하는 용도로 사용한다.

- 현재 프로그램 ID와 버전
- API 서버 주소
- 최신 버전 조회 결과
- 실제 ZIP 다운로드 주소
- 다운로드 및 압축 해제 결과
- 설치 위치
- `current.json` 갱신 결과
- 이전 버전 삭제 결과
- 프로그램 실행 결과

---

## 15. 빌드 흐름

`build_launcher.ps1`은 다음 작업을 수행한다.

```text
current.json 읽기
    ↓
program_id와 현재 버전 확인
    ↓
기존 GB7Launcher 빌드 폴더 삭제
    ↓
PyInstaller onedir 빌드
    ↓
data, versions 폴더 생성
    ↓
app.json, current.json 복사
    ↓
notice_ack.json 빈 파일 생성
    ↓
현재 프로그램 빌드 결과를 버전 폴더에 복사
```

현재 프로그램 빌드 결과의 기본 위치:

```text
dist/{program_id}/
```

런처 내부 복사 위치:

```text
dist/GB7Launcher/versions/{현재 버전 폴더}/
```

예:

```text
dist/NAVER_BAND_MEMBER/
→ dist/GB7Launcher/versions/v1_0_1/
```

---

## 16. 운영 배포 전 확인

- `current.json`의 `program_id`가 실제 프로그램과 일치하는지 확인
- `current.json`의 `version`이 포함된 프로그램 버전과 일치하는지 확인
- `server_url`에서 최신 버전 API와 공지 API가 정상 응답하는지 확인
- 서버의 `asset.url`이 실제 ZIP 파일을 가리키는지 확인
- ZIP 내부에 `CrawlProgram.exe`가 포함되어 있는지 확인
- 빌드 결과의 `versions/{현재 버전}` 폴더에 프로그램 파일이 존재하는지 확인
- 업데이트 완료 후 새 버전이 자동 실행되는지 확인
- 업데이트 실패 후 기존 버전 실행과 재시도가 가능한지 확인
- 버전 폴더가 최신 2개만 유지되는지 확인

---

## 17. 개발 및 운영 원칙

- 런처는 버전 조회, 다운로드, 설치, 실행만 담당한다.
- ZIP 주소는 런처에서 직접 생성하지 않고 서버 응답을 사용한다.
- 다운로드 파일은 임시 경로에 저장한 뒤 검증 후 설치한다.
- 업데이트 실패 시 현재 사용 가능한 버전을 손상시키지 않는다.
- 고객 설정과 작업 데이터는 버전 폴더와 분리하여 관리한다.
- 세부 구현은 각 Python 파일별 문서에서 관리하고, 이 문서는 전체 흐름만 유지한다.

---

## TODO — 런처 다운로드 인증 및 업데이트 기간 관리

> 작성일: 2026-07-17

현재는 `program_id`와 다운로드 URL을 알면 최신 버전 조회와 업데이트 파일 다운로드가 가능하다.

추후에는 고객에게 프로그램을 전달할 때 **고객별·프로그램별 런처 인증키**를 함께 발급하고, 런처의 최신 버전 조회 및 다운로드 요청에서 해당 키를 검증하도록 변경한다.

### 적용 목적

- 허가된 고객만 최신 버전 조회 가능
- 허가된 고객만 업데이트 파일 다운로드 가능
- 고객별로 사용 가능한 프로그램 구분
- 문제 발생 시 해당 인증키를 직접 비활성화하거나 삭제
- 업데이트 제공 기간이 끝난 고객의 신규 업데이트 차단
- 프로그램 복제본이 유출되어도 실제 사용은 기존 로그인에서 차단

### 권한 구분

```text
런처 인증키
    → 최신 버전 조회 및 업데이트 다운로드 권한 관리

프로그램 로그인
    → 실제 프로그램 사용 권한 관리

동시 로그인 제한
    → 한 계정의 동시 사용 방지
```

현재 프로그램 로그인은 동시 로그인 1개로 제한되어 있으므로, 프로그램 폴더가 다른 사람에게 복제되더라도 정상 계정으로 로그인하지 못하면 실제 사용은 제한된다.

### 인증키 발급 기준

인증키는 프로그램 전체가 함께 사용하는 공통키보다 **고객별·프로그램별**로 발급한다.

```text
고객 A + NAVER_BAND_MEMBER → KEY-A1
고객 B + NAVER_BAND_MEMBER → KEY-B1
고객 A + NAVER_PLACE       → KEY-A2
```

문제가 발생한 고객의 키만 서버 DB에서 비활성화하거나 삭제할 수 있도록 관리한다.

### 요청 방식

최신 버전 조회와 다운로드는 `GET` 방식을 유지한다.

인증키는 URL 쿼리 파라미터에 넣지 않고 HTTP 헤더로 전달한다.

```http
GET /launcher/api/v1/programs/NAVER_BAND_MEMBER/latest
X-Launcher-Key: 고객별-프로그램별-인증키
```

다운로드도 동일한 인증키를 검증한다.

```http
GET /launcher/api/v1/programs/NAVER_BAND_MEMBER/download/1.0.2
X-Launcher-Key: 고객별-프로그램별-인증키
```

### 업데이트 기간 관리

프로그램 실행 권한과 업데이트 제공 기간은 분리한다.

```text
프로그램 실행
    → 로그인 계정이 정상인 동안 가능

신규 업데이트
    → 업데이트 제공 기간 안에서만 가능
```

업데이트 기간이 만료된 경우에도 이미 설치된 기존 버전은 실행할 수 있게 유지한다.

```text
update_expired_at 이전
    → 최신 버전 조회 및 다운로드 가능

update_expired_at 이후
    → 신규 업데이트 차단
    → 기존 설치 버전 실행 가능
```

초기 운영 단계에서는 만료일 없이 인증키의 활성 상태만 관리할 수 있다.

추후 유지보수 또는 업데이트 비용 정책이 확정되면 `update_expired_at`을 적용한다.

### 예상 관리 항목

```text
launcher_key
customer_id
program_id
use_yn
update_expired_at
created_at
last_access_at
```

| 항목 | 내용 |
|---|---|
| `launcher_key` | 고객별·프로그램별 런처 인증키 |
| `customer_id` | 인증키를 발급받은 고객 |
| `program_id` | 업데이트가 허용된 프로그램 |
| `use_yn` | 인증키 사용 여부 |
| `update_expired_at` | 업데이트 제공 만료일 |
| `created_at` | 인증키 발급일 |
| `last_access_at` | 마지막 최신 버전 조회 또는 다운로드 일시 |

### 최종 적용 흐름

```text
고객에게 프로그램 전달
    ↓
고객별·프로그램별 인증키 발급
    ↓
런처가 program_id와 인증키 전달
    ↓
서버에서 키 상태와 프로그램 권한 확인
    ↓
업데이트 기간 확인
    ↓
최신 버전 조회 및 다운로드 허용
    ↓
프로그램 실행 후 기존 로그인 인증
```

### 운영 기준

- 인증키는 업데이트 권한만 관리한다.
- 실제 프로그램 사용 여부는 기존 로그인에서 관리한다.
- 동시 로그인은 현재와 같이 1개로 제한한다.
- 문제가 발생하면 해당 인증키 또는 사용자 계정을 직접 비활성화한다.
- 업데이트 만료 후에도 이미 설치된 버전은 계속 실행할 수 있게 한다.
- 모든 인증키 전송과 파일 다운로드는 HTTPS 환경에서 처리한다.