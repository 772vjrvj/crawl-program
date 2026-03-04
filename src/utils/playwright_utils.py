# PlaywrightUtils.py
# -*- coding: utf-8 -*-

import os
import time
import glob
import shutil
import tempfile
import uuid
from typing import Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

DEFAULT_WIDTH  = 1280
DEFAULT_HEIGHT = 800
SLEEP_AFTER_PROFILE = 0.2

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"


class PlaywrightUtils:
    def __init__(self, headless: bool = False):
        self.headless = headless

        self._pw = None
        self.context = None
        self.page = None

        self.profile_dir: Optional[str] = None
        self._is_temp_profile: bool = False  # ✅ 핵심
        self.last_error: Optional[Exception] = None

    # ----- 내부 유틸 -----
    def _new_tmp_profile(self) -> str:
        base = os.path.join(tempfile.gettempdir(), "playwright_profiles")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, f"profile_{uuid.uuid4().hex}")
        os.makedirs(path, exist_ok=True)
        return path

    def _wipe_locks(self, path: str):
        for pat in ["Singleton*", "LOCK", "LockFile", "DevToolsActivePort", "lockfile"]:
            for p in glob.glob(os.path.join(path, pat)):
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                except Exception:
                    pass

    # ----- 외부에서 쓰는 함수 -----
    def start_driver(self, timeout: int = 30, use_persistent_profile: bool = True):
        """
        use_persistent_profile=True:
            LOCALAPPDATA에 고정 프로필을 써서 로그인 유지(권장)
        use_persistent_profile=False:
            temp 프로필(실험/일회성) - quit()에서 삭제
        """
        if use_persistent_profile:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            profile_dir = os.path.join(base, "MyCrawlerProfile", "pw_profile")
            os.makedirs(profile_dir, exist_ok=True)
            self.profile_dir = profile_dir
            self._is_temp_profile = False
        else:
            self.profile_dir = self._new_tmp_profile()
            self._is_temp_profile = True

        self._wipe_locks(self.profile_dir)
        time.sleep(SLEEP_AFTER_PROFILE)

        try:
            self._pw = sync_playwright().start()

            args = [
                "--start-maximized",
                "--lang=ko-KR",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            if self.headless:
                args += ["--no-sandbox"]

            self.context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=self.headless,
                viewport=None,
                args=args,
                channel="chrome",
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                user_agent=DEFAULT_UA,
            )

            self.page = self.context.new_page()
            self.page.set_default_timeout(timeout * 1000)
            return self.page

        except Exception as e:
            self.last_error = e
            self.quit()
            raise

    def quit(self):
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._pw = None
            self.context = None
            self.page = None

            # ✅ temp 프로필만 삭제
            if self._is_temp_profile and self.profile_dir and os.path.isdir(self.profile_dir):
                try:
                    shutil.rmtree(self.profile_dir, ignore_errors=True)
                except Exception:
                    pass

            self.profile_dir = None
            self._is_temp_profile = False

    # ----- 헬퍼 -----
    def goto(self, url: str, wait_until: str = "networkidle"):
        try:
            self.page.goto(url, wait_until=wait_until)
            return True
        except Exception as e:
            self.last_error = e
            return False

    def wait_selector(self, selector: str, timeout: int = 10):
        try:
            self.page.wait_for_selector(selector, timeout=timeout * 1000)
            return True
        except PWTimeoutError as e:
            self.last_error = e
            return False
        except Exception as e:
            self.last_error = e
            return False

    def get_html(self) -> str:
        try:
            return self.page.content()
        except Exception as e:
            self.last_error = e
            return ""

    @staticmethod
    def explain_exception(context: str, e: Exception) -> str:
        msg = str(e)
        if "Timeout" in msg:
            return f"⏱️ {context}: 시간 초과"
        return f"❗ {context}: {msg}"