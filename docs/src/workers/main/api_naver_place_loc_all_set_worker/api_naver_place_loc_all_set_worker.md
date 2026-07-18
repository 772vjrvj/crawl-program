# 네이버 플레이스 전국 정보 수집

## 1. 프로그램 정보

| 구분 | 내용 |
|---|---|
| 프로그램명 | 네이버 플레이스 |
| 화면 표시명 | 네이버 플레이스 전국 |
| 프로그램 키 | `NAVER_PLACE_LOC_ALL` |
| DB 구분명 | `NAVER_PLACE_LOC_ALL` |
| Worker 이름 | `naver_place_loc_all` |
| 상세 테이블명 | `naver_place_loc_all` |
| 공통 작업 이력 테이블 | `WORKER_JOB_HIST` |
| Worker 클래스 | `ApiNaverPlaceLocAllSetWorker` |
| Worker 경로 | `src.workers.main.api_naver_place_loc_all_set_worker` |
| 실행 방식 | 지역 + 키워드 조합 검색 |
| 결과 저장 | SQLite DB 및 선택적 엑셀 자동 저장 |

---

## 2. 작업 목적

사용자가 입력한 키워드와 선택한 지역 단위를 조합하여 네이버 플레이스를 검색하고, 검색 결과에 포함된 업체의 상세 정보를 수집한다.

예시:

```text
지역 단위: 읍면동
지역: 경기도 수원시 영통구 망포동
키워드: 펜션

최종 검색어:
경기도 수원시 영통구 망포동 펜션
```

수집된 결과는 먼저 작업 DB의 상세 테이블에 저장하고, 설정에서 자동 엑셀 저장을 활성화한 경우 작업 종료 시 엑셀 파일로 내보낸다.

---

## 3. 주요 기능

* 여러 키워드를 콤마로 구분하여 입력
* 전국 지역 목록과 키워드를 조합하여 검색
* 시도, 시군구, 읍면동 단위 선택
* 네이버 플레이스 목록 API 조회
* 플레이스 상세 페이지 정보 수집
* 방문자 리뷰, 블로그 리뷰, 영수증 리뷰 정보 수집
* 영업시간, 메뉴, 좌석, 편의시설, 주차 정보 수집
* 대표 이미지, 소개, 홈페이지, 전화번호 수집
* 선택한 경우 우편번호 추가 조회
* 선택한 경우 네이버 예약 대행사 정보 추가 조회
* Place ID 기준 중복 제거
* 성공 및 실패 결과를 DB에 모두 기록
* 작업 종료 시 엑셀 자동 저장

---

## 4. 설정 항목

### 키워드

```json
{
  "name": "1. 키워드(콤마(,)로 구분해주세요)",
  "code": "keyword",
  "value": "리조트, 펜션, 호스텔, 민박, 한옥, 글램핑, 카라반, 캠핑",
  "type": "input"
}
```

여러 키워드는 콤마로 구분한다.

```text
리조트, 펜션, 호스텔, 민박
```

프로그램 시작 시 입력값을 분리하여 키워드 목록으로 만든다.

---

### 지역 단위 선택

```json
{
  "name": "지역구 선택",
  "code": "naver_loc",
  "value": "읍면동",
  "type": "select"
}
```

선택 가능한 값:

* 시도
* 시군구
* 읍면동

선택한 지역 단위에 따라 검색어에 포함되는 주소 범위가 달라진다.

#### 시도

```text
경기도 펜션
서울특별시 호스텔
```

#### 시군구

```text
경기도 수원시 펜션
서울특별시 강남구 호스텔
```

#### 읍면동

```text
경기도 수원시 영통구 망포동 펜션
서울특별시 강남구 역삼동 호스텔
```

지역 목록은 선택 단위에 맞게 중복 제거한 뒤 실행한다.

---

### 저장 폴더

```json
{
  "code": "folder_path",
  "value": "E:\\git\\crawl-program",
  "type": "folder"
}
```

