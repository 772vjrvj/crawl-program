# src/workers/main/api_naver_land_real_estate_loc_all_set_load_worker.py
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

from src.core.global_state import GlobalState
from src.utils.api_utils import APIClient
from src.utils.chrome_macro import ChromeMacro
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.utils.str_utils import split_comma_keywords
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverLandRealEstateLocAllSetLoadWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.current_cnt: int = 0
        self.total_cnt: int = 0
        self.driver: Any = None
        self.columns: Optional[List[str]] = None

        self.csv_filename: Optional[str] = None
        self.folder_path: str = ""
        self.out_dir: str = "output_naver_land_real_estate_loc_all"

        self.keyword_list: List[str] = []
        self.site_name: str = "네이버 부동산 공인중개사 번호"
        self.before_pro_value: float = 0.0

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.selenium_driver: Optional[SeleniumUtils] = None
        self.chrome_macro: Optional[ChromeMacro] = None
        self.api_client: Optional[APIClient] = None

        self.complex_result_list: List[Dict[str, Any]] = []
        self.article_result_list: List[Dict[str, Any]] = []
        self.real_state_result_list: List[Dict[str, Any]] = []

        self.seen_numbers: set[str] = set()
        self.seen_article_numbers: set[str] = set()
        self.seen_broker_keys: set[tuple] = set()

        self._is_cleaned_up: bool = False

    # 초기화
    def init(self) -> bool:
        try:
            self._is_cleaned_up = False
            self.current_cnt = 0
            self.total_cnt = 0
            self.before_pro_value = 0.0

            self.complex_result_list = []
            self.article_result_list = []
            self.real_state_result_list = []

            self.seen_numbers.clear()
            self.seen_article_numbers.clear()
            self.seen_broker_keys.clear()

            if self.columns is None:
                self.columns = []

            keyword_str = self.get_setting_value(self.setting, "keyword")
            self.keyword_list = split_comma_keywords(keyword_str)
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            self.driver_set(False)

            self.log_signal_func(f"선택 항목 : {self.columns}")
            self.log_signal_func(f"[DEBUG] folder_path = {self.folder_path}")
            self.log_signal_func(f"[DEBUG] out_dir = {self.out_dir}")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func("시작합니다.")

            if not self.file_driver or not self.excel_driver:
                self.log_signal_func("⚠️ 드라이버가 초기화되지 않았습니다. (file_driver/excel_driver)")
                return False

            if not self.columns:
                self.log_signal_func("⚠️ columns가 비어있습니다.")
                return False

            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            self.excel_driver.init_csv(
                filename=self.csv_filename,
                columns=self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.loc_all_keyword_list()

            for index, cmplx in enumerate(self.complex_result_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                self.log_signal_func(f"데이터 {index}: {cmplx}")
                self.fetch_article_by_complex(cmplx)

            try:
                if getattr(self, "driver", None):
                    self.driver.quit()
            except Exception as e:
                self.log_signal_func(f"[경고] 드라이버 종료 중 예외: {e}")

            self.driver = None

            total_len = len(self.article_result_list)
            self.log_signal_func(f"article_result_list len : {total_len}")

            if self.chrome_macro:
                self.chrome_macro.start_focus_watcher(interval=1.5)

            for ix, article in enumerate(self.article_result_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                self.fetch_article_detail_by_article(article)
                self.log_signal_func(f"진행 ({ix} / {total_len}) ==============================")

                if len(self.real_state_result_list) >= 20 and self.csv_filename:
                    self.excel_driver.append_to_csv(
                        filename=self.csv_filename,
                        data_list=self.real_state_result_list,
                        columns=self.columns,
                        folder_path=self.folder_path,
                        sub_dir=self.out_dir
                    )
                    self.real_state_result_list = []

                if total_len > 0:
                    pro_value = (ix / total_len) * 1000000
                    self.progress_signal.emit(self.before_pro_value, pro_value)
                    self.before_pro_value = pro_value

            if self.real_state_result_list and self.csv_filename:
                self.excel_driver.append_to_csv(
                    filename=self.csv_filename,
                    data_list=self.real_state_result_list,
                    columns=self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.real_state_result_list = []

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"🚨 예외 발생: {e}")
            return False

        finally:
            self.cleanup()

    # 전국 키워드 조회
    def loc_all_keyword_list(self) -> None:
        loc_all_len = len(self.region)
        keyword_list_len = len(self.keyword_list)

        if keyword_list_len:
            self.total_cnt = loc_all_len * keyword_list_len
        else:
            self.total_cnt = loc_all_len

        self.log_signal_func(f"전체 수 {self.total_cnt} 개")

        for index, loc in enumerate(self.region, start=1):
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            name = f'{loc["시도"]} {loc["시군구"]} {loc["읍면동"]} '

            if self.keyword_list:
                for idx, query in enumerate(self.keyword_list, start=1):
                    if not self.running:
                        self.log_signal_func("크롤링이 중지되었습니다.")
                        break

                    full_name = name + query
                    self.log_signal_func(
                        f"전국: {index} / {loc_all_len}, 키워드: {idx} / {keyword_list_len}, 검색어: {full_name}"
                    )
                    self.fetch_complex(full_name)
            else:
                self.log_signal_func(f"전국: {index} / {loc_all_len}, 검색어: {name}")
                self.fetch_complex(name)

    def wait_ready(self, timeout_sec: float = 5.0) -> None:
        end = time.time() + timeout_sec
        while time.time() < end:
            try:
                state = self.driver.execute_script("return document.readyState")
                if state == "complete":
                    return
            except Exception:
                pass
            time.sleep(0.05)

    def fetch_complex(self, kw: str) -> None:
        """
        자동완성 단지 API를 키워드별로 순회
        """
        self.driver.get(self.build_search_url(kw))
        self.wait_ready()
        time.sleep(0.15)

        page = 1
        size = 10
        page_count = 0

        while True:
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            api_url = self.build_api_url(kw, size=size, page=page)
            data = self.execute_fetch(api_url)

            if not isinstance(data, dict) or not data.get("isSuccess"):
                break

            result = data.get("result") or {}
            items: List[Dict[str, Any]] = result.get("list") or []

            if not items:
                break

            new_count = 0

            for it in items:
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                # ===== 중복 주석1 시작 =====
                # raw_num = it.get("complexNumber")
                # num = str(raw_num) if raw_num is not None else None
                #
                # if num is not None:
                #     if num in self.seen_numbers:
                #         continue
                #     self.seen_numbers.add(num)
                # ===== 중복 주석1 끝 =====

                it.setdefault("_meta", {})
                it["_meta"].update({"keyword": kw, "page": page})

                self.complex_result_list.append(it)
                new_count += 1
                page_count += 1

            # ===== 중복 주석1 시작 =====
            # tc = result.get("totalCount")
            # self.log_signal_func(f"    · 수집: {page_count}건 / totalCount={tc}, 누적={len(self.complex_result_list)}")
            # ===== 중복 주석1 끝 =====

            if new_count <= 0:
                break

            page += 1
            time.sleep(0.35)

    def build_search_url(self, keyword: str) -> str:
        return "https://fin.land.naver.com/search?q=" + keyword

    def build_api_url(self, keyword: str, size: int, page: int) -> str:
        return (
            "https://fin.land.naver.com/front-api/v1/search/autocomplete/complexes"
            f"?keyword={keyword}&size={size}&page={page}"
        )

    def _restart_driver(self) -> None:
        try:
            if getattr(self, "driver", None):
                try:
                    self.driver.quit()
                except Exception:
                    pass
        finally:
            state = GlobalState()
            user = state.get("user")
            self.driver = self.selenium_driver.start_driver(1200, user)

    def _with_driver_retry(self, fn, max_retry: int = 1):
        try:
            return fn()
        except (InvalidSessionIdException, WebDriverException):
            if max_retry <= 0:
                raise

            self.log_signal_func("[세션복구] 드라이버 재시작")
            self._restart_driver()
            return self._with_driver_retry(fn, max_retry - 1)

    def execute_fetch(self, api_url: str, timeout_ms: int = 15000) -> Dict[str, Any]:
        js = r"""
            const url = arguments[0];
            const timeoutMs = arguments[1];
            const done = arguments[2];

            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);

            fetch(url, {
                method: "GET",
                credentials: "include",
                headers: {
                    "Accept": "application/json, text/plain, */*"
                },
                signal: controller.signal
            })
            .then(r => r.json())
            .then(data => done({ ok: true, data }))
            .catch(err => done({ ok: false, error: String(err) }))
            .finally(() => clearTimeout(timer));
        """

        result = self._with_driver_retry(
            lambda: self.driver.execute_async_script(js, api_url, timeout_ms)
        )

        if not isinstance(result, dict) or not result.get("ok"):
            return {}

        data = result.get("data") or {}
        return data if isinstance(data, dict) else {}

    def fetch_article_by_complex(self, row: Dict[str, Any]) -> None:
        cn = row.get("complexNumber")
        if cn is None:
            return

        complex_number = str(cn)
        complex_name = row.get("complexName") or row.get("name")
        legal_division_name = row.get("legalDivisionName", "")
        keyword = row.get("_meta", {}).get("keyword", "")

        html_url_tpl = "https://fin.land.naver.com/complexes/{complexNumber}?tab=article"
        api_url = "https://fin.land.naver.com/front-api/v1/complex/article/list"

        default_payload_base = {
            "tradeTypes": [],
            "pyeongTypes": [],
            "dongNumbers": [],
            "userChannelType": "PC",
            "articleSortType": "RANKING_DESC",
            "seed": "",
            "lastInfo": [],
            "size": 100,
        }

        html_url = html_url_tpl.format(complexNumber=complex_number)
        self.driver.get(html_url)
        self.wait_ready()
        time.sleep(0.15)

        payload = dict(default_payload_base)
        payload["complexNumber"] = complex_number
        payload["size"] = 100
        payload["lastInfo"] = []

        page = 1

        while True:
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            data = self.execute_post_json(api_url, payload)
            if data.get("isSuccess") is not True:
                break

            result = data.get("result") or {}
            items: List[Dict[str, Any]] = (
                    result.get("list") or result.get("articles") or result.get("contents") or []
            )

            if not items:
                break

            for it in items:
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                rep = it.get("representativeArticleInfo") or {}
                addr = rep.get("address") or {}
                broker = rep.get("brokerInfo") or {}

                # ===== 중복 주석2 시작 =====
                # city = (addr.get("city") or "").strip().casefold()
                # division = (addr.get("division") or "").strip().casefold()
                # sector = (addr.get("sector") or "").strip().casefold()
                # bname = (broker.get("brokerageName") or "").strip().casefold()
                #
                # broker_key = (city, division, sector, bname)
                #
                # art_no = rep.get("articleNumber") or rep.get("id")
                # if isinstance(art_no, (int, float)):
                #     art_no = str(int(art_no))
                # elif art_no is not None:
                #     art_no = str(art_no).strip()
                #
                # if broker_key in self.seen_broker_keys:
                #     continue
                # self.seen_broker_keys.add(broker_key)
                #
                # if art_no:
                #     if art_no in self.seen_article_numbers:
                #         continue
                #     self.seen_article_numbers.add(art_no)
                # ===== 중복 주석2 끝 =====

                new_item = {
                    "_meta": {
                        "complexNumber": str(complex_number),
                        "complexName": complex_name,
                        "page": page,
                        "legal_division_name": legal_division_name,
                        "keyword": keyword,
                    },
                    "representativeArticleInfo": rep,
                }

                self.log_signal_func(
                    f"city={addr.get('city', '')} division={addr.get('division', '')} "
                    f"sector={addr.get('sector', '')} brokerageName={broker.get('brokerageName', '')}"
                )
                self.article_result_list.append(new_item)

            next_cursor = result.get("lastInfo")
            has_more = result.get("hasMore") or result.get("isNext") or result.get("hasNext")

            if next_cursor:
                payload["lastInfo"] = next_cursor

            if has_more or (next_cursor and len(items) > 0):
                page += 1
                time.sleep(0.25)
                continue

            break

        time.sleep(0.25)

    def execute_post_json(self, url: str, body: Dict[str, Any], timeout_ms: int = 15000) -> Dict[str, Any]:
        js = r"""
            const url = arguments[0];
            const body = arguments[1];
            const timeoutMs = arguments[2];
            const done = arguments[3];

            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);

            fetch(url, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body),
                signal: controller.signal
            })
            .then(r => r.json())
            .then(data => done({ ok: true, data }))
            .catch(err => done({ ok: false, error: String(err) }))
            .finally(() => clearTimeout(timer));
        """

        result = self._with_driver_retry(
            lambda: self.driver.execute_async_script(js, url, body, timeout_ms)
        )

        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(f"fetch error: {result.get('error') if isinstance(result, dict) else result}")

        data = result.get("data") or {}
        if not isinstance(data, dict):
            raise RuntimeError("Invalid JSON response")

        return data

    def parse_next_queries_results(self, html: str) -> List[Dict[str, Any]]:
        if not isinstance(html, str) or not html:
            return []

        m = re.search(
            r'<script\s+id=["\']__NEXT_DATA__["\']\s+type=["\']application/json["\'][^>]*>(\{.*?\})</script>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except Exception:
            return []

        dstate = (data.get("props") or {}).get("pageProps", {}).get("dehydratedState", {})
        queries = dstate.get("queries") or []
        results: List[Dict[str, Any]] = []

        for q in queries:
            if not self.running:
                self.log_signal_func("크롤링이 중지되었습니다.")
                break

            try:
                st = (q or {}).get("state", {})
                dt = (st or {}).get("data", {})
                if dt.get("isSuccess") is True and isinstance(dt.get("result"), dict):
                    results.append(dt["result"])
            except Exception:
                continue

        return results

    def is_target_broker_result(self, obj: Dict[str, Any]) -> bool:
        if not isinstance(obj, dict):
            return False

        required_result_keys = {
            "brokerageName",
            "brokerName",
            "address",
            "businessRegistrationNumber",
            "profileImageUrl",
            "brokerId",
            "ownerConfirmationSaleCount",
            "phone",
        }

        required_phone_keys = {"brokerage", "mobile"}

        if not required_result_keys.issubset(obj.keys()):
            return False

        phone = obj.get("phone")
        if not isinstance(phone, dict):
            return False

        if not required_phone_keys.issubset(phone.keys()):
            return False

        return True

    def parse_target_broker_results(self, html: str) -> List[Dict[str, Any]]:
        all_results = self.parse_next_queries_results(html)
        return [r for r in all_results if self.is_target_broker_result(r)]

    def _to_pyeong(self, sqm: Any, nd: int = 1) -> str:
        try:
            v = float(sqm)
            return f"{round(v / 3.305785, nd)}"
        except Exception:
            return ""

    def _fmt_price_krw(self, n: Any) -> str:
        try:
            n = int(n)
        except Exception:
            return ""

        eok = n // 100_000_000
        man = (n % 100_000_000) // 10_000

        if eok and man:
            return f"{eok}억 {man:,}만원"
        if eok:
            return f"{eok}억"
        return f"{man:,}만원"

    def _fmt_date_yyyymmdd(self, s: Any) -> str:
        s = s or ""
        if isinstance(s, str) and len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s or ""

    def _direction_to_ko(self, code: Any) -> str:
        c = (code or "").upper()
        table = {
            "E": "동", "EE": "동",
            "W": "서", "WW": "서",
            "S": "남", "SS": "남",
            "N": "북", "NN": "북",
            "SE": "남동", "ES": "남동",
            "SW": "남서", "WS": "남서",
            "NE": "북동", "EN": "북동",
            "NW": "북서", "WN": "북서",
        }

        if c in table:
            return table[c]
        if "S" in c and "E" in c and "W" not in c:
            return "남동"
        if "S" in c and "W" in c and "E" not in c:
            return "남서"
        if "N" in c and "E" in c and "W" not in c:
            return "북동"
        if "N" in c and "W" in c and "E" not in c:
            return "북서"
        if "E" in c and "W" not in c:
            return "동"
        if "W" in c and "E" not in c:
            return "서"
        if "S" in c and "N" not in c:
            return "남"
        if "N" in c and "S" not in c:
            return "북"
        return c

    def _extract_article_info_from_flat_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(d, dict):
            return {}

        addr = d.get("address") or {}
        coords = addr.get("coordinates") or {}
        detail = d.get("articleDetail") or {}
        fdet = detail.get("floorDetailInfo") or {}
        space = d.get("spaceInfo") or {}
        price = d.get("priceInfo") or {}
        binfo = d.get("buildingInfo") or {}
        verif = d.get("verificationInfo") or {}
        binfo2 = d.get("brokerInfo") or {}

        ex = space.get("exclusiveSpace")
        sp = space.get("supplySpace")
        ct = space.get("contractSpace")
        deal = price.get("dealPrice")
        mfee = price.get("managementFeeAmount")

        floor_info = detail.get("floorInfo") or (
            f"{fdet.get('targetFloor', '')}/{fdet.get('totalFloor', '')}"
            if (fdet.get("targetFloor") and fdet.get("totalFloor")) else ""
        )

        out: Dict[str, Any] = {
            "번호": d.get("articleNumber") or "",
            "단지명": d.get("complexName") or d.get("articleName") or "",
            "매물명": d.get("articleName") or "",
            "동(단지)": d.get("dongName") or "",

            "시도": addr.get("city") or "",
            "시군구": addr.get("division") or "",
            "읍면동": addr.get("sector") or "",

            "경도": coords.get("xCoordinate"),
            "위도": coords.get("yCoordinate"),

            "층": floor_info,
            "층(목표)": fdet.get("targetFloor") or "",
            "층(전체)": fdet.get("totalFloor") or "",

            "방향": self._direction_to_ko(detail.get("direction")),
            "방향(원문)": detail.get("direction") or "",
            "방향기준": detail.get("directionStandard") or "",

            "전용(㎡/평)": f"{ex} / {self._to_pyeong(ex)}" if ex is not None else "",
            "공급(㎡/평)": f"{sp} / {self._to_pyeong(sp)}" if sp is not None else "",
            "계약(㎡/평)": f"{ct} / {self._to_pyeong(ct)}" if ct is not None else "",

            "매매가": self._fmt_price_krw(deal) if deal else "",
            "매매가(원)": deal,
            "관리비": mfee,

            "부동산종류": d.get("realEstateType") or "",
            "거래유형": d.get("tradeType") or "",

            "노출일": verif.get("exposureStartDate") or "",
            "확인일": verif.get("articleConfirmDate") or "",
            "준공연차": binfo.get("approvalElapsedYear"),
            "준공일": self._fmt_date_yyyymmdd(binfo.get("buildingConjunctionDate")),
        }

        if binfo2:
            out.setdefault("중개사무소이름", binfo2.get("brokerageName", ""))
            out.setdefault("중개사이름", binfo2.get("brokerName", ""))

        return out

    def fetch_article_detail_by_article(self, article: Dict[str, Any]) -> None:
        if not self.chrome_macro:
            self.log_signal_func("[경고] chrome_macro 가 없어 상세 조회를 건너뜁니다.")
            return

        article_url = "https://fin.land.naver.com/articles/"

        rep = article.get("representativeArticleInfo") or {}
        article_number = rep.get("articleNumber") or rep.get("id")

        keyword = article.get("_meta", {}).get("keyword", "")
        legal_division_name = article.get("_meta", {}).get("legal_division_name", "")
        complex_name = article.get("_meta", {}).get("complexName", "")

        if not article_number:
            self.log_signal_func("[경고] articleNumber가 없어 상세 조회를 건너뜁니다.")
            return

        out = self._extract_article_info_from_flat_dict(rep)

        url = f"{article_url}{article_number}"
        html = self.chrome_macro.open_and_grab_html(
            url,
            settle=1.1,
            close_tab_after=True,
            view_source_settle=1.2,
            copy_retries=6,
            copy_wait_each=3.0,
        )

        real_states = self.parse_target_broker_results(html)

        for ix, rs in enumerate(real_states, start=1):
            phone = rs.get("phone") or {}

            row_ko = {
                "중개사무소 이름": rs.get("brokerageName", ""),
                "중개사 이름": rs.get("brokerName", ""),
                "중개사무소 주소": rs.get("address", ""),
                "중개사무소 번호": phone.get("brokerage", ""),
                "중개사 헨드폰번호": phone.get("mobile", ""),
                "지역": legal_division_name,
                "키워드": keyword,
                "매물": complex_name,
            }

            row_ko.update(out)

            self.log_signal_func(
                f"rs({ix}): {row_ko['중개사무소 이름']} / {row_ko['중개사 이름']} / "
                f"{row_ko['중개사무소 주소']} / {row_ko['중개사무소 번호']} / "
                f"{row_ko['중개사 헨드폰번호']}"
            )

            self.real_state_result_list.append(row_ko)

    # 드라이버 세팅
    def driver_set(self, headless: bool) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")

        try:
            tmp_macro = ChromeMacro(default_settle=1.0)
            tmp_macro.close_all()
            time.sleep(0.6)
        except Exception as e:
            self.log_signal_func(f"[경고] 시작 전 크롬 종료 실패: {e}")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.selenium_driver = SeleniumUtils(headless)

        state = GlobalState()
        user = state.get("user")
        self.driver = self.selenium_driver.start_driver(1200, user)

        self.chrome_macro = ChromeMacro(default_settle=1.0)
        self.log_signal_func("✅ driver_set 완료")

    # 정리
    def cleanup(self) -> None:
        if self._is_cleaned_up:
            return

        self._is_cleaned_up = True
        self.log_signal_func("✅ cleanup 시작")

        try:
            if self.csv_filename and self.excel_driver:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    csv_filename=self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
                    keep_csv=True
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
                self.csv_filename = None
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if getattr(self, "chrome_macro", None):
                try:
                    self.chrome_macro.stop_focus_watcher()
                except Exception as e:
                    self.log_signal_func(f"[경고] watcher 종료 중 예외: {e}")

                try:
                    self.chrome_macro.close_all()
                except Exception as e:
                    self.log_signal_func(f"[경고] 크롬 종료 중 예외: {e}")
        finally:
            self.chrome_macro = None

        try:
            if getattr(self, "driver", None):
                try:
                    self.driver.quit()
                except Exception as e:
                    self.log_signal_func(f"[경고] 드라이버 종료 중 예외: {e}")
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
        self.log_signal_func("✅ cleanup 완료")

    # 중지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()