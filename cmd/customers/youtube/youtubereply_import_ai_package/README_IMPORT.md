# youtubereply AI 결과 CSV import

## 1. 이 파일의 역할

`youtubereply_import_ai_result.py`는 AI에게 받은 결과 CSV를 PostgreSQL에 넣는 프로그램입니다.

기존 수집 프로그램 역할:

```text
youtubereply_collect_insert_export.py
→ 유튜브 댓글 수집
→ DB 원본 저장
→ AI에게 줄 CSV 생성
```

이번 import 프로그램 역할:

```text
youtubereply_import_ai_result.py
→ AI 결과 CSV 읽기
→ comment_analysis 저장
→ comment_suspicion_analysis 저장
→ video_content_analysis 저장
→ AI 키워드 저장
→ 워드클라우드 집계
→ 네트워크 그래프 집계
→ 시간별 댓글 집계
```

## 2. AI에게 받는 파일명

수집 프로그램 실행 후 아래 폴더가 생깁니다.

```text
output/영상ID/
```

AI에게 받은 결과 파일은 아래 이름으로 저장하세요.

```text
07_ai_comment_analysis_result.csv
08_ai_suspicion_analysis_result.csv
09_ai_video_summary_result.csv
```

### 2-1. 댓글 감정/키워드 분석 결과

입력으로 AI에게 준 파일:

```text
02_ai_comment_analysis_input.csv
prompt_01_comment_analysis.txt
```

AI에게 받아야 하는 파일:

```text
07_ai_comment_analysis_result.csv
```

DB 반영 대상:

```text
comment_analysis
comment_keyword_raw
comment_keyword_summary
video_keyword
keyword_edge
youtube_comment.analysis_status
youtube_comment.keyword_status
video_comment_timeseries
```

### 2-2. 의심 댓글 분석 결과

입력으로 AI에게 준 파일:

```text
03_ai_suspicion_analysis_input.csv
prompt_02_suspicion_analysis.txt
```

AI에게 받아야 하는 파일:

```text
08_ai_suspicion_analysis_result.csv
```

DB 반영 대상:

```text
comment_suspicion_analysis
youtube_comment.suspicion_status
video_comment_timeseries
```

### 2-3. 영상 요약 결과

입력으로 AI에게 준 파일:

```text
04_ai_video_summary_input.csv
prompt_03_video_summary.txt
```

AI에게 받아야 하는 파일:

```text
09_ai_video_summary_result.csv
```

DB 반영 대상:

```text
video_content_analysis
```

## 3. 설치

기존 수집 프로그램과 같은 패키지를 씁니다.

```bat
pip install -r requirements.txt
```

필요 패키지:

```text
pandas
psycopg2-binary
python-dotenv
```

## 4. 환경변수 설정

`.env.import.example`을 복사해서 `.env`에 합치거나, 기존 `.env`에 아래 내용을 추가하세요.

```env
VIDEO_ID=NJFf64DGjds
OUTPUT_DIR=./output

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=youtubereply
DB_USER=postgres
DB_PASSWORD=PostgreSQL 비밀번호

IMPORT_PROVIDER=AI_WEB
IMPORT_MODEL_NAME=WEB_AI
REPLACE_EXISTING=Y
```

직접 파일 경로를 지정하고 싶으면:

```env
AI_COMMENT_RESULT_CSV=E:/git/youtubereply/output/NJFf64DGjds/07_ai_comment_analysis_result.csv
AI_SUSPICION_RESULT_CSV=E:/git/youtubereply/output/NJFf64DGjds/08_ai_suspicion_analysis_result.csv
AI_VIDEO_SUMMARY_RESULT_CSV=E:/git/youtubereply/output/NJFf64DGjds/09_ai_video_summary_result.csv
```

## 5. 실행

```bat
python youtubereply_import_ai_result.py
```

## 6. 처리 흐름

### 6-1. `07_ai_comment_analysis_result.csv`

1. `comment_id` 기준으로 DB의 `youtube_comment`와 연결합니다.
2. 기존 분석 결과를 지웁니다. `REPLACE_EXISTING=Y` 기준.
3. `comment_analysis`에 감정/세부감정/재미/유형/요약을 저장합니다.
4. `ai_keywords`를 분리해서 `comment_keyword_raw`에 `source_type='AI'`로 저장합니다.
5. `comment_keyword_summary`를 갱신합니다.
6. `video_keyword`를 다시 집계합니다.
7. `keyword_edge`를 다시 집계합니다.
8. `youtube_comment.analysis_status`, `keyword_status`를 `DONE`으로 바꿉니다.

### 6-2. `08_ai_suspicion_analysis_result.csv`

1. 자동댓글/AI댓글/댓글부대/정치댓글 의심 결과를 읽습니다.
2. `comment_suspicion_analysis`에 저장합니다.
3. `youtube_comment.suspicion_status`를 `DONE`으로 바꿉니다.
4. 시간별 집계에 의심 댓글 수를 반영합니다.

### 6-3. `09_ai_video_summary_result.csv`

1. 영상 요약 결과를 읽습니다.
2. `video_content_analysis`에 저장합니다.

## 7. 확인 SQL

### 댓글 AI 분석 결과 확인

```sql
SELECT
    c.comment_id,
    c.comment_text,
    a.sentiment_label,
    a.positive_score,
    a.negative_score,
    a.humor_score,
    a.ai_keywords
FROM youtube_comment c
JOIN comment_analysis a
    ON a.comment_id = c.comment_id
ORDER BY a.analysis_id DESC
LIMIT 20;
```

### AI 키워드 확인

```sql
SELECT
    keyword,
    ai_count,
    total_count
FROM video_keyword
WHERE ai_yn = 'Y'
ORDER BY ai_count DESC
LIMIT 50;
```

### 네트워크 연결 확인

```sql
SELECT
    source_keyword,
    target_keyword,
    ai_edge_count,
    total_edge_count
FROM keyword_edge
WHERE ai_yn = 'Y'
ORDER BY ai_edge_count DESC
LIMIT 50;
```

### 시간별 댓글 그래프 데이터 확인

```sql
SELECT
    time_unit,
    time_bucket,
    total_count,
    positive_count,
    negative_count,
    neutral_count
FROM video_comment_timeseries
ORDER BY time_unit, time_bucket
LIMIT 100;
```

## 8. 주의

- AI 결과 CSV에서 `comment_id`가 바뀌면 DB 연결이 안 됩니다.
- CSV 컬럼명이 바뀌면 오류가 납니다.
- 처음에는 `REPLACE_EXISTING=Y` 추천입니다.
- 여러 AI 결과를 비교하고 싶을 때만 `REPLACE_EXISTING=N`을 고려하세요.
