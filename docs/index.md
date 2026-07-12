# Crawl Program 개발 문서

Crawl Program의 전체 구조, 실행 흐름, 공통 모듈, 데이터 저장 방식과 신규 Target 추가 절차를 정리한 내부 개발 문서입니다.

---

## 프로그램 개요

Crawl Program은 Target별 설정에 따라 Worker를 실행하고 데이터를 수집하는 크롤링 프로그램입니다.

수집한 데이터는 SQLite에 저장하며, 필요한 경우 엑셀 파일로 출력합니다.

```text
main.py
    ↓
설정 파일 로드
    ↓
Worker 생성
    ↓
Repository 초기화
    ↓
데이터 수집
    ↓
SQLite 저장
    ↓
엑셀 생성
    ↓
작업 종료
```

---

## 문서 구성

### 프로그램 시작

* [main.py](main.md)

### Repository

* [WorkerDbRepository](src/repositories/worker_db_repository.md)

### Worker

* [ApiBaseWorker](src/workers/api_base_worker.md)

---

## 프로젝트 구조

```text
crawl-program/
├─ cmd/
├─ docs/
├─ history/
├─ launcher/
├─ logs/
├─ output/
├─ rawdata/
├─ resources/
├─ runtime/
├─ src/
├─ main.py
├─ mkdocs.yml
└─ site/
```

### `cmd`

일회성 크롤링, 데이터 변환, 테스트 및 보조 작업용 스크립트를 관리합니다.

정식 프로그램에 포함되지 않는 단독 실행 스크립트가 위치합니다.

```text
cmd/
├─ customers/
├─ main/
└─ tools/
```

---

### `docs`

MkDocs에서 사용하는 개발 문서 원본을 관리합니다.

실제 `src` 폴더 구조와 비슷하게 문서를 구성하고, 주요 Python 파일과 모듈의 역할 및 사용 방법을 설명합니다.

```text
docs/
├─ index.md
├─ main.md
└─ src/
   ├─ repositories/
   └─ workers/
```

코드의 세부 구현은 Python 코드와 docstring에 작성하고, 전체 구조와 실행 흐름은 `docs` 문서에 작성합니다.

---

### `history`

Target별 개발 이력과 배포 관련 문서를 관리합니다.

주요 관리 대상은 다음과 같습니다.

* 버전 변경 이력
* 고객별 작업 정보
* 테스트 내역
* 빌드 방법
* 배포 및 사용 설명서
* 릴리스 기록

```text
history/
├─ customers/<target>/
├─ releases/
├─ CHANGELOG.md
└─ GIT.md
```

---

### `launcher`

프로그램 버전 확인, 업데이트, 설치 및 실행을 담당하는 런처 소스입니다.

```text
launcher/
├─ core/
├─ data/
├─ ui/
├─ versions/
├─ workers/
└─ launcher_main.py
```

---

### `logs`

프로그램 실행 중 생성되는 로그 파일을 저장합니다.

```text
logs/
```

---

### `output`

크롤링 결과 엑셀, JSON 및 기타 결과 파일을 저장합니다.

```text
output/
```

---

### `rawdata`

개발 및 테스트 과정에서 사용하는 원본 HTML, JSON 등의 데이터를 저장합니다.

```text
rawdata/
├─ html/
└─ json/
```

---

### `resources`

Target별 데이터, DB 스키마, 지역 정보, 아이콘 등 프로그램에서 사용하는 정적 자원을 관리합니다.

```text
resources/
├─ customers/
│  ├─ common/
│  └─ <target>/
└─ icons/
```

현재 프로젝트 운영 정책상 `resources` 폴더는 Git 커밋 대상에서 제외합니다.

빌드에 필요한 파일은 로컬 환경에 별도로 존재해야 합니다.

---

### `runtime`

실행 시 사용하는 프로그램 설정 파일을 관리합니다.

```text
runtime/
├─ app.json
└─ customers/
   ├─ common/
   └─ <target>/
      └─ config.json
```

* `app.json`: 프로그램에 등록할 Target 목록
* `customers/<target>/config.json`: Target별 화면, Worker, DB, 컬럼 설정
* `customers/common`: 공통 실행 데이터

배포 시 실행 파일과 함께 복사해야 합니다.

---

### `src`

프로그램의 실제 소스 코드를 관리합니다.

```text
src/
├─ core/
├─ models/
├─ repositories/
├─ ui/
├─ utils/
├─ workers/
└─ app_manager.py
```

주요 역할은 다음과 같습니다.

