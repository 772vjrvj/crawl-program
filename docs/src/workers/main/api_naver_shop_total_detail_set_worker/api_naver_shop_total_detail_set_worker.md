# 네이버 스토어 판매자 정보 수집

## 1. 작업 정보

| 구분 | 내용 |
|---|---|
| 고객 | 갓승찬 |
| 유입 경로 | 크몽 |
| 요청 일시 | 2026-03-30 |
| 작업 금액 | 180,000원 |
| 프로그램 코드 | `NAVER_SHOP_TOTAL_DETAIL` |
| 크롤링 사이트 | `https://msearch.shopping.naver.com` |
| 작업 내용 | 네이버 쇼핑 검색 결과에서 스토어 및 방문자 정보를 수집 |
| 주요 특징 | Chrome 매크로 방식, 음성 캡차 처리, Whisper 사용 |

---

## 2. 작업 목적

네이버 쇼핑 모바일 검색 결과에서 설정한 키워드를 조회하고, 상품에 연결된 스토어 상세 페이지에 접속하여 필요한 업체 정보를 수집한다.

동일한 스토어가 여러 상품 또는 여러 키워드에서 반복 노출될 수 있으므로 최종 저장은 **스토어명 기준으로 한 번만 처리**한다.

네이버 쇼핑에서 캡차가 발생하면 음성 인증을 이용해 캡차 해결을 시도하며, 네이버 쇼핑 접속 제한 화면이 감지되면 일정 시간 요청을 중단한 뒤 동일 위치에서 재시도한다.

---

## 3. 고객 요청사항

### 검색 조건

* 고객이 입력한 검색 키워드를 콤마 기준으로 순서대로 조회
* 네이버페이 조건 적용
* N페이 조건 적용
* 등록일순 정렬 적용
* 등록일순 정렬 파라미터는 `sort=date` 사용
* 시작 페이지와 종료 페이지 범위 내에서 수집

### 수집 기준

* 상품 목록을 기준으로 스토어 상세정보 조회
* 동일 스토어가 여러 상품에서 확인돼도 최초 한 건만 저장
* 기존 DB에 저장된 스토어와 현재 실행 중 확인한 스토어를 함께 비교
* 방문자 수가 0인 데이터는 최종 저장 대상에서 제외
* 고객이 동일 키워드를 반복 입력한 경우 입력 순서를 그대로 유지

### 키워드 반복 처리

동일 키워드가 여러 번 입력돼 있더라도 자동으로 제거하지 않는다.

고객이 같은 키워드를 여러 차례 반복하여 새롭게 노출되는 업체를 추가로 수집하려는 목적이 있을 수 있기 때문이다.

```text
패션잡화, 화장품, 원피스, ...
패션잡화, 화장품, 원피스, ...
```

위처럼 동일한 키워드 묶음이 반복 입력되면 프로그램도 입력된 순서대로 반복 실행한다.

스토어명 중복 제거가 활성화된 경우 이전 순회에서 저장한 업체는 다시 저장하지 않고, 새롭게 발견된 업체만 처리한다.

---

## 4. 수집 항목

실제 수집 컬럼은 `config.json`의 `columns[].code` 정의를 기준으로 한다.

주요 수집 항목은 다음과 같다.

* 검색 키워드
* 검색 페이지
* 상품명
* 상품 URL
* 스토어명
* 스토어 URL
* 방문자 수
* 수집일시

선택된 컬럼만 엑셀 결과에 포함한다.

---

## 5. 스토어 중복 처리

스토어 중복 제거 기준은 스토어명이다.

### 기존 DB 중복 확인

프로그램 시작 시 기존 상세 테이블에서 저장된 스토어명을 조회하여 메모리에 보관한다.

```text
기존 DB 스토어명
→ 실행 중 중복 확인용 Set 생성
```

### 현재 실행 중 중복 확인

목록에서 확인된 스토어명이 기존 DB 또는 현재 실행 중 이미 처리된 스토어와 같으면 상세 조회 또는 저장 대상에서 제외한다.

