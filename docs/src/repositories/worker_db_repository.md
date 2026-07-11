# WorkerDbRepository

## 코드 위치

```text
src/repositories/worker_db_repository.py
```

## 연동 예제 Worker

```text
src/workers/main/api_naver_place_loc_all_set_worker.py
```

---

## 1. 개요

`WorkerDbRepository`는 각 크롤링 Worker에서 공통으로 사용하는 SQLite 저장소 클래스다.

Worker가 SQLite 연결, 작업 이력 관리, 동적 INSERT SQL 생성, 행 단위 상태 저장, 성공·실패 건수 집계, 엑셀 데이터 변환을 직접 처리하지 않도록 DB 관련 책임을 한곳에 모은다.

```text
Worker
    ↓ 수집 결과와 행 상태 전달
WorkerDbRepository
    ├─ SQLite 연결 및 스키마 초기화
    ├─ 작업 이력 시작·종료
    ├─ Detail 성공 행 저장
    ├─ Detail 실패 행 저장
    ├─ 행 시작·종료시간 저장
    ├─ 성공·실패 건수 집계
    ├─ Detail 데이터 조회
    └─ 엑셀용 컬럼명 변환
```

Worker는 상세 조회 성공 여부와 관계없이 처리한 행을 Repository에 전달할 수 있다.

```text
상세 조회 성공
    → row_status = SUCCESS
    → 수집 결과 저장

상세 조회 실패
    → row_status = FAIL
    → 오류 메시지와 최소 식별정보 저장
```

---

## 2. 주요 책임

| 구분 | 설명 |
|---|---|
| DB 연결 | `SqliteUtils`를 이용해 SQLite 연결을 생성하고 종료한다. |
| 스키마 초기화 | 공통 작업 이력 테이블과 Worker별 Detail 테이블 SQL을 실행한다. |
| 작업 이력 관리 | `worker_job_hist`에 작업 시작과 종료 상태를 기록한다. |
| Detail 저장 | Worker가 전달한 성공 행과 실패 행을 Worker별 Detail 테이블에 저장한다. |
| 행 상태 저장 | `row_status`, `row_error_message`, `row_start_at`, `row_end_at`을 저장한다. |
| 동적 컬럼 관리 | `config.json`의 `columns[].code`를 실제 DB 컬럼으로 사용한다. |
| 엑셀 컬럼 관리 | `checked=true`인 컬럼만 조회하고 `columns[].value`를 엑셀 헤더로 사용한다. |
| 결과 집계 | 행 처리 상태와 DB 저장 결과를 기준으로 성공·실패 건수를 누적한다. |
| 로그 전달 | 외부에서 전달한 로그 함수를 통해 DB 처리 결과를 출력한다. |

---

## 3. 클래스 의존 관계

```text
ApiNaverPlaceLocAllSetWorker
    │
    ├─ WorkerDbRepository
    │      └─ SqliteUtils
    │
    └─ ExcelUtils
```

### 직접 의존 모듈

```python
from src.utils.sqlite_utils import SqliteUtils
```

`WorkerDbRepository`는 SQLite 저수준 연결과 SQL 실행을 `SqliteUtils`에 위임한다.

Repository 자체는 다음 작업에 집중한다.

- 어떤 테이블에 저장할지 결정
- 어떤 컬럼을 저장할지 결정
- 작업 이력과 Detail 데이터의 SQL 구성
- 행 상태와 오류 정보 저장
- 성공·실패 건수 집계
- 엑셀용 데이터 구조 변환

---

## 4. 생성자

```python
WorkerDbRepository(
    db_path=...,
    site_name=...,
    worker_name=...,
    detail_table_name=...,
    column_defs=...,
    user_id=...,
    hist_table_name="worker_job_hist",
    log_func=...,
    detail_log_fields=...,
)
```

### 생성자 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `db_path` | `str` | O | SQLite DB 파일 경로 |
| `site_name` | `str` | O | 사용자에게 표시할 사이트명 |
| `worker_name` | `str` | O | Worker 식별자 |
| `detail_table_name` | `str` | O | 수집 데이터를 저장할 Detail 테이블명 |
| `column_defs` | `Sequence[Dict[str, Any]]` | O | `config.json`의 `columns` 정의 |
| `user_id` | `Any` | X | 작업 실행 사용자 식별값 |
| `hist_table_name` | `str` | X | 작업 이력 테이블명, 기본값은 `worker_job_hist` |
| `log_func` | `Callable[[str], None]` | X | Repository 로그를 전달할 외부 함수 |
| `detail_log_fields` | `Sequence[str]` | X | Detail 단건 저장 로그에 표시할 대표 필드 |

### 네이버 플레이스 Worker 생성 예시

```python
self.db_repository = WorkerDbRepository(
    db_path=self.get_runtime_db_path(),
    site_name=self.site_name,
    worker_name=self.worker_name,
    detail_table_name=self.detail_table_name,
    column_defs=column_defs,
    user_id=self._get_db_user_id(),
    log_func=self.log_signal_func,
    detail_log_fields=("id", "name"),
)
```

위 설정에서는 Detail 한 건을 저장할 때 `id`, `name`을 대표 로그 필드로 출력한다.

성공 행:

```text
✅ [DB] detail 성공행 저장 완료 |
hist_id=10 |
row_status=SUCCESS |
id=12345 |
name=테스트 매장
```

실패 행:

```text
⚠️ [DB] detail 실패행 저장 완료 |
hist_id=10 |
row_status=FAIL |
id=12345 |
name=
```

---

## 5. config.json 컬럼 구조

Repository는 Worker별 수집 컬럼을 코드 안에 고정하지 않고 `config.json`의 `columns` 정의로 전달받는다.

### 예시

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

### 속성 역할

