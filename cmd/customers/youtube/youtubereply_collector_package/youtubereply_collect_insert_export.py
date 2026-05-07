import os
import re
import csv
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube 댓글 수집 → PostgreSQL INSERT → AI 분석용 CSV 생성
# ============================================================
#
# 실행 전 준비:
# 1) PostgreSQL에 youtubereply DB 생성
# 2) youtubereply_postgresql_schema.sql 실행
# 3) .env 파일 생성
# 4) pip install -r requirements.txt
#
# 실행:
# python youtubereply_collect_insert_export.py
#
# ============================================================


# ==============================
# 공통 유틸
# ==============================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_int(value):
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_text(value):
    if value is None:
        return ""
    return str(value)


def parse_datetime(value):
    """
    YouTube API 시간 문자열을 PostgreSQL TIMESTAMPTZ에 넣기 위한 값으로 그대로 반환.
    예: 2026-05-07T12:00:00Z
    psycopg2가 PostgreSQL에 전달하면 TIMESTAMPTZ로 변환 가능.
    """
    if not value:
        return None
    return value


def get_video_id(url):
    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?&]+)",
        r"shorts/([^?&]+)",
        r"embed/([^?&]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return url


def short_hash(value):
    """
    작성자 채널 ID를 그대로 AI CSV에 넘기지 않기 위해 해시 처리.
    동일 작성자 패턴 분석은 가능하지만, 원본 ID는 숨김.
    """
    value = safe_text(value)
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


# ==============================
# 환경설정
# ==============================

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
VIDEO_URL = os.getenv("VIDEO_URL", "").strip()

MAX_TOP_COMMENTS_RAW = os.getenv("MAX_TOP_COMMENTS", "").strip()
MAX_TOP_COMMENTS = None
if MAX_TOP_COMMENTS_RAW:
    MAX_TOP_COMMENTS = int(MAX_TOP_COMMENTS_RAW)

COMMENT_ORDER = os.getenv("COMMENT_ORDER", "relevance").strip()
SLEEP_SEC = float(os.getenv("SLEEP_SEC", "0.1"))

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output")).resolve()
AI_CHUNK_SIZE = int(os.getenv("AI_CHUNK_SIZE", "500"))

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
# YouTube API 요청
# ==============================

def get_json(url, params):
    try:
        res = requests.get(url, params=params, timeout=30)
        data = res.json()
    except Exception as e:
        print("[요청 오류]", str(e))
        return None

    if "error" in data:
        print("[API 오류]")
        print(json.dumps(data["error"], ensure_ascii=False, indent=2))
        return None

    return data


# ==============================
# 영상 정보 수집
# ==============================

def fetch_video_info(video_id):
    params = {
        "key": API_KEY,
        "part": "snippet,statistics",
        "id": video_id
    }

    data = get_json(
        "https://www.googleapis.com/youtube/v3/videos",
        params
    )

    if not data:
        return {}

    items = data.get("items", [])

    if not items:
        return {}

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    thumbnails = snippet.get("thumbnails", {})

    thumbnail_url = ""
    if "maxres" in thumbnails:
        thumbnail_url = thumbnails.get("maxres", {}).get("url", "")
    elif "high" in thumbnails:
        thumbnail_url = thumbnails.get("high", {}).get("url", "")
    elif "default" in thumbnails:
        thumbnail_url = thumbnails.get("default", {}).get("url", "")

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "channel_id": snippet.get("channelId", ""),
        "video_url": "https://www.youtube.com/watch?v=" + video_id,
        "thumbnail_url": thumbnail_url,
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": safe_int(statistics.get("viewCount", 0)),
        "like_count": safe_int(statistics.get("likeCount", 0)),
        "comment_count": safe_int(statistics.get("commentCount", 0)),
        "comment_order": COMMENT_ORDER,
        "collected_at": now_str(),
        "raw_json": item
    }


# ==============================
# 대댓글 전체 수집
# ==============================