```text
상품 목록 조회
→ 스토어명 추출
→ 기존 DB 스토어명 확인
→ 현재 실행 중 스토어명 확인
→ 신규 스토어만 상세 조회
```

### 방문자 수 0 처리

스토어 상세 페이지에서 방문자 수가 없거나 0으로 확인되면 최종 저장하지 않는다.

---

## 6. 프로그램 처리 순서

```text
1. 프로그램 설정값 조회
2. DB Repository 초기화
3. 작업 이력 생성
4. 기존 DB 스토어명 조회
5. 입력된 키워드 순회
6. 시작 페이지부터 종료 페이지까지 목록 조회
7. 상품 목록에서 스토어명과 상세 URL 추출
8. 기존 DB 및 현재 실행 기준 스토어명 중복 제거
9. 스토어 상세 페이지 접속
10. 캡차 발생 여부 확인
11. 음성 캡차 발생 시 Whisper로 인증 시도
12. 방문자 수 등 상세정보 추출
13. 방문자 수가 0이면 제외
14. 신규 데이터 DB 저장
15. 작업 이력 성공·실패 건수 갱신
16. 설정에 따라 엑셀 자동 저장
17. DB 작업 이력 최종 마감
```

---

## 7. 캡차 처리

네이버 쇼핑 캡차가 나타나면 음성 인증 방식을 사용한다.

### 처리 방식

```text
캡차 화면 감지
→ 음성 인증 선택
→ 시스템 오디오 녹음
→ Whisper 음성 인식
→ 인식 결과 입력
→ 캡차 완료 여부 확인
```

### 주요 구성요소

* `whisper`
* `pyaudiowpatch`
* `ffmpeg.exe`
* Chrome 브라우저
* PyAutoGUI 기반 화면 제어

### 캡차 처리 결과

프로그램 내부에서는 다음 상태를 구분한다.

```text
캡차 없음
캡차 해결 완료
캡차 해결 실패
네이버 쇼핑 접속 제한
사용자 중단
```

캡차 해결에 최종 실패하면 작업 상태를 `FAIL`로 기록하고 종료한다.

---

## 8. 네이버 쇼핑 접속 제한 처리

다음 문구 중 하나가 화면에서 확인되면 네이버 쇼핑 접속 제한으로 판단한다.

```python
ACCESS_LIMIT_TEXTS = (
    "쇼핑 서비스 접속이 일시적으로 제한되었습니다",
    "해당 네트워크의 접속을 일시적으로 제한",
    "비정상적인 접근이 감지",
)
```

### 처리 순서

```text
접속 제한 문구 감지
→ 현재 키워드와 페이지 유지
→ 브라우저 종료
→ 12시간 동안 네이버 요청 중단
→ 동일 키워드와 동일 페이지 1회 재확인
→ 정상 화면이면 작업 재개
→ 여전히 제한이면 브라우저 종료
→ 추가 12시간 대기
→ 동일 위치 1회 재확인
→ 정상 화면이면 작업 재개
→ 총 24시간 이후에도 제한이면 FAIL 처리 후 종료
```

### 중요 사항

* 제한 화면에서 페이지 재시도를 반복하지 않는다.
* 다음 페이지로 넘어가지 않는다.
* 제한 상태에서는 진행률을 증가시키지 않는다.
* 대기 중에는 네이버 쇼핑 요청을 보내지 않는다.
* 대기 중 사용자가 정지하면 즉시 `STOP` 처리한다.
* 접속 제한이 해제되면 실패했던 동일 키워드와 동일 페이지부터 재개한다.

---

## 9. DB Repository 및 상세 테이블

DB 직접 연결과 SQL 실행은 Worker에서 처리하지 않고 `WorkerDbRepository`를 사용한다.

### Repository 담당 기능

* 공통 작업 이력 테이블 초기화
* 네이버 스토어 상세 테이블 초기화
* 작업 시작 이력 생성
* 상세 데이터 저장
* 성공·실패 건수 집계
* 작업 상태 저장
* 엑셀용 데이터 조회
* DB 연결 종료

### 상세 테이블 스키마 경로

```text
crawl-program\resources\customers\naver_shop_total_detail\db\schema_detail.sql
```

