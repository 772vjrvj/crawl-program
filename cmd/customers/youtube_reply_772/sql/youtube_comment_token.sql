-- ============================================================
-- 댓글별 token 분석 결과 테이블
-- ============================================================
--
-- 댓글 1개를 문서 1개로 보고, 해당 댓글에서 나온 token을 저장한다.
-- 전체 통계는 이 테이블을 GROUP BY 해서 구한다.
--
-- comment_id를 저장하는 이유:
-- - 어떤 댓글에서 나온 token인지 추적 가능
-- - 원댓글/대댓글 분석 가능
-- - 좋아요 많은 댓글, 부정 댓글 등 다른 분석 결과와 JOIN 가능
--
-- parent_comment_id/comment_kind를 저장하는 이유:
-- - 원본 youtube_comment와 JOIN하지 않고도 원댓글/대댓글 조건 분석 가능
-- - 분석 테이블만으로 조회가 쉬워짐
-- ============================================================
CREATE TABLE IF NOT EXISTS public.youtube_comment_token
(
    token_id bigserial NOT NULL,

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

    token_text character varying(300) NOT NULL,
    -- 형태소 분석 결과 원문 token

    token_norm character varying(300) NOT NULL,
    -- 정규화된 token
    -- 예: 국힘 -> 국민의힘

    pos character varying(30),
    -- 품사
    -- 예: NNG, NNP, VV, VA

    token_type character varying(30) DEFAULT 'MORPHEME',
    -- MORPHEME : 형태소 분석 결과
    -- WORD     : 공백 기준 단어
    -- PHRASE   : 구문
    -- AI_TERM  : AI가 뽑은 핵심어
    -- HUMAN    : 사람이 지정한 token

    token_count integer DEFAULT 1,
    -- 해당 댓글 안에서 같은 token이 나온 횟수

    first_token_order integer DEFAULT 0,
    -- 해당 댓글 안에서 이 token이 처음 등장한 순서
    -- 대통령 정책 때문에 경제 문제가 커졌다 1 대통령 2 정책
    -- 빈도/TF-IDF만 볼 때는 필수는 아니지만, 문맥 추적용으로 유용하다.

    token_len integer DEFAULT 0,
    -- token_norm 글자 수
    -- 조회 조건이나 품질 점검용으로 사용 가능

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_comment_token_pkey PRIMARY KEY (token_id),

    CONSTRAINT fk_youtube_comment_token_run FOREIGN KEY (run_id)
        REFERENCES public.youtube_analysis_run (run_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_token_method FOREIGN KEY (method_id)
        REFERENCES public.youtube_analysis_method (method_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT,

    CONSTRAINT fk_youtube_comment_token_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_token_comment FOREIGN KEY (comment_id)
        REFERENCES public.youtube_comment (comment_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT uk_youtube_comment_token_once UNIQUE
        (
         run_id,
         comment_id,
         token_norm,
         pos,
         token_type
            )
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_comment_token OWNER to postgres;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_video
    ON public.youtube_comment_token (video_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_run
    ON public.youtube_comment_token (run_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_method
    ON public.youtube_comment_token (method_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_comment
    ON public.youtube_comment_token (comment_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_parent
    ON public.youtube_comment_token (parent_comment_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_kind
    ON public.youtube_comment_token (comment_kind);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_token_norm
    ON public.youtube_comment_token (token_norm);

COMMENT ON TABLE public.youtube_comment_token
IS '댓글별 token 분석 결과 테이블. 댓글 1개에서 추출된 token과 등장 횟수를 저장한다.';

COMMENT ON COLUMN public.youtube_comment_token.comment_id
IS 'token이 나온 댓글 ID';

COMMENT ON COLUMN public.youtube_comment_token.parent_comment_id
IS '대댓글인 경우 부모 원댓글 ID. 원댓글이면 NULL';

COMMENT ON COLUMN public.youtube_comment_token.comment_kind
IS '댓글 유형. TOP=원댓글, REPLY=대댓글';

COMMENT ON COLUMN public.youtube_comment_token.token_text
IS '형태소 분석 결과 원문 token';

COMMENT ON COLUMN public.youtube_comment_token.token_norm
IS '정규화 적용 후 token. 통계/TF-IDF/네트워크 기준 값';

COMMENT ON COLUMN public.youtube_comment_token.token_count
IS '해당 댓글 안에서 같은 token이 등장한 횟수';

COMMENT ON COLUMN public.youtube_comment_token.first_token_order
IS '댓글 안에서 해당 token이 처음 등장한 순서';

COMMENT ON COLUMN public.youtube_comment_token.token_len
IS 'token_norm 글자 수';