def fetch_replies(video_id, parent_comment_id, top_no):
    rows = []
    page_token = ""
    reply_no = 0

    while True:
        params = {
            "key": API_KEY,
            "part": "snippet",
            "parentId": parent_comment_id,
            "maxResults": 100,
            "textFormat": "plainText"
        }

        if page_token:
            params["pageToken"] = page_token

        data = get_json(
            "https://www.googleapis.com/youtube/v3/comments",
            params
        )

        if not data:
            break

        items = data.get("items", [])

        for item in items:
            snippet = item.get("snippet", {})
            author_channel_id = snippet.get("authorChannelId", {})
            reply_no += 1

            comment_id = item.get("id", "")

            row = {
                "comment_id": comment_id,
                "video_id": video_id,

                "parent_comment_id": parent_comment_id,
                "root_comment_id": parent_comment_id,

                "top_comment_no": top_no,
                "reply_no": reply_no,

                "comment_depth": 2,
                "comment_type": "대댓글",
                "sort_no": str(top_no) + "-" + str(reply_no),

                "author_name": snippet.get("authorDisplayName", ""),
                "author_channel_id": author_channel_id.get("value", ""),
                "author_channel_url": snippet.get("authorChannelUrl", ""),
                "author_profile_image": snippet.get("authorProfileImageUrl", ""),

                "comment_text": snippet.get("textDisplay", ""),
                "comment_original": snippet.get("textOriginal", ""),

                "like_count": safe_int(snippet.get("likeCount", 0)),
                "reply_count": 0,

                "published_at": snippet.get("publishedAt", ""),
                "updated_at": snippet.get("updatedAt", ""),

                "can_rate": safe_text(snippet.get("canRate", "")),
                "viewer_rating": snippet.get("viewerRating", ""),

                "is_public": "",
                "can_reply": "",

                "is_top_comment": "N",
                "is_reply": "Y",

                "raw_json": item
            }

            rows.append(row)

        page_token = data.get("nextPageToken", "")

        if not page_token:
            break

        time.sleep(SLEEP_SEC)

    return rows


# ==============================
# 원댓글 + 대댓글 전체 수집
# ==============================

def fetch_comments(video_id):
    rows = []
    top_count = 0
    page_token = ""

    while True:
        print("[원댓글 수집]", top_count)

        params = {
            "key": API_KEY,
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "order": COMMENT_ORDER,
            "textFormat": "plainText"
        }

        if page_token:
            params["pageToken"] = page_token

        data = get_json(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params
        )

        if not data:
            break

        items = data.get("items", [])

        if not items:
            break

        for item in items:
            snippet = item.get("snippet", {})
            top_comment = snippet.get("topLevelComment", {})
            top_snippet = top_comment.get("snippet", {})
            author_channel_id = top_snippet.get("authorChannelId", {})

            top_count += 1

            comment_id = top_comment.get("id", "")
            reply_count = safe_int(snippet.get("totalReplyCount", 0))

            row = {
                "comment_id": comment_id,
                "video_id": video_id,

                # 원댓글은 부모댓글ID를 자기 자신으로 넣음
                "parent_comment_id": comment_id,
                "root_comment_id": comment_id,

                "top_comment_no": top_count,
                "reply_no": 0,

                "comment_depth": 1,
                "comment_type": "원댓글",
                "sort_no": str(top_count),

                "author_name": top_snippet.get("authorDisplayName", ""),
                "author_channel_id": author_channel_id.get("value", ""),
                "author_channel_url": top_snippet.get("authorChannelUrl", ""),
                "author_profile_image": top_snippet.get("authorProfileImageUrl", ""),

                "comment_text": top_snippet.get("textDisplay", ""),
                "comment_original": top_snippet.get("textOriginal", ""),

                "like_count": safe_int(top_snippet.get("likeCount", 0)),
                "reply_count": reply_count,

                "published_at": top_snippet.get("publishedAt", ""),
                "updated_at": top_snippet.get("updatedAt", ""),

                "can_rate": safe_text(top_snippet.get("canRate", "")),
                "viewer_rating": top_snippet.get("viewerRating", ""),

                "is_public": safe_text(snippet.get("isPublic", "")),
                "can_reply": safe_text(snippet.get("canReply", "")),

                "is_top_comment": "Y",
                "is_reply": "N",

                "raw_json": item
            }

            rows.append(row)

            print(
                "  - 원댓글:",
                top_count,
                "/ 좋아요:",
                row["like_count"],
                "/ 대댓글:",
                reply_count
            )

            if reply_count > 0:
                reply_rows = fetch_replies(video_id, comment_id, top_count)
                rows.extend(reply_rows)
                print("    ㄴ 대댓글 수집:", len(reply_rows), "개")

            if MAX_TOP_COMMENTS is not None:
                if top_count >= MAX_TOP_COMMENTS:
                    return rows

            time.sleep(SLEEP_SEC)

        page_token = data.get("nextPageToken", "")

        if not page_token:
            break

    return rows