스키마 파일 상단 주석도 실제 경로와 동일하게 작성한다.

```sql
-- resources/customers/naver_shop_total_detail/db/schema_detail.sql
```

`naver_shop_total`이 아니라 `naver_shop_total_detail`이 정확한 고객 디렉터리명이다.

### 상세 테이블명

```text
naver_shop_total_detail
```

상세 테이블은 실행할 때마다 새로 만드는 임시 테이블이 아니라 동일 테이블에 계속 누적 저장한다.

각 실행 결과는 `hist_id`, `job_id`, `worker_name`으로 구분한다.

### 공통 관리 컬럼

| 컬럼 | 설명 |
|---|---|
| `detail_id` | 상세 데이터 PK |
| `hist_id` | 공통 작업 이력 PK |
| `site_name` | 사이트명 |
| `worker_name` | Worker명 |
| `table_name` | 상세 테이블명 |
| `job_id` | 실행별 작업 ID |
| `user_id` | 작업자 ID |
| `row_status` | 행 처리 상태 |
| `row_error_message` | 행 단위 오류 메시지 |
| `row_start_at` | 행 처리 시작시간 |
| `row_end_at` | 행 처리 종료시간 |
| `created_at` | 생성시간 |
| `updated_at` | 수정시간 |

### 수집 데이터 컬럼

| 컬럼 | 설명 |
|---|---|
| `keyword` | 검색 키워드 |
| `crawled_at` | 수집일시 |
| `product_name` | 상품명 |
| `category` | 카테고리 |
| `product_no` | 상품번호 |
| `list_price` | 원가 |
| `low_price` | 최소가 |
| `sale_price` | 판매가격 |
| `delivery_fee` | 배송비 |
| `discount_ratio` | 할인률 |
| `brand` | 브랜드 |
| `review_count` | 리뷰수 |
| `purchase_count` | 구매건수 |
| `wish_count` | 찜하기수 |
| `store_name` | 스토어명 |
| `mall_prod_mbl_url` | 스토어 모바일 주소 |
| `mall_product_url` | 스토어 PC 주소 |
| `pc_url` | 네이버 쇼핑 PC 주소 |
| `total_visit_count` | 전체 방문자 수 |
| `page` | 검색 페이지 |
| `no` | 검색 결과 순번 |

수집 데이터 컬럼명은 `config.json`의 `columns[].code`와 동일하게 유지한다.

### 인덱스

다음 컬럼에는 조회 성능을 위한 인덱스를 생성한다.

```text
hist_id
job_id
product_no
keyword
store_name
page
crawled_at
```

주요 용도는 다음과 같다.

* `hist_id`, `job_id`: 특정 실행 결과 조회
* `product_no`: 상품번호 기준 검색
* `keyword`: 키워드별 결과 조회
* `store_name`: 기존 스토어 중복 확인
* `page`: 페이지별 결과 조회
* `crawled_at`: 수집일시 기준 정렬 및 검색

### 중복 처리 위치

DB에는 `store_name` UNIQUE 제약조건을 두지 않는다.

스토어 중복 제거 여부는 설정값 `dup_yn`에 따라 달라지므로, 중복 제거는 Worker에서 처리한다.

```text
dup_yn = true
→ 기존 DB 스토어명 + 현재 실행 스토어명 비교
→ 중복 스토어 저장 제외

dup_yn = false
→ 중복 여부와 관계없이 저장 가능
```

따라서 `store_name`에는 일반 인덱스만 생성하고 UNIQUE 인덱스는 생성하지 않는다.

### 작업 상태

```text
RUNNING : 작업 진행 중
SUCCESS : 정상 완료
STOP    : 사용자 중단
FAIL    : 오류 또는 접속 제한 지속
```

### 행 단위 상태

```text
SUCCESS : 상세 수집 및 저장 성공
FAIL    : 상세 조회 또는 저장 실패
```

---

## 10. 설정 항목

### 일반 설정

* 저장 폴더
* 엑셀 자동 저장 여부
* 중복 제거 여부
* 검색 키워드
* 시작 페이지
* 종료 페이지
* 상세 조회 여부

