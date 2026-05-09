-- ============================================================
-- 분석 방식 마스터 테이블
-- ============================================================
--
-- 이 테이블은 분석 결과가 어떤 방식으로 생성되었는지 관리한다.
-- 예:
-- - MORPH_KIWI_V1          : Kiwi 형태소 분석기 1차 버전
-- - AI_GPT_SENTIMENT_V1    : GPT 기반 감정분석 1차 버전
-- - HUMAN_TOKEN_V1         : 사람이 직접 지정한 token 버전
--
-- 같은 댓글이라도 분석 방식에 따라 결과가 달라질 수 있으므로,
-- 모든 분석 결과 테이블에 method_id를 같이 저장한다.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_analysis_method
(
    method_id character varying(50) NOT NULL,

    method_type character varying(30) NOT NULL,
    -- MORPH : 형태소 분석기 기반
    -- AI    : GPT/Gemini/Claude 등 AI 기반
    -- HUMAN : 사람이 직접 분류/검수
    -- ML    : 직접 학습한 머신러닝 모델
    -- RULE  : 규칙 기반 처리

    method_name character varying(100) NOT NULL,
    -- 화면 표시용 이름
    -- 예: KIWI 형태소 분석, GPT 감정분석, 사람 검수

    provider character varying(100),
    -- 제공자 또는 라이브러리명
    -- 예: kiwipiepy, openai, google, human, custom

    model_name character varying(100),
    -- 모델 또는 분석기 이름
    -- 예: kiwi, gpt-4.1, gemini-1.5-pro

    model_version character varying(100),
    -- 모델/분석기 버전
    -- 예: v1, 0.21.0, 2026-05

    worker_name character varying(100),
    -- 사람이 작업한 경우 작업자명
    -- AI/형태소 분석이면 NULL 가능

    description text,

    option_json jsonb,
    -- 분석 방식의 기본 옵션 저장
    -- 예: {"pos_list": ["NNG", "NNP"], "min_token_len": 2}

    use_yn character varying(1) DEFAULT 'Y',

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_analysis_method_pkey PRIMARY KEY (method_id)
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_analysis_method OWNER to postgres;

COMMENT ON TABLE public.youtube_analysis_method
IS '댓글 분석 방식 마스터 테이블. 형태소 분석기, AI, 사람 검수, 머신러닝, 규칙 기반 분석 방법을 관리한다.';

COMMENT ON COLUMN public.youtube_analysis_method.method_id
IS '분석 방식 고유 ID. 예: MORPH_KIWI_V1, AI_GPT_SENTIMENT_V1, HUMAN_TOKEN_V1';

COMMENT ON COLUMN public.youtube_analysis_method.method_type
IS '분석 방식 유형. MORPH, AI, HUMAN, ML, RULE 중 하나로 사용';

COMMENT ON COLUMN public.youtube_analysis_method.method_name
IS '분석 방식 표시명';

COMMENT ON COLUMN public.youtube_analysis_method.provider
IS '분석 제공자 또는 라이브러리명. 예: kiwipiepy, openai, human';

COMMENT ON COLUMN public.youtube_analysis_method.model_name
IS '모델명 또는 분석기명';

COMMENT ON COLUMN public.youtube_analysis_method.model_version
IS '모델/분석기 버전';

COMMENT ON COLUMN public.youtube_analysis_method.worker_name
IS '사람이 작업한 경우 작업자명';

COMMENT ON COLUMN public.youtube_analysis_method.option_json
IS '분석 기본 옵션 JSON';
