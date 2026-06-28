COPY (
    SELECT COALESCE(
        jsonb_agg(to_jsonb(t) ORDER BY t.token_id),
        '[]'::jsonb
    )::text
    FROM (
        SELECT
            token_id,
            run_id,
            method_id,
            video_id,
            comment_id,
            parent_comment_id,
            comment_kind,
            token_text,
            token_norm,
            pos,
            token_type,
            token_count,
            first_token_order,
            token_len,
            create_dt,
            update_dt
        FROM public.youtube_comment_token
        WHERE video_id = 'D_axHX2HaW8'
    ) t
)
    TO 'E:/git/crawl-program/output/youtube_comment_token.json'
WITH (FORMAT text, ENCODING 'UTF8');