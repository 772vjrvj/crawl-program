# src/utils/api_utils.py

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Literal, overload

import requests
try:
    import requests_cache
except Exception:
    requests_cache = None  # 캐시 옵션 쓸 때만 필요

from typing import cast
from bs4 import UnicodeDammit
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    Timeout, TooManyRedirects, ConnectionError, HTTPError,
    URLRequired, RequestException
)
from urllib3.util.retry import Retry


JsonType = Union[Dict[str, Any], List[Any]]
ApiResult = Union[JsonType, str, bytes, None]
HttpMethod = Literal["GET", "POST", "PATCH", "DELETE"]


class APIClient:
    def __init__(
            self,
            timeout: int = 30,
            verify: bool = True,
            retries: int = 3,
            backoff: float = 0.3,
            use_cache: bool = False,
            log_func: Optional[Callable[[str], None]] = None,
            encoding: Optional[str] = None,
            cache_ttl_sec: int = 300,
    ):
        """
        encoding: 기본 강제 인코딩 (예: "euc-kr"). None이면 자동 추론 사용
        """
        self.timeout: int = int(timeout)
        self.verify: bool = bool(verify)
        self.log_func: Optional[Callable[[str], None]] = log_func
        self.default_encoding: Optional[str] = encoding  # None → 자동 추론
        self.cache_ttl_sec: int = int(cache_ttl_sec)

        self.session: requests.Session = self._create_session(use_cache=use_cache)
        self._mount_retry_adapter(retries=retries, backoff=backoff)

    # =========================
    # logging helper
    # =========================
    def _log(self, msg: str) -> None:
        if self.log_func:
            try:
                self.log_func(msg)
            except Exception:
                logging.exception("log_func failed")

    # =========================
    # session / cache
    # =========================
    def _create_session(self, use_cache: bool) -> requests.Session:
        if not use_cache:
            return requests.Session()

        # requests-cache가 없으면 그냥 일반 세션으로 폴백
        if requests_cache is None:
            self._log("⚠️ requests-cache 미설치: cache OFF로 동작합니다.")
            return requests.Session()

        # ✅ 전역 install_cache 대신 CachedSession 사용 (세션 단위 캐시)
        try:
            sess = requests_cache.CachedSession(
                cache_name="api_cache",
                expire_after=self.cache_ttl_sec,
                allowable_methods=("GET",),  # ✅ GET만 캐시
                cache_control=True,
                stale_if_error=True,
            )
            self._log("✅ cache ON: GET-only / TTL={}s / stale-if-error".format(self.cache_ttl_sec))
            return sess  # type: ignore[return-value]
        except Exception as e:
            self._log(f"⚠️ cache 설정 실패: {e}")
            return requests.Session()

    def _mount_retry_adapter(self, retries: int, backoff: float) -> None:
        # 멱등 메서드만 재시도 + 지수 백오프 + Retry-After 존중
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=frozenset(["HEAD", "GET", "OPTIONS"]),  # ✅ 멱등만
            respect_retry_after_header=True,
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=100,
            pool_maxsize=100,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # =========================
    # public methods
    # =========================
    def get(
            self,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None,
            encoding: Optional[str] = None,
            return_bytes: bool = False,
    ) -> ApiResult:
        return self._request("GET", url, headers=headers, params=params, encoding=encoding, return_bytes=return_bytes)

    def post(
            self,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            data: Optional[Union[Dict[str, Any], str, bytes]] = None,
            json: Optional[Any] = None,
            encoding: Optional[str] = None,
            return_bytes: bool = False,
    ) -> ApiResult:
        return self._request("POST", url, headers=headers, data=data, json=json, encoding=encoding, return_bytes=return_bytes)

    def patch(
            self,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            data: Optional[Union[Dict[str, Any], str, bytes]] = None,
            json: Optional[Any] = None,
            encoding: Optional[str] = None,
            return_bytes: bool = False,
    ) -> ApiResult:
        return self._request("PATCH", url, headers=headers, data=data, json=json, encoding=encoding, return_bytes=return_bytes)

    def delete(
            self,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None,
            encoding: Optional[str] = None,
            return_bytes: bool = False,
    ) -> ApiResult:
        return self._request("DELETE", url, headers=headers, params=params, encoding=encoding, return_bytes=return_bytes)

    # =========================
    # cookie helpers
    # =========================
    def cookie_set(self, name: Optional[str], value: Optional[str]) -> None:
        if name and value is not None:
            self.session.cookies.set(name, value)

    def cookie_set_dict(self, c: Optional[Dict[str, Any]]) -> None:
        # c: selenium driver.get_cookies()의 원소(dict)
        if not c:
            return
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            return

        domain = c.get("domain") or ".band.us"
        path = c.get("path") or "/"

        # domain 앞에 점(.) 없으면 서브도메인 공유가 안 될 수 있어서 보정
        if domain and (not str(domain).startswith(".")) and str(domain).endswith("band.us"):
            domain = "." + str(domain)

        self.session.cookies.set(name, value, domain=domain, path=path)

    def cookie_get(
            self,
            name: Optional[str] = None,
            domain: Optional[str] = None,
            path: Optional[str] = None,
            as_dict: bool = False,
    ) -> Union[List[Any], List[Dict[str, Any]]]:
        """
        세션 쿠키 필터링 반환.
        - name/domain/path 조건 매칭
        - as_dict=True: dict 리스트로 반환
        """
        jar = self.session.cookies
        matched = []
        for c in jar:
            if name is not None and c.name != name:
                continue
            if domain is not None and (c.domain or "").lstrip(".") != domain.lstrip("."):
                continue
            if path is not None and (c.path or "/") != path:
                continue
            matched.append(c)

        if as_dict:
            return [
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure,
                    "expires": c.expires,
                    "rest": getattr(c, "rest", {}),
                }
                for c in matched
            ]
        return matched

    # =========================
    # decoding
    # =========================
    def _to_text(self, res: requests.Response, force_encoding: Optional[str]) -> str:
        raw = res.content  # bytes
        if force_encoding:
            try:
                return raw.decode(force_encoding, errors="replace")
            except Exception as e:
                self._log(f"⚠️ 강제 인코딩 실패({force_encoding}): {e} → 자동 추론으로 전환")

        dammit = UnicodeDammit(raw, is_html=True)
        text = dammit.unicode_markup
        if text:
            return text

        # 최후 수단
        try:
            enc = res.apparent_encoding or "utf-8"
            return raw.decode(enc, errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    # =========================
    # core request
    # =========================
    def _request(
            self,
            method: HttpMethod,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None,
            data: Optional[Union[Dict[str, Any], str, bytes]] = None,
            json: Optional[Any] = None,
            encoding: Optional[str] = None,
            return_bytes: bool = False,
    ) -> ApiResult:
        try:
            res = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                json=json,
                timeout=self.timeout,
                verify=self.verify,
            )
            res.raise_for_status()

            logging.debug("✅ %s %s | %s | %s bytes", method, url, res.status_code, len(res.content))

            if return_bytes:
                return res.content

            ctype = (res.headers.get("Content-Type") or "").lower()

            # JSON 우선
            if "application/json" in ctype or "application/ld+json" in ctype:
                return cast(JsonType, res.json())

            # HTML/XML/Text 류 안전 디코딩
            if (
                    "text/html" in ctype
                    or "application/xhtml+xml" in ctype
                    or "application/xml" in ctype
                    or "text/xml" in ctype
                    or "text/plain" in ctype
            ):
                force = encoding if encoding is not None else self.default_encoding
                return self._to_text(res, force_encoding=force)

            # 기타: JSON 시도 → 실패 시 텍스트 디코딩
            try:
                return cast(JsonType, res.json())
            except ValueError:
                force = encoding if encoding is not None else self.default_encoding
                return self._to_text(res, force_encoding=force)

        except Timeout:
            self._log("⏰ 요청 시간이 초과되었습니다.")
        except TooManyRedirects:
            self._log("🔁 리다이렉션이 너무 많습니다.")
        except ConnectionError:
            self._log("🌐 네트워크 연결 오류입니다.")
        except HTTPError as e:
            self._log(f"📛 HTTP 오류 발생: {e}")
        except URLRequired:
            self._log("❗ 유효한 URL이 필요합니다.")
        except RequestException as e:
            self._log(f"🚨 요청 실패: {e}")
        except Exception as e:
            self._log(f"❗ 예기치 못한 오류: {e}")

        return None