| 경로                   | 역할                            |
| -------------------- | ----------------------------- |
| `src/core`           | 공통 서비스와 전역 상태                 |
| `src/models`         | 프로그램 데이터 모델                   |
| `src/repositories`   | SQLite 저장 및 조회                |
| `src/ui`             | 메인 화면과 팝업 UI                  |
| `src/utils`          | 파일, 엑셀, API, Selenium 등 공통 기능 |
| `src/workers`        | Target별 크롤링 Worker            |
| `src/app_manager.py` | 프로그램 실행 및 화면 관리               |

---

### `main.py`

Crawl Program의 시작 파일입니다.

프로그램 설정과 UI를 초기화하고 전체 애플리케이션을 실행합니다.

---

### `site`

MkDocs가 자동으로 생성하는 정적 사이트 결과물입니다.

```text
site/
├─ index.html
└─ assets/
```

`site` 폴더 내부 파일은 직접 수정하지 않습니다.

---

## DB 저장 구조

Crawl Program의 데이터는 다음 두 종류의 테이블로 저장합니다.

```text
공통 작업 이력 테이블
worker_job_hist
        ↓ hist_id
Target별 상세 테이블
<target>
```

### 공통 작업 이력 테이블

경로:

```text
resources/customers/common/db/schema_hist.sql
```

테이블:

```text
worker_job_hist
```

Worker 작업 한 번당 하나의 이력을 저장합니다.

주요 저장 정보:

* 작업 ID
* Target 및 Worker 정보
* 작업 시작·종료 시간
* 작업 상태
* 전체·성공·실패 건수
* 대표 오류 메시지
* 작업자 정보

작업 상태는 다음 값을 사용합니다.

```text
READY
RUNNING
SUCCESS
FAIL
STOP
```

---

### Target별 상세 테이블

경로:

```text
resources/customers/<target>/db/schema_detail.sql
```

크롤링 결과 한 건당 상세 테이블에 한 행을 저장합니다.

상세 테이블은 다음 영역으로 구성합니다.

```text
공통 작업 정보
행 단위 처리 상태
Target별 수집 데이터
공통 생성·수정 정보
```

공통 컬럼 예시:

```text
detail_id
hist_id
site_name
worker_name
table_name
job_id
user_id

row_status
row_error_message
row_start_at
row_end_at

created_at
updated_at
```

Target를 추가할 때는 공통 컬럼을 유지하고, Target별 수집 데이터 영역만 변경합니다.

예를 들어 `yeogi_admin`은 다음 판매자 정보 컬럼을 사용합니다.

```text
business_name
representative_name
address
phone
email
business_number
search_keyword
url
```

```sql
-- 여기어때 판매자 정보
business_name TEXT,
representative_name TEXT,
address TEXT,
phone TEXT,
email TEXT,
business_number TEXT,
search_keyword TEXT,
url TEXT
```

Target별 데이터 컬럼은 반드시 다음 세 곳에서 동일하게 맞춥니다.

```text
config.json의 columns[].code
Worker가 반환하는 결과 Dictionary의 key
schema_detail.sql의 컬럼명
```

---

## 신규 Target 추가

새로운 크롤링 Target을 추가할 때 `<target>`과 `<TARGET_KEY>`를 실제 이름으로 변경합니다.

```text
<target>     → yeogi_admin
<TARGET_KEY> → YEOGI_ADMIN
```

---

### 1. DB 스키마 생성

다음 경로에 상세 데이터 저장용 SQL 파일을 생성합니다.

```text
resources/customers/<target>/db/schema_detail.sql
```

공통 작업 정보와 행 처리 상태 컬럼은 기존 Target 스키마를 기준으로 유지합니다.

Target별로 변경되는 부분은 수집 데이터 컬럼입니다.

```sql
-- Target별 수집 데이터
target_column_1 TEXT,
target_column_2 TEXT
```

---

### 2. Worker 생성

다음 경로에 Target Worker를 생성합니다.

```text
src/workers/main/api_<target>_set_worker.py
```

예시:

```text
src/workers/main/api_yeogi_admin_set_worker.py
```

Worker 클래스 예시:

```python
class ApiYeogiAdminSetWorker(BaseApiWorker):
    pass
```

Worker에서 반환하는 데이터 키는 `config.json`과 `schema_detail.sql`의 컬럼명과 동일해야 합니다.

---

### 3. Target 설정 생성

다음 경로에 Target 설정 파일을 생성합니다.

```text
runtime/customers/<target>/config.json
```

기본 구조:

```json
{
  "label": "화면 표시명",
  "key": "<TARGET_KEY>",
  "db_name": "<TARGET_KEY>",
  "db_common_name": "WORKER_JOB_HIST",
  "enabled": true,
  "worker_class": "src.workers.main.api_<target>_set_worker:<WorkerClass>",
  "setting": [],
  "columns": [],
  "search_col_list": []
}
```

