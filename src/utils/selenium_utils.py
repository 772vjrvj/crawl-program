# -*- coding: utf-8 -*-
"""
SeleniumUtils (undetected-chromedriver 기반 유틸)

목적
- Windows 환경에서 Chrome 실행 파일 경로를 탐색하고(레지스트리/기본 경로),
  undetected_chromedriver(uc)로 안정적으로 드라이버를 기동한다.
- 필요 시 CDP(Network) + performance log를 이용해 특정 API 호출의
  request/response/body(json)까지 캡처한다.
- 임시 프로필을 생성/정리하여 실행 간 세션 충돌을 줄인다.

주의
- performance log 캡처는 Chrome/드라이버 조합에 따라 지원 여부가 달라질 수 있다.
- Network.getResponseBody는 로딩 완료(loadingFinished) 이후에만 정상 동작하는 편이다.

===============================================================================
[Performance Log + CDP 기반 네트워크 캡처 설명]

이 모듈은 Chrome DevTools Protocol(CDP)과 performance log를 함께 사용하여
브라우저 내부에서 발생하는 특정 API 요청/응답을 감지하고,
최종적으로 응답 body(JSON 등)까지 추출하기 위한 유틸리티이다.

--------------------------------------------------------------------------------
1. CDP (Chrome DevTools Protocol)

CDP는 Chrome 개발자도구(F12)가 내부적으로 사용하는 디버깅 프로토콜이다.
Selenium에서는 driver.execute_cdp_cmd()를 통해 직접 명령을 호출할 수 있다.

주요 사용 예:
- Network.enable
    → 네트워크 이벤트 도메인 활성화
- Network.getResponseBody
    → 특정 requestId의 응답 body 조회

CDP는 "명령 실행"과 "응답 body 직접 조회"에 강점이 있다.

--------------------------------------------------------------------------------
2. Performance Log

Chrome에서 발생하는 네트워크 이벤트를 로그 형태로 수집하는 기능이다.

driver.get_log("performance") 로 읽을 수 있으며,
다음과 같은 이벤트들이 포함된다:

- Network.requestWillBeSent   (요청 발생)
- Network.responseReceived    (응답 헤더 도착)
- Network.loadingFinished     (다운로드 완료)
- Network.loadingFailed       (다운로드 실패)

Performance log는 "이벤트 감지 및 requestId 추적"에 사용된다.

--------------------------------------------------------------------------------
3. 왜 둘을 같이 사용하는가?

Performance Log만 사용하면:
- 요청/응답 메타 정보(URL, status 등)는 확인 가능
- 하지만 응답 body는 직접 얻기 어렵다

CDP만 사용하면:
- 응답 body는 가져올 수 있음
- 하지만 어떤 requestId가 목표 요청인지 찾는 과정이 필요함

따라서 일반적인 실무 패턴은 다음과 같다:

1) Performance log에서 특정 URL을 가진 요청을 탐지한다.
2) 해당 요청의 requestId를 확보한다.
3) CDP(Network.getResponseBody)로 body를 가져온다.

본 유틸은 위 3단계를 자동화하여,
특정 API의 JSON 응답을 안정적으로 추출하는 것을 목적으로 한다.

--------------------------------------------------------------------------------
4. 사용 전제 조건

- capture_enabled=True 설정 필요
- ChromeOptions에 performance logging 활성화 필요
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
- CDP Network.enable 호출 필요

--------------------------------------------------------------------------------
5. 주요 사용 목적

- 화면에 렌더링되지 않는 내부 API(JSON) 응답 추출
- F12 네트워크 탭에 보이는 요청 자동 추적
- 백엔드 응답 기반 데이터 수집

===============================================================================
"""

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import winreg
from typing import Optional, Dict, Any, List, Set, Union, TypedDict

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSelectorException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from typing import Optional, Callable, Any  # === 신규 ===


class ApiRequestMeta(TypedDict, total=False):
    requestId: str
    url: str
    method: str
    headers: Any
    postData: Optional[str]


