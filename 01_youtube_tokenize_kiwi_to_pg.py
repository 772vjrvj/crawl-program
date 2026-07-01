import os
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime
from collections import Counter

import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv
from kiwipiepy import Kiwi


# ============================================================
# YouTube 댓글 형태소/token 분석 -> PostgreSQL 저장
# ============================================================
#
# 목적:
# 1) 기존 youtube_collect.py로 수집된 public.youtube_comment 데이터를 조회한다.
# 2) DB의 youtube_token_dictionary 사전을 읽는다.
#    - STOPWORD  : 분석 제외 단어
#    - USER_WORD : Kiwi 사용자 단어
#    - NORMALIZE : 표현 통일 단어
# 3) kiwipiepy(Kiwi)로 댓글을 형태소 분석한다.
# 4) 명사/고유명사 등 설정한 품사만 token으로 추출한다.
# 5) 정규화/불용어 처리를 한 뒤 public.youtube_comment_token에 저장한다.
# 6) public.youtube_analysis_run에 TOKENIZE 실행 이력을 남긴다.
#
# 전제:
# - youtube_collect.py를 먼저 실행해서 youtube_video, youtube_comment에 데이터가 있어야 한다.
# - youtube_analysis_method에는 ANALYSIS_METHOD_ID 값이 미리 등록되어 있어야 한다.
# - youtube_token_dictionary 테이블은 없어도 동작은 가능하지만, 있으면 사전을 적용한다.
#
# 설치:
# pip install psycopg2-binary python-dotenv kiwipiepy
#
# 실행:
# python 01_youtube_tokenize_kiwi_to_pg.py
#
# ============================================================


# ============================================================
# 1. 공통 유틸 함수
# ============================================================

def base_dir():
    """
    현재 py 또는 exe가 있는 폴더를 반환한다.

    기존 youtube_collect.py와 같은 방식이다.
    .env 파일을 py 파일 옆에 두면 개발/배포 모두 동일하게 동작한다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


def now_str():
    """
    DB의 create_dt, update_dt, started_at, ended_at에 넣을 문자열 시간.
    기존 프로젝트 기준에 맞춰 YYYY-MM-DD HH:MI:SS 형식으로 저장한다.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_text(value):
    """
    None 값을 빈 문자열로 바꾼다.
    형태소 분석/문자 비교에서 None 오류를 막기 위한 함수다.
    """
    if value is None:
        return ""
    return str(value)


def safe_int(value):
    """
    숫자 변환 유틸.
    None, 빈값, 변환 실패는 0으로 처리한다.
    """
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def get_yn(value):
    """
    .env의 Y/N 값을 boolean으로 변환한다.
    Y, YES, TRUE, 1 이면 True.
    """
    value = safe_text(value).strip().upper()
    return value in ["Y", "YES", "TRUE", "1"]


def get_video_id(value):
    """
    YouTube 영상 ID 또는 URL에서 영상 ID만 추출한다.

    입력 예:
    - 021SZCV8ZFI
    - https://www.youtube.com/watch?v=021SZCV8ZFI
    - https://youtu.be/021SZCV8ZFI
    - https://www.youtube.com/shorts/021SZCV8ZFI
    """
    value = safe_text(value).strip()

    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?&]+)",
        r"shorts/([^?&]+)",
        r"embed/([^?&]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)

    return value


def normalize_basic(value):
    """
    아주 기본적인 token 정리 함수.

    여기서는 과하게 손대지 않고 아래 정도만 처리한다.
    - 앞뒤 공백 제거
    - 영어 소문자 통일

    실제 표현 통일은 youtube_token_dictionary의 NORMALIZE 사전으로 처리한다.
    """
    value = safe_text(value).strip()
    value = value.lower()
    return value


# ============================================================
# 2. .env 설정 읽기
# ============================================================

