# iHerb 상품 정보 수집

## 1. 프로그램 정보

| 구분 | 내용 |
|---|---|
| 프로그램명 | iHerb 상품 정보 수집 |
| 화면 표시명 | 아이허브 |
| 프로그램 키 | `IHERB` |
| DB 구분명 | `IHERB` |
| Worker 이름 | `iherb` |
| 상세 테이블명 | `iherb` |
| 공통 작업 이력 테이블 | `WORKER_JOB_HIST` |
| Worker 클래스 | `ApiIherbSetLoadWorker` |
| Worker 경로 | `src.workers.main.api_iherb_set_worker` |
| 실행 방식 | `numbers.txt`의 품번을 순서대로 조회 |
| 결과 저장 | SQLite DB 및 선택적 엑셀 자동 저장 |

---

## 2. 작업 목적

사용자가 선택한 `numbers.txt` 파일에서 iHerb 품번을 읽고, 설정한 상품 URL 뒤에 품번을 붙여 상품 페이지를 조회한다.

각 상품 페이지에서 다음 정보를 수집한다.

* 품번
* 할인기간
* 할인율
* 가격
* 재고

예시:

```text
상품 URL:
https://kr.iherb.com/pr/doctor-s-best-alpha-lipoic-acid-150-150-mg-120-veggie-caps

품번:
12345

최종 조회 URL:
https://kr.iherb.com/pr/doctor-s-best-alpha-lipoic-acid-150-150-mg-120-veggie-caps/12345
```

수집 결과는 먼저 작업 DB의 `iherb` 상세 테이블에 건별 저장한다.

설정에서 자동 엑셀 저장을 활성화하면 작업 종료 시 DB에 저장된 결과를 엑셀 파일로 내보낸다.

---

## 3. 주요 기능

* `numbers.txt` 파일에서 품번 목록 읽기
* 품번 파일 경로를 설정 화면에서 변경
* 시작 번호와 종료 번호를 이용한 작업 범위 지정
* 상품 기본 URL을 설정 화면에서 변경
* iHerb 국가, 언어, 통화 및 단위 설정
* Selenium을 이용한 상품 페이지 조회
* 할인기간 및 할인율 수집
* 가격 및 재고 수집
* 국가 판매 제외 상품 가격 예외 처리
* 성공 및 실패 결과를 DB에 모두 기록
* 작업 이력 상태 및 성공·실패 건수 저장
* 사용자 중지 처리
* 작업 종료 시 선택적 엑셀 자동 저장

---

## 4. 설정 항목

### 상품 URL

```json
{
  "name": "상품 URL",
  "code": "product_url",
  "value": "https://kr.iherb.com/pr/doctor-s-best-alpha-lipoic-acid-150-150-mg-120-veggie-caps",
  "type": "input",
  "placeholder": "품번을 제외한 iHerb 상품 URL을 입력하세요."
}
```

품번을 제외한 상품 기본 URL을 입력한다.

Worker에서는 설정값 마지막에 있는 `/`를 제거한다.

```python
self.product_url = str(
    self.get_setting_value(self.setting, "product_url") or ""
).strip().rstrip("/")
```

따라서 다음 두 값은 동일하게 처리된다.

```text
https://kr.iherb.com/pr/example-product
https://kr.iherb.com/pr/example-product/
```

상품 URL이 비어 있으면 프로그램을 시작하지 않고 오류를 출력한다.

---

### 품번 파일

```json
{
  "name": "품번 파일",
  "code": "numbers_file_path",
  "value": "file\\numbers.txt",
  "type": "file",
  "placeholder": "품번이 한 줄에 하나씩 입력된 numbers.txt 파일을 선택하세요.",
  "button_text": "파일 선택",
  "dialog_title": "품번 파일 선택",
  "path_type": "main"
}
```

기본 경로:

```text
file\numbers.txt
```

상대 경로이면 프로그램 실행 경로를 기준으로 절대 경로로 변환한다.