| 속성 | 역할 |
|---|---|
| `code` | Detail 테이블의 실제 DB 컬럼명이며 Worker 결과 dict의 key로 사용한다. |
| `value` | 화면과 엑셀에 표시할 사용자용 컬럼명이다. |
| `checked` | `true`이면 엑셀 조회 및 출력 대상에 포함한다. |

### 생성되는 내부 컬럼 목록

위 설정을 전달하면 Repository 내부 값은 다음과 같이 구성된다.

```python
db_columns = [
    "id",
    "name",
    "phone",
]

checked_codes = [
    "id",
    "name",
]

excel_columns = [
    "아이디",
    "상호명",
]
```

### 컬럼 처리 기준

```text
columns[].code
    ├─ Detail INSERT 컬럼
    ├─ Worker 수집 결과 dict의 key
    └─ Detail SELECT 컬럼

columns[].value
    └─ 엑셀 헤더

columns[].checked
    ├─ 엑셀 출력 여부
    └─ 선택 데이터 추가 조회 여부 판단
```

`row_status`, `row_error_message`, `row_start_at`, `row_end_at`은 `config.json`의 동적 컬럼이 아니다.

해당 컬럼은 모든 Worker Detail 테이블에 공통으로 존재하는 시스템 컬럼이다.

---

## 6. Detail 테이블 컬럼 구성

Detail INSERT 컬럼은 다음 순서로 동적으로 생성된다.

```text
공통 컬럼
    +
config.json의 columns[].code
    +
created_at, updated_at
```

### 공통 컬럼

| 컬럼 | 설명 |
|---|---|
| `hist_id` | 현재 작업 이력 PK |
| `site_name` | 사용자 표시용 사이트명 |
| `worker_name` | Worker 식별자 |
| `table_name` | 현재 Detail 테이블명 |
| `job_id` | 작업 고유 ID |
| `user_id` | 실행 사용자 ID |
| `row_status` | 행 단위 처리 결과 상태 |
| `row_error_message` | 행 처리 실패 원인 |
| `row_start_at` | 상세 조회 시작 시간 |
| `row_end_at` | 상세 조회 종료 시간 |

### 행 상태 컬럼 SQL

각 Worker의 `schema_detail.sql`에는 다음 컬럼이 포함되어야 한다.

```sql
row_status TEXT NOT NULL DEFAULT 'SUCCESS',
row_error_message TEXT,
row_start_at TEXT,
row_end_at TEXT,
```

### 전체 컬럼 예시

`config.json`에 `id`, `name`, `phone`이 정의되어 있다면 실제 INSERT 컬럼 순서는 다음과 같다.

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
id
name
phone
created_at
updated_at
```

Worker가 전달하지 않은 동적 컬럼은 빈 문자열로 저장된다.

```python
row.get(column, "")
```

`dict` 또는 `list` 값은 JSON 문자열로 변환한 뒤 SQLite에 저장한다.

```python
json.dumps(
    value,
    ensure_ascii=False,
    default=str,
)
```

---

## 7. 행 단위 상태 설계

### 기본 상태

| 상태 | 의미 |
|---|---|
| `SUCCESS` | 상세 조회와 데이터 구성이 정상적으로 완료된 행 |
| `FAIL` | 상세 조회 또는 데이터 처리에 실패한 행 |

Repository는 전달받은 `row_status`를 대문자로 정규화하여 성공 여부를 판별한다.

```python
str(row_status or "").strip().upper() == "SUCCESS"
```

따라서 정확히 `SUCCESS`인 경우만 성공 행으로 집계한다.

그 외 상태는 실패 행으로 집계된다.

```text
SUCCESS
    → success_count

FAIL
ERROR
STOP
빈 문자열
기타 상태
    → fail_count
```

행 상태 값은 Worker 전체 작업 상태와 별개다.

```text
작업 상태
    ├─ RUNNING
    ├─ SUCCESS
    ├─ STOP
    └─ FAIL

행 상태
    ├─ SUCCESS
    └─ FAIL
```

전체 작업이 `SUCCESS`로 종료되어도 일부 Detail 행은 `FAIL`일 수 있다.

---

## 8. 행 시작·종료시간 기준

네이버 플레이스 Worker는 상세조회 1건마다 시간을 측정한다.

```text
row_start_at 기록
    ↓
_fetch_place_info() 실행
    ↓
row_end_at 기록
    ↓
Repository.insert_detail() 호출
```

따라서 현재 `row_start_at`과 `row_end_at`은 다음 구간을 의미한다.

```text
상세 조회 시작
    ~
상세 조회 성공·실패 결정 시점
```

DB INSERT 시간은 해당 구간에 포함되지 않는다.

### 시간 형식

```text
YYYY-MM-DD HH:MM:SS.mmm
```

예시:

```text
2026-07-11 15:00:01.123
2026-07-11 15:00:04.519
```

Repository의 `_now()`와 Worker의 `_now_db()`는 동일한 밀리초 형식을 사용한다.

---

## 9. 전체 작업 생명주기

```text
Worker.init()
    ↓
Worker.db_set()
    ↓
WorkerDbRepository 생성
    ↓
initialize(schema_files, start_job=True)
    ├─ connect()
    ├─ 스키마 SQL 실행
    └─ start_job()
           └─ worker_job_hist INSERT
    ↓
Worker 데이터 수집
    ↓
상세조회 1건 시작
    ↓
row_start_at 기록
    ↓
상세조회 실행
    ├─ 성공 → SUCCESS 행 저장
    └─ 실패 → FAIL 행 저장
    ↓
row_end_at 기록
    ↓
다음 상세조회 반복
    ↓
Worker가 최종 작업 상태 설정
    ├─ SUCCESS
    ├─ STOP
    └─ FAIL
    ↓
Repository.finish_job()
    └─ worker_job_hist UPDATE
    ↓
