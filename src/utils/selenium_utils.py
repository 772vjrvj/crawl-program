# ./src/utils/selenium_utils.py
from __future__ import annotations

import os
import time
import glob
import shutil
import tempfile
import uuid
import subprocess
import re
import json
import base64
import winreg
from typing import Optional, Any, List, Dict, Mapping, TypedDict, NotRequired, cast

import undetected_chromedriver as uc
from undetected_chromedriver.patcher import Patcher

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSelectorException,
    WebDriverException,
    SessionNotCreatedException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement


DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800
SLEEP_AFTER_PROFILE = 0.3


# =========================
# === 신규 === 타입 정의
# =========================
class StartEnv(TypedDict):
    headless: bool
    timeout: int
    fixed_profile_dir: str
    chosen_profile_dir: str
    force_profile_dir: bool
    allow_profile_fallback: bool
    capture_enabled_at_start: bool
    block_images_at_start: bool

    chrome_major: NotRequired[int | None]
    profile_fallback: NotRequired[bool]
    profile_fallback_reason: NotRequired[str]


class ApiRequestMeta(TypedDict):
    requestId: str | None
    url: str
    method: str | None
    headers: Mapping[str, Any] | None
    postData: str | None


class ApiResponseMeta(TypedDict):
    requestId: str
    url: str
    status: int
    mimeType: str | None


class ApiBodyHit(ApiResponseMeta):
    bodyText: str