### 검색 설정

* 네이버페이 조건
* N페이 조건
* 등록일순 정렬
* 페이지당 조회 범위

### 출력 설정

* DB 저장 컬럼
* 엑셀 출력 컬럼
* 상세정보 컬럼 선택

---

## 11. 주요 파일 경로

### 네이버 스토어 Worker

```text
crawl-program\src\workers\main\api_naver_shop_total_detail_set_worker.py
```

* 네이버 쇼핑 목록 및 스토어 상세정보 수집
* 캡차 처리
* 접속 제한 처리
* DB Repository 저장

### 네이버 스토어 실행 설정

```text
crawl-program\runtime\customers\naver_shop_total_detail\config.json
```

* 키워드, 페이지, 저장 경로, 컬럼 설정 관리

### 프로그램 사이트 등록 설정

```text
crawl-program\runtime\app.json
```

* `NAVER_SHOP_TOTAL_DETAIL` Worker 및 설정 파일 경로 등록

### 네이버 스토어 상세 테이블 스키마

```text
crawl-program\resources\customers\naver_shop_total_detail\db\schema_detail.sql
```

* 네이버 스토어 수집 결과 테이블과 인덱스 생성

### 공통 작업 이력 스키마

```text
crawl-program\resources\customers\common\db\schema_hist.sql
```

* 모든 Worker가 사용하는 공통 작업 이력 테이블 생성

### 작업 이력 DB

```text
crawl-program\runtime\customers\common\db\worker_hist.db
```

* 작업 이력과 네이버 스토어 상세 데이터를 저장하는 SQLite DB

### Whisper 및 FFmpeg 리소스

```text
crawl-program\resources\customers\naver_shop_total_detail\bin\ffmpeg.exe
```

* 음성 캡차 처리에 사용하는 FFmpeg 실행 파일

### 버전 정보

```text
crawl-program\docs\src\workers\main\naver_shop_total_detail\version_info.txt
```

* PyInstaller 실행 파일 버전 정보

---

## 12. 특수 구조

이 Worker는 다른 일반 API Worker와 달리 Chrome 화면 자동화와 음성 캡차 처리를 사용한다.

### Service Loader

네이버 스토어 Worker는 별도의 Service Loader를 사용하는 구조다.

Worker 수정 또는 빌드 시 Service Loader 등록 및 호출 구조가 유지되는지 함께 확인해야 한다.

### Chrome 실행 주의사항

Chrome에 로그인된 프로필이 2개 이상 활성화돼 있으면 안 된다.

```text
Chrome 로그인 프로필 1개만 유지
```

복수 프로필 또는 여러 Chrome 창이 열려 있으면 PyAutoGUI가 잘못된 창을 제어하거나 복사한 HTML이 다른 탭에서 가져와질 수 있다.

---

## 13. 수집 종료 조건

다음 조건 중 하나가 발생하면 작업을 종료한다.

* 설정된 모든 키워드와 페이지 수집 완료
* 사용자가 작업 중지
* 캡차 최종 해결 실패
* 네이버 쇼핑 접속 제한이 총 24시간 이후에도 유지
* Chrome 제어 불가
* 복구할 수 없는 DB 오류
* 복구할 수 없는 프로그램 예외

---

## 14. 프로그램 빌드

네이버 스토어 전용 실행 파일은 프로젝트 루트에서 PowerShell로 빌드한다.

### 빌드 명령어