필요 시 get_excel_data()
    ↓
Repository.close()
```

---

## 10. 초기화 흐름

### Worker의 DB 설정

네이버 플레이스 Worker의 `db_set()`은 다음 순서로 실행된다.

```text
런타임 고객 config 조회
    ↓
config의 columns 검증
    ↓
WorkerDbRepository 생성
    ↓
공통 schema_hist.sql 등록
    ↓
Worker별 schema_detail.sql 등록
    ↓
Repository.initialize()
    ↓
엑셀 표시 컬럼 저장
```

### 스키마 파일 예시

```python
schema_files = [
    os.path.join(
        "resources",
        "customers",
        "common",
        "db",
        "schema_hist.sql",
    ),
    os.path.join(
        "resources",
        "customers",
        self.worker_name,
        "db",
        "schema_detail.sql",
    ),
]
```

### `initialize()`

```python
repository.initialize(
    schema_files,
    start_job=True,
)
```

처리 순서:

1. SQLite 연결
2. 전달된 스키마 파일 실행
3. `start_job=True`이면 작업 이력 생성
4. 모든 작업이 성공하면 `True` 반환
5. 연결 또는 스키마 초기화에 실패하면 `False` 반환

---

## 11. 작업 이력 관리

### 작업 시작

`start_job()`은 `worker_job_hist`에 `RUNNING` 상태의 작업을 생성한다.

```text
start_job()
    ↓
기존 작업 상태 초기화
    ↓
job_id 생성
    ↓
worker_job_hist INSERT
    ↓
last_insert_rowid() 조회
    ↓
