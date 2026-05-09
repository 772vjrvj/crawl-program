-- ============================================================
-- YouTube 댓글 원본 테이블
-- 파일명: youtube_comment.sql
-- ============================================================
--
-- 전제:
-- - public.youtube_video 테이블은 이미 존재해야 한다.
-- - youtube_comment.video_id 는 youtube_video.video_id 를 참조한다.
--
-- 댓글 구분 기준:
-- - 원댓글: parent_comment_id IS NULL
-- - 대댓글: parent_comment_id IS NOT NULL
-- ============================================================


-- ============================================================
-- 0. 기존 댓글 테이블 삭제가 필요할 때만 주석 해제
-- ============================================================

-- DROP TABLE IF EXISTS public.youtube_comment;


-- ============================================================
-- 1. 유튜브 댓글 테이블 생성
-- ============================================================

CREATE TABLE IF NOT EXISTS public.youtube_comment
(
    comment_id character varying(150) COLLATE pg_catalog."default" NOT NULL,
    video_id character varying(50) COLLATE pg_catalog."default" NOT NULL,

    parent_comment_id character varying(150) COLLATE pg_catalog."default",

    top_comment_no integer DEFAULT 0,
    reply_no integer DEFAULT 0,
    sort_no character varying(50) COLLATE pg_catalog."default",

    author_name character varying(300) COLLATE pg_catalog."default",
    author_channel_id character varying(150) COLLATE pg_catalog."default",
    author_channel_url text COLLATE pg_catalog."default",
    author_profile_image text COLLATE pg_catalog."default",

    comment_text text COLLATE pg_catalog."default",

    like_count integer DEFAULT 0,
    reply_count integer DEFAULT 0,

    published_at timestamp with time zone,
    updated_at timestamp with time zone,

    can_rate character varying(20) COLLATE pg_catalog."default",
    viewer_rating character varying(50) COLLATE pg_catalog."default",
    is_public character varying(20) COLLATE pg_catalog."default",
    can_reply character varying(20) COLLATE pg_catalog."default",

    raw_json jsonb,

    create_dt character varying(19) COLLATE pg_catalog."default",
    update_dt character varying(19) COLLATE pg_catalog."default",

    CONSTRAINT youtube_comment_pkey PRIMARY KEY (comment_id),

    CONSTRAINT fk_youtube_comment_video FOREIGN KEY (video_id)
        REFERENCES public.youtube_video (video_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

    TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.youtube_comment
    OWNER to postgres;


-- ============================================================
-- 2. 테이블 / 컬럼 설명
-- ============================================================

COMMENT ON TABLE public.youtube_comment
    IS '유튜브 댓글 원본 테이블. 원댓글과 대댓글을 모두 저장한다. 분석 결과가 아니라 수집 원본 기준 데이터다.';

COMMENT ON COLUMN public.youtube_comment.comment_id
    IS '유튜브 댓글 ID. 원댓글/대댓글 모두 고유 ID';

COMMENT ON COLUMN public.youtube_comment.video_id
    IS '댓글이 달린 유튜브 영상 ID';

COMMENT ON COLUMN public.youtube_comment.parent_comment_id
    IS '부모 댓글 ID. 원댓글이면 NULL, 대댓글이면 원댓글 comment_id';

COMMENT ON COLUMN public.youtube_comment.top_comment_no
    IS '수집 순서 기준 원댓글 번호. 예: 1, 2, 3';

COMMENT ON COLUMN public.youtube_comment.reply_no
    IS '대댓글 번호. 원댓글이면 0, 대댓글이면 1부터 증가';

COMMENT ON COLUMN public.youtube_comment.sort_no
    IS '화면 표시용 정렬번호. 예: 원댓글 3, 대댓글 3-2';

COMMENT ON COLUMN public.youtube_comment.author_name
    IS '작성자 표시명. 외부 공개 화면에서는 익명화 권장';

COMMENT ON COLUMN public.youtube_comment.author_channel_id
    IS '작성자 채널 ID';

COMMENT ON COLUMN public.youtube_comment.author_channel_url
    IS '작성자 채널 URL';

COMMENT ON COLUMN public.youtube_comment.author_profile_image
    IS '작성자 프로필 이미지 URL';

COMMENT ON COLUMN public.youtube_comment.comment_text
    IS '댓글 내용. 화면 표시/분석에 사용할 텍스트';

COMMENT ON COLUMN public.youtube_comment.like_count
    IS '댓글 좋아요수. 수집 당시 값';

COMMENT ON COLUMN public.youtube_comment.reply_count
    IS '대댓글 수. 원댓글 기준 totalReplyCount 값. 대댓글은 0';

COMMENT ON COLUMN public.youtube_comment.published_at
    IS '댓글 작성일시';

COMMENT ON COLUMN public.youtube_comment.updated_at
    IS '댓글 수정일시';

COMMENT ON COLUMN public.youtube_comment.can_rate
    IS '평가 가능 여부. 유튜브 API canRate 값';

COMMENT ON COLUMN public.youtube_comment.viewer_rating
    IS '내 평가 상태. 보통 none';

COMMENT ON COLUMN public.youtube_comment.is_public
    IS '댓글 스레드 공개 여부. 원댓글 스레드 기준 값';

COMMENT ON COLUMN public.youtube_comment.can_reply
    IS '답글 가능 여부. 원댓글 스레드 기준 값';

COMMENT ON COLUMN public.youtube_comment.raw_json
    IS '유튜브 댓글 API 원본 JSON 저장용';

COMMENT ON COLUMN public.youtube_comment.create_dt
    IS 'DB 최초 생성일시. YYYY-MM-DD HH24:MI:SS';

COMMENT ON COLUMN public.youtube_comment.update_dt
    IS 'DB 최종 수정일시. YYYY-MM-DD HH24:MI:SS';


-- ============================================================
-- 3. 인덱스
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_youtube_comment_video_id
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_parent
    ON public.youtube_comment USING btree
    (parent_comment_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_video_parent
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST, parent_comment_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_sort
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST, top_comment_no ASC NULLS LAST, reply_no ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_like
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST, like_count DESC NULLS FIRST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_reply
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST, reply_count DESC NULLS FIRST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_youtube_comment_published
    ON public.youtube_comment USING btree
    (video_id COLLATE pg_catalog."default" ASC NULLS LAST, published_at ASC NULLS LAST)
    TABLESPACE pg_default;


-- ============================================================
-- 4. 확인용 SELECT
-- ============================================================

-- 원댓글 조회
-- SELECT *
-- FROM public.youtube_comment
-- WHERE video_id = '021SZCV8ZFI'
--   AND parent_comment_id IS NULL
-- ORDER BY top_comment_no ASC;

-- 대댓글 조회
-- SELECT *
-- FROM public.youtube_comment
-- WHERE video_id = '여기에_영상_ID'
--   AND parent_comment_id IS NOT NULL
-- ORDER BY top_comment_no ASC, reply_no ASC;

-- 원댓글 + 대댓글 전체 순서 조회
SELECT *
FROM public.youtube_comment
WHERE video_id = '021SZCV8ZFI'
ORDER BY top_comment_no ASC, reply_no ASC;



SELECT
    -- video_id,
    top_comment_no,
    reply_no,
    sort_no,
    CASE
        WHEN parent_comment_id IS NULL THEN '원댓글'
        ELSE '대댓글'
    END AS comment_type,
    -- comment_id,
    parent_comment_id,
    author_name,
    comment_text,
    like_count,
    reply_count,
    published_at,
    updated_at
FROM public.youtube_comment
WHERE video_id = '021SZCV8ZFI'
ORDER BY top_comment_no ASC, reply_no ASC;




-- 댓글 수 확인
SELECT COUNT(*) AS comment_count
FROM public.youtube_comment
WHERE video_id = '021SZCV8ZFI';

-- 데이터 삭제
-- DELETE FROM public.youtube_comment
-- WHERE video_id = '021SZCV8ZFI';

