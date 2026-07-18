# 네이버 부동산 매물 광고 수집

## 1. 작업 정보

| 구분 | 내용 |
|---|---|
| 고객 | 하얀토끼0102 |
| 요청 일자 | 2026-06-08 |
| 금액 | 220,000원 |
| 작업 내용 | 네이버 부동산 매물 광고 수집 |
| 핵심 기능 | 좌표 기반 역지오코딩, 주소 중복 제거, 장기 광고 매물 BAN 처리, 등록일 범위 필터 |

---

## 2. 작업 목적

네이버 부동산에서 선택한 지역과 검색 조건에 해당하는 매물 목록을 수집한다.

목록에서 제공되는 위도와 경도를 역지오코딩 API로 전달하여 **도로명주소와 지번주소를 보완**하고, 동일한 주소로 반복 등록된 광고를 제거한다.

특히 같은 주소가 서로 다른 날짜에 반복 노출된 경우에는 장기간 광고 중인 매물로 판단하여, 기존에 저장한 데이터까지 제거한 뒤 해당 주소를 현재 작업에서 BAN 처리한다.

최종적으로 다음 조건을 모두 만족하는 매물만 DB와 엑셀에 저장한다.

```text
선택 지역과 검색 조건에 해당함
→ 매물번호가 중복되지 않음
→ 도로명주소 또는 지번주소가 존재함
→ 동일 날짜의 동일 주소는 최초 1건임
→ 서로 다른 날짜에 반복된 주소가 아님
→ 설정한 등록 시작일과 종료일 사이에 포함됨
```

---

## 3. 고객 요청사항

### 3.1 역지오코딩

네이버 부동산 목록에서 제공하는 위도와 경도를 주소 API로 전달하여 다음 주소를 조회한다.

* 도로명주소
* 지번주소

주소 API 결과의 우선순위는 다음과 같다.

```text
도로명주소가 있으면 전체주소에 도로명주소 사용
도로명주소가 없고 지번주소가 있으면 전체주소에 지번주소 사용
```

### 3.2 동일 주소는 한 번만 저장

도로명주소 또는 지번주소가 동일한 매물이 여러 건 존재하면 같은 날짜에서는 최초 한 건만 저장한다.

```text
도로명주소 동일 + 같은 날짜
→ 최초 1건 저장
→ 이후 매물 제외

지번주소 동일 + 같은 날짜
→ 최초 1건 저장
→ 이후 매물 제외
```

도로명주소와 지번주소를 각각 중복키로 관리하므로, 둘 중 하나라도 기존 이력과 일치하면 중복으로 판단할 수 있다.

### 3.3 여러 날짜에 반복된 광고 제거

오늘 등록된 것처럼 보이더라도 같은 주소가 서로 다른 날짜에 반복 노출되면 장기간 광고 중인 매물로 판단한다.

같은 주소가 2일 이상에 걸쳐 발견되면 다음과 같이 처리한다.

```text
첫 번째 날짜에 주소 A 발견
→ 임시 저장 대상

다른 날짜에 주소 A 재발견
→ 이전에 DB에 저장한 주소 A 삭제
→ 아직 DB 저장 전 대기열에 있던 주소 A 삭제
→ 주소 A BAN 처리
→ 이후 주소 A는 모두 저장하지 않음
```

BAN 처리는 도로명주소와 지번주소에 각각 적용한다.

### 3.4 날짜 범위 필터

설정 화면의 다음 값을 사용한다.

* 등록일 시작: `fr_date`
* 등록일 종료: `to_date`

날짜 형식은 `YYYYMMDD`이다.

예시:

```text
등록 시작일: 20260618
등록 종료일: 20260620

저장 대상: 2026-06-18 ~ 2026-06-20
```

설정한 시작일과 종료일 사이에 포함되지 않는 매물은 최종 저장에서 제외한다.

### 3.5 결과 컬럼 순서

고객이 요청한 핵심 컬럼 순서는 다음과 같다.

