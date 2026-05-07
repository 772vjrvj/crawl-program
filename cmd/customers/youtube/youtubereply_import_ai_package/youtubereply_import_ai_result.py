import os
import re
import json
from pathlib import Path
from itertools import combinations
from collections import defaultdict
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# AI 결과 CSV → PostgreSQL 반영
# ============================================================
#
# 이 파일은 아래 CSV를 DB에 넣는 전용 프로그램입니다.
#
# 1) 07_ai_comment_analysis_result.csv
#    → comment_analysis
#    → comment_keyword_raw source_type='AI'
#    → comment_keyword_summary ai_yn='Y'
#    → video_keyword AI 집계
#    → keyword_edge AI 연결선 집계
#    → youtube_comment.analysis_status='DONE'
#
# 2) 08_ai_suspicion_analysis_result.csv
#    → comment_suspicion_analysis
#    → youtube_comment.suspicion_status='DONE'
#
# 3) 09_ai_video_summary_result.csv
#    → video_content_analysis
#
# 실행 전:
# - 먼저 youtubereply_collect_insert_export.py를 실행해서 원본 댓글이 DB에 들어가 있어야 합니다.
# - AI에게 받은 결과 CSV를 output/영상ID/ 폴더에 저장하세요.
#
# 실행:
# python youtubereply_import_ai_result.py
#
# ============================================================


# ==============================
# 공통 유틸
# ==============================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_text(value):
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def safe_float(value):
    try:
        text = safe_text(value)
        if text == "":
            return 0
        return float(text)
    except Exception:
        return 0


def safe_yn(value):
    text = safe_text(value).upper()
    if text == "Y":
        return "Y"
    return "N"


def normalize_label(value, allowed, default_value):
    text = safe_text(value).lower()
    if text in allowed:
        return text
    return default_value


def normalize_suspicion_label(value):
    text = safe_text(value).upper()
    allowed = {
        "NORMAL",
        "AUTO_COMMENT",
        "AI_GENERATED",
        "COMMENT_FARM",
        "POLITICAL",
        "PROPAGANDA",
        "SPAM",
        "TROLL"
    }
    if text in allowed:
        return text
    return "NORMAL"


def read_csv(path):
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def split_keywords(text):
    """
    AI가 준 ai_keywords 값을 키워드 배열로 변환.
    쉼표, 세미콜론, 줄바꿈, | 구분자를 모두 허용.
    """
    text = safe_text(text)

    if not text:
        return []

    parts = re.split(r"[,;\n|]+", text)
    keywords = []

    for part in parts:
        keyword = part.strip()
        keyword = keyword.replace("#", "").strip()

        if not keyword:
            continue

        if len(keyword) > 100:
            keyword = keyword[:100]

        if keyword not in keywords:
            keywords.append(keyword)

    return keywords


def normalize_keyword(keyword):
    """
    키워드 비교용 정규화.
    - 앞뒤 공백 제거
    - 내부 공백 제거
    - 소문자화
    """
    keyword = safe_text(keyword)
    keyword = re.sub(r"\s+", "", keyword)
    return keyword.lower()


def get_required_path(path_text, label):
    path = Path(path_text).resolve()

    if not path.exists():
        raise FileNotFoundError(label + " 파일을 찾을 수 없습니다: " + str(path))

    return path


# ==============================
# 환경설정
# ==============================

load_dotenv()

VIDEO_ID = os.getenv("VIDEO_ID", "").strip()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output")).resolve()

AI_COMMENT_RESULT_CSV = os.getenv("AI_COMMENT_RESULT_CSV", "").strip()
AI_SUSPICION_RESULT_CSV = os.getenv("AI_SUSPICION_RESULT_CSV", "").strip()
AI_VIDEO_SUMMARY_RESULT_CSV = os.getenv("AI_VIDEO_SUMMARY_RESULT_CSV", "").strip()

# === 신규 === 결과 CSV가 여러 개일 때 폴더 단위로 자동 import
AI_COMMENT_RESULT_DIR = os.getenv("AI_COMMENT_RESULT_DIR", "").strip()
AI_SUSPICION_RESULT_DIR = os.getenv("AI_SUSPICION_RESULT_DIR", "").strip()
AI_VIDEO_SUMMARY_RESULT_DIR = os.getenv("AI_VIDEO_SUMMARY_RESULT_DIR", "").strip()

IMPORT_PROVIDER = os.getenv("IMPORT_PROVIDER", "AI_WEB").strip()
IMPORT_MODEL_NAME = os.getenv("IMPORT_MODEL_NAME", "WEB_AI").strip()

# Y면 같은 comment_id의 기존 분석 결과를 지우고 다시 넣음
# 초기 개발에서는 Y 추천
REPLACE_EXISTING = os.getenv("REPLACE_EXISTING", "Y").strip().upper() == "Y"

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "youtubereply")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


# ==============================
# DB 연결
# ==============================

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


# ==============================
# DB 공통
# ==============================

