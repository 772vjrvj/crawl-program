-- ============================================================
-- 댓글별 TF-IDF 결과 테이블(Term Frequency - Inverse Document Frequency)
-- ============================================================
--
-- TF-IDF는 단순 빈도와 다른 중요도 점수다.
-- - TF  : 특정 댓글 안에서 token이 나온 횟수
-- - DF  : 전체 댓글 중 해당 token이 등장한 댓글 수
-- - IDF : 흔한 token의 점수를 낮추고, 드문 token의 점수를 높이는 값
--
-- 이 테이블은 댓글별 token의 TF-IDF 점수를 저장한다.
-- 전체 중요 token TOP은 이 테이블을 token_norm 기준으로 GROUP BY 해서 구한다.
-- 댓글 하나 안에서 특정 단어가 얼마나 자주 나왔는지입니다.
-- 이 영상 진짜 좋네요. 설명도 좋고 내용도 좋아요.(여기서 좋다가 여러 번 나오면 TF 점수가 올라갑니다.)
-- IDF = 희귀도 전체 댓글에서 너무 흔한 단어는 중요도를 낮춥니다. (반대로 특정 주제 댓글에서만 많이 나오는 단어:)
-- 단순 빈도는 영상, 좋다, 진짜 같은 단어가 많이 잡힐 수 있습니다.  하지만 TF-IDF는 댓글 전체에서 흔한 단어보다, 특정 주제를 강하게 나타내는: 부동산, 정책, 청년, 가격
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_comment_tfidf
(
    tfidf_id bigserial NOT NULL,

    run_id character varying(50) NOT NULL,

    method_id character varying(50) NOT NULL,

    video_id character varying(50) NOT NULL,

    comment_id character varying(150) NOT NULL,

    parent_comment_id character varying(150),

    comment_kind character varying(20) NOT NULL,

    token_norm character varying(300) NOT NULL,

    pos character varying(30),

    tf integer DEFAULT 0,
    -- 해당 댓글 안에서 token 등장 횟수

    df integer DEFAULT 0,
    -- 전체 댓글 중 해당 token이 등장한 댓글 수

    total_doc_count integer DEFAULT 0,
    -- 분석 대상 전체 댓글 수

    idf numeric(20, 10) DEFAULT 0,
    -- IDF 점수

    tfidf_score numeric(20, 10) DEFAULT 0,
    -- TF * IDF 최종 점수

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_comment_tfidf_pkey PRIMARY KEY (tfidf_id),

    CONSTRAINT fk_youtube_comment_tfidf_run FOREIGN KEY (run_id)
        REFERENCES public.youtube_analysis_run (run_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_tfidf_method FOREIGN KEY (method_id)
        REFERENCES public.youtube_analysis_method (method_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT,

    CONSTRAINT fk_youtube_comment_tfidf_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_comment_tfidf_comment FOREIGN KEY (comment_id)
        REFERENCES public.youtube_comment (comment_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT uk_youtube_comment_tfidf_once UNIQUE
        (
         run_id,
         comment_id,
         token_norm,
         pos
            )
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_comment_tfidf OWNER to postgres;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_video
    ON public.youtube_comment_tfidf (video_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_run
    ON public.youtube_comment_tfidf (run_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_comment
    ON public.youtube_comment_tfidf (comment_id);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_kind
    ON public.youtube_comment_tfidf (comment_kind);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_token
    ON public.youtube_comment_tfidf (token_norm);

CREATE INDEX IF NOT EXISTS idx_youtube_comment_tfidf_score
    ON public.youtube_comment_tfidf (tfidf_score DESC);

COMMENT ON TABLE public.youtube_comment_tfidf
IS '댓글별 TF-IDF 결과 테이블. token의 빈도와 희소성을 반영한 중요도 점수를 저장한다.';

COMMENT ON COLUMN public.youtube_comment_tfidf.tf
IS '특정 댓글 안에서 해당 token이 등장한 횟수';

COMMENT ON COLUMN public.youtube_comment_tfidf.df
IS '전체 분석 댓글 중 해당 token이 등장한 댓글 수';

COMMENT ON COLUMN public.youtube_comment_tfidf.total_doc_count
IS 'TF-IDF 계산 기준 전체 댓글 수';

COMMENT ON COLUMN public.youtube_comment_tfidf.idf
IS '희소성 점수. 흔한 token일수록 낮아진다';

COMMENT ON COLUMN public.youtube_comment_tfidf.tfidf_score
IS 'TF-IDF 최종 점수. 일반적으로 중요한 token 정렬 기준으로 사용';