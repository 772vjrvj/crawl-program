# WorkerDbRepository

## 코드 위치

```text
src/repositories/worker_db_repository.py
```

## 연동 Worker 예시

```text
src/workers/main/api_naver_place_loc_all_set_worker.py
```

---

## 1. 개요

`WorkerDbRepository`는 크롤링 Worker에서 공통으로 사용하는 SQLite 저장소 클래스입니다.

Worker는 **데이터 수집과 성공/실패 판단**을 담당하고,  
Repository는 **DB 저장, 작업 이력, 집계, 조회**를 담당합니다.

```text
Worker
    → 데이터 수집
    → 행 상태 결정

WorkerDbRepository
    → DB 저장
    → 작업 이력 관리
    → 성공/실패 집계
    → 엑셀용 데이터 변환
```

---

## 2. 주요 역할

- SQLite 연결 및 종료
- 스키마 초기화
- 작업 시작/종료 이력 저장
- Detail 성공 행 저장
- Detail 실패 행 저장
- 행 시작시간/종료시간 저장
- 성공/실패 건수 집계
- Detail 데이터 조회
- 엑셀용 컬럼명 변환

---

## 3. 전체 처리 흐름

```text
Worker 시작
    ↓
Repository 생성
    ↓
initialize(..., start_job=True)
    ↓
worker_job_hist 시작 이력 생성
    ↓
상세조회 1건 처리
    ├─ 성공 → SUCCESS 행 저장
    └─ 실패 → FAIL 행 저장
    ↓
Worker 최종 상태 설정
    ↓
Repository.finish_job()
    ↓
worker_job_hist 최종 업데이트
    ↓
필요 시 엑셀 생성
    ↓
Repository.close()
```

---

## 4. Repository 생성 예시

```python
self.db_repository = WorkerDbRepository(
    db_path=self.get_runtime_db_path(),
    site_name=self.site_name,
    worker_name=self.worker_name,
    detail_table_name=self.detail_table_name,
    column_defs=column_defs,
    user_id=self.user,
    log_func=self.log_signal_func,
    detail_log_fields=("id", "name"),
)
```

초기화:

```python
schema_files = [
    "resources/customers/common/db/schema_hist.sql",
    "resources/customers/naver_place_loc_all/db/schema_detail.sql",
]

if not self.db_repository.initialize(
    schema_files,
    start_job=True,
):
    return False
```

---

## 5. config.json 컬럼 규칙

Repository는 `config.json`의 `columns` 정보를 기준으로 동작합니다.

```json
{
  "columns": [
    {
      "code": "id",
      "value": "아이디",
      "checked": true
    },
    {
      "code": "name",
      "value": "상호명",
      "checked": true
    },
    {
      "code": "phone",
      "value": "전화번호",
      "checked": false
    }
  ]
}
```

### 속성 의미

| 속성 | 설명 |
|---|---|
| `code` | DB 컬럼명이며 Worker 결과 dict의 key로 사용 |
| `value` | 화면과 엑셀에 표시할 컬럼명 |
| `checked` | 엑셀 출력 여부 |

중요한 규칙:

```text
config.json columns[].code
    = Detail 테이블 컬럼명
    = Worker 결과 dict key
```

예시:

```python
row = {
    "id": "12345",
    "name": "테스트 매장",
    "phone": "02-0000-0000",
}
```

---

## 6. Detail 공통 컬럼

모든 Worker Detail 테이블에는 다음 공통 컬럼이 들어갑니다.

```text
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

행 처리와 관련된 핵심 컬럼:

| 컬럼 | 설명 |
|---|---|
| `row_status` | 행 처리 결과 (`SUCCESS`, `FAIL`) |
| `row_error_message` | 행 처리 실패 원인 |
| `row_start_at` | 상세조회 시작시간 |
| `row_end_at` | 상세조회 종료시간 |

각 Worker의 `schema_detail.sql`에는 아래 컬럼이 포함되어야 합니다.

```sql
row_status TEXT NOT NULL DEFAULT 'SUCCESS',
row_error_message TEXT,
row_start_at TEXT,
row_end_at TEXT,
```

---

## 7. 행 상태 저장 방식

상세조회 1건마다 성공 또는 실패 상태를 DB에 저장합니다.

### 성공 행

```text
row_status = SUCCESS
row_error_message = NULL
row_start_at = 상세조회 시작시간
row_end_at = 상세조회 종료시간
```

### 실패 행

```text
row_status = FAIL
row_error_message = 실제 오류 메시지
row_start_at = 상세조회 시작시간
row_end_at = 상세조회 종료시간
```

중요한 원칙:

```text
상세조회 실패
    ≠ 저장하지 않음