def create_batch(conn, video_id, batch_type, import_file_name, target_count, memo):
    sql = """
          INSERT INTO analysis_batch (
              video_id,
              batch_type,
              provider,
              model_name,
              import_file_name,
              status,
              target_count,
              success_count,
              fail_count,
              memo,
              create_dt,
              update_dt
          ) VALUES (
                       %s, %s, %s, %s, %s,
                       'RUNNING',
                       %s, 0, 0,
                       %s,
                       %s, %s
                   )
          RETURNING batch_id \
          """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                video_id,
                batch_type,
                IMPORT_PROVIDER,
                IMPORT_MODEL_NAME,
                import_file_name,
                target_count,
                memo,
                now_str(),
                now_str()
            )
        )
        return cur.fetchone()[0]


def finish_batch(conn, batch_id, status, success_count, fail_count, memo):
    sql = """
          UPDATE analysis_batch
          SET
              status = %s,
              success_count = %s,
              fail_count = %s,
              memo = %s,
              update_dt = %s
          WHERE batch_id = %s \
          """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                status,
                success_count,
                fail_count,
                memo,
                now_str(),
                batch_id
            )
        )


def get_comment_video_map(conn, comment_ids):
    if not comment_ids:
        return {}

    sql = """
          SELECT comment_id, video_id
          FROM youtube_comment
          WHERE comment_id = ANY(%s) \
          """

    with conn.cursor() as cur:
        cur.execute(sql, (list(comment_ids),))
        rows = cur.fetchall()

    result = {}

    for comment_id, video_id in rows:
        result[comment_id] = video_id

    return result


def get_video_id_from_comments(conn, comment_ids):
    mapping = get_comment_video_map(conn, comment_ids)

    video_ids = sorted(set(mapping.values()))

    if len(video_ids) == 1:
        return video_ids[0]

    if VIDEO_ID:
        return VIDEO_ID

    if not video_ids:
        raise ValueError("DB에서 comment_id에 해당하는 영상 ID를 찾지 못했습니다.")

    raise ValueError("CSV 안에 여러 영상의 댓글이 섞여 있습니다. .env에 VIDEO_ID를 지정하세요.")


# ==============================
# 1. 댓글 AI 분석 결과 import
# ==============================

