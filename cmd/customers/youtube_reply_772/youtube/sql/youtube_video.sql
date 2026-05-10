-- ============================================================
-- 0. 기존 테이블 삭제가 필요할 때만 아래 주석 해제
-- ============================================================

-- DROP TABLE IF EXISTS public.youtube_video;

-- ============================================================
-- 유튜브 영상 테이블
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_video
(
    video_id character varying(50) COLLATE pg_catalog."default" NOT NULL,
    title character varying(500) COLLATE pg_catalog."default",
    channel_title character varying(300) COLLATE pg_catalog."default",
    channel_id character varying(100) COLLATE pg_catalog."default",
    video_url text COLLATE pg_catalog."default",
    thumbnail_url text COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    published_at timestamp with time zone,
    view_count bigint DEFAULT 0,
    like_count bigint DEFAULT 0,
    comment_count bigint DEFAULT 0,
    comment_order character varying(30) COLLATE pg_catalog."default",
    collected_at character varying(19) COLLATE pg_catalog."default",
    raw_json jsonb,
    create_dt character varying(19) COLLATE pg_catalog."default",
    update_dt character varying(19) COLLATE pg_catalog."default",

    CONSTRAINT youtube_video_pkey PRIMARY KEY (video_id)
)

    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_video
    OWNER to postgres;


-- ============================================================
-- 1-1. 유튜브 영상 테이블 코멘트
-- ============================================================

COMMENT ON TABLE public.youtube_video
    IS '유튜브 영상 원본 정보 테이블. 영상 제목, 채널, 조회수, 좋아요수, 댓글수, 원본 JSON 등을 저장한다.';

COMMENT ON COLUMN public.youtube_video.video_id
    IS '유튜브 영상 ID. 예: NJFf64DGjds';

COMMENT ON COLUMN public.youtube_video.title
    IS '영상 제목';

COMMENT ON COLUMN public.youtube_video.channel_title
    IS '채널명';

COMMENT ON COLUMN public.youtube_video.channel_id
    IS '유튜브 채널 ID';

COMMENT ON COLUMN public.youtube_video.video_url
    IS '영상 URL';

COMMENT ON COLUMN public.youtube_video.thumbnail_url
    IS '영상 썸네일 URL';

COMMENT ON COLUMN public.youtube_video.description
    IS '영상 설명란 원문';

COMMENT ON COLUMN public.youtube_video.published_at
    IS '영상 업로드 일시. 유튜브 API publishedAt 값';

COMMENT ON COLUMN public.youtube_video.view_count
    IS '수집 당시 영상 조회수';

COMMENT ON COLUMN public.youtube_video.like_count
    IS '수집 당시 영상 좋아요수';

COMMENT ON COLUMN public.youtube_video.comment_count
    IS '수집 당시 영상 전체 댓글수';

COMMENT ON COLUMN public.youtube_video.comment_order
    IS '댓글 수집 정렬 기준. relevance=인기순, time=최신순';

COMMENT ON COLUMN public.youtube_video.collected_at
    IS '영상 정보를 수집한 로컬 시간. YYYY-MM-DD HH24:MI:SS';

COMMENT ON COLUMN public.youtube_video.raw_json
    IS '유튜브 영상 API 원본 응답 JSON 저장용';

COMMENT ON COLUMN public.youtube_video.create_dt
    IS 'DB 최초 생성일시. YYYY-MM-DD HH24:MI:SS';

COMMENT ON COLUMN public.youtube_video.update_dt
    IS 'DB 최종 수정일시. YYYY-MM-DD HH24:MI:SS';


-- ============================================================
-- 1-2. 유튜브 영상 테이블 인덱스
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_youtube_video_channel_id
    ON public.youtube_video USING btree
    (channel_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_video_published_at
    ON public.youtube_video USING btree
    (published_at DESC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_video_collected_at
    ON public.youtube_video USING btree
    (collected_at COLLATE pg_catalog."default" DESC NULLS LAST)
    TABLESPACE pg_default;

-- ============================================================
-- 3. 확인용 SELECT
-- ============================================================

SELECT COUNT(*) AS video_count FROM public.youtube_video;

SELECT *
FROM public.youtube_video
ORDER BY collected_at DESC
LIMIT 10;


DELETE FROM public.youtube_video
WHERE video_id = '021SZCV8ZFI';