배포 후 기본 위치:

```text
CrawlProgram.exe
file\numbers.txt
```

사용자가 설정 화면에서 다른 파일을 선택하면 선택한 경로를 사용한다.

`numbers.txt` 작성 예시:

```text
2
3
4
13
18
```

처리 기준:

* 품번은 한 줄에 하나씩 작성
* 빈 줄은 제외
* UTF-8 및 UTF-8 BOM 파일 지원
* 숫자가 아닌 값이 있으면 해당 줄 번호와 함께 오류 처리
* 같은 품번이 여러 번 있으면 입력된 횟수만큼 처리

---

### 시작 번호

```json
{
  "name": "시작 번호",
  "code": "st_page",
  "value": 1,
  "type": "input"
}
```

`numbers.txt` 목록에서 작업을 시작할 순번이다.

첫 번째 품번은 `1`이다.

---

### 종료 번호

```json
{
  "name": "종료 번호",
  "code": "ed_page",
  "value": 1536,
  "type": "input"
}
```

`numbers.txt` 목록에서 작업을 종료할 순번이다.

시작 번호와 종료 번호는 모두 포함된다.

예시:

```text
시작 번호: 10
종료 번호: 20

처리 범위:
numbers.txt의 10번째 품번부터 20번째 품번까지
```

종료 번호가 시작 번호보다 작으면 초기화에 실패한다.

---

### 저장 폴더

```json
{
  "name": "저장 폴더",
  "code": "folder_path",
  "value": "",
  "type": "folder",
  "placeholder": "엑셀을 저장할 폴더를 선택하세요(기본 문서).",
  "button_text": "폴더 선택",
  "dialog_title": "저장 폴더 선택",
  "path_type": "main"
}
```

엑셀 자동 저장 시 선택한 폴더 아래의 `output` 폴더에 결과가 생성된다.

---

### 자동 엑셀 저장

```json
{
  "name": "자동 엑셀 저장",
  "code": "auto_save_yn",
  "value": true,
  "type": "check"
}
```

활성화하면 작업 종료 시 DB에 저장된 상세 데이터를 엑셀 파일로 내보낸다.

파일명 형식:

```text
iHerb_{JOB_ID}.xlsx
```

---

## 5. 전체 처리 흐름

```text
1. 프로그램 설정값 조회
2. 상품 URL 확인 및 마지막 슬래시 제거
3. 품번 파일 경로 확인
4. 시작 번호와 종료 번호 검증
5. Selenium, FileUtils, ExcelUtils 생성
6. WorkerDbRepository 생성
7. 공통 작업 이력 및 iHerb 상세 테이블 스키마 초기화
8. Selenium 브라우저 실행
9. iHerb 메인 페이지 접속
10. 국가, 언어, 통화 및 단위 설정
11. numbers.txt에서 전체 품번 읽기
12. 시작 번호와 종료 번호 범위만 추출
13. 상품 URL과 품번으로 최종 조회 URL 생성
14. 상품 페이지 조회
15. 할인기간, 할인율, 가격 및 재고 추출
16. 상세 결과를 DB에 저장
17. 실패한 품번도 FAIL 상태로 DB에 저장
18. 진행률 갱신
19. 작업 이력 SUCCESS, STOP 또는 FAIL 처리
20. 자동 저장 설정 시 DB 데이터를 엑셀로 저장
21. Selenium, DB, 파일 및 엑셀 객체 정리
```

---

## 6. 국가·통화 설정

프로그램 시작 후 iHerb의 국가 선택 팝업에서 다음 값을 순서대로 설정한다.

```text
국가: 일본
언어: 한국어
통화: USD ($)
단위: 미터법(kg, cm)
```

현재 Worker의 설정값:

```python
texts = ["일본", "한국어", "USD ($)", "미터법(kg, cm)"]
```

iHerb 화면 구조 또는 표시 문구가 변경되면 이 값과 CSS 선택자를 함께 확인해야 한다.