def load_config():
    """
    .env에서 분석 설정과 DB 설정을 읽는다.

    기존 수집 .env와 같은 파일을 사용한다.
    ANALYZE_VIDEO_CODE가 있으면 우선 사용하고,
    없으면 YOUTUBE_VIDEO_CODE / YOUTUBE_VIDEO_URL을 사용한다.
    """
    env_path = base_dir() / ".env"
    load_dotenv(env_path)

    video_raw = os.getenv("ANALYZE_VIDEO_CODE", "").strip()

    if not video_raw:
        video_raw = os.getenv("YOUTUBE_VIDEO_CODE", "").strip()

    if not video_raw:
        video_raw = os.getenv("YOUTUBE_VIDEO_URL", "").strip()

    pos_raw = os.getenv("TOKEN_POS_LIST", "NNG,NNP").strip()

    pos_list = []
    for item in pos_raw.split(","):
        item = item.strip()
        if item:
            pos_list.append(item)

    return {
        # 분석 대상 영상 ID
        "video_id": get_video_id(video_raw),

        # 분석 방식 ID
        # youtube_analysis_method.method_id에 미리 등록되어 있어야 한다.
        "method_id": os.getenv("ANALYSIS_METHOD_ID", "MORPH_KIWI_V1").strip(),

        # Y = 원댓글 + 대댓글 분석
        # N = 원댓글만 분석
        "include_replies": get_yn(os.getenv("ANALYZE_REPLIES", "Y")),

        # token으로 인정할 최소 글자 수
        # 예: 2이면 한 글자 token은 제외
        "min_token_len": int(os.getenv("MIN_TOKEN_LEN", "2")),

        # 추출할 품사 목록
        # 추천 기본값: NNG,NNP
        "pos_list": pos_list,

        # Y이면 같은 video_id + method_id + TOKENIZE 기존 실행 이력을 삭제하고 다시 저장한다.
        # 삭제 시 youtube_comment_token은 FK ON DELETE CASCADE 기준으로 같이 삭제되는 구조를 권장한다.
        "reset_yn": get_yn(os.getenv("ANALYSIS_RESET_YN", "Y")),

        # 테스트용 제한
        # 0이면 전체 댓글 분석
        "max_comments": int(os.getenv("ANALYZE_MAX_COMMENTS", "0")),

        # PostgreSQL DB 접속 정보
        "db_host": os.getenv("DB_HOST", ""),
        "db_port": int(os.getenv("DB_PORT", "")),
        "db_name": os.getenv("DB_NAME", ""),
        "db_user": os.getenv("DB_USER", ""),
        "db_password": os.getenv("DB_PASSWORD", "")
    }


def get_conn(cfg):
    """
    PostgreSQL 연결 객체를 생성한다.
    기존 youtube_collect.py와 같은 DB 설정을 사용한다.
    """
    return psycopg2.connect(
        host=cfg["db_host"],
        port=cfg["db_port"],
        dbname=cfg["db_name"],
        user=cfg["db_user"],
        password=cfg["db_password"]
    )


# ============================================================
# 3. 분석 method / run 처리
# ============================================================

def check_analysis_method(conn, method_id):
    """
    youtube_analysis_method에 method_id가 등록되어 있는지 확인한다.

    사용자가 이미 youtube_analysis_method에 방식을 하나 넣었다고 했으므로,
    여기서는 자동 INSERT 하지 않고 존재 여부만 확인한다.
    """
    sql = """
        SELECT COUNT(*)
        FROM public.youtube_analysis_method
        WHERE method_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (method_id,))
        count = cur.fetchone()[0]

    if count <= 0:
        raise Exception(
            "youtube_analysis_method에 method_id가 없습니다. "
            + "먼저 등록하세요. method_id="
            + method_id
        )


def delete_previous_tokenize_runs(conn, cfg):
    """
    기존 TOKENIZE 실행 이력을 삭제한다.

    기준:
    - 같은 video_id
    - 같은 method_id
    - analysis_task = TOKENIZE

    주의:
    - youtube_comment_token이 run_id FK ON DELETE CASCADE로 잡혀 있으면
      run 삭제 시 token 결과도 같이 삭제된다.
    - TFIDF/NETWORK는 별도 py에서 다시 실행하는 것을 권장한다.
    """
    sql = """
        DELETE FROM public.youtube_analysis_run
        WHERE video_id = %s
          AND method_id = %s
          AND analysis_task = 'TOKENIZE'
    """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))


def create_analysis_run(conn, cfg):
    """
    TOKENIZE 실행 이력을 youtube_analysis_run에 생성한다.

    result_count는 분석 완료 후 update_run_success에서 저장한다.
    """
    run_id = str(uuid.uuid4())
    now = now_str()

    sql = """
        INSERT INTO public.youtube_analysis_run
        (
            run_id,
            video_id,
            method_id,
            analysis_task,
            include_reply_yn,
            status,
            config_json,
            total_comment_count,
            result_count,
            started_at,
            create_dt,
            update_dt
        )
        VALUES
        (
            %(run_id)s,
            %(video_id)s,
            %(method_id)s,
            'TOKENIZE',
            %(include_reply_yn)s,
            'RUNNING',
            %(config_json)s,
            0,
            0,
            %(now)s,
            %(now)s,
            %(now)s
        )
    """

    data = {
        "run_id": run_id,
        "video_id": cfg["video_id"],
        "method_id": cfg["method_id"],
        "include_reply_yn": "Y" if cfg["include_replies"] else "N",
        "config_json": Json({
            "pos_list": cfg["pos_list"],
            "min_token_len": cfg["min_token_len"],
            "include_replies": cfg["include_replies"],
            "max_comments": cfg["max_comments"]
        }),
        "now": now
    }

    with conn.cursor() as cur:
        cur.execute(sql, data)

    return run_id


def update_run_success(conn, run_id, total_comment_count, result_count):
    """
    TOKENIZE 성공 처리.

    result_count 의미:
    - youtube_comment_token에 저장한 token row 수
    """
    now = now_str()

    sql = """
        UPDATE public.youtube_analysis_run
        SET status = 'SUCCESS',
            total_comment_count = %s,
            result_count = %s,
            ended_at = %s,
            update_dt = %s
        WHERE run_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            total_comment_count,
            result_count,
            now,
            now,
            run_id
        ))


