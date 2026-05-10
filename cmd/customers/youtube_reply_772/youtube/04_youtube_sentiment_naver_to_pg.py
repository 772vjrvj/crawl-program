# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import time
import uuid
import requests
from pathlib import Path
from datetime import datetime

import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube 댓글 감성분석 NAVER CLOVA -> PostgreSQL 저장
# ============================================================
#
# 처리 순서:
# 1) DB에서 youtube_comment 조회
# 2) NAVER CLOVA Studio HCX-005에 댓글 감성분석 요청
# 3) youtube_analysis_run에 실행 이력 생성
# 4) youtube_comment_sentiment에 결과 저장
#
# 설치:
# pip install requests psycopg2-binary python-dotenv
#
# 실행:
# python 04_youtube_sentiment_naver_to_pg.py
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

    raw_api_key = os.getenv("CLOVA_STUDIO_API_KEY", "").strip()

    if raw_api_key and not raw_api_key.startswith("Bearer "):
        raw_api_key = "Bearer " + raw_api_key

    return {
        "video_id": get_video_id(video_raw),

        "method_id": os.getenv("SENTIMENT_METHOD_ID", "SENTIMENT_NAVER_CLOVA_HCX005_V1").strip(),

        "include_replies": get_yn(os.getenv("ANALYZE_REPLIES", "Y")),

        # 0이면 전체, 10이면 10개만 테스트
        "max_comments": int(os.getenv("SENTIMENT_MAX_COMMENTS", "0")),

        # Y이면 같은 video_id + method_id SENTIMENT run 삭제 후 다시 분석
        "reset_yn": get_yn(os.getenv("SENTIMENT_RESET_YN", "N")),

        # Y이면 예전에 같은 method_id로 분석된 comment_id는 제외
        "skip_done_yn": get_yn(os.getenv("SENTIMENT_SKIP_DONE_YN", "Y")),

        "sleep_sec": float(os.getenv("SENTIMENT_SLEEP_SEC", "0.2")),

        "clova_host": os.getenv("CLOVA_STUDIO_HOST", "https://clovastudio.stream.ntruss.com").strip(),
        "clova_model": os.getenv("CLOVA_STUDIO_MODEL", "HCX-005").strip(),
        "clova_api_key": raw_api_key,

        "db_host": os.getenv("DB_HOST", "127.0.0.1"),
        "db_port": int(os.getenv("DB_PORT", "5432")),
        "db_name": os.getenv("DB_NAME", "youtubereply"),
        "db_user": os.getenv("DB_USER", "postgres"),
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
# 3. NAVER CLOVA 감성분석
# ============================================================

class NaverClovaSentimentAnalyzer:
    def __init__(self, cfg):
        if not cfg["clova_api_key"]:
            raise ValueError("CLOVA_STUDIO_API_KEY 값이 .env에 없습니다.")

        self.host = cfg["clova_host"]
        self.model = cfg["clova_model"]
        self.api_key = cfg["clova_api_key"]

    def analyze(self, comment_text, video_summary):
        url = self.host + "/v3/chat-completions/" + self.model
        request_id = str(uuid.uuid4())

        headers = {
            "Authorization": self.api_key,
            "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream"
        }

        data = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 유튜브 댓글 감성분석 API다. "
                        "분석 대상은 유튜브 영상에 달린 댓글이다. "
                        "댓글 하나만 단독으로 판단하지 말고, 함께 제공되는 영상 요약과 댓글들이 이어지는 전체 분위기를 고려해서 판단한다. "
                        "단, 최종 감성 라벨은 분석 대상 댓글 자체의 감정을 중심으로 결정한다. "

                        "댓글 감성은 반드시 POSITIVE, NEGATIVE, NEUTRAL, MIXED 중 하나로 분류한다. "

                        "POSITIVE는 영상 내용이나 상황에 대한 칭찬, 동의, 지지, 긍정적 평가다. "
                        "NEGATIVE는 비판, 불만, 분노, 조롱, 비난, 우려, 냉소, 욕설이 포함된 경우다. "
                        "NEUTRAL은 단순 설명, 정보 전달, 질문, 감정이 약한 의견이다. "
                        "MIXED는 긍정과 부정이 함께 강하게 나타나는 경우다. "

                        "반어법, 비꼼, 조롱, 욕설, 냉소 표현은 문맥상 부정 가능성을 높게 본다. "
                        "다만 사실 설명이나 대안 제시가 중심이면 무조건 부정으로 보지 말고 NEUTRAL 또는 MIXED로 판단한다. "

                        "sentiment_score는 -1.0부터 1.0까지다. "
                        "1에 가까우면 긍정, -1에 가까우면 부정, 0에 가까우면 중립이다. "
                        "sentiment_magnitude는 감정 강도이며 0.0부터 1.0까지다. "

                        "반드시 JSON 객체 1개만 출력한다. "
                        "마크다운 코드블록과 설명 문장은 절대 출력하지 않는다. "
                        "JSON 밖에 어떤 문장도 출력하지 않는다. "

                        "출력 형식은 반드시 다음 JSON 형식이다. "
                        "{"
                        "\"sentiment_label\":\"NEGATIVE\","
                        "\"sentiment_score\":-0.7,"
                        "\"sentiment_magnitude\":0.7,"
                        "\"positive_score\":0.05,"
                        "\"negative_score\":0.80,"
                        "\"neutral_score\":0.10,"
                        "\"mixed_score\":0.05,"
                        "\"confidence_score\":0.85,"
                        "\"reason_text\":\"짧은 판단 이유\""
                        "} "
                    )
                },
                {
                    "role": "user",
                    "content": (
                            "영상 요약:\n"
                            + safe_text(video_summary)
                            + "\n\n"
                              "분석 참고:\n"
                              "이 댓글을 판단하기 전에 영상 주제와 지금까지 댓글들이 이어지는 전체 분위기를 함께 고려한다.\n"
                              "다만 최종 판단은 아래 분석 대상 댓글의 감성을 기준으로 한다.\n\n"
                              "분석 대상 댓글:\n"
                            + safe_text(comment_text)
                    )
                }
            ],
            "topP": 0.1,
            "topK": 0,
            "maxTokens": 180,
            "temperature": 0.0,
            "repetitionPenalty": 1.1,
            "stop": [],
            "seed": 0,
            "includeAiFilters": True
        }

        started = time.time()
        result_text = self._request_stream(url, headers, data)
        response_ms = int((time.time() - started) * 1000)

        result_json = self._extract_first_json(result_text)

        if result_json is None:
            result_json = {
                "sentiment_label": "NEUTRAL",
                "sentiment_score": 0,
                "sentiment_magnitude": 0,
                "positive_score": 0,
                "negative_score": 0,
                "neutral_score": 1,
                "mixed_score": 0,
                "confidence_score": 0,
                "reason_text": "JSON 파싱 실패",
                "raw_text": result_text
            }

        result = self._normalize_result(result_json)
        result["request_id"] = request_id
        result["response_ms"] = response_ms
        result["raw_json"] = result_json

        return result

    def _request_stream(self, url, headers, data):
        result_text = ""
        current_event = ""

        with requests.post(url, headers=headers, json=data, stream=True, timeout=60) as response:
            if response.status_code != 200:
                print("HTTP_STATUS:", response.status_code)
                print("ERROR_BODY:", response.text)
                response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                line_text = line.decode("utf-8").strip()

                if line_text.startswith("event:"):
                    current_event = line_text.replace("event:", "", 1).strip()
                    continue

                if not line_text.startswith("data:"):
                    continue

                if current_event != "token":
                    continue

                json_text = line_text.replace("data:", "", 1).strip()

                if json_text == "[DONE]":
                    continue

                try:
                    item = json.loads(json_text)
                except json.JSONDecodeError:
                    continue

                content = item.get("message", {}).get("content", "")

                if content:
                    result_text += content

        return result_text.strip()

    def _extract_first_json(self, text):
        if not text:
            return None

        clean_text = text.strip()
        clean_text = clean_text.replace("```json", "")
        clean_text = clean_text.replace("```JSON", "")
        clean_text = clean_text.replace("```", "")
        clean_text = clean_text.strip()

        start_idx = clean_text.find("{")

        if start_idx < 0:
            return None

        clean_text = clean_text[start_idx:]

        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(clean_text)
            return obj
        except json.JSONDecodeError:
            return None

    def _normalize_result(self, item):
        label = safe_text(item.get("sentiment_label")).strip().upper()

        if label not in ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]:
            label = "NEUTRAL"

        score = safe_float(item.get("sentiment_score"))

        if score > 1:
            score = 1.0

        if score < -1:
            score = -1.0

        if label == "POSITIVE" and score <= 0:
            score = 0.3

        if label == "NEGATIVE" and score >= 0:
            score = -0.3

        if label == "NEUTRAL":
            score = 0.0

        magnitude = safe_float(item.get("sentiment_magnitude"))

        if magnitude <= 0:
            magnitude = abs(score)

        return {
            "sentiment_label": label,
            "sentiment_score": score,
            "sentiment_magnitude": magnitude,
            "positive_score": clamp01(item.get("positive_score")),
            "negative_score": clamp01(item.get("negative_score")),
            "neutral_score": clamp01(item.get("neutral_score")),
            "mixed_score": clamp01(item.get("mixed_score")),
            "confidence_score": clamp01(item.get("confidence_score")),
            "reason_text": safe_text(item.get("reason_text"))
        }