엑셀 자동 저장 시 선택한 폴더 아래의 `output` 폴더에 결과가 생성된다.

---

### 자동 엑셀 저장

```json
{
  "code": "auto_save_yn",
  "value": true,
  "type": "check"
}
```

활성화하면 작업 종료 시 DB에 저장된 상세 데이터를 엑셀 파일로 내보낸다.

파일명 형식:

```text
네이버 플레이스 전국_{JOB_ID}.xlsx
```

---

### 중복 제거

```json
{
  "code": "remove_duplicate_yn",
  "value": true,
  "type": "check"
}
```

활성화하면 같은 실행 중 이미 저장한 Place ID는 다시 상세 조회하지 않는다.

중복 기준:

```text
Place ID
```

상세 조회와 DB 저장이 모두 성공한 Place ID만 중복 목록에 추가한다.

따라서 상세 조회에 실패한 Place ID는 다른 검색어에서 다시 발견될 경우 재시도할 수 있다.

---

## 5. 지역 처리 방식

현재 설정은 다음과 같다.

```json
{
  "region": true
}
```

`region=true`이면 전국 지역 목록과 키워드를 조합하여 검색한다.

처리 흐름:

```text
전체 지역 목록 조회
→ 선택한 지역 단위 확인
→ 시도/시군구/읍면동 기준으로 지역 목록 가공
→ 동일 지역 중복 제거
→ 각 지역과 각 키워드를 조합
→ 네이버 플레이스 검색
```

예시:

```text
지역 목록:
경기도 수원시 영통구 망포동
경기도 수원시 팔달구 인계동

키워드:
펜션
리조트

생성되는 검색어:
경기도 수원시 영통구 망포동 펜션
경기도 수원시 영통구 망포동 리조트
경기도 수원시 팔달구 인계동 펜션
경기도 수원시 팔달구 인계동 리조트
```

---

## 6. 전체 처리 흐름

```text
1. 프로그램 설정값 조회
2. 키워드 문자열을 콤마 기준으로 분리
3. 저장 폴더, 지역 단위, 엑셀 저장 여부 확인
4. APIClient, ExcelUtils, FileUtils 생성
5. WorkerDbRepository 생성
6. 공통 작업 이력 및 상세 테이블 스키마 초기화
7. 선택된 지역 단위에 맞게 지역 목록 가공
8. 지역과 키워드를 조합하여 전체 검색어 생성
9. 네이버 플레이스 목록 API를 페이지 단위로 조회
10. 검색 결과에서 Place ID 수집
11. Place ID 기준 중복 여부 확인
12. 플레이스 상세 페이지 조회
13. APOLLO_STATE 데이터 파싱
14. 상세 정보 추출
15. 필요한 경우 우편번호 추가 조회
16. 필요한 경우 네이버 예약 대행사 정보 추가 조회
17. 상세 결과를 DB에 저장
18. 실패한 상세 조회도 FAIL 상태로 DB에 저장
19. 작업 이력 SUCCESS, STOP 또는 FAIL 처리
20. 자동 저장 설정 시 DB 데이터를 엑셀로 저장
21. DB, API, 파일, 엑셀 객체 정리
```

---

## 7. 목록 조회 방식

네이버 플레이스 목록은 다음 GraphQL API를 사용한다.

```text
POST https://pcmap-api.place.naver.com/graphql
```

주요 요청값:

```text
operationName: getPlacesList
start: (페이지 - 1) × 100 + 1
display: 100
query: 지역 + 키워드
deviceType: pcmap
```

페이지당 최대 요청 수:

```text
100개
```

처리 흐름:

```text
1페이지 조회
→ Place ID 목록 수집
→ 다음 페이지 조회
→ 결과가 없으면 목록 조회 종료
```

목록 조회 사이에는 과도한 연속 요청을 줄이기 위해 임의 대기 시간을 적용한다.