```text
매물명
→ 번지
→ 도로명주소
→ 매매가
→ 등록일자
→ 대지면적
→ 연면적
→ 건축면적
→ 나머지 선택 컬럼
```

현재 설정 파일에는 `매물번호`가 첫 번째 컬럼으로 등록되어 있으므로, 고객 요청 순서를 정확히 적용하려면 `config.json`의 `columns` 순서를 조정해야 한다.

---

## 4. 핵심 함수

```python
_save_list_items_multi
```

이 함수가 일반 목록 수집 모드에서 다음 핵심 처리를 담당한다.

* 매물번호 전역 중복 제거
* 역지오코딩 API 일괄 호출
* 주소 API 캐시 적용
* 도로명주소와 지번주소 보완
* 동일 주소 중복 제거
* 다른 날짜에 반복된 주소 BAN 처리
* 기존 DB 데이터 삭제
* DB 저장 대기열 데이터 삭제
* 날짜 범위 필터
* SQLite Bulk Insert
* 저장 성공한 매물번호 전역 등록

---

## 5. `_save_list_items_multi` 처리 순서

### 5.1 매물번호 중복 제거

처음 받은 매물 목록에서 매물번호를 기준으로 중복을 제거한다.

제외 조건은 다음과 같다.

* 매물번호가 없는 데이터
* 이전 지역 처리에서 이미 DB 저장에 성공한 매물번호
* 현재 목록 안에서 중복된 매물번호

사용하는 전역 중복 저장소:

```python
self.saved_article_numbers: set[str]
```

매물번호는 DB 저장에 성공한 이후에만 전역 중복 저장소에 추가한다.

따라서 DB 저장에 실패한 매물이 중복 저장소에 먼저 들어가 재처리되지 않는 문제를 방지한다.

### 5.2 역지오코딩 주소 조회

중복 제거가 끝난 매물을 주소 API로 전달한다.

현재 주요 설정:

```text
chunk_size = 100
address_max_workers = 1
```

주소 API 요청 데이터:

```json
{
  "id": "매물번호",
  "lat": "위도",
  "lng": "경도",
  "sido": "시도",
  "sigungu": "시군구",
  "eupmyeondong": "읍면동"
}
```

API 인증은 요청 헤더의 `X-API-KEY`를 사용한다.

```text
POST {server_url}
X-API-KEY: {master_api_key}
Content-Type: application/json
```

`master_api_key`는 문서나 Git 저장소에 실제 값을 노출하지 않고 런타임 설정에서 관리한다.

### 5.3 주소 API 캐시

같은 실행 안에서 동일한 좌표를 다시 조회하지 않도록 주소 결과를 메모리에 캐시한다.

```python
self.address_cache
```

캐시 키는 위도와 경도를 소수점 5자리까지 내림 처리하여 생성한다.

```text
위도|경도
```

같은 좌표의 캐시 결과를 다른 매물에 재사용할 때는 응답의 `id`만 현재 매물번호로 교체한다.

### 5.4 주소 데이터 보완

주소 API 결과를 매물번호 기준으로 원본 매물과 결합한다.

```text
road_address.address_name
→ 도로명주소

address.address_name
→ 번지
```

도로명주소가 있으면 전체주소에 도로명주소를 우선 적용한다.

### 5.5 주소 이력 확인

주소 중복과 BAN 상태는 다음 전역 저장소로 관리한다.

```python
self.global_address_history
```

저장 구조:

```python
{
    "주소": {
        "date": "YYYYMMDD",
        "banned": False
    }
}
```

도로명주소와 지번주소를 각각 별도의 키로 등록한다.

### 5.6 주소가 없는 매물 제거

다음 두 값이 모두 없으면 주소 중복 여부를 판단할 수 없으므로 저장하지 않는다.

```text
도로명주소 없음
AND
지번주소 없음
→ 저장 제외
```

### 5.7 이미 BAN된 주소 제거

도로명주소 또는 지번주소 중 하나라도 기존 이력에서 `banned=True`이면 해당 매물을 즉시 제외한다.

