import os
import re
import csv
import json
import time
import sys
from pathlib import Path
from datetime import datetime

import requests
import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv


# ============================================================
# YouTube API 댓글 수집 -> PostgreSQL 저장 -> CSV 2개 출력
# ============================================================
#
# 목적:
# 1) .env에서 YouTube API KEY, 영상 ID/URL, DB 접속정보를 읽는다.
# 2) YouTube API로 영상 정보 1건을 수집한다.
# 3) YouTube API로 원댓글 + 대댓글을 수집한다.
# 4) PostgreSQL youtube_video, youtube_comment 테이블에 저장한다.
# 5) .env의 CSV_EXPORT_YN=Y 인 경우 CSV 2개를 저장한다.
#
# 사용 테이블:
# - public.youtube_video
# - public.youtube_comment
#
# 댓글 구분 기준:
# - 원댓글: parent_comment_id IS NULL
# - 대댓글: parent_comment_id IS NOT NULL
#
# 설치:
# pip install requests psycopg2-binary python-dotenv
#
# 실행:
# python youtube_collect_to_pg.py
#
# 빌드 후 사용:
# - exe 파일 옆에 .env 파일을 두면 된다.
#
# ============================================================


# ============================================================
# 1. 공통 유틸 함수
# ============================================================

def base_dir():
    """
    현재 프로그램의 기준 폴더를 반환한다.

    개발 중:
        youtube_collect_to_pg.py 파일이 있는 폴더

    PyInstaller 빌드 후:
        exe 파일이 있는 폴더

    그래서 .env 파일을 py 또는 exe 옆에 두면 동일하게 동작한다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


def now_str():
    """
    DB의 create_dt, update_dt, collected_at 컬럼에 넣을 문자열 시간.
    사용자가 기존에 쓰는 형식인 YYYY-MM-DD HH:MI:SS 형식으로 맞춘다.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_int(value):
    """
    YouTube API의 통계값은 문자열로 오는 경우가 많다.
    예: "12345"

    None, 빈값, 숫자 변환 실패는 0으로 처리한다.
    """
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_text(value):
    """
    None 값을 빈 문자열로 바꾼다.
    CSV/DB 저장 시 None 때문에 불편한 것을 줄이기 위한 함수다.
    """
    if value is None:
        return ""
    return str(value)


def get_yn(value):
    """
    .env의 Y/N 값을 boolean으로 바꾼다.
    Y, YES, TRUE, 1 이면 True.
    그 외에는 False.
    """
    value = safe_text(value).strip().upper()
    return value in ["Y", "YES", "TRUE", "1"]


def get_path(value):
    """
    .env에 적은 경로를 Path로 바꾼다.

    절대경로:
        그대로 사용

    상대경로:
        py 또는 exe 파일 기준 폴더 아래 경로로 사용

    예:
        OUTPUT_DIR=./output
        -> exe파일 옆 output 폴더
    """
    path = Path(value)

    if path.is_absolute():
        return path

    return base_dir() / path


