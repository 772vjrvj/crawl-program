SELECT
    JSONB_PRETTY(
            JSONB_AGG(
                    JSONB_BUILD_OBJECT(
                            'rank_type', 'like',
                            'comment_id', comment_id,
                            'sort_no', sort_no,
                            'author_name', author_name,
                            'comment_text', comment_text,
                            'like_count', like_count,
                            'reply_count', reply_count,
                            'published_at', TO_CHAR(published_at, 'YYYY-MM-DD HH24:MI:SS')
                    )
                        ORDER BY rn
            )
    ) AS like_top5_json
FROM (
         SELECT
             ROW_NUMBER() OVER (
                 ORDER BY
                     COALESCE(like_count, 0) DESC,
                     published_at ASC
                 ) AS rn,
             comment_id,
             sort_no,
             author_name,
             comment_text,
             like_count,
             reply_count,
             published_at
         FROM public.youtube_comment
         WHERE video_id = 'D_axHX2HaW8'
         ORDER BY
             COALESCE(like_count, 0) DESC,
             published_at ASC
         LIMIT 5
     ) T;