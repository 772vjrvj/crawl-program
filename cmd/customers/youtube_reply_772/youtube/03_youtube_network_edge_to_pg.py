import os
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime
from collections import Counter
from itertools import combinations

import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube 댓글 token 동시출현 네트워크 생성 -> PostgreSQL 저장
# ============================================================
#
# 목적:
# 1) 01_youtube_tokenize_kiwi_to_pg.py 실행 후 저장된 youtube_comment_token을 조회한다.
# 2) 최신 TOKENIZE run_id를 자동으로 찾는다.
# 3) 댓글 1개 안에서 같이 등장한 token 쌍을 만든다.
# 4) token 쌍이 몇 개 댓글에서 같이 등장했는지 weight를 계산한다.
# 5) 계산 결과를 public.youtube_token_edge에 저장한다.
# 6) public.youtube_analysis_run에 NETWORK 실행 이력을 남긴다.
#
# 전제:
# - youtube_collect.py 실행 완료
# - 01_youtube_tokenize_kiwi_to_pg.py 실행 완료
# - youtube_comment_token에 token 데이터가 있어야 한다.
#
# 네트워크 기준:
# - document = comment_id 1개
# - node     = token_norm
# - edge     = 같은 댓글 안에 같이 등장한 token pair
# - weight   = 해당 token pair가 같이 등장한 댓글 수
#
# 예:
# 댓글1 token = [경제, 정책, 부동산]
# 생성 edge:
# - 경제 - 정책
# - 경제 - 부동산
# - 정책 - 부동산
#
# 설치:
# pip install psycopg2-binary python-dotenv
#
# 실행:
# python 03_youtube_network_edge_to_pg.py
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
    .env에서 NETWORK 설정과 DB 설정을 읽는다.

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
        # 현재는 형태소 분석 결과 기반 네트워크이므로 같은 method_id를 사용한다.
        "method_id": os.getenv("ANALYSIS_METHOD_ID", "MORPH_KIWI_V1").strip(),

        # 특정 TOKENIZE run_id를 직접 지정하고 싶을 때 사용
        # 비워두면 최신 SUCCESS TOKENIZE run을 자동 선택한다.
        "source_token_run_id": os.getenv("SOURCE_TOKEN_RUN_ID", "").strip(),

        # Y이면 같은 video_id + method_id + NETWORK 기존 실행 이력을 삭제하고 다시 저장한다.
        "reset_yn": get_yn(os.getenv("NETWORK_RESET_YN", os.getenv("ANALYSIS_RESET_YN", "Y"))),

        # edge 최소 weight
        # 1이면 한 댓글에서만 같이 나온 token 쌍도 저장
        # 2이면 최소 2개 댓글 이상 같이 나온 token 쌍만 저장
        "min_edge_weight": int(os.getenv("NETWORK_MIN_EDGE_WEIGHT", "1")),

        # 댓글 1개에서 네트워크 조합에 사용할 token 최대 개수
        # 너무 큰 댓글에서 조합 수가 폭증하는 것을 막기 위한 안전장치다.
        # 30이면 댓글 1개당 최대 30개 token만 edge 생성에 사용한다.
        "max_tokens_per_comment": int(os.getenv("NETWORK_MAX_TOKENS_PER_COMMENT", "30")),

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
    네트워크 생성에 사용할 TOKENIZE run_id를 찾는다.

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


def delete_previous_network_runs(conn, cfg):
    """
    기존 NETWORK 실행 이력을 삭제한다.

    기준:
    - 같은 video_id
    - 같은 method_id
    - analysis_task = NETWORK

    주의:
    - youtube_token_edge가 run_id FK ON DELETE CASCADE로 잡혀 있으면
      run 삭제 시 edge 결과도 같이 삭제된다.
    """
    sql = """
        DELETE FROM public.youtube_analysis_run
        WHERE video_id = %s
          AND method_id = %s
          AND analysis_task = 'NETWORK'
    """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))