```text
1초 ~ 2초
```

---

## 8. 상세 조회 방식

각 Place ID에 대해 다음 모바일 플레이스 페이지를 조회한다.

```text
https://m.place.naver.com/place/{PLACE_ID}
```

상세 페이지의 HTML에서 다음 스크립트 데이터를 찾는다.

```text
window.__APOLLO_STATE__
```

추출 흐름:

```text
HTML 조회
→ script 태그 검색
→ window.__APOLLO_STATE__ 위치 확인
→ JSON 시작 위치 확인
→ JSONDecoder로 데이터 파싱
→ PlaceDetailBase 및 ROOT_QUERY 분석
→ 상세 항목 추출
```

상세 조회 사이에는 임의 대기 시간을 적용한다.

```text
2초 ~ 4초
```

---

## 9. 수집 항목

### 기본 정보

* 아이디
* 이름
* 주소(지번)
* 주소(도로명)
* 대분류
* 소분류
* 전체 카테고리
* URL
* 지도
* 대표 이미지 URL
* 소개
* 주소지 정보

---

### 리뷰 정보

* 방문자 리뷰 평점
* 방문자 리뷰 수
* 키워드·별점 리뷰 수
* 블로그 리뷰 수
* 영수증 리뷰 수
* AI 요약

방문자 리뷰 수는 전체 방문자 리뷰 수에서 키워드·별점 리뷰 수를 제외하여 계산한다.

```text
방문자 리뷰 수
= visitorReviewsTotal - ratingReviewsTotal
```

값이 0인 일부 리뷰 항목은 결과에서 빈 값으로 처리한다.

---

### 운영 정보

* 이용시간1
* 이용시간2
* 편의시설 및 서비스
* 테마
* 메뉴
* 좌석·공간
* 주차 가능
* 발렛 가능
* 주차 상세
* 결제 수단

`이용시간1`은 새로운 영업시간 구조를 기준으로 정리한다.

포함 가능한 정보:

* 요일
* 시작 시간
* 종료 시간
* 브레이크타임
* 라스트오더
* 휴무 또는 설명

`이용시간2`는 기존 영업시간 구조를 기준으로 정리한다.

---

### 연락처 및 외부 연결

* 가상번호
* 전화번호
* 사이트
* 연관 키워드

홈페이지는 네이버 플레이스 상세 데이터의 대표 홈페이지와 기타 홈페이지를 모아 저장한다.

---

### 검색 기준 정보

* 시도(검색)
* 시군구(검색)
* 읍면동(검색)
* 키워드(검색)
* 전체 검색어

예시:

```text
시도(검색): 경기도
시군구(검색): 수원시 영통구
읍면동(검색): 망포동
키워드(검색): 펜션
전체 검색어: 경기도 수원시 영통구 망포동 펜션
```

---

### 우편번호

* 우편번호

`zip_code` 컬럼이 선택된 경우에만 추가 조회한다.

조회 순서:

```text
지번 주소 조회
→ 실패 시 도로명 주소 조회
```

조회 URL:

```text
https://event.naver.com/personalInfo/zipCode
```

처리 기준:

* 4자리 우편번호는 앞에 `0`을 붙여 5자리로 복원
* 5자리 우편번호는 그대로 사용
* 6자리 구우편번호는 사용하지 않음

---

### 네이버 예약 대행사 정보

* 대행사 상호
* 대행사 대표자명
* 대행사 소재지
* 대행사 사업자번호
* 대행사 통신판매업번호
* 대행사 연락처
* 대행사 홈페이지

대행사 관련 컬럼 중 하나라도 선택된 경우에만 추가 조회한다.

처리 흐름:

```text
플레이스 상세 데이터에서 bookingBusinessId 추출
→ 네이버 예약 페이지 조회
→ window.__APOLLO_STATE__ 파싱
→ Business:{bookingBusinessId} 데이터 확인
→ agencies 첫 번째 항목 추출
```

