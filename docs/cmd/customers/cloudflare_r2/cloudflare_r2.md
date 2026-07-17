# Cloudflare R2 설정 및 연동 문서

> 작성일: 2026-07-17  
> 목적: GB7 Launcher 프로그램 업데이트 ZIP 파일을 Cloudflare R2에 저장하고 안전하게 배포하기 위한 설정 및 테스트 기록

---

## 1. 도입 목적

기존 Spring Boot 웹서버의 저장 용량은 약 1GB이므로, 프로그램별 업데이트 ZIP 파일을 여러 버전 보관하기 어렵다.

프로그램 ZIP 파일은 보통 약 150MB이며, 프로그램별로 최근 버전 2개만 유지하더라도 프로그램 수가 늘어나면 웹서버 저장 용량이 빠르게 부족해진다.

따라서 역할을 다음과 같이 분리한다.

```text
Spring Boot 서버
├─ 공지사항 관리
├─ 프로그램 및 최신 버전 관리
├─ 고객별 프로그램 사용 권한 확인
├─ 업데이트 기간 확인
└─ R2 임시 다운로드 URL 생성

Cloudflare R2
└─ 실제 프로그램 ZIP 파일 저장

GB7 Launcher
├─ Spring Boot 서버에 최신 버전 조회
├─ 임시 다운로드 URL 수신
├─ R2에서 ZIP 다운로드
├─ SHA-256 검증
└─ 압축 해제 및 업데이트
```

---

## 2. Cloudflare R2란?

Cloudflare R2는 ZIP, 이미지, 영상, 백업 파일 같은 대용량 파일을 저장하는 오브젝트 스토리지다.

Amazon S3와 같은 종류의 서비스이며, S3 호환 API를 제공한다.

R2가 AWS에 의존하는 것은 아니며 Cloudflare가 직접 운영한다. 다만 기존 S3 SDK와 도구를 사용할 수 있도록 S3 방식의 API를 지원한다.

### 핵심 특징

- S3 호환 오브젝트 스토리지
- 인터넷 다운로드 egress 비용 없음
- 버킷 단위 파일 관리
- 비공개 버킷 지원
- Presigned URL 지원
- Python `boto3`, Java AWS SDK 사용 가능

---

## 3. 요금제

현재 활성화한 저장소는 `Standard` 스토리지 클래스다.

### 월 무료 제공량

| 항목 | 무료 제공량 |
|---|---:|
| Standard Storage | 10GB / 월 |
| Class A Operations | 1,000,000회 / 월 |
| Class B Operations | 10,000,000회 / 월 |
| 인터넷 egress | 무료 |

### 무료 제공량 초과 요금

| 항목 | 초과 요금 |
|---|---:|
| Storage | $0.015 / GB-month |
| Class A | $4.50 / 100만 회 |
| Class B | $0.36 / 100만 회 |

> 무료 제공량은 `Standard` 스토리지 클래스에 적용된다.  
> 현재 용도에서는 `Infrequent Access`를 사용하지 않는다.

### 예상 저장 용량

```text
프로그램 ZIP 1개         약 150MB
프로그램별 2개 버전      약 300MB
프로그램 10개            약 3GB
프로그램 30개            약 9GB
```

현재 계획에서는 무료 10GB 범위 안에서 사용할 가능성이 높다.

---

## 4. 현재 완료된 Cloudflare 설정

### R2 구독

```text
상태        활성화 완료
기본요금    $0 / month
스토리지    Standard
```

### 버킷

```text
Bucket Name           gb7-launcher-files
Location              Automatic
배치 지역             Asia Pacific
Default Storage Class Standard
Public Access         Disabled
```

버킷 이름은 생성 후 변경할 수 없으므로 그대로 사용한다.

### 공개 접근 설정

현재 버킷은 비공개 상태다.

```text
Public Access    Disabled
r2.dev           사용하지 않음
Custom Domain    연결하지 않음
```

영구 공개 주소를 사용하면 주소를 아는 누구나 다운로드할 수 있으므로 공개 버킷으로 전환하지 않는다.

---

## 5. R2 API 토큰

Spring Boot 서버가 R2에 접근할 수 있도록 Account API Token을 생성했다.

### 토큰 설정

```text
Token Name       gb7-springboot-r2
Permission       Object Read & Write
Bucket Scope     gb7-launcher-files만 허용
TTL              Forever
IP Filtering     사용하지 않음
```

### TTL 의미

TTL은 API 토큰 자체의 유효기간이다.

```text
Forever
→ 직접 폐기하거나 삭제하기 전까지 계속 사용 가능

30 days
→ 생성 후 30일이 지나면 자동 만료
```

