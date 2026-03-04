# ./src/workers/api_krx_nextrade_set_load_worker.py
from __future__ import annotations

import time
import datetime
import random
import json
from typing import Optional, Callable, List, Dict, Any, Tuple
from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker
from src.utils.number_utils import to_int, to_float


class ApiKrxNextradeSetLoadWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: APIClient = APIClient(use_cache=False, log_func=self.log_signal_func)

        self.output_xlsx_auto: str = "krx_nextrade.xlsx"
        self.output_xlsx: str = self.output_xlsx_auto

        self.running: bool = True
        self.before_pro_value: float = 0
        self.last_auto_date: Optional[str] = None

        self._last_keepalive: float = 0

        self.krx_url: str = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCEASY016&locale=ko_KR&kosdaqGlobalYn=1"
        self.krx_api_url: str = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

        self.nx_url: str = "https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do"

        self.krx_headers: Dict[str, str] = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://data.krx.co.kr",
            "Referer": self.krx_url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": "__smVisitorID=Q42GehS1puT"
        }

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

        self.sheet_cond1: str = "Sheet1"
        self.sheet_cond2: str = "Sheet2"

    # =========================
    # init / main
    # =========================
    def init(self) -> bool:
        self.log_signal_func("드라이버 세팅 ==========================")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)

        return True


    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("=============== 크롤링 종료중...")
        self.cleanup()
        time.sleep(1)
        self.log_signal_func("=============== 크롤링 종료")
        self.progress_end_signal.emit()


    def stop(self) -> None:
        self.running = False
        self.cleanup()


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

            if auto_yn:
                self.output_xlsx = self.output_xlsx_auto
                self.auto_loop(auto_time, min_rate1, min_sum_won1, min_rate2, min_sum_won2)

            else:
                self.output_xlsx = f"krx_nextrade_{fr_date}_{to_date}.xlsx"

                dates: List[str] = self.make_dates(fr_date, to_date)

                all_rows_c1: List[Dict[str, Any]] = []
                all_rows_c2: List[Dict[str, Any]] = []

                for idx, ymd in enumerate(dates, start=1):
                    if not self.running:
                        break

                    rows_c1, rows_c2 = self.process_one_day(ymd, min_rate1, min_sum_won1, min_rate2, min_sum_won2)

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
                        sheet_name=self.sheet_cond1
                    )

                if all_rows_c2:
                    self.excel_driver.append_rows_text_excel(
                        filename=self.output_xlsx,
                        rows=all_rows_c2,
                        columns=self.columns,
                        sheet_name=self.sheet_cond2
                    )

            return True

        except Exception as e:
            self.log_signal_func(f"❌ 오류: {e}")
            return False

    # =========================
    # auto
    # =========================
    def auto_loop(self, auto_time: str, min_rate1: float, min_sum_won1: int, min_rate2: float, min_sum_won2: int) -> None:
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
                                sheet_name=self.sheet_cond1
                            )

                        if rows_c2:
                            self.excel_driver.append_rows_text_excel(
                                filename=self.output_xlsx,
                                rows=rows_c2,
                                columns=self.columns,
                                sheet_name=self.sheet_cond2
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
        nx: List[Dict[str, Any]] = self.fetch_nextrade(ymd)

        krx_map: Dict[str, Dict[str, Any]] = {self.only_digits(r.get("ISU_SRT_CD")): r for r in krx}
        nx_map: Dict[str, Dict[str, Any]] = {self.only_digits(r.get("isuSrdCd", "").replace("A", "")): r for r in nx}

        # 즉, KRX에만 있는 종목, NXT에만 있는 종목, 둘 다 있는 종목 전부 포함
        all_codes = set(krx_map.keys()) | set(nx_map.keys())

        merged: List[Dict[str, Any]] = []

        # 종목별로 “통합 레코드(merged)” 만들기
        for code in all_codes:
            k = krx_map.get(code)
            n = nx_map.get(code)

            # 거래대금(원) 합산
            trade_sum_won: int = (to_int(k.get("ACC_TRDVAL")) if k else 0) + (to_int(n.get("accTrval")) if n else 0)

            # 등락률 결정 (우선순위: KRX → 없으면 NXT)
            rate: Optional[float] = to_float(k.get("FLUC_RT")) if k else None
            if rate is None and n:
                rate = to_float(n.get("upDownRate"))

            # 종목명 결정 (우선순위: NXT → 없으면 KRX → 없으면 코드)
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

        # 거래대금 큰 순서로 정렬 (순위 산정 기반)
        merged.sort(key=lambda x: x.get("거래대금합계_원", 0), reverse=True)

        rows_c1: List[Dict[str, Any]] = []
        rows_c2: List[Dict[str, Any]] = []

        rank: int = 1
        for m in merged:
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
        payload: Dict[str, Any] = {
            "bld": "dbms/MDC_OUT/EASY/ranking/MDCEASY01601_OUT", # MDCSTAT01501
            # "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "locale": "ko_KR",
            "mktId": "ALL",
            "segTpCd": "1",
            "itmTpCd3": "2",
            "itmTpCd2": "1",
            "strtDd": str(ymd),
            "endDd": str(ymd),
            "stkprcTpCd": "Y",
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        }

        resp = self.api_client.post(self.krx_api_url, headers=self.krx_headers, data=payload)
        time.sleep(random.uniform(1, 2))

        data: Dict[str, Any] = json.loads(resp)
        return data.get("OutBlock_1", [])


    def fetch_nextrade(self, ymd: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        page: int = 1
        total_cnt: int = 0

        while True:
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