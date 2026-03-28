# -*- coding: utf-8 -*-
import os
import re
import json
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from src.utils.selenium_utils import SeleniumUtils


class NaverLandArticleHtmlWorker:
    def __init__(self):
        self.sel = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=print,
        )

    def _ensure_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def _save_text(self, file_path: str, text: str) -> str:
        folder = os.path.dirname(file_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

        return file_path

    def _save_json(self, file_path: str, data: Any) -> str:
        folder = os.path.dirname(file_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return file_path

    def _build_article_url(self, article_no: str) -> str:
        return f"https://fin.land.naver.com/articles/{article_no}"

    def _dedupe_keep_order(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result: List[Dict[str, Any]] = []

        for row in rows:
            media_key = (
                str(row.get("imageUrl") or "").strip(),
                str(row.get("videoUrl") or "").strip(),
                str(row.get("imageType") or "").strip(),
                str(row.get("sortingOrder") or "").strip(),
            )

            if media_key in seen:
                continue

            seen.add(media_key)
            result.append(row)

        return result

    def _extract_str_field(self, block: str, field_name: str) -> str:
        patterns = [
            rf'\\"{re.escape(field_name)}\\":\\"([^"]*)\\"',
            rf'"{re.escape(field_name)}":"([^"]*)"',
        ]

        for pattern in patterns:
            m = re.search(pattern, block, re.DOTALL)
            if m:
                return (m.group(1) or "").replace("\\/", "/").replace("&amp;", "&")

        return ""

    def _extract_bool_field(self, block: str, field_name: str) -> bool:
        patterns = [
            rf'\\"{re.escape(field_name)}\\":(true|false)',
            rf'"{re.escape(field_name)}":(true|false)',
        ]

        for pattern in patterns:
            m = re.search(pattern, block, re.DOTALL)
            if m:
                return m.group(1) == "true"

        return False

    def _extract_int_field(self, block: str, field_name: str, default: int = 999999) -> int:
        patterns = [
            rf'\\"{re.escape(field_name)}\\":(\d+)',
            rf'"{re.escape(field_name)}":(\d+)',
        ]

        for pattern in patterns:
            m = re.search(pattern, block, re.DOTALL)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    return default

        return default

    def _find_video_url_in_block(self, block: str) -> str:
        """
        SITEV 블록 안에서 실제 mp4 주소 탐색
        """
        patterns = [
            r'https:\\/\\/[^"]+?\.mp4[^"]*',
            r'https://[^"]+?\.mp4[^"]*',
            r'https:\\/\\/b\d{2}-kr-naver-vod\.pstatic\.net\\/[^"]+?\.mp4[^"]*',
            r'https://b\d{2}-kr-naver-vod\.pstatic\.net/[^"]+?\.mp4[^"]*',
        ]

        for pattern in patterns:
            m = re.search(pattern, block, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(0).replace("\\/", "/").replace("&amp;", "&")

        candidate_fields = [
            "videoUrl",
            "vodUrl",
            "playUrl",
            "playVideoUrl",
            "vodPlayUrl",
            "originVideoUrl",
            "originalVideoUrl",
            "mediaUrl",
            "fileUrl",
            "sourceUrl",
            "src",
        ]

        for field_name in candidate_fields:
            value = self._extract_str_field(block, field_name)
            if value and ".mp4" in value.lower():
                return value

        return ""

    def _extract_gallery_rows_from_html(self, html: str, site_only: bool = False) -> List[Dict[str, Any]]:
        """
        최초 HTML(page_source) 안에서
        imageId 기준 블록 단위로 media 정보 추출
        """

        block_patterns = [
            re.compile(
                r'(\\"imageId\\":\\"[^"]+\\".*?\\"sortingOrder\\":\d+.*?)(?=\\",\\"imageId\\":\\"|$)',
                re.DOTALL
            ),
            re.compile(
                r'("imageId":"[^"]+".*?"sortingOrder":\d+.*?)(?=","imageId":"|$)',
                re.DOTALL
            ),
        ]

        rows: List[Dict[str, Any]] = []

        for block_pattern in block_patterns:
            for m in block_pattern.finditer(html):
                block = m.group(1)

                image_id = self._extract_str_field(block, "imageId")
                image_url = self._extract_str_field(block, "imageUrl")
                image_type = self._extract_str_field(block, "imageType")
                vod_id = self._extract_str_field(block, "vodId")
                vod_key = self._extract_str_field(block, "vodKey")
                sorting_order = self._extract_int_field(block, "sortingOrder", 999999)
                is_representative = self._extract_bool_field(block, "isRepresentative")
                is_vr_exposed = self._extract_bool_field(block, "isVrExposed")

                if not image_url:
                    continue

                if "landthumb-phinf.pstatic.net" not in image_url:
                    continue

                video_url = ""
                is_video = (image_type == "SITEV")

                if is_video:
                    video_url = self._find_video_url_in_block(block)

                row = {
                    "imageId": image_id,
                    "imageUrl": image_url,
                    "imageType": image_type,
                    "sortingOrder": sorting_order,
                    "isRepresentative": is_representative,
                    "isVrExposed": is_vr_exposed,
                    "vodId": vod_id,
                    "vodKey": vod_key,
                    "videoUrl": video_url,
                    "isVideo": is_video,
                }
                rows.append(row)

        rows = self._dedupe_keep_order(rows)
        rows.sort(key=lambda x: int(x.get("sortingOrder", 999999)))

        if site_only:
            rows = [row for row in rows if row.get("imageType") == "SITE"]

        return rows

    def _download_binary(self, url: str, file_path: str, headers: Dict[str, str]) -> bool:
        try:
            res = requests.get(url, headers=headers, timeout=40, stream=True)
            res.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        f.write(chunk)

            return True
        except Exception as e:
            print(f"다운로드 실패: {url} / {e}")
            return False

    def download_media(
            self,
            items: List[Dict[str, Any]],
            save_dir: str,
            article_no: str,
    ) -> Dict[str, List[str]]:
        self._ensure_dir(save_dir)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": "https://fin.land.naver.com/",
        }

        image_files: List[str] = []
        video_files: List[str] = []
        meta_files: List[str] = []

        for idx, item in enumerate(items, start=1):
            image_url = str(item.get("imageUrl") or "").strip()
            video_url = str(item.get("videoUrl") or "").strip()
            image_type = str(item.get("imageType") or "").strip()
            is_video = bool(item.get("isVideo"))

            base_name = f"{article_no}_{idx:02d}_{image_type}"

            if is_video:
                if video_url:
                    video_ext = os.path.splitext(urlparse(video_url).path)[1].lower()
                    if video_ext not in [".mp4", ".mov", ".m4v", ".webm"]:
                        video_ext = ".mp4"

                    video_path = os.path.join(save_dir, f"{base_name}{video_ext}")
                    ok = self._download_binary(video_url, video_path, headers)
                    if ok:
                        video_files.append(video_path)
                        print(f"동영상 저장 완료: {video_path}")
                    else:
                        print(f"동영상 저장 실패: {video_url}")

                if image_url:
                    thumb_ext = os.path.splitext(urlparse(image_url).path)[1].lower()
                    if thumb_ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                        thumb_ext = ".jpg"

                    thumb_path = os.path.join(save_dir, f"{base_name}_thumb{thumb_ext}")
                    ok = self._download_binary(image_url, thumb_path, headers)
                    if ok:
                        image_files.append(thumb_path)
                        print(f"동영상 썸네일 저장 완료: {thumb_path}")

                meta_path = os.path.join(save_dir, f"{base_name}_meta.json")
                self._save_json(meta_path, item)
                meta_files.append(meta_path)
                print(f"동영상 메타 저장 완료: {meta_path}")
                continue

            if image_url:
                img_ext = os.path.splitext(urlparse(image_url).path)[1].lower()
                if img_ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                    img_ext = ".jpg"

                img_path = os.path.join(save_dir, f"{base_name}{img_ext}")
                ok = self._download_binary(image_url, img_path, headers)
                if ok:
                    image_files.append(img_path)
                    print(f"이미지 저장 완료: {img_path}")

        return {
            "image_files": image_files,
            "video_files": video_files,
            "meta_files": meta_files,
        }

    def run(
            self,
            article_no: str,
            save_dir: str = "naver_land_article",
            site_only: bool = False,
            wait_sec: float = 4.0,
    ) -> Dict[str, Any]:
        self._ensure_dir(save_dir)

        article_url = self._build_article_url(article_no)
        html_path = os.path.join(save_dir, f"{article_no}.html")
        json_path = os.path.join(save_dir, f"{article_no}_media.json")

        driver = self.sel.start_driver(
            timeout=30,
            view_mode="mobile",
            window_size=(520, 980),
            mobile_metrics=(430, 932),
            mobile_user_agent=(
                "Mozilla/5.0 (Linux; Android 13; SM-S918N) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Mobile Safari/537.36"
            ),
        )

        try:
            print(f"접속 URL: {article_url}")
            driver.get(article_url)
            time.sleep(wait_sec)

            html = driver.page_source
            self._save_text(html_path, html)
            print(f"HTML 저장 완료: {html_path}")

            rows = self._extract_gallery_rows_from_html(html, site_only=site_only)

            if not rows:
                raise RuntimeError("최초 HTML에서 매물 미디어 추출 실패")

            self._save_json(json_path, rows)
            print(f"미디어 JSON 저장 완료: {json_path}")

            for item in rows:
                if item.get("imageType") == "SITEV":
                    print("SITEV 확인:", json.dumps(item, ensure_ascii=False, indent=2))

            media_result = self.download_media(
                items=rows,
                save_dir=save_dir,
                article_no=article_no,
            )

            return {
                "article_no": article_no,
                "article_url": article_url,
                "html_path": html_path,
                "json_path": json_path,
                "items": rows,
                "image_files": media_result["image_files"],
                "video_files": media_result["video_files"],
                "meta_files": media_result["meta_files"],
            }

        finally:
            # self.sel.quit()
            print(f"HTML 저장 완료:")


if __name__ == "__main__":
    article_no = "2615948861"
    save_dir = "naver_land_article"

    worker = NaverLandArticleHtmlWorker()

    # False = SITEV + P360 + SITE 전부
    # True  = SITE(일반 사진)만
    result = worker.run(
        article_no=article_no,
        save_dir=save_dir,
        site_only=False,
        wait_sec=4.0,
    )

    print("\n=== 추출 미디어 목록 ===")
    for i, item in enumerate(result["items"], start=1):
        print(
            f"{i}. "
            f"type={item.get('imageType')} "
            f"isVideo={item.get('isVideo')} "
            f"order={item.get('sortingOrder')} "
            f"imageUrl={item.get('imageUrl')} "
            f"videoUrl={item.get('videoUrl')}"
        )

    time.sleep(10000000)

    print(f"\n총 미디어 수: {len(result['items'])}")
    print(f"HTML: {result['html_path']}")
    print(f"JSON: {result['json_path']}")

    print("\n=== 이미지 파일 ===")
    for path in result["image_files"]:
        print(path)

    print("\n=== 동영상 파일 ===")
    for path in result["video_files"]:
        print(path)

    print("\n=== 동영상 메타 파일 ===")
    for path in result["meta_files"]:
        print(path)