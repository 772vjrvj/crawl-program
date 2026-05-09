import os
import re
import sys
import uuid
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube 댓글 TF-IDF 계산 -> PostgreSQL 저장
# ============================================================
#
# 목적:
# 1) 01_youtube_tokenize_kiwi_to_pg.py 실행 후 저장된 youtube_comment_token을 조회한다.
# 2) 최신 TOKENIZE run_id를 자동으로 찾는다.
# 3) 댓글 1개를 document로 보고 TF-IDF를 계산한다.
# 4) 계산 결과를 public.youtube_comment_tfidf에 저장한다.
# 5) public.youtube_analysis_run에 TFIDF 실행 이력을 남긴다.
#
# 전제:
# - youtube_collect.py 실행 완료
# - 01_youtube_tokenize_kiwi_to_pg.py 실행 완료
# - youtube_comment_token에 token 데이터가 있어야 한다.
#
# TF-IDF 기준:
# - document = comment_id 1개
# - term     = token_norm
# - TF       = 댓글 안에서 token 등장 횟수
# - DF       = 전체 댓글 중 해당 token이 등장한 댓글 수
# - IDF      = log((전체 댓글 수 + 1) / (DF + 1)) + 1
# - TF-IDF   = TF * IDF
#
# 설치:
# pip install psycopg2-binary python-dotenv
#
# 실행:
# python 02_youtube_tfidf_to_pg.py
#
# ============================================================


# ============================================================
# 1. 공통 유틸 함수
# ============================================================

def base_dir():
    """
    현재 py 또는 exe가 있는 폴더를 반환한다.
    .env 파일을 py 파일 옆에 두면 그대로 읽는다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


def now_str():
    """
    DB 시간 문자열.
    기존 프로젝트 기준에 맞춰 YYYY-MM-DD HH:MI:SS 형식으로 저장한다.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_text(value):
    """
    None 값을 빈 문자열로 바꾼다.
    """
    if value is None:
        return ""
    return str(value)


def safe_int(value):
    """
    숫자 변환 유틸.
    """
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_float(value):
    """
    실수 변환 유틸.
    """
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def get_yn(value):
    """
    .env의 Y/N 값을 boolean으로 변환한다.
    """
    value = safe_text(value).strip().upper()
    return value in ["Y", "YES", "TRUE", "1"]


def get_video_id(value):
    """
    YouTube 영상 ID 또는 URL에서 영상 ID만 추출한다.
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


# ============================================================
# 2. .env 설정 읽기
# ============================================================

def load_config():
    """
    .env에서 TF-IDF 설정과 DB 설정을 읽는다.

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

    return {
        # 분석 대상 영상 ID
        "video_id": get_video_id(video_raw),

        # TOKENIZE 때 사용한 method_id
        # 현재는 형태소 분석 결과 기반 TF-IDF이므로 같은 method_id를 사용한다.
        "method_id": os.getenv("ANALYSIS_METHOD_ID", "MORPH_KIWI_V1").strip(),

        # 특정 TOKENIZE run_id를 직접 지정하고 싶을 때 사용
        # 비워두면 최신 SUCCESS TOKENIZE run을 자동 선택한다.
        "source_token_run_id": os.getenv("SOURCE_TOKEN_RUN_ID", "").strip(),

        # Y이면 같은 video_id + method_id + TFIDF 기존 실행 이력을 삭제하고 다시 저장한다.
        "reset_yn": get_yn(os.getenv("TFIDF_RESET_YN", os.getenv("ANALYSIS_RESET_YN", "Y"))),

        # DF가 너무 낮은 token을 제외하고 싶을 때 사용
        # 1이면 모든 token 계산
        "min_df": int(os.getenv("TFIDF_MIN_DF", "1")),

        # TF-IDF 점수가 너무 낮은 row를 제외하고 싶을 때 사용
        # 0이면 전부 저장
        "min_tfidf_score": float(os.getenv("TFIDF_MIN_SCORE", "0")),

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


def find_source_token_run_id(conn, cfg):
    """
    TF-IDF 계산에 사용할 TOKENIZE run_id를 찾는다.

    1) .env의 SOURCE_TOKEN_RUN_ID가 있으면 그 값을 사용한다.
    2) 없으면 같은 video_id + method_id 중 최신 SUCCESS TOKENIZE run을 사용한다.
    """
    if cfg["source_token_run_id"]:
        return cfg["source_token_run_id"]

    sql = """
        SELECT run_id
        FROM public.youtube_analysis_run
        WHERE video_id = %s
          AND method_id = %s
          AND analysis_task = 'TOKENIZE'
          AND status = 'SUCCESS'
        ORDER BY ended_at DESC NULLS LAST,
                 started_at DESC NULLS LAST,
                 create_dt DESC NULLS LAST
        LIMIT 1
    """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))
        row = cur.fetchone()

    if not row:
        raise Exception("SUCCESS 상태의 TOKENIZE run을 찾지 못했습니다. 먼저 형태소 분석 py를 실행하세요.")

    return row[0]