def import_comment_analysis(conn, csv_path):
    print("")
    print("[AI 댓글 분석 결과 import]", csv_path)

    df = read_csv(csv_path)

    if df.empty:
        print("[건너뜀] AI 댓글 분석 결과 CSV가 비어 있습니다.")
        return

    required_cols = [
        "comment_id",
        "sentiment_label",
        "positive_score",
        "negative_score",
        "neutral_score",
        "emotion_label",
        "emotion_intensity",
        "joy_score",
        "anger_score",
        "sadness_score",
        "fear_score",
        "surprise_score",
        "disgust_score",
        "humor_score",
        "sarcasm_score",
        "toxicity_score",
        "controversy_score",
        "quality_score",
        "comment_category",
        "topic",
        "summary",
        "ai_reason",
        "ai_keywords"
    ]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError("AI 댓글 분석 결과 CSV에 필요한 컬럼이 없습니다: " + col)

    comment_ids = [safe_text(x) for x in df["comment_id"].tolist() if safe_text(x)]
    comment_ids = list(dict.fromkeys(comment_ids))

    comment_video_map = get_comment_video_map(conn, comment_ids)
    video_id = get_video_id_from_comments(conn, comment_ids)

    batch_id = create_batch(
        conn=conn,
        video_id=video_id,
        batch_type="COMMENT_AI_IMPORT",
        import_file_name=str(csv_path),
        target_count=len(df),
        memo="AI 댓글 분석 결과 CSV import"
    )

    success_count = 0
    fail_count = 0

    try:
        if REPLACE_EXISTING:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM comment_analysis WHERE comment_id = ANY(%s)",
                    (comment_ids,)
                )
                cur.execute(
                    "DELETE FROM comment_keyword_raw WHERE source_type = 'AI' AND comment_id = ANY(%s)",
                    (comment_ids,)
                )

        analysis_values = []
        keyword_values = []
        done_comment_ids = []

        sentiment_allowed = {"positive", "negative", "neutral"}
        emotion_allowed = {"joy", "anger", "sadness", "fear", "surprise", "disgust", "neutral"}
        category_allowed = {
            "praise", "criticism", "question", "joke",
            "request", "info", "spam", "argument", "normal"
        }

        for _, row in df.iterrows():
            comment_id = safe_text(row.get("comment_id"))

            if not comment_id:
                fail_count += 1
                continue

            row_video_id = comment_video_map.get(comment_id)

            if not row_video_id:
                print("[경고] DB에 없는 comment_id 건너뜀:", comment_id)
                fail_count += 1
                continue

            sentiment_label = normalize_label(row.get("sentiment_label"), sentiment_allowed, "neutral")
            emotion_label = normalize_label(row.get("emotion_label"), emotion_allowed, "neutral")
            comment_category = normalize_label(row.get("comment_category"), category_allowed, "normal")

            raw_data = {}
            for col in df.columns:
                raw_data[col] = safe_text(row.get(col))

            analysis_values.append((
                comment_id,
                row_video_id,
                batch_id,
                IMPORT_PROVIDER,
                IMPORT_MODEL_NAME,

                sentiment_label,
                safe_float(row.get("positive_score")),
                safe_float(row.get("negative_score")),
                safe_float(row.get("neutral_score")),

                emotion_label,
                safe_float(row.get("emotion_intensity")),

                safe_float(row.get("joy_score")),
                safe_float(row.get("anger_score")),
                safe_float(row.get("sadness_score")),
                safe_float(row.get("fear_score")),
                safe_float(row.get("surprise_score")),
                safe_float(row.get("disgust_score")),

                safe_float(row.get("humor_score")),
                safe_float(row.get("sarcasm_score")),
                safe_float(row.get("toxicity_score")),
                safe_float(row.get("controversy_score")),
                safe_float(row.get("quality_score")),

                comment_category,
                safe_text(row.get("topic")),
                safe_text(row.get("summary")),
                safe_text(row.get("ai_reason")),
                safe_text(row.get("ai_keywords")),

                Json(raw_data),
                now_str(),
                now_str()
            ))

            keywords = split_keywords(row.get("ai_keywords"))

            for keyword in keywords:
                normalized = normalize_keyword(keyword)

                if not normalized:
                    continue

                keyword_values.append((
                    comment_id,
                    row_video_id,
                    keyword,
                    normalized,
                    "AI",
                    "",
                    "",
                    1,
                    Json({"source": "ai_keywords", "raw": safe_text(row.get("ai_keywords"))}),
                    now_str()
                ))

            done_comment_ids.append(comment_id)
            success_count += 1

        if analysis_values:
            sql = """
                  INSERT INTO comment_analysis (
                      comment_id,
                      video_id,
                      batch_id,
                      provider,
                      model_name,
                      sentiment_label,
                      positive_score,
                      negative_score,
                      neutral_score,
                      emotion_label,
                      emotion_intensity,
                      joy_score,
                      anger_score,
                      sadness_score,
                      fear_score,
                      surprise_score,
                      disgust_score,
                      humor_score,
                      sarcasm_score,
                      toxicity_score,
                      controversy_score,
                      quality_score,
                      comment_category,
                      topic,
                      summary,
                      ai_reason,
                      ai_keywords,
                      analysis_result,
                      create_dt,
                      update_dt
                  ) VALUES %s \
                  """

            with conn.cursor() as cur:
                execute_values(cur, sql, analysis_values, page_size=500)

        if keyword_values:
            sql = """
                  INSERT INTO comment_keyword_raw (
                      comment_id,
                      video_id,
                      keyword,
                      normalized_keyword,
                      source_type,
                      keyword_type_code,
                      keyword_type_name,
                      keyword_score,
                      raw_result,
                      create_dt
                  ) VALUES %s
                  ON CONFLICT (comment_id, source_type, normalized_keyword)
                  DO UPDATE SET
                      keyword = EXCLUDED.keyword,
                      keyword_score = EXCLUDED.keyword_score,
                      raw_result = EXCLUDED.raw_result,
                      create_dt = EXCLUDED.create_dt \
                  """

            with conn.cursor() as cur:
                execute_values(cur, sql, keyword_values, page_size=500)

        if done_comment_ids:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE youtube_comment
                    SET
                        analysis_status = 'DONE',
                        keyword_status = 'DONE',
                        update_dt = %s
                    WHERE comment_id = ANY(%s)
                    """,
                    (now_str(), done_comment_ids)
                )

        rebuild_ai_keyword_summary(conn, video_id)
        rebuild_ai_video_keyword(conn, video_id)
        rebuild_ai_keyword_edges(conn, video_id)

        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="DONE",
            success_count=success_count,
            fail_count=fail_count,
            memo="AI 댓글 분석 결과 import 완료"
        )

        print("[완료] AI 댓글 분석 import:", success_count, "건 / 실패:", fail_count, "건")

    except Exception as e:
        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="FAIL",
            success_count=success_count,
            fail_count=fail_count,
            memo=str(e)
        )
        raise


# ==============================
# AI 키워드 요약/집계/연결선 재생성
# ==============================

def rebuild_ai_keyword_summary(conn, video_id):
    print("[집계] comment_keyword_summary AI 갱신")

    with conn.cursor() as cur:
        # AI 쪽 상태 초기화
        cur.execute(
            """
            UPDATE comment_keyword_summary
            SET
                ai_yn = 'N',
                ai_score = 0,
                source_count =
                    (CASE WHEN morph_yn = 'Y' THEN 1 ELSE 0 END),
                update_dt = %s
            WHERE video_id = %s
              AND ai_yn = 'Y'
            """,
            (now_str(), video_id)
        )

        # AI 키워드 반영
        cur.execute(
            """
            INSERT INTO comment_keyword_summary (
                comment_id,
                video_id,
                keyword,
                ai_yn,
                morph_yn,
                source_count,
                ai_score,
                morph_score,
                create_dt,
                update_dt
            )
            SELECT
                comment_id,
                video_id,
                normalized_keyword,
                'Y',
                'N',
                1,
                MAX(keyword_score),
                0,
                %s,
                %s
            FROM comment_keyword_raw
            WHERE video_id = %s
              AND source_type = 'AI'
            GROUP BY comment_id, video_id, normalized_keyword
            ON CONFLICT (comment_id, keyword)
            DO UPDATE SET
                ai_yn = 'Y',
                ai_score = EXCLUDED.ai_score,
                update_dt = EXCLUDED.update_dt
            """,
            (now_str(), now_str(), video_id)
        )

        # source_count 재계산
        cur.execute(
            """
            UPDATE comment_keyword_summary
            SET
                source_count =
                    (CASE WHEN ai_yn = 'Y' THEN 1 ELSE 0 END) +
                    (CASE WHEN morph_yn = 'Y' THEN 1 ELSE 0 END),
                update_dt = %s
            WHERE video_id = %s
            """,
            (now_str(), video_id)
        )


def rebuild_ai_video_keyword(conn, video_id):
    print("[집계] video_keyword AI 갱신")

    with conn.cursor() as cur:
        # 기존 AI 집계 초기화. 형태소 값은 유지.
        cur.execute(
            """
            UPDATE video_keyword
            SET
                ai_yn = 'N',
                ai_count = 0,
                ai_weight_score = 0,
                total_count = morph_count,
                total_weight_score = morph_weight_score,
                positive_count = 0,
                negative_count = 0,
                neutral_count = 0,
                update_dt = %s
            WHERE video_id = %s
            """,
            (now_str(), video_id)
        )

        cur.execute(
            """
            SELECT
                s.keyword,
                COUNT(*) AS ai_count,
                SUM(CASE WHEN a.sentiment_label = 'positive' THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_count,
                SUM(CASE WHEN a.sentiment_label = 'neutral' THEN 1 ELSE 0 END) AS neutral_count
            FROM comment_keyword_summary s
                     LEFT JOIN comment_analysis a
                               ON a.comment_id = s.comment_id
            WHERE s.video_id = %s
              AND s.ai_yn = 'Y'
            GROUP BY s.keyword
            """,
            (video_id,)
        )

        rows = cur.fetchall()

    values = []

    for row in rows:
        keyword = row[0]
        ai_count = int(row[1] or 0)
        positive_count = int(row[2] or 0)
        negative_count = int(row[3] or 0)
        neutral_count = int(row[4] or 0)

        # 1차 버전에서는 count를 그대로 weight로 사용
        ai_weight_score = float(ai_count)

        values.append((
            video_id,
            keyword,
            "Y",
            "N",
            ai_count,
            0,
            ai_count,
            ai_weight_score,
            0,
            ai_weight_score,
            positive_count,
            negative_count,
            neutral_count,
            now_str(),
            now_str()
        ))

    if not values:
        return

    sql = """
          INSERT INTO video_keyword (
              video_id,
              keyword,
              ai_yn,
              morph_yn,
              ai_count,
              morph_count,
              total_count,
              ai_weight_score,
              morph_weight_score,
              total_weight_score,
              positive_count,
              negative_count,
              neutral_count,
              create_dt,
              update_dt
          ) VALUES %s
          ON CONFLICT (video_id, keyword)
          DO UPDATE SET
              ai_yn = 'Y',
              ai_count = EXCLUDED.ai_count,
              ai_weight_score = EXCLUDED.ai_weight_score,
              total_count = EXCLUDED.ai_count + video_keyword.morph_count,
              total_weight_score = EXCLUDED.ai_weight_score + video_keyword.morph_weight_score,
              positive_count = EXCLUDED.positive_count,
              negative_count = EXCLUDED.negative_count,
              neutral_count = EXCLUDED.neutral_count,
              update_dt = EXCLUDED.update_dt \
          """

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)


def rebuild_ai_keyword_edges(conn, video_id):
    print("[집계] keyword_edge AI 갱신")

    with conn.cursor() as cur:
        # 기존 AI 연결값 초기화. 형태소 값은 유지.
        cur.execute(
            """
            UPDATE keyword_edge
            SET
                ai_yn = 'N',
                ai_edge_count = 0,
                ai_weight_score = 0,
                total_edge_count = morph_edge_count,
                total_weight_score = morph_weight_score,
                positive_count = 0,
                negative_count = 0,
                neutral_count = 0,
                update_dt = %s
            WHERE video_id = %s
            """,
            (now_str(), video_id)
        )

        cur.execute(
            """
            SELECT
                s.comment_id,
                s.keyword,
                COALESCE(a.sentiment_label, 'neutral') AS sentiment_label
            FROM comment_keyword_summary s
                     LEFT JOIN comment_analysis a
                               ON a.comment_id = s.comment_id
            WHERE s.video_id = %s
              AND s.ai_yn = 'Y'
            ORDER BY s.comment_id, s.keyword
            """,
            (video_id,)
        )

        rows = cur.fetchall()

    comment_map = defaultdict(list)
    sentiment_map = {}

    for comment_id, keyword, sentiment_label in rows:
        if keyword not in comment_map[comment_id]:
            comment_map[comment_id].append(keyword)
        sentiment_map[comment_id] = sentiment_label

    edge_map = {}

    for comment_id, keywords in comment_map.items():
        if len(keywords) < 2:
            continue

        # 한 댓글에서 키워드가 너무 많으면 네트워크가 지저분해지므로 상위 10개까지만 사용
        keywords = sorted(keywords)[:10]
        sentiment_label = sentiment_map.get(comment_id, "neutral")

        for a, b in combinations(keywords, 2):
            source_keyword = a
            target_keyword = b

            key = (source_keyword, target_keyword)

            if key not in edge_map:
                edge_map[key] = {
                    "count": 0,
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0
                }

            edge_map[key]["count"] += 1

            if sentiment_label == "positive":
                edge_map[key]["positive"] += 1
            elif sentiment_label == "negative":
                edge_map[key]["negative"] += 1
            else:
                edge_map[key]["neutral"] += 1

    values = []

    for (source_keyword, target_keyword), info in edge_map.items():
        count = info["count"]
        weight_score = float(count)

        values.append((
            video_id,
            source_keyword,
            target_keyword,
            "Y",
            "N",
            count,
            0,
            count,
            weight_score,
            0,
            weight_score,
            info["positive"],
            info["negative"],
            info["neutral"],
            now_str(),
            now_str()
        ))

    if not values:
        return

    sql = """
          INSERT INTO keyword_edge (
              video_id,
              source_keyword,
              target_keyword,
              ai_yn,
              morph_yn,
              ai_edge_count,
              morph_edge_count,
              total_edge_count,
              ai_weight_score,
              morph_weight_score,
              total_weight_score,
              positive_count,
              negative_count,
              neutral_count,
              create_dt,
              update_dt
          ) VALUES %s
          ON CONFLICT (video_id, source_keyword, target_keyword)
          DO UPDATE SET
              ai_yn = 'Y',
              ai_edge_count = EXCLUDED.ai_edge_count,
              ai_weight_score = EXCLUDED.ai_weight_score,
              total_edge_count = EXCLUDED.ai_edge_count + keyword_edge.morph_edge_count,
              total_weight_score = EXCLUDED.ai_weight_score + keyword_edge.morph_weight_score,
              positive_count = EXCLUDED.positive_count,
              negative_count = EXCLUDED.negative_count,
              neutral_count = EXCLUDED.neutral_count,
              update_dt = EXCLUDED.update_dt \
          """

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)


# ==============================
# 2. 의심 댓글 분석 결과 import
# ==============================

def import_suspicion_analysis(conn, csv_path):
    print("")
    print("[의심 댓글 분석 결과 import]", csv_path)

    df = read_csv(csv_path)

    if df.empty:
        print("[건너뜀] 의심 댓글 분석 결과 CSV가 비어 있습니다.")
        return

    required_cols = [
        "comment_id",
        "is_suspicious",
        "suspicion_label",
        "auto_comment_score",
        "ai_generated_score",
        "comment_farm_score",
        "political_related_score",
        "propaganda_score",
        "spam_score",
        "repeated_pattern_score",
        "coordinated_score",
        "political_topic",
        "political_target",
        "evidence_text",
        "ai_reason"
    ]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError("의심 댓글 분석 결과 CSV에 필요한 컬럼이 없습니다: " + col)

    comment_ids = [safe_text(x) for x in df["comment_id"].tolist() if safe_text(x)]
    comment_ids = list(dict.fromkeys(comment_ids))

    comment_video_map = get_comment_video_map(conn, comment_ids)
    video_id = get_video_id_from_comments(conn, comment_ids)

    batch_id = create_batch(
        conn=conn,
        video_id=video_id,
        batch_type="SUSPICION_AI_IMPORT",
        import_file_name=str(csv_path),
        target_count=len(df),
        memo="의심 댓글 분석 결과 CSV import"
    )

    success_count = 0
    fail_count = 0

    try:
        if REPLACE_EXISTING:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM comment_suspicion_analysis WHERE comment_id = ANY(%s)",
                    (comment_ids,)
                )

        values = []
        done_comment_ids = []

        for _, row in df.iterrows():
            comment_id = safe_text(row.get("comment_id"))

            if not comment_id:
                fail_count += 1
                continue

            row_video_id = comment_video_map.get(comment_id)

            if not row_video_id:
                print("[경고] DB에 없는 comment_id 건너뜀:", comment_id)
                fail_count += 1
                continue

            raw_data = {}
            for col in df.columns:
                raw_data[col] = safe_text(row.get(col))

            values.append((
                comment_id,
                row_video_id,
                batch_id,
                IMPORT_PROVIDER,
                IMPORT_MODEL_NAME,

                safe_yn(row.get("is_suspicious")),
                normalize_suspicion_label(row.get("suspicion_label")),

                safe_float(row.get("auto_comment_score")),
                safe_float(row.get("ai_generated_score")),
                safe_float(row.get("comment_farm_score")),
                safe_float(row.get("political_related_score")),
                safe_float(row.get("propaganda_score")),
                safe_float(row.get("spam_score")),
                safe_float(row.get("repeated_pattern_score")),
                safe_float(row.get("coordinated_score")),

                safe_text(row.get("political_topic")),
                safe_text(row.get("political_target")),
                safe_text(row.get("evidence_text")),
                safe_text(row.get("ai_reason")),

                Json(raw_data),
                now_str(),
                now_str()
            ))

            done_comment_ids.append(comment_id)
            success_count += 1

        if values:
            sql = """
                  INSERT INTO comment_suspicion_analysis (
                      comment_id,
                      video_id,
                      batch_id,
                      provider,
                      model_name,
                      is_suspicious,
                      suspicion_label,
                      auto_comment_score,
                      ai_generated_score,
                      comment_farm_score,
                      political_related_score,
                      propaganda_score,
                      spam_score,
                      repeated_pattern_score,
                      coordinated_score,
                      political_topic,
                      political_target,
                      evidence_text,
                      ai_reason,
                      analysis_result,
                      create_dt,
                      update_dt
                  ) VALUES %s \
                  """

            with conn.cursor() as cur:
                execute_values(cur, sql, values, page_size=500)

        if done_comment_ids:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE youtube_comment
                    SET
                        suspicion_status = 'DONE',
                        update_dt = %s
                    WHERE comment_id = ANY(%s)
                    """,
                    (now_str(), done_comment_ids)
                )

        update_suspicion_timeseries(conn, video_id)

        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="DONE",
            success_count=success_count,
            fail_count=fail_count,
            memo="의심 댓글 분석 결과 import 완료"
        )

        print("[완료] 의심 댓글 분석 import:", success_count, "건 / 실패:", fail_count, "건")

    except Exception as e:
        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="FAIL",
            success_count=success_count,
            fail_count=fail_count,
            memo=str(e)
        )
        raise


