-- ============================================================
-- YouTube 댓글 분석 GLOBAL STOPWORD Seed SQL
-- ============================================================
--
-- 목적:
-- - 모든 영상에 공통 적용할 기본 불용어(STOPWORD)를 등록한다.
-- - youtube_token_dictionary 테이블에 dict_type='STOPWORD'로 저장한다.
-- - 여러 번 실행해도 중복 에러가 나지 않도록 ON CONFLICT ... DO UPDATE SET을 사용한다.
--
-- 전제:
-- - public.youtube_token_dictionary 테이블이 이미 생성되어 있어야 한다.
-- - UNIQUE(scope_key, dict_type, source_text) 제약이 있어야 한다.
--
-- 적용 범위:
-- - scope_type = 'GLOBAL'
-- - scope_key  = 'GLOBAL'
-- - video_id   = NULL
--
-- 사용 방식:
-- 1) 이 SQL을 먼저 실행한다.
-- 2) 01_youtube_tokenize_kiwi_to_pg.py 실행 시 DB에서 GLOBAL STOPWORD를 읽어 적용한다.
-- 3) 분석 결과 TOP token을 보고 필요하면 이 파일에 단어를 추가한다.
-- 4) 다시 이 SQL 실행 후 TOKENIZE를 재실행한다.
--
-- 주의:
-- - 불용어를 너무 많이 넣으면 중요한 단어까지 빠질 수 있다.
-- - 처음에는 GLOBAL 기본 불용어를 쓰고, 특정 영상에서만 제외할 단어는 VIDEO STOPWORD로 별도 등록하는 것을 권장한다.
-- ============================================================

INSERT INTO public.youtube_token_dictionary
(
    scope_type,
    scope_key,
    video_id,
    dict_type,
    source_text,
    target_text,
    pos,
    description,
    use_yn,
    create_dt,
    update_dt
)
VALUES
-- ============================================================
-- 1. 웃음 / 감탄 / 반응 표현
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅋㅋ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅋㅋㅋ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅋㅋㅋㅋ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅎㅎ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅎㅎㅎ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅎㅎㅎㅎ', NULL, NULL, 'GLOBAL 기본 불용어 - 웃음 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅠㅠ', NULL, NULL, 'GLOBAL 기본 불용어 - 감정 기호', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅠㅠㅠ', NULL, NULL, 'GLOBAL 기본 불용어 - 감정 기호', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅜㅜ', NULL, NULL, 'GLOBAL 기본 불용어 - 감정 기호', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', 'ㅜㅜㅜ', NULL, NULL, 'GLOBAL 기본 불용어 - 감정 기호', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '아', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '어', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '오', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '와', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '헐', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '음', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '흠', NULL, NULL, 'GLOBAL 기본 불용어 - 감탄사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '네', NULL, NULL, 'GLOBAL 기본 불용어 - 짧은 반응', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '예', NULL, NULL, 'GLOBAL 기본 불용어 - 짧은 반응', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '아니', NULL, NULL, 'GLOBAL 기본 불용어 - 짧은 반응', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),

-- ============================================================
-- 2. 지시어 / 대명사 / 의문사
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '이거', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '저거', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '그거', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '이것', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '저것', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '그것', NULL, NULL, 'GLOBAL 기본 불용어 - 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '여기', NULL, NULL, 'GLOBAL 기본 불용어 - 장소 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '저기', NULL, NULL, 'GLOBAL 기본 불용어 - 장소 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '거기', NULL, NULL, 'GLOBAL 기본 불용어 - 장소 지시어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '이런', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 관형 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '저런', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 관형 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '그런', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 관형 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '이렇게', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 부사 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '저렇게', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 부사 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '그렇게', NULL, NULL, 'GLOBAL 기본 불용어 - 지시 부사 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '뭐', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '무엇', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '누구', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '어디', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '언제', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '어떻게', NULL, NULL, 'GLOBAL 기본 불용어 - 의문 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),

