# -*- coding: utf-8 -*-
"""
YouTube 내부 검색 API (youtubei/v1/search) 테스트용 전체 코드

기능
1. 키워드 검색
2. 검색 필터(sp / params) 적용
   - 예: Shorts 필터
3. continuation 기반 다음 페이지 수집
4. 영상 정보 파싱
   - 제목
   - video_id
   - url
   - 채널명
   - 썸네일
   - 길이
   - 조회수
   - 업로드 시점

주의
- 비공식 내부 API 구조라 응답 구조가 바뀔 수 있음
- clientVersion 은 나중에 바뀔 수 있음
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import requests


class YoutubeSearchCrawler:
    def __init__(self) -> None:
        self.url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
        self.session = requests.Session()

        # 최소 헤더 위주
        self.headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://www.youtube.com",
            "referer": "https://www.youtube.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "x-youtube-client-name": "1",
            "x-youtube-client-version": "2.20260306.01.00",
        }

        self.client_context = {
            "client": {
                "hl": "ko",
                "gl": "KR",
                "clientName": "WEB",
                "clientVersion": "2.20260306.01.00",
            }
        }

    # =========================================================
    # 공통
    # =========================================================
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(
            self.url,
            headers=self.headers,
            json=payload,
            timeout=30,
        )

        print(f"[DEBUG] status_code = {resp.status_code}")
        print(f"[DEBUG] content_type = {resp.headers.get('content-type')}")
        print(f"[DEBUG] response_head = {resp.text[:400]}")

        resp.raise_for_status()
        return resp.json()

    def build_search_payload(
            self,
            query: str,
            sp: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "context": self.client_context,
            "query": query,
        }

        # URL의 sp 파라미터가 body에서는 보통 params 로 들어감
        if sp:
            payload["params"] = sp

        return payload

    def build_continuation_payload(self, continuation: str) -> Dict[str, Any]:
        return {
            "context": self.client_context,
            "continuation": continuation,
        }

    # =========================================================
    # 1페이지 검색
    # =========================================================
    def search_first_page(
            self,
            query: str,
            sp: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self.build_search_payload(query=query, sp=sp)
        return self._post(payload)

    # =========================================================
    # continuation 다음 페이지
    # =========================================================
    def search_next_page(self, continuation: str) -> Dict[str, Any]:
        payload = self.build_continuation_payload(continuation=continuation)
        return self._post(payload)

    # =========================================================
    # 파싱 유틸
    # =========================================================
    @staticmethod
    def _get_text(obj: Any) -> str:
        if obj is None:
            return ""

        if isinstance(obj, str):
            return obj

        if isinstance(obj, dict):
            if "simpleText" in obj:
                return str(obj.get("simpleText", "")).strip()

            runs = obj.get("runs", [])
            if isinstance(runs, list):
                return "".join(str(x.get("text", "")) for x in runs).strip()

        return ""

    @staticmethod
    def _safe_get_thumb(video: Dict[str, Any]) -> str:
        thumbs = (
            video.get("thumbnail", {})
            .get("thumbnails", [])
        )
        if not thumbs:
            return ""
        return thumbs[-1].get("url", "")

    @staticmethod
    def _safe_get_owner(video: Dict[str, Any]) -> str:
        owner = YoutubeSearchCrawler._get_text(video.get("ownerText"))
        if owner:
            return owner

        owner = YoutubeSearchCrawler._get_text(video.get("longBylineText"))
        if owner:
            return owner

        owner = YoutubeSearchCrawler._get_text(video.get("shortBylineText"))
        return owner

    @staticmethod
    def _parse_video_renderer(video: Dict[str, Any]) -> Dict[str, Any]:
        video_id = video.get("videoId", "")
        title = YoutubeSearchCrawler._get_text(video.get("title"))
        channel_name = YoutubeSearchCrawler._safe_get_owner(video)
        thumbnail = YoutubeSearchCrawler._safe_get_thumb(video)
        duration = YoutubeSearchCrawler._get_text(video.get("lengthText"))
        view_count = YoutubeSearchCrawler._get_text(video.get("viewCountText"))
        published_time = YoutubeSearchCrawler._get_text(video.get("publishedTimeText"))

        # shorts 는 lengthText 없을 수도 있음
        if not duration:
            overlays = video.get("thumbnailOverlays", [])
            for overlay in overlays:
                time_status = overlay.get("thumbnailOverlayTimeStatusRenderer")
                if time_status:
                    duration = YoutubeSearchCrawler._get_text(time_status.get("text"))
                    if duration:
                        break

        return {
            "type": "video",
            "title": title,
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "channel_name": channel_name,
            "thumbnail": thumbnail,
            "duration": duration,
            "view_count": view_count,
            "published_time": published_time,
        }

    @staticmethod
    def _parse_reel_renderer(reel: Dict[str, Any]) -> Dict[str, Any]:
        # Shorts 전용 렌더러 대응
        video_id = reel.get("videoId", "")
        title = YoutubeSearchCrawler._get_text(reel.get("headline"))
        if not title:
            title = YoutubeSearchCrawler._get_text(reel.get("title"))

        channel_name = YoutubeSearchCrawler._get_text(reel.get("ownerText"))

        thumbs = reel.get("thumbnail", {}).get("thumbnails", [])
        thumbnail = thumbs[-1].get("url", "") if thumbs else ""

        view_count = YoutubeSearchCrawler._get_text(reel.get("viewCountText"))

        return {
            "type": "shorts",
            "title": title,
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}" if video_id else "",
            "channel_name": channel_name,
            "thumbnail": thumbnail,
            "duration": "",
            "view_count": view_count,
            "published_time": "",
        }

    def extract_videos_from_search(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        sections = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in sections:
            items = (
                section.get("itemSectionRenderer", {})
                .get("contents", [])
            )

            for item in items:
                video = item.get("videoRenderer")
                if video:
                    out.append(self._parse_video_renderer(video))
                    continue

                reel = item.get("reelShelfRenderer")
                if reel:
                    # 쇼츠 shelf 형태 대응
                    shorts_items = reel.get("items", [])
                    for short_item in shorts_items:
                        reel_item = short_item.get("reelItemRenderer")
                        if reel_item:
                            out.append(self._parse_reel_renderer(reel_item))
                    continue

        return out

    def extract_videos_from_continuation(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        actions = data.get("onResponseReceivedCommands", [])
        if not actions:
            actions = data.get("onResponseReceivedActions", [])

        for action in actions:
            append_items = (
                action.get("appendContinuationItemsAction", {})
                .get("continuationItems", [])
            )

            for item in append_items:
                section_item = item.get("itemSectionRenderer", {}).get("contents", [])
                for inner in section_item:
                    video = inner.get("videoRenderer")
                    if video:
                        out.append(self._parse_video_renderer(video))
                        continue

                    reel = inner.get("reelShelfRenderer")
                    if reel:
                        shorts_items = reel.get("items", [])
                        for short_item in shorts_items:
                            reel_item = short_item.get("reelItemRenderer")
                            if reel_item:
                                out.append(self._parse_reel_renderer(reel_item))

                video = item.get("videoRenderer")
                if video:
                    out.append(self._parse_video_renderer(video))
                    continue

        return out

    def extract_continuation(self, data: Dict[str, Any]) -> str:
        # 1페이지 검색 응답 구조
        sections = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in sections:
            continuation = (
                section.get("continuationItemRenderer", {})
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token", "")
            )
            if continuation:
                return continuation

        # continuation 응답 구조
        actions = data.get("onResponseReceivedCommands", [])
        if not actions:
            actions = data.get("onResponseReceivedActions", [])

        for action in actions:
            items = (
                action.get("appendContinuationItemsAction", {})
                .get("continuationItems", [])
            )

            for item in items:
                continuation = (
                    item.get("continuationItemRenderer", {})
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token", "")
                )
                if continuation:
                    return continuation

        return ""

    # =========================================================
    # 통합 검색
    # =========================================================
    def search_videos(
            self,
            query: str,
            sp: Optional[str] = None,
            max_pages: int = 1,
    ) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []

        print(f"[INFO] query = {query}")
        print(f"[INFO] sp = {sp}")
        print(f"[INFO] max_pages = {max_pages}")

        # 1페이지
        first_data = self.search_first_page(query=query, sp=sp)
        first_rows = self.extract_videos_from_search(first_data)
        all_rows.extend(first_rows)

        continuation = self.extract_continuation(first_data)
        print(f"[INFO] first_page_rows = {len(first_rows)}")
        print(f"[INFO] first_continuation_exists = {bool(continuation)}")

        # 2페이지 이상
        current_page = 1
        while continuation and current_page < max_pages:
            current_page += 1
            print(f"[INFO] loading page {current_page} ...")

            next_data = self.search_next_page(continuation=continuation)
            next_rows = self.extract_videos_from_continuation(next_data)
            all_rows.extend(next_rows)

            continuation = self.extract_continuation(next_data)
            print(f"[INFO] page_{current_page}_rows = {len(next_rows)}")
            print(f"[INFO] next_continuation_exists = {bool(continuation)}")

            # 안전장치: 빈 결과면 중단
            if not next_rows:
                break

        return all_rows


def print_rows(rows: List[Dict[str, Any]], limit: int = 20) -> None:
    print("\n=== RESULT ===")
    for idx, row in enumerate(rows[:limit], start=1):
        print(
            f"{idx}. "
            f"[{row.get('type', '')}] "
            f"{row.get('title', '')} / "
            f"{row.get('channel_name', '')} / "
            f"{row.get('view_count', '')} / "
            f"{row.get('published_time', '')} / "
            f"{row.get('url', '')}"
        )


if __name__ == "__main__":
    crawler = YoutubeSearchCrawler()

    # =====================================================
    # 1) 일반 검색
    # =====================================================
    query = "초등인강"
    rows = crawler.search_videos(
        query=query,
        sp=None,
        max_pages=2,
    )
    print_rows(rows, limit=10)

    # =====================================================
    # 2) 쇼츠 필터 검색
    # URL:
    # https://www.youtube.com/results?search_query=초등인강&sp=EgIQCQ%253D%253D
    #
    # 실제 body params 로 넣을 값은 보통 디코딩된 값:
    # EgIQCQ==
    # =====================================================
    shorts_sp = "EgIQCQ=="

    shorts_rows = crawler.search_videos(
        query=query,
        sp=shorts_sp,
        max_pages=2,
    )
    print_rows(shorts_rows, limit=20)

    # 필요하면 JSON 파일 저장
    with open("youtube_search_result.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open("youtube_shorts_result.json", "w", encoding="utf-8") as f:
        json.dump(shorts_rows, f, ensure_ascii=False, indent=2)

    print("\n[INFO] 저장 완료")