# ==============================
# 3. 영상 요약 결과 import
# ==============================

def import_video_summary(conn, csv_path):
    print("")
    print("[영상 요약 결과 import]", csv_path)

    df = read_csv(csv_path)

    if df.empty:
        print("[건너뜀] 영상 요약 결과 CSV가 비어 있습니다.")
        return

    required_cols = [
        "video_id",
        "summary_short",
        "summary_long",
        "main_topic",
        "sub_topics",
        "video_keywords",
        "content_category",
        "target_audience",
        "issue_points",
        "ai_reason"
    ]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError("영상 요약 결과 CSV에 필요한 컬럼이 없습니다: " + col)

    first_video_id = safe_text(df.iloc[0].get("video_id"))

    if not first_video_id:
        if not VIDEO_ID:
            raise ValueError("영상 요약 CSV에 video_id가 없고 .env VIDEO_ID도 없습니다.")
        first_video_id = VIDEO_ID

    batch_id = create_batch(
        conn=conn,
        video_id=first_video_id,
        batch_type="VIDEO_SUMMARY_IMPORT",
        import_file_name=str(csv_path),
        target_count=len(df),
        memo="영상 요약 결과 CSV import"
    )

    success_count = 0
    fail_count = 0

    try:
        if REPLACE_EXISTING:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM video_content_analysis WHERE video_id = %s",
                    (first_video_id,)
                )

        values = []

        for _, row in df.iterrows():
            video_id = safe_text(row.get("video_id"))

            if not video_id:
                video_id = first_video_id

            raw_data = {}
            for col in df.columns:
                raw_data[col] = safe_text(row.get(col))

            values.append((
                video_id,
                batch_id,
                IMPORT_PROVIDER,
                IMPORT_MODEL_NAME,
                "DESCRIPTION",
                "",
                safe_text(row.get("summary_short")),
                safe_text(row.get("summary_long")),
                safe_text(row.get("main_topic")),
                safe_text(row.get("sub_topics")),
                safe_text(row.get("video_keywords")),
                safe_text(row.get("content_category")),
                safe_text(row.get("target_audience")),
                safe_text(row.get("issue_points")),
                safe_text(row.get("ai_reason")),
                Json(raw_data),
                now_str(),
                now_str()
            ))

            success_count += 1

        sql = """
              INSERT INTO video_content_analysis (
                  video_id,
                  batch_id,
                  provider,
                  model_name,
                  transcript_source,
                  transcript_text,
                  summary_short,
                  summary_long,
                  main_topic,
                  sub_topics,
                  video_keywords,
                  content_category,
                  target_audience,
                  issue_points,
                  ai_reason,
                  analysis_result,
                  create_dt,
                  update_dt
              ) VALUES %s \
              """

        with conn.cursor() as cur:
            execute_values(cur, sql, values, page_size=100)

        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="DONE",
            success_count=success_count,
            fail_count=fail_count,
            memo="영상 요약 결과 import 완료"
        )

        print("[완료] 영상 요약 import:", success_count, "건")

    except Exception as e:
        finish_batch(
            conn=conn,
            batch_id=batch_id,
            status="FAIL",
            success_count=success_count,
            fail_count=fail_count,
            memo=str(e)
        )
        raise


