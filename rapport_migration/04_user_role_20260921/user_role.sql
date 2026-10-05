SET @seq := (
    SELECT COALESCE(
                   MAX(CAST(SUBSTRING(USER_ROLE_ID, 10) AS UNSIGNED)),
                   0
           )
    FROM USER_ROLE
);

INSERT INTO USER_ROLE (
    USER_ROLE_ID,
    USER_ID,
    ROLE_ID,
    CREATE_DT,
    UPDATE_DT,
    DELETE_YN
)
SELECT
    CONCAT('USER_ROLE', LPAD(@seq := @seq + 1, 8, '0')) AS USER_ROLE_ID,
    U.USER_ID,
    CASE
        WHEN U.USER_ID IN (
                           '171868121360645264',
                           '171869958181731834',
                           '171876200131909740',
                           '172076303875081148',
                           '172342599515949182',
                           '172523906005189656',
                           '172584498380071948',
                           '175669399852771003'
            ) THEN 'ROLE00000003'
        WHEN U.USER_TYPE_CD = 'MEMBER' THEN 'ROLE00000005'
        WHEN U.USER_TYPE_CD = 'TEACHER' THEN 'ROLE00000004'
        END AS ROLE_ID,
    DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s') AS CREATE_DT,
    NULL AS UPDATE_DT,
    'N' AS DELETE_YN
FROM `USER` U
WHERE U.USER_TYPE_CD IN ('MEMBER', 'TEACHER')
ORDER BY U.USER_ID;