-- ============================================================
-- youtube_analysis_run
-- 분석 실행 이력 테이블
-- ============================================================
-- 목적:
-- 1. 어떤 영상(video_id)을
-- 2. 어떤 분석 방법(method_id)으로
-- 3. 어떤 분석 작업(analysis_task)을
-- 4. 언제 실행했는지 기록한다.

-- 같은 video_id라도 분석 조건이 바뀌면 결과가 달라진다.
-- 예:
-- - 1차: 명사만 추출
-- - 2차: 명사 + 형용사 추출
-- - 3차: 불용어 추가 후 재분석
--
-- 그래서 실행 단위인 run_id를 만들고,
-- token/tfidf/edge 결과를 run_id 기준으로 묶는다.

-- 예:
-- TOKENIZE  실행 결과 수 = token row 수
-- TFIDF     실행 결과 수 = tfidf row 수
-- NETWORK   실행 결과 수 = edge row 수
-- SENTIMENT 실행 결과 수 = sentiment row 수
--
-- 그래서 token_count, tfidf_count, edge_count처럼
-- 작업별 컬럼을 따로 두지 않고 result_count 하나로 통일한다.
-- ============================================================


CREATE TABLE IF NOT EXISTS public.youtube_analysis_run
(
    run_id character varying(50) NOT NULL,

    video_id character varying(50) NOT NULL,

    method_id character varying(50) NOT NULL,

    analysis_task character varying(50) NOT NULL,
    -- TOKENIZE   : 형태소/token 분석
    -- TFIDF      : TF-IDF 계산
    -- NETWORK    : 동시출현 네트워크 생성
    -- SENTIMENT  : 감정분석
    -- TOPIC      : 주제분류
    -- HUMAN      : 사람 검수

    include_reply_yn character varying(1) DEFAULT 'Y',

    status character varying(30) DEFAULT 'READY',
    -- READY   : 실행 전
    -- RUNNING : 실행 중
    -- SUCCESS : 성공
    -- FAIL    : 실패
    -- STOP    : 중지

    config_json jsonb,
    -- 실행 당시 사용한 옵션 저장
    -- 예:
    -- {
    --   "pos_list": ["NNG", "NNP"],
    --   "min_token_len": 2,
    --   "min_edge_weight": 2,
    --   "dictionary_scope": ["GLOBAL", "VIDEO"]
    -- }

    total_comment_count integer DEFAULT 0,
    -- 분석 대상 댓글 수
    -- 원댓글만 분석하면 원댓글 수
    -- 대댓글 포함이면 원댓글 + 대댓글 수

    result_count integer DEFAULT 0,
    -- 분석 작업별 결과 row 수
    --
    -- analysis_task = TOKENIZE 이면
    -- youtube_comment_token에 저장된 row 수
    --
    -- analysis_task = TFIDF 이면
    -- youtube_comment_tfidf에 저장된 row 수
    --
    -- analysis_task = NETWORK 이면
    -- youtube_token_edge에 저장된 row 수
    --
    -- analysis_task = SENTIMENT 이면
    -- 감정분석 결과 row 수

    error_message text,

    started_at character varying(19),

    ended_at character varying(19),

    create_dt character varying(19),

    update_dt character varying(19),

    CONSTRAINT youtube_analysis_run_pkey PRIMARY KEY (run_id),

    CONSTRAINT fk_youtube_analysis_run_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_analysis_run_method FOREIGN KEY (method_id)
        REFERENCES public.youtube_analysis_method (method_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT
)

    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_analysis_run
    OWNER to postgres;


-- ============================================================
-- 테이블 설명
-- ============================================================

COMMENT ON TABLE public.youtube_analysis_run
IS '유튜브 댓글 분석 실행 이력 테이블. 영상별, 분석방법별, 분석작업별 실행 정보를 저장한다.';


-- ============================================================
-- 컬럼 설명
-- ============================================================

COMMENT ON COLUMN public.youtube_analysis_run.run_id
IS '분석 실행 ID. UUID 또는 별도 생성 규칙으로 만든 고유값';

COMMENT ON COLUMN public.youtube_analysis_run.video_id
IS '분석 대상 유튜브 영상 ID. youtube_video.video_id 참조';

COMMENT ON COLUMN public.youtube_analysis_run.method_id
IS '분석 방법 ID. youtube_analysis_method.method_id 참조. 예: MORPH_KIWI_V1, AI_GPT_SENTIMENT_V1, HUMAN_REVIEW_V1';

COMMENT ON COLUMN public.youtube_analysis_run.analysis_task
IS '분석 작업 구분. TOKENIZE=형태소/token 분석, TFIDF=TF-IDF 계산, NETWORK=동시출현 네트워크, SENTIMENT=감정분석, TOPIC=주제분류, HUMAN=사람 검수';

COMMENT ON COLUMN public.youtube_analysis_run.include_reply_yn
IS '대댓글 포함 여부. Y=원댓글+대댓글 분석, N=원댓글만 분석';

COMMENT ON COLUMN public.youtube_analysis_run.status
IS '분석 실행 상태. READY=실행전, RUNNING=실행중, SUCCESS=성공, FAIL=실패, STOP=중지';

COMMENT ON COLUMN public.youtube_analysis_run.config_json
IS '분석 실행 당시 사용한 설정 JSON. 품사 목록, 최소 token 길이, edge 최소 weight, 사전 적용 범위 등을 저장';

COMMENT ON COLUMN public.youtube_analysis_run.total_comment_count
IS '분석 대상 댓글 수. include_reply_yn 설정에 따라 원댓글만 또는 원댓글+대댓글 수를 저장';

COMMENT ON COLUMN public.youtube_analysis_run.result_count
IS '분석 결과 row 수. analysis_task에 따라 TOKENIZE는 token row 수, TFIDF는 tfidf row 수, NETWORK는 edge row 수를 의미';

COMMENT ON COLUMN public.youtube_analysis_run.error_message
IS '분석 실패 시 오류 메시지 저장';

COMMENT ON COLUMN public.youtube_analysis_run.started_at
IS '분석 시작일시. YYYY-MM-DD HH24:MI:SS 형식 문자열';

COMMENT ON COLUMN public.youtube_analysis_run.ended_at
IS '분석 종료일시. YYYY-MM-DD HH24:MI:SS 형식 문자열';

COMMENT ON COLUMN public.youtube_analysis_run.create_dt
IS 'DB 최초 생성일시. YYYY-MM-DD HH24:MI:SS 형식 문자열';

COMMENT ON COLUMN public.youtube_analysis_run.update_dt
IS 'DB 최종 수정일시. YYYY-MM-DD HH24:MI:SS 형식 문자열';


-- ============================================================
-- 인덱스
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_youtube_analysis_run_video
    ON public.youtube_analysis_run (video_id);

CREATE INDEX IF NOT EXISTS idx_youtube_analysis_run_method
    ON public.youtube_analysis_run (method_id);

CREATE INDEX IF NOT EXISTS idx_youtube_analysis_run_task
    ON public.youtube_analysis_run (analysis_task);

CREATE INDEX IF NOT EXISTS idx_youtube_analysis_run_status
    ON public.youtube_analysis_run (status);

CREATE INDEX IF NOT EXISTS idx_youtube_analysis_run_video_task
    ON public.youtube_analysis_run (video_id, analysis_task);