Spring Boot 서버가 계속 사용하는 키이므로 현재는 `Forever`로 설정했다.

### 발급받은 값

```text
Access Key ID
Secret Access Key
S3 API Endpoint
```

실제 값은 이 문서와 Git 저장소에 기록하지 않는다.

### 보안 주의사항

다음 값은 외부에 노출하면 안 된다.

```text
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
```

저장하면 안 되는 위치:

```text
Git 저장소
README 또는 Markdown 문서
런처 Python 코드
런처 app.json
브라우저 JavaScript
DB 일반 컬럼
고객 PC
로그 파일
```

허용 위치:

```text
Spring Boot 서버 환경변수
서버의 비밀 설정 파일
배포 환경의 Secret 관리 기능
```

Secret Access Key가 노출되면 기존 토큰을 폐기하고 새 토큰을 발급해야 한다.

---

## 6. 현재 테스트 파일

Cloudflare 대시보드에서 다음 테스트 파일을 수동으로 업로드했다.

```text
gb7-launcher-files
└─ test.txt
```

### 파일 정보

```text
Object Key      test.txt
Content Type    text/plain
Storage Class   Standard
Size            8 bytes
```

파일 내용:

```text
test1234
```

---

## 7. Python 연결 테스트

R2 연결 테스트는 Python과 `boto3`를 사용했다.

### 필요 라이브러리

`requirements.txt`에 다음 항목을 추가한다.

```text
boto3
```

`botocore`는 `boto3` 설치 시 함께 설치되므로 별도로 추가하지 않아도 된다.

### 테스트 코드 파일

권장 파일명:

```text
r2_test.py
```

현재 작성된 테스트 코드에서는 다음 작업을 수행한다.

```text
1. R2 Endpoint 입력
2. Access Key ID 입력
3. Secret Access Key 입력
4. 버킷 파일 목록 조회
5. test.txt 존재 확인
6. 600초 Presigned GET URL 생성
7. URL을 이용해 파일 다운로드
8. 다운로드 파일 크기 확인
```

### 코드 주요 설정

```python
BUCKET_NAME = "gb7-launcher-files"
OBJECT_KEY = "test.txt"
DOWNLOAD_PATH = Path("downloaded_test.txt")
```

R2 클라이언트 생성:

```python
s3 = boto3.client(
    service_name="s3",
    endpoint_url=endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="auto",
)
```

600초 다운로드 URL 생성:

```python
download_url = s3.generate_presigned_url(
    ClientMethod="get_object",
    Params={
        "Bucket": BUCKET_NAME,
        "Key": OBJECT_KEY,
    },
    ExpiresIn=600,
)
```

### 테스트 결과

```text
=== Cloudflare R2 연결 테스트 ===

[1] 버킷 파일 목록 확인
- test.txt (8 bytes)

[2] 600초 Presigned URL 생성
Presigned URL 생성 성공

[3] Presigned URL로 파일 다운로드
다운로드 성공: E:\git\crawl-program\downloaded_test.txt
파일 크기: 8 bytes

Process finished with exit code 0
```

### 확인된 항목

- [x] R2 API 인증키 정상
- [x] 비공개 버킷 접근 정상
- [x] 버킷 객체 목록 조회 정상
- [x] `test.txt` 조회 정상
- [x] 600초 Presigned URL 생성 정상
- [x] Presigned URL 직접 다운로드 정상
- [x] 다운로드된 파일 크기 확인 정상

---

## 8. Presigned URL 동작 원리

R2 버킷은 비공개로 유지하고, 다운로드가 필요한 경우에만 제한된 시간 동안 사용할 수 있는 Presigned URL을 생성한다.

### 최종 다운로드 흐름

```text
GB7 Launcher
    │
    │ program_id + 고객별 프로그램 key
    ▼
Spring Boot 서버
    │
    ├─ 고객 key 확인
    ├─ 프로그램 권한 확인
    ├─ 고객 사용 상태 확인
    ├─ 업데이트 만료일 확인
    └─ 600초 Presigned GET URL 생성
    │
    ▼
GB7 Launcher
    │
    │ 임시 URL로 GET 요청
    ▼
Cloudflare R2
    │
    ├─ 서명 검증
    ├─ 파일 경로 확인
    ├─ 요청 방식 확인
    └─ 만료 시간 확인
    │
    ▼
ZIP 파일 다운로드
```

### URL에 포함되는 주요 값

```text
파일 경로
Access Key 식별값
생성 시간
만료 시간
요청 방식
서명값
```

