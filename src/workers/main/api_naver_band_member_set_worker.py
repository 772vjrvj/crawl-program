# ApiNaverBandMemberSetLoadWorker.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import requests
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.utils.time_utils import ms_to_yyyy_mm_dd
from src.workers.api_base_worker import BaseApiWorker
from selenium.webdriver.remote.webdriver import WebDriver


class ApiNaverBandMemberSetWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()

        self.site_name: str = "naver_band"
        self.site_login_url: str = "https://auth.band.us/login_page?next_url=https%3A%2F%2Fwww.band.us%2F"
        self.site_url: str = "https://www.band.us/band"

        # === 신규 === stop 안정성(Event)
        self._stop_event = threading.Event()

        self.csv_filename: Optional[str] = None

        self.selenium_driver: Optional[SeleniumUtils] = None
        self.driver: Optional[WebDriver] = None

        self.excel_driver: Optional[ExcelUtils] = None
        self.file_driver: Optional[FileUtils] = None
        self.api_client: Optional[APIClient] = None

        self.band_name: str = ""
        self._driver_closed: bool = False

        # ✅ Band Web 번들에 박혀있는 APP_KEY (= akey 기본값)
        self.band_app_key: str = "bbc59b0b5f7a1c6efe950f6236ccda35"

    # =========================================================
    # lifecycle
    # =========================================================
    def init(self) -> bool:
        self.driver_set()
        return True

    def driver_set(self) -> None:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        # ✅ 로그인만 사용 (후킹/캡처 옵션 제거)
        self.selenium_driver = SeleniumUtils(headless=False)
        self.driver = self.selenium_driver.start_driver(1200)

    def _close_driver_once(self) -> None:
        if self._driver_closed:
            return
        self._driver_closed = True

        try:
            if self.selenium_driver:
                self.selenium_driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None
            self.selenium_driver = None

    def stop(self) -> None:
        # === 신규 === Event 기반 stop
        self._stop_event.set()
        self._close_driver_once()

    def destroy(self) -> None:
        self._close_driver_once()

        # BaseApiWorker 시그니처에 맞춰 emit (현재 코드 유지)
        self.progress_signal.emit(0.0, 1000000)
        self.log_signal_func("크롤링 종료중...")
        time.sleep(2.5)
        self.log_signal_func("크롤링 종료")
        self.progress_end_signal.emit()

    # =========================================================
    # main
    # =========================================================
    def main(self) -> bool:
        self.log_signal_func("크롤링 시작합니다.")

        if not self.file_driver or not self.excel_driver or not self.selenium_driver or not self.driver:
            self.log_signal_func("❌ 초기화 실패(driver_set 누락)")
            return False

        self.csv_filename = self.file_driver.get_csv_filename(self.site_name)
        self.excel_driver.init_csv(self.csv_filename, self.columns)

        band_id = self.get_setting_value(self.setting, "band_id")
        if not band_id:
            self.log_signal_func("❌ band_id 없음")
            return False
        band_id_str = str(band_id)

        # 1) 로그인(유저 OK 대기) + 멤버 페이지 이동
        self.wait_for_user_confirmation(band_id_str)
        if self._stop_event.is_set():
            return False

        time.sleep(1)

        # 2) 밴드명(옵션)
        self._extract_band_name_from_page(band_id_str)

        # 3) Selenium 쿠키 확보 (secretKey 필요)
        cookie_jar = self._get_cookiejar_from_selenium()
        if not cookie_jar.get_dict():
            self.log_signal_func("❌ 쿠키 확보 실패(빈 쿠키 jar)")
            return False

        secret_key = self._normalize_cookie_value(self._get_cookie_value(cookie_jar, "secretKey"))
        if not secret_key:
            self.log_signal_func("❌ secretKey 쿠키를 못 찾음 (도메인/세션 확인 필요)")
            self._debug_dump_cookies(cookie_jar)
            return False

        # ✅ akey는 고정 APP_KEY 사용
        akey = self.band_app_key

        # 4) requests 세션 구성 + API 호출
        sess = requests.Session()
        sess.cookies.update(cookie_jar)

        data = self._call_members_api(
            sess=sess,
            band_id=band_id_str,
            secret_key=secret_key,
            akey=akey,
            referer=f"https://www.band.us/band/{band_id_str}/post",
        )
        if not data:
            self.log_signal_func("❌ API 호출 실패(응답 없음/파싱 실패)")
            return False

        members = self._extract_members(data)
        self._save_members(members)

        self.excel_driver.convert_csv_to_excel_and_delete(self.csv_filename)
        self.log_signal_func("✅ 완료")
        return True

    # =========================================================
    # login (simple)
    # =========================================================
    def wait_for_user_confirmation(self, band_id: str) -> None:
        if not self.driver:
            return

        self.driver.get(self.site_login_url)

        event = threading.Event()
        self.msg_signal_func("로그인 완료 후 OK를 눌러주세요", "info", event)
        event.wait()

        if self._stop_event.is_set():
            return

        member_url = f"{self.site_url}/{band_id}/member"
        self.driver.get(member_url)
        self.log_signal_func("✅ 멤버 페이지 진입 완료")

    # =========================================================
    # band name (optional)
    # =========================================================
    def _extract_band_name_from_page(self, band_id: str) -> None:
        if not self.driver:
            self.band_name = ""
            return

        try:
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            el = soup.select_one(f'a.uriText[href="/band/{band_id}/post"]')
            self.band_name = el.get_text(strip=True) if el else ""
        except Exception:
            self.band_name = ""

    # =========================================================
    # requests helpers (MD)
    # =========================================================
    def _extract_path_band(self, url: str) -> str:
        u = str(url).replace("'", "%27")
        u = re.sub(r"^.*?:\/\/", "", u)
        u = re.sub(r"^[^/]+", "", u)
        return u

    def _make_md(self, url: str, secret_key: str) -> str:
        source = self._extract_path_band(url)
        mac = hmac.new(secret_key.encode("utf-8"), source.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode("ascii")

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    # =========================================================
    # cookie / normalize
    # =========================================================
    def _normalize_cookie_value(self, v: str) -> str:
        v = (v or "").strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        return v

    def _get_cookiejar_from_selenium(self) -> requests.cookies.RequestsCookieJar:
        jar = requests.cookies.RequestsCookieJar()

        if not self.driver:
            return jar

        # ✅ secretKey가 세팅되는 경로를 강제로 한번 방문
        scan_urls: List[str] = [
            "https://www.band.us/",
            "https://auth.band.us/",
            "https://www.band.us/s/login/getKey",
            "https://www.band.us/",
        ]

        for u in scan_urls:
            if self._stop_event.is_set():
                break

            try:
                self.driver.get(u)
                time.sleep(1.0)
            except Exception as e:
                self.log_signal_func(f"[cookie-scan] 이동 실패: {u} / {str(e)}")
                continue

            try:
                cookies = self.driver.get_cookies()
            except Exception as e:
                self.log_signal_func(f"[cookie-scan] get_cookies 실패: {u} / {str(e)}")
                continue

            names = sorted([c.get("name") for c in cookies if c.get("name")])
            self.log_signal_func(f"[cookie-scan] {u} count={len(cookies)} names={names}")

            for c in cookies:
                name = c.get("name")
                value = c.get("value")
                domain = c.get("domain")
                path = c.get("path") or "/"
                if not name:
                    continue
                jar.set(name, value, domain=domain, path=path)

            sk = jar.get_dict().get("secretKey") or ""
            if sk:
                self.log_signal_func(f"[cookie-scan] ✅ secretKey found (len={len(sk)}) domain/path preserved")
                break

        final_keys = sorted(list(jar.get_dict().keys()))
        self.log_signal_func(f"[cookie-scan] final jar keys({len(final_keys)}): {final_keys}")

        return jar

    def _get_cookie_value(self, jar: requests.cookies.RequestsCookieJar, key: str) -> str:
        try:
            d = jar.get_dict()
            return d.get(key) or ""
        except Exception:
            return ""

    def _debug_dump_cookies(self, jar: requests.cookies.RequestsCookieJar) -> None:
        try:
            d = jar.get_dict()
        except Exception:
            d = {}
        keys = sorted(list(d.keys()))
        self.log_signal_func(f"cookies keys({len(keys)}): {keys}")

    # =========================================================
    # api call
    # =========================================================
    def _call_members_api(
            self,
            sess: requests.Session,
            band_id: str,
            secret_key: str,
            akey: str,
            referer: str,
    ) -> Dict[str, Any]:
        ts = self._now_ms()
        url = (
            "https://api-kr.band.us/v2.0.0/get_members_of_band"
            f"?ts={ts}&band_no={band_id}"
        )

        md = self._make_md(url, secret_key)
        final_akey = (akey or "").strip() or self.band_app_key

        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "origin": "https://www.band.us",
            "referer": referer,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "device-time-zone-id": "Asia/Seoul",
            "device-time-zone-ms-offset": "32400000",
            "language": "ko",
            "md": md,
            "akey": final_akey,  # ✅ 핵심: akey는 고정(APP_KEY)
        }

        self.log_signal_func(f"API 호출: {url}")
        self.log_signal_func(f"MD: {md}")
        self.log_signal_func(f"akey(len)={len(final_akey)}")

        try:
            resp = sess.get(url, headers=headers, timeout=15)
        except Exception as e:
            self.log_signal_func(f"❌ requests 실패: {str(e)}")
            return {}

        self.log_signal_func(f"status={resp.status_code}")
        if resp.status_code != 200:
            self.log_signal_func(f"❌ 응답 실패 status={resp.status_code}")
            try:
                self.log_signal_func(
                    "resp hdr: "
                    f"content-type={resp.headers.get('content-type')} "
                    f"www-authenticate={resp.headers.get('www-authenticate')} "
                    f"set-cookie={resp.headers.get('set-cookie')}"
                )
            except Exception:
                pass
            self.log_signal_func(f"body(앞 800): {resp.text[:800]}")
            return {}

        try:
            return resp.json()
        except Exception as e:
            self.log_signal_func(f"❌ json 파싱 실패: {str(e)} / body(앞 800): {resp.text[:800]}")
            return {}

    # =========================================================
    # phone extract
    # =========================================================
    _SEP = r"[^\d]*"
    _RE_MOBILE = re.compile(rf"(01[016789]){_SEP}(\d{{3,4}}){_SEP}(\d{{3,4}})")
    _RE_070 = re.compile(rf"(070){_SEP}(\d{{3,4}}){_SEP}(\d{{4}})")
    _RE_AREA = re.compile(rf"(0(?:2|[3-6]\d)){_SEP}(\d{{3,4}}){_SEP}(\d{{4}})")
    _RE_SPECIAL = re.compile(rf"(1\d{{3}}){_SEP}(\d{{4}})")
    _RE_LOCAL = re.compile(r"(?<!\d)(\d{3,4})" + _SEP + r"(\d{4})(?!\d)")

    def _clean_text_for_scan(self, s: str) -> str:
        if not s:
            return ""
        s = s.replace("\u00A0", " ")
        s = re.sub(r"[()]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _fmt_mobile(self, a: str, b: str, c: str) -> str:
        if len(c) == 3:
            c = "0" + c
        return f"{a}-{b}-{c}"

    def extract_phones(self, name: str, desc: str) -> List[str]:
        hay = self._clean_text_for_scan(f"{name or ''} {desc or ''}")
        if not hay:
            return []

        found: List[str] = []

        for m in self._RE_MOBILE.finditer(hay):
            found.append(self._fmt_mobile(m.group(1), m.group(2), m.group(3)))

        for m in self._RE_070.finditer(hay):
            found.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")

        for m in self._RE_AREA.finditer(hay):
            found.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")

        for m in self._RE_SPECIAL.finditer(hay):
            found.append(f"{m.group(1)}-{m.group(2)}")

        for m in self._RE_LOCAL.finditer(hay):
            if m.group(1).startswith("0"):
                continue
            found.append(f"{m.group(1)}-{m.group(2)}")

        # 중복 제거(순서 유지)
        return list(dict.fromkeys(found))

    def pick_phone(self, name: str, desc: str) -> str:
        phones = self.extract_phones(name, desc)
        return phones[0] if phones else ""

    # =========================================================
    # members
    # =========================================================
    def _extract_members(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not data or data.get("result_code") != 1:
            return []
        result_data = data.get("result_data") or {}
        members = result_data.get("members") or []
        return members

    def _save_members(self, members: List[Dict[str, Any]]) -> None:
        if not self.excel_driver or not self.csv_filename:
            return

        rows: List[Dict[str, Any]] = [
            {
                "밴드명": self.band_name or "",
                "유저번호": m.get("user_no"),
                "직책": m.get("role"),
                "등록일": ms_to_yyyy_mm_dd(m.get("created_at")),
                "이름": (m.get("name") or ""),
                "설명": (m.get("description") or ""),
                "전화번호": self.pick_phone((m.get("name") or ""), (m.get("description") or "")),
            }
            for m in (members or [])
        ]

        if rows:
            self.excel_driver.append_to_csv(self.csv_filename, rows, self.columns)