### 5.8 다른 날짜에 반복된 주소 처리

주소 이력에 존재하지만 기존 날짜와 현재 날짜가 다르면 장기간 반복 광고로 판단한다.

처리 순서:

```text
1. 현재 작업 hist_id로 DB에 이미 저장된 동일 주소 삭제
2. detail_success_count에서 삭제 건수 차감
3. 현재 Bulk Insert 대기열에 있는 동일 주소 삭제
4. 도로명주소 BAN 처리
5. 지번주소 BAN 처리
6. 현재 매물 저장 제외
```

DB 삭제 조건:

```sql
DELETE FROM naver_land_real_estate_ad
WHERE hist_id = ?
  AND (
      roadName = ?
      OR jibun = ?
  )
```

BAN 처리된 주소는 현재 실행이 종료될 때까지 다시 저장하지 않는다.

### 5.9 같은 날짜의 동일 주소 제거

주소 이력의 날짜와 현재 매물 날짜가 같으면 동일 날짜 중복으로 판단한다.

```text
최초 주소 1건
→ 저장 대상

동일 날짜 동일 주소 재발견
→ 저장 제외
```

### 5.10 새로운 주소 등록

처음 발견한 주소는 `banned=False` 상태로 주소 이력에 등록하고 DB 저장 대기열에 추가한다.

### 5.11 최종 날짜 필터

주소 중복과 BAN 처리가 끝난 데이터에 날짜 범위 필터를 적용한다.

현재 Worker는 다음 우선순위로 날짜값을 구한다.

```python
매물확인일 or 등록일자
```

날짜의 `-`, `.`, `/` 문자를 제거한 뒤 `YYYYMMDD` 문자열로 비교한다.

```text
fr_date <= 날짜 <= to_date
```

범위 밖의 데이터는 제외한다.

### 5.12 Bulk Insert

최종 데이터는 SQLite `executemany`로 일괄 저장한다.

```text
최종 데이터
→ chunk_size 단위 분할
→ bulk_insert_detail_rows()
→ DB commit
→ 성공한 매물번호를 saved_article_numbers에 추가
```

현재 실제 저장 단위는 `chunk_size=100`이다.

코드 주석에는 20개 단위라고 적혀 있지만 실제 로직은 100개 단위이므로 주석 수정이 필요하다.

---

## 6. 주소 중복 및 BAN 판단표

| 기존 주소 이력 | 날짜 비교 | 처리 결과 |
|---|---|---|
| 없음 | 해당 없음 | 최초 1건 저장 대상 |
| 있음, `banned=True` | 관계없음 | 저장 제외 |
| 있음, `banned=False` | 같은 날짜 | 동일 날짜 중복으로 저장 제외 |
| 있음, `banned=False` | 다른 날짜 | 기존 저장 데이터 삭제 후 BAN 처리 |
| 도로명과 지번 모두 없음 | 해당 없음 | 저장 제외 |

---

## 7. 날짜 처리 기준

### 고객 요구 기준

고객 요구사항은 **매물 등록일자**를 기준으로 시작일과 종료일 사이의 매물만 저장하는 것이다.

### 현재 코드 기준

현재 `_save_list_items_multi`의 중복 날짜 및 최종 날짜 필터는 다음 순서로 날짜를 선택한다.

```python
rs.get("매물확인일") or rs.get("등록일자")
```

따라서 `매물확인일`이 존재하면 `등록일자`보다 먼저 사용한다.

또한 목록 수집 함수에는 `articleConfirmDate`를 기준으로 페이지를 조기 종료하는 함수가 작성되어 있지만, 현재 해당 호출 부분은 주석 처리되어 있다.

```text
현재 실제 동작
→ 목록은 계속 수집
→ _save_list_items_multi에서 최종 날짜 필터 수행
```

고객 요구를 정확히 적용하려면 날짜 기준을 다음과 같이 통일하는 것이 안전하다.

```python
d_val = str(rs.get("등록일자") or "")
```

---

## 8. 전체 프로그램 처리 흐름