상세조회 실패
    = FAIL 행으로 저장
```

실패 행에는 가능한 범위에서 최소 식별정보를 남깁니다.

```python
failed_row = {
    "id": place_id,
    "name": "",
    "url": f"https://m.place.naver.com/place/{place_id}/home",
    "map": f"https://map.naver.com/p/entry/place/{place_id}",
    "city": loc.get("시도", ""),
    "division": loc.get("시군구", ""),
    "sector": loc.get("읍면동", ""),
    "keyword": query_keyword,
    "all_keyword": query,
}
```

---

## 8. Detail 저장 방법

### 기본 저장

```python
self.db_repository.insert_detail(row)
```

기본값:

```text
row_status = SUCCESS
row_error_message = None
row_start_at = None
row_end_at = None
```

### 상태와 시간 포함 저장

```python
self.db_repository.insert_detail(
    row,
    row_status="SUCCESS",
    row_error_message=None,
    row_start_at="2026-07-11 15:00:00.000",
    row_end_at="2026-07-11 15:00:01.000",
)
```

### 실패 행 저장

```python
self.db_repository.insert_detail(
    failed_row,
    row_status="FAIL",
    row_error_message="상세 조회 실패",
    row_start_at="2026-07-11 15:00:00.000",
    row_end_at="2026-07-11 15:00:03.500",
)
```

---

## 9. 성공/실패 집계 기준

Repository는 DB INSERT 성공 여부만으로 집계하지 않습니다.

행 상태와 DB 저장 결과를 함께 사용합니다.

```text
DB INSERT 성공
+
row_status == SUCCESS
    → success_count 증가
```

```text
DB INSERT 성공
+
row_status != SUCCESS
    → fail_count 증가
```

```text
DB INSERT 실패
    → fail_count 증가
```

정리:

```text
success_count
    = SUCCESS 상태로 저장된 행 수

fail_count
    = FAIL 상태로 저장된 행 수
    + DB 저장 자체가 실패한 행 수

total_count
    = success_count + fail_count
```

---

## 10. 작업 상태와 행 상태 구분

### 작업 상태

Worker 전체 작업의 최종 상태입니다.

```text
RUNNING
SUCCESS
STOP
FAIL
```

### 행 상태

상세조회 1건의 처리 결과입니다.

```text
SUCCESS
FAIL
```

예를 들어 전체 작업은 정상 종료되었지만 일부 상세조회가 실패할 수 있습니다.

```text
작업 상태 = SUCCESS
성공 행 = 950건
실패 행 = 50건
```

---

## 11. 작업 종료 처리

Worker에서 상태 설정:

```python
self.db_repository.set_job_result(
    "SUCCESS"
)
```

이 호출은 메모리상의 상태만 변경합니다.

실제 `worker_job_hist` 업데이트:

```python
self.db_repository.finish_job()
```

정리:

```text
set_job_result()
    → 최종 상태 설정

finish_job()
    → worker_job_hist 실제 UPDATE
```

종료 순서는 다음과 같습니다.

```text
최종 상태 설정
    ↓
Repository.finish_job()
    ↓
필요 시 엑셀 생성
    ↓
Repository.close()
```

DB 연결을 먼저 닫으면 작업 이력 업데이트나 엑셀 조회가 실패할 수 있습니다.

---

## 12. 네이버 플레이스 Worker 적용 흐름

```text
db_set()
    ↓
Repository 생성
    ↓
initialize()
    ↓
Place ID 목록 조회
    ↓
각 ID 상세조회 시작
    ↓
row_start_at 기록
    ↓
_fetch_place_info()
    ├─ 성공 → SUCCESS 행 저장
    └─ 실패 → FAIL 행 저장
    ↓
row_end_at 기록
    ↓
반복
    ↓
Worker 최종 상태 설정
    ↓
finalize_db_and_excel()
    ├─ Repository.finish_job()
    └─ 필요 시 엑셀 저장
    ↓