사용 선택자:

```text
설정 버튼:
.selected-country-wrapper

설정 팝업:
.selection-list-wrapper

검색 입력:
input.search-input.gh-dropdown-search.gh-fake-input

저장 버튼:
button.save-selection.gh-btn.gh-btn-primary
```

---

## 7. 상품 URL 생성 방식

상품 상세 URL은 다음 방식으로 생성한다.

```python
product_detail_url = f"{self.product_url}/{num}"
self.driver.get(product_detail_url)
```

`product_url`은 초기화 단계에서 `rstrip("/")` 처리하므로 중복 슬래시가 발생하지 않는다.

---

## 8. 수집 항목

### 품번

```text
DB 컬럼: product_no
엑셀 헤더: 품번
```

`numbers.txt`에서 읽은 값을 그대로 저장한다.

---

### 할인기간

```text
DB 컬럼: discount_period
엑셀 헤더: 할인기간
```

확인 대상:

```text
div.discount-title
span.expiration-date
```

처리 기준:

* `슈퍼 세일`이 포함되면 `SS` 저장
* 종료 날짜가 있으면 `YYYY-MM-DD` 형식으로 저장
* 할인 정보가 없으면 `해당없음` 저장

지원하는 날짜 예시:

```text
2026년 8월 31일 오후 11시
```

---

### 할인율

```text
DB 컬럼: discount_percent
엑셀 헤더: 할인 %
```

할인 관련 전체 문자열에서 다음 형식을 찾는다.

```text
10%
20%
35%
```

값이 없으면 `해당없음`을 저장한다.

---

### 가격

```text
DB 컬럼: price
엑셀 헤더: 가격
```

조회 순서:

```text
1차: span.list-price
2차: div.price-inner-text > p
```

다음 요소에 `판매 제외`가 포함되어 있으면 가격을 `해당없음`으로 처리한다.

```text
span.title.title-prohibited
```

---

### 재고

```text
DB 컬럼: stock
엑셀 헤더: 재고
```

확인 대상:

```text
strong.text-primary
```

값이 없으면 `해당없음`을 저장한다.

---

## 9. 컬럼 설정

```json
"columns": [
  {
    "code": "product_no",
    "value": "품번",
    "checked": true
  },
  {
    "code": "discount_period",
    "value": "할인기간",
    "checked": true
  },
  {
    "code": "discount_percent",
    "value": "할인 %",
    "checked": true
  },
  {
    "code": "price",
    "value": "가격",
    "checked": true
  },
  {
    "code": "stock",
    "value": "재고",
    "checked": true
  }
]
```

저장 기준:

```text
DB 컬럼명: columns[].code
엑셀 헤더명: columns[].value
```

---

## 10. DB 저장 구조

DB 처리는 `WorkerDbRepository`를 사용한다.

### 작업 시작

```text
WorkerDbRepository 생성
→ schema_hist.sql 실행
→ schema_detail.sql 실행
→ 작업 이력 RUNNING 생성
```

### 상세 저장

성공한 상품은 다음 상태로 저장한다.

```text
row_status = SUCCESS
```

상품 처리 중 예외가 발생해도 해당 품번을 실패 행으로 저장한다.

실패 행에 남는 값:

* 품번
* 할인기간 `해당없음`
* 할인율 `해당없음`
* 가격 `해당없음`
* 재고 `해당없음`
* 오류 메시지
* 행 시작 시간
* 행 종료 시간

실패 상태:

```text
row_status = FAIL
```

---

## 11. 작업 종료 상태

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

### 실행 오류

```text
FAIL
```

발생한 예외 메시지를 대표 오류 메시지로 저장한다.

### 비정상 종료

종료 처리 시 상태가 계속 `RUNNING`이면 다음과 같이 처리한다.

```text
FAIL
```

오류 메시지:

```text
비정상 종료
```

---