class ApiBodyMeta(TypedDict, total=False):
    requestId: str
    url: str
    status: int
    mimeType: Optional[str]
    bodyText: str


class SeleniumUtils:
    """
    Selenium/undetected-chromedriver 공용 유틸 클래스.

    주요 기능
    - Chrome 경로 탐색 / 버전 major 감지
    - uc.ChromeOptions 구성
    - uc 드라이버 기동/종료 및 임시 프로필 정리
    - CDP(Network) enable 및 performance log 기반 API 캡처
    """

    def __init__(
            self,
            headless: bool = False,
            debug: Optional[bool] = None,
            log_func: Optional[Callable[[str], None]] = None,  # === 신규 ===
    ):
        """
        Args:
            headless: headless 실행 여부 (Chrome '--headless=new' 사용)
            debug: 디버깅 로그 출력 여부
                   None이면 환경변수 SELENIUMUTILS_DEBUG로 결정(1/true/y/yes)
        """
        self.headless = bool(headless)

        # WebDriver 인스턴스 (start_driver 호출 후 유효)
        self.driver: Optional[WebDriver] = None

        # 가장 최근 발생한 예외(내부적으로 잡아두는 용도)
        self.last_error: Optional[Exception] = None

        # debug 옵션 자동 결정
        if debug is None:
            debug = os.environ.get("SELENIUMUTILS_DEBUG", "").strip().lower() in ("1", "true", "y", "yes")
        self.debug = bool(debug)

        self.log_func = log_func

        # user-data-dir로 사용할 프로필 디렉토리 (임시 생성)
        self._profile_dir: Optional[str] = None

        # Network/performance 캡처 기능 on/off
        self.capture_enabled: bool = False

        # 이미지 로딩 차단(속도/트래픽 절감용)
        self.block_images: bool = False

        # CDP Network.enable 호출 여부(세션 단위)
        self._net_enabled: bool = False

        # performance log 지원 여부 캐시(드라이버별 지원 다름)
        self._perf_supported: Optional[bool] = None

    # ---------------------------------------------------------------------
    # Logging / Config
    # ---------------------------------------------------------------------
    def _log(self, *args: Any, force: bool = False) -> None:
        """
        debug 모드일 때만 로그 출력.
        - log_func가 있으면 UI로 전달
        - 없으면 콘솔 print fallback
        """
        if not (self.debug or force):
            return

        msg = "[SeleniumUtils] " + " ".join(str(x) for x in args)

        # === 신규 === UI 로그로 전달
        if self.log_func:
            try:
                self.log_func(msg)
                return
            except Exception:
                # log_func가 터져도 크롤링이 죽지 않도록 fallback
                pass

        # fallback
        print(msg)



    def set_capture_options(self, enabled: bool, block_images: Optional[bool] = None) -> None:
        """
        네트워크 캡처 옵션 설정.

        Args:
            enabled: performance log + CDP 캡처 활성화 여부
            block_images: 이미지 로딩 차단 여부(옵션). None이면 기존값 유지
        """
        self.capture_enabled = bool(enabled)
        if block_images is not None:
            self.block_images = bool(block_images)


    # ---------------------------------------------------------------------
    # Profile handling
    # ---------------------------------------------------------------------
    def _new_tmp_profile(self) -> str:
        """
        임시 user-data-dir 프로필 디렉토리를 생성한다.

        Returns:
            생성된 프로필 경로
        """
        base = os.path.join(tempfile.gettempdir(), "selenium_profiles")
        os.makedirs(base, exist_ok=True)

        # 실행마다 UUID로 고유 폴더 생성(충돌 방지)
        path = os.path.join(base, f"profile_{uuid.uuid4().hex}")
        os.makedirs(path, exist_ok=True)
        return path

    # ---------------------------------------------------------------------
    # Chrome discovery / version
    # ---------------------------------------------------------------------
    def _find_chrome_exe_windows(self) -> Optional[str]:
        """
        Windows에서 Chrome 실행 파일 경로를 최대한 탐색한다.
        우선순위:
        1) uc.find_chrome_executable()
        2) ProgramFiles/LocalAppData 기본 설치 경로
        3) 레지스트리 App Paths

        Returns:
            chrome.exe 절대 경로 또는 None
        """
        # 1) uc 내장 탐색
        try:
            p = uc.find_chrome_executable()
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass

        # 2) 대표 설치 경로 후보
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

        # 3) 레지스트리 App Paths
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

        # 후보 경로 순회
        for p in candidates:
            if p and os.path.isfile(p):
                return p

        return None

    def _detect_chrome_major(self, chrome_exe: Optional[str]) -> Optional[int]:
        """
        chrome.exe --version 출력에서 major 버전을 추출한다.

        Args:
            chrome_exe: chrome.exe 경로

        Returns:
            major 버전(int) 또는 None
        """
        if not chrome_exe or not os.path.isfile(chrome_exe):
            return None
        try:
            out = subprocess.check_output([chrome_exe, "--version"], stderr=subprocess.STDOUT, text=True)
            m = re.search(r"(\d+)\.", out or "")
            return int(m.group(1)) if m else None
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # UC cache handling
    # ---------------------------------------------------------------------
    def wipe_uc_driver_cache(self) -> None:
        """
        undetected_chromedriver가 내려받아 캐시해두는 드라이버/패치 파일을 삭제한다.
        - 드라이버 생성 실패 시 '깨진 캐시' 가능성을 줄이기 위한 재시도 전략으로 사용.
        """
        bases = [
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "undetected_chromedriver"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "undetected_chromedriver"),
        ]
        for base in bases:
            try:
                if os.path.isdir(base):
                    shutil.rmtree(base, ignore_errors=True)
                    self._log("uc cache removed:", base)
            except Exception as e:
                self._log("uc cache remove failed:", base, str(e))

    # ---------------------------------------------------------------------
    # Options building
    # ---------------------------------------------------------------------
    def _build_options(self, chrome_exe: Optional[str]) -> uc.ChromeOptions:
        """
        uc.ChromeOptions를 구성한다.
        - locale, 팝업/첫실행 비활성화, 로그 레벨, 최대화 등
        - block_images/capture_enabled/profile_dir 적용

        Args:
            chrome_exe: chrome.exe 경로(있으면 binary_location 지정)

        Returns:
            uc.ChromeOptions 객체
        """
        opts = uc.ChromeOptions()

        # === 기본 실행 옵션(실무에서 흔히 세팅) ===
        opts.add_argument("--lang=ko-KR")
        # 브라우저 기본 언어를 한국어로 설정 (사이트 언어/로케일 영향 방지)

        opts.add_argument("--disable-popup-blocking")
        # Chrome 기본 팝업 차단 기능 비활성화 (로그인/인증 팝업 막힘 방지)

        opts.add_argument("--no-first-run")
        # Chrome 최초 실행 시 뜨는 환영/초기 설정 화면 방지

        opts.add_argument("--no-default-browser-check")
        # 기본 브라우저 설정 여부 확인 팝업 방지

        opts.add_argument("--disable-dev-shm-usage")
        # /dev/shm(shared memory) 대신 디스크 사용 (리눅스/도커 환경에서 크래시 방지용)
        # Windows에서는 영향 거의 없음

        opts.add_argument("--disable-quic")
        # QUIC 프로토콜 비활성화 (일부 네트워크/프록시 환경에서 불안정 방지)

        opts.add_argument("--log-level=3")
        # Chrome 내부 로그 레벨 최소화 (0=verbose ~ 3=error만 출력)

        # opts.add_argument("--start-maximized")
        # 브라우저를 최대화 상태로 시작 (반응형 레이아웃 오작동 방지)
        opts.add_argument("--window-size=600,700")
        # 가로 1000px, 세로 900px로 시작

        # Headless 모드
        if self.headless:
            opts.add_argument("--headless=new")

        # 이미지 로딩 차단(속도 향상/트래픽 절감)
        if self.block_images:
            opts.add_experimental_option(
                "prefs",
                {
                    "profile.managed_default_content_settings.images": 2,
                    "profile.default_content_setting_values.notifications": 2,
                },
            )

        # Network/performance 캡처를 위해 performance log 활성화
        # (드라이버/브라우저 조합에 따라 지원 안 될 수 있음)
        if self.capture_enabled:
            opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # 임시 프로필 디렉토리(user-data-dir)
        if self._profile_dir:
            opts.add_argument(f"--user-data-dir={self._profile_dir}")

        # chrome binary 지정(탐색 성공 시)
        if chrome_exe:
            try:
                opts.binary_location = chrome_exe
            except Exception:
                pass

        return opts



    # ---------------------------------------------------------------------
    # CDP / performance log
    # ---------------------------------------------------------------------
    def enable_capture_now(self) -> bool:
        """
        CDP Network domain을 enable 한다.
        - performance log만 켜도 request/response 이벤트는 찍히지만,
          getResponseBody 등 일부는 Network.enable이 필요할 때가 많아 같이 호출한다.

        Returns:
            성공 여부
        """
        if not self.driver:
            return False
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            self._net_enabled = True
            return True
        except Exception as e:
            self._net_enabled = False
            self._log("Network.enable failed:", str(e))
            return False

    def _ensure_perf_supported(self) -> bool:
        """
        performance log를 driver.get_log('performance')로 읽을 수 있는지 확인한다.
        지원 여부는 드라이버/Chrome 조합에 따라 달라질 수 있으므로 캐시한다.

        Returns:
            지원 여부
        """
        if self._perf_supported is not None:
            return bool(self._perf_supported)

        if not self.driver:
            self._perf_supported = False
            return False

        try:
            _ = self.driver.get_log("performance")
            self._perf_supported = True
        except Exception as e:
            self._perf_supported = False
            self._log("performance log not supported:", str(e))

        return bool(self._perf_supported)

    def _get_response_body(self, request_id: str) -> Optional[str]:
        """
        CDP Network.getResponseBody로 특정 requestId의 response body를 가져온다.

        Args:
            request_id: CDP requestId

        Returns:
            response body(utf-8 문자열) 또는 None

        Note:
            base64Encoded가 true인 경우 디코딩이 필요하다.
        """
        if not request_id:
            return None
        if not self.driver:
            return None

        try:
            res = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            if not isinstance(res, dict):
                return None

            body = res.get("body")
            if body is None:
                return None

            # 일부 응답은 base64로 인코딩되어 온다.
            if res.get("base64Encoded"):
                return base64.b64decode(body).decode("utf-8", "replace")

            return str(body)
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # Network capture helpers
    # ---------------------------------------------------------------------
    def wait_api_request(
            self,
            url_contains: str,
            query_contains: Optional[str] = None,
            timeout_sec: float = 15.0,
            poll: float = 0.2,
    ) -> Optional[ApiRequestMeta]:
        """
        performance log에서 특정 API 요청(requestWillBeSent)을 탐지한다.

        Args:
            url_contains: URL에 포함되어야 하는 문자열(필수)
            query_contains: URL/로그 메시지에 추가로 포함되어야 하는 문자열(옵션)
            timeout_sec: 최대 대기 시간(초)
            poll: 폴링 간격(초)

        Returns:
            request 메타(dict): requestId/url/method/headers/postData 또는 None

        전제 조건:
            - set_capture_options(enabled=True)로 capture_enabled가 true여야 한다.
            - Network.enable 및 performance log 지원이 필요하다.
        """
        if not self.capture_enabled:
            return None
        if not self.driver:
            return None
        if not self._net_enabled and not self.enable_capture_now():
            return None
        if not self._ensure_perf_supported():
            return None

        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            logs = self.driver.get_log("performance")

            # performance log는 JSON 문자열을 담고 있는 'message' 필드를 가진 dict 리스트 형태
            for row in logs or []:
                msg = row.get("message") if isinstance(row, dict) else None
                if not msg:
                    continue

                # 빠른 필터링(문자열 포함 여부로 1차 거르기)
                if "Network.requestWillBeSent" not in msg:
                    continue
                if url_contains not in msg:
                    continue
                if query_contains and query_contains not in msg:
                    continue

                # 메시지 파싱
                j = json.loads(msg)
                m = (j or {}).get("message") or {}
                if m.get("method") != "Network.requestWillBeSent":
                    continue

                params = m.get("params") or {}
                req = params.get("request") or {}
                url = req.get("url") or ""

                # 최종적으로 URL 기준으로 재검증
                if url_contains not in url:
                    continue
                if query_contains and query_contains not in url:
                    continue

                return {
                    "requestId": params.get("requestId") or "",
                    "url": url,
                    "method": req.get("method") or "",
                    "headers": req.get("headers"),
                    "postData": req.get("postData"),
                }

            time.sleep(poll)

        return None

    def wait_api_body(
            self,
            url_contains: str,
            query_contains: Optional[str] = None,
            timeout_sec: float = 15.0,
            poll: float = 0.2,
            require_status_200: bool = True,
    ) -> Optional[ApiBodyMeta]:
        """
        performance log + CDP를 이용해 특정 API 응답 body를 가져온다.

        처리 흐름
        1) responseReceived에서 requestId/상태/URL을 candidates에 저장
        2) loadingFinished(또는 loadingFailed)로 완료 여부를 추적
        3) 완료된 requestId에 대해 Network.getResponseBody로 실제 body를 가져옴

        Args:
            url_contains: URL에 포함되어야 하는 문자열(필수)
            query_contains: URL/로그 메시지에 추가로 포함되어야 하는 문자열(옵션)
            timeout_sec: 최대 대기 시간(초)
            poll: 폴링 간격(초)
            require_status_200: True면 status=200만 허용

        Returns:
            dict: requestId/url/status/mimeType/bodyText 또는 None
        """
        if not self.capture_enabled:
            return None
        if not self.driver:
            return None
        if not self._net_enabled and not self.enable_capture_now():
            return None
        if not self._ensure_perf_supported():
            return None

        # responseReceived에서 잡은 후보들(requestId -> meta)
        candidates: Dict[str, ApiBodyMeta] = {}

        # 로딩 완료/실패 집합
        finished: Set[str] = set()
        failed: Set[str] = set()

        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            logs = self.driver.get_log("performance")

            for row in logs or []:
                msg = row.get("message") if isinstance(row, dict) else None
                if not msg:
                    continue

                # === responseReceived 탐지: response 메타 확보 ===
                if "Network.responseReceived" in msg and (url_contains in msg) and (
                        query_contains is None or query_contains in msg
                ):
                    j = json.loads(msg)
                    m = (j or {}).get("message") or {}
                    if m.get("method") != "Network.responseReceived":
                        continue

                    params = m.get("params") or {}
                    resp = params.get("response") or {}
                    url = resp.get("url") or ""

                    # URL 기준 필터
                    if url_contains not in url:
                        continue
                    if query_contains and query_contains not in url:
                        continue

                    status = int(resp.get("status") or 0)
                    if require_status_200 and status != 200:
                        # 200만 받도록 설정되어 있으면 다른 상태는 스킵
                        continue

                    rid = params.get("requestId")
                    if not rid:
                        continue

                    candidates[str(rid)] = {
                        "requestId": str(rid),
                        "url": url,
                        "status": status,
                        "mimeType": resp.get("mimeType"),
                    }
                    continue

                # === 로딩 완료/실패 추적 ===
                if ("Network.loadingFinished" in msg) or ("Network.loadingFailed" in msg):
                    j = json.loads(msg)
                    m = (j or {}).get("message") or {}
                    method = m.get("method")
                    params = m.get("params") or {}
                    rid = params.get("requestId")
                    if not rid:
                        continue

                    rid_s = str(rid)
                    if method == "Network.loadingFinished":
                        finished.add(rid_s)
                    elif method == "Network.loadingFailed":
                        failed.add(rid_s)

            # === 완료된 후보에 대해 body 수집 ===
            for rid, meta in list(candidates.items()):
                if rid in failed:
                    candidates.pop(rid, None)
                    continue

                if rid not in finished:
                    continue

                body_text = self._get_response_body(rid)
                if body_text:
                    out: ApiBodyMeta = dict(meta)
                    out["bodyText"] = body_text
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
    ) -> Optional[Dict[str, Any]]:
        """
        wait_api_body로 받은 response bodyText를 JSON으로 파싱해 반환한다.

        Args:
            url_contains: URL 포함 문자열
            query_contains: 추가 포함 문자열
            timeout_sec: 최대 대기 시간
            poll: 폴링 간격
            require_status_200: status 200만 허용 여부

        Returns:
            파싱된 JSON(dict) 또는 None
        """
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
            return json.loads(text)
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------------------
    def dump_env(self) -> Dict[str, Any]:
        """
        실행 환경/버전/설정 정보를 진단용으로 반환한다.

        Returns:
            chrome 경로/major, 프로필 경로, headless/capture/block_images,
            selenium/uc 버전 등을 담은 dict
        """
        chrome_exe = self._find_chrome_exe_windows()
        info: Dict[str, Any] = {
            "chrome_exe": chrome_exe,
            "chrome_major": self._detect_chrome_major(chrome_exe),
            "profile_dir": self._profile_dir,
            "headless": self.headless,
            "capture_enabled": self.capture_enabled,
            "block_images": self.block_images,
        }
        try:
            import selenium
            info["selenium_version"] = getattr(selenium, "__version__", "")
        except Exception:
            info["selenium_version"] = ""
        try:
            info["uc_version"] = getattr(uc, "__version__", "")
        except Exception:
            info["uc_version"] = ""
        return info

    # ---------------------------------------------------------------------
    # Driver lifecycle
    # ---------------------------------------------------------------------
    def _safe_quit_driver(self) -> None:
        """
        driver.quit()를 안전하게 수행한다(예외 무시).
        - quit 중 예외가 나더라도 이후 cleanup이 진행되도록 보호한다.
        """
        d = self.driver
        self.driver = None
        if not d:
            return
        try:
            d.quit()
        except Exception:
            pass


    def start_driver(self, timeout: int = 30, force_major: Optional[int] = None) -> WebDriver:
        """
        uc.Chrome 드라이버를 기동한다.
        - 임시 프로필 생성 후 user-data-dir로 지정
        - Chrome exe 탐색 후 options에 반영
        - driver 생성 실패 시 uc 캐시 삭제 후 1회 재시도

        Args:
            timeout: page_load_timeout (초)
            force_major: 강제 major 버전(옵션). None이면 내부 기본값 사용

        Returns:
            생성된 WebDriver(uc.Chrome)

        Raises:
            드라이버 생성이 최종 실패할 경우 예외를 그대로 raise
        """

        self.cleanup_old_profiles(older_than_hours=24)

        # 실행마다 새 프로필(세션/락 충돌 방지)
        self._profile_dir = self._new_tmp_profile()

        chrome_exe = self._find_chrome_exe_windows()

        # NOTE: 원본 코드 로직 유지(없으면 145 기본)
        major = int(force_major) if force_major else 145

        def _create_driver(opts_any: uc.ChromeOptions) -> WebDriver:
            """
            uc.Chrome 생성 래퍼.
            - version_main에 major를 지정하여 chromedriver 매칭을 유도한다.
            """
            return uc.Chrome(
                options=opts_any,
                version_main=int(major),
            )

        try:
            # 1차 생성 시도
            opts = self._build_options(chrome_exe)
            t = time.time()
            self.driver = _create_driver(opts)
            self._force_window(600, 700)  # 여기(1차 생성 직후)
            self._log("driver create time:", time.time() - t)

            # 페이지 로드 타임아웃 설정(지원 안 되면 무시)
            try:
                self.driver.set_page_load_timeout(timeout)
            except Exception:
                pass

            return self.driver

        except Exception as e:
            # 실패 기록 + 안전 종료
            self._log("start failed:", str(e))
            self.last_error = e
            self._safe_quit_driver()

            # uc 캐시 삭제(깨진 캐시/패치 파일 방어)
            try:
                self.wipe_uc_driver_cache()
            except Exception:
                pass

            # 2차 재시도
            try:
                opts = self._build_options(chrome_exe)
                t = time.time()
                self.driver = _create_driver(opts)
                self._force_window(600, 700)  # 여기(1차 생성 직후)
                self._log("driver create time:", time.time() - t)

                try:
                    self.driver.set_page_load_timeout(timeout)
                except Exception:
                    pass

                return self.driver

            except Exception as e2:
                # 재시도도 실패하면 최종 raise
                self.last_error = e2
                self._safe_quit_driver()
                raise e2


    def quit(self) -> None:
        """
        드라이버 종료 + 임시 프로필 디렉토리 정리 + 캡처 상태 초기화.
        """
        self._safe_quit_driver()

        # 임시 프로필 폴더 정리
        try:
            if self._profile_dir and os.path.isdir(self._profile_dir):
                shutil.rmtree(self._profile_dir, ignore_errors=True)
        except Exception:
            pass

        self._profile_dir = None
        self._net_enabled = False
        self._perf_supported = None


    def _force_window(self, w: int = 600, h: int = 700) -> None:
        # === 신규 === uc/Chrome 조합에서 --window-size가 무시되는 케이스가 있어 생성 직후 강제 적용
        if not self.driver:
            return
        try:
            self.driver.set_window_position(0, 0)
            self.driver.set_window_size(int(w), int(h))
            self._log("window forced:", self.driver.get_window_size(), self.driver.get_window_position())
        except Exception as e:
            self._log("window force failed:", str(e))


    def cleanup_old_profiles(self, older_than_hours: int = 24) -> int:
        base = os.path.join(tempfile.gettempdir(), "selenium_profiles")
        if not os.path.isdir(base):
            return 0

        now = time.time()
        removed = 0

        for name in os.listdir(base):
            if not name.startswith("profile_"):
                continue
            path = os.path.join(base, name)
            if not os.path.isdir(path):
                continue
            try:
                mtime = os.path.getmtime(path)
                if (now - mtime) >= (older_than_hours * 3600):
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except Exception:
                # 청소 실패는 무시(권한/락 등)
                pass

        return removed

    # ---------------------------------------------------------------------
    # Element helpers
    # ---------------------------------------------------------------------
    def wait_element(self, by: Union[By, str], selector: str, timeout: int = 10) -> Optional[WebElement]:
        """
        지정 selector의 요소가 DOM에 나타날 때까지 대기 후 반환한다(presence 기준).

        Args:
            by: selenium By 타입 등 (예: By.CSS_SELECTOR)
            selector: 선택자 문자열
            timeout: 최대 대기 시간(초)

        Returns:
            WebElement 또는 None(예외 발생 시)
        """
        if not self.driver:
            return None
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except Exception as e:
            self.last_error = e
            return None

    # ---------------------------------------------------------------------
    # Exception explain helper
    # ---------------------------------------------------------------------
    @staticmethod
    def explain_exception(context: str, e: Exception) -> str:
        """
        Selenium 예외를 사용자 친화적인 메시지로 매핑한다.

        Args:
            context: 오류 발생 맥락(예: "로그인 버튼 클릭")
            e: 발생 예외

        Returns:
            한국어 요약 메시지
        """
        if isinstance(e, NoSuchElementException):
            return f"{context}: 요소 없음"
        if isinstance(e, StaleElementReferenceException):
            return f"{context}: Stale 요소"
        if isinstance(e, TimeoutException):
            return f"{context}: 시간 초과"
        if isinstance(e, ElementClickInterceptedException):
            return f"{context}: 클릭 방해"
        if isinstance(e, ElementNotInteractableException):
            return f"{context}: 비활성 요소"
        if isinstance(e, InvalidSelectorException):
            return f"{context}: 선택자 오류"
        if isinstance(e, WebDriverException):
            return f"{context}: WebDriver 오류"
        return f"{context}: 알 수 없는 오류"