def validate_source_token_run(conn, source_run_id, cfg):
    """
    source_run_id가 실제 TOKENIZE 성공 run인지 확인한다.
    """
    sql = """
        SELECT
            video_id,
            method_id,
            analysis_task,
            status,
            result_count
        FROM public.youtube_analysis_run
        WHERE run_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (source_run_id,))
        row = cur.fetchone()

    if not row:
        raise Exception("SOURCE_TOKEN_RUN_ID에 해당하는 run이 없습니다. run_id=" + source_run_id)

    video_id = row[0]
    method_id = row[1]
    analysis_task = row[2]
    status = row[3]
    result_count = safe_int(row[4])

    if video_id != cfg["video_id"]:
        raise Exception("SOURCE_TOKEN_RUN_ID의 video_id가 현재 분석 영상과 다릅니다.")

    if method_id != cfg["method_id"]:
        raise Exception("SOURCE_TOKEN_RUN_ID의 method_id가 현재 ANALYSIS_METHOD_ID와 다릅니다.")

    if analysis_task != "TOKENIZE":
        raise Exception("SOURCE_TOKEN_RUN_ID가 TOKENIZE 작업이 아닙니다.")

    if status != "SUCCESS":
        raise Exception("SOURCE_TOKEN_RUN_ID가 SUCCESS 상태가 아닙니다.")

    if result_count <= 0:
        raise Exception("SOURCE_TOKEN_RUN_ID의 token 결과 수가 0입니다.")


def delete_previous_tfidf_runs(conn, cfg):
    """
    기존 TFIDF 실행 이력을 삭제한다.

    기준:
    - 같은 video_id
    - 같은 method_id
    - analysis_task = TFIDF

    주의:
    - youtube_comment_tfidf가 run_id FK ON DELETE CASCADE로 잡혀 있으면
      run 삭제 시 TF-IDF 결과도 같이 삭제된다.
    """
    sql = """
        DELETE FROM public.youtube_analysis_run
        WHERE video_id = %s
          AND method_id = %s
          AND analysis_task = 'TFIDF'
    """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))


def create_analysis_run(conn, cfg, source_run_id):
    """
    TFIDF 실행 이력을 youtube_analysis_run에 생성한다.

    source_run_id 컬럼이 없는 구조를 고려해서,
    원본 TOKENIZE run_id는 config_json에 저장한다.
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
            'TFIDF',
            'Y',
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
        "config_json": Json({
            "source_token_run_id": source_run_id,
            "min_df": cfg["min_df"],
            "min_tfidf_score": cfg["min_tfidf_score"],
            "idf_formula": "log((total_doc_count + 1) / (df + 1)) + 1"
        }),
        "now": now
    }

    with conn.cursor() as cur:
        cur.execute(sql, data)

    return run_id