```text
1. Worker 초기화
2. 런타임 config에서 주소 API URL과 API Key 조회
3. SQLite DB 연결
4. 공통 작업 이력 및 네이버 부동산 상세 스키마 생성
5. 작업 이력 RUNNING 저장
6. Selenium 브라우저 실행
7. 저장 폴더, 날짜, 자동 저장, 기준금액 등 설정 조회
8. 지역 데이터와 필터 데이터 로드
9. JS 리소스 로드
10. 즐겨찾기 지역/필터 또는 기본 지역/필터 작업목록 생성
11. 시도·시군구·읍면동 단위로 지역 순회
12. 네이버 부동산 목록 API 호출
13. 대표 매물과 동일주소 묶음 매물을 모두 목록에 추가
14. 매물번호 기준 중복 제거
15. 좌표 기준 역지오코딩 주소 조회
16. 도로명주소와 지번주소 보완
17. 동일 날짜 동일 주소 중복 제거
18. 다른 날짜 동일 주소 기존 데이터 삭제 및 BAN 처리
19. 날짜 범위 필터
20. SQLite Bulk Insert
21. 작업 종료 상태 및 성공·실패 건수 갱신
22. 자동 엑셀 저장이 활성화된 경우 결과 파일 생성
23. 브라우저, 파일, DB 자원 정리
```

---

## 9. 네이버 부동산 목록 처리

네이버 부동산 목록 API:

```text
POST https://fin.land.naver.com/front-api/v1/article/boundedArticles
```

페이지 처리에 사용하는 주요 값:

* `seed`
* `lastInfo`
* `hasNextPage`
* `totalCount`

수집 종료 조건:

* 목록 데이터가 없음
* `hasNextPage`가 `false`
* `seed`와 `lastInfo`가 반복되어 무한 루프 위험이 있음
* 중복 제거 후 새로 추가된 매물이 없음
* 최대 페이지 300페이지 초과
* 사용자가 작업을 중단함
* API 또는 브라우저 처리에서 복구할 수 없는 오류가 발생함

동일주소 묶음 매물은 대표 매물만 저장하지 않고 `duplicatedArticleInfo.articleInfoList`에 숨겨진 개별 매물까지 꺼내어 처리한다.

대표 매물 정보를 하위 매물에 병합하여 주소, 가격, 면적, 중개사 정보가 누락되지 않도록 구성한다.

---

## 10. 지역 및 검색 조건

### 지역 데이터

전국 시도·시군구·읍면동 데이터:

```text
resources/customers/naver_land_real_estate_ad/region/korea_eup_myeon_dong.json
```

기본 지역 선택 데이터:

```text
resources/customers/naver_place_loc_all/naver_loc_all_real.json
```

### 즐겨찾기 모드

`setting_region_filter_favorite`에 체크된 즐겨찾기가 있으면 즐겨찾기별 지역과 필터를 하나의 작업 단위로 생성한다.

```text
즐겨찾기 1
→ 선택 지역 목록
→ 즐겨찾기 전용 필터

즐겨찾기 2
→ 선택 지역 목록
→ 즐겨찾기 전용 필터
```

즐겨찾기가 없으면 기존 기본 지역과 `setting_detail_all_style` 필터를 사용한다.

### 검색 필터

설정 파일에서 다음 조건을 관리한다.

* 거래유형
* 매물유형
* 매매가, 보증금, 월세
* 면적
* 세대수와 주차 시설
* 역세권 도보거리
* 사진 및 소유자 인증 여부
* 방과 욕실 개수
* 층과 방향
* 사용승인 경과연도
* 관리비
* 계약조건
* 건물 및 내부 시설

---

## 11. 일반 설정 항목