## 12. 엑셀 저장

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
iHerb_{JOB_ID}.xlsx
```

저장 대상 데이터가 없으면 엑셀 파일을 만들지 않는다.

---

## 13. 진행률 계산

```text
진행률 = 현재 처리한 품번 수 ÷ 전체 작업 대상 품번 수
```

프로그램의 진행률 최대값은 `1,000,000`이다.

```python
pro_value = (self.current_cnt / self.total_cnt) * 1000000
```

---

## 14. 중지 및 정리 처리

사용자가 작업을 중지하면 다음 순서로 처리한다.

```text
running = false
→ 작업 상태 STOP 저장
→ DB 작업 이력 마감
→ 자동 엑셀 저장 처리
→ Selenium 브라우저 종료
→ DB 연결 종료
→ FileUtils 종료
→ ExcelUtils 종료
```

`cleanup()`은 중복 실행되지 않도록 `_cleaned_up`으로 보호한다.

---

## 15. 검색 컬럼

결과 조회 화면에서 다음 항목을 검색 조건으로 사용할 수 있다.

* 품번
* 할인기간
* 할인율
* 가격
* 재고

---

## 16. 주요 파일 경로

### Worker

```text
src\workers\main\api_iherb_set_worker.py
```

### 고객 설정

```text
resources\customers\iherb\config.json
```

### iHerb 상세 테이블 스키마

```text
resources\customers\iherb\db\schema_detail.sql
```

### 공통 작업 이력 스키마

```text
resources\customers\common\db\schema_hist.sql
```

### 기본 품번 파일

개발 프로젝트:

```text
file\numbers.txt
```

배포 결과:

```text
dist\CrawlProgram\file\numbers.txt
```

### 프로그램 아이콘

```text
resources\icons\crawling.ico
```

### 버전 정보

Worker별 버전 파일 구조를 사용하는 경우:

```text
docs\src\workers\main\api_iherb_set_worker\version_info.txt
```

실제 프로젝트의 버전 파일 위치가 다르면 아래 빌드 명령의 `--version-file`만 실제 경로에 맞게 변경한다.

---

## 17. 프로그램 빌드

### 빌드 전 준비

프로젝트 루트에서 PowerShell을 실행한다.

가상환경을 사용하는 경우 먼저 활성화한다.

```powershell
.\.venv\Scripts\Activate.ps1
```

필수 패키지를 확인한다.

```powershell
python -m pip install --upgrade pyinstaller
python -m pip install selenium pyautogui pandas openpyxl
```

빌드 전 다음 파일이 실제로 존재해야 한다.

```text
main.py
src\workers\main\api_iherb_set_worker.py
resources\customers\iherb\config.json
resources\customers\iherb\db\schema_detail.sql
resources\customers\common\db\schema_hist.sql
resources\icons\crawling.ico
file\numbers.txt
docs\src\workers\main\api_iherb_set_worker\version_info.txt
```

### 운영용 빌드

GUI 프로그램이므로 운영 배포본은 `--windowed`만 사용한다.

```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_iherb_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_iherb_set_worker" `
--hidden-import "selenium" `
--hidden-import "selenium.webdriver" `
--hidden-import "pyautogui" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--collect-submodules "selenium.webdriver" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\iherb\db\schema_detail.sql;resources\customers\iherb\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"
```

빌드가 끝나면 기본 품번 파일을 실행 파일 옆 `file` 폴더로 복사한다.

```powershell
$IherbDistDir = ".\dist\CrawlProgram"
$IherbFileDir = Join-Path $IherbDistDir "file"

New-Item -ItemType Directory -Force $IherbFileDir | Out-Null
Copy-Item ".\file\numbers.txt" (Join-Path $IherbFileDir "numbers.txt") -Force
```

최종 구조:

```text
dist\CrawlProgram\
├─ CrawlProgram.exe
├─ file\
│  └─ numbers.txt
└─ _internal\
   └─ resources\
      └─ customers\
         ├─ common\db\schema_hist.sql
         └─ iherb\
            ├─ config.json
            └─ db\schema_detail.sql
