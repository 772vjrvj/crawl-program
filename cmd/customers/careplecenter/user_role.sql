START TRANSACTION;

SET @user_role_no = (
    SELECT COALESCE(
                   MAX(CAST(SUBSTRING(USER_ROLE_ID, 10) AS UNSIGNED)),
                   0
           )
    FROM `USER_ROLE`
    WHERE USER_ROLE_ID LIKE 'USER_ROLE%'
);

INSERT INTO `USER_ROLE`
(
    USER_ROLE_ID,
    USER_ID,
    ROLE_ID,
    CREATE_DT,
    UPDATE_DT,
    DELETE_YN
)
SELECT
    CONCAT(
            'USER_ROLE',
            LPAD(@user_role_no := @user_role_no + 1, 8, '0')
    ),
    u.USER_ID,
    r.ROLE_ID,
    COALESCE(u.CREATE_DT, DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s')),
    NULL,
    'N'
FROM `USER` u
         JOIN `ROLE_MASTER` r
              ON r.ROLE_CD =
                 CASE
                     WHEN u.USER_NM IN
                          (
                           '권하영',
                           '김형익',
                           '박병준',
                           '신예은',
                           '이은영',
                           '전혜리',
                           '조민석'
                              )
                         THEN 'ROLE_ADMIN'

                     WHEN u.USER_TYPE_CD = 'MEMBER'
                         THEN 'ROLE_MEMBER'

                     ELSE 'ROLE_TEACHER'
                     END
WHERE NOT EXISTS
          (
              SELECT 1
              FROM `USER_ROLE` ur
              WHERE ur.USER_ID = u.USER_ID
                AND ur.ROLE_ID = r.ROLE_ID
                AND COALESCE(ur.DELETE_YN, 'N') = 'N'
          )
ORDER BY u.USER_ID;

COMMIT;