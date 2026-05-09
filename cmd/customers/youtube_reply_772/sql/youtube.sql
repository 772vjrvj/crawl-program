

DELETE FROM public.youtube_video
WHERE video_id = '021SZCV8ZFI';

-- 데이터 삭제
DELETE FROM public.youtube_comment
WHERE video_id = '021SZCV8ZFI';




INSERT INTO public.youtube_analysis_method
(
    method_id,
    method_type,
    method_name,
    provider,
    model_name,
    model_version,
    worker_name,
    description,
    option_json,
    use_yn,
    create_dt,
    update_dt
)
VALUES
    (
        'MORPH_KIWI_V1',
        'MORPH',
        'KIWI 형태소 분석 V1',
        'kiwipiepy',
        'kiwi',
        'v1',
        NULL,
        '한국어 댓글 형태소 분석, token 빈도, TF-IDF, 동시출현 네트워크 기본 분석 방식',
        '{"pos_list": ["NNG", "NNP"], "min_token_len": 2, "tfidf": "smooth_idf", "edge_type": "CO_OCCURRENCE"}'::jsonb,
        'Y',
        TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
        TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
ON CONFLICT (method_id)
DO UPDATE SET
    method_type = EXCLUDED.method_type,
    method_name = EXCLUDED.method_name,
    provider = EXCLUDED.provider,
    model_name = EXCLUDED.model_name,
    model_version = EXCLUDED.model_version,
    worker_name = EXCLUDED.worker_name,
    description = EXCLUDED.description,
    option_json = EXCLUDED.option_json,
    use_yn = EXCLUDED.use_yn,
    update_dt = EXCLUDED.update_dt;