| 설정명 | 코드 | 설명 |
|---|---|---|
| 저장 폴더 | `folder_path` | 엑셀 결과를 저장할 기준 폴더 |
| 등록일 시작 | `fr_date` | `YYYYMMDD` 시작일 |
| 등록일 종료 | `to_date` | `YYYYMMDD` 종료일 |
| 자동 엑셀 저장 | `auto_save_yn` | 작업 종료 후 DB 결과를 엑셀로 자동 저장 |
| 기준금액 | `baseAmount` | 원, 만원, 억 단위 변환 |
| 상세정보조회 | `detail_column_yn` | 매물별 상세 API 추가 호출 여부 |
| 영어컬럼 | `eng_yn` | 영문 컬럼 형식으로 결과 저장 여부 |
| 링크 | `link_yn` | 매물번호, URL, 주소에 하이퍼링크 적용 |

기준금액 옵션:

```text
10K  = 만원 단위
100M = 억 단위
KRW  = 원 단위
```

---

## 12. 결과 컬럼

### 기본 컬럼

현재 설정 파일에 등록된 주요 기본 컬럼은 다음과 같다.

```text
매물번호
매물명
번지
도로명주소
매매가
등록일자
대지면적
연면적
건축면적
단지명
동이름
보증금/전세
월세
공급면적
전용면적
매물확인일
매물노출시작일
해당층
전체층
시도
시군구
읍면동
우편번호
전체주소
중개사무소이름
중개사이름
URL
상위매물명
상위매물동
부모여부
상위매물번호
매물유형
거래유형
매물태그
위도
경도
방향정보
동일주소매물수
동일주소최소가
동일주소최대가
매물설명
현재업종
추천업종
매물확인코드
사용승인일
검색 주소
층정보
ID
검색조건
가격정보
순위
```

### 상세조회 컬럼

다음 컬럼은 `상세정보조회`를 활성화한 경우에만 수집하도록 설정되어 있다.

* 평수
* 건축물용도
* 매물상세설명
* 중개사무소주소
* 중개사무소번호
* 중개사핸드폰번호

상세 조회는 매물별 추가 API를 호출하므로 일반 목록 모드보다 처리 속도가 느리다.

---

## 13. DB 및 엑셀 저장

### 작업 이력

공통 작업 이력 테이블:

```text
WORKER_JOB_HIST
```

주요 상태:

* `RUNNING`
* `SUCCESS`
* `FAIL`
* `STOP`

작업 종료 시 다음 값을 갱신한다.

* 종료일시
* 작업 상태
* 전체 건수
* 성공 건수
* 실패 건수
* 오류 메시지

### 상세 데이터

상세 테이블:

```text
NAVER_LAND_REAL_ESTATE_AD
```

실제 SQLite 테이블명:

```text
naver_land_real_estate_ad
```

### 엑셀 저장

자동 저장이 활성화되면 현재 `hist_id`에 해당하는 상세 데이터를 조회하여 엑셀로 저장한다.

파일명:

```text
네이버 부동산_{job_id}.xlsx
```

저장 위치:

```text
{folder_path}/output
```

---

## 14. 주요 파일 경로

### Worker

```text
crawl-program/src/workers/main/api_naver_land_real_estate_ad_set_worker.py
```

네이버 부동산 목록 수집, 역지오코딩, 중복 제거, BAN 처리, DB 저장을 담당하는 핵심 코드다.

### 실행 설정

```text
crawl-program/runtime/customers/naver_land_real_estate_ad/config.json
```

주소 API, 날짜, 저장 옵션, 검색 필터, 출력 컬럼을 관리한다.

### 상세 DB 스키마

```text
crawl-program/resources/customers/naver_land_real_estate_ad/db/schema_detail.sql
```

### 공통 작업 이력 스키마

```text
crawl-program/resources/customers/common/db/schema_hist.sql
```

### 전국 지역 데이터

```text
crawl-program/resources/customers/naver_land_real_estate_ad/region/korea_eup_myeon_dong.json
```

### 목록 후킹 JS

```text
crawl-program/resources/customers/naver_land_real_estate_ad/js/list_hook.js
```

### 브라우저 API 호출 JS

```text
crawl-program/resources/customers/naver_land_real_estate_ad/js/browser_fetch_json.js
```

### 정렬 버튼 JS