핵심 확인 사항:

* `key`, `db_name`, `app.json`의 `key`를 동일하게 설정합니다.
* `worker_class`에 실제 모듈 및 클래스 경로를 입력합니다.
* `columns[].code`는 Worker 결과 키와 DB 컬럼명에 맞춥니다.
* `search_col_list`에는 실제 검색에 사용할 컬럼만 등록합니다.

---

### 4. app.json 등록

`runtime/app.json`의 `site_list`에 Target을 추가합니다.

기본 화면에 노출할 경우 `site_list_use`에도 Target Key를 추가합니다.

```json
{
  "site_list_use": [
    "<TARGET_KEY>"
  ],
  "site_list": [
    {
      "key": "<TARGET_KEY>",
      "config_path": "customers/<target>/config.json"
    }
  ]
}
```

기존 Target이 있는 개발 환경에서는 기존 배열을 유지하고 새 항목만 추가합니다.

배포용 `app.json`은 실행할 Target만 남깁니다.

---

### 5. 문서 및 이력 생성

필요한 경우 다음 경로에 Worker 문서를 작성합니다.

```text
docs/src/workers/main/api_<target>_set_worker.md
```

Target별 이력과 빌드 정보는 다음 경로에서 관리합니다.

```text
history/customers/<target>/
├─ HISTORY.md
├─ README.md
├─ TEST.md
└─ 설명서.md
```

---

## 프로그램 빌드

프로젝트 루트에서 PyInstaller를 실행합니다.

```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "<target>" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\history\customers\<target>\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_<target>_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\<target>\db\schema_detail.sql;resources\customers\<target>\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"
```

콘솔 로그를 직접 확인해야 하는 테스트 빌드는 `--windowed` 대신 `--console`을 사용합니다.

---

### 전국 지역 데이터 사용

전국 지역 데이터를 사용하는 Target은 다음 리소스를 추가합니다.

```powershell
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all"
```

---

### 빌드 후 Runtime 복사

빌드가 완료되면 다음 Runtime 파일을 실행 파일 경로에 복사합니다.

```text
runtime/
├─ app.json
└─ customers/
   ├─ common/
   └─ <target>/
      └─ config.json
```

배포용 `runtime/app.json`에는 해당 Target만 등록합니다.

```json
{
  "site_list_use": [
    "<TARGET_KEY>"
  ],
  "site_list": [
    {
      "key": "<TARGET_KEY>",
      "config_path": "customers/<target>/config.json"
    }
  ]
}
```

---

## 개발 문서 서버 실행

프로젝트 루트에서 다음 명령을 실행합니다.

```powershell
cd E:\git\crawl-program
python -m mkdocs serve --livereload -f .\mkdocs.yml
```

정상적으로 실행되면 다음 주소로 접속합니다.

```text
http://127.0.0.1:8000/
```

`docs` 폴더의 Markdown 파일을 수정하고 저장하면 문서가 자동으로 다시 빌드됩니다.

```text
Markdown 수정
    ↓
Ctrl + S
    ↓
MkDocs 변경 감지
    ↓
브라우저 반영
```

개발 서버 종료:

```text
Ctrl + C
```

---

## 정적 사이트 생성

직원 공유 또는 정적 서버 배포용 사이트를 생성합니다.

```powershell
python -m mkdocs build -f .\mkdocs.yml
```

생성 결과는 프로젝트 루트의 `site` 폴더에 저장됩니다.

```text
site/
├─ index.html
└─ assets/
```

---

## 자주 사용하는 명령어

### 개발 문서 실행

```powershell
python -m mkdocs serve --livereload -f .\mkdocs.yml
```

### 정적 사이트 생성

```powershell
python -m mkdocs build -f .\mkdocs.yml
```

### MkDocs 버전 확인

```powershell
python -m mkdocs --version
```

### Material 설치 확인

```powershell
python -m pip show mkdocs-material
```

---

## 문서 작성 규칙

* 실제 코드와 유사한 폴더 구조로 문서를 구성합니다.
* Python 코드를 `docs` 폴더에 복사하지 않습니다.
* 주요 Python 파일과 같은 이름의 Markdown 문서를 작성합니다.
* 클래스와 함수의 상세 설명은 코드 docstring에 작성합니다.
* 전체 구조, 실행 흐름, 설정 및 사용 방법은 MkDocs 문서에 작성합니다.
* 고객별 변경 이력과 빌드 방법은 `history`에서 관리합니다.

예시:

```text
실제 코드
src/repositories/worker_db_repository.py

대응 문서
docs/src/repositories/worker_db_repository.md
```
