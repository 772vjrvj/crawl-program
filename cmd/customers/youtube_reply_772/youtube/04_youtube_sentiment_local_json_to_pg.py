# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime

import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube 댓글 감성분석 JSON -> PostgreSQL 저장
# ============================================================
#
# 목적:
# 1) youtube_comment_sentiment_gpt.json 파일을 읽는다.
# 2) JSON 배열 안의 comment_id 기준으로 youtube_comment에서
#    video_id, parent_comment_id, comment_kind 정보를 가져온다.
# 3) youtube_analysis_run에 SENTIMENT 실행 이력을 생성한다.
# 4) youtube_comment_sentiment 테이블에 감성분석 결과를 저장한다.
#
# 전제:
# - youtube_comment 테이블에 댓글 원본이 먼저 들어 있어야 한다.
# - youtube_comment_sentiment 테이블이 생성되어 있어야 한다.
# - youtube_analysis_method에 SENTIMENT_CLOVA_HCX005_V1 이 등록되어 있어야 한다.
#
# 설치:
# pip install psycopg2-binary python-dotenv
#
# 실행:
# python 04_youtube_sentiment_local_json_to_pg.py
# ============================================================


# ============================================================
# 1. 공통 유틸
# ============================================================

def base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_text(value):
    if value is None:
        return ""
    return str(value)