# ==============================
# DB INSERT
# ==============================

def insert_video(conn, video_info):
    sql = """
          INSERT INTO youtube_video (
              video_id,
              title,
              channel_title,
              channel_id,
              video_url,
              thumbnail_url,
              description,
              published_at,
              view_count,
              like_count,
              comment_count,
              comment_order,
              collected_at,
              raw_json,
              create_dt,
              update_dt
          ) VALUES (
                       %(video_id)s,
                       %(title)s,
                       %(channel_title)s,
                       %(channel_id)s,
                       %(video_url)s,
                       %(thumbnail_url)s,
                       %(description)s,
                       %(published_at)s,
                       %(view_count)s,
                       %(like_count)s,
                       %(comment_count)s,
                       %(comment_order)s,
                       %(collected_at)s,
                       %(raw_json)s,
                       %(create_dt)s,
                       %(update_dt)s
                   )
          ON CONFLICT (video_id)
          DO UPDATE SET
              title = EXCLUDED.title,
              channel_title = EXCLUDED.channel_title,
              channel_id = EXCLUDED.channel_id,
              video_url = EXCLUDED.video_url,
              thumbnail_url = EXCLUDED.thumbnail_url,
              description = EXCLUDED.description,
              published_at = EXCLUDED.published_at,
              view_count = EXCLUDED.view_count,
              like_count = EXCLUDED.like_count,
              comment_count = EXCLUDED.comment_count,
              comment_order = EXCLUDED.comment_order,
              collected_at = EXCLUDED.collected_at,
              raw_json = EXCLUDED.raw_json,
              update_dt = EXCLUDED.update_dt \
          """

    data = dict(video_info)
    data["published_at"] = parse_datetime(video_info.get("published_at"))
    data["raw_json"] = Json(video_info.get("raw_json", {}))
    data["create_dt"] = now_str()
    data["update_dt"] = now_str()

    with conn.cursor() as cur:
        cur.execute(sql, data)