-- ============================================================
-- 3. 의미 약한 일반 명사
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '것', NULL, NULL, 'GLOBAL 기본 불용어 - 의존/일반 명사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '거', NULL, NULL, 'GLOBAL 기본 불용어 - 의존/일반 명사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '수', NULL, NULL, 'GLOBAL 기본 불용어 - 의존/일반 명사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '때', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '말', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '일', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '점', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '개', NULL, NULL, 'GLOBAL 기본 불용어 - 단위성 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '명', NULL, NULL, 'GLOBAL 기본 불용어 - 단위성 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '번', NULL, NULL, 'GLOBAL 기본 불용어 - 단위성 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '중', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '듯', NULL, NULL, 'GLOBAL 기본 불용어 - 추측 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '정도', NULL, NULL, 'GLOBAL 기본 불용어 - 정도 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '부분', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '관련', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '내용', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '상황', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '경우', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '사람', NULL, NULL, 'GLOBAL 기본 불용어 - 일반어. 분석 목적에 따라 VIDEO 사전에서 별도 조정 가능', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '분', NULL, NULL, 'GLOBAL 기본 불용어 - 일반/존칭 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '쪽', NULL, NULL, 'GLOBAL 기본 불용어 - 방향/일반어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),

-- ============================================================
-- 4. 강조어 / 부사성 표현
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '진짜', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '정말', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '너무', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '매우', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '완전', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '엄청', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '되게', NULL, NULL, 'GLOBAL 기본 불용어 - 강조어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '그냥', NULL, NULL, 'GLOBAL 기본 불용어 - 의미 약한 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '좀', NULL, NULL, 'GLOBAL 기본 불용어 - 정도 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '조금', NULL, NULL, 'GLOBAL 기본 불용어 - 정도 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '많이', NULL, NULL, 'GLOBAL 기본 불용어 - 정도 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '계속', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '항상', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '다시', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '이미', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '바로', NULL, NULL, 'GLOBAL 기본 불용어 - 시간 부사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '제발', NULL, NULL, 'GLOBAL 기본 불용어 - 요청 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '아마', NULL, NULL, 'GLOBAL 기본 불용어 - 추측 표현', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),

-- ============================================================
-- 5. 흔한 용언 기본형 후보
--    현재 TOKEN_POS_LIST=NNG,NNP이면 대부분 저장되지 않는다.
--    나중에 VV, VA, XR까지 확장할 때를 대비한 기본 후보이다.
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '하다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '되다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '있다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '없다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '같다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '보다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '가다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '오다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '주다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '받다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '알다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '모르다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '싶다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '나다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '들다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 용언', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '좋다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 형용사. 감정 분석에서는 제외하지 않을 수도 있음', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '나쁘다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 형용사. 감정 분석에서는 제외하지 않을 수도 있음', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '크다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 형용사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '작다', NULL, NULL, 'GLOBAL 기본 불용어 - 흔한 형용사', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),

-- ============================================================
-- 6. 유튜브 플랫폼 공통어
--    영상 자체 평가를 분석할 때는 일부 단어를 use_yn='N'으로 바꿔도 된다.
-- ============================================================
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '영상', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '댓글', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '유튜브', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '채널', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '구독', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '좋아요', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '싫어요', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '조회수', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '추천', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '알고리즘', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '업로드', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '라이브', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
('GLOBAL', 'GLOBAL', NULL, 'STOPWORD', '방송', NULL, NULL, 'GLOBAL 기본 불용어 - 유튜브 플랫폼 공통어', 'Y', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'), TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'))
ON CONFLICT
(
    scope_key,
    dict_type,
    source_text
)
DO UPDATE SET
    scope_type = EXCLUDED.scope_type,
    video_id = EXCLUDED.video_id,
    target_text = EXCLUDED.target_text,
    pos = EXCLUDED.pos,
    description = EXCLUDED.description,
    use_yn = EXCLUDED.use_yn,
    update_dt = EXCLUDED.update_dt;


-- ============================================================
-- 등록 확인용 조회
-- ============================================================
-- SELECT
--     dict_type,
--     scope_type,
--     COUNT(*) AS cnt
-- FROM public.youtube_token_dictionary
-- WHERE scope_key = 'GLOBAL'
-- GROUP BY dict_type, scope_type
-- ORDER BY dict_type, scope_type;
--
-- SELECT
--     source_text,
--     description,
--     use_yn
-- FROM public.youtube_token_dictionary
-- WHERE scope_key = 'GLOBAL'
--   AND dict_type = 'STOPWORD'
-- ORDER BY source_text;
-- ============================================================