```text
crawl-program/resources/customers/naver_land_real_estate_ad/js/click_sort_button.js
```

### 매물 버튼 JS

```text
crawl-program/resources/customers/naver_land_real_estate_ad/js/click_article_button.js
```

### 개발 문서

```text
crawl-program/docs/customers/naver_land_real_estate_ad/api_naver_land_real_estate_ad_set_worker.md
```

---

## 15. 작업 중단 및 마감 처리

사용자가 중단하면 다음 순서로 처리한다.

```text
running = False
→ 작업 상태 STOP 지정
→ 브라우저 종료
→ 파일 객체 종료
→ 기존 DB 연결 종료
→ 임시 DB 연결로 작업 이력 최종 갱신
→ 자동 엑셀 저장 실행
→ 엑셀 객체 종료
```

정상 완료 시 `SUCCESS`, 예외 발생 시 `FAIL`, 사용자 중단 시 `STOP`으로 기록한다.

---

## 16. 현재 구현 확인사항

### 16.1 날짜 기준

고객 요구는 `등록일자` 기준이지만 현재 핵심 함수는 `매물확인일`을 우선 사용한다.

```python
현재:
매물확인일 or 등록일자

요구사항 권장:
등록일자
```

### 16.2 컬럼 순서

고객 요청 순서는 `매물명`부터 시작하지만 현재 설정은 `매물번호`가 첫 번째다.

정확한 납품 형식을 맞추려면 `config.json`의 `columns` 순서를 변경해야 한다.

### 16.3 BAN 유지 범위

`global_address_history`는 메모리 변수이므로 BAN 상태는 **현재 프로그램 실행 동안만 유지**된다.

프로그램을 종료하고 다시 실행하면 BAN 이력이 초기화된다.

실행을 넘어 영구적으로 BAN을 유지하려면 별도 DB 테이블이나 파일 저장이 필요하다.

### 16.4 Bulk Insert 주석

코드 주석은 20개 단위라고 되어 있으나 실제 `chunk_size`는 100이다.

```python
chunk_size = 100
```

### 16.5 API Key 보안

`master_api_key`가 설정 JSON에 평문으로 저장되어 있다.

배포본 또는 Git 저장소에 포함될 가능성이 있다면 다음 방식 중 하나로 분리하는 것이 안전하다.

* 배포 환경 전용 JSON
* 환경변수
* 암호화된 로컬 설정
* 서버에서 발급한 별도 런처 키

---

## 17. 프로그램 빌드

프로젝트 루트에서 PowerShell로 실행한다.

```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_naver_land_real_estate_ad_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_land_real_estate_ad_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_land_real_estate_ad\region\korea_eup_myeon_dong.json;resources\customers\naver_land_real_estate_ad\region" `
--add-data ".\resources\customers\naver_land_real_estate_ad\js\list_hook.js;resources\customers\naver_land_real_estate_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_ad\js\browser_fetch_json.js;resources\customers\naver_land_real_estate_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_ad\js\click_sort_button.js;resources\customers\naver_land_real_estate_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_ad\js\click_article_button.js;resources\customers\naver_land_real_estate_ad\js" `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all" `
--add-data ".\resources\customers\naver_land_real_estate_ad\db\schema_detail.sql;resources\customers\naver_land_real_estate_ad\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"
```

---

## 18. 핵심 요약

```text
네이버 부동산 지역별 목록 수집
→ 매물번호 중복 제거
→ 위도·경도 역지오코딩
→ 도로명주소·지번주소 보완
→ 같은 날짜의 동일 주소는 최초 1건만 유지
→ 다른 날짜에 반복된 주소는 기존 데이터까지 삭제 후 BAN
→ 날짜 범위 밖 매물 제거
→ SQLite Bulk Insert
→ 작업 종료 후 엑셀 자동 저장
```

가장 중요한 로직은 `_save_list_items_multi` 함수이며, 주소 중복 제거와 장기간 반복 광고 BAN 처리의 기준이 이 함수에 집중되어 있다.