형태 예시:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com/
<BUCKET>/<OBJECT_KEY>
?X-Amz-Algorithm=AWS4-HMAC-SHA256
&X-Amz-Credential=...
&X-Amz-Date=...
&X-Amz-Expires=600
&X-Amz-SignedHeaders=host
&X-Amz-Signature=...
```

### 중요한 점

- URL 전체가 임시 다운로드 허가증 역할을 한다.
- `X-Amz-Signature`는 위조 여부를 확인하는 서명값이다.
- `X-Amz-Expires=600`은 URL의 유효시간이다.
- Secret Access Key 자체는 URL에 포함되지 않는다.
- R2는 값을 복호화하는 것이 아니라 같은 방식으로 서명을 다시 계산해 비교한다.
- 파일 경로나 만료시간을 임의로 수정하면 서명이 달라져 다운로드가 거부된다.
- 유출된 URL은 만료 전까지 다른 사람도 사용할 수 있다.
- Presigned URL은 기본적으로 완전한 1회용 URL은 아니다.
- 만료 시간을 짧게 유지하고 URL 전체를 로그에 남기지 않는다.

---

## 9. Cloudflare 사용량 모니터링

버킷의 사용량은 다음 화면에서 확인한다.

```text
Cloudflare
→ R2 Object Storage
→ gb7-launcher-files
→ Metrics
```

### 주요 확인 항목

```text
Average Storage
Data Retrieved
Class A Operations
Class B Operations
Request Distribution
```

### 현재 확인된 값

테스트 과정에서 대시보드 조회, 파일 목록 확인, 업로드, 다운로드 요청 등이 발생했다.

```text
Class A Operations    발생 확인
Class B Operations    발생 확인
Public Access         Disabled
Object                test.txt 8 B
```

### Class A 작업 예시

비교적 변경 비용이 높은 저장소 작업이다.

```text
PutObject
ListObjects
CreateMultipartUpload
UploadPart
CompleteMultipartUpload
```

### Class B 작업 예시

주로 읽기 작업이다.

```text
GetObject
HeadObject
```

### 참고사항

- 파일 한 개만 올려도 대시보드 새로고침과 목록 조회 때문에 요청 횟수가 여러 번 증가할 수 있다.
- Metrics의 요약값과 시간대별 그래프는 반영 시점이 다를 수 있다.
- 파일 업로드 직후 `Average Storage`가 0B로 표시되어도 객체 목록에 파일이 보이면 정상이다.
- 정확한 과금 여부는 Cloudflare의 Billing 또는 Billable Usage 화면에서도 확인한다.

---

## 10. 권장 폴더 구조

프로젝트 내 별도 문서 및 테스트 폴더를 다음처럼 관리한다.

```text
cloudflare_r2/
├─ cloudflare_r2.md
├─ r2_test.py
├─ test.txt
├─ requirements.txt
└─ screenshots/
   ├─ 01_r2_subscription.png
   ├─ 02_bucket_create.png
   ├─ 03_bucket_private.png
   ├─ 04_api_token_setting.png
   ├─ 05_object_upload.png
   ├─ 06_python_test_result.png
   └─ 07_metrics.png
