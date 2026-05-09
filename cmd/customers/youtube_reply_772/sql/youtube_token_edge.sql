-- ============================================================
-- token 동시출현 네트워크 edge 테이블
-- ============================================================
--
-- 같은 댓글 안에 같이 등장한 token 쌍을 저장한다.
-- 예:
-- 댓글에 [경제, 정책, 부동산]이 있으면
-- - 경제 - 정책
-- - 경제 - 부동산
-- - 정책 - 부동산
-- edge가 만들어진다.
--
-- weight는 같은 token 쌍이 몇 개 댓글에서 같이 등장했는지 의미한다.
-- 네트워크 그래프에서 선 굵기 기준으로 사용할 수 있다.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_token_edge
(
    edge_id bigserial NOT NULL,

    run_id character varying(50) NOT NULL,

    method_id character varying(50) NOT NULL,

    video_id character varying(50) NOT NULL,

    source_token character varying(300) NOT NULL,

    target_token character varying(300) NOT NULL,

    source_pos character varying(30),

    target_pos character varying(30),

    edge_type character varying(30) DEFAULT 'CO_OCCURRENCE',
    -- CO_OCCURRENCE : 같은 댓글 안에서 같이 등장
    -- AI_RELATION   : AI가 관계 있다고 판단
    -- HUMAN_RELATION: 사람이 직접 연결한 관계

    weight integer DEFAULT 1,
    -- 같이 등장한 댓글 수

    comment_count integer DEFAULT 1,
    -- 현재는 weight와 같은 값으로 저장
    -- 나중에 edge 발생 방식이 늘어나면 별도 의미로 확장 가능

    create_dt character varying(19),
    update_dt character varying(19),

    CONSTRAINT youtube_token_edge_pkey PRIMARY KEY (edge_id),

    CONSTRAINT fk_youtube_token_edge_run FOREIGN KEY (run_id)
        REFERENCES public.youtube_analysis_run (run_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT fk_youtube_token_edge_method FOREIGN KEY (method_id)
        REFERENCES public.youtube_analysis_method (method_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT,

    CONSTRAINT fk_youtube_token_edge_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,

    CONSTRAINT uk_youtube_token_edge_once UNIQUE
        (
         run_id,
         source_token,
         target_token,
         edge_type
            )
)
    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_token_edge OWNER to postgres;

CREATE INDEX IF NOT EXISTS idx_youtube_token_edge_video
    ON public.youtube_token_edge (video_id);

CREATE INDEX IF NOT EXISTS idx_youtube_token_edge_run
    ON public.youtube_token_edge (run_id);

CREATE INDEX IF NOT EXISTS idx_youtube_token_edge_source
    ON public.youtube_token_edge (source_token);

CREATE INDEX IF NOT EXISTS idx_youtube_token_edge_target
    ON public.youtube_token_edge (target_token);

CREATE INDEX IF NOT EXISTS idx_youtube_token_edge_weight
    ON public.youtube_token_edge (weight DESC);

COMMENT ON TABLE public.youtube_token_edge
IS 'token 동시출현 네트워크 edge 테이블. 같은 댓글 안에 같이 등장한 token 쌍과 가중치를 저장한다.';

COMMENT ON COLUMN public.youtube_token_edge.source_token
IS '네트워크 연결 시작 token. 정렬 안정성을 위해 보통 사전순 앞 token을 넣는다.';

COMMENT ON COLUMN public.youtube_token_edge.target_token
IS '네트워크 연결 대상 token. 정렬 안정성을 위해 보통 사전순 뒤 token을 넣는다.';

COMMENT ON COLUMN public.youtube_token_edge.weight
IS 'source_token과 target_token이 같은 댓글 안에서 같이 등장한 댓글 수';