def update_run_fail(conn, run_id, error_message):
    """
    TOKENIZE 실패 처리.
    오류 메시지를 youtube_analysis_run.error_message에 저장한다.
    """
    now = now_str()

    sql = """
        UPDATE public.youtube_analysis_run
        SET status = 'FAIL',
            error_message = %s,
            ended_at = %s,
            update_dt = %s
        WHERE run_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            safe_text(error_message)[:5000],
            now,
            now,
            run_id
        ))


# ============================================================
# 4. 사전 조회
# ============================================================

def fetch_token_dictionary(conn, video_id):
    """
    youtube_token_dictionary에서 현재 영상에 적용할 사전을 조회한다.

    적용 범위:
    1) GLOBAL 공통 사전
    2) VIDEO 해당 video_id 전용 사전

    dict_type:
    - STOPWORD  : token에서 제외
    - USER_WORD : Kiwi 사용자 사전 등록
    - NORMALIZE : source_text를 target_text로 통일

    테이블이 아직 없거나 데이터가 없어도 분석은 가능해야 하므로,
    오류가 나면 빈 사전으로 처리한다.
    """
    sql = """
        SELECT
            dict_type,
            source_text,
            target_text
        FROM public.youtube_token_dictionary
        WHERE use_yn = 'Y'
          AND (
                scope_type = 'GLOBAL'
                OR (
                    scope_type = 'VIDEO'
                    AND video_id = %s
                )
          )
        ORDER BY
            CASE WHEN scope_type = 'GLOBAL' THEN 1 ELSE 2 END,
            dict_type,
            source_text
    """

    result = {
        "stopwords": set(),
        "user_words": [],
        "normalize_map": {}
    }

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (video_id,))
            rows = cur.fetchall()

        for row in rows:
            dict_type = safe_text(row[0]).strip().upper()
            source_text = normalize_basic(row[1])
            target_text = normalize_basic(row[2])

            if not source_text:
                continue

            if dict_type == "STOPWORD":
                result["stopwords"].add(source_text)

            elif dict_type == "USER_WORD":
                # 사용자 사전은 원문 단어 기준이 중요하므로 source_text를 넣는다.
                result["user_words"].append(source_text)

            elif dict_type == "NORMALIZE":
                if target_text:
                    result["normalize_map"][source_text] = target_text

    except Exception as e:
        print("[사전 조회 경고]", str(e))
        print("[사전 조회 경고] youtube_token_dictionary 없이 기본 분석을 진행합니다.")

    return result


def add_user_words_to_kiwi(kiwi, user_words):
    """
    USER_WORD 사전을 Kiwi에 등록한다.

    목적:
    - 형태소 분석기가 고유명사/신조어/정당명/사람명 등을 잘못 쪼개는 것을 줄인다.

    예:
    - 국민의힘
    - 더불어민주당
    - 한동훈
    - 이재명

    Kiwi.add_user_word(word, tag='NNP') 형식으로 등록한다.
    """
    added = 0

    for word in user_words:
        word = safe_text(word).strip()

        if not word:
            continue

        try:
            kiwi.add_user_word(word, tag="NNP")
            added += 1
        except Exception:
            # 같은 단어가 중복 등록되거나 분석기 내부에서 거부되는 경우가 있을 수 있다.
            # 전체 분석이 중단되지 않도록 무시한다.
            pass

    return added


# ============================================================
# 5. 댓글 조회
# ============================================================

def fetch_comments(conn, cfg):
    """
    youtube_comment에서 분석 대상 댓글을 조회한다.

    include_replies = Y:
        원댓글 + 대댓글 전체 분석

    include_replies = N:
        원댓글만 분석

    max_comments:
        테스트용 제한.
        0이면 전체 조회.
    """
    params = [cfg["video_id"]]

    if cfg["include_replies"]:
        sql = """
            SELECT
                comment_id,
                video_id,
                parent_comment_id,
                comment_text,
                top_comment_no,
                reply_no,
                sort_no
            FROM public.youtube_comment
            WHERE video_id = %s
            ORDER BY top_comment_no ASC, reply_no ASC
        """
    else:
        sql = """
            SELECT
                comment_id,
                video_id,
                parent_comment_id,
                comment_text,
                top_comment_no,
                reply_no,
                sort_no
            FROM public.youtube_comment
            WHERE video_id = %s
              AND parent_comment_id IS NULL
            ORDER BY top_comment_no ASC, reply_no ASC
        """

    if cfg["max_comments"] > 0:
        sql += " LIMIT %s"
        params.append(cfg["max_comments"])

    rows = []

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))

        for row in cur.fetchall():
            rows.append({
                "comment_id": row[0],
                "video_id": row[1],
                "parent_comment_id": row[2],
                "comment_text": row[3],
                "top_comment_no": row[4],
                "reply_no": row[5],
                "sort_no": row[6]
            })

    return rows


# ============================================================
# 6. 형태소/token 분석
# ============================================================

def analyze_comment(kiwi, comment, cfg, dictionary):
    """
    댓글 1개를 형태소 분석해서 youtube_comment_token에 넣을 row 목록을 만든다.

    처리 순서:
    1) 댓글 원문 가져오기
    2) Kiwi 형태소 분석
    3) TOKEN_POS_LIST에 포함된 품사만 남김
    4) token 정규화
    5) NORMALIZE 사전 적용
    6) MIN_TOKEN_LEN 미만 제외
    7) STOPWORD 제외
    8) 댓글 안 token 빈도 계산
    """
    text = safe_text(comment.get("comment_text")).strip()

    if not text:
        return []

    # Kiwi 형태소 분석 실행
    tokens = kiwi.tokenize(text)

    token_counter = Counter()
    token_text_map = {}
    pos_map = {}
    first_order_map = {}

    order_no = 0

    for token in tokens:
        token_text = safe_text(token.form).strip()
        pos = safe_text(token.tag).strip()

        # 설정한 품사만 분석에 사용한다.
        # 예: NNG, NNP
        if pos not in cfg["pos_list"]:
            continue

        token_norm = normalize_basic(token_text)

        # NORMALIZE 사전 적용
        # 예: 국힘 -> 국민의힘
        if token_norm in dictionary["normalize_map"]:
            token_norm = dictionary["normalize_map"][token_norm]

        # 너무 짧은 token 제외
        if len(token_norm) < cfg["min_token_len"]:
            continue

        # STOPWORD 불용어 제외
        if token_norm in dictionary["stopwords"]:
            continue

        order_no += 1

        # 같은 댓글 안에서 같은 token_norm + pos는 1 row로 합친다.
        key = (token_norm, pos)

        token_counter[key] += 1

        if key not in first_order_map:
            first_order_map[key] = order_no
            token_text_map[key] = token_text
            pos_map[key] = pos

    result = []

    parent_comment_id = comment.get("parent_comment_id")

    if parent_comment_id:
        comment_kind = "REPLY"
    else:
        comment_kind = "TOP"

    for key, count in token_counter.items():
        token_norm, pos = key

        result.append({
            "video_id": comment.get("video_id"),
            "comment_id": comment.get("comment_id"),
            "parent_comment_id": parent_comment_id,
            "comment_kind": comment_kind,
            "token_text": token_text_map.get(key, token_norm),
            "token_norm": token_norm,
            "pos": pos_map.get(key, pos),
            "token_type": "MORPHEME",
            "token_count": count,
            "first_token_order": first_order_map.get(key, 0),
            "token_len": len(token_norm)
        })

    return result


def build_token_rows(comments, cfg, dictionary):
    """
    전체 댓글 목록을 순회하면서 token row 목록을 만든다.
    """
    kiwi = Kiwi()

    added_count = add_user_words_to_kiwi(kiwi, dictionary["user_words"])

    print("[USER_WORD 등록 수]", added_count)
    print("[STOPWORD 수]", len(dictionary["stopwords"]))
    print("[NORMALIZE 수]", len(dictionary["normalize_map"]))

    all_rows = []

    for idx, comment in enumerate(comments, start=1):
        rows = analyze_comment(kiwi, comment, cfg, dictionary)
        all_rows.extend(rows)

        if idx % 100 == 0:
            print("[형태소 분석중]", idx, "/", len(comments), "token rows:", len(all_rows))

    return all_rows


# ============================================================
# 7. token DB 저장
# ============================================================

def insert_token_rows(conn, run_id, cfg, rows):
    """
    youtube_comment_token에 형태소/token 결과를 저장한다.

    저장 단위:
    - 댓글 1개 + token_norm + pos + token_type 기준으로 1 row

    예:
    댓글 A에 '경제'가 2번 나오면:
    - comment_id = A
    - token_norm = 경제
    - token_count = 2
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO public.youtube_comment_token
        (
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
        )
        VALUES %s
        ON CONFLICT
        (
            run_id,
            comment_id,
            token_norm,
            pos,
            token_type
        )
        DO UPDATE SET
            parent_comment_id = EXCLUDED.parent_comment_id,
            comment_kind = EXCLUDED.comment_kind,
            token_text = EXCLUDED.token_text,
            token_count = EXCLUDED.token_count,
            first_token_order = EXCLUDED.first_token_order,
            token_len = EXCLUDED.token_len,
            update_dt = EXCLUDED.update_dt
    """

    now = now_str()

    values = []

    for row in rows:
        values.append((
            run_id,
            cfg["method_id"],
            row.get("video_id"),
            row.get("comment_id"),
            row.get("parent_comment_id"),
            row.get("comment_kind"),
            row.get("token_text"),
            row.get("token_norm"),
            row.get("pos"),
            row.get("token_type"),
            safe_int(row.get("token_count")),
            safe_int(row.get("first_token_order")),
            safe_int(row.get("token_len")),
            now,
            now
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)

    return len(values)


# ============================================================
# 8. 실행 main
# ============================================================

def main():
    cfg = load_config()

    if not cfg["video_id"]:
        print("[중지] ANALYZE_VIDEO_CODE 또는 YOUTUBE_VIDEO_CODE를 입력하세요.")
        return

    if not cfg["method_id"]:
        print("[중지] ANALYSIS_METHOD_ID를 입력하세요.")
        return

    print("[ENV 위치]", base_dir() / ".env")
    print("[분석 작업]", "TOKENIZE")
    print("[분석 영상]", cfg["video_id"])
    print("[분석 방식]", cfg["method_id"])
    print("[대댓글 포함]", "Y" if cfg["include_replies"] else "N")
    print("[품사 목록]", cfg["pos_list"])
    print("[최소 token 길이]", cfg["min_token_len"])
    print("[기존 TOKENIZE 삭제]", "Y" if cfg["reset_yn"] else "N")
    print("[테스트 댓글 제한]", cfg["max_comments"])

    conn = get_conn(cfg)
    run_id = None

    try:
        print("")
        print("[1] 분석 방식 확인")
        check_analysis_method(conn, cfg["method_id"])
        print("[분석 방식 확인 완료]")

        if cfg["reset_yn"]:
            print("")
            print("[2] 기존 TOKENIZE 실행 이력 삭제")
            delete_previous_tokenize_runs(conn, cfg)
            print("[기존 TOKENIZE 삭제 완료]")

        print("")
        print("[3] TOKENIZE run 생성")
        run_id = create_analysis_run(conn, cfg)
        print("[run_id]", run_id)

        print("")
        print("[4] 사전 조회")
        dictionary = fetch_token_dictionary(conn, cfg["video_id"])

        print("")
        print("[5] 댓글 조회")
        comments = fetch_comments(conn, cfg)
        print("[댓글 수]", len(comments))

        if not comments:
            raise Exception("분석할 댓글이 없습니다. youtube_comment 데이터를 먼저 확인하세요.")

        print("")
        print("[6] 형태소/token 분석")
        token_rows = build_token_rows(comments, cfg, dictionary)
        print("[token rows]", len(token_rows))

        print("")
        print("[7] DB 저장")
        inserted_count = insert_token_rows(conn, run_id, cfg, token_rows)
        print("[저장 token rows]", inserted_count)

        update_run_success(
            conn,
            run_id,
            len(comments),
            inserted_count
        )

        conn.commit()

        print("")
        print("[완료]")
        print("[TOKENIZE run_id]", run_id)

    except Exception as e:
        conn.rollback()

        if run_id:
            try:
                update_run_fail(conn, run_id, str(e))
                conn.commit()
            except Exception:
                conn.rollback()

        print("[오류]", str(e))
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