def get_video_id(value):
    """
    YouTube 영상 ID 또는 URL에서 영상 ID만 추출한다.

    입력 예:
        NJFf64DGjds
        https://www.youtube.com/watch?v=NJFf64DGjds
        https://youtu.be/NJFf64DGjds
        https://www.youtube.com/shorts/NJFf64DGjds

    반환:
        NJFf64DGjds
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


def get_author_channel_id(snippet):
    """
    YouTube 댓글 API의 authorChannelId는 아래처럼 들어온다.

    {
        "authorChannelId": {
            "value": "UCxxxx"
        }
    }

    그래서 value만 꺼내서 DB의 author_channel_id 컬럼에 넣는다.
    """
    data = snippet.get("authorChannelId", {})

    if isinstance(data, dict):
        return data.get("value", "")

    return ""



def parse_youtube_datetime(value):
    """
    YouTube API 시간 문자열을 정렬용 datetime으로 바꾼다.

    입력 예:
        2026-05-02T03:59:00Z

    사용 목적:
        댓글 순서를 published_at 기준 오름차순으로 다시 맞추기 위해 사용한다.

    주의:
        DB에는 원래 문자열을 그대로 넣는다.
        이 함수는 정렬용으로만 사용한다.
    """
    if not value:
        return datetime.max

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.max


def reorder_comment_rows(rows):
    """
    DB 저장 전 댓글 순서를 published_at ASC 기준으로 다시 정리한다.

    이유:
        YouTube API의 COMMENT_ORDER=time은 보통 최신순으로 내려온다.
        그런데 분석 데이터 기준에서는 오래된 댓글부터 1, 2, 3 순번을 주는 것이 더 자연스럽다.

    정리 기준:
        1) 원댓글은 published_at 오름차순으로 정렬
        2) top_comment_no를 오래된 원댓글부터 1, 2, 3으로 다시 부여
        3) 각 원댓글의 대댓글도 published_at 오름차순으로 정렬
        4) reply_no를 오래된 대댓글부터 1, 2, 3으로 다시 부여

    최종 조회:
        ORDER BY top_comment_no ASC, reply_no ASC
        로 조회하면 오래된 원댓글부터 자연스럽게 볼 수 있다.
    """
    top_rows = []
    reply_rows = []

    for row in rows:
        if row.get("parent_comment_id") is None:
            top_rows.append(row)
        else:
            reply_rows.append(row)

    reply_map = {}

    for row in reply_rows:
        parent_id = row.get("parent_comment_id")

        if parent_id not in reply_map:
            reply_map[parent_id] = []

        reply_map[parent_id].append(row)

    top_rows.sort(
        key=lambda row: (
            parse_youtube_datetime(row.get("published_at")),
            safe_text(row.get("comment_id"))
        )
    )

    ordered_rows = []
    used_comment_ids = set()

    for top_no, top_row in enumerate(top_rows, start=1):
        top_comment_id = top_row.get("comment_id")

        top_row["top_comment_no"] = top_no
        top_row["reply_no"] = 0
        top_row["sort_no"] = str(top_no)

        ordered_rows.append(top_row)
        used_comment_ids.add(top_comment_id)

        replies = reply_map.get(top_comment_id, [])

        replies.sort(
            key=lambda row: (
                parse_youtube_datetime(row.get("published_at")),
                safe_text(row.get("comment_id"))
            )
        )

        for reply_no, reply_row in enumerate(replies, start=1):
            reply_row["top_comment_no"] = top_no
            reply_row["reply_no"] = reply_no
            reply_row["sort_no"] = str(top_no) + "-" + str(reply_no)

            ordered_rows.append(reply_row)
            used_comment_ids.add(reply_row.get("comment_id"))

    # 혹시 부모 원댓글을 찾지 못한 데이터가 있으면 마지막에 붙인다.
    # 정상적인 YouTube 수집에서는 거의 발생하지 않는다.
    for row in rows:
        comment_id = row.get("comment_id")

        if comment_id not in used_comment_ids:
            ordered_rows.append(row)

    return ordered_rows


# ============================================================
# 2. .env 설정 읽기
# ============================================================

def load_config():
    """
    .env 파일에서 실행 설정을 읽는다.

    주요 설정:
    - YOUTUBE_API_KEY      : YouTube Data API Key
    - YOUTUBE_VIDEO_CODE   : 유튜브 영상 ID
    - YOUTUBE_VIDEO_URL    : 유튜브 영상 URL
    - COMMENT_ORDER        : relevance=인기순, time=최신순
    - FETCH_REPLIES        : Y=대댓글까지 수집, N=원댓글만 수집
    - CSV_EXPORT_YN        : Y=CSV 저장, N=CSV 저장 안함
    - DB_*                 : PostgreSQL 접속 정보
    """
    env_path = base_dir() / ".env"
    load_dotenv(env_path)

    # 영상 ID는 YOUTUBE_VIDEO_CODE를 우선 사용하고, 없으면 YOUTUBE_VIDEO_URL에서 추출한다.
    video_code = os.getenv("YOUTUBE_VIDEO_CODE", "").strip()
    video_url = os.getenv("YOUTUBE_VIDEO_URL", "").strip()
    video_id = get_video_id(video_code or video_url)

    # MAX_TOP_COMMENTS:
    # 0 또는 빈값이면 전체 수집
    # 10이면 원댓글 10개까지만 테스트 수집
    max_top_raw = os.getenv("MAX_TOP_COMMENTS", "").strip()
    max_top_comments = None

    if max_top_raw and max_top_raw != "0":
        max_top_comments = int(max_top_raw)

    return {
        # YouTube API 인증키
        "api_key": os.getenv("YOUTUBE_API_KEY", "").strip(),

        # 수집 대상 영상 ID
        "video_id": video_id,

        # 댓글 정렬 기준
        # relevance: 인기순
        # time: 최신순
        "comment_order": os.getenv("COMMENT_ORDER", "time").strip(),

        # 대댓글까지 수집할지 여부
        "fetch_replies": get_yn(os.getenv("FETCH_REPLIES", "Y")),

        # 테스트용 원댓글 수 제한
        "max_top_comments": max_top_comments,

        # API 연속 호출 사이 딜레이
        "sleep_sec": float(os.getenv("SLEEP_SEC", "0.1")),

        # CSV 저장 여부
        "csv_export_yn": get_yn(os.getenv("CSV_EXPORT_YN", "Y")),

        # CSV 저장 폴더
        "output_dir": get_path(os.getenv("OUTPUT_DIR", "./output")),

        # PostgreSQL DB 접속 정보
        "db_host": os.getenv("DB_HOST", "127.0.0.1"),
        "db_port": int(os.getenv("DB_PORT", "5432")),
        "db_name": os.getenv("DB_NAME", "youtubereply"),
        "db_user": os.getenv("DB_USER", "postgres"),
        "db_password": os.getenv("DB_PASSWORD", "")
    }


# ============================================================
# 3. PostgreSQL 연결
# ============================================================

def get_conn(cfg):
    """
    PostgreSQL 연결 객체를 생성한다.

    .env DB 컬럼 의미:
    - DB_HOST      : PostgreSQL 서버 IP 또는 도메인
    - DB_PORT      : PostgreSQL 포트. 기본 5432
    - DB_NAME      : DB명
    - DB_USER      : DB 사용자명
    - DB_PASSWORD  : DB 비밀번호
    """
    return psycopg2.connect(
        host=cfg["db_host"],
        port=cfg["db_port"],
        dbname=cfg["db_name"],
        user=cfg["db_user"],
        password=cfg["db_password"]
    )


# ============================================================
# 4. YouTube API 공통 요청 함수
# ============================================================

def youtube_get(url, params):
    """
    YouTube API GET 요청 공통 함수.

    YouTube API 주요 파라미터:
    - key        : YouTube API Key
    - part       : 어떤 데이터 묶음을 받을지 지정
                   예) snippet, statistics
    - id         : 영상 ID 조회 시 사용
    - videoId    : 특정 영상의 댓글 스레드 조회 시 사용
    - parentId   : 특정 원댓글의 대댓글 조회 시 사용
    - maxResults : 한 번에 가져올 개수. 댓글 API는 최대 100
    - pageToken  : 다음 페이지 조회용 토큰
    - order      : 댓글 정렬. relevance=인기순, time=최신순
    - textFormat : 댓글 텍스트 형식. plainText로 받으면 HTML 태그가 줄어든다.
    """
    res = requests.get(url, params=params, timeout=30)
    data = res.json()

    if "error" in data:
        raise Exception(json.dumps(data["error"], ensure_ascii=False, indent=2))

    return data


# ============================================================
# 5. 영상 정보 수집
# ============================================================

def fetch_video_info(cfg):
    """
    YouTube videos.list API로 영상 정보를 1건 수집한다.

    API:
        GET https://www.googleapis.com/youtube/v3/videos

    part:
        snippet     : 제목, 설명, 채널명, 업로드일, 썸네일 등
        statistics  : 조회수, 좋아요수, 댓글수 등

    DB 저장 대상:
        public.youtube_video
    """
    video_id = cfg["video_id"]

    data = youtube_get(
        "https://www.googleapis.com/youtube/v3/videos",
        {
            "key": cfg["api_key"],
            "part": "snippet,statistics",
            "id": video_id
        }
    )

    items = data.get("items", [])

    if not items:
        raise Exception("영상 정보를 찾지 못했습니다. YOUTUBE_VIDEO_CODE 또는 YOUTUBE_VIDEO_URL을 확인하세요.")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    thumbnails = snippet.get("thumbnails", {})

    # 썸네일은 화질이 좋은 순서대로 선택한다.
    thumbnail_url = ""
    for key in ["maxres", "standard", "high", "medium", "default"]:
        if key in thumbnails:
            thumbnail_url = thumbnails.get(key, {}).get("url", "")
            break

    return {
        # youtube_video.video_id
        # 유튜브 실제 영상 ID
        "video_id": video_id,

        # youtube_video.title
        # 영상 제목
        "title": snippet.get("title", ""),

        # youtube_video.channel_title
        # 채널 표시명
        "channel_title": snippet.get("channelTitle", ""),

        # youtube_video.channel_id
        # 유튜브 채널 ID
        "channel_id": snippet.get("channelId", ""),

        # youtube_video.video_url
        # 영상 URL
        "video_url": "https://www.youtube.com/watch?v=" + video_id,

        # youtube_video.thumbnail_url
        # 대표 썸네일 URL
        "thumbnail_url": thumbnail_url,

        # youtube_video.description
        # 영상 설명란 원문
        "description": snippet.get("description", ""),

        # youtube_video.published_at
        # 영상 업로드 시각. PostgreSQL timestamptz에 바로 넣는다.
        "published_at": snippet.get("publishedAt"),

        # youtube_video.view_count
        # 수집 시점 조회수
        "view_count": safe_int(statistics.get("viewCount")),

        # youtube_video.like_count
        # 수집 시점 좋아요수
        "like_count": safe_int(statistics.get("likeCount")),

        # youtube_video.comment_count
        # 수집 시점 전체 댓글수
        "comment_count": safe_int(statistics.get("commentCount")),

        # youtube_video.comment_order
        # 이번 수집에서 사용한 댓글 정렬 기준
        "comment_order": cfg["comment_order"],

        # youtube_video.collected_at
        # 수집한 로컬 시간
        "collected_at": now_str(),

        # youtube_video.raw_json
        # YouTube API 원본 JSON
        "raw_json": item
    }


# ============================================================
# 6. 댓글 row 생성 함수
# ============================================================

def make_top_comment_row(video_id, item, top_no):
    """
    commentThreads.list 응답 item 1개를 원댓글 row로 변환한다.

    원댓글 기준:
    - parent_comment_id = NULL
    - top_comment_no = 원댓글 순번
    - reply_no = 0

    원댓글/대댓글 구분은 DB에서 아래 기준으로 판단한다.
    - 원댓글: parent_comment_id IS NULL
    - 대댓글: parent_comment_id IS NOT NULL
    """
    snippet = item.get("snippet", {})
    top_comment = snippet.get("topLevelComment", {})
    top_snippet = top_comment.get("snippet", {})
    comment_id = top_comment.get("id", "")

    return {
        # youtube_comment.comment_id
        # 유튜브 댓글 ID
        "comment_id": comment_id,

        # youtube_comment.video_id
        # 댓글이 달린 영상 ID
        "video_id": video_id,

        # youtube_comment.parent_comment_id
        # 원댓글은 부모 댓글이 없으므로 NULL로 넣는다.
        "parent_comment_id": None,

        # youtube_comment.top_comment_no
        # 수집 순서 기준 원댓글 번호
        "top_comment_no": top_no,

        # youtube_comment.reply_no
        # 원댓글은 0
        "reply_no": 0,

        # youtube_comment.sort_no
        # 화면 표시용 번호
        "sort_no": str(top_no),

        # 작성자 정보
        "author_name": top_snippet.get("authorDisplayName", ""),
        "author_channel_id": get_author_channel_id(top_snippet),
        "author_channel_url": top_snippet.get("authorChannelUrl", ""),
        "author_profile_image": top_snippet.get("authorProfileImageUrl", ""),

        # 댓글 내용
        "comment_text": top_snippet.get("textOriginal", "") or top_snippet.get("textDisplay", ""),
        # 댓글 통계
        "like_count": safe_int(top_snippet.get("likeCount")),
        "reply_count": safe_int(snippet.get("totalReplyCount")),

        # 댓글 작성/수정 시각
        "published_at": top_snippet.get("publishedAt"),
        "updated_at": top_snippet.get("updatedAt"),

        # YouTube API 기타 속성
        "can_rate": safe_text(top_snippet.get("canRate")),
        "viewer_rating": top_snippet.get("viewerRating", ""),
        "is_public": safe_text(snippet.get("isPublic")),
        "can_reply": safe_text(snippet.get("canReply")),

        # 원본 JSON 저장
        "raw_json": item
    }


def make_reply_row(video_id, parent_comment_id, item, top_no, reply_no):
    """
    comments.list 응답 item 1개를 대댓글 row로 변환한다.

    대댓글 기준:
    - parent_comment_id = 원댓글 comment_id
    - top_comment_no = 원댓글 번호
    - reply_no = 대댓글 순번
    """
    snippet = item.get("snippet", {})
    comment_id = item.get("id", "")

    return {
        "comment_id": comment_id,
        "video_id": video_id,
        "parent_comment_id": parent_comment_id,
        "top_comment_no": top_no,
        "reply_no": reply_no,
        "sort_no": str(top_no) + "-" + str(reply_no),

        "author_name": snippet.get("authorDisplayName", ""),
        "author_channel_id": get_author_channel_id(snippet),
        "author_channel_url": snippet.get("authorChannelUrl", ""),
        "author_profile_image": snippet.get("authorProfileImageUrl", ""),

        "comment_text": snippet.get("textOriginal", "") or snippet.get("textDisplay", ""),
        "like_count": safe_int(snippet.get("likeCount")),
        "reply_count": 0,

        "published_at": snippet.get("publishedAt"),
        "updated_at": snippet.get("updatedAt"),

        "can_rate": safe_text(snippet.get("canRate")),
        "viewer_rating": snippet.get("viewerRating", ""),

        # comments.list 대댓글 응답에는 스레드 기준 isPublic/canReply가 없어서 빈값 처리한다.
        "is_public": "",
        "can_reply": "",

        "raw_json": item
    }


# ============================================================
# 7. 댓글 수집 함수
# ============================================================

def fetch_replies(cfg, parent_comment_id, top_no):
    """
    특정 원댓글의 대댓글 전체를 수집한다.

    API:
        GET https://www.googleapis.com/youtube/v3/comments

    중요:
        commentThreads.list에서 replies를 같이 받을 수도 있지만,
        응답 안의 replies는 전체 대댓글이 아닐 수 있다.
        그래서 parentId 기준으로 comments.list를 따로 호출해서 전체 대댓글을 수집한다.
    """
    rows = []
    page_token = ""
    reply_no = 0

    while True:
        params = {
            "key": cfg["api_key"],
            "part": "snippet",
            "parentId": parent_comment_id,
            "maxResults": 100,
            "textFormat": "plainText"
        }

        if page_token:
            params["pageToken"] = page_token

        data = youtube_get("https://www.googleapis.com/youtube/v3/comments", params)

        for item in data.get("items", []):
            reply_no += 1
            row = make_reply_row(cfg["video_id"], parent_comment_id, item, top_no, reply_no)
            rows.append(row)

        page_token = data.get("nextPageToken", "")

        if not page_token:
            break

        time.sleep(cfg["sleep_sec"])

    return rows


def fetch_comments(cfg):
    """
    원댓글과 대댓글을 수집한다.

    원댓글 API:
        commentThreads.list

    대댓글 API:
        comments.list

    페이지 처리:
        YouTube API는 maxResults가 최대 100이다.
        댓글이 100개를 넘으면 nextPageToken으로 다음 페이지를 반복 조회한다.
    """
    rows = []
    top_no = 0
    page_token = ""

    while True:
        params = {
            "key": cfg["api_key"],
            "part": "snippet",
            "videoId": cfg["video_id"],
            "maxResults": 100,
            "order": cfg["comment_order"],
            "textFormat": "plainText"
        }

        if page_token:
            params["pageToken"] = page_token

        data = youtube_get("https://www.googleapis.com/youtube/v3/commentThreads", params)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            top_no += 1

            row = make_top_comment_row(cfg["video_id"], item, top_no)
            rows.append(row)

            print("[원댓글]", top_no, "좋아요:", row["like_count"], "대댓글:", row["reply_count"])

            if cfg["fetch_replies"] and row["reply_count"] > 0:
                reply_rows = fetch_replies(cfg, row["comment_id"], top_no)
                rows.extend(reply_rows)
                print("  ㄴ 대댓글 수집:", len(reply_rows))

            if cfg["max_top_comments"] is not None and top_no >= cfg["max_top_comments"]:
                return reorder_comment_rows(rows)

            time.sleep(cfg["sleep_sec"])

        page_token = data.get("nextPageToken", "")

        if not page_token:
            break

    return reorder_comment_rows(rows)


# ============================================================
# 8. DB 저장 함수
# ============================================================

def insert_video(conn, video):
    """
    youtube_video 테이블에 영상 정보를 저장한다.

    PK:
        video_id

    ON CONFLICT:
        같은 video_id가 이미 있으면 최신 수집 정보로 UPDATE 한다.
        create_dt는 최초 생성 시점으로만 넣고,
        update_dt는 재수집할 때마다 갱신한다.
    """
    sql = """
          INSERT INTO public.youtube_video (
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

    data = dict(video)
    data["raw_json"] = Json(video.get("raw_json", {}))
    data["create_dt"] = now_str()
    data["update_dt"] = now_str()

    with conn.cursor() as cur:
        cur.execute(sql, data)


def insert_comments(conn, rows):
    """
    youtube_comment 테이블에 댓글을 저장한다.

    방식:
        댓글 1개씩 INSERT 하지 않고,
        execute_values로 500개씩 묶어서 벌크 INSERT 한다.

    장점:
        댓글이 많을 때 속도가 훨씬 빠르다.

    PK:
        comment_id

    ON CONFLICT:
        같은 comment_id가 이미 있으면 좋아요수, 댓글 내용, 수정일시 등을 UPDATE 한다.
    """
    if not rows:
        return

    sql = """
          INSERT INTO public.youtube_comment (
              comment_id,
              video_id,
              parent_comment_id,
              top_comment_no,
              reply_no,
              sort_no,
              author_name,
              author_channel_id,
              author_channel_url,
              author_profile_image,
              comment_text,
              like_count,
              reply_count,
              published_at,
              updated_at,
              can_rate,
              viewer_rating,
              is_public,
              can_reply,
              raw_json,
              create_dt,
              update_dt
          ) VALUES %s
          ON CONFLICT (comment_id)
          DO UPDATE SET
              video_id = EXCLUDED.video_id,
              parent_comment_id = EXCLUDED.parent_comment_id,
              top_comment_no = EXCLUDED.top_comment_no,
              reply_no = EXCLUDED.reply_no,
              sort_no = EXCLUDED.sort_no,
              author_name = EXCLUDED.author_name,
              author_channel_id = EXCLUDED.author_channel_id,
              author_channel_url = EXCLUDED.author_channel_url,
              author_profile_image = EXCLUDED.author_profile_image,
              comment_text = EXCLUDED.comment_text,
              like_count = EXCLUDED.like_count,
              reply_count = EXCLUDED.reply_count,
              published_at = EXCLUDED.published_at,
              updated_at = EXCLUDED.updated_at,
              can_rate = EXCLUDED.can_rate,
              viewer_rating = EXCLUDED.viewer_rating,
              is_public = EXCLUDED.is_public,
              can_reply = EXCLUDED.can_reply,
              raw_json = EXCLUDED.raw_json,
              update_dt = EXCLUDED.update_dt \
          """

    values = []

    for row in rows:
        values.append((
            row.get("comment_id"),
            row.get("video_id"),
            row.get("parent_comment_id"),
            safe_int(row.get("top_comment_no")),
            safe_int(row.get("reply_no")),
            row.get("sort_no"),
            row.get("author_name"),
            row.get("author_channel_id"),
            row.get("author_channel_url"),
            row.get("author_profile_image"),
            row.get("comment_text"),
            safe_int(row.get("like_count")),
            safe_int(row.get("reply_count")),
            row.get("published_at"),
            row.get("updated_at"),
            row.get("can_rate"),
            row.get("viewer_rating"),
            row.get("is_public"),
            row.get("can_reply"),
            Json(row.get("raw_json", {})),
            now_str(),
            now_str()
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)


# ============================================================
# 9. CSV 저장 함수
# ============================================================

def write_csv(file_path, rows, columns):
    """
    Dict 리스트를 CSV로 저장한다.

    인코딩:
        utf-8-sig

    이유:
        엑셀에서 한글이 깨지지 않게 하기 위해서다.

    raw_json:
        dict 형태이므로 JSON 문자열로 바꿔서 저장한다.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for row in rows:
            out = {}

            for col in columns:
                value = row.get(col, "")

                if col == "raw_json":
                    value = json.dumps(value, ensure_ascii=False)

                out[col] = value

            writer.writerow(out)


def export_csv(cfg, video, comments):
    """
    CSV 2개를 저장한다.

    저장 위치:
        OUTPUT_DIR/{video_id}/youtube_video.csv
        OUTPUT_DIR/{video_id}/youtube_comment.csv

    저장 여부:
        .env의 CSV_EXPORT_YN=Y 일 때만 실행된다.
    """
    out_dir = cfg["output_dir"] / cfg["video_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # youtube_video.csv 컬럼
    video_cols = [
        "video_id",
        "title",
        "channel_title",
        "channel_id",
        "video_url",
        "thumbnail_url",
        "description",
        "published_at",
        "view_count",
        "like_count",
        "comment_count",
        "comment_order",
        "collected_at",
        "raw_json"
    ]

    # youtube_comment.csv 컬럼
    comment_cols = [
        "comment_id",
        "video_id",
        "parent_comment_id",
        "top_comment_no",
        "reply_no",
        "sort_no",
        "author_name",
        "author_channel_id",
        "author_channel_url",
        "author_profile_image",
        "comment_text",
        "like_count",
        "reply_count",
        "published_at",
        "updated_at",
        "can_rate",
        "viewer_rating",
        "is_public",
        "can_reply",
        "raw_json"
    ]

    video_file = out_dir / "youtube_video.csv"
    comment_file = out_dir / "youtube_comment.csv"

    write_csv(video_file, [video], video_cols)
    write_csv(comment_file, comments, comment_cols)

    print("[CSV 저장]", video_file)
    print("[CSV 저장]", comment_file)


# ============================================================
# 10. 실행 main
# ============================================================

def main():
    cfg = load_config()

    if not cfg["api_key"]:
        print("[중지] .env에 YOUTUBE_API_KEY를 입력하세요.")
        return

    if not cfg["video_id"]:
        print("[중지] .env에 YOUTUBE_VIDEO_CODE 또는 YOUTUBE_VIDEO_URL을 입력하세요.")
        return

    print("[ENV 위치]", base_dir() / ".env")
    print("[영상 ID]", cfg["video_id"])
    print("[댓글 정렬]", cfg["comment_order"])
    print("[대댓글 수집 여부]", "Y" if cfg["fetch_replies"] else "N")
    print("[CSV 저장 여부]", "Y" if cfg["csv_export_yn"] else "N")

    print("")
    print("[1] 영상 정보 수집 시작")
    video = fetch_video_info(cfg)

    print("[영상 제목]", video.get("title", ""))

    print("")
    print("[2] 댓글 수집 시작")
    comments = fetch_comments(cfg)

    print("[댓글 수집 완료]", len(comments), "개")
    print("[댓글 순서 정리]", "published_at ASC 기준으로 top_comment_no/reply_no 재부여 완료")

    print("")
    print("[3] DB 저장 시작")

    conn = get_conn(cfg)

    try:
        insert_video(conn, video)
        insert_comments(conn, comments)
        conn.commit()

        print("[DB 저장 완료]")

    except Exception as e:
        conn.rollback()
        print("[DB 저장 오류]", str(e))
        raise

    finally:
        conn.close()

    print("")
    print("[4] CSV 처리")

    if cfg["csv_export_yn"]:
        export_csv(cfg, video, comments)
    else:
        print("[CSV 건너뜀] CSV_EXPORT_YN=N")

    print("")
    print("[완료]")


if __name__ == "__main__":
    main()