# ==============================
# 4. 시간별 집계 생성/갱신
# ==============================

def rebuild_comment_timeseries(conn, video_id):
    print("[집계] video_comment_timeseries 시간/일자 갱신")

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM video_comment_timeseries WHERE video_id = %s",
            (video_id,)
        )

        # 시간별
        cur.execute(
            """
            INSERT INTO video_comment_timeseries (
                video_id,
                time_unit,
                time_bucket,
                total_count,
                top_comment_count,
                reply_count,
                positive_count,
                negative_count,
                neutral_count,
                joy_count,
                anger_count,
                sadness_count,
                fear_count,
                surprise_count,
                disgust_count,
                create_dt,
                update_dt
            )
            SELECT
                c.video_id,
                'hour',
                DATE_TRUNC('hour', c.published_at),
                COUNT(*),
                SUM(CASE WHEN c.comment_type = '원댓글' THEN 1 ELSE 0 END),
                SUM(CASE WHEN c.comment_type = '대댓글' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'positive' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'neutral' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'joy' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'anger' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'sadness' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'fear' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'surprise' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'disgust' THEN 1 ELSE 0 END),
                %s,
                %s
            FROM youtube_comment c
                     LEFT JOIN comment_analysis a
                               ON a.comment_id = c.comment_id
            WHERE c.video_id = %s
              AND c.published_at IS NOT NULL
            GROUP BY c.video_id, DATE_TRUNC('hour', c.published_at)
            """,
            (now_str(), now_str(), video_id)
        )

        # 날짜별
        cur.execute(
            """
            INSERT INTO video_comment_timeseries (
                video_id,
                time_unit,
                time_bucket,
                total_count,
                top_comment_count,
                reply_count,
                positive_count,
                negative_count,
                neutral_count,
                joy_count,
                anger_count,
                sadness_count,
                fear_count,
                surprise_count,
                disgust_count,
                create_dt,
                update_dt
            )
            SELECT
                c.video_id,
                'day',
                DATE_TRUNC('day', c.published_at),
                COUNT(*),
                SUM(CASE WHEN c.comment_type = '원댓글' THEN 1 ELSE 0 END),
                SUM(CASE WHEN c.comment_type = '대댓글' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'positive' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.sentiment_label = 'neutral' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'joy' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'anger' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'sadness' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'fear' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'surprise' THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.emotion_label = 'disgust' THEN 1 ELSE 0 END),
                %s,
                %s
            FROM youtube_comment c
                     LEFT JOIN comment_analysis a
                               ON a.comment_id = c.comment_id
            WHERE c.video_id = %s
              AND c.published_at IS NOT NULL
            GROUP BY c.video_id, DATE_TRUNC('day', c.published_at)
            """,
            (now_str(), now_str(), video_id)
        )