def insert_comments(conn, rows):
    if not rows:
        return

    sql = """
          INSERT INTO youtube_comment (
              comment_id,
              video_id,
              parent_comment_id,
              root_comment_id,
              top_comment_no,
              reply_no,
              comment_depth,
              comment_type,
              sort_no,
              author_name,
              author_channel_id,
              author_channel_url,
              author_profile_image,
              comment_text,
              comment_original,
              like_count,
              reply_count,
              published_at,
              updated_at,
              can_rate,
              viewer_rating,
              is_public,
              can_reply,
              is_top_comment,
              is_reply,
              analysis_status,
              keyword_status,
              suspicion_status,
              raw_json,
              create_dt,
              update_dt
          ) VALUES %s
          ON CONFLICT (comment_id)
          DO UPDATE SET
              video_id = EXCLUDED.video_id,
              parent_comment_id = EXCLUDED.parent_comment_id,
              root_comment_id = EXCLUDED.root_comment_id,
              top_comment_no = EXCLUDED.top_comment_no,
              reply_no = EXCLUDED.reply_no,
              comment_depth = EXCLUDED.comment_depth,
              comment_type = EXCLUDED.comment_type,
              sort_no = EXCLUDED.sort_no,
              author_name = EXCLUDED.author_name,
              author_channel_id = EXCLUDED.author_channel_id,
              author_channel_url = EXCLUDED.author_channel_url,
              author_profile_image = EXCLUDED.author_profile_image,
              comment_text = EXCLUDED.comment_text,
              comment_original = EXCLUDED.comment_original,
              like_count = EXCLUDED.like_count,
              reply_count = EXCLUDED.reply_count,
              published_at = EXCLUDED.published_at,
              updated_at = EXCLUDED.updated_at,
              can_rate = EXCLUDED.can_rate,
              viewer_rating = EXCLUDED.viewer_rating,
              is_public = EXCLUDED.is_public,
              can_reply = EXCLUDED.can_reply,
              is_top_comment = EXCLUDED.is_top_comment,
              is_reply = EXCLUDED.is_reply,
              raw_json = EXCLUDED.raw_json,
              update_dt = EXCLUDED.update_dt \
          """

    values = []

    for row in rows:
        values.append((
            row.get("comment_id"),
            row.get("video_id"),
            row.get("parent_comment_id"),
            row.get("root_comment_id"),
            safe_int(row.get("top_comment_no")),
            safe_int(row.get("reply_no")),
            safe_int(row.get("comment_depth")),
            row.get("comment_type"),
            row.get("sort_no"),
            row.get("author_name"),
            row.get("author_channel_id"),
            row.get("author_channel_url"),
            row.get("author_profile_image"),
            row.get("comment_text"),
            row.get("comment_original"),
            safe_int(row.get("like_count")),
            safe_int(row.get("reply_count")),
            parse_datetime(row.get("published_at")),
            parse_datetime(row.get("updated_at")),
            row.get("can_rate"),
            row.get("viewer_rating"),
            row.get("is_public"),
            row.get("can_reply"),
            row.get("is_top_comment"),
            row.get("is_reply"),
            "READY",
            "READY",
            "READY",
            Json(row.get("raw_json", {})),
            now_str(),
            now_str()
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)


def insert_comment_metric_snapshots(conn, rows):
    if not rows:
        return

    sql = """
          INSERT INTO comment_metric_snapshot (
              comment_id,
              video_id,
              like_count,
              reply_count,
              collected_at,
              create_dt
          ) VALUES %s \
          """

    collected_at = now_str()
    values = []

    for row in rows:
        values.append((
            row.get("comment_id"),
            row.get("video_id"),
            safe_int(row.get("like_count")),
            safe_int(row.get("reply_count")),
            collected_at,
            now_str()
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)


def insert_analysis_batch(conn, video_id, batch_type, provider, model_name, export_file_name, target_count, memo):
    sql = """
          INSERT INTO analysis_batch (
              video_id,
              batch_type,
              provider,
              model_name,
              export_file_name,
              status,
              target_count,
              success_count,
              fail_count,
              memo,
              create_dt,
              update_dt
          ) VALUES (
                       %s, %s, %s, %s, %s,
                       'DONE',
                       %s, %s, 0,
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
                provider,
                model_name,
                export_file_name,
                target_count,
                target_count,
                memo,
                now_str(),
                now_str()
            )
        )
        return cur.fetchone()[0]


# ==============================
# CSV Export
# ==============================

def save_split_csv(df, out_dir, prefix, chunk_size):
    """
    AI에게 한 번에 너무 많은 댓글을 주면 누락/잘림이 생길 수 있으므로
    CSV를 chunk_size 단위로 나눠서 저장한다.

    예:
    02_ai_comment_analysis_input_001.csv
    02_ai_comment_analysis_input_002.csv
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    files = []

    if df.empty:
        return files

    if chunk_size <= 0:
        chunk_size = 500

    total = len(df)
    chunk_no = 0

    for start in range(0, total, chunk_size):
        chunk_no += 1
        part = df.iloc[start:start + chunk_size].copy()

        file_path = out_dir / (prefix + "_" + str(chunk_no).zfill(3) + ".csv")
        part.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_ALL
        )

        files.append(file_path)

    return files



def make_df(video_info, rows):
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = df.sort_values(
        by=["top_comment_no", "comment_depth", "reply_no"],
        ascending=[True, True, True]
    )

    return df


def export_csv_files(video_info, rows):
    video_id = video_info.get("video_id")
    out_dir = OUTPUT_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    df = make_df(video_info, rows)

    if df.empty:
        print("[CSV] 저장할 댓글이 없습니다.")
        return {}

    # 내부 검수용 전체 댓글
    full_cols = [
        "video_id",
        "top_comment_no",
        "reply_no",
        "comment_depth",
        "comment_type",
        "sort_no",
        "comment_id",
        "parent_comment_id",
        "root_comment_id",
        "author_name",
        "author_channel_id",
        "comment_text",
        "comment_original",
        "like_count",
        "reply_count",
        "published_at",
        "updated_at",
        "is_top_comment",
        "is_reply"
    ]

    # AI 감정/분류 분석용
    # 작성자 원본 정보는 빼고 comment_id 기준으로 다시 DB에 넣을 수 있게 구성
    ai_comment_cols = [
        "comment_id",
        "video_id",
        "comment_type",
        "comment_depth",
        "parent_comment_id",
        "root_comment_id",
        "like_count",
        "reply_count",
        "published_at",
        "comment_text"
    ]

    # AI 의심 댓글 분석용
    # 작성자 식별자는 해시만 제공
    df_suspicion = df.copy()
    df_suspicion["author_hash"] = df_suspicion["author_channel_id"].apply(short_hash)

    suspicion_cols = [
        "comment_id",
        "video_id",
        "comment_type",
        "comment_depth",
        "parent_comment_id",
        "root_comment_id",
        "author_hash",
        "like_count",
        "reply_count",
        "published_at",
        "comment_text"
    ]

    # 영상 내용 요약용
    video_summary_rows = [{
        "video_id": video_info.get("video_id"),
        "title": video_info.get("title"),
        "channel_title": video_info.get("channel_title"),
        "published_at": video_info.get("published_at"),
        "view_count": video_info.get("view_count"),
        "like_count": video_info.get("like_count"),
        "comment_count": video_info.get("comment_count"),
        "description": video_info.get("description")
    }]

    # 결과 템플릿: 댓글 AI 분석 결과
    df_ai_result_template = pd.DataFrame(columns=[
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
    ])

    # 결과 템플릿: 의심 댓글 분석 결과
    df_suspicion_result_template = pd.DataFrame(columns=[
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
    ])

    # 기본 순위 CSV
    df_top = df[df["comment_type"] == "원댓글"].copy()
    df_like_rank = df.sort_values("like_count", ascending=False)
    df_reply_rank = df_top.sort_values("reply_count", ascending=False)

    files = {}

    files["comments_full"] = out_dir / "01_comments_full_internal.csv"
    df[full_cols].to_csv(files["comments_full"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    files["ai_comment_input"] = out_dir / "02_ai_comment_analysis_input.csv"
    df[ai_comment_cols].to_csv(files["ai_comment_input"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    # === 신규 === AI 댓글 분석용 CSV 500건 단위 분할 저장
    ai_comment_chunk_dir = out_dir / "ai_comment_chunks"
    ai_comment_chunk_files = save_split_csv(
        df[ai_comment_cols],
        ai_comment_chunk_dir,
        "02_ai_comment_analysis_input",
        AI_CHUNK_SIZE
    )

    files["ai_suspicion_input"] = out_dir / "03_ai_suspicion_analysis_input.csv"
    df_suspicion[suspicion_cols].to_csv(files["ai_suspicion_input"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    # === 신규 === 의심 댓글 분석용 CSV 500건 단위 분할 저장
    ai_suspicion_chunk_dir = out_dir / "ai_suspicion_chunks"
    ai_suspicion_chunk_files = save_split_csv(
        df_suspicion[suspicion_cols],
        ai_suspicion_chunk_dir,
        "03_ai_suspicion_analysis_input",
        AI_CHUNK_SIZE
    )

    files["video_summary_input"] = out_dir / "04_ai_video_summary_input.csv"
    pd.DataFrame(video_summary_rows).to_csv(files["video_summary_input"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    files["top_liked"] = out_dir / "05_top_liked_comments.csv"
    df_like_rank[ai_comment_cols].head(100).to_csv(files["top_liked"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    files["top_replied"] = out_dir / "06_top_replied_comments.csv"
    df_reply_rank[ai_comment_cols].head(100).to_csv(files["top_replied"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    files["ai_comment_result_template"] = out_dir / "07_ai_comment_analysis_result_template.csv"
    df_ai_result_template.to_csv(files["ai_comment_result_template"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    files["ai_suspicion_result_template"] = out_dir / "08_ai_suspicion_analysis_result_template.csv"
    df_suspicion_result_template.to_csv(files["ai_suspicion_result_template"], index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)

    # === 신규 === AI 결과 파일을 넣어둘 폴더를 미리 생성
    ai_comment_result_dir = out_dir / "ai_comment_results"
    ai_suspicion_result_dir = out_dir / "ai_suspicion_results"
    ai_video_summary_result_dir = out_dir / "ai_video_summary_results"

    ai_comment_result_dir.mkdir(parents=True, exist_ok=True)
    ai_suspicion_result_dir.mkdir(parents=True, exist_ok=True)
    ai_video_summary_result_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print("[CSV 저장 완료]")
    for key, path in files.items():
        print(" -", key, ":", path)

    print("")
    print("[AI 분할 CSV 저장 완료]")
    print(" - 댓글 분석 분할 폴더:", ai_comment_chunk_dir)
    print(" - 댓글 분석 분할 파일 수:", len(ai_comment_chunk_files))
    print(" - 의심 댓글 분할 폴더:", ai_suspicion_chunk_dir)
    print(" - 의심 댓글 분할 파일 수:", len(ai_suspicion_chunk_files))
    print("")
    print("[AI 결과 저장 위치]")
    print(" - 댓글 분석 결과 저장 폴더:", ai_comment_result_dir)
    print(" - 의심 댓글 결과 저장 폴더:", ai_suspicion_result_dir)
    print(" - 영상 요약 결과 저장 폴더:", ai_video_summary_result_dir)

    return files


# ==============================
# AI 프롬프트 파일 생성
# ==============================

def export_prompt_files(video_info):
    video_id = video_info.get("video_id")
    out_dir = OUTPUT_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_comment = """아래 CSV는 유튜브 댓글 목록입니다. 파일은 500건 단위로 나눠서 전달될 수 있습니다.\n\n목표:
댓글별로 감정, 세부 감정, 재미 가능성, 댓글 유형, 주제, 요약, AI 키워드를 분석해주세요.

중요 규칙:
1. comment_id는 절대 변경하지 마세요.
2. 결과는 반드시 CSV 형식으로만 주세요.
3. 원본 행 개수를 유지하세요.
4. 점수는 0~1 사이 숫자로 주세요.
5. sentiment_label은 positive, negative, neutral 중 하나만 사용하세요.
6. emotion_label은 joy, anger, sadness, fear, surprise, disgust, neutral 중 하나만 사용하세요.
7. comment_category는 praise, criticism, question, joke, request, info, spam, argument, normal 중 하나를 사용하세요.
8. ai_keywords는 쉼표로 구분하세요.
9. 모르는 값은 빈칸이 아니라 0 또는 normal/neutral로 채워주세요.

출력 컬럼:
comment_id,
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
ai_keywords
"""

    prompt_suspicion = """아래 CSV는 유튜브 댓글 목록입니다. 파일은 500건 단위로 나눠서 전달될 수 있습니다.\n\n목표:
자동 댓글, AI 생성 댓글, 댓글부대 의심, 정치 관련 댓글, 선동성 댓글, 스팸 댓글 가능성을 점수로 분석해주세요.

중요:
1. 확정 판정이 아니라 의심 점수입니다.
2. comment_id는 절대 변경하지 마세요.
3. 결과는 반드시 CSV 형식으로만 주세요.
4. 점수는 0~1 사이 숫자로 주세요.
5. is_suspicious는 Y 또는 N만 사용하세요.
6. suspicion_label은 NORMAL, AUTO_COMMENT, AI_GENERATED, COMMENT_FARM, POLITICAL, PROPAGANDA, SPAM, TROLL 중 하나를 사용하세요.

출력 컬럼:
comment_id,
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
ai_reason
"""

    prompt_video = """아래 CSV는 유튜브 영상 정보입니다.

목표:
영상 제목과 설명을 기준으로 영상 내용을 요약하고, 핵심 주제와 키워드를 뽑아주세요.
자막이 없는 경우 설명란과 제목 기준으로만 분석하세요.

출력은 반드시 CSV 형식으로만 주세요.

출력 컬럼:
video_id,
summary_short,
summary_long,
main_topic,
sub_topics,
video_keywords,
content_category,
target_audience,
issue_points,
ai_reason
"""

    files = {}

    files["prompt_comment"] = out_dir / "prompt_01_comment_analysis.txt"
    files["prompt_comment"].write_text(prompt_comment, encoding="utf-8")

    files["prompt_suspicion"] = out_dir / "prompt_02_suspicion_analysis.txt"
    files["prompt_suspicion"].write_text(prompt_suspicion, encoding="utf-8")

    files["prompt_video"] = out_dir / "prompt_03_video_summary.txt"
    files["prompt_video"].write_text(prompt_video, encoding="utf-8")

    print("")
    print("[AI 프롬프트 저장 완료]")
    for key, path in files.items():
        print(" -", key, ":", path)

    return files


# ==============================
# 실행
# ==============================

def main():
    if not API_KEY:
        print("[중지] .env 파일에 YOUTUBE_API_KEY를 넣어주세요.")
        return

    if not VIDEO_URL:
        print("[중지] .env 파일에 VIDEO_URL을 넣어주세요.")
        return

    video_id = get_video_id(VIDEO_URL)

    print("[영상 ID]", video_id)
    print("[영상 정보 수집]")

    video_info = fetch_video_info(video_id)

    if not video_info:
        print("[중지] 영상 정보를 가져오지 못했습니다.")
        return

    print("[영상 제목]", video_info.get("title", ""))
    print("[수집 시작]")

    rows = fetch_comments(video_id)

    print("[수집 완료]", len(rows), "개")

    print("[DB 저장 시작]")

    conn = get_conn()

    try:
        insert_video(conn, video_info)
        insert_comments(conn, rows)
        insert_comment_metric_snapshots(conn, rows)

        csv_files = export_csv_files(video_info, rows)
        prompt_files = export_prompt_files(video_info)

        insert_analysis_batch(
            conn=conn,
            video_id=video_id,
            batch_type="CSV_EXPORT",
            provider="PYTHON",
            model_name="NONE",
            export_file_name=str(OUTPUT_DIR / video_id),
            target_count=len(rows),
            memo="댓글 수집 후 AI 분석용 CSV 생성"
        )

        conn.commit()

        print("")
        print("[DB 저장 완료]")
        print("[영상 제목]", video_info.get("title", ""))
        print("[전체 댓글 수]", len(rows))
        print("[출력 폴더]", OUTPUT_DIR / video_id)

    except Exception as e:
        conn.rollback()
        print("[DB 저장 오류]", str(e))
        raise
    finally:
        conn.close()

    print("[완료]")


if __name__ == "__main__":
    main()
