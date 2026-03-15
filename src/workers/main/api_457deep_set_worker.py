# -*- coding: utf-8 -*-
import json
import os
import random
import time
import threading
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd
import pyautogui
from bs4 import BeautifulSoup

from src.utils.selenium_utils import SeleniumUtils
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


# rhdygksv3@gmail.com / kyh2050!


class Api457deepSetLoadWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.running = True

        self.driver = None
        self.selenium_driver = None
        self.site_name = "457deep"

        self.csv_filename: Optional[str] = None
        self.excel_filename: Optional[str] = None
        self.sheet_name = "Sheet1"

        self.flush_size = 18
        self.buffer: List[Dict[str, Any]] = []
        self.finalized = False
        self.total_saved = 0

        self.excel_driver: Optional[ExcelUtils] = None
        self.file_driver: Optional[FileUtils] = None
        self.api_client: Optional[APIClient] = None

        # progress
        self.current_cnt = 0
        self.total_cnt = 0
        self.before_pro_value = 0.0

        self.login_url = "https://457deep.com/start?next=/"
        self.login_cookies: Dict[str, str] = {}

        # === 신규 === 나중에 서버 생기면 여기만 바꾸면 됨
        self.asset_base_url = "testurl"

        # === 신규 === 내용 저장 폴더명
        self.content_base_dir_name = "내용"
        self.image_base_dir_name = "이미지"
        self.img_timeout = httpx.Timeout(connect=5.0, read=8.0, write=8.0, pool=5.0)

        self.folder_path: str = ""
        self.out_dir: str = "output_457deep"
        self.init_flag = False

    def stop(self) -> None:
        self.log_signal_func("⛔ 중지 요청됨 (저장 후 종료합니다.)")
        self.running = False
        self._stop_event.set()

    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화 실행 완료")
                return True

            self.driver_set()

            # 현재 모니터 해상도 가져오기
            screen_width, screen_height = pyautogui.size()

            # 창 크기를 너비 절반, 높이 전체로 설정
            self.driver.set_window_size(screen_width // 2, screen_height)

            # 창 위치를 왼쪽 상단에 배치
            self.driver.set_window_position(0, 0)

            # 로그인 열기
            self.driver.get(self.login_url)
            self.wait_for_user_login_and_store_cookies()

            if self._stop_event.is_set():
                return False

            self.init_flag = True
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.selenium_driver = SeleniumUtils(headless=False)
        self.driver = self.selenium_driver.start_driver(1200)
        self.log_signal_func("✅ driver_set 완료")

    def main(self) -> bool:
        self.log_signal_func("시작합니다.")

        self.finalized = False
        self.buffer = []
        self.total_saved = 0
        self.current_cnt = 0
        self.total_cnt = 0
        self.before_pro_value = 0.0
        self.running = True

        if not self.columns:
            self.log_signal_func("columns가 비어있습니다.")
            return False

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        # --- total_cnt: 체크된 item 개수 ---
        for r in (self.setting_detail or []):
            if r.get("row_type") == "item" and r.get("checked", True):
                self.total_cnt += 1

        if self.total_cnt <= 0:
            self.total_cnt = 1

        self.log_signal_func(f"작업 대상(자식 item) 수: {self.total_cnt}")

        if not self.file_driver or not self.excel_driver:
            self.log_signal_func("❌ file/excel driver가 초기화되지 않았습니다.")
            return False

        # CSV 초기화
        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))
        self.excel_driver.init_csv(
            self.csv_filename,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )
        self.log_signal_func(f"CSV 생성: {self._resolve_export_path(self.csv_filename)}")

        # XLSX(마지막에만 저장, CSV는 유지)
        self.excel_filename = os.path.splitext(self.csv_filename)[0] + ".xlsx"
        self.log_signal_func(f"XLSX(마지막 저장): {self._resolve_export_path(self.excel_filename)}")

        try:
            sections = self.get_sections()
            if not sections:
                self.log_signal_func("setting_detail에 section이 없습니다.")
                return True

            with httpx.Client(timeout=30) as client:
                client.cookies.update(self.login_cookies or {})

                for sec in sections:
                    if self._stop_event.is_set() or not self.running:
                        self.log_signal_func("⛔ 중지 감지 (섹션) → 저장 후 종료")
                        return True

                    sec_id = sec.get("id")
                    sec_title = (sec.get("title") or sec_id or "").replace("\n", "").strip()
                    self.log_signal_func(f"[섹션] {sec_title}")

                    for it in self.get_items(sec_id):
                        if self._stop_event.is_set() or not self.running:
                            self.log_signal_func("⛔ 중지 감지 (카테고리) → 저장 후 종료")
                            return True

                        if not it.get("checked", True):
                            continue

                        name = (it.get("value") or it.get("code") or "").replace("\n", "").strip()
                        list_url = it.get("list_url") or ""
                        if not list_url:
                            self.log_signal_func(f"  - list_url 없음: {name}")
                            continue

                        context = f"{sec_title} > {name}".strip()

                        self.log_signal_func(f"[{context}] ✅ 카테고리 시작")
                        self.log_signal_func(f"[{context}] url: {list_url}")

                        posts = self.collect_all_posts(client, list_url, context)
                        self.log_signal_func(f"[{context}] post 수집 완료: {len(posts)}개")

                        cat_saved = 0
                        total_posts = len(posts)

                        for idx, post in enumerate(posts, start=1):
                            if self._stop_event.is_set() or not self.running:
                                self.log_signal_func(f"[{context}] ⛔ 중지 감지 (상세) → 저장 후 종료")
                                return True

                            if idx == 1 or (idx % 100 == 0) or (idx == total_posts):
                                self.log_signal_func(f"[{context}] 📥 상세 {idx}/{total_posts}")

                            post["_category_path"] = " > ".join(
                                [p.strip() for p in str(context).split(">") if p.strip()]
                            )

                            detail_base = it.get("detail_url") or (list_url.rstrip("/") + "/detail")
                            post2, detail_url = self.fetch_post(client, detail_base, post, context)

                            if not post2:
                                continue

                            self.buffer.append(self.map_row(post2, detail_url))
                            cat_saved += 1

                            if len(self.buffer) >= self.flush_size:
                                self.flush_buffer(context)

                        self.log_signal_func(
                            f"[{context}] ✅ 카테고리 완료 / saved={cat_saved} / total_saved={self.total_saved}"
                        )

                        # progress: 자식 item 1개 끝날 때마다
                        self.current_cnt += 1
                        pro_value = (self.current_cnt / self.total_cnt) * 1000000
                        self.progress_signal.emit(self.before_pro_value, pro_value)
                        self.before_pro_value = pro_value
                        self.log_signal_func(f"[진행] {self.current_cnt}/{self.total_cnt} (pro={int(pro_value)})")

            return True

        except Exception as e:
            self.log_signal_func(f"❌ main 오류: {e}")
            return False

        finally:
            self.finalize_export()
            self.cleanup()

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("=============== 작업 종료")
        self.progress_end_signal.emit()

    def wait_for_user_login_and_store_cookies(self) -> None:
        self.log_signal_func("로그인 창을 열었습니다. 로그인 후 OK를 눌러주세요.")

        event = threading.Event()
        self.msg_signal.emit("457deep 로그인 후 OK를 눌러주세요", "info", event)

        self.log_signal_func("📢 사용자 입력 대기 중...")

        while not event.wait(0.2):
            if self._stop_event.is_set():
                self.log_signal_func("⛔ 로그인 대기 중 중지 감지")
                return

        if self._stop_event.is_set():
            return

        self.driver.get("https://457deep.com/community/success-story")

        cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
        self.login_cookies = cookies

        self.log_signal_func(f"✅ 쿠키 저장 완료: {len(self.login_cookies)}개")

    def _apply_login_cookies(self) -> None:
        if not self.login_cookies or not self.api_client:
            return

        for k, v in self.login_cookies.items():
            self.api_client.cookie_set(k, v)

    # =========================
    # setting_detail helpers
    # =========================
    def get_sections(self) -> List[Dict[str, Any]]:
        return [r for r in (self.setting_detail or []) if r.get("row_type") == "section"]

    def get_items(self, parent_id: Any) -> List[Dict[str, Any]]:
        rows = self.setting_detail or []
        return [r for r in rows if r.get("row_type") == "item" and r.get("parent_id") == parent_id]

    # =========================
    # export
    # =========================
    def _resolve_export_path(self, filename: Optional[str]) -> str:
        if not filename:
            return ""

        base_dir = self.folder_path.strip() if self.folder_path else os.getcwd()
        if self.out_dir:
            base_dir = os.path.join(base_dir, self.out_dir)

        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, filename)

    def flush_buffer(self, context: str = "") -> None:
        if not self.buffer or not self.excel_driver or not self.csv_filename:
            return

        n = len(self.buffer)
        self.excel_driver.append_to_csv(
            self.csv_filename,
            self.buffer,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )
        self.total_saved += n
        self.log_signal_func(
            f"[{context}] 💾 CSV 저장 +{n} (누적 {self.total_saved})"
            if context else f"💾 CSV 저장 +{n} (누적 {self.total_saved})"
        )
        self.buffer = []

    def finalize_export(self) -> None:
        if self.finalized:
            return

        try:
            if self.buffer:
                self.log_signal_func(f"🧾 잔여 데이터 flush: {len(self.buffer)}건")
                self.flush_buffer("FINAL")

            csv_abs = self._resolve_export_path(self.csv_filename)
            excel_abs = self._resolve_export_path(self.excel_filename)

            if csv_abs and os.path.exists(csv_abs):
                self.log_signal_func(f"📦 CSV → XLSX 변환 시작 (CSV 유지): {csv_abs}")
                self._convert_csv_to_excel_keep(csv_abs, excel_abs, self.sheet_name)
                self.log_signal_func(f"✅ CSV → XLSX 변환 완료 (CSV 유지): {excel_abs}")

            self.finalized = True

        except Exception as e:
            self.log_signal_func(f"❌ finalize 오류: {e}")

    def _convert_csv_to_excel_keep(
            self,
            csv_filename: str,
            excel_filename: str,
            sheet_name: str = "Sheet1"
    ) -> None:
        try:
            df = pd.read_csv(csv_filename, encoding="utf-8-sig", dtype=str)

            if df is None or df.empty:
                self.log_signal_func(f"⚠️ CSV 비어있음: {csv_filename}")
                return

            df = df.fillna("").astype(str)

            # === 신규 === openpyxl 금지 문자 제거 (0x00~0x1F 중 \t,\n,\r 제외)
            def _clean_excel_text(s: str) -> str:
                if not s:
                    return ""
                out = []
                for ch in str(s):
                    o = ord(ch)
                    if o >= 32 or ch in ("\t", "\n", "\r"):
                        out.append(ch)
                return "".join(out)

            df = df.applymap(_clean_excel_text)

            with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                ws = writer.sheets[sheet_name]

                for r in ws.iter_rows(min_row=2, max_row=len(df) + 1):
                    for cell in r:
                        if cell.value is not None:
                            cell.value = str(cell.value)
                            cell.number_format = "@"

        except Exception as e:
            self.log_signal_func(f"❌ XLSX 변환 오류: {e}")

    # =========================
    # list -> posts (id 중복 제거)
    # =========================
    def collect_all_posts(self, client: httpx.Client, list_url: str, context: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        page = 1
        total = 0

        while True:
            if self._stop_event.is_set() or not self.running:
                self.log_signal_func(f"[{context}] ⛔ 중지 감지 (목록)")
                break

            posts = self.fetch_posts(client, list_url, page, context)
            self.log_signal_func(f"[{context}] 📄 목록 page={page} posts={len(posts)} total_posts={total}")

            if not posts:
                self.log_signal_func(f"[{context}] ✔ 마지막 페이지 (page={page})")
                break

            new_cnt = 0
            for p in posts:
                pid = p.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                out.append(p)
                new_cnt += 1

            total += new_cnt
            self.log_signal_func(f"[{context}] ➕ 신규 {new_cnt} / 누적 {total}")

            if new_cnt == 0:
                self.log_signal_func(f"[{context}] ✔ 신규 없음 → 종료 (page={page})")
                break

            page += 1
            time.sleep(random.uniform(0.15, 0.35))

        self.log_signal_func(f"[{context}] ✅ 목록 수집 완료 total={total}")
        return out

    def fetch_posts(self, client: httpx.Client, list_url: str, page: int, context: str) -> List[Dict[str, Any]]:
        url = list_url + ("&page=" if "?" in list_url else "?page=") + str(page)
        headers = self.make_headers(list_url)

        try:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            return self.extract_posts(r.text)
        except Exception as e:
            self.log_signal_func(f"[{context}] ❌ 목록 실패 page={page}: {e}")
            return []

    def extract_posts(self, text: str) -> List[Dict[str, Any]]:
        # =========================
        # 1) 기존: "posts":[...] 파싱
        # =========================
        i = text.find('"posts":')
        if i >= 0:
            i = text.find("[", i)
            if i < 0:
                return []

            d = 0
            for j in range(i, len(text)):
                ch = text[j]
                if ch == "[":
                    d += 1
                elif ch == "]":
                    d -= 1
                    if d == 0:
                        try:
                            return json.loads(text[i:j + 1])
                        except Exception:
                            return []
            return []

        # =========================
        # 2) posts 없으면: "N:[...]" 덩어리들을 전부 훑어서
        #    {"content":{...},"isAdmin":...} content만 수집
        # =========================
        def _load_arrays_containing_isadmin(s: str) -> List[Any]:
            roots = []
            pos = 0
            while True:
                k = s.find(":[", pos)
                if k < 0:
                    break

                if '"isAdmin"' not in s[k:k + 50000]:
                    pos = k + 2
                    continue

                i2 = s.find("[", k)
                d2 = 0
                for j2 in range(i2, len(s)):
                    ch2 = s[j2]
                    if ch2 == "[":
                        d2 += 1
                    elif ch2 == "]":
                        d2 -= 1
                        if d2 == 0:
                            try:
                                roots.append(json.loads(s[i2:j2 + 1]))
                            except Exception:
                                pass
                            pos = j2 + 1
                            break
                else:
                    break
            return roots

        roots = _load_arrays_containing_isadmin(text)
        if not roots:
            return []

        out = []

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                c = x.get("content")
                if c and "isAdmin" in x and isinstance(c, dict):
                    out.append(c)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        for r in roots:
            walk(r)

        seen = set()
        posts = []

        for p in out:
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            posts.append(p)

        return posts

    # =========================
    # detail fetch
    # =========================
    def fetch_post(
            self,
            client: httpx.Client,
            detail_base: str,
            post: Dict[str, Any],
            context: str
    ):
        post_id = post.get("id")
        seq = post.get("sequence")

        seq_str = f"{int(seq):03d}" if str(seq).isdigit() else "000"
        folder_key = f"{seq_str}_{post_id}"

        detail_url = f"{detail_base}/{post_id}"

        self._apply_login_cookies()

        path = urlparse(detail_url).path
        html_headers = {
            "authority": "457deep.com",
            "method": "GET",
            "path": path,
            "scheme": "https",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "max-age=0",
            "priority": "u=0, i",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"144\", \"Google Chrome\";v=\"144\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "referer": detail_url,
        }

        try:
            r = client.get(
                detail_url,
                headers=html_headers,
                timeout=httpx.Timeout(connect=8.0, read=15.0, write=15.0, pool=5.0),
            )
            r.raise_for_status()
            html = r.text
        except Exception as e:
            self.log_signal_func(f"[{context}] ❌ 상세 HTML 실패: {e}")
            return None, detail_url

        div_html, img_names, img_dir_abs = self._process_tiptap_div_and_images(
            client=client,
            html=html,
            detail_url=detail_url,
            context=context,
            category_path=context,
            folder_id=folder_key,
            post_id=post_id,
        )

        if img_names:
            post["_images"] = img_names
            post["_image_dir"] = img_dir_abs.replace("\\", "/")

        if div_html:
            rel_content_path = self._save_content_html(
                category_path=context,
                filename_no_ext=folder_key,
                html_text=div_html,
            )
            post["_content_path"] = rel_content_path or ""

        if img_names:
            post["_images"] = img_names
            post["_image_dir"] = img_dir_abs

        return post, detail_url

    def make_headers(self, list_url: str) -> Dict[str, str]:
        path = "/"
        try:
            s = list_url.split("://", 1)[1]
            idx = s.find("/")
            if idx >= 0:
                path = "/" + s[idx + 1:]
        except Exception:
            path = "/"

        return {
            "rsc": "1",
            "next-url": path,
            "referer": list_url,
            "user-agent": "Mozilla/5.0"
        }

    # =========================
    # content html save (1 file)
    # =========================
    def _build_content_dir_and_rel(self, category_path: str, create_dir: bool = True):
        parts = [p.strip() for p in (category_path or "").split(">") if p.strip()]
        if not parts:
            parts = ["category"]

        bad = '<>:"/\\|?*\n\r\t'

        def clean(s: str) -> str:
            s = s.replace(" ", "")
            out = []
            for ch in s:
                out.append("_" if ch in bad else ch)
            s2 = "".join(out)
            return s2[:120] or "category"

        safe_parts = [clean(p) for p in parts]

        rel_dir = "/".join([self.site_name, self.content_base_dir_name] + safe_parts)
        out_dir = os.path.join(os.getcwd(), self.site_name, self.content_base_dir_name, *safe_parts)

        if create_dir:
            os.makedirs(out_dir, exist_ok=True)

        return out_dir, rel_dir

    def _save_content_html(self, category_path: str, filename_no_ext: str, html_text: str) -> str:
        if not html_text:
            return ""

        save_dir, rel_dir = self._build_content_dir_and_rel(category_path, create_dir=True)
        filename = f"{filename_no_ext}.html"
        abs_path = os.path.join(save_dir, filename)

        try:
            soup = BeautifulSoup(str(html_text), "html.parser")

            for img in soup.find_all("img"):
                src = (img.get("src") or "").strip()
                if not src.startswith("local://"):
                    continue

                rel_img = src[len("local://"):].lstrip("/")
                abs_img = os.path.join(os.getcwd(), *rel_img.split("/"))

                rel_from_html = os.path.relpath(abs_img, start=save_dir).replace("\\", "/")
                img["src"] = rel_from_html

            html_text = str(soup)

        except Exception as e:
            self.log_signal_func(f"❌ local 이미지 src 치환 실패: {e}")

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(str(html_text))

        return f"{rel_dir}/{filename}"

    # =========================
    # HTML parse + image download (URL + base64) + img src rewrite
    # =========================
    def _process_tiptap_div_and_images(
            self,
            client: httpx.Client,
            html: str,
            detail_url: str,
            context: str,
            category_path: str,
            folder_id: str,
            post_id: Any
    ):
        soup = BeautifulSoup(html, "html.parser")
        div = soup.select_one("div.typo.tiptap.p-4")
        if not div:
            return "", [], ""

        save_dir = None
        rel_dir = None

        def ensure_dir() -> None:
            nonlocal save_dir, rel_dir
            if save_dir is None:
                save_dir, rel_dir = self._build_image_dir_and_rel(category_path, folder_id, create_dir=True)

        saved_names = []
        idx = 0

        for img in div.find_all("img"):
            src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or img.get("data-origin")
                    or ""
            ).strip()

            srcset = img.get("srcset")
            if srcset:
                try:
                    src = srcset.split(",")[-1].split(" ")[0].strip()
                except Exception:
                    pass

            src_norm = src.lower().strip()

            if not src_norm or src_norm == "undefined":
                img.decompose()
                continue

            idx += 1

            if src_norm.startswith("data:image"):
                try:
                    ext, b = self._decode_data_image(src)

                    ensure_dir()

                    filename = f"{post_id}_{idx}.{ext}"
                    save_path = os.path.join(save_dir, filename)

                    if not (os.path.exists(save_path) and os.path.getsize(save_path) > 0):
                        with open(save_path, "wb") as f:
                            f.write(b)

                    saved_names.append(filename)
                    img["src"] = f"local://{rel_dir}/{filename}"

                except Exception as e:
                    self.log_signal_func(f"[{context}] ❌ base64 이미지 저장 실패: {e}")
                    img.decompose()
                    continue

            else:
                try:
                    img_url = urljoin(detail_url, src)
                    ext = self._guess_ext(img_url) or "jpg"

                    ensure_dir()

                    filename = f"{post_id}_{idx}.{ext}"
                    save_path = os.path.join(save_dir, filename)

                    if not (os.path.exists(save_path) and os.path.getsize(save_path) > 0):
                        rr = client.get(
                            img_url,
                            headers={"referer": detail_url, "user-agent": "Mozilla/5.0"},
                            timeout=self.img_timeout,
                        )
                        rr.raise_for_status()

                        with open(save_path, "wb") as f:
                            f.write(rr.content)

                    saved_names.append(filename)
                    img["src"] = f"local://{rel_dir}/{filename}"

                except Exception as e:
                    self.log_signal_func(f"[{context}] ❌ 이미지 다운로드 실패: {src} / {e}")
                    img.decompose()
                    continue

            for k in ("data-src", "data-original", "data-origin", "srcset"):
                if img.get(k) is not None:
                    del img[k]

        return str(div), saved_names, (save_dir or "")

    def _build_image_dir_and_rel(self, category_path: str, post_id: Any, create_dir: bool = True):
        parts = [p.strip() for p in (category_path or "").split(">") if p.strip()]
        if not parts:
            parts = ["category"]

        bad = '<>:"/\\|?*\n\r\t'

        def clean(s: str) -> str:
            s = s.replace(" ", "")
            out = []
            for ch in s:
                out.append("_" if ch in bad else ch)
            s2 = "".join(out)
            return s2[:120] or "category"

        safe_parts = [clean(p) for p in parts]

        rel_dir = "/".join([self.site_name, self.image_base_dir_name] + safe_parts + [str(post_id)])
        out_dir = os.path.join(os.getcwd(), self.site_name, self.image_base_dir_name, *safe_parts, str(post_id))

        if create_dir:
            os.makedirs(out_dir, exist_ok=True)

        return out_dir, rel_dir

    def _decode_data_image(self, data_uri: str):
        head, b64 = data_uri.split(",", 1)
        mime = head.split(";", 1)[0].split(":", 1)[1]
        ext = mime.split("/", 1)[1].lower() if "/" in mime else "png"
        if ext == "jpeg":
            ext = "jpg"
        b = base64.b64decode(b64)
        return ext, b

    def _join_url(self, base: str, rel_dir: str, filename: str) -> str:
        b = (base or "").rstrip("/")
        r = (rel_dir or "").strip("/")

        if r:
            return f"{b}/{r}/{filename}"
        return f"{b}/{filename}"

    def _guess_ext(self, url: str) -> str:
        try:
            path = urlparse(str(url)).path
            _, ext = os.path.splitext(path)
            ext = (ext or "").lower().lstrip(".")
            if ext == "jpeg":
                ext = "jpg"
            return ext if ext in ("jpg", "png", "gif", "webp", "bmp") else ""
        except Exception:
            return ""

    # =========================
    # date
    # =========================
    def _to_kst_dt(self, v: Any) -> str:
        try:
            s = str(v or "").strip()
            if not s:
                return ""

            if s.startswith("$D"):
                s = s[2:]

            if s.endswith("Z"):
                s = s[:-1] + "+00:00"

            dt = datetime.fromisoformat(s)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            dt2 = dt.astimezone(timezone(timedelta(hours=9)))
            return dt2.strftime("%Y-%m-%d %H:%M:%S")

        except Exception:
            return str(v) if v is not None else ""

    # =========================
    # mapping
    # =========================
    def map_row(self, post: Dict[str, Any], detail_url: str) -> Dict[str, Any]:
        row = {col: "" for col in self.columns}

        if "URL" in row:
            row["URL"] = detail_url

        if "아이디" in row:
            row["아이디"] = post.get("id", "")

        if "등록일" in row:
            pub = post.get("publishedAt")
            created = post.get("createdAt")
            row["등록일"] = self._to_kst_dt(pub or created)

        if "수정일" in row:
            row["수정일"] = self._to_kst_dt(post.get("updatedAt", ""))

        if "유저아이디" in row:
            row["유저아이디"] = post.get("userId", "")

        if "제목" in row:
            row["제목"] = post.get("title", "")

        if "내용" in row:
            row["내용"] = post.get("_content_path", "") or ""

        if "순서" in row:
            row["순서"] = post.get("sequence", "")
        if "좋아요" in row:
            row["좋아요"] = post.get("likeCount", "")
        if "댓글수" in row:
            row["댓글수"] = post.get("commentCount", "")
        if "조회수" in row:
            row["조회수"] = post.get("viewCount", "")

        if "유저명" in row:
            user = post.get("user") or {}
            profile = user.get("profile") or {}
            row["유저명"] = profile.get("name") or ""

        if "카테고리" in row:
            row["카테고리"] = post.get("_category_path", "") or ""

        if "이미지" in row:
            row["이미지"] = json.dumps(post.get("_images") or [], ensure_ascii=False)

        if "이미지 경로" in row:
            row["이미지 경로"] = post.get("_image_dir", "")

        return row

    # =========================
    # cleanup
    # =========================
    def cleanup(self) -> None:
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
                try:
                    self.selenium_driver.quit()
                except Exception:
                    pass
        finally:
            self.selenium_driver = None

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")
        finally:
            self.file_driver = None

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

        self.api_client = None