def update_suspicion_timeseries(conn, video_id):
    print("[집계] video_comment_timeseries 의심 댓글 수 갱신")

    with conn.cursor() as cur:
        # 시간별 의심 댓글 갱신
        cur.execute(
            """
            UPDATE video_comment_timeseries t
            SET
                suspicious_count = s.suspicious_count,
                political_count = s.political_count,
                ai_generated_count = s.ai_generated_count,
                update_dt = %s
                FROM (
                         SELECT
                             DATE_TRUNC('hour', c.published_at) AS bucket,
                             COUNT(CASE WHEN sa.is_suspicious = 'Y' THEN 1 END) AS suspicious_count,
                             COUNT(CASE WHEN sa.political_related_score >= 0.5 THEN 1 END) AS political_count,
                             COUNT(CASE WHEN sa.ai_generated_score >= 0.5 THEN 1 END) AS ai_generated_count
                         FROM youtube_comment c
                                  JOIN comment_suspicion_analysis sa
                                       ON sa.comment_id = c.comment_id
                         WHERE c.video_id = %s
                           AND c.published_at IS NOT NULL
                         GROUP BY DATE_TRUNC('hour', c.published_at)
                     ) s
            WHERE t.video_id = %s
                     AND t.time_unit = 'hour'
                     AND t.time_bucket = s.bucket
            """,
            (now_str(), video_id, video_id)
        )

        # 날짜별 의심 댓글 갱신
        cur.execute(
            """
            UPDATE video_comment_timeseries t
            SET
                suspicious_count = s.suspicious_count,
                political_count = s.political_count,
                ai_generated_count = s.ai_generated_count,
                update_dt = %s
                FROM (
                         SELECT
                             DATE_TRUNC('day', c.published_at) AS bucket,
                             COUNT(CASE WHEN sa.is_suspicious = 'Y' THEN 1 END) AS suspicious_count,
                             COUNT(CASE WHEN sa.political_related_score >= 0.5 THEN 1 END) AS political_count,
                             COUNT(CASE WHEN sa.ai_generated_score >= 0.5 THEN 1 END) AS ai_generated_count
                         FROM youtube_comment c
                                  JOIN comment_suspicion_analysis sa
                                       ON sa.comment_id = c.comment_id
                         WHERE c.video_id = %s
                           AND c.published_at IS NOT NULL
                         GROUP BY DATE_TRUNC('day', c.published_at)
                     ) s
            WHERE t.video_id = %s
                     AND t.time_unit = 'day'
                     AND t.time_bucket = s.bucket
            """,
            (now_str(), video_id, video_id)
        )