```

프로젝트 전체에 이미 `requirements.txt`가 있다면 `cloudflare_r2` 폴더에 별도 파일을 만들 필요 없이 기존 파일에 `boto3`만 추가한다.

`downloaded_test.txt`는 테스트 실행 결과물이므로 Git에 저장할 필요가 없다.

---

## 11. 실제 ZIP 파일 경로 규칙

R2의 객체 경로는 프로그램과 버전을 쉽게 구분할 수 있도록 고정한다.

### 권장 규칙

```text
{program_id}/{version_dir}/{file_name}
```

### 예시

```text
NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip
NAVER_PLACE_LOC_ALL/v1_0_0/v1_0_0.zip
YEOGI_ADMIN/v1_0_0/v1_0_0.zip
```

R2에서 `/`는 실제 디렉터리라기보다 객체 이름의 일부지만, 화면에서는 폴더처럼 관리할 수 있다.

---

## 12. DB 저장 원칙

Presigned URL은 일정 시간이 지나면 만료되므로 DB에 저장하지 않는다.

DB에는 R2의 객체 위치와 검증 정보를 저장한다.

### 권장 저장 항목

```text
program_id
version
object_key
file_name
file_size
sha256
active_yn
created_at
updated_at
```

### 저장 예시

```text
program_id    NAVER_BAND_MEMBER
version       1.0.2
object_key    NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip
file_name     v1_0_2.zip
file_size     157286400
sha256        <SHA-256 값>
active_yn     Y
```

다운로드 요청이 들어오면 Spring Boot가 `object_key`를 이용해 새로운 Presigned URL을 생성한다.

---

## 13. 앞으로 진행할 작업

### 1단계 — Cloudflare R2 기본 설정

- [x] Cloudflare R2 구독 활성화
- [x] `gb7-launcher-files` 버킷 생성
- [x] Standard Storage 선택
- [x] Public Access 비활성화
- [x] 테스트 파일 수동 업로드
- [x] Account API Token 생성
- [x] Python R2 연결 테스트
- [x] Presigned GET URL 다운로드 테스트
- [x] Metrics 화면 확인

### 2단계 — Spring Boot R2 연결

- [ ] AWS SDK 의존성 추가
- [ ] R2 환경변수 등록
- [ ] R2 설정 Properties 작성
- [ ] `S3Client` 설정
- [ ] `S3Presigner` 설정
- [ ] `test.txt` 파일 조회
- [ ] 600초 Presigned GET URL 생성
- [ ] Spring 서버에서 실제 다운로드 확인

### 3단계 — 관리자 ZIP 업로드

권장 방식:

```text
관리자 브라우저
→ Spring Boot에 업로드 URL 요청
→ Spring Boot가 Presigned PUT URL 생성
→ 관리자 브라우저가 R2에 ZIP 직접 업로드
→ 업로드 완료 후 Spring Boot에 완료 요청
→ Spring Boot가 R2 파일 존재와 크기 확인
→ DB에 object_key, size, sha256 저장
```

작업 목록:

- [ ] 관리자 업로드 URL 발급 API
- [ ] 업로드용 Presigned PUT URL 생성
- [ ] R2 CORS 설정
- [ ] 브라우저 직접 업로드
- [ ] 업로드 완료 API
- [ ] 업로드 파일 존재 확인
- [ ] 파일 크기 검증
- [ ] SHA-256 저장
- [ ] DB 버전 정보 저장

### 4단계 — 런처 다운로드

- [ ] 런처가 `program_id` 전송
- [ ] 런처가 고객별 프로그램 key 전송
- [ ] Spring Boot에서 key 검증
- [ ] 고객 상태 확인
- [ ] 프로그램 사용 권한 확인
- [ ] 업데이트 기간 확인
- [ ] Presigned GET URL 반환
- [ ] 런처가 R2에서 ZIP 직접 다운로드
- [ ] SHA-256 검증
- [ ] 압축 해제
- [ ] 업데이트 적용
- [ ] 최신 로컬 버전 2개 유지

### 5단계 — 운영 관리

- [ ] 업로드 성공·실패 로그
- [ ] 다운로드 URL 발급 로그
- [ ] 고객별 다운로드 요청 로그
- [ ] Presigned URL 전체 로그 출력 금지
- [ ] 이전 버전 R2 삭제 정책
- [ ] 프로그램별 최근 버전 유지 정책
- [ ] 무료 사용량 정기 확인
- [ ] API Token 주기적 교체 여부 검토
- [ ] Secret 노출 시 토큰 즉시 폐기

---

## 14. Spring Boot 환경변수 예정 목록

아직 Spring Boot 서버에 적용하지 않은 예정 설정이다.

```text
R2_ENDPOINT
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_PRESIGN_SECONDS
```

설정 예시:

```properties
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<ACCESS_KEY_ID>
R2_SECRET_ACCESS_KEY=<SECRET_ACCESS_KEY>
R2_BUCKET_NAME=gb7-launcher-files
R2_PRESIGN_SECONDS=600
```

실제 비밀값은 Git에 커밋하지 않는다.

---

## 15. 최종 목표 구조

```text
관리자
  │
  │ ZIP 업로드 요청
  ▼
Spring Boot
  │
  ├─ 관리자 인증
  ├─ Presigned PUT URL 생성
  └─ DB 메타데이터 저장
  │
  ▼
Cloudflare R2
  │
  └─ 실제 ZIP 파일 저장


GB7 Launcher
  │
  │ program_id + launcher_key
  ▼
Spring Boot
  │
  ├─ 고객 인증
  ├─ 프로그램 권한 확인
  ├─ 업데이트 기간 확인
  └─ Presigned GET URL 생성
  │
  ▼
GB7 Launcher
  │
  │ 임시 URL로 직접 요청
  ▼
Cloudflare R2
  │
  └─ ZIP 파일 다운로드
```

---

## 16. 변경 이력

### 2026-07-17

- Cloudflare R2 구독 활성화
- `gb7-launcher-files` 비공개 버킷 생성
- Standard 스토리지 클래스 적용
- `test.txt` 테스트 파일 업로드
- Spring Boot용 Account API Token 생성
- Python `boto3` 연결 테스트 완료
- R2 객체 목록 조회 성공
- 600초 Presigned GET URL 생성 성공
- Presigned URL 파일 다운로드 성공
- R2 Metrics 사용량 확인
- Spring Boot 연동 전 기초 설정 문서화
