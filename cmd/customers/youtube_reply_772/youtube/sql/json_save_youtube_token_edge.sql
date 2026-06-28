COPY (
    SELECT COALESCE(
        jsonb_agg(to_jsonb(t) ORDER BY t.edge_id),
        '[]'::jsonb
    )::text
    FROM (
        SELECT
            edge_id,
            run_id,
            method_id,
            video_id,
            source_token,
            target_token,
            source_pos,
            target_pos,
            edge_type,
            weight,
            comment_count,
            create_dt,
            update_dt
        FROM public.youtube_token_edge
        WHERE video_id = 'D_axHX2HaW8'
    ) t
)
    TO 'E:/git/crawl-program/output/youtube_token_edge.json'
WITH (FORMAT text, ENCODING 'UTF8');