조회 URL:

```text
https://booking.naver.com/booking/3/bizes/{BOOKING_BUSINESS_ID}
```

선택하지 않은 경우 불필요한 네이버 예약 페이지 요청을 하지 않는다.

---

## 10. 컬럼 선택 처리

화면에서 `checked=true`인 컬럼만 엑셀 출력 대상으로 사용한다.

DB 저장 기준:

```text
columns[].code
```

엑셀 헤더 기준:

```text
columns[].value
```

예시:

```json
{
  "code": "name",
  "value": "이름",
  "checked": true
}
```

DB에는 `name` 컬럼으로 저장하고, 엑셀에는 `이름`이라는 헤더로 출력한다.

일부 추가 조회는 컬럼 선택 여부에 따라 실행된다.

```text
zip_code 선택
→ 우편번호 조회 실행

대행사 컬럼 중 하나 이상 선택
→ 네이버 예약 대행사 조회 실행
```

---

## 11. DB 저장 구조

DB 처리는 `WorkerDbRepository`를 사용한다.

### 작업 시작

```text
WorkerDbRepository 생성
→ schema_hist.sql 실행
→ schema_detail.sql 실행
→ 작업 이력 RUNNING 생성
```

### 상세 저장

성공한 상세 정보는 다음 상태로 저장한다.

```text
row_status = SUCCESS
```

상세 조회에 실패해도 최소 정보를 포함한 실패 행을 저장한다.

실패 행에 남는 주요 정보:

* Place ID
* 플레이스 URL
* 지도 URL
* 검색 시도
* 검색 시군구
* 검색 읍면동
* 검색 키워드
* 전체 검색어
* 오류 메시지
* 행 시작 시간
* 행 종료 시간

실패 상태:

```text
row_status = FAIL
```

이 구조를 통해 상세 조회 실패 건도 작업 DB에서 확인할 수 있다.

---

## 12. 작업 종료 상태

작업 이력 상태는 다음과 같이 처리한다.

### 정상 완료

```text
SUCCESS
```

### 사용자 중단

```text
STOP
```

오류 메시지:

```text
사용자 중단
```

### 비정상 종료

작업 종료 시 상태가 계속 `RUNNING`이면 다음과 같이 처리한다.

```text
FAIL
```

오류 메시지:

```text
비정상 종료
```

종료 시 상세 성공·실패 건수를 집계하여 작업 이력 테이블을 최종 업데이트한다.

---

## 13. 엑셀 저장

자동 엑셀 저장이 활성화된 경우 작업 종료 단계에서 DB 데이터를 조회하여 엑셀을 생성한다.

처리 흐름:

```text
DB 상세 데이터 조회
→ 체크된 엑셀 컬럼 확인
→ 엑셀 파일 생성
→ 설정한 저장 폴더의 output 폴더에 저장
```

파일명:

```text
네이버 플레이스 전국_{JOB_ID}.xlsx
```

저장 대상 데이터가 없는 경우 엑셀 파일을 만들지 않는다.

---

## 14. 진행률 계산 기준

지역 검색 모드에서는 다음 값을 예상 수집량으로 사용한다.

```text
예상 수집 수
= 실행 지역 수 × 키워드 수 × 300

예상 페이지 수
= 실행 지역 수 × 키워드 수 × 15
```

이 값은 진행률 표시를 위한 예상치다.

실제 결과 수와 페이지 수는 네이버 검색 결과에 따라 달라질 수 있다.

---

## 15. 중지 및 정리 처리

사용자가 작업을 중지하면 다음 순서로 처리한다.

```text
running = false
→ 작업 상태 STOP 저장
→ DB 작업 이력 마감
→ 자동 엑셀 저장 처리
→ DB 연결 종료
→ APIClient 종료
→ FileUtils 종료
→ ExcelUtils 종료
```