def clamp01(value):
    num = safe_float(value)

    if num < 0:
        return 0.0

    if num > 1:
        return 1.0

    return num


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
        raise Exception("youtube_analysis_method에 method_id가 없습니다: " + method_id)


def delete_previous_sentiment_runs(conn, cfg):
    sql = """
          DELETE FROM public.youtube_analysis_run
          WHERE video_id = %s
            AND method_id = %s
            AND analysis_task = 'SENTIMENT' \
          """

    with conn.cursor() as cur:
        cur.execute(sql, (cfg["video_id"], cfg["method_id"]))


def create_analysis_run(conn, cfg):
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
                  0,
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
            "provider": "NAVER_CLOVA",
            "model": cfg["clova_model"],
            "label_list": ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"],
            "score_range": "-1_to_1",
            "skip_done_yn": "Y" if cfg["skip_done_yn"] else "N"
        }),
        "now": now
    }

    with conn.cursor() as cur:
        cur.execute(sql, data)

    return run_id


def update_run_success(conn, run_id, total_count, result_count):
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
        cur.execute(sql, (total_count, result_count, now, now, run_id))


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
        cur.execute(sql, (safe_text(error_message)[:5000], now, now, run_id))


# ============================================================
# 5. 댓글 조회
# ============================================================

def fetch_comments(conn, cfg):
    params = [cfg["video_id"]]

    sql = """
          SELECT
              c.comment_id,
              c.video_id,
              c.parent_comment_id,
              CASE
                  WHEN c.parent_comment_id IS NULL THEN 'TOP'
                  ELSE 'REPLY'
                  END AS comment_kind,
              c.comment_text
          FROM public.youtube_comment c
          WHERE c.video_id = %s \
          """

    if not cfg["include_replies"]:
        sql += """
          AND c.parent_comment_id IS NULL
        """

    if cfg["skip_done_yn"]:
        sql += """
          AND NOT EXISTS (
              SELECT 1
              FROM public.youtube_comment_sentiment s
              WHERE s.comment_id = c.comment_id
                AND s.method_id = %s
          )
        """
        params.append(cfg["method_id"])

    sql += """
        ORDER BY c.top_comment_no ASC, c.reply_no ASC
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
                "comment_kind": row[3],
                "comment_text": row[4]
            })

    return rows


def fetch_video_summary(conn, video_id):
    """
    youtube_video에서 영상 제목/설명을 가져와 감성분석 문맥으로 사용한다.
    별도 summary 컬럼이 없으므로 title + description을 요약 문맥으로 사용한다.
    """
    sql = """
          SELECT
              title,
              description
          FROM public.youtube_video
          WHERE video_id = %s \
          """

    with conn.cursor() as cur:
        cur.execute(sql, (video_id,))
        row = cur.fetchone()

    if not row:
        return ""

    title = safe_text(row[0]).strip()
    description = safe_text(row[1]).strip()

    text = (
            "영상 제목: " + title + "\n"
                                "영상 설명: " + description
    )

    # 너무 길면 CLOVA 입력이 길어지므로 적당히 자른다.
    return text[:2500]

# ============================================================
# 6. 감성 결과 저장
# ============================================================

def insert_sentiment_rows(conn, run_id, cfg, rows):
    if not rows:
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
              response_ms = EXCLUDED.response_ms,
              raw_json = EXCLUDED.raw_json,
              update_dt = EXCLUDED.update_dt \
          """

    now = now_str()
    values = []

    for row in rows:
        values.append((
            run_id,
            cfg["method_id"],
            row["video_id"],
            row["comment_id"],
            row["parent_comment_id"],
            row["comment_kind"],
            row["sentiment_label"],
            row["sentiment_score"],
            row["sentiment_magnitude"],
            row["positive_score"],
            row["negative_score"],
            row["neutral_score"],
            row["mixed_score"],
            row["confidence_score"],
            row["reason_text"],
            row["request_id"],
            0,
            0,
            0,
            row["response_ms"],
            Json(row["raw_json"]),
            now,
            now
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)

    return len(values)


# ============================================================
# 7. 실행
# ============================================================

def main():
    cfg = load_config()

    if not cfg["video_id"]:
        print("[중지] ANALYZE_VIDEO_CODE 또는 YOUTUBE_VIDEO_CODE를 입력하세요.")
        return

    print("[ENV 위치]", base_dir() / ".env")
    print("[분석 작업]", "SENTIMENT NAVER CLOVA")
    print("[분석 영상]", cfg["video_id"])
    print("[분석 방식]", cfg["method_id"])
    print("[대댓글 포함]", "Y" if cfg["include_replies"] else "N")
    print("[기존 분석 제외]", "Y" if cfg["skip_done_yn"] else "N")
    print("[최대 댓글 수]", cfg["max_comments"])
    print("[기존 SENTIMENT 삭제]", "Y" if cfg["reset_yn"] else "N")

    conn = get_conn(cfg)
    run_id = None

    try:
        print("")
        print("[1] 분석 방식 확인")
        check_analysis_method(conn, cfg["method_id"])

        if cfg["reset_yn"]:
            print("[2] 기존 SENTIMENT 삭제")
            delete_previous_sentiment_runs(conn, cfg)

        print("[3] run 생성")
        run_id = create_analysis_run(conn, cfg)
        conn.commit()
        print("[run_id]", run_id)

        print("[4] 댓글 조회")
        comments = fetch_comments(conn, cfg)
        print("[조회 댓글 수]", len(comments))

        print("[4-1] 영상 요약 조회")
        video_summary = fetch_video_summary(conn, cfg["video_id"])
        print("[영상 요약 길이]", len(video_summary))

        if not comments:
            update_run_success(conn, run_id, 0, 0)
            conn.commit()
            print("[완료] 분석할 댓글이 없습니다.")
            return

        analyzer = NaverClovaSentimentAnalyzer(cfg)

        result_rows = []
        done_count = 0

        print("[5] CLOVA 감성분석 시작")

        for comment in comments:
            done_count += 1

            print(
                "[분석중]",
                done_count,
                "/",
                len(comments),
                comment["comment_id"]
            )

            result = analyzer.analyze(comment["comment_text"], video_summary)

            save_row = dict(comment)
            save_row.update(result)
            result_rows.append(save_row)

            # 20개씩 중간 저장
            if len(result_rows) >= 20:
                inserted = insert_sentiment_rows(conn, run_id, cfg, result_rows)
                conn.commit()
                print("[중간 저장]", inserted, "개")
                result_rows = []

            time.sleep(cfg["sleep_sec"])

        inserted_last = insert_sentiment_rows(conn, run_id, cfg, result_rows)
        conn.commit()

        update_run_success(conn, run_id, len(comments), done_count)
        conn.commit()

        print("")
        print("[완료]")
        print("[총 분석 댓글 수]", done_count)
        print("[마지막 저장 수]", inserted_last)
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