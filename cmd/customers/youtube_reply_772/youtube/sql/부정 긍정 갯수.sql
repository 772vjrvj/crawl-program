/** 부정 긍정 갯수 **/
WITH SENTIMENT_COUNT AS (
    SELECT
        CASE
            WHEN SENTIMENT_LABEL IN ('NEUTRAL', 'MIXED') THEN 'NEUTRAL'
            ELSE SENTIMENT_LABEL
            END AS SENTIMENT_LABEL,
        COUNT(*) AS CNT
    FROM YOUTUBE_COMMENT_SENTIMENT
    WHERE VIDEO_ID = 'D_axHX2HaW8'
    GROUP BY
        CASE
            WHEN SENTIMENT_LABEL IN ('NEUTRAL', 'MIXED') THEN 'NEUTRAL'
            ELSE SENTIMENT_LABEL
            END
)
SELECT
    SENTIMENT_LABEL,
    CNT
FROM (
         SELECT
             SENTIMENT_LABEL,
             CNT,
             CASE SENTIMENT_LABEL
                 WHEN 'POSITIVE' THEN 1
                 WHEN 'NEUTRAL' THEN 2
                 WHEN 'NEGATIVE' THEN 3
                 ELSE 9
                 END AS SORT_NO
         FROM SENTIMENT_COUNT

         UNION ALL

         SELECT
             'TOTAL' AS SENTIMENT_LABEL,
             SUM(CNT) AS CNT,
             4 AS SORT_NO
         FROM SENTIMENT_COUNT
     ) T
ORDER BY SORT_NO;