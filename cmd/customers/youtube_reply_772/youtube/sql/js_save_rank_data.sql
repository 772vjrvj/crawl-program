WITH BASE AS (
    SELECT
        S.comment_id,
        C.comment_text,
        C.author_name,
        S.sentiment_label,
        S.sentiment_score,
        S.positive_score,
        S.negative_score,
        S.neutral_score,
        S.mixed_score,
        S.confidence_score,
        S.reason_text
    FROM public.youtube_comment_sentiment S
             JOIN public.youtube_comment C
                  ON C.comment_id = S.comment_id
                      AND C.video_id = S.video_id
    WHERE S.video_id = 'D_axHX2HaW8'
),
     POS_RANK AS (
         SELECT
             'pos' AS rank_type,
             ROW_NUMBER() OVER (
                 ORDER BY
                     COALESCE(positive_score, 0) DESC,
                     COALESCE(sentiment_score, 0) DESC,
                     COALESCE(confidence_score, 0) DESC
                 ) AS rn,
             comment_text,
             author_name,
             sentiment_score,
             positive_score,
             negative_score,
             reason_text
         FROM BASE
         WHERE sentiment_label = 'POSITIVE'
     ),
     NEG_RANK AS (
         SELECT
             'neg' AS rank_type,
             ROW_NUMBER() OVER (
                 ORDER BY
                     COALESCE(negative_score, 0) DESC,
                     COALESCE(sentiment_score, 0) ASC,
                     COALESCE(confidence_score, 0) DESC
                 ) AS rn,
             comment_text,
             author_name,
             sentiment_score,
             positive_score,
             negative_score,
             reason_text
         FROM BASE
         WHERE sentiment_label = 'NEGATIVE'
     ),
     RANK_UNION AS (
         SELECT * FROM POS_RANK WHERE rn <= 5
         UNION ALL
         SELECT * FROM NEG_RANK WHERE rn <= 5
     ),
     RANK_JSON AS (
         SELECT
             rank_type,
             JSONB_AGG(
                     JSONB_BUILD_OBJECT(
                             'comment_text', comment_text,
                             'author_name', author_name,
                             'sentiment_score', sentiment_score,
                             'positive_score', positive_score,
                             'negative_score', negative_score,
                             'reason_text', reason_text
                     )
                         ORDER BY rn
             ) AS items
         FROM RANK_UNION
         GROUP BY rank_type
     ),
     FINAL_JSON AS (
         SELECT
             JSONB_BUILD_OBJECT(
                     'pos', COALESCE((SELECT items FROM RANK_JSON WHERE rank_type = 'pos'), '[]'::JSONB),
                     'neg', COALESCE((SELECT items FROM RANK_JSON WHERE rank_type = 'neg'), '[]'::JSONB)
             ) AS data
     )
SELECT
    'const rankData = ' || data::TEXT || ';' AS js_code
FROM FINAL_JSON;
