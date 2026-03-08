# ./src/workers/api_krx_nextrade_set_load_worker.py
from __future__ import annotations

import datetime
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag
from requests import Session

from src.core.global_state import GlobalState
from src.utils.api_utils import APIClient
from src.utils.config import server_url
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.number_utils import to_float, to_int
from src.workers.api_base_worker import BaseApiWorker


class ApiKrxNextradeSetLoadWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.output_xlsx_auto: str = "krx_nextrade.xlsx"
        self.output_xlsx: str = self.output_xlsx_auto

        self.running: bool = True
        self.before_pro_value: float = 0
        self.last_auto_date: Optional[str] = None

        self.krx_server_api_url: str = f"{server_url}/krx/select-by-date"
        self.krx_last_server_api_url: str = f"{server_url}/krx/last/select-all"

        self.nx_url: str = "https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do"

        self.nx_headers: Dict[str, str] = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.nextrade.co.kr",
            "referer": "https://www.nextrade.co.kr/menu/transactionStatusMain/menuList.do",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0.0.0 Safari/537.36"
            ),
            "x-requested-with": "XMLHttpRequest",
        }

        # === 신규 === NAVER 오늘자 전용 설정
        self.naver_max_workers: int = 8
        self.naver_market_headers: Dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "Referer": "https://finance.naver.com/",
            "Accept": "application/json, text/plain, */*",
        }
        self.naver_market_cookies: Dict[str, str] = {
            "field_list": "12|06E10000"
        }
        self.naver_markets: List[Dict[str, str]] = [
            {
                "market_type": "STANDARD",
                "base_url": "https://finance.naver.com/sise/sise_market_sum.naver",
                "sosok": "0",
                "MKT_ID": "STK",
                "MKT_NM": "KOSPI",
            },
            {
                "market_type": "STANDARD",
                "base_url": "https://finance.naver.com/sise/sise_market_sum.naver",
                "sosok": "1",
                "MKT_ID": "KSQ",
                "MKT_NM": "KOSDAQ",
            },
            {
                "market_type": "KONEX",
                "base_url": "https://finance.naver.com/api/sise/konexItemList.nhn",
                "MKT_ID": "KNX",
                "MKT_NM": "KONEX",
            },
        ]
        self.naver_field_ids: List[str] = [
            "quant",
            "amount",
            "open_val",
            "high_val",
            "low_val",
            "listed_stock_cnt",
            "market_sum",
        ]

        self.sheet_cond1: str = "Sheet1"
        self.sheet_cond2: str = "Sheet2"

        # === 신규 === 최근 1일치 캐시
        self.krx_last_rows: List[Dict[str, Any]] = []
        self.krx_last_rows_map: Dict[str, Dict[str, Any]] = {}

        state = GlobalState()
        self.session: Session = state.get("session")

    # =========================
    # init / main
    # =========================
    def init(self) -> bool:
        self.log_signal_func("드라이버 세팅 ==========================")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        # 시작 시 최근 1일치 데이터 캐시
        self.load_last_krx_snapshot()

        return True

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def cleanup(self) -> None:
        try:
            if self.api_client:
                self.api_client.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")


    def main(self) -> bool:
        try:
            fr_date: str = self.get_setting_value(self.setting, "fr_date")
            to_date: str = self.get_setting_value(self.setting, "to_date")

            min_sum_uk1: int = int(self.get_setting_value(self.setting, "price_sum1"))
            min_rate1: float = float(self.get_setting_value(self.setting, "rate1"))
            min_sum_uk2: int = int(self.get_setting_value(self.setting, "price_sum2"))
            min_rate2: float = float(self.get_setting_value(self.setting, "rate2"))

            min_sum_won1: int = min_sum_uk1 * 100000000
            min_sum_won2: int = min_sum_uk2 * 100000000

            auto_yn: bool = str(self.get_setting_value(self.setting, "auto_yn")).lower() in ("1", "true", "y")
            auto_time: str = str(self.get_setting_value(self.setting, "auto_time"))
            folder_path: str = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            if auto_yn:
                self.output_xlsx = self.output_xlsx_auto
                self.auto_loop(auto_time, min_rate1, min_sum_won1, min_rate2, min_sum_won2, folder_path)

            else:
                self.output_xlsx = f"krx_nextrade_{fr_date}_{to_date}.xlsx"

                dates: List[str] = self.make_dates(fr_date, to_date)

                all_rows_c1: List[Dict[str, Any]] = []
                all_rows_c2: List[Dict[str, Any]] = []

                for idx, ymd in enumerate(dates, start=1):
                    if not self.running:
                        return True

                    self.log_signal_func(f"[{idx}/{len(dates)}] 날짜 처리 시작: {ymd}")

                    rows_c1, rows_c2 = self.process_one_day(
                        ymd,
                        min_rate1,
                        min_sum_won1,
                        min_rate2,
                        min_sum_won2
                    )

                    self.log_signal_func(
                        f"[{idx}/{len(dates)}] 날짜 처리 완료: {ymd} / "
                        f"Sheet1={len(rows_c1)}건, Sheet2={len(rows_c2)}건"
                    )

                    all_rows_c1.extend(rows_c1)
                    all_rows_c2.extend(rows_c2)

                    pro: float = (idx / len(dates)) * 1000000
                    self.progress_signal.emit(self.before_pro_value, pro)
                    self.before_pro_value = pro

                    time.sleep(random.uniform(1, 2))

                if all_rows_c1:
                    self.excel_driver.append_rows_text_excel(
                        filename=self.output_xlsx,
                        rows=all_rows_c1,
                        columns=self.columns,
                        sheet_name=self.sheet_cond1,
                        folder_path=folder_path
                    )

                if all_rows_c2:
                    self.excel_driver.append_rows_text_excel(
                        filename=self.output_xlsx,
                        rows=all_rows_c2,
                        columns=self.columns,
                        sheet_name=self.sheet_cond2,
                        folder_path=folder_path
                    )

            return True

        except Exception as e:
            self.log_signal_func(f"❌ 오류: {e}")
            return False

    # =========================
    # auto
    # =========================
    def auto_loop(
            self,
            auto_time: str,
            min_rate1: float,
            min_sum_won1: int,
            min_rate2: float,
            min_sum_won2: int,
            folder_path: str
    ) -> None:
        hour, minute = self.parse_auto_hour(auto_time)

        while self.running:
            try:
                now = datetime.datetime.now()
                today: str = now.strftime("%Y%m%d")

                if self.last_auto_date == today:
                    time.sleep(1)
                    continue

                if now.hour == hour and now.minute == minute:
                    try:
                        rows_c1, rows_c2 = self.process_one_day(today, min_rate1, min_sum_won1, min_rate2, min_sum_won2)

                        if rows_c1:
                            self.excel_driver.append_rows_text_excel(
                                filename=self.output_xlsx,
                                rows=rows_c1,
                                columns=self.columns,
                                sheet_name=self.sheet_cond1,
                                folder_path=folder_path
                            )

                        if rows_c2:
                            self.excel_driver.append_rows_text_excel(
                                filename=self.output_xlsx,
                                rows=rows_c2,
                                columns=self.columns,
                                sheet_name=self.sheet_cond2,
                                folder_path=folder_path
                            )

                        self.last_auto_date = today

                    except Exception as e:
                        self.log_signal_func(f"[AUTO] 실행 오류: {e}")

                    time.sleep(65)
                else:
                    time.sleep(1)

            except Exception as e:
                self.log_signal_func(f"[AUTO LOOP] 예외 발생: {e}")
                time.sleep(5)

    # =========================
    # core
    # =========================
    def process_one_day(
            self,
            ymd: str,
            min_rate1: float,
            min_sum_won1: int,
            min_rate2: float,
            min_sum_won2: int
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:

        krx: List[Dict[str, Any]] = self.fetch_krx(ymd)

        # === 신규 === 오늘 날짜인데 KRX가 비어 있으면 휴장/미개장으로 보고 NX도 스킵
        if str(ymd) == datetime.datetime.now().strftime("%Y%m%d") and not krx:
            self.log_signal_func(f"[PROCESS] 오늘 날짜({ymd}) KRX 데이터 없음 -> NX 수집도 스킵")
            return [], []

        nx: List[Dict[str, Any]] = self.fetch_nextrade(ymd)

        krx_map: Dict[str, Dict[str, Any]] = {self.only_digits(r.get("ISU_SRT_CD")): r for r in krx}
        nx_map: Dict[str, Dict[str, Any]] = {self.only_digits(str(r.get("isuSrdCd", "")).replace("A", "")): r for r in nx}

        all_codes = set(krx_map.keys()) | set(nx_map.keys())
        merged: List[Dict[str, Any]] = []

        for code in all_codes:
            if not self.running:
                return [], []

            k = krx_map.get(code)
            n = nx_map.get(code)

            trade_sum_won: int = (to_int(k.get("ACC_TRDVAL")) if k else 0) + (to_int(n.get("accTrval")) if n else 0)

            rate: Optional[float] = to_float(k.get("FLUC_RT")) if k else None
            if rate is None and n:
                rate = to_float(n.get("upDownRate"))

            name: str = ""
            if n:
                name = n.get("isuAbwdNm", "")
            if not name and k:
                name = k.get("ISU_ABBRV", "")
            if not name:
                name = code

            merged.append({
                "날짜": ymd,
                "종목명": name,
                "거래대금합계_원": trade_sum_won,
                "등락률": rate
            })

        merged.sort(key=lambda x: x.get("거래대금합계_원", 0), reverse=True)

        rows_c1: List[Dict[str, Any]] = []
        rows_c2: List[Dict[str, Any]] = []

        rank: int = 1
        for m in merged:
            if not self.running:
                return [], []

            m["순위"] = rank
            rank += 1

            if m.get("등락률") is None:
                continue

            trade_won: int = m.get("거래대금합계_원", 0)
            rate_val: float = m.get("등락률", 0)

            ok1: bool = trade_won >= min_sum_won1 and rate_val >= min_rate1
            ok2: bool = trade_won >= min_sum_won2 and rate_val >= min_rate2

            if not (ok1 or ok2):
                continue

            m["거래대금합계"] = str(int(trade_won) // 100000000)

            mapped = self.map_columns(m)

            if ok1:
                rows_c1.append(mapped)
            if ok2:
                rows_c2.append(mapped)

        return rows_c1, rows_c2

    # =========================
    # fetch
    # =========================
    def fetch_krx(self, ymd: str) -> List[Dict[str, Any]]:
        today_ymd = datetime.datetime.now().strftime("%Y%m%d")

        # === 신규 === 오늘 날짜면 NAVER 실시간 크롤링 사용
        if str(ymd) == today_ymd:
            self.log_signal_func(f"[KRX] 오늘 날짜({ymd})는 NAVER 실시간 데이터로 수집")
            today_rows = self.fetch_krx_today_from_naver(ymd)

            # === 신규 === 최근 1일치와 비교해 휴장 여부 판단
            if not today_rows:
                self.log_signal_func("[KRX] NAVER 오늘 데이터가 비어 있습니다.")
                return []

            if self.should_process_today_data(today_rows):
                self.log_signal_func("[KRX] 오늘 데이터 처리 진행")
                return today_rows

            self.log_signal_func("[KRX] 오늘은 휴장 또는 미개장 상태로 판단되어 스킵")
            return []

        # === 신규 === 과거 날짜는 서버 API 사용
        payload: Dict[str, Any] = {
            "mktId": "ALL",
            "strtDd": str(ymd),
            "endDd": str(ymd),
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        resp = self.session.get(
            self.krx_server_api_url,
            params=payload,
            headers=headers,
            timeout=15,
        )

        time.sleep(random.uniform(0.3, 0.8))

        data = self._loads_if_needed(resp.text)
        out_block = data.get("OutBlock_1", [])

        if isinstance(out_block, list):
            return out_block

        self.log_signal_func(f"[KRX] 서버 응답 형식 이상: OutBlock_1={type(out_block).__name__}")
        return []

    def fetch_nextrade(self, ymd: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        page: int = 1
        total_cnt: int = 0

        while True:
            if not self.running:
                return result

            payload: Dict[str, Any] = {
                "_search": "false",
                "nd": str(int(time.time() * 1000)),
                "pageUnit": "1000",
                "pageIndex": str(page),
                "sidx": "",
                "sord": "asc",
                "scAggDd": str(ymd),
                "scMktId": "",
                "searchKeyword": "",
            }

            resp = self.api_client.post(self.nx_url, headers=self.nx_headers, data=payload)
            time.sleep(random.uniform(1, 2))

            data: Dict[str, Any] = json.loads(resp)
            items: List[Dict[str, Any]] = data.get("brdinfoTimeList", [])

            if not items:
                break

            if total_cnt == 0:
                try:
                    total_cnt = int(data.get("totalCnt", 0))
                except Exception:
                    total_cnt = 0

            result.extend(items)

            if total_cnt and len(result) >= total_cnt:
                break

            page += 1

        return result

    # =========================
    # === 신규 === KRX 최근 1일치 캐시 로딩
    # =========================
    def load_last_krx_snapshot(self) -> None:
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            resp = self.session.get(
                self.krx_last_server_api_url,
                headers=headers,
                timeout=15,
            )

            data = self._loads_if_needed(resp.text)
            out_block = data.get("OutBlock_1", [])

            if not isinstance(out_block, list):
                self.log_signal_func("[KRX-LAST] OutBlock_1 형식이 올바르지 않습니다.")
                self.krx_last_rows = []
                self.krx_last_rows_map = {}
                return

            self.krx_last_rows = out_block
            self.krx_last_rows_map = {
                self.only_digits(row.get("ISU_SRT_CD")): row
                for row in out_block
                if self.only_digits(row.get("ISU_SRT_CD"))
            }

            self.log_signal_func(f"[KRX-LAST] 최근 1일치 캐시 로딩 완료: {len(self.krx_last_rows)}건")

        except Exception as e:
            self.krx_last_rows = []
            self.krx_last_rows_map = {}
            self.log_signal_func(f"[KRX-LAST] 최근 1일치 로딩 실패: {e}")

    def should_process_today_data(self, today_rows: List[Dict[str, Any]]) -> bool:
        if not self.krx_last_rows:
            self.log_signal_func("[KRX-COMPARE] 최근 1일치 캐시가 없어 오늘 데이터 그대로 진행합니다.")
            return True

        top10_today = sorted(
            today_rows,
            key=lambda x: self.to_int_text(x.get("MKTCAP")),
            reverse=True
        )[:10]

        if not top10_today:
            self.log_signal_func("[KRX-COMPARE] 오늘 상위 10개 데이터가 없어 스킵합니다.")
            return False

        diff_count = 0
        same_count = 0
        compared_count = 0

        for today_row in top10_today:
            code = self.only_digits(today_row.get("ISU_SRT_CD"))
            if not code:
                continue

            last_row = self.krx_last_rows_map.get(code)
            if not last_row:
                self.log_signal_func(f"[KRX-COMPARE] 기준 데이터 없음: code={code}")
                continue

            compared_count += 1

            if self.is_same_ohlc(today_row, last_row):
                same_count += 1
                self.log_signal_func(
                    f"[KRX-COMPARE] 동일 code={code} "
                    f"시가={self.to_int_text(today_row.get('TDD_OPNPRC'))}, "
                    f"고가={self.to_int_text(today_row.get('TDD_HGPRC'))}, "
                    f"저가={self.to_int_text(today_row.get('TDD_LWPRC'))}, "
                    f"종가={self.to_int_text(today_row.get('TDD_CLSPRC'))}"
                )
            else:
                diff_count += 1
                self.log_signal_func(
                    f"[KRX-COMPARE] 변경 code={code} "
                    f"today(시/고/저/종)=("
                    f"{self.to_int_text(today_row.get('TDD_OPNPRC'))}, "
                    f"{self.to_int_text(today_row.get('TDD_HGPRC'))}, "
                    f"{self.to_int_text(today_row.get('TDD_LWPRC'))}, "
                    f"{self.to_int_text(today_row.get('TDD_CLSPRC'))}) "
                    f"last(시/고/저/종)=("
                    f"{self.to_int_text(last_row.get('TDD_OPNPRC'))}, "
                    f"{self.to_int_text(last_row.get('TDD_HGPRC'))}, "
                    f"{self.to_int_text(last_row.get('TDD_LWPRC'))}, "
                    f"{self.to_int_text(last_row.get('TDD_CLSPRC'))})"
                )

        self.log_signal_func(
            f"[KRX-COMPARE] 비교결과 compared={compared_count}, same={same_count}, diff={diff_count}"
        )

        if compared_count == 0:
            self.log_signal_func("[KRX-COMPARE] 비교 가능한 종목이 없어 오늘 데이터 진행합니다.")
            return True

        # 전부 동일 => 휴장일
        if diff_count == 0:
            self.log_signal_func("[KRX-COMPARE] 상위 10개 가격이 모두 동일하여 휴장일로 판단")
            return False

        # 5개 이상 다름 => 장 진행중/개장일
        if diff_count >= 5:
            self.log_signal_func("[KRX-COMPARE] 다른 종목이 5개 이상이라 장이 열린 날로 판단")
            return True

        # 1~4개 다름 => 애매하므로 스킵
        self.log_signal_func("[KRX-COMPARE] 다른 종목 수가 5개 미만이라 오늘 데이터 스킵")
        return False

    def is_same_ohlc(self, row1: Dict[str, Any], row2: Dict[str, Any]) -> bool:
        compare_fields = [
            "TDD_OPNPRC",
            "TDD_HGPRC",
            "TDD_LWPRC",
            "TDD_CLSPRC",
        ]

        for field in compare_fields:
            v1 = self.to_int_text(row1.get(field))
            v2 = self.to_int_text(row2.get(field))
            if v1 != v2:
                return False

        return True

    # =========================
    # === 신규 === NAVER today fetch
    # =========================
    def fetch_krx_today_from_naver(self, ymd: str) -> List[Dict[str, Any]]:
        all_result: List[Dict[str, Any]] = []

        for market_info in self.naver_markets:
            if not self.running:
                return all_result

            self.log_signal_func(f"[NAVER] {market_info['MKT_NM']} 수집 시작")

            try:
                if market_info["market_type"] == "KONEX":
                    market_rows = self.collect_konex(market_info, ymd)
                else:
                    market_rows = self.collect_market_all(market_info, ymd)

                self.log_signal_func(f"[NAVER] {market_info['MKT_NM']} 수집 완료: {len(market_rows)}건")
                all_result.extend(market_rows)

            except Exception as e:
                self.log_signal_func(f"[NAVER] {market_info['MKT_NM']} 수집 실패: {e}")

        return all_result

    def build_naver_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.naver_market_headers)
        session.cookies.update(self.naver_market_cookies)
        return session

    def fetch_standard_page(self, session: requests.Session, market_info: Dict[str, str], page: int) -> str:
        params: List[Tuple[str, str]] = [
            ("sosok", market_info["sosok"]),
            ("page", str(page)),
        ]

        for field_id in self.naver_field_ids:
            params.append(("fieldIds", field_id))

        resp = session.get(market_info["base_url"], params=params, timeout=20)
        resp.raise_for_status()
        resp.encoding = "euc-kr"
        return resp.text

    def fetch_konex_page(self, session: requests.Session, market_info: Dict[str, str]) -> Dict[str, Any]:
        params = {
            "targetColumn": "default",
            "sortOrder": "desc",
        }

        resp = session.get(market_info["base_url"], params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def extract_headers(self, table: Tag) -> List[str]:
        return [
            self.clean_text(th.get_text())
            for th in table.select("thead tr th")
            if self.clean_text(th.get_text())
        ]

    def extract_stock_info(self, tr: Tag) -> Tuple[str, str]:
        a_tag = tr.select_one('a[href*="/item/main.naver?code="]')
        if not a_tag:
            return "", ""

        name = self.clean_text(a_tag.get_text())
        href = a_tag.get("href", "")
        code = href.split("code=")[-1].split("&")[0] if "code=" in href else ""
        return name, code

    def extract_row_values(self, tr: Tag) -> List[str]:
        values: List[str] = []

        for td in tr.find_all("td"):
            a_tag = td.select_one('a[href*="/item/main.naver?code="]')
            if a_tag:
                values.append(self.clean_text(a_tag.get_text()))
            else:
                values.append(self.clean_text(td.get_text()))

        return values

    def map_row(self, headers_ko: List[str], values: List[str]) -> Dict[str, str]:
        row: Dict[str, str] = {}

        for i in range(min(len(headers_ko), len(values))):
            row[headers_ko[i]] = values[i]

        return row

    def convert_standard_to_row(self, row: Dict[str, str], market_info: Dict[str, str], ymd: str) -> Dict[str, Any]:
        current_price = self.to_int_text(row.get("현재가", "0"))
        listed_stock_cnt_thousand = self.to_int_text(row.get("상장주식수", "0"))

        list_shrs = listed_stock_cnt_thousand * 1000
        market_cap = current_price * list_shrs if current_price and list_shrs else 0

        return {
            "TRD_DD": ymd,
            "ISU_SRT_CD": row.get("종목코드", ""),
            "ISU_CD": "",
            "ISU_ABBRV": row.get("종목명", ""),
            "MKT_NM": market_info["MKT_NM"],
            "SECT_TP_NM": "",
            "TDD_CLSPRC": current_price,
            "FLUC_TP_CD": self.parse_fluc_tp_cd(row.get("전일비", "")),
            "CMPPREVDD_PRC": "",
            "FLUC_RT": self.to_float_str_text(row.get("등락률", "")),
            "TDD_OPNPRC": self.to_int_text(row.get("시가", "0")),
            "TDD_HGPRC": self.to_int_text(row.get("고가", "0")),
            "TDD_LWPRC": self.to_int_text(row.get("저가", "0")),
            "ACC_TRDVOL": self.to_int_text(row.get("거래량", "0")),
            "ACC_TRDVAL": self.to_int_text(row.get("거래대금", "0")),
            "MKTCAP": market_cap,
            "LIST_SHRS": list_shrs,
            "MKT_ID": market_info["MKT_ID"],
            "CRAWL_TYPE": "NAVER",
        }

    def parse_standard_page(self, html: str, market_info: Dict[str, str], ymd: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.type_2")
        if not table:
            return []

        headers_ko = self.extract_headers(table)
        results: List[Dict[str, Any]] = []

        for tr in table.select("tbody tr"):
            if not tr.find_all("td"):
                continue

            stock_name, stock_code = self.extract_stock_info(tr)
            if not stock_code:
                continue

            values = self.extract_row_values(tr)
            row = self.map_row(headers_ko, values)
            row["종목명"] = stock_name
            row["종목코드"] = stock_code

            results.append(self.convert_standard_to_row(row, market_info, ymd))

        return results

    def parse_konex_page(self, json_data: Dict[str, Any], market_info: Dict[str, str], ymd: str) -> List[Dict[str, Any]]:
        if json_data.get("resultCode") != "success":
            return []

        result = json_data.get("result") or {}
        item_list = result.get("konexItemList") or []

        results: List[Dict[str, Any]] = []

        for item in item_list:
            current_price = self.to_int_text(item.get("nowVal"))
            change_val = self.to_int_text(item.get("changeVal"))
            open_val = self.to_int_text(item.get("openVal"))
            high_val = self.to_int_text(item.get("highVal"))
            low_val = self.to_int_text(item.get("lowVal"))
            acc_trdvol = self.to_int_text(item.get("accQuant"))
            acc_amount_thousand = self.to_int_text(item.get("accAmount"))
            market_sum_eok = self.to_int_text(item.get("marketSum"))
            list_shrs = self.to_int_text(item.get("listedStockCount"))

            results.append({
                "TRD_DD": ymd,
                "ISU_SRT_CD": self.clean_text(str(item.get("itemcode", ""))),
                "ISU_CD": "",
                "ISU_ABBRV": self.clean_text(str(item.get("itemname", ""))),
                "MKT_NM": market_info["MKT_NM"],
                "SECT_TP_NM": "",
                "TDD_CLSPRC": current_price,
                "FLUC_TP_CD": self.parse_konex_risefall(item.get("risefall")),
                "CMPPREVDD_PRC": abs(change_val),
                "FLUC_RT": self.to_float_str_text(item.get("changeRate")),
                "TDD_OPNPRC": open_val,
                "TDD_HGPRC": high_val,
                "TDD_LWPRC": low_val,
                "ACC_TRDVOL": acc_trdvol,
                "ACC_TRDVAL": acc_amount_thousand * 1000,
                "MKTCAP": market_sum_eok * 100_000_000,
                "LIST_SHRS": list_shrs,
                "MKT_ID": market_info["MKT_ID"],
                "CRAWL_TYPE": "NAVER",
            })

        return results

    def collect_standard_page(self, page: int, market_info: Dict[str, str], ymd: str) -> List[Dict[str, Any]]:
        session = self.build_naver_session()
        html = self.fetch_standard_page(session, market_info, page)
        return self.parse_standard_page(html, market_info, ymd)

    def collect_market_all(self, market_info: Dict[str, str], ymd: str) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        page = 1

        while True:
            if not self.running:
                return all_rows

            pages = list(range(page, page + self.naver_max_workers))
            page_results: Dict[int, List[Dict[str, Any]]] = {}

            with ThreadPoolExecutor(max_workers=self.naver_max_workers) as executor:
                future_map = {
                    executor.submit(self.collect_standard_page, p, market_info, ymd): p
                    for p in pages
                }

                for future in as_completed(future_map):
                    p = future_map[future]
                    try:
                        rows = future.result()
                    except Exception as e:
                        self.log_signal_func(f"[NAVER][{market_info['MKT_NM']}] page={p} 오류: {e}")
                        rows = []

                    page_results[p] = rows
                    self.log_signal_func(f"[NAVER][{market_info['MKT_NM']}] page={p} rows={len(rows)}")

            stop = False

            for p in sorted(page_results.keys()):
                rows = page_results[p]
                if not rows:
                    stop = True
                    break
                all_rows.extend(rows)

            if stop:
                break

            page += self.naver_max_workers

        return all_rows

    def collect_konex(self, market_info: Dict[str, str], ymd: str) -> List[Dict[str, Any]]:
        session = self.build_naver_session()
        json_data = self.fetch_konex_page(session, market_info)
        rows = self.parse_konex_page(json_data, market_info, ymd)
        self.log_signal_func(f"[NAVER][{market_info['MKT_NM']}] rows={len(rows)}")
        return rows

    # =========================
    # utils
    # =========================
    def map_columns(self, m: Dict[str, Any]) -> Dict[str, Any]:
        return {c: m.get(c, "") for c in self.columns}

    def make_dates(self, fr: str, to: str) -> List[str]:
        s = datetime.datetime.strptime(str(fr), "%Y%m%d")
        e = datetime.datetime.strptime(str(to), "%Y%m%d")

        dates: List[str] = []
        while s <= e:
            dates.append(s.strftime("%Y%m%d"))
            s += datetime.timedelta(days=1)

        return dates

    def only_digits(self, s: Any) -> str:
        return "".join(ch for ch in str(s) if ch.isdigit())

    def parse_auto_hour(self, auto_time: str) -> Tuple[int, int]:
        s = str(auto_time).strip()

        if not s.isdigit():
            raise ValueError("auto_time은 숫자여야 합니다")

        n = int(s)

        if n < 0 or n > 2359:
            raise ValueError("auto_time 범위 오류")

        if n < 100:
            hour = 0
            minute = n
        else:
            hour = n // 100
            minute = n % 100

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

        raise ValueError("auto_time은 HHMM 형식")

    # =========================
    # === 신규 === helper
    # =========================
    def _loads_if_needed(self, value: Any) -> Dict[str, Any]:
        text = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value).strip()

        if not text:
            return {}

        try:
            return json.loads(text)
        except Exception:
            self.log_signal_func(f"[JSON 파싱 실패] 앞부분: {text[:200]}")
            return {}

    def clean_text(self, text: Optional[str]) -> str:
        if text is None:
            return ""
        return " ".join(str(text).strip().split())

    def to_int_text(self, value: Any) -> int:
        if value is None:
            return 0

        if isinstance(value, (int, float)):
            return int(value)

        value = self.clean_text(str(value)).replace(",", "").replace("%", "").replace("배", "")
        if value == "":
            return 0

        try:
            return int(float(value))
        except Exception:
            return 0

    def to_float_str_text(self, value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, (int, float)):
            return str(value)

        value = self.clean_text(str(value)).replace(",", "").replace("%", "")
        if value == "":
            return ""

        return value

    def parse_fluc_tp_cd(self, value: str) -> str:
        value = self.clean_text(value)

        if value in ("상승", "상한"):
            return "1"
        if value in ("하락", "하한"):
            return "2"
        if value == "보합":
            return "0"

        if "상승" in value or "상한" in value:
            return "1"
        if "하락" in value or "하한" in value:
            return "2"
        if "보합" in value:
            return "0"

        return ""

    def parse_konex_risefall(self, value: Any) -> str:
        risefall = self.to_int_text(value)

        if risefall in (1, 2):
            return "1"
        if risefall == 3:
            return "0"
        if risefall in (4, 5):
            return "2"

        return ""