# ==============================
# 결과 파일 자동 탐색/병합
# ==============================

def resolve_result_files(explicit_file, explicit_dir, default_sub_dir, legacy_file_name, pattern):
    """
    AI 결과 CSV를 찾는다.

    우선순위:
    1. .env에 직접 파일 경로 지정
    2. .env에 결과 폴더 지정
    3. output/VIDEO_ID/default_sub_dir 폴더에서 pattern 검색
    4. 예전 방식 output/VIDEO_ID/legacy_file_name 검색
    """
    paths = []

    if explicit_file:
        # 여러 파일을 ; 로 직접 지정해도 허용
        for item in explicit_file.split(";"):
            item = item.strip()
            if item:
                p = Path(item).resolve()
                if p.exists():
                    paths.append(p)
        return sorted(paths)

    if explicit_dir:
        d = Path(explicit_dir).resolve()
        if d.exists():
            return sorted(d.glob(pattern))
        return []

    if VIDEO_ID:
        video_dir = OUTPUT_DIR / VIDEO_ID

        d = video_dir / default_sub_dir
        if d.exists():
            paths = sorted(d.glob(pattern))
            if paths:
                return paths

        legacy = video_dir / legacy_file_name
        if legacy.exists():
            return [legacy]

    return []


def combine_csv_files(paths, combined_path):
    """
    AI 결과 CSV가 여러 개이면 하나로 합친 임시 CSV를 만든다.
    1개이면 그대로 사용한다.
    """
    if not paths:
        return None

    if len(paths) == 1:
        return paths[0]

    frames = []

    for path in paths:
        df = read_csv(path)

        if df.empty:
            continue

        frames.append(df)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(combined_path, index=False, encoding="utf-8-sig")

    print("[병합 완료]", combined_path, "/ 파일 수:", len(paths), "/ 행 수:", len(combined))

    return combined_path