`cleanup()`은 중복 실행되지 않도록 `_cleaned_up` 상태값으로 보호한다.

---

## 16. 검색 컬럼

결과 조회 화면에서 다음 항목을 검색 조건으로 사용할 수 있다.

* 아이디
* 이름
* 주소(도로명)
* 주소(지번)
* 카테고리
* 키워드(검색)
* 전체 검색어
* 시도(검색)
* 시군구(검색)
* 읍면동(검색)

---

## 17. 주요 파일 경로

### Worker

```text
src\workers\main\api_naver_place_loc_all_set_worker.py
```

* 네이버 플레이스 목록 및 상세 정보 수집
* DB 저장
* 엑셀 자동 저장
* 중복 제거
* 지역 및 키워드 순회 처리

### 전국 지역 데이터

```text
resources\customers\naver_place_loc_all\naver_loc_all_real.json
```

* 전국 시도, 시군구, 읍면동 지역 정보

### 상세 테이블 스키마

```text
resources\customers\naver_place_loc_all\db\schema_detail.sql
```

* 네이버 플레이스 상세 결과 테이블 및 인덱스 생성

### 공통 작업 이력 스키마

```text
resources\customers\common\db\schema_hist.sql
```

* Worker 공통 작업 이력 테이블 생성

### 프로그램 아이콘

```text
resources\icons\crawling.ico
```

### 버전 정보

현재 빌드 명령에 지정된 경로:

```text
docs\customers\naver_place_url_all\version_info.txt
```

프로그램 이름이 `naver_place_loc_all`이므로 실제 버전 파일 폴더명이 올바른지 빌드 전에 확인한다.

---

## 18. 프로그램 빌드

프로젝트 루트에서 PowerShell로 실행한다.

```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_naver_place_loc_all_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_place_loc_all_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all" `
--add-data ".\resources\customers\naver_place_loc_all\db\schema_detail.sql;resources\customers\naver_place_loc_all\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"
```

---

## 19. 빌드 전 확인사항

### console과 windowed 옵션

현재 명령에는 다음 옵션이 함께 들어 있다.

```text
--console
--windowed
```

두 옵션은 콘솔 표시 여부를 결정하는 반대 성격의 옵션이다.

GUI 프로그램으로 배포할 경우 일반적으로 다음처럼 `--windowed`만 유지한다.

```powershell
--windowed `
```

개발 중 로그 콘솔이 필요한 경우에는 다음처럼 `--console`만 사용한다.

```powershell
--console `
```

### 버전 파일 경로

현재 버전 파일 경로:

```text
docs\customers\naver_place_url_all\version_info.txt
```

Worker와 리소스 이름:

```text
naver_place_loc_all
```

실제 폴더 구조가 다음 이름으로 되어 있다면 빌드 명령도 맞춰야 한다.

```text
docs\customers\naver_place_loc_all\version_info.txt
```

---

## 20. 핵심 정리

이 프로그램은 전국 지역 정보와 사용자가 입력한 키워드를 조합하여 네이버 플레이스를 검색하고, 각 Place ID의 상세 정보를 수집하는 프로그램이다.

핵심 흐름:

```text
지역 단위 선택
→ 지역 목록 가공
→ 지역 + 키워드 검색어 생성
→ 네이버 플레이스 목록 조회
→ Place ID 수집
→ Place ID 중복 제거
→ 상세 페이지 APOLLO_STATE 파싱
→ 선택 컬럼 기준 추가 정보 조회
→ DB 저장
→ 작업 이력 마감
→ 엑셀 자동 저장
```

핵심 중복 기준:

```text
Place ID
```

핵심 저장 기준:

```text
DB에는 columns[].code
엑셀에는 columns[].value
```

핵심 추가 조회 최적화:

```text
우편번호 컬럼 선택 시에만 우편번호 조회
대행사 컬럼 선택 시에만 네이버 예약 대행사 조회
```