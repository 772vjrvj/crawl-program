# youtubereply 댓글 수집 + DB 저장 + AI CSV 생성

## 1. 파일 구성

- `youtubereply_collect_insert_export.py`
  - YouTube 댓글 수집
  - PostgreSQL `youtube_video`, `youtube_comment`, `comment_metric_snapshot` INSERT
  - AI에게 줄 CSV 파일 생성
  - AI 프롬프트 txt 생성

- `.env.example`
  - 환경변수 샘플

- `requirements.txt`
  - Python 설치 패키지 목록

## 2. 설치

```bat
pip install -r requirements.txt
```

## 3. 환경변수 설정

`.env.example`을 복사해서 `.env`로 변경합니다.

```bat
copy .env.example .env
```

`.env`에서 아래 값 수정:

```env
YOUTUBE_API_KEY=본인 API KEY
VIDEO_URL=분석할 유튜브 URL
DB_PASSWORD=PostgreSQL 비밀번호
MAX_TOP_COMMENTS=100
```

전체 수집하려면:

```env
MAX_TOP_COMMENTS=
```

## 4. 실행

```bat
python youtubereply_collect_insert_export.py
```

## 5. 생성되는 CSV

영상 ID별 폴더에 저장됩니다.

예:

```text
output/NJFf64DGjds/
```

파일:

```text
01_comments_full_internal.csv
- 내부 검수용 전체 댓글

02_ai_comment_analysis_input.csv
- 감정/재미/유형/키워드 분석용
- 이 파일을 AI에게 주면 됨

03_ai_suspicion_analysis_input.csv
- 자동 댓글/AI 댓글/댓글부대/정치성 의심 분석용
- author_channel_id는 원본 대신 author_hash로 제공

04_ai_video_summary_input.csv
- 영상 제목/설명 기반 영상 요약용

05_top_liked_comments.csv
- 좋아요 많은 댓글 상위 100개

06_top_replied_comments.csv
- 대댓글 많은 원댓글 상위 100개

07_ai_comment_analysis_result_template.csv
- AI 결과를 받아야 하는 컬럼 템플릿

08_ai_suspicion_analysis_result_template.csv
- 의심 댓글 분석 결과 템플릿
```

## 6. AI에게 주는 방식

1. `02_ai_comment_analysis_input.csv` 업로드
2. `prompt_01_comment_analysis.txt` 내용을 같이 붙여넣기
3. AI가 결과 CSV를 주면 저장
4. 다음 단계에서 Python import 프로그램으로 DB에 넣기

의심 댓글도 동일합니다.

1. `03_ai_suspicion_analysis_input.csv` 업로드
2. `prompt_02_suspicion_analysis.txt` 사용

영상 요약은:

1. `04_ai_video_summary_input.csv` 업로드
2. `prompt_03_video_summary.txt` 사용

## 7. 다음 단계

다음 단계에서는 아래를 만들면 됩니다.

- AI 결과 CSV import
- `comment_analysis` INSERT
- `comment_suspicion_analysis` INSERT
- AI 키워드 `comment_keyword_raw` INSERT
- `video_keyword`, `keyword_edge` 집계 생성