def update_run_success(conn, run_id, total_comment_count, result_count):
    """
    TFIDF 성공 처리.

    result_count 의미:
    - youtube_comment_tfidf에 저장한 row 수
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
    TFIDF 실패 처리.
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
# 4. token 조회
# ============================================================

def fetch_token_rows(conn, source_run_id):
    """
    source TOKENIZE run_id의 token 데이터를 조회한다.

    조회 컬럼:
    - comment_id : document ID
    - token_norm : term
    - pos        : 품사
    - token_count: TF 계산에 사용할 댓글 안 등장 횟수
    """
    sql = """
        SELECT
            comment_id,
            token_norm,
            pos,
            token_count
        FROM public.youtube_comment_token
        WHERE run_id = %s
        ORDER BY comment_id, token_norm, pos
    """

    rows = []

    with conn.cursor() as cur:
        cur.execute(sql, (source_run_id,))

        for row in cur.fetchall():
            rows.append({
                "comment_id": row[0],
                "token_norm": row[1],
                "pos": row[2],
                "token_count": safe_int(row[3])
            })

    return rows


# ============================================================
# 5. TF-IDF 계산
# ============================================================

def build_tfidf_rows(token_rows, cfg):
    """
    youtube_comment_token row 목록을 기반으로 TF-IDF row를 만든다.

    계산 기준:
    - 전체 댓글 수 = DISTINCT comment_id 수
    - DF = token_norm + pos가 등장한 DISTINCT comment_id 수
    - TF = 해당 comment_id 안에서 token_count
    - IDF = log((전체 댓글 수 + 1) / (DF + 1)) + 1
    - TF-IDF = TF * IDF

    pos를 같이 묶는 이유:
    - 같은 표면형이라도 품사가 다르면 분석 결과를 구분할 수 있기 때문이다.
    - 현재는 NNG, NNP 위주라 큰 차이는 없지만 구조상 안전하다.
    """
    comment_ids = set()

    # token_key별 등장 댓글 집합
    # token_key = (token_norm, pos)
    df_comment_map = defaultdict(set)

    # 댓글별 token row 목록
    tf_rows = []

    for row in token_rows:
        comment_id = row["comment_id"]
        token_norm = row["token_norm"]
        pos = row["pos"]
        tf = safe_int(row["token_count"])

        if not comment_id or not token_norm:
            continue

        if tf <= 0:
            continue

        token_key = (token_norm, pos)

        comment_ids.add(comment_id)
        df_comment_map[token_key].add(comment_id)

        tf_rows.append({
            "comment_id": comment_id,
            "token_norm": token_norm,
            "pos": pos,
            "tf": tf
        })

    total_doc_count = len(comment_ids)

    if total_doc_count <= 0:
        return [], 0

    # token_key별 DF/IDF 계산
    idf_map = {}
    df_map = {}

    # 이 token이 몇 개 댓글에 등장했는가
    for token_key, comment_set in df_comment_map.items():
        df = len(comment_set)

        # 너무 적은 댓글에만 등장한 token을 제외하고 싶을 때 사용한다.
        if df < cfg["min_df"]:
            continue

        idf = math.log((total_doc_count + 1) / (df + 1)) + 1

        df_map[token_key] = df
        idf_map[token_key] = idf

    result = []

    for row in tf_rows:
        token_key = (row["token_norm"], row["pos"])

        if token_key not in idf_map:
            continue

        tf = row["tf"]
        df = df_map[token_key]
        idf = idf_map[token_key]
        tfidf_score = tf * idf

        if tfidf_score < cfg["min_tfidf_score"]:
            continue

        result.append({
            "comment_id": row["comment_id"],
            "token_norm": row["token_norm"],
            "pos": row["pos"],
            "tf": tf,
            "df": df,
            "total_doc_count": total_doc_count,
            "idf": idf,
            "tfidf_score": tfidf_score
        })

    return result, total_doc_count


# ============================================================
# 6. TF-IDF DB 저장
# ============================================================

def insert_tfidf_rows(conn, run_id, cfg, rows):
    """
    youtube_comment_tfidf에 TF-IDF 결과를 저장한다.

    저장 단위:
    - TFIDF run_id
    - comment_id
    - token_norm
    - pos

    이 조합으로 1 row를 저장한다.
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO public.youtube_comment_tfidf
        (
            run_id,
            method_id,
            video_id,
            comment_id,
            token_norm,
            pos,
            tf,
            df,
            total_doc_count,
            idf,
            tfidf_score,
            create_dt,
            update_dt
        )
        VALUES %s
        ON CONFLICT
        (
            run_id,
            comment_id,
            token_norm,
            pos
        )
        DO UPDATE SET
            tf = EXCLUDED.tf,
            df = EXCLUDED.df,
            total_doc_count = EXCLUDED.total_doc_count,
            idf = EXCLUDED.idf,
            tfidf_score = EXCLUDED.tfidf_score,
            update_dt = EXCLUDED.update_dt
    """

    now = now_str()

    values = []

    for row in rows:
        values.append((
            run_id,
            cfg["method_id"],
            cfg["video_id"],
            row.get("comment_id"),
            row.get("token_norm"),
            row.get("pos"),
            safe_int(row.get("tf")),
            safe_int(row.get("df")),
            safe_int(row.get("total_doc_count")),
            safe_float(row.get("idf")),
            safe_float(row.get("tfidf_score")),
            now,
            now
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)

    return len(values)


# ============================================================
# 7. 실행 main
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
    print("[분석 작업]", "TFIDF")
    print("[분석 영상]", cfg["video_id"])
    print("[분석 방식]", cfg["method_id"])
    print("[지정 TOKENIZE run_id]", cfg["source_token_run_id"] or "(자동)")
    print("[기존 TFIDF 삭제]", "Y" if cfg["reset_yn"] else "N")
    print("[최소 DF]", cfg["min_df"])
    print("[최소 TF-IDF score]", cfg["min_tfidf_score"])

    conn = get_conn(cfg)
    run_id = None

    try:
        print("")
        print("[1] 분석 방식 확인")
        check_analysis_method(conn, cfg["method_id"])
        print("[분석 방식 확인 완료]")

        print("")
        print("[2] TOKENIZE run 찾기")
        source_run_id = find_source_token_run_id(conn, cfg)
        validate_source_token_run(conn, source_run_id, cfg)
        print("[TOKENIZE run_id]", source_run_id)

        if cfg["reset_yn"]:
            print("")
            print("[3] 기존 TFIDF 실행 이력 삭제")
            delete_previous_tfidf_runs(conn, cfg)
            print("[기존 TFIDF 삭제 완료]")

        print("")
        print("[4] TFIDF run 생성")
        run_id = create_analysis_run(conn, cfg, source_run_id)
        print("[TFIDF run_id]", run_id)

        print("")
        print("[5] token 조회")
        token_rows = fetch_token_rows(conn, source_run_id)
        print("[token rows]", len(token_rows))

        if not token_rows:
            raise Exception("TF-IDF 계산할 token 데이터가 없습니다. TOKENIZE를 먼저 실행하세요.")

        print("")
        print("[6] TF-IDF 계산")
        tfidf_rows, total_doc_count = build_tfidf_rows(token_rows, cfg)
        print("[전체 댓글/document 수]", total_doc_count)
        print("[tfidf rows]", len(tfidf_rows))

        print("")
        print("[7] DB 저장")
        inserted_count = insert_tfidf_rows(conn, run_id, cfg, tfidf_rows)
        print("[저장 tfidf rows]", inserted_count)

        update_run_success(
            conn,
            run_id,
            total_doc_count,
            inserted_count
        )

        conn.commit()

        print("")
        print("[완료]")
        print("[TFIDF run_id]", run_id)
        print("[SOURCE TOKENIZE run_id]", source_run_id)

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