def safe_int(value):
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_float(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def get_yn(value):
    value = safe_text(value).strip().upper()
    return value in ["Y", "YES", "TRUE", "1"]


def get_video_id(value):
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


def get_path(value):
    path = Path(value)

    if path.is_absolute():
        return path

    return base_dir() / path


# ============================================================
# 2. .env 설정
# ============================================================

def load_config():
    env_path = base_dir() / ".env"
    load_dotenv(env_path)

    video_raw = os.getenv("ANALYZE_VIDEO_CODE", "").strip()

    if not video_raw:
        video_raw = os.getenv("YOUTUBE_VIDEO_CODE", "").strip()

    if not video_raw:
        video_raw = os.getenv("YOUTUBE_VIDEO_URL", "").strip()

    return {
        "video_id": get_video_id(video_raw),

        # 감성분석 method_id
        "method_id": os.getenv("SENTIMENT_METHOD_ID", "SENTIMENT_CLOVA_HCX005_V1").strip(),

        # JSON 파일 경로
        "json_file": get_path(os.getenv("SENTIMENT_JSON_FILE", "youtube_comment_sentiment_gpt.json")),

        # Y이면 같은 video_id + method_id + SENTIMENT 기존 실행 이력 삭제 후 다시 저장
        "reset_yn": get_yn(os.getenv("SENTIMENT_RESET_YN", "Y")),

        # 대댓글 포함 여부. 현재 JSON에 들어온 comment_id 기준으로 저장하므로 run 기록용이다.
        "include_replies": get_yn(os.getenv("ANALYZE_REPLIES", "Y")),

        # DB
        "db_host": os.getenv("DB_HOST", ""),
        "db_port": int(os.getenv("DB_PORT", "")),
        "db_name": os.getenv("DB_NAME", ""),
        "db_user": os.getenv("DB_USER", ""),
        "db_password": os.getenv("DB_PASSWORD", "")
    }


def get_conn(cfg):
    return psycopg2.connect(
        host=cfg["db_host"],
        port=cfg["db_port"],
        dbname=cfg["db_name"],
        user=cfg["db_user"],
        password=cfg["db_password"]
    )


# ============================================================
# 3. JSON 읽기
# ============================================================

def load_sentiment_json(json_file):
    if not json_file.exists():
        raise Exception("JSON 파일을 찾지 못했습니다: " + str(json_file))

    with json_file.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # 혹시 단일 JSON 객체로 저장한 경우도 배열로 맞춘다.
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        raise Exception("JSON 최상위 구조는 배열이어야 합니다.")

    result = []
    duplicate_count = 0
    seen = set()

    # 같은 comment_id가 중복되면 마지막 값을 사용한다.
    temp_map = {}

    for item in data:
        if not isinstance(item, dict):
            continue

        comment_id = safe_text(item.get("comment_id")).strip()

        if not comment_id:
            continue

        if comment_id in seen:
            duplicate_count += 1

        seen.add(comment_id)
        temp_map[comment_id] = item

    for comment_id in temp_map:
        result.append(temp_map[comment_id])

    print("[JSON 원본 수]", len(data))
    print("[JSON 유효 수]", len(result))
    print("[JSON 중복 제거 수]", duplicate_count)

    return result


# ============================================================
# 4. method / run 처리
# ============================================================

def check_analysis_method(conn, method_id):
    sql = """
          SELECT COUNT(*)
          FROM public.youtube_analysis_method
          WHERE method_id = %s \
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


def delete_previous_sentiment_runs(conn, cfg):
    sql = """
          DELETE FROM public.youtube_analysis_run
          WHERE video_id = %s
            AND method_id = %s
            AND analysis_task = 'SENTIMENT' \
          """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))


def create_analysis_run(conn, cfg, json_count):
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
                  'SENTIMENT',
                  %(include_reply_yn)s,
                  'RUNNING',
                  %(config_json)s,
                  %(total_comment_count)s,
                  0,
                  %(now)s,
                  %(now)s,
                  %(now)s
              ) \
          """

    data = {
        "run_id": run_id,
        "video_id": cfg["video_id"],
        "method_id": cfg["method_id"],
        "include_reply_yn": "Y" if cfg["include_replies"] else "N",
        "config_json": Json({
            "json_file": str(cfg["json_file"]),
            "json_count": json_count,
            "label_list": ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"],
            "score_range": "-1_to_1",
            "source": "manual_json_import"
        }),
        "total_comment_count": json_count,
        "now": now
    }

    with conn.cursor() as cur:
        cur.execute(sql, data)

    return run_id


def update_run_success(conn, run_id, total_comment_count, result_count):
    now = now_str()

    sql = """
          UPDATE public.youtube_analysis_run
          SET status = 'SUCCESS',
              total_comment_count = %s,
              result_count = %s,
              ended_at = %s,
              update_dt = %s
          WHERE run_id = %s \
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
    now = now_str()

    sql = """
          UPDATE public.youtube_analysis_run
          SET status = 'FAIL',
              error_message = %s,
              ended_at = %s,
              update_dt = %s
          WHERE run_id = %s \
          """

    with conn.cursor() as cur:
        cur.execute(sql, (
            safe_text(error_message)[:5000],
            now,
            now,
            run_id
        ))


# ============================================================
# 5. 댓글 원본 정보 조회
# ============================================================

def fetch_comment_info_map(conn, comment_ids):
    if not comment_ids:
        return {}

    sql = """
          SELECT
              comment_id,
              video_id,
              parent_comment_id
          FROM public.youtube_comment
          WHERE comment_id = ANY(%s) \
          """

    result = {}

    with conn.cursor() as cur:
        cur.execute(sql, (comment_ids,))

        for row in cur.fetchall():
            comment_id = row[0]
            video_id = row[1]
            parent_comment_id = row[2]

            if parent_comment_id:
                comment_kind = "REPLY"
            else:
                comment_kind = "TOP"

            result[comment_id] = {
                "comment_id": comment_id,
                "video_id": video_id,
                "parent_comment_id": parent_comment_id,
                "comment_kind": comment_kind
            }

    return result


def validate_comment_ids(sentiment_items, comment_info_map):
    missing = []

    for item in sentiment_items:
        comment_id = safe_text(item.get("comment_id")).strip()

        if comment_id not in comment_info_map:
            missing.append(comment_id)

    if missing:
        print("[DB에 없는 comment_id 수]", len(missing))
        print("[DB에 없는 comment_id 예시]", missing[:10])
        raise Exception("JSON에는 있지만 youtube_comment 테이블에 없는 comment_id가 있습니다.")


# ============================================================
# 6. 감성 결과 저장
# ============================================================

def normalize_label(value):
    value = safe_text(value).strip().upper()

    if value in ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]:
        return value

    # 혹시 한글로 들어온 경우 보정
    if value in ["긍정", "좋음"]:
        return "POSITIVE"

    if value in ["부정", "나쁨"]:
        return "NEGATIVE"

    if value in ["중립"]:
        return "NEUTRAL"

    if value in ["혼합", "복합"]:
        return "MIXED"

    return "NEUTRAL"


def insert_sentiment_rows(conn, run_id, cfg, sentiment_items, comment_info_map):
    if not sentiment_items:
        return 0

    sql = """
          INSERT INTO public.youtube_comment_sentiment
          (
              run_id,
              method_id,
              video_id,
              comment_id,
              parent_comment_id,
              comment_kind,
              sentiment_label,
              sentiment_score,
              sentiment_magnitude,
              positive_score,
              negative_score,
              neutral_score,
              mixed_score,
              confidence_score,
              reason_text,
              request_id,
              input_token_count,
              output_token_count,
              total_token_count,
              response_ms,
              raw_json,
              create_dt,
              update_dt
          )
          VALUES %s
          ON CONFLICT
          (
              run_id,
              comment_id
          )
          DO UPDATE SET
              method_id = EXCLUDED.method_id,
              video_id = EXCLUDED.video_id,
              parent_comment_id = EXCLUDED.parent_comment_id,
              comment_kind = EXCLUDED.comment_kind,
              sentiment_label = EXCLUDED.sentiment_label,
              sentiment_score = EXCLUDED.sentiment_score,
              sentiment_magnitude = EXCLUDED.sentiment_magnitude,
              positive_score = EXCLUDED.positive_score,
              negative_score = EXCLUDED.negative_score,
              neutral_score = EXCLUDED.neutral_score,
              mixed_score = EXCLUDED.mixed_score,
              confidence_score = EXCLUDED.confidence_score,
              reason_text = EXCLUDED.reason_text,
              request_id = EXCLUDED.request_id,
              input_token_count = EXCLUDED.input_token_count,
              output_token_count = EXCLUDED.output_token_count,
              total_token_count = EXCLUDED.total_token_count,
              response_ms = EXCLUDED.response_ms,
              raw_json = EXCLUDED.raw_json,
              update_dt = EXCLUDED.update_dt \
          """

    now = now_str()
    values = []

    for item in sentiment_items:
        comment_id = safe_text(item.get("comment_id")).strip()
        comment_info = comment_info_map[comment_id]

        sentiment_label = normalize_label(item.get("sentiment_label"))
        sentiment_score = safe_float(item.get("sentiment_score"))

        # -1 ~ 1 범위 보정
        if sentiment_score > 1:
            sentiment_score = 1.0
        elif sentiment_score < -1:
            sentiment_score = -1.0

        values.append((
            run_id,
            cfg["method_id"],
            comment_info["video_id"],
            comment_id,
            comment_info["parent_comment_id"],
            comment_info["comment_kind"],
            sentiment_label,
            sentiment_score,
            safe_float(item.get("sentiment_magnitude")),
            safe_float(item.get("positive_score")),
            safe_float(item.get("negative_score")),
            safe_float(item.get("neutral_score")),
            safe_float(item.get("mixed_score")),
            safe_float(item.get("confidence_score")),
            safe_text(item.get("reason_text")),
            safe_text(item.get("request_id")),
            safe_int(item.get("input_token_count")),
            safe_int(item.get("output_token_count")),
            safe_int(item.get("total_token_count")),
            safe_int(item.get("response_ms")),
            Json(item),
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
        print("[중지] SENTIMENT_METHOD_ID를 입력하세요.")
        return

    print("[ENV 위치]", base_dir() / ".env")
    print("[분석 작업]", "SENTIMENT JSON IMPORT")
    print("[분석 영상]", cfg["video_id"])
    print("[분석 방식]", cfg["method_id"])
    print("[JSON 파일]", cfg["json_file"])
    print("[기존 SENTIMENT 삭제]", "Y" if cfg["reset_yn"] else "N")

    sentiment_items = load_sentiment_json(cfg["json_file"])

    if not sentiment_items:
        print("[중지] JSON에 저장할 데이터가 없습니다.")
        return

    conn = get_conn(cfg)
    run_id = None

    try:
        print("")
        print("[1] 분석 방식 확인")
        check_analysis_method(conn, cfg["method_id"])
        print("[분석 방식 확인 완료]")

        if cfg["reset_yn"]:
            print("")
            print("[2] 기존 SENTIMENT 실행 이력 삭제")
            delete_previous_sentiment_runs(conn, cfg)
            print("[기존 SENTIMENT 삭제 완료]")

        print("")
        print("[3] SENTIMENT run 생성")
        run_id = create_analysis_run(conn, cfg, len(sentiment_items))
        print("[run_id]", run_id)

        print("")
        print("[4] comment_id 원본 댓글 정보 조회")
        comment_ids = [safe_text(item.get("comment_id")).strip() for item in sentiment_items]
        comment_info_map = fetch_comment_info_map(conn, comment_ids)
        print("[DB 조회된 comment_id 수]", len(comment_info_map))

        validate_comment_ids(sentiment_items, comment_info_map)
        print("[comment_id 검증 완료]")

        print("")
        print("[5] 감성분석 결과 DB 저장")
        inserted_count = insert_sentiment_rows(
            conn,
            run_id,
            cfg,
            sentiment_items,
            comment_info_map
        )
        print("[저장 sentiment rows]", inserted_count)

        update_run_success(
            conn,
            run_id,
            len(sentiment_items),
            inserted_count
        )

        conn.commit()

        print("")
        print("[완료]")
        print("[SENTIMENT run_id]", run_id)

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