class SeleniumUtils:
    def __init__(self, headless: bool = False, debug: Optional[bool] = None) -> None:
        self.headless: bool = headless
        self.driver: WebDriver | None = None
        self.last_error: Exception | None = None

        if debug is None:
            debug = os.environ.get("SELENIUMUTILS_DEBUG", "").strip().lower() in ("1", "true", "y", "yes")
        self.debug: bool = bool(debug)

        self._profile_dir: str | None = None

        self.capture_enabled: bool = False
        self.block_images: bool = False

        self._net_enabled: bool = False
        self._perf_supported: bool | None = None

        self.last_start_env: StartEnv = {
            "headless": self.headless,
            "timeout": 0,
            "fixed_profile_dir": "",
            "chosen_profile_dir": "",
            "force_profile_dir": False,
            "allow_profile_fallback": True,
            "capture_enabled_at_start": False,
            "block_images_at_start": False,
        }

    # =========================================================
    # log
    # =========================================================
    def _log(self, *args: Any) -> None:
        if self.debug:
            print("[SeleniumUtils]", *args)

    # =========================================================
    # capture options
    # =========================================================
    def set_capture_options(self, enabled: bool, block_images: Optional[bool] = None) -> None:
        self.capture_enabled = bool(enabled)
        if block_images is not None:
            self.block_images = bool(block_images)

    def enable_capture_now(self) -> bool:
        d = self.driver
        if d is None:
            return False
        try:
            d.execute_cdp_cmd("Network.enable", {})
            self._net_enabled = True
            self._log("CDP Network.enable 성공")
            return True
        except Exception as e:
            self._net_enabled = False
            self._log("❌ CDP Network.enable 실패:", str(e))
            return False

    # =========================================================
    # profile
    # =========================================================
    def _new_tmp_profile(self) -> str:
        base = os.path.join(tempfile.gettempdir(), "selenium_profiles")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, f"profile_{uuid.uuid4().hex}")
        os.makedirs(path, exist_ok=True)
        return path

    def _wipe_locks(self, path: str) -> None:
        for pat in ["Singleton*", "LOCK", "LockFile", "DevToolsActivePort", "lockfile"]:
            for p in glob.glob(os.path.join(path, pat)):
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                except Exception:
                    pass

    def _is_profile_in_use(self, profile_dir: str) -> bool:
        lock_path = os.path.join(profile_dir, "SingletonLock")
        return os.path.exists(lock_path)

    def _wait_profile_unlock(self, profile_dir: str, timeout_sec: float = 6.0, poll: float = 0.2) -> bool:
        t0 = time.time()
        while time.time() - t0 < float(timeout_sec):
            if not self._is_profile_in_use(profile_dir):
                return True
            time.sleep(float(poll))
        return not self._is_profile_in_use(profile_dir)

    def _cleanup_tmp_profiles(self, keep_latest: int = 3, max_age_days: int = 2) -> None:
        base = os.path.join(tempfile.gettempdir(), "selenium_profiles")
        if not os.path.isdir(base):
            return

        now = time.time()
        max_age_sec = int(max_age_days) * 86400

        items: List[str] = []
        try:
            for name in os.listdir(base):
                p = os.path.join(base, name)
                if os.path.isdir(p) and name.startswith("profile_"):
                    items.append(p)
        except Exception:
            return

        items.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in items[int(keep_latest):]:
            try:
                age = now - os.path.getmtime(p)
                if age >= max_age_sec:
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass

    # =========================================================
    # chrome version / uc patcher
    # =========================================================
    def _find_chrome_exe_windows(self) -> Optional[str]:
        try:
            p = uc.find_chrome_executable()
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass

        pf = os.environ.get("ProgramFiles")
        pf86 = os.environ.get("ProgramFiles(x86)")
        local = os.environ.get("LOCALAPPDATA")

        candidates: List[str] = []
        if pf:
            candidates.append(os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"))
        if pf86:
            candidates.append(os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"))
        if local:
            candidates.append(os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"))

        reg_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", ""),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", ""),
        ]
        for hive, subkey, value_name in reg_paths:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    v, _ = winreg.QueryValueEx(k, value_name)
                    if v and os.path.isfile(v):
                        return v
            except Exception:
                pass

        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    def _detect_chrome_major(self) -> Optional[int]:
        chrome = self._find_chrome_exe_windows()
        if not chrome:
            return None
        try:
            out = subprocess.check_output([chrome, "--version"], stderr=subprocess.STDOUT, text=True)
            m = re.search(r"(\d+)\.", out or "")
            return int(m.group(1)) if m else None
        except Exception:
            return None

    def _get_driver_path_for_major(self, major: int) -> str:
        patcher = Patcher(version_main=major)
        patcher.auto()
        return patcher.executable_path

    def _wipe_uc_driver_cache(self) -> None:
        bases = [
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "undetected_chromedriver"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "undetected_chromedriver"),
        ]
        for base in bases:
            try:
                if os.path.isdir(base):
                    for p in glob.glob(os.path.join(base, "**", "chromedriver*"), recursive=True):
                        if os.path.isfile(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
            except Exception:
                pass

    # =========================================================
    # options
    # =========================================================
    def _build_options(self) -> uc.ChromeOptions:
        opts = uc.ChromeOptions()

        opts.add_argument("--lang=ko-KR")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-quic")
        opts.add_argument("--remote-allow-origins=*")
        opts.add_argument("--log-level=3")
        opts.add_argument("--start-maximized")

        if self.headless:
            opts.add_argument("--headless=new")

        if self.block_images:
            opts.add_experimental_option("prefs", {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2,
            })

        if self.capture_enabled:
            opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        if self._profile_dir:
            opts.add_argument(f"--user-data-dir={self._profile_dir}")

        return opts

    # =========================================================
    # CDP / performance logs
    # =========================================================
    def _ensure_perf_supported(self) -> bool:
        if self.driver is None:
            self._perf_supported = False
            return False

        if self._perf_supported is not None:
            return bool(self._perf_supported)

        try:
            _ = self.driver.get_log("performance")
            self._perf_supported = True
        except Exception as e:
            self._perf_supported = False
            self._log("performance log not supported:", str(e))
        return bool(self._perf_supported)

    def drain_performance_logs(self, max_round: int = 20, sleep_sec: float = 0.05) -> int:
        if self.driver is None:
            return 0
        if not self.capture_enabled:
            return 0
        if not self._ensure_perf_supported():
            return 0

        total = 0
        for _ in range(int(max_round)):
            try:
                logs = self.driver.get_log("performance") or []
            except Exception:
                break
            n = len(logs)
            total += n
            if n == 0:
                break
            time.sleep(float(sleep_sec))
        return total

    def _smoke_test(self, timeout_sec: float = 6.0) -> bool:
        if self.driver is None:
            return False
        try:
            self.driver.set_page_load_timeout(int(timeout_sec))
        except Exception:
            pass

        try:
            self.driver.get("about:blank")
            _ = self.driver.execute_script("return 1;")
            return True
        except Exception as e:
            self._log("smoke_test fail:", str(e))
            return False

    def _restart_with_tmp_profile(self, timeout: int, major: Optional[int]) -> WebDriver:
        self._safe_quit_driver()

        self._profile_dir = self._new_tmp_profile()
        self.last_start_env["profile_fallback"] = True
        self.last_start_env["profile_fallback_reason"] = "hang_or_smoke_test_fail"

        opts = self._build_options()

        if major:
            driver_path = self._get_driver_path_for_major(major)
            self.driver = cast(WebDriver, uc.Chrome(
                options=opts,
                driver_executable_path=driver_path,
                use_subprocess=True,
            ))
        else:
            self.driver = cast(WebDriver, uc.Chrome(
                options=opts,
                use_subprocess=True,
            ))

        try:
            self.driver.set_page_load_timeout(timeout)
        except Exception:
            pass

        return self.driver

    # =========================================================
    # request capture
    # =========================================================
    def wait_api_request(
            self,
            url_contains: str,
            query_contains: Optional[str] = None,
            timeout_sec: float = 15.0,
            poll: float = 0.2,
    ) -> Optional[ApiRequestMeta]:
        if not self.capture_enabled:
            return None
        if self.driver is None:
            return None
        if not self._net_enabled:
            if not self.enable_capture_now():
                return None
        if not self._ensure_perf_supported():
            return None

        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            logs = self.driver.get_log("performance")

            for row in logs or []:
                msg = row.get("message") if isinstance(row, dict) else None
                if not msg:
                    continue
                if "Network.requestWillBeSent" not in msg:
                    continue
                if url_contains not in msg:
                    continue
                if query_contains and query_contains not in msg:
                    continue

                j = json.loads(msg)
                m = (j or {}).get("message") or {}
                if m.get("method") != "Network.requestWillBeSent":
                    continue

                params = m.get("params") or {}
                req = params.get("request") or {}
                url = req.get("url") or ""

                if url_contains not in url:
                    continue
                if query_contains and query_contains not in url:
                    continue

                return {
                    "requestId": params.get("requestId"),
                    "url": url,
                    "method": req.get("method"),
                    "headers": req.get("headers"),
                    "postData": req.get("postData"),
                }

            time.sleep(poll)

        return None

    def _get_response_body(self, request_id: str) -> Optional[str]:
        if not request_id:
            return None
        if self.driver is None:
            return None

        try:
            res = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            if not isinstance(res, dict):
                return None

            body = res.get("body")
            if body is None:
                return None

            if res.get("base64Encoded"):
                return base64.b64decode(body).decode("utf-8", "replace")

            return str(body)
        except Exception:
            return None

    def wait_api_body(
            self,
            url_contains: str,
            query_contains: Optional[str] = None,
            timeout_sec: float = 15.0,
            poll: float = 0.2,
            require_status_200: bool = True,
    ) -> Optional[ApiBodyHit]:
        if not self.capture_enabled:
            self._log("capture_enabled is False -> wait_api_body skip")
            return None
        if self.driver is None:
            return None
        if not self._net_enabled:
            if not self.enable_capture_now():
                return None
        if not self._ensure_perf_supported():
            return None

        candidates: Dict[str, ApiResponseMeta] = {}
        finished: set[str] = set()
        failed: set[str] = set()

        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            logs = self.driver.get_log("performance")

            for row in logs or []:
                msg = row.get("message") if isinstance(row, dict) else None
                if not msg:
                    continue

                if "Network.responseReceived" in msg and (url_contains in msg) and (query_contains is None or query_contains in msg):
                    j = json.loads(msg)
                    m = (j or {}).get("message") or {}
                    if m.get("method") != "Network.responseReceived":
                        continue

                    params = m.get("params") or {}
                    resp = params.get("response") or {}
                    url = resp.get("url") or ""

                    if url_contains not in url:
                        continue
                    if query_contains and query_contains not in url:
                        continue

                    status = int(resp.get("status") or 0)
                    if require_status_200 and status != 200:
                        continue

                    rid = params.get("requestId")
                    if not rid:
                        continue

                    candidates[rid] = {
                        "requestId": rid,
                        "url": url,
                        "status": status,
                        "mimeType": resp.get("mimeType"),
                    }
                    continue

                if ("Network.loadingFinished" in msg) or ("Network.loadingFailed" in msg):
                    j = json.loads(msg)
                    m = (j or {}).get("message") or {}
                    method = m.get("method")
                    params = m.get("params") or {}
                    rid = params.get("requestId")
                    if not rid:
                        continue

                    if method == "Network.loadingFinished":
                        finished.add(rid)
                    elif method == "Network.loadingFailed":
                        failed.add(rid)

            for rid, meta in list(candidates.items()):
                if rid in failed:
                    candidates.pop(rid, None)
                    continue
                if rid not in finished:
                    continue

                body_text = self._get_response_body(rid)
                if body_text:
                    out: ApiBodyHit = {
                        "requestId": meta["requestId"],
                        "url": meta["url"],
                        "status": meta["status"],
                        "mimeType": meta["mimeType"],
                        "bodyText": body_text,
                    }
                    return out

            time.sleep(poll)

        return None

    def wait_api_json(
            self,
            url_contains: str,
            query_contains: Optional[str] = None,
            timeout_sec: float = 15.0,
            poll: float = 0.2,
            require_status_200: bool = True,
    ) -> Optional[dict[str, Any]]:
        hit = self.wait_api_body(
            url_contains=url_contains,
            query_contains=query_contains,
            timeout_sec=timeout_sec,
            poll=poll,
            require_status_200=require_status_200,
        )
        if not hit:
            return None

        text = hit.get("bodyText") or ""
        if not text:
            return None

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return cast(dict[str, Any], data)
            return None
        except Exception:
            return None

    # =========================================================
    # start / quit
    # =========================================================
    def start_driver(
            self,
            timeout: int = 30,
            force_profile_dir: Optional[str] = None,
            allow_profile_fallback: bool = True
    ) -> WebDriver:
        try:
            self._cleanup_tmp_profiles(keep_latest=3, max_age_days=2)
        except Exception:
            pass

        fixed_profile_dir = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "MyCrawlerProfile",
            "selenium_profile",
            )
        os.makedirs(fixed_profile_dir, exist_ok=True)

        chosen_profile = force_profile_dir or fixed_profile_dir

        self.last_start_env = {
            "headless": self.headless,
            "timeout": timeout,
            "fixed_profile_dir": fixed_profile_dir,
            "chosen_profile_dir": chosen_profile,
            "force_profile_dir": bool(force_profile_dir),
            "allow_profile_fallback": bool(allow_profile_fallback),
            "capture_enabled_at_start": bool(self.capture_enabled),
            "block_images_at_start": bool(self.block_images),
        }

        if force_profile_dir:
            self._profile_dir = force_profile_dir
            self._wipe_locks(self._profile_dir)
            self._wait_profile_unlock(self._profile_dir, timeout_sec=6.0, poll=0.2)
            time.sleep(SLEEP_AFTER_PROFILE)
        else:
            if self._is_profile_in_use(chosen_profile):
                if allow_profile_fallback:
                    self._profile_dir = self._new_tmp_profile()
                    self.last_start_env["profile_fallback"] = True
                    self._log("fixed profile in-use -> tmp profile:", self._profile_dir)
                else:
                    self._profile_dir = chosen_profile
                    self.last_start_env["profile_fallback"] = False
                    self._wipe_locks(self._profile_dir)
                    self._wait_profile_unlock(self._profile_dir, timeout_sec=8.0, poll=0.2)
                    time.sleep(SLEEP_AFTER_PROFILE)
            else:
                self._profile_dir = chosen_profile
                self.last_start_env["profile_fallback"] = False
                self._wipe_locks(self._profile_dir)
                time.sleep(SLEEP_AFTER_PROFILE)

        major = self._detect_chrome_major()
        self.last_start_env["chrome_major"] = major

        try:
            opts = self._build_options()

            def _create_driver() -> WebDriver:
                if major:
                    driver_path = self._get_driver_path_for_major(major)
                    return cast(WebDriver, uc.Chrome(
                        options=opts,
                        driver_executable_path=driver_path,
                        use_subprocess=True,
                    ))
                return cast(WebDriver, uc.Chrome(
                    options=opts,
                    use_subprocess=True,
                ))

            try:
                self.driver = _create_driver()
            except SessionNotCreatedException as e:
                self.last_error = e
                self._log("SessionNotCreatedException:", str(e))
                self._safe_quit_driver()

                self._wipe_uc_driver_cache()

                if not self.last_start_env.get("profile_fallback"):
                    self._profile_dir = self._new_tmp_profile()
                    self.last_start_env["profile_fallback"] = True
                    self.last_start_env["profile_fallback_reason"] = "session_not_created_retry"
                    opts = self._build_options()

                time.sleep(0.5)
                self.driver = _create_driver()

            try:
                self.driver.set_page_load_timeout(timeout)
            except Exception:
                pass

            if not self._smoke_test(timeout_sec=6.0):
                self._log("hang detected -> restart with tmp profile once")
                self._restart_with_tmp_profile(timeout=timeout, major=major)

                if not self._smoke_test(timeout_sec=6.0):
                    raise WebDriverException("driver hang after restart(tmp profile)")

            return self.driver

        except SessionNotCreatedException as e:
            self.last_error = e
            self._safe_quit_driver()
            self._wipe_uc_driver_cache()
            raise e

        except Exception as e:
            self.last_error = e
            self._safe_quit_driver()
            raise e

    def _safe_quit_driver(self) -> None:
        d = self.driver
        self.driver = None
        if d is None:
            return
        try:
            d.quit()
        except Exception:
            pass

    def quit(self) -> None:
        self._safe_quit_driver()

        try:
            fixed_profile_dir = os.path.join(
                os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                "MyCrawlerProfile",
                "selenium_profile",
                )
            if self._profile_dir and os.path.isdir(self._profile_dir) and self._profile_dir != fixed_profile_dir:
                shutil.rmtree(self._profile_dir, ignore_errors=True)
        except Exception:
            pass
        finally:
            self._profile_dir = None
            self._net_enabled = False
            self._perf_supported = None

    # =========================================================
    # helpers
    # =========================================================
    def wait_element(self, by: Any, selector: str, timeout: int = 10) -> Optional[WebElement]:
        if self.driver is None:
            return None
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except Exception as e:
            self.last_error = e
            return None

    @staticmethod
    def explain_exception(context: str, e: Exception) -> str:
        if isinstance(e, NoSuchElementException):
            return f"❌ {context}: 요소 없음"
        if isinstance(e, StaleElementReferenceException):
            return f"❌ {context}: Stale 요소"
        if isinstance(e, TimeoutException):
            return f"⏱️ {context}: 시간 초과"
        if isinstance(e, ElementClickInterceptedException):
            return f"🚫 {context}: 클릭 방해"
        if isinstance(e, ElementNotInteractableException):
            return f"🚫 {context}: 비활성 요소"
        if isinstance(e, InvalidSelectorException):
            return f"🚫 {context}: 선택자 오류"
        if isinstance(e, WebDriverException):
            return f"⚠️ {context}: WebDriver 오류"
        return f"❗ {context}: 알 수 없는 오류"