# ==============================
# 실행
# ==============================

def main():
    comment_paths = resolve_result_files(
        explicit_file=AI_COMMENT_RESULT_CSV,
        explicit_dir=AI_COMMENT_RESULT_DIR,
        default_sub_dir="ai_comment_results",
        legacy_file_name="07_ai_comment_analysis_result.csv",
        pattern="07_ai_comment_analysis_result*.csv"
    )

    suspicion_paths = resolve_result_files(
        explicit_file=AI_SUSPICION_RESULT_CSV,
        explicit_dir=AI_SUSPICION_RESULT_DIR,
        default_sub_dir="ai_suspicion_results",
        legacy_file_name="08_ai_suspicion_analysis_result.csv",
        pattern="08_ai_suspicion_analysis_result*.csv"
    )

    video_paths = resolve_result_files(
        explicit_file=AI_VIDEO_SUMMARY_RESULT_CSV,
        explicit_dir=AI_VIDEO_SUMMARY_RESULT_DIR,
        default_sub_dir="ai_video_summary_results",
        legacy_file_name="09_ai_video_summary_result.csv",
        pattern="09_ai_video_summary_result*.csv"
    )

    print("[설정]")
    print("VIDEO_ID:", VIDEO_ID)
    print("OUTPUT_DIR:", OUTPUT_DIR)
    print("REPLACE_EXISTING:", "Y" if REPLACE_EXISTING else "N")
    print("AI 댓글 결과 파일 수:", len(comment_paths))
    print("AI 의심 결과 파일 수:", len(suspicion_paths))
    print("AI 영상 요약 결과 파일 수:", len(video_paths))

    if comment_paths:
        for p in comment_paths:
            print(" - COMMENT:", p)

    if suspicion_paths:
        for p in suspicion_paths:
            print(" - SUSPICION:", p)

    if video_paths:
        for p in video_paths:
            print(" - VIDEO:", p)

    conn = get_conn()
    imported_video_ids = set()

    try:
        combined_dir = OUTPUT_DIR / (VIDEO_ID if VIDEO_ID else "_combined")
        combined_dir.mkdir(parents=True, exist_ok=True)

        # 댓글 AI 분석 결과
        if comment_paths:
            comment_csv = combine_csv_files(
                comment_paths,
                combined_dir / "_combined_07_ai_comment_analysis_result.csv"
            )

            if comment_csv:
                import_comment_analysis(conn, comment_csv)

                if VIDEO_ID:
                    imported_video_ids.add(VIDEO_ID)
                else:
                    df = read_csv(comment_csv)
                    ids = [safe_text(x) for x in df["comment_id"].tolist() if safe_text(x)]
                    imported_video_ids.add(get_video_id_from_comments(conn, ids))
        else:
            print("[건너뜀] AI 댓글 분석 결과 파일 없음")

        # 의심 댓글 분석 결과
        if suspicion_paths:
            suspicion_csv = combine_csv_files(
                suspicion_paths,
                combined_dir / "_combined_08_ai_suspicion_analysis_result.csv"
            )

            if suspicion_csv:
                import_suspicion_analysis(conn, suspicion_csv)

                if VIDEO_ID:
                    imported_video_ids.add(VIDEO_ID)
                else:
                    df = read_csv(suspicion_csv)
                    ids = [safe_text(x) for x in df["comment_id"].tolist() if safe_text(x)]
                    imported_video_ids.add(get_video_id_from_comments(conn, ids))
        else:
            print("[건너뜀] 의심 댓글 분석 결과 파일 없음")

        # 영상 요약 결과
        if video_paths:
            video_csv = combine_csv_files(
                video_paths,
                combined_dir / "_combined_09_ai_video_summary_result.csv"
            )

            if video_csv:
                import_video_summary(conn, video_csv)

                df = read_csv(video_csv)
                if "video_id" in df.columns and len(df) > 0:
                    imported_video_ids.add(safe_text(df.iloc[0].get("video_id")))
        else:
            print("[건너뜀] 영상 요약 결과 파일 없음")

        # 시간 집계 재생성
        for video_id in imported_video_ids:
            if video_id:
                rebuild_comment_timeseries(conn, video_id)
                update_suspicion_timeseries(conn, video_id)

        conn.commit()

        print("")
        print("[전체 완료] AI 결과 CSV import 완료")

    except Exception as e:
        conn.rollback()
        print("[오류] import 실패:", str(e))
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
