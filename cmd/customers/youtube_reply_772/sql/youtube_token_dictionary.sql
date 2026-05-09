-- ============================================================
-- token 사전 테이블
-- ============================================================
--
-- 한국어 댓글 분석 품질을 높이기 위한 보정 사전이다.
-- 하나의 테이블에서 3가지 사전을 관리한다.
--
-- dict_type:
-- - STOPWORD  : 분석에서 제외할 단어
-- - USER_WORD : 형태소 분석기가 쪼개지 말고 하나의 단어로 보게 할 단어
-- - NORMALIZE : 여러 표현을 하나의 표준 표현으로 통일
--
-- scope_type:
-- - GLOBAL : 모든 영상에 공통 적용
-- - VIDEO  : 특정 video_id에만 적용
--
-- scope_key:
-- - GLOBAL이면 'GLOBAL'
-- - VIDEO이면 video_id 값
--
-- scope_key를 별도로 두는 이유:
-- - video_id가 NULL인 GLOBAL 데이터도 중복 관리하기 쉽게 하기 위해서다.
-- - UNIQUE(scope_key, dict_type, source_text)로 seed SQL을 여러 번 실행할 수 있다.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_token_dictionary
(
    dict_id bigserial NOT NULL,

    scope_type character varying(20) NOT NULL DEFAULT 'GLOBAL',
    -- GLOBAL: 모든 영상 공통
    -- VIDEO : 특정 영상 전용

    scope_key character varying(100) NOT NULL DEFAULT 'GLOBAL',
    -- GLOBAL이면 GLOBAL
    -- VIDEO이면 video_id

    video_id character varying(50),
    -- scope_type = VIDEO일 때만 사용
    -- scope_type = GLOBAL이면 NULL

    dict_type character varying(30) NOT NULL,
    -- STOPWORD  : 불용어
    -- USER_WORD : 사용자 사전 단어
    -- NORMALIZE : 정규화 사전

    source_text character varying(300) NOT NULL,
    -- 원본 표현
    -- STOPWORD  : 제외할 단어
    -- USER_WORD : 사용자 사전에 등록할 단어
    -- NORMALIZE : 바꾸기 전 표현

    target_text character varying(300),
    -- 바꿀 표현
    -- STOPWORD  : 보통 NULL
    -- USER_WORD : 보통 source_text와 동일
    -- NORMALIZE : 표준 표현

    pos character varying(30),
    -- USER_WORD 등록 시 사용할 품사
    -- 태그	| 이름 | 설명 | 댓글 | 분석 | 사용
    -- NNG	일반 명사	경제, 정책, 영상, 문제	매우 많이 사용
    -- NNP	고유 명사	사람명, 기관명, 정당명, 브랜드명	매우 많이 사용
    -- VV	동사	하다, 가다, 만들다	선택
    -- VA	형용사	좋다, 나쁘다, 심각하다	감정 분석 보조용
    -- XR	어근	중요, 심각, 불안 같은 어근	선택
    -- MAG	일반 부사	매우, 너무, 잘	보통 제외하거나 선택
    -- IC	감탄사	와, 아, 헐	감정 분석이면 선택
    -- 비워두면 py에서 기본 NNP로 등록

    description text,

    use_yn character varying(1) DEFAULT 'Y',

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_token_dictionary_pkey PRIMARY KEY (dict_id),

    CONSTRAINT fk_youtube_token_dictionary_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT uk_youtube_token_dictionary_once UNIQUE
        (
         scope_key,
         dict_type,
         source_text
            )
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_token_dictionary OWNER to postgres;

CREATE INDEX IF NOT EXISTS idx_youtube_token_dictionary_scope
    ON public.youtube_token_dictionary (scope_type, scope_key);

CREATE INDEX IF NOT EXISTS idx_youtube_token_dictionary_type
    ON public.youtube_token_dictionary (dict_type);

CREATE INDEX IF NOT EXISTS idx_youtube_token_dictionary_video
    ON public.youtube_token_dictionary (video_id);

COMMENT ON TABLE public.youtube_token_dictionary
IS '댓글 token 분석용 사전 테이블. 불용어, 사용자 사전, 정규화 사전을 GLOBAL/VIDEO 범위로 관리한다.';

COMMENT ON COLUMN public.youtube_token_dictionary.scope_type
IS '사전 적용 범위. GLOBAL은 모든 영상, VIDEO는 특정 영상 전용';

COMMENT ON COLUMN public.youtube_token_dictionary.scope_key
IS '중복 관리를 위한 범위 키. GLOBAL이면 GLOBAL, VIDEO이면 video_id';

COMMENT ON COLUMN public.youtube_token_dictionary.dict_type
IS '사전 유형. STOPWORD, USER_WORD, NORMALIZE';

COMMENT ON COLUMN public.youtube_token_dictionary.source_text
IS '원본 표현. 불용어/사용자 단어/정규화 전 표현';

COMMENT ON COLUMN public.youtube_token_dictionary.target_text
IS '정규화 후 표준 표현. STOPWORD는 보통 NULL';

COMMENT ON COLUMN public.youtube_token_dictionary.pos
IS '사용자 사전 등록용 품사. 보통 고유명사 NNP 사용';