def create_analysis_run(conn, cfg, source_run_id):
    """
    NETWORK 실행 이력을 youtube_analysis_run에 생성한다.

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
            'NETWORK',
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
            "edge_type": "CO_OCCURRENCE",
            "min_edge_weight": cfg["min_edge_weight"],
            "max_tokens_per_comment": cfg["max_tokens_per_comment"]
        }),
        "now": now
    }

    with conn.cursor() as cur:
        cur.execute(sql, data)

    return run_id


def update_run_success(conn, run_id, total_comment_count, result_count):
    """
    NETWORK 성공 처리.

    result_count 의미:
    - youtube_token_edge에 저장한 edge row 수
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
    NETWORK 실패 처리.
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
    - comment_id  : 댓글 ID. 댓글 1개가 네트워크 조합 기준이다.
    - token_norm  : 네트워크 node 이름
    - pos         : 품사
    - token_count : 댓글 안 token 빈도. 댓글별 token 정렬용으로 사용한다.
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
# 5. 네트워크 edge 생성
# ============================================================

def build_edge_rows(token_rows, cfg):
    """
    댓글별 token 목록을 기반으로 동시출현 edge row를 만든다.

    처리 방식:
    1) comment_id 기준으로 token을 묶는다.
    2) 댓글 1개 안의 token 목록에서 2개씩 조합을 만든다.
    3) 같은 token pair가 여러 댓글에서 나오면 weight를 누적한다.
    4) min_edge_weight 미만 edge는 제외한다.

    주의:
    - 댓글 1개에 token이 너무 많으면 조합 수가 급격히 늘어난다.
      예: token 50개면 1,225개 조합
    - 그래서 NETWORK_MAX_TOKENS_PER_COMMENT로 댓글당 token 수를 제한한다.
    """
    comment_token_map = {}

    for row in token_rows:
        comment_id = row["comment_id"]
        token_norm = safe_text(row["token_norm"]).strip()
        pos = safe_text(row["pos"]).strip()
        token_count = safe_int(row["token_count"])

        if not comment_id or not token_norm:
            continue

        if comment_id not in comment_token_map:
            comment_token_map[comment_id] = {}

        # 같은 댓글에서 같은 token_norm이 여러 품사로 잡히는 경우가 있을 수 있다.
        # 현재 edge 테이블 unique 기준은 token 텍스트 중심이므로 token_norm 기준으로 1개만 사용한다.
        # token_count가 더 큰 품사를 대표 pos로 사용한다.
        if token_norm not in comment_token_map[comment_id]:
            comment_token_map[comment_id][token_norm] = {
                "pos": pos,
                "token_count": token_count
            }
        else:
            old = comment_token_map[comment_id][token_norm]

            if token_count > old["token_count"]:
                comment_token_map[comment_id][token_norm] = {
                    "pos": pos,
                    "token_count": token_count
                }

    edge_counter = Counter()
    edge_pos_map = {}

    for comment_id, token_info_map in comment_token_map.items():
        token_items = []

        for token_norm, info in token_info_map.items():
            token_items.append({
                "token_norm": token_norm,
                "pos": info["pos"],
                "token_count": info["token_count"]
            })

        # 댓글 안에서 많이 등장한 token을 우선 사용한다.
        # 같은 빈도면 token 글자 기준으로 정렬해서 결과를 안정적으로 만든다.(유니코드 순서 ㄱㄴㄷ 순)
        token_items.sort(
            key=lambda item: (
                -safe_int(item["token_count"]),
                item["token_norm"]
            )
        )

        # 댓글당 token 수 제한
        max_count = cfg["max_tokens_per_comment"]

        if max_count > 0 and len(token_items) > max_count:
            token_items = token_items[:max_count]

        # token이 2개 미만이면 edge를 만들 수 없다.
        if len(token_items) < 2:
            continue

        # token pair 생성
        for item_a, item_b in combinations(token_items, 2):
            token_a = item_a["token_norm"]
            token_b = item_b["token_norm"]

            if token_a == token_b:
                continue

            # 무방향 네트워크이므로 항상 사전순으로 source/target을 고정한다.
            # 이렇게 해야 경제-정책, 정책-경제가 서로 다른 edge로 저장되지 않는다.
            if token_a < token_b:
                source_token = token_a
                target_token = token_b
                source_pos = item_a["pos"]
                target_pos = item_b["pos"]
            else:
                source_token = token_b
                target_token = token_a
                source_pos = item_b["pos"]
                target_pos = item_a["pos"]

            edge_key = (source_token, target_token)

            # 댓글 1개에서는 같은 pair를 1번만 세는 구조다.
            # 이미 comment_token_map에서 token_norm을 unique 처리했으므로 그대로 +1 한다.
            edge_counter[edge_key] += 1

            if edge_key not in edge_pos_map:
                edge_pos_map[edge_key] = {
                    "source_pos": source_pos,
                    "target_pos": target_pos
                }

    result = []

    for edge_key, weight in edge_counter.items():
        if weight < cfg["min_edge_weight"]:
            continue

        source_token, target_token = edge_key
        pos_info = edge_pos_map.get(edge_key, {})

        result.append({
            "source_token": source_token,
            "target_token": target_token,
            "source_pos": pos_info.get("source_pos"),
            "target_pos": pos_info.get("target_pos"),
            "edge_type": "CO_OCCURRENCE",
            "weight": weight,
            "comment_count": weight
        })

    # weight 높은 순으로 정렬해서 저장/확인하기 쉽게 한다.
    result.sort(
        key=lambda row: (
            -safe_int(row["weight"]),
            row["source_token"],
            row["target_token"]
        )
    )

    return result, len(comment_token_map)