```

PyInstaller 버전에 따라 내부 리소스 폴더 구조가 다를 수 있지만, 사용자가 직접 선택·수정하는 `numbers.txt`는 반드시 실행 파일 옆의 `file` 폴더에 둔다.

Worker의 기본 경로 계산이 실행 파일 위치를 기준으로 하기 때문이다.

```python
if getattr(sys, "frozen", False):
    base_dir = os.path.dirname(os.path.abspath(sys.executable))
```

### 개발 확인용 빌드

빌드 직후 오류 로그를 콘솔에서 확인하려면 운영용 명령의 다음 옵션만 변경한다.

기존:

```powershell
--windowed `
```

변경:

```powershell
--console `
```

`--console`과 `--windowed`는 동시에 사용하지 않는다.

---

## 18. 빌드 후 확인사항

### 1. 실행 파일 확인

```text
dist\CrawlProgram\CrawlProgram.exe
```

### 2. 품번 파일 확인

```text
dist\CrawlProgram\file\numbers.txt
```

### 3. 프로그램 설정 확인

* 아이허브 메뉴가 표시되는지 확인
* 상품 URL이 설정 화면에 표시되는지 확인
* 품번 파일 기본 경로가 `file\numbers.txt`인지 확인
* 시작 번호와 종료 번호가 정상 표시되는지 확인
* 저장 폴더 선택이 동작하는지 확인
* 자동 엑셀 저장 체크가 동작하는지 확인

### 4. 테스트 범위 실행

처음에는 다음처럼 작은 범위로 실행한다.

```text
시작 번호: 1
종료 번호: 3
```

확인 항목:

* Selenium 브라우저 실행
* iHerb 국가·통화 설정
* 상품 상세 URL 이동
* 품번, 할인기간, 할인율, 가격 및 재고 수집
* `iherb` 상세 테이블 저장
* `worker_job_hist` 작업 이력 저장
* 자동 엑셀 저장
* 정상 종료 시 브라우저와 DB 연결 정리

### 5. 오류 발생 시 확인 순서

```text
1. file\numbers.txt 존재 여부
2. 상품 URL 설정값
3. 시작 번호와 종료 번호
4. Chrome 설치 상태
5. Selenium이 사용하는 ChromeDriver 실행 여부
6. iHerb 국가 선택 팝업의 CSS 선택자 변경 여부
7. 상품 페이지의 가격 및 재고 CSS 선택자 변경 여부
8. config.json과 schema_detail.sql 포함 여부
9. DB 파일 생성 및 쓰기 권한
10. 개발 확인용 --console 빌드 로그
```

---

## 19. 핵심 정리

이 프로그램은 `numbers.txt`의 품번을 순서대로 읽고, 설정한 iHerb 상품 URL 뒤에 품번을 붙여 상품 정보를 수집한다.

핵심 흐름:

```text
설정값 확인
→ numbers.txt 품번 목록 읽기
→ 시작·종료 범위 추출
→ 상품 URL + 품번 생성
→ Selenium 상품 페이지 조회
→ 할인기간·할인율·가격·재고 추출
→ DB 건별 저장
→ 작업 이력 마감
→ 선택적 엑셀 자동 저장
```

핵심 파일:

```text
Worker:
src\workers\main\api_iherb_set_worker.py

설정:
resources\customers\iherb\config.json

상세 스키마:
resources\customers\iherb\db\schema_detail.sql

품번 파일:
실행 파일 경로\file\numbers.txt
```

빌드 핵심:

```text
Worker는 hidden-import로 포함
config.json과 DB 스키마는 add-data로 포함
numbers.txt는 빌드 후 실행 파일 옆 file 폴더로 복사
운영본은 --windowed 사용
오류 확인용 빌드는 --console 사용
```
