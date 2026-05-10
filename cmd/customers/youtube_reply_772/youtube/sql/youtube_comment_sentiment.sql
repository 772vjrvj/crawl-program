-- ============================================================
-- 댓글별 감성분석 결과 테이블
-- ============================================================
--
-- 목적:
-- 1) youtube_comment 원본 댓글을 직접 수정하지 않는다.
-- 2) comment_id를 기준으로 감성분석 결과를 별도 저장한다.
-- 3) run_id 기준으로 같은 댓글도 여러 방식/프롬프트/모델로 재분석 가능하게 한다.
--
-- 점수 기준:
-- sentiment_score: -1.0000 ~ 1.0000
--   1에 가까움  = 긍정
--   0에 가까움  = 중립
--  -1에 가까움  = 부정
--
-- label 기준:
-- POSITIVE : 긍정
-- NEGATIVE : 부정
-- NEUTRAL  : 중립
-- MIXED    : 긍정/부정 혼합
-- ============================================================


-- ============================================================
-- 0. 기존 테이블 삭제가 필요할 때만 주석 해제
-- ============================================================

-- DROP TABLE IF EXISTS public.youtube_comment_sentiment;


-- ============================================================
-- 1. 댓글별 감성분석 결과 테이블 생성
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_comment_sentiment
(
    sentiment_id bigserial NOT NULL,

    run_id character varying(50) NOT NULL,

    method_id character varying(50) NOT NULL,

    video_id character varying(50) NOT NULL,

    comment_id character varying(150) NOT NULL,

    parent_comment_id character varying(150),
    -- 원댓글이면 NULL
    -- 대댓글이면 부모 원댓글 comment_id

    comment_kind character varying(20) NOT NULL,
    -- TOP   : 원댓글
    -- REPLY : 대댓글

    sentiment_label character varying(20) NOT NULL,
    -- POSITIVE
    -- NEGATIVE
    -- NEUTRAL
    -- MIXED

    sentiment_score numeric(8, 4) NOT NULL DEFAULT 0,
    -- -1.0000 ~ 1.0000
    --  1에 가까울수록 긍정
    --  0에 가까울수록 중립
    -- -1에 가까울수록 부정

    sentiment_magnitude numeric(8, 4),
    -- 감정 강도
    -- 예: 욕설/강한 비난/강한 칭찬처럼 감정 표현이 강하면 높게 저장
    -- Google NLP의 magnitude 개념과 유사하게 사용 가능

    positive_score numeric(8, 4),
    -- 긍정 확률 또는 긍정 점수. 0 ~ 1

    negative_score numeric(8, 4),
    -- 부정 확률 또는 부정 점수. 0 ~ 1

    neutral_score numeric(8, 4),
    -- 중립 확률 또는 중립 점수. 0 ~ 1

    mixed_score numeric(8, 4),
    -- 긍정/부정 혼합 확률 또는 혼합 점수. 0 ~ 1

    confidence_score numeric(8, 4),
    -- 모델 판단 신뢰도. 0 ~ 1

    reason_text text,
    -- 선택값
    -- AI가 판단 근거를 짧게 반환하는 경우 저장
    -- 대량 분석에서는 비용/속도 때문에 비워도 됨

    request_id character varying(100),
    -- CLOVA, GPT 등 API 요청 ID 저장용

    input_token_count integer DEFAULT 0,
    -- AI API 입력 토큰 수. 제공하지 않는 모델이면 0

    output_token_count integer DEFAULT 0,
    -- AI API 출력 토큰 수. 제공하지 않는 모델이면 0

    total_token_count integer DEFAULT 0,
    -- input + output 토큰 수. 비용 계산용

    response_ms integer DEFAULT 0,
    -- API 응답 소요 시간(ms)

    raw_json jsonb,
    -- AI 원본 응답 JSON 저장
    -- 나중에 재검증/디버깅/논문 근거용으로 중요

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_comment_sentiment_pkey PRIMARY KEY (sentiment_id),

    CONSTRAINT fk_youtube_comment_sentiment_run FOREIGN KEY (run_id)
        REFERENCES public.youtube_analysis_run (run_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_sentiment_method FOREIGN KEY (method_id)
        REFERENCES public.youtube_analysis_method (method_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT,

    CONSTRAINT fk_youtube_comment_sentiment_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_sentiment_comment FOREIGN KEY (comment_id)
        REFERENCES public.youtube_comment (comment_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT uk_youtube_comment_sentiment_once UNIQUE
        (
         run_id,
         comment_id
            ),

    CONSTRAINT ck_youtube_comment_sentiment_kind CHECK
        (
        comment_kind IN ('TOP', 'REPLY')
        ),

    CONSTRAINT ck_youtube_comment_sentiment_label CHECK
        (
        sentiment_label IN ('POSITIVE', 'NEGATIVE', 'NEUTRAL', 'MIXED')
        ),

    CONSTRAINT ck_youtube_comment_sentiment_score CHECK
        (
        sentiment_score >= -1
            AND sentiment_score <= 1
        ),

    CONSTRAINT ck_youtube_comment_sentiment_positive_score CHECK
        (
        positive_score IS NULL
            OR (
            positive_score >= 0
                AND positive_score <= 1
            )
        ),

    CONSTRAINT ck_youtube_comment_sentiment_negative_score CHECK
        (
        negative_score IS NULL
            OR (
            negative_score >= 0
                AND negative_score <= 1
            )
        ),

    CONSTRAINT ck_youtube_comment_sentiment_neutral_score CHECK
        (
        neutral_score IS NULL
            OR (
            neutral_score >= 0
                AND neutral_score <= 1
            )
        ),

    CONSTRAINT ck_youtube_comment_sentiment_mixed_score CHECK
        (
        mixed_score IS NULL
            OR (
            mixed_score >= 0
                AND mixed_score <= 1
            )
        ),

    CONSTRAINT ck_youtube_comment_sentiment_confidence_score CHECK
        (
        confidence_score IS NULL
            OR (
            confidence_score >= 0
                AND confidence_score <= 1
            )
        )
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_comment_sentiment OWNER TO postgres;


-- ============================================================
-- 2. 인덱스
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_video
    ON public.youtube_comment_sentiment (video_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_run
    ON public.youtube_comment_sentiment (run_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_method
    ON public.youtube_comment_sentiment (method_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_comment
    ON public.youtube_comment_sentiment (comment_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_parent
    ON public.youtube_comment_sentiment (parent_comment_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_kind
    ON public.youtube_comment_sentiment (comment_kind);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_label
    ON public.youtube_comment_sentiment (sentiment_label);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_score
    ON public.youtube_comment_sentiment (video_id, sentiment_score DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_negative
    ON public.youtube_comment_sentiment (video_id, negative_score DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sentiment_confidence
    ON public.youtube_comment_sentiment (confidence_score DESC);


-- ============================================================
-- 3. 테이블 / 컬럼 설명
-- ============================================================

COMMENT ON TABLE public.youtube_comment_sentiment
IS '댓글별 감성분석 결과 테이블. 원본 댓글은 수정하지 않고 comment_id 기준으로 감성 라벨, 점수, 확률, 원본 AI 응답을 저장한다.';

COMMENT ON COLUMN public.youtube_comment_sentiment.run_id
IS '감성분석 실행 ID. youtube_analysis_run.run_id 참조';

COMMENT ON COLUMN public.youtube_comment_sentiment.method_id
IS '감성분석 방법 ID. youtube_analysis_method.method_id 참조';

COMMENT ON COLUMN public.youtube_comment_sentiment.video_id
IS '분석 대상 유튜브 영상 ID';

COMMENT ON COLUMN public.youtube_comment_sentiment.comment_id
IS '감성분석 대상 댓글 ID. youtube_comment.comment_id 참조';

COMMENT ON COLUMN public.youtube_comment_sentiment.parent_comment_id
IS '대댓글인 경우 부모 원댓글 ID. 원댓글이면 NULL';

COMMENT ON COLUMN public.youtube_comment_sentiment.comment_kind
IS '댓글 유형. TOP=원댓글, REPLY=대댓글';

COMMENT ON COLUMN public.youtube_comment_sentiment.sentiment_label
IS '감성 라벨. POSITIVE=긍정, NEGATIVE=부정, NEUTRAL=중립, MIXED=혼합';

COMMENT ON COLUMN public.youtube_comment_sentiment.sentiment_score
IS '감성 점수. -1~1 범위. 1에 가까우면 긍정, -1에 가까우면 부정, 0에 가까우면 중립';

COMMENT ON COLUMN public.youtube_comment_sentiment.sentiment_magnitude
IS '감정 강도. 감정 표현이 강할수록 높은 값. 선택 컬럼';

COMMENT ON COLUMN public.youtube_comment_sentiment.positive_score
IS '긍정 확률 또는 긍정 점수. 0~1 범위';

COMMENT ON COLUMN public.youtube_comment_sentiment.negative_score
IS '부정 확률 또는 부정 점수. 0~1 범위';

COMMENT ON COLUMN public.youtube_comment_sentiment.neutral_score
IS '중립 확률 또는 중립 점수. 0~1 범위';

COMMENT ON COLUMN public.youtube_comment_sentiment.mixed_score
IS '긍정/부정 혼합 확률 또는 혼합 점수. 0~1 범위';

COMMENT ON COLUMN public.youtube_comment_sentiment.confidence_score
IS '모델 판단 신뢰도. 0~1 범위';

COMMENT ON COLUMN public.youtube_comment_sentiment.reason_text
IS 'AI가 반환한 감성 판단 근거. 대량 분석에서는 비워도 됨';

COMMENT ON COLUMN public.youtube_comment_sentiment.request_id
IS 'AI API 요청 ID. 장애 추적/원본 요청 확인용';

COMMENT ON COLUMN public.youtube_comment_sentiment.input_token_count
IS 'AI API 입력 토큰 수. 비용 계산용';

COMMENT ON COLUMN public.youtube_comment_sentiment.output_token_count
IS 'AI API 출력 토큰 수. 비용 계산용';

COMMENT ON COLUMN public.youtube_comment_sentiment.total_token_count
IS 'AI API 전체 토큰 수. 비용 계산용';

COMMENT ON COLUMN public.youtube_comment_sentiment.response_ms
IS 'AI API 응답 소요 시간(ms)';

COMMENT ON COLUMN public.youtube_comment_sentiment.raw_json
IS 'AI 감성분석 원본 응답 JSON';

COMMENT ON COLUMN public.youtube_comment_sentiment.create_dt
IS 'DB 최초 생성일시. YYYY-MM-DD HH24:MI:SS';

COMMENT ON COLUMN public.youtube_comment_sentiment.update_dt
IS 'DB 최종 수정일시. YYYY-MM-DD HH24:MI:SS';


-- ============================================================
-- 4. 감성분석 method 기본 등록
-- ============================================================

INSERT INTO public.youtube_analysis_method
(
    method_id,
    method_type,
    method_name,
    provider,
    model_name,
    model_version,
    worker_name,
    description,
    option_json,
    use_yn,
    create_dt,
    update_dt
)
VALUES
    (
        'SENTIMENT_CHATGPT_GPT55_THINKING_V1',
        'AI',
        'ChatGPT 댓글 감성분석',
        'OPENAI',
        'GPT-5.5 Thinking',
        'V1',
        NULL,
        'ChatGPT를 이용하여 유튜브 댓글을 POSITIVE, NEGATIVE, NEUTRAL, MIXED로 분류하고 -1~1 감성 점수를 부여한 감성분석 방식',
        '{
            "label_list": ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"],
            "score_range": "-1_to_1",
            "positive_threshold": 0.3,
            "negative_threshold": -0.3,
            "neutral_range": [-0.3, 0.3],
            "score_description": {
                "1": "strong_positive",
                "0": "neutral",
                "-1": "strong_negative"
            },
            "analysis_source": "manual_chatgpt_json",
            "output_format": "json",
            "fields": [
                "comment_id",
                "sentiment_label",
                "sentiment_score",
                "sentiment_magnitude",
                "positive_score",
                "negative_score",
                "neutral_score",
                "mixed_score",
                "confidence_score",
                "reason_text"
            ]
        }'::jsonb,
        'Y',
        TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
        TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
ON CONFLICT (method_id)
DO UPDATE SET
    method_type = EXCLUDED.method_type,
    method_name = EXCLUDED.method_name,
    provider = EXCLUDED.provider,
    model_name = EXCLUDED.model_name,
    model_version = EXCLUDED.model_version,
    worker_name = EXCLUDED.worker_name,
    description = EXCLUDED.description,
    option_json = EXCLUDED.option_json,
    use_yn = EXCLUDED.use_yn,
    update_dt = EXCLUDED.update_dt;


-- ============================================================
-- 5. 확인용 SELECT
-- ============================================================

SELECT *
FROM public.youtube_analysis_method
WHERE method_id = 'SENTIMENT_CHATGPT_GPT55_THINKING_V1';

SELECT COUNT(*) AS sentiment_count
FROM public.youtube_comment_sentiment;

DELETE FROM public.youtube_comment_sentiment
WHERE video_id = '8kFnA0oxFeI';


SELECT
    c.comment_text AS 본문,
    CASE s.sentiment_label
        WHEN 'POSITIVE' THEN '긍정'
        WHEN 'NEGATIVE' THEN '부정'
        WHEN 'NEUTRAL'  THEN '중립'
        WHEN 'MIXED'    THEN '혼합'
        ELSE s.sentiment_label
        END AS 감성,
    s.sentiment_score AS 점수
FROM public.youtube_comment_sentiment s
         JOIN public.youtube_comment c
              ON s.comment_id = c.comment_id
WHERE s.run_id = (
    SELECT r.run_id
    FROM public.youtube_analysis_run r
    WHERE r.video_id = '8kFnA0oxFeI'
      AND r.analysis_task = 'SENTIMENT'
      AND r.status = 'SUCCESS'
    ORDER BY r.ended_at DESC NULLS LAST,
             r.started_at DESC NULLS LAST,
             r.create_dt DESC NULLS LAST
    LIMIT 1
)
ORDER BY c.top_comment_no ASC, c.reply_no ASC;