hist_id 저장
```

### job_id 생성 규칙

외부에서 `job_id`를 전달하지 않으면 다음 형식으로 자동 생성한다.

```text
현재시간 + UUID 앞 8자리
```

예시:

```text
20260711153025123456_a1b2c3d4
```

### 시작 시 저장 값

| 항목 | 초기값 |
|---|---|
| `status` | `RUNNING` |
| `total_count` | `0` |
| `success_count` | `0` |
| `fail_count` | `0` |
| `start_at` | 현재 시간 |
| `created_at` | 현재 시간 |
| `updated_at` | 현재 시간 |

---

## 12. 작업 상태 처리

Repository 생성 직후 상태는 다음과 같다.

```python
status = "RUNNING"
error_message = None
success_count = 0
fail_count = 0
```

### 일반적인 작업 상태

| 상태 | 의미 |
|---|---|
| `RUNNING` | 작업 진행 중 |
| `SUCCESS` | 정상 완료 |
| `STOP` | 사용자 중단 |
| `FAIL` | 예외 또는 비정상 종료 |

Repository는 작업 상태 문자열을 제한하거나 검증하지 않는다.

Worker에서 정해진 상태값을 일관되게 전달해야 한다.

### 상태 설정과 DB 반영의 차이

네이버 플레이스 Worker에는 다음 래퍼 메서드가 있다.

```python
def finish_job(
    self,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    if self.db_repository:
        self.db_repository.set_job_result(
            status,
            error_message,
        )
```

이 메서드는 이름이 `finish_job()`이지만 실제 DB UPDATE를 실행하지 않는다.

```text
Worker.finish_job()
    └─ Repository.set_job_result()
           └─ 메모리의 status와 error_message만 변경
```

실제 `worker_job_hist` 종료 UPDATE는 다음 위치에서 실행된다.

```text
Worker.cleanup()
    ↓
Worker.finalize_db_and_excel()
    ↓
Repository.finish_job()
    ↓
worker_job_hist UPDATE
```

따라서 두 기능을 구분해야 한다.

| 호출 | 실제 역할 |
|---|---|
| `repository.set_job_result()` | 최종 작업 상태와 대표 오류 메시지를 메모리에 설정 |
| `repository.finish_job()` | 설정된 상태와 누적 건수를 DB에 최종 반영 |

---

## 13. 정상 종료, 중단, 비정상 종료

### 정상 종료

```text
Worker.main() 완료
    ↓
running == True
    ↓
Worker.finish_job("SUCCESS")
    ↓
작업 상태를 SUCCESS로 설정
    ↓
cleanup()
    ↓
Repository.finish_job()
    ↓
worker_job_hist 최종 UPDATE
```

일부 Detail 행이 `FAIL`이어도 Worker 자체가 예외 없이 전체 순회를 완료하면 작업 상태는 `SUCCESS`가 될 수 있다.

```text
작업 상태 = SUCCESS
성공 행 = 950건
실패 행 = 50건
```

### 사용자 중단

```text
Worker.stop()
    ↓
running = False
    ↓
Worker.finish_job("STOP", "사용자 중단")
    ↓
cleanup()
    ↓
Repository.finish_job()
```

### 비정상 종료

`cleanup()` 시점까지 작업 상태가 `RUNNING`이면 비정상 종료로 판단한다.

```python
if self.db_repository.status == "RUNNING":
    self.db_repository.set_job_result(
        "FAIL",
        "비정상 종료",
    )
```

이후 `Repository.finish_job()`으로 DB에 최종 상태를 저장한다.

---

## 14. 작업 종료 중복 방지

Worker의 정상 종료, `stop()`, `cleanup()`, `destroy()` 경로에서 종료 처리가 중복 호출될 수 있다.

Repository는 `_job_finished` 값으로 작업 이력 UPDATE 중복 실행을 방지한다.

```python
if self._job_finished:
    return True
```

작업 종료 UPDATE가 성공하면 다음과 같이 변경한다.

```python
self._job_finished = True
```

따라서 동일한 Repository 인스턴스에서 `finish_job()`이 여러 번 호출되어도 최초 성공 이후에는 추가 UPDATE를 수행하지 않는다.

---

## 15. Detail 단건 저장

### 기본 호출

행 상태 정보가 필요하지 않은 기존 Worker는 다음과 같이 사용할 수 있다.

```python
repository.insert_detail(row)
```

기본값:

```python
row_status="SUCCESS"
row_error_message=None
row_start_at=None
row_end_at=None
```

### 전체 파라미터 호출

```python
repository.insert_detail(
    row,
    row_status="SUCCESS",
    row_error_message=None,
    row_start_at="2026-07-11 15:00:00.000",
    row_end_at="2026-07-11 15:00:01.000",
)
```

### Worker 래퍼 메서드

```python
def insert_detail_row(
    self,
    row: Dict[str, Any],
    *,
    row_status: str = "SUCCESS",
    row_error_message: Optional[str] = None,
    row_start_at: Optional[str] = None,
    row_end_at: Optional[str] = None,
) -> bool:
    if not self.db_repository:
        return False

    return self.db_repository.insert_detail(
        row,
        row_status=row_status,
        row_error_message=row_error_message,
        row_start_at=row_start_at,
        row_end_at=row_end_at,
    )
```

### 성공 행 예시

```python
place_info = {
    "id": "1234567890",
    "name": "테스트 매장",
    "addr_jibun": "서울특별시 ...",
    "addr_road": "서울특별시 ...",
    "phone": "02-0000-0000",
    "site": "https://example.com",
}

repository.insert_detail(
    place_info,
    row_status="SUCCESS",
    row_start_at="2026-07-11 15:00:00.000",
    row_end_at="2026-07-11 15:00:01.000",
)
```

dict의 key는 반드시 `config.json`의 `columns[].code`와 일치해야 한다.

---

## 16. 실패 행 저장

상세조회가 실패해도 해당 건을 버리지 않고 Detail 테이블에 `FAIL` 행으로 저장한다.

```text
상세조회 실패
    ≠ 저장 생략

상세조회 실패
    = FAIL 행 저장
```

### 실패 행 호출 예시

```python
repository.insert_detail(
    failed_row,
    row_status="FAIL",
    row_error_message="Place ID 123 응답 없음",
    row_start_at="2026-07-11 15:00:00.000",
    row_end_at="2026-07-11 15:00:03.500",
)
```

### 실패 행 최소 데이터

네이버 플레이스 Worker는 상세 결과가 없어도 다음 정보를 가능한 범위에서 저장한다.

```python
{
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

이렇게 저장하면 나중에 다음 내용을 확인할 수 있다.

- 실패한 Place ID
- 조회한 지역
- 원본 키워드
- 전체 검색어
- 상세 페이지 URL
- 지도 URL
- 실패 원인
- 조회 시작시간
- 조회 종료시간

---

## 17. 네이버 플레이스 상세조회 처리

네이버 플레이스 Worker는 `_fetch_and_save_place_detail()`에서 상세조회와 DB 저장을 하나의 흐름으로 처리한다.

```text
_fetch_and_save_place_detail()
    ↓
row_start_at 기록
    ↓
_last_detail_error_message 초기화
    ↓
_fetch_place_info()
    ↓
성공 여부 판단
```

### 성공

```text
place_info 존재
    ↓
row_end_at 기록
    ↓
row_status = SUCCESS
    ↓
수집 데이터 저장
    ↓
place_info, save_ok 반환
```

### 실패

```text
place_info 없음
    ↓
row_end_at 기록
    ↓
_last_detail_error_message 확인
    ↓
없으면 기본 오류 메시지 생성
    ↓
실패 행 최소 데이터 생성
    ↓
row_status = FAIL
    ↓
오류 메시지와 함께 저장
```

### 예외

```text
상세조회 래퍼 내부 예외 발생
    ↓
row_end_at 기록
    ↓
예외 메시지 생성
    ↓
실패 행 생성
    ↓
row_status = FAIL
    ↓
Repository 저장
```

---

## 18. 상세조회 오류 메시지 처리

네이버 플레이스 Worker는 `_set_detail_error()`를 이용해 현재 상세조회 실패 원인을 보관한다.

```python
def _set_detail_error(
    self,
    message: str,
) -> None:
    self._last_detail_error_message = (
        str(message or "상세 조회 실패")
    )
    self.log_signal_func(
        self._last_detail_error_message
    )
```

### 저장 가능한 대표 오류

```text
api_client가 초기화되지 않음
응답 없음
APOLLO_STATE 스크립트 없음
APOLLO_STATE marker 없음
JSON 시작 위치 없음
JSON decode 실패
data 형식 오류
placeDetail key 없음
네트워크 오류
상세 처리 중 예외
```

`_fetch_place_info()`가 `None`을 반환하면 `_fetch_and_save_place_detail()`이 마지막 오류 메시지를 `row_error_message`로 전달한다.

오류 메시지가 설정되지 않은 경우 기본 메시지를 사용한다.

```text
Place ID {place_id} 상세 정보 조회 실패
```

---

## 19. Detail 저장 전 검증

Detail 저장 전 다음 항목을 확인한다.

```text
row가 dict인가?
    ↓
SQLite 연결이 존재하는가?
    ↓
hist_id가 존재하는가?
    ↓
job_id가 존재하는가?
```

검증 실패 시 다음과 같이 처리한다.

```text
fail_count += 1
False 반환
```

Detail 저장에 필요한 작업 정보는 일반적으로 다음 호출에서 생성된다.

```python
repository.initialize(
    schema_files,
    start_job=True,
)
```

---

## 20. 성공·실패 집계 기준

Repository의 집계는 DB INSERT 성공 여부만으로 판단하지 않는다.

행 처리 상태와 DB INSERT 결과를 함께 사용한다.

### 단건 저장 기준

```text
DB INSERT 성공
+
row_status == SUCCESS
    → success_count += 1
```

```text
DB INSERT 성공
+
row_status != SUCCESS
    → fail_count += 1
```

```text
DB INSERT 실패
    → fail_count += 1
```

### 예시

| 처리 결과 | DB 저장 | 집계 |
|---|---|---|
| 상세조회 성공 | 성공 | `success_count + 1` |
| 상세조회 실패 행 | 성공 | `fail_count + 1` |
| 성공 행 DB INSERT 실패 | 실패 | `fail_count + 1` |
| 실패 행 DB INSERT 실패 | 실패 | `fail_count + 1` |

### 중요한 의미

`success_count`는 단순 DB INSERT 성공 횟수가 아니다.

```text
success_count
    = SUCCESS 상태로 DB에 저장된 행 수
```

`fail_count`는 다음 두 종류를 포함한다.

```text
fail_count
    = FAIL 상태로 정상 저장된 행 수
    + DB INSERT 자체가 실패한 행 수
```

---

## 21. Detail 다건 저장

```python
repository.insert_details(
    rows,
    row_status="SUCCESS",
)
```

`insert_details()`는 여러 행을 하나의 트랜잭션으로 저장한다.

```text
행 목록 검증
    ↓
INSERT SQL 한 번 생성
    ↓
각 행의 파라미터 목록 생성
    ↓
executemany()
    ↓
commit()
```

### 동일 상태 적용

현재 `insert_details()`는 전체 행에 하나의 `row_status`를 공통 적용한다.

```python
repository.insert_details(
    success_rows,
    row_status="SUCCESS",
)

repository.insert_details(
    fail_rows,
    row_status="FAIL",
)
```

성공 행과 실패 행이 섞여 있다면 상태별로 분리해서 호출해야 한다.

### 현재 제한

`insert_details()`는 다음 값을 행별로 받지 않는다.

```text
row_error_message
row_start_at
row_end_at
```

행별 오류 메시지와 시간이 필요하면 `insert_detail()`을 사용해야 한다.

### 성공 집계

```text
row_status == SUCCESS
    → success_count += len(rows)

row_status != SUCCESS
    → fail_count += len(rows)
```

### 트랜잭션 실패

```text
rollback()
fail_count += len(rows)
```

### 잘못된 행 형식

행 목록 중 하나라도 `dict`가 아니면 전체 요청을 실패로 처리한다.

```text
100개 중 1개가 dict가 아님
    ↓
100개 전체 실패 처리
    ↓
fail_count += 100
```

---

## 22. Detail INSERT SQL 생성

`_build_detail_insert_query()`는 Repository 생성 시 구성한 컬럼 목록을 이용해 INSERT SQL을 동적으로 만든다.

```text
DETAIL_COMMON_COLUMNS
    +
db_columns
    +
created_at
updated_at
```

테이블명과 컬럼명은 SQLite 식별자 형태로 감싼다.

```python
def _quote(name: str) -> str:
    return f'"{name}"'
```

예시:

```sql
INSERT INTO "naver_place_loc_all" (
    "hist_id",
    "site_name",
    "worker_name",
    "table_name",
    "job_id",
    "user_id",
    "row_status",
    "row_error_message",
    "row_start_at",
    "row_end_at",
    "id",
    "name",
    "phone",
    "created_at",
    "updated_at"
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

값은 문자열 결합이 아니라 SQLite 파라미터 바인딩 방식으로 전달한다.

---

## 23. 선택 컬럼 확인

### 단일 컬럼 확인

```python
repository.is_column_checked(
    "zip_code"
)
```

`zip_code`가 `checked=true`이면 `True`를 반환한다.

### 여러 컬럼 중 하나 이상 확인

```python
repository.are_any_columns_checked(
    [
        "agency_name",
        "agency_ceo",
        "agency_address",
    ]
)
```

하나라도 `checked=true`이면 `True`를 반환한다.

### 실제 Worker 활용

네이버 플레이스 Worker는 선택하지 않은 고비용 데이터의 추가 요청을 생략한다.

#### 우편번호

```python
zip_code = ""

if (
    self.db_repository
    and self.db_repository.is_column_checked(
        "zip_code"
    )
):
    zip_code = self._fetch_zipcode_by_addr(
        address,
        road_address,
    )
```

#### 대행사 정보

```text
agency 관련 컬럼이 하나라도 checked=true
    ↓
booking_business_id 조회
    ↓
예약 페이지 추가 요청
    ↓
선택한 agency 컬럼만 결과에 추가
```

이 방식은 사용자가 선택하지 않은 데이터 때문에 불필요한 네트워크 요청이 발생하는 것을 줄인다.

---

## 24. Detail 조회

### 전체 동적 컬럼 조회

```python
rows = repository.fetch_detail_rows(
    checked_only=False,
)
```

### 엑셀 선택 컬럼만 조회

```python
rows = repository.fetch_detail_rows(
    checked_only=True,
)
```

조회 조건은 현재 Repository의 `hist_id`다.

```sql
WHERE hist_id = ?
ORDER BY detail_id
```

즉, 동일한 Detail 테이블에 여러 작업 결과가 저장되어 있어도 현재 작업에서 저장한 데이터만 반환한다.

### 조회 범위 주의

현재 `fetch_detail_rows()`는 `row_status` 조건을 사용하지 않는다.

따라서 다음 행이 모두 조회 대상이다.

```text
SUCCESS 행
FAIL 행
```

엑셀 출력에서도 실패 행을 제외하지 않는다.

실패 행은 수집 데이터 컬럼이 비어 있을 수 있다.

### 조회 전제 조건

Detail 테이블에는 정렬 기준으로 사용하는 `detail_id` 컬럼이 존재해야 한다.

---

## 25. 엑셀 데이터 변환

### 처리 흐름

```text
get_excel_data()
    ↓
fetch_detail_rows(checked_only=True)
    ↓
DB 컬럼 code로 조회
    ↓
to_excel_rows()
    ↓
code를 value로 변환
    ↓
엑셀 헤더와 행 목록 반환
```

### DB 조회 결과

```python
[
    {
        "id": "123",
        "name": "테스트 매장",
    }
]
```

### 엑셀 변환 결과

```python
[
    {
        "아이디": "123",
        "상호명": "테스트 매장",
    }
]
```

### 반환값

```python
excel_columns, excel_rows = (
    repository.get_excel_data()
)
```

```python
excel_columns = [
    "아이디",
    "상호명",
]

excel_rows = [
    {
        "아이디": "123",
        "상호명": "테스트 매장",
    }
]
```

### FAIL 행과 엑셀

현재 엑셀 조회는 `row_status`를 선택하지 않으며, 상태 조건으로 필터링하지도 않는다.

따라서 FAIL 행도 엑셀 행에 포함된다.

다만 `row_status`, `row_error_message`, `row_start_at`, `row_end_at`은 `config.json` 기반 엑셀 컬럼이 아니므로 기본 엑셀에는 표시되지 않는다.

실패 정보까지 엑셀에 표시해야 한다면 별도의 조회 옵션 또는 시스템 컬럼 포함 기능을 추가해야 한다.

---

## 26. Worker의 엑셀 저장 흐름

네이버 플레이스 Worker의 `export_detail_to_excel()`은 Repository로부터 엑셀 데이터를 받은 뒤 `ExcelUtils`에 저장을 위임한다.

```text
Repository.get_excel_data()
    ↓
excel_columns
excel_rows
    ↓
ExcelUtils.save_db_rows_to_excel()
    ↓
xlsx 파일 생성
```

파일명에는 현재 작업의 `job_id`를 사용한다.

```python
excel_filename = (
    f"{self.site_name}_"
    f"{self.db_repository.job_id}.xlsx"
)
```

예시:

```text
네이버 플레이스 전국_20260711153025123456_a1b2c3d4.xlsx
```

`auto_save_yn=True`인 경우 작업 종료 시 자동으로 엑셀 파일을 생성한다.

---

## 27. 최종 작업 이력 UPDATE

`Repository.finish_job()`은 누적된 작업 결과를 `worker_job_hist`에 반영한다.

### 반영 항목

| 항목 | 값 |
|---|---|
| `end_at` | 종료 시간 |
| `status` | 최종 작업 상태 |
| `total_count` | `success_count + fail_count` |
| `success_count` | `SUCCESS` 상태로 저장된 행 수 |
| `fail_count` | 실패 상태 행 수와 DB 저장 실패 수 |
| `error_message` | 작업 전체의 대표 오류 메시지 |
| `updated_at` | 최종 수정 시간 |

### total_count 계산

```python
total_count = (
    success_count
    + fail_count
)
```

여기서 `total_count`는 다음 의미다.

```text
Repository가 처리 결과로 집계한 전체 행 수
```

다음 값과는 다를 수 있다.

- 검색된 전체 ID 수
- API 요청 횟수
- 중복 제거 전 대상 수
- 목록 조회 페이지 수
- Worker 진행률 계산용 예상 건수

### 행 오류와 작업 오류 구분

```text
row_error_message
    → 개별 Detail 행의 실패 원인

worker_job_hist.error_message
    → 전체 작업의 대표 종료 오류
```

개별 상세조회 실패 메시지는 `row_error_message`에 저장한다.

전체 작업 비정상 종료나 사용자 중단 사유는 `worker_job_hist.error_message`에 저장한다.

---

## 28. 로그 처리

Repository는 직접 특정 UI나 로깅 프레임워크에 의존하지 않는다.

외부에서 전달한 `log_func`가 있을 때만 로그를 전송한다.

```python
WorkerDbRepository(
    ...,
    log_func=self.log_signal_func,
)
```

로그 함수 자체에서 예외가 발생해도 DB 작업에는 영향을 주지 않는다.

```python
try:
    self.log_func(message)
except Exception:
    pass
```

### 대표 로그

```text
[DB] 실제 경로 = ...
✅ [DB] 스키마 초기화 완료
✅ [DB] hist 시작 row 저장 완료
✅ [DB] detail 성공행 저장 완료
⚠️ [DB] detail 실패행 저장 완료
❌ [DB] detail DB 저장 실패
✅ [DB] detail bulk 저장 완료
✅ [DB] hist 종료 row 수정 완료
```

### 단건 저장 로그 구분

| 조건 | 로그 |
|---|---|
| INSERT 실패 | `❌ DB 저장 실패` |
| INSERT 성공 + SUCCESS 행 | `✅ 성공행 저장 완료` |
| INSERT 성공 + 비 SUCCESS 행 | `⚠️ 실패행 저장 완료` |

---

## 29. 주요 public 메서드

| 메서드 | 반환값 | 설명 |
|---|---|---|
| `initialize()` | `bool` | DB 연결, 스키마 초기화, 작업 시작 |
| `connect()` | `bool` | SQLite 연결 |
| `close()` | `None` | SQLite 연결 종료 |
| `is_column_checked()` | `bool` | 단일 컬럼의 엑셀 선택 여부 확인 |
| `are_any_columns_checked()` | `bool` | 여러 컬럼 중 하나 이상의 선택 여부 확인 |
| `reset_job_state()` | `None` | 작업 상태와 카운터 초기화 |
| `set_job_result()` | `None` | 최종 작업 상태와 대표 오류 설정 |
| `start_job()` | `bool` | 작업 시작 이력 INSERT |
| `finish_job()` | `bool` | 작업 종료 이력 UPDATE |
| `insert_detail()` | `bool` | 상태와 시간을 포함한 Detail 한 건 저장 |
| `insert_details()` | `bool` | 동일 상태의 Detail 여러 건 트랜잭션 저장 |
| `fetch_detail_rows()` | `List[Dict]` | 현재 작업 Detail 조회 |
| `to_excel_rows()` | `List[Dict]` | DB code를 엑셀 value로 변환 |
| `get_excel_data()` | `Tuple[List[str], List[Dict]]` | 엑셀 헤더와 행 데이터 반환 |

---

## 30. 주요 내부 메서드

| 메서드 | 설명 |
|---|---|
| `_can_save_detail()` | Detail 저장에 필요한 연결, `hist_id`, `job_id` 검증 |
| `_build_detail_insert_query()` | 동적 INSERT SQL 생성 |
| `_build_detail_params()` | 공통 컬럼, 동적 컬럼, 행 상태 파라미터 생성 |
| `_is_success_row_status()` | `row_status`가 `SUCCESS`인지 확인 |
| `_quote()` | 테이블명과 컬럼명을 SQLite 식별자로 처리 |
| `_to_db_value()` | `dict`, `list`를 JSON 문자열로 변환 |
| `_now()` | 밀리초 단위 DB 저장 시간 생성 |
| `_log_detail_result()` | DB 저장 결과와 행 상태를 구분해 로그 생성 |
| `_log()` | 외부 로그 함수 안전 호출 |

---

## 31. 기본 사용 예제

```python
from datetime import datetime

from src.repositories.worker_db_repository import (
    WorkerDbRepository,
)


def now_db() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


column_defs = [
    {
        "code": "id",
        "value": "아이디",
        "checked": True,
    },
    {
        "code": "name",
        "value": "상호명",
        "checked": True,
    },
]

repository = WorkerDbRepository(
    db_path="data/crawl.db",
    site_name="샘플 사이트",
    worker_name="sample_worker",
    detail_table_name="sample_detail",
    column_defs=column_defs,
    user_id=1,
    log_func=print,
    detail_log_fields=("id", "name"),
)

schema_files = [
    "resources/customers/common/db/schema_hist.sql",
    "resources/customers/sample_worker/db/schema_detail.sql",
]

try:
    if not repository.initialize(
        schema_files,
        start_job=True,
    ):
        raise RuntimeError(
            "DB Repository 초기화 실패"
        )

    row_start_at = now_db()

    try:
        row = {
            "id": "100",
            "name": "테스트 데이터",
        }

        row_end_at = now_db()

        repository.insert_detail(
            row,
            row_status="SUCCESS",
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    except Exception as e:
        row_end_at = now_db()

        repository.insert_detail(
            {
                "id": "100",
                "name": "",
            },
            row_status="FAIL",
            row_error_message=str(e),
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    repository.set_job_result(
        "SUCCESS"
    )

    excel_columns, excel_rows = (
        repository.get_excel_data()
    )

finally:
    repository.finish_job()
    repository.close()
```

---

## 32. 구현 시 주의사항

### 32.1 config code와 DB 컬럼 일치

다음 세 항목은 동일한 이름을 사용해야 한다.

```text
config.json columns[].code
Detail 테이블 컬럼명
Worker 결과 dict key
```

하나라도 다르면 해당 값이 저장되지 않거나 SQL 오류가 발생할 수 있다.

### 32.2 공통 상태 컬럼 필수

모든 Worker Detail 테이블에는 다음 컬럼이 있어야 한다.

```text
row_status
row_error_message
row_start_at
row_end_at
```

Repository는 INSERT SQL에 해당 컬럼을 항상 포함한다.

컬럼이 없으면 Detail 저장이 실패한다.

### 32.3 기존 DB 마이그레이션

`CREATE TABLE IF NOT EXISTS`는 기존 테이블에 새 컬럼을 추가하지 않는다.

이미 생성된 SQLite 테이블이라면 별도 마이그레이션이 필요하다.

확인:

```sql
PRAGMA table_info(naver_place_loc_all);
```

컬럼이 없다면 다음과 같은 방식으로 추가한다.

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

이미 컬럼이 존재하면 같은 `ALTER TABLE`을 다시 실행하면 안 된다.

### 32.4 작업 시작 후 Detail 저장

`insert_detail()`과 `insert_details()`를 호출하려면 다음 값이 준비되어 있어야 한다.

```text
SQLite 연결
hist_id
job_id
```

일반적으로 `initialize(..., start_job=True)`가 성공한 이후에 Detail을 저장한다.

### 32.5 실패 행도 반드시 저장

상세조회 결과가 `None`이라고 바로 `continue`하면 실패 정보가 DB에 남지 않는다.

다음 흐름을 사용해야 한다.

```text
상세조회 실패
    ↓
실패 행 최소 데이터 생성
    ↓
row_status = FAIL
    ↓
row_error_message 설정
    ↓
row_start_at, row_end_at 설정
    ↓
Repository.insert_detail()
```

### 32.6 작업 종료 전에 연결을 닫지 않기

작업 종료 순서는 다음과 같아야 한다.

```text
작업 상태 설정
    ↓
Repository.finish_job()
    ↓
필요 시 엑셀 조회 및 저장
    ↓
Repository.close()
```

DB 연결을 먼저 닫으면 최종 작업 이력 UPDATE와 엑셀 데이터 조회가 실패할 수 있다.

### 32.7 수집 대상 수와 Repository 집계 구분

Repository의 `success_count`, `fail_count`, `total_count`는 행 상태와 DB 저장 기준이다.

다음 값과 다를 수 있다.

- 검색된 전체 ID 수
- API 요청 수
- 목록 조회 실패 수
- 중복 제거 전 수집 대상 수
- Worker 진행률 계산용 예상 수
- 중복으로 인해 실제 처리하지 않은 ID 수

### 32.8 FAIL 행 엑셀 포함

현재 엑셀 조회는 상태 필터가 없다.

FAIL 행을 엑셀에서 제외하려면 다음과 같은 별도 기능이 필요하다.

```sql
WHERE hist_id = ?
  AND row_status = 'SUCCESS'
```

현재 Repository 코드는 해당 조건을 사용하지 않는다.

### 32.9 엑셀에 상태 컬럼 미포함

현재 `get_excel_data()`는 `config.json columns`만 조회한다.

따라서 다음 공통 컬럼은 엑셀에 포함되지 않는다.

```text
row_status
row_error_message
row_start_at
row_end_at
```

상태와 오류를 엑셀에 표시해야 하면 별도 옵션을 설계해야 한다.

### 32.10 다건 저장은 동일 상태

`insert_details()`에 성공 행과 실패 행을 섞어 전달하지 않는다.

상태별로 분리한다.

```python
repository.insert_details(
    success_rows,
    row_status="SUCCESS",
)

repository.insert_details(
    fail_rows,
    row_status="FAIL",
)
```

### 32.11 finish_job 중복 호출

동일한 Repository 인스턴스에서 최초 `finish_job()`이 성공하면 `_job_finished=True`가 된다.

이후 호출은 DB UPDATE 없이 `True`를 반환한다.

---

## 33. DB 스키마 전제 조건

### worker_job_hist

최소한 다음 컬럼이 존재해야 한다.

```text
hist_id
job_id
table_name
site_name
worker_name
user_id
start_at
end_at
status
total_count
success_count
fail_count
error_message
created_at
updated_at
```

### Worker Detail 테이블

최소한 다음 요소가 필요하다.

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

config.json columns[].code 전체

created_at
updated_at
```

`detail_id`는 조회 결과 정렬에 사용한다.

```sql
ORDER BY detail_id
```

### 네이버 플레이스 Detail 상태 컬럼 예시

```sql
row_status TEXT NOT NULL DEFAULT 'SUCCESS',
row_error_message TEXT,
row_start_at TEXT,
row_end_at TEXT,
```

---

## 34. 네이버 플레이스 Worker 연동 요약

```text
ApiNaverPlaceLocAllSetWorker.init()
    ↓
driver_set()
    ↓
db_set()
    ├─ config columns 조회
    ├─ Repository 생성
    └─ initialize()
    ↓
main()
    ├─ 지역·키워드 조합
    ├─ 플레이스 ID 목록 조회
    └─ 각 Place ID 상세 처리
           ↓
       _fetch_and_save_place_detail()
           ├─ row_start_at 기록
           ├─ _fetch_place_info()
           ├─ row_end_at 기록
           ├─ 성공 → SUCCESS 행 저장
           └─ 실패 → FAIL 행 저장
    ↓
최종 작업 상태 설정
    ├─ SUCCESS
    └─ STOP
    ↓
cleanup()
    ↓
finalize_db_and_excel()
    ├─ RUNNING이면 작업 FAIL 처리
    ├─ Repository.finish_job()
    └─ auto_save_yn이면 엑셀 생성
    ↓
Repository.close()
```

### 전국 지역 검색 흐름

```text
지역 + 키워드별 Place ID 조회
    ↓
중복 ID 확인
    ↓
상세조회 시작시간 기록
    ↓
상세조회 및 저장
    ├─ 성공 행
    └─ 실패 행
    ↓
성공 데이터가 DB에 저장된 경우만
중복 제거 목록에 ID 추가
```

### 키워드 단독 검색 흐름

```text
전체 Place ID 조회
    ↓
각 ID 상세조회 및 저장
    ├─ SUCCESS 행
    └─ FAIL 행
    ↓
진행률 갱신
```

---

## 35. 관련 파일

```text
src/repositories/worker_db_repository.py
src/utils/sqlite_utils.py
src/workers/main/api_naver_place_loc_all_set_worker.py
src/workers/api_base_worker.py

resources/customers/common/db/schema_hist.sql
resources/customers/naver_place_loc_all/db/schema_detail.sql
resources/customers/naver_place_loc_all/config.json
```

기존 DB를 사용하는 경우에는 행 상태 컬럼을 추가하는 마이그레이션 SQL도 함께 관리한다.

```text
schema_detail_row_status_migration.sql
```

---

## 36. 핵심 정리

`WorkerDbRepository`는 Worker마다 반복되던 SQLite 작업을 공통화한 저장 계층이다.

최신 구조에서는 성공 데이터뿐 아니라 상세조회 실패 데이터도 행 단위 이력으로 저장한다.

```text
Worker
    ├─ 수집 수행
    ├─ 행 시작·종료시간 측정
    ├─ 성공·실패 상태 결정
    └─ 실패 원인 생성

WorkerDbRepository
    ├─ DB 연결
    ├─ 작업 이력 관리
    ├─ SUCCESS 행 저장
    ├─ FAIL 행 저장
    ├─ 성공·실패 집계
    ├─ Detail 조회
    └─ 엑셀 데이터 변환

config.json
    └─ 동적 DB 컬럼과 엑셀 컬럼 결정

ExcelUtils
    └─ Repository가 변환한 데이터를 실제 파일로 저장
```

Worker는 `config.json`의 `columns[].code`에 맞는 dict와 함께 다음 값을 Repository에 전달한다.

```text
row_status
row_error_message
row_start_at
row_end_at
```

Repository는 해당 데이터를 현재 작업의 `hist_id`, `job_id`와 연결해 저장한다.

작업 종료 시 다음 기준으로 `worker_job_hist`를 업데이트한다.

```text
success_count
    = SUCCESS 상태로 저장된 행 수

fail_count
    = FAIL 상태로 저장된 행 수
    + DB 저장 실패 행 수

total_count
    = success_count + fail_count
```

이를 통해 성공한 데이터뿐 아니라 실패한 대상, 실패 원인, 처리 시간까지 작업별로 추적할 수 있다.