```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "네이버 스토어" `
--version-file ".\docs\src\workers\main\naver_shop_total_detail\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--icon ".\resources\icons\crawling.ico" `
--add-data "E:\git\crawl-program\venv\Lib\site-packages\whisper\assets;whisper\assets" `
--add-data ".\resources\customers\naver_shop_total_detail\bin;resources\customers\naver_shop_total_detail\bin" `
--add-data ".\resources\customers\common\db;resources\customers\common\db" `
--add-data ".\resources\customers\naver_shop_total_detail\db;resources\customers\naver_shop_total_detail\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons" `
--hidden-import "src.workers.main.api_naver_shop_total_detail_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--hidden-import "pyaudiowpatch" `
--hidden-import "whisper" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl
```

### `--add-data` 형식

```text
--add-data "원본경로;실행시경로"
```

Windows 환경에서는 원본 경로와 실행 시 경로를 세미콜론(`;`)으로 구분한다.

---

## 15. 빌드 후 작업

PyInstaller 빌드가 완료되면 FFmpeg 파일 위치를 확인한다.

### 원본 파일

```text
resources\customers\naver_shop_total_detail\bin\ffmpeg.exe
```

### 빌드 결과에 필요한 위치

```text
dist\네이버 스토어\_internal\resources\bin\ffmpeg.exe
```

빌드 후 다음 경로가 되도록 파일을 복사한다.

```text
/resources/customers/naver_shop_total_detail/bin/ffmpeg.exe
→
_internal/resources/bin/ffmpeg.exe
```

PowerShell 예시:

```powershell
New-Item `
-ItemType Directory `
-Force `
".\dist\네이버 스토어\_internal\resources\bin" | Out-Null

Copy-Item `
".\resources\customers\naver_shop_total_detail\bin\ffmpeg.exe" `
".\dist\네이버 스토어\_internal\resources\bin\ffmpeg.exe" `
-Force
```

### 빌드 후 확인 항목

* `네이버 스토어.exe` 실행 여부
* Chrome 정상 실행 여부
* Chrome 프로필 1개만 사용 중인지 확인
* Whisper 모델 로딩 여부
* 음성 녹음 장치 인식 여부
* FFmpeg 파일 경로 확인
* 공통 DB 스키마 포함 여부
* 네이버 스토어 상세 DB 스키마 포함 여부
* `naver_shop_total_detail` 테이블 및 인덱스 생성 여부
* Service Loader에서 Worker 로딩 여부
* 접속 제한 문구 감지 여부
* 12시간 대기 중 정지 기능 동작 여부

---

## 16. 개발 및 운영 주의사항

### 브라우저

* 실행 전 Chrome 창을 모두 종료한다.
* Chrome 로그인 계정 또는 프로필은 하나만 유지한다.
* 작업 중 사용자가 마우스나 키보드를 조작하지 않는다.
* 화면 해상도와 배율을 임의로 변경하지 않는다.

### 네트워크

* 네이버 쇼핑에서 접속 제한이 발생하면 프로그램이 자동 대기한다.
* 대기 중 수동으로 네이버 쇼핑을 반복 새로고침하지 않는다.
* 같은 네트워크의 다른 PC에서 대량 요청이 발생하면 제한에 영향을 줄 수 있다.

### 캡차

* 시스템 오디오 녹음 장치가 활성화돼 있어야 한다.
* FFmpeg 실행 파일이 지정된 경로에 있어야 한다.
* Whisper assets가 빌드 결과에 포함돼 있어야 한다.

---

## 17. 개발 진행 상태

### 완료

* 네이버 쇼핑 키워드 목록 조회
* 네이버페이 조건 적용
* N페이 조건 적용
* 등록일순 `sort=date` 적용
* 스토어명 중복 제거
* 방문자 수 0 제외
* DB 조회 팝업 추가
* Chrome 화면 자동화
* 음성 캡차 처리
* Whisper 연동
* DB Repository 적용
* `naver_shop_total_detail` 고정 누적 테이블 적용
* 실행 이력·스토어명·키워드·페이지·수집일시 인덱스 적용
* 작업 이력 저장
* 상세 데이터 저장
* 자동 엑셀 저장
* 네이버 쇼핑 접속 제한 문구 감지
* 접속 제한 시 12시간 + 12시간 대기
* 총 24시간 이후 제한 지속 시 `FAIL` 종료
* 대기 중 사용자 정지 처리

### 운영 확인

* 장시간 실행 시 Chrome 안정성 확인
* 고객 PC의 오디오 장치 확인
* 접속 제한 해제 후 동일 페이지 재개 확인
* PyInstaller 빌드 결과에서 FFmpeg 경로 확인
* Service Loader 정상 동작 확인