Repository.close()
```

---

## 13. 엑셀 데이터

Repository는 `checked=true`인 컬럼만 엑셀용 데이터로 변환합니다.

```python
excel_columns, excel_rows = (
    self.db_repository.get_excel_data()
)
```

- `excel_columns`  
  → `config.json columns[].value`
- `excel_rows`  
  → 엑셀 저장용 행 목록

주의:

현재 기본 엑셀에는 다음 공통 컬럼이 포함되지 않습니다.

```text
row_status
row_error_message
row_start_at
row_end_at
```

실패 상태와 오류 메시지를 엑셀에 표시하려면 별도 기능이 필요합니다.

---

## 14. DB 스키마 주의사항

### 신규 DB

`schema_detail.sql`에 아래 컬럼을 포함합니다.

```sql
row_status TEXT NOT NULL DEFAULT 'SUCCESS',
row_error_message TEXT,
row_start_at TEXT,
row_end_at TEXT,
```

### 기존 DB

`CREATE TABLE IF NOT EXISTS`는 기존 테이블에 새 컬럼을 추가하지 않습니다.

현재 컬럼 확인:

```sql
PRAGMA table_info(naver_place_loc_all);
```

컬럼이 없다면 마이그레이션이 필요합니다.

```sql
ALTER TABLE naver_place_loc_all
ADD COLUMN row_status TEXT
NOT NULL DEFAULT 'SUCCESS';

ALTER TABLE naver_place_loc_all
ADD COLUMN row_error_message TEXT;

ALTER TABLE naver_place_loc_all
ADD COLUMN row_start_at TEXT;

ALTER TABLE naver_place_loc_all
ADD COLUMN row_end_at TEXT;
```

이미 컬럼이 존재하면 같은 `ALTER TABLE`을 다시 실행하면 안 됩니다.

---

## 15. 구현 시 주의사항

### 1. 컬럼 이름 일치

다음 세 항목은 반드시 같아야 합니다.

```text
config.json columns[].code
Detail 테이블 컬럼명
Worker 결과 dict key
```

### 2. 실패 행 저장

상세조회가 실패했다고 바로 `continue`하면 안 됩니다.

```text
실패 최소 데이터 생성
    ↓
row_status = FAIL
    ↓
row_error_message 설정
    ↓
row_start_at / row_end_at 설정
    ↓
Repository.insert_detail()
```

### 3. Repository 초기화 후 저장

Detail 저장 전에 다음 값이 준비되어 있어야 합니다.

```text
SQLite 연결
hist_id
job_id
```

일반적으로 아래 호출이 성공한 후 저장합니다.

```python
repository.initialize(
    schema_files,
    start_job=True,
)
```

### 4. 다건 저장

`insert_details()`는 전체 행에 동일한 `row_status`를 적용합니다.

성공 행과 실패 행이 섞여 있다면 상태별로 나누거나 `insert_detail()`을 사용합니다.

### 5. 엑셀 조회

현재 Detail 조회에는 `row_status` 필터가 없습니다.

따라서 FAIL 행도 엑셀 데이터에 포함될 수 있습니다.

---

## 16. 관련 파일

```text
src/repositories/worker_db_repository.py
src/utils/sqlite_utils.py
src/workers/main/api_naver_place_loc_all_set_worker.py
src/workers/api_base_worker.py

resources/customers/common/db/schema_hist.sql
resources/customers/naver_place_loc_all/db/schema_detail.sql
resources/customers/naver_place_loc_all/config.json
```

---

## 17. 핵심 정리

```text
Worker
    → 데이터 수집
    → 성공/실패 판단
    → 시작/종료시간 측정

WorkerDbRepository
    → SUCCESS/FAIL 행 저장
    → 작업 이력 관리
    → 성공/실패 집계
    → Detail 조회
    → 엑셀 데이터 변환
```

핵심 규칙은 다음과 같습니다.

```text
SUCCESS 행 저장 성공
    → success_count

FAIL 행 저장 성공
    → fail_count

DB 저장 실패
    → fail_count
```

이 구조를 사용하면 작업별로 다음 내용을 추적할 수 있습니다.

- 성공한 데이터
- 실패한 데이터
- 실패 원인
- 상세조회 시작시간
- 상세조회 종료시간
- 작업 전체 성공/실패 건수
