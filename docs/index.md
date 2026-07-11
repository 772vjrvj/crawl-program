# Crawl Program 개발 문서

크롤링 프로그램의 구조, 실행 흐름, 공통 모듈 및 데이터 저장 방식을 정리한 내부 개발 문서입니다.

---

## 프로그램 개요

Crawl Program은 설정에 따라 Worker를 실행하고 데이터를 수집한 뒤, 수집 결과를 SQLite에 저장하고 엑셀 파일로 출력하는 프로그램입니다.

## 전체 실행 흐름

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

---

## 프로젝트 구조

```text
crawl-program/
├─ main.py
├─ src/
│  ├─ repositories/
│  ├─ utils/
│  └─ workers/
│
├─ docs/
│  ├─ index.md
│  ├─ main.md
│  └─ src/
│     └─ repositories/
│        └─ worker_db_repository.md
│
├─ mkdocs.yml
└─ site/
```

`docs` 폴더는 Markdown 문서 원본을 관리합니다.

`site` 폴더는 MkDocs가 자동으로 생성하는 정적 사이트 결과물입니다.
`site` 폴더 내부 파일은 직접 수정하지 않습니다.

---

## 개발 문서 서버 실행

프로젝트 루트에서 다음 명령을 실행합니다.

```powershell
cd E:\git\crawl-program
python -m mkdocs serve --livereload -f .\mkdocs.yml
```

정상적으로 실행되면 터미널에 다음과 같은 로그가 표시됩니다.

```text
Watching paths for changes: 'docs', 'mkdocs.yml'
Serving on http://127.0.0.1:8000/
```

브라우저에서 다음 주소로 접속합니다.

```text
http://127.0.0.1:8000/
```

---

## 문서 수정 반영

개발 서버가 실행 중인 상태에서 `docs` 폴더의 Markdown 파일을 수정하고 저장하면 자동으로 다시 빌드됩니다.

```text
Markdown 파일 수정
    ↓
Ctrl + S 저장
    ↓
MkDocs 변경 감지
    ↓
문서 자동 재빌드
    ↓
브라우저 자동 반영
```

자동으로 화면이 갱신되지 않으면 브라우저에서 `Ctrl + R`을 누릅니다.

서버를 다시 실행할 필요는 없습니다.

---

## 개발 서버 종료

MkDocs를 실행한 터미널에서 다음 키를 누릅니다.

```text
Ctrl + C
```

---

## 정적 사이트 생성

직원들과 공유하거나 정적 서버에 배포할 때는 다음 명령을 실행합니다.

```powershell
python -m mkdocs build -f .\mkdocs.yml
```

빌드가 완료되면 프로젝트 루트의 `site` 폴더에 정적 HTML 파일이 생성됩니다.

```text
site/
├─ index.html
├─ assets/
├─ main/
└─ src/
```

생성된 `site` 폴더를 Nginx, Apache 또는 기타 정적 웹 서버에 배포할 수 있습니다.

---

## 자주 사용하는 명령어

### 개발 문서 서버 실행

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

### 설치된 Material 확인

```powershell
python -m pip show mkdocs-material
```

---

## 문서 작성 규칙

* 실제 코드 구조와 유사한 폴더 구조로 문서를 구성합니다.
* 코드 파일은 `docs` 폴더에 복사하지 않습니다.
* 코드 파일과 같은 이름의 Markdown 문서를 작성합니다.
* 클래스와 함수 설명은 코드의 docstring에 작성합니다.
* 전체 구조, 실행 흐름, 사용 방법은 `docs` 문서에 작성합니다.

예시:

```text
실제 코드
src/repositories/worker_db_repository.py

대응 문서
docs/src/repositories/worker_db_repository.md
```
****