# ============================================================
# 6. edge DB 저장
# ============================================================

def insert_edge_rows(conn, run_id, cfg, rows):
    """
    youtube_token_edge에 네트워크 edge 결과를 저장한다.

    저장 단위:
    - NETWORK run_id
    - source_token
    - target_token
    - edge_type

    이 조합으로 1 row를 저장한다.
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO public.youtube_token_edge
        (
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
        )
        VALUES %s
        ON CONFLICT
        (
            run_id,
            source_token,
            target_token,
            edge_type
        )
        DO UPDATE SET
            source_pos = EXCLUDED.source_pos,
            target_pos = EXCLUDED.target_pos,
            weight = EXCLUDED.weight,
            comment_count = EXCLUDED.comment_count,
            update_dt = EXCLUDED.update_dt
    """

    now = now_str()

    values = []

    for row in rows:
        values.append((
            run_id,
            cfg["method_id"],
            cfg["video_id"],
            row.get("source_token"),
            row.get("target_token"),
            row.get("source_pos"),
            row.get("target_pos"),
            row.get("edge_type"),
            safe_int(row.get("weight")),
            safe_int(row.get("comment_count")),
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
    print("[분석 작업]", "NETWORK")
    print("[분석 영상]", cfg["video_id"])
    print("[분석 방식]", cfg["method_id"])
    print("[지정 TOKENIZE run_id]", cfg["source_token_run_id"] or "(자동)")
    print("[기존 NETWORK 삭제]", "Y" if cfg["reset_yn"] else "N")
    print("[edge 최소 weight]", cfg["min_edge_weight"])
    print("[댓글당 최대 token 수]", cfg["max_tokens_per_comment"])

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
            print("[3] 기존 NETWORK 실행 이력 삭제")
            delete_previous_network_runs(conn, cfg)
            print("[기존 NETWORK 삭제 완료]")

        print("")
        print("[4] NETWORK run 생성")
        run_id = create_analysis_run(conn, cfg, source_run_id)
        print("[NETWORK run_id]", run_id)

        print("")
        print("[5] token 조회")
        token_rows = fetch_token_rows(conn, source_run_id)
        print("[token rows]", len(token_rows))

        if not token_rows:
            raise Exception("네트워크 생성할 token 데이터가 없습니다. TOKENIZE를 먼저 실행하세요.")

        print("")
        print("[6] 네트워크 edge 생성")
        edge_rows, total_comment_count = build_edge_rows(token_rows, cfg)
        print("[edge 계산 기준 댓글 수]", total_comment_count)
        print("[edge rows]", len(edge_rows))

        print("")
        print("[7] DB 저장")
        inserted_count = insert_edge_rows(conn, run_id, cfg, edge_rows)
        print("[저장 edge rows]", inserted_count)

        update_run_success(
            conn,
            run_id,
            total_comment_count,
            inserted_count
        )

        conn.commit()

        print("")
        print("[완료]")
        print("[NETWORK run_id]", run_id)
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
