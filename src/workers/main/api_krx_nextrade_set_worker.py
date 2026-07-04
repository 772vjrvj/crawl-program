# ./src/workers/api_krx_nextrade_set_worker.py
from __future__ import annotations

import datetime
import os
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
from src.utils.sqlite_utils import SqliteUtils
from src.utils.number_utils import to_float, to_int
from src.workers.api_base_worker import BaseApiWorker
from decimal import Decimal, ROUND_DOWN

class ApiKrxNextradeSetWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
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
            # {
            #     "market_type": "KONEX",
            #     "base_url": "https://finance.naver.com/api/sise/konexItemList.nhn",
            #     "MKT_ID": "KNX",
            #     "MKT_NM": "KONEX",
            # },
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

        self.out_dir: str = "output_krx_nextrade"

        self.no_stock_keywords: List[str] = []

        # =========================
        # DB 저장용 상태
        # =========================
        self.site_name: str = "KRX_NEXTRADE"
        self.worker_name: str = "KRX_NEXTRADE"
        self.detail_table_name: str = "KRX_NEXTRADE"

        self.hist_id: Optional[int] = None
        self.job_id: Optional[str] = None
        self.hist_status: str = "RUNNING"
        self.hist_error_message: Optional[str] = None

        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0

        # schema_detail.sql 컬럼 기준
        self.db_columns: List[str] = [
            "sheet_name",
            "date",
            "rank",
            "name",
            "sum",
            "rate",
            "krx_trade_sum",
            "nxt_trade_sum",
            "source_type",
        ]

        # 설정 columns가 code/date 형태든 value/날짜 형태든 모두 대응
        self.output_key_map: Dict[str, str] = {
            # code -> 한글 원본키
            "date": "날짜",
            "rank": "순위",
            "name": "종목명",
            "sum": "거래대금합계",
            "rate": "등락률",

            # 한글 컬럼명 -> 실제 데이터키
            "시트명": "sheet_name",
            "KRX 거래대금": "krx_trade_sum",
            "NEXTRADE 거래대금": "nxt_trade_sum",
            "데이터구분": "source_type",
        }

        self._cleaned_up: bool = False


    # =========================
    # init / main
    # =========================
    def init(self) -> bool:
        try:
            self.log_signal_func("드라이버 세팅 ==========================")

            self.excel_driver = ExcelUtils(self.log_signal_func)
            self.file_driver = FileUtils(self.log_signal_func)
            self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

            # SQLite 데이터베이스 세팅
            if not self.db_set():
                return False

            # 시작 시 최근 1일치 데이터 캐시
            self.load_last_krx_snapshot()

            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        self.finalize_db_and_excel()

        try:
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] sqlite_driver.close 실패: {e}")
        finally:
            self.sqlite_driver = None

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

        self.file_driver = None
        self.excel_driver = None
        self.api_client = None
        self._cleaned_up = True


    def main(self) -> bool:
        try:
            fr_date: str = str(self.get_setting_value(self.setting, "fr_date"))
            to_date: str = str(self.get_setting_value(self.setting, "to_date"))

            # 조건값은 빈값/null이면 기본값 0으로 대체하지 않고 해당 조건을 스킵합니다.
            # 단, 한 시트의 거래대금/등락률 조건이 모두 비어 있으면 해당 시트 조건 자체를 비활성화합니다.
            min_sum_won1: Optional[int] = self.to_sum_won_condition("price_sum1")
            min_rate1: Optional[float] = self.to_rate_condition("rate1")
            min_sum_won2: Optional[int] = self.to_sum_won_condition("price_sum2")
            min_rate2: Optional[float] = self.to_rate_condition("rate2")

            auto_yn: bool = str(self.get_setting_value(self.setting, "auto_yn")).lower() in ("1", "true", "y")
            auto_time: str = str(self.get_setting_value(self.setting, "auto_time"))
            folder_path: str = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            no_stock_raw: str = str(self.get_setting_value(self.setting, "no_stock") or "").strip()
            self.no_stock_keywords = [
                keyword.strip()
                for keyword in no_stock_raw.split(",")
                if keyword and keyword.strip()
            ]

            self.log_signal_func(
                f"[FILTER] 종목 제거 키워드: {', '.join(self.no_stock_keywords) if self.no_stock_keywords else '(없음)'}"
            )
            self.log_filter_conditions(min_sum_won1, min_rate1, min_sum_won2, min_rate2)

            if auto_yn:
                self.output_xlsx = self.output_xlsx_auto
                self.auto_loop(auto_time, min_rate1, min_sum_won1, min_rate2, min_sum_won2, folder_path)
                return True

            self.output_xlsx = f"krx_nextrade_{fr_date}_{to_date}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
            dates: List[str] = self.make_dates(fr_date, to_date)

            all_rows_c1: List[Dict[str, Any]] = []
            all_rows_c2: List[Dict[str, Any]] = []

            # 수동 날짜 범위 실행 1번 = History 1건
            self.reset_db_job_state()
            if not self.insert_hist_start():
                self.log_signal_func("❌ [DB] 히스토리 생성 실패")

            try:
                for idx, ymd in enumerate(dates, start=1):
                    if not self.running:
                        self.finish_job("STOP", "사용자 중단")
                        break

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

                # DB와 엑셀 저장에 같은 최종 row를 사용합니다.
                # 여기서 sheet_name 및 한글 보조키를 한 번만 주입해서 DB/엑셀 값 차이를 막습니다.
                final_rows_c1 = self.make_db_rows_with_sheet_name(all_rows_c1, self.sheet_cond1)
                final_rows_c2 = self.make_db_rows_with_sheet_name(all_rows_c2, self.sheet_cond2)

                db_rows = []
                db_rows.extend(final_rows_c1)
                db_rows.extend(final_rows_c2)
                self.insert_detail_rows(db_rows)

                if final_rows_c1:
                    self.excel_driver.append_rows_text_excel(
                        filename=self.output_xlsx,
                        rows=self.to_excel_rows(final_rows_c1),
                        columns=self.columns,
                        sheet_name=self.sheet_cond1,
                        folder_path=folder_path,
                        sub_dir=self.out_dir
                    )

                if final_rows_c2:
                    self.excel_driver.append_rows_text_excel(
                        filename=self.output_xlsx,
                        rows=self.to_excel_rows(final_rows_c2),
                        columns=self.columns,
                        sheet_name=self.sheet_cond2,
                        folder_path=folder_path,
                        sub_dir=self.out_dir
                    )

                if self.hist_status == "RUNNING":
                    self.finish_job("SUCCESS")

                return True

            except Exception as e:
                self.finish_job("FAIL", str(e))
                raise

            finally:
                self.update_hist_end()
                self.hist_id = None

        except Exception as e:
            self.log_signal_func(f"❌ 오류: {e}")
            return False

    # =========================
    # auto
    # =========================
    def auto_loop(
            self,
            auto_time: str,
            min_rate1: Optional[float],
            min_sum_won1: Optional[int],
            min_rate2: Optional[float],
            min_sum_won2: Optional[int],
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
                    self.reset_db_job_state()
                    if not self.insert_hist_start():
                        self.log_signal_func("❌ [DB][AUTO] 히스토리 생성 실패")

                    try:
                        rows_c1, rows_c2 = self.process_one_day(today, min_rate1, min_sum_won1, min_rate2, min_sum_won2)

                        # DB와 엑셀 저장에 같은 최종 row를 사용합니다.
                        final_rows_c1 = self.make_db_rows_with_sheet_name(rows_c1, self.sheet_cond1)
                        final_rows_c2 = self.make_db_rows_with_sheet_name(rows_c2, self.sheet_cond2)

                        db_rows = []
                        db_rows.extend(final_rows_c1)
                        db_rows.extend(final_rows_c2)
                        self.insert_detail_rows(db_rows)

                        if final_rows_c1:
                            self.excel_driver.append_rows_text_excel(
                                filename=self.output_xlsx,
                                rows=self.to_excel_rows(final_rows_c1),
                                columns=self.columns,
                                sheet_name=self.sheet_cond1,
                                folder_path=folder_path,
                                sub_dir=self.out_dir
                            )

                        if final_rows_c2:
                            self.excel_driver.append_rows_text_excel(
                                filename=self.output_xlsx,
                                rows=self.to_excel_rows(final_rows_c2),
                                columns=self.columns,
                                sheet_name=self.sheet_cond2,
                                folder_path=folder_path,
                                sub_dir=self.out_dir
                            )

                        if self.hist_status == "RUNNING":
                            self.finish_job("SUCCESS")

                        self.update_hist_end()
                        self.hist_id = None

                        self.last_auto_date = today

                    except Exception as e:
                        self.finish_job("FAIL", str(e))
                        self.update_hist_end()
                        self.hist_id = None
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
            min_rate1: Optional[float],
            min_sum_won1: Optional[int],
            min_rate2: Optional[float],
            min_sum_won2: Optional[int]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:

        krx: List[Dict[str, Any]] = self.fetch_krx(ymd)

        # KONEX 제외: MKT_ID가 KNX인 데이터는 KRX/NXT 병합 대상에서 제거
        krx = [
            row for row in krx
            if str(row.get("MKT_ID", "")).strip().upper() != "KNX"
        ]

        self.log_signal_func(f"[PROCESS] KRX 수집 완료 - 날짜={ymd}, 건수={len(krx)}")

        # === 신규 === 오늘 날짜인데 KRX가 비어 있으면 휴장/미개장으로 보고 NX도 스킵
        if str(ymd) == datetime.datetime.now().strftime("%Y%m%d") and not krx:
            self.log_signal_func(f"[PROCESS] 오늘 날짜({ymd}) KRX 데이터 없음 -> NX 수집도 스킵")
            return [], []

        nx: List[Dict[str, Any]] = self.fetch_nextrade(ymd)
        self.log_signal_func(f"[PROCESS] NXT 수집 완료 - 날짜={ymd}, 건수={len(nx)}")

        krx_map: Dict[str, Dict[str, Any]] = {self.only_digits(r.get("ISU_SRT_CD")): r for r in krx}
        nx_map: Dict[str, Dict[str, Any]] = {self.only_digits(str(r.get("isuSrdCd", "")).replace("A", "")): r for r in nx}

        all_codes = set(krx_map.keys()) | set(nx_map.keys())
        self.log_signal_func(
            f"[PROCESS] 병합 대상 종목 수 - 날짜={ymd}, "
            f"KRX={len(krx_map)}, NXT={len(nx_map)}, MERGED={len(all_codes)}"
        )
        merged: List[Dict[str, Any]] = []

        for code in all_codes:
            if not self.running:
                return [], []

            k = krx_map.get(code)
            n = nx_map.get(code)

            # 거래대금 단위 보정
            # - KRX/NAVER 쪽 ACC_TRDVAL은 백만원 단위로 들어오는 경우가 있습니다.
            # - NXT accTrval은 원 단위로 들어오는 경우가 많습니다.
            # 가격 * 거래량과 비교해서 백만원 단위/원 단위를 자동 판정한 뒤 모두 원 단위로 맞춥니다.
            krx_trade_sum_won: int = self.to_krx_trade_sum_won(k) if k else 0
            nxt_trade_sum_won: int = self.to_nxt_trade_sum_won(n) if n else 0
            trade_sum_won: int = krx_trade_sum_won + nxt_trade_sum_won
            source_type: str = self.get_source_type(k, n)

            # 등락률은 방향코드/문구가 따로 오는 경우가 있어 상승은 +, 하락은 -로 보정합니다.
            # 조건명이 "이상(▲)" 이므로 하락 15%가 상승 15%처럼 통과하면 안 됩니다.
            rate: Optional[float] = self.get_signed_rate_from_krx(k) if k else None
            if rate is None and n:
                rate = self.get_signed_rate_from_nxt(n)

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
                "등락률": rate,
                # DB 저장 전용 필드입니다. 엑셀 저장 시에는 to_excel_rows()에서 제외됩니다.
                "krx_trade_sum": krx_trade_sum_won,
                "nxt_trade_sum": nxt_trade_sum_won,
                "source_type": source_type,
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

            rate_val_opt = self.to_float_value(m.get("등락률"))
            if rate_val_opt is None:
                continue
            m["등락률"] = rate_val_opt

            stock_name: str = str(m.get("종목명", "")).strip()
            if stock_name and self.is_excluded_stock(stock_name):
                continue


            trade_won: int = m.get("거래대금합계_원", 0)
            rate_val: float = rate_val_opt

            ok1: bool = self.is_condition_matched(trade_won, rate_val, min_sum_won1, min_rate1)
            ok2: bool = self.is_condition_matched(trade_won, rate_val, min_sum_won2, min_rate2)

            if not (ok1 or ok2):
                continue

            m["거래대금합계"] = self.won_to_eok_text(trade_won)

            # 조건 통과 row는 DB/엑셀 공통으로 사용할 표준 row로 만듭니다.
            result_row = self.make_result_row(m)

            if ok1:
                rows_c1.append(result_row)
            if ok2:
                rows_c2.append(result_row)

        source_count = {
            "KRX_ONLY": 0,
            "NXT_ONLY": 0,
            "BOTH": 0,
        }

        for row in rows_c1 + rows_c2:
            source_type = str(row.get("source_type", "")).strip()
            if source_type in source_count:
                source_count[source_type] += 1

        self.log_signal_func(
            f"[PROCESS] 조건 통과 결과 - 날짜={ymd}, "
            f"Sheet1={len(rows_c1)}, Sheet2={len(rows_c2)}, "
            f"KRX_ONLY={source_count['KRX_ONLY']}, "
            f"NXT_ONLY={source_count['NXT_ONLY']}, "
            f"BOTH={source_count['BOTH']}"
        )

        return rows_c1, rows_c2


    def get_source_type(self, krx_row: Optional[Dict[str, Any]], nxt_row: Optional[Dict[str, Any]]) -> str:
        has_krx = krx_row is not None
        has_nxt = nxt_row is not None

        if has_krx and has_nxt:
            return "BOTH"
        if has_krx:
            return "KRX_ONLY"
        if has_nxt:
            return "NXT_ONLY"
        return "NONE"

    def is_excluded_stock(self, stock_name: str) -> bool:
        name = str(stock_name or "").strip()
        if not name:
            return False

        for keyword in self.no_stock_keywords:
            if keyword and keyword in name:
                return True

        return False

    def make_result_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        조건을 통과한 데이터를 DB/엑셀 공통 표준 row로 만듭니다.
        여기서 code 키와 한글 키를 모두 채워야 DB 저장값과 엑셀 저장값이 달라지지 않습니다.
        """
        date_value = self.pick_row_value(row, "date", "날짜")
        rank_value = self.pick_row_value(row, "rank", "순위")
        name_value = self.pick_row_value(row, "name", "종목명")
        sum_value = self.pick_row_value(row, "sum", "거래대금합계")
        rate_value = self.pick_row_value(row, "rate", "등락률")
        krx_trade_sum = self.pick_row_value(row, "krx_trade_sum", "KRX 거래대금", "KRX거래대금")
        nxt_trade_sum = self.pick_row_value(row, "nxt_trade_sum", "NEXTRADE 거래대금", "NXT거래대금")
        source_type = self.pick_row_value(row, "source_type", "데이터구분", "구분")
        sheet_name = self.pick_row_value(row, "sheet_name", "시트명")

        result = {
            "date": date_value,
            "날짜": date_value,
            "rank": rank_value,
            "순위": rank_value,
            "name": name_value,
            "종목명": name_value,
            "sum": sum_value,
            "거래대금합계": sum_value,
            "rate": rate_value,
            "등락률": rate_value,
            "krx_trade_sum": krx_trade_sum,
            "KRX 거래대금": krx_trade_sum,
            "nxt_trade_sum": nxt_trade_sum,
            "NEXTRADE 거래대금": nxt_trade_sum,
            "source_type": source_type,
            "데이터구분": source_type,
        }

        if sheet_name:
            result["sheet_name"] = sheet_name
            result["시트명"] = sheet_name

        return result


    # =========================
    # fetch
    # =========================
    def fetch_krx(self, ymd: str) -> List[Dict[str, Any]]:
        today_ymd = datetime.datetime.now().strftime("%Y%m%d")

        self.log_signal_func(f"📌 KRX 조회 시작 - 날짜: {ymd}")

        # === 오늘 날짜면 NAVER 실시간 크롤링 사용
        if str(ymd) == today_ymd:
            self.log_signal_func(f"[KRX] 오늘 날짜({ymd})는 NAVER 실시간 데이터로 수집")

            today_rows = self.fetch_krx_today_from_naver(ymd)

            self.log_signal_func(f"[KRX] NAVER 수집 결과 - 날짜={ymd}, 건수={len(today_rows)}")

            if not today_rows:
                self.log_signal_func("[KRX] NAVER 오늘 데이터가 비어 있습니다.")
                return []

            if self.should_process_today_data(today_rows):
                self.log_signal_func(f"✅ KRX 조회 완료 - 날짜={ymd}, 최종건수={len(today_rows)}, source=NAVER")
                return today_rows

            self.log_signal_func("[KRX] 오늘은 휴장 또는 미개장 상태로 판단되어 스킵")
            return []

        # === 과거 날짜는 서버 API 사용
        payload: Dict[str, Any] = {
            "mktId": "ALL",
            "strtDd": str(ymd),
            "endDd": str(ymd),
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            self.log_signal_func(
                f"📄 KRX 서버 요청 시작 - 날짜={ymd}, "
                f"url={self.krx_server_api_url}, params={payload}"
            )

            resp = self.session.get(
                self.krx_server_api_url,
                params=payload,
                headers=headers,
                timeout=15,
            )

            time.sleep(random.uniform(0.3, 0.8))

            status_code = getattr(resp, "status_code", "")
            resp_text = getattr(resp, "text", "")

            self.log_signal_func(
                f"✅ KRX 서버 응답 수신 - 날짜={ymd}, "
                f"status={status_code}, resp_len={len(resp_text)}"
            )

            data = self._loads_if_needed(resp_text)
            out_block = data.get("OutBlock_1", [])

            if isinstance(out_block, list):
                self.log_signal_func(f"📦 KRX 데이터 확인 - 날짜={ymd}, items={len(out_block)}")

                if not out_block:
                    self.log_signal_func(f"📭 KRX 데이터 없음 - 날짜={ymd}")

                self.log_signal_func(f"🏁 KRX 조회 종료 - 날짜={ymd}, 최종건수={len(out_block)}")
                return out_block

            self.log_signal_func(
                f"[KRX] 서버 응답 형식 이상 - 날짜={ymd}, "
                f"OutBlock_1={type(out_block).__name__}"
            )
            return []

        except Exception as e:
            self.log_signal_func(
                f"❌ KRX 조회 오류 - 날짜={ymd}, "
                f"error={(e and e.args[0]) if (e and e.args) else str(e)}"
            )
            return []

    def fetch_nextrade(self, ymd: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        page: int = 1
        total_cnt: int = 0

        self.log_signal_func(f"📌 NXT 조회 시작 - 날짜: {ymd}")
        while True:
            if not self.running:
                self.log_signal_func("⛔ NXT 조회 중단 - running=False")
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

            try:
                self.log_signal_func(f"📄 NXT 요청 시작 - page={page}")

                resp = self.api_client.post(
                    self.nx_url,
                    headers=self.nx_headers,
                    data=payload
                )

                time.sleep(random.uniform(1, 2))

                if not resp:
                    self.log_signal_func(f"⚠️ NXT 응답 없음 - page={page}")
                    break

                self.log_signal_func(f"✅ NXT 응답 수신 - page={page}, resp_len={len(resp)}")

                data: Dict[str, Any] = json.loads(resp)
                items: List[Dict[str, Any]] = data.get("brdinfoTimeList", [])

                if total_cnt == 0:
                    try:
                        total_cnt = int(data.get("totalCnt", 0))
                    except Exception:
                        total_cnt = 0

                    self.log_signal_func(f"📊 NXT totalCnt={total_cnt}")

                self.log_signal_func(
                    f"📦 NXT 데이터 확인 - page={page}, items={len(items)}, 누적={len(result)}"
                )

                if not items:
                    self.log_signal_func(f"📭 NXT 데이터 없음 - page={page}, 조회 종료")
                    break

                result.extend(items)

                self.log_signal_func(
                    f"📝 NXT 누적 적재 완료 - page={page}, current_items={len(items)}, total_loaded={len(result)}"
                )

                if total_cnt and len(result) >= total_cnt:
                    self.log_signal_func(
                        f"✅ NXT 전체 수집 완료 - totalCnt={total_cnt}, loaded={len(result)}"
                    )
                    break

                page += 1

            except Exception as e:
                self.log_signal_func(
                    f"❌ NXT 조회 오류 - page={page}, error={(e and e.args[0]) if (e and e.args) else str(e)}"
                )
                break

        self.log_signal_func(f"🏁 NXT 조회 종료 - 날짜: {ymd}, 최종건수={len(result)}")
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
    # NAVER today fetch
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
            "ACC_TRDVAL": self.to_int_text(row.get("거래대금", "0")) * 1000000,
            "MKTCAP": market_cap * 100000000,
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

    # =========================================================
    # 설정값 안전 변환
    # =========================================================
    def to_int_setting(self, code: str, default: int = 0) -> int:
        value = self.get_setting_value(self.setting, code)
        parsed = self.to_int_nullable(value)
        if parsed is None:
            self.log_signal_func(f"[SETTING] {code} 값이 비어 있거나 숫자가 아니라서 기본값 {default} 사용")
            return default
        return parsed

    def to_float_setting(self, code: str, default: float = 0.0) -> float:
        value = self.get_setting_value(self.setting, code)
        parsed = self.to_float_value(value)
        if parsed is None:
            self.log_signal_func(f"[SETTING] {code} 값이 비어 있거나 숫자가 아니라서 기본값 {default} 사용")
            return default
        return parsed

    def to_sum_won_condition(self, code: str) -> Optional[int]:
        """
        거래대금 조건값은 설정에서 억 단위로 받습니다.
        예: 2000 입력 => 2000억 => 200,000,000,000원

        빈값/null/숫자 아님이면 None을 반환해서 해당 거래대금 조건을 스킵합니다.
        """
        value = self.get_setting_value(self.setting, code)
        parsed = self.to_decimal_value(value)

        if parsed is None:
            self.log_signal_func(f"[SETTING] {code} 값이 비어 있어 거래대금 조건을 스킵합니다")
            return None

        return int((parsed * Decimal("100000000")).to_integral_value(rounding=ROUND_DOWN))

    def to_rate_condition(self, code: str) -> Optional[float]:
        """
        등락률 조건값은 설정에서 % 숫자로 받습니다.
        예: 15 입력 => 15% 이상

        빈값/null/숫자 아님이면 None을 반환해서 해당 등락률 조건을 스킵합니다.
        """
        value = self.get_setting_value(self.setting, code)
        parsed = self.to_decimal_value(value)

        if parsed is None:
            self.log_signal_func(f"[SETTING] {code} 값이 비어 있어 등락률 조건을 스킵합니다")
            return None

        return float(parsed)

    def log_filter_conditions(
            self,
            min_sum_won1: Optional[int],
            min_rate1: Optional[float],
            min_sum_won2: Optional[int],
            min_rate2: Optional[float]
    ) -> None:
        self.log_signal_func(
            "[FILTER] 조건1 "
            f"거래대금={self.won_to_eok_text(min_sum_won1) + '억 이상' if min_sum_won1 is not None else '스킵'}, "
            f"등락률={str(min_rate1) + '% 이상' if min_rate1 is not None else '스킵'}"
        )
        self.log_signal_func(
            "[FILTER] 조건2 "
            f"거래대금={self.won_to_eok_text(min_sum_won2) + '억 이상' if min_sum_won2 is not None else '스킵'}, "
            f"등락률={str(min_rate2) + '% 이상' if min_rate2 is not None else '스킵'}"
        )

    def is_condition_matched(
            self,
            trade_won: int,
            rate_val: float,
            min_sum_won: Optional[int],
            min_rate: Optional[float]
    ) -> bool:
        """
        조건 그룹 판정.
        - 거래대금 조건이 None이면 거래대금 비교는 스킵
        - 등락률 조건이 None이면 등락률 비교는 스킵
        - 둘 다 None이면 해당 Sheet 조건 자체를 비활성화
        """
        if min_sum_won is None and min_rate is None:
            return False

        if min_sum_won is not None and trade_won < min_sum_won:
            return False

        if min_rate is not None and rate_val < min_rate:
            return False

        return True

    def won_to_eok_text(self, value: Any) -> str:
        """
        원 단위 금액을 억 단위 정수 문자열로 변환합니다.
        예: 500,099,999,999원 -> 5000

        요청사항: 엑셀/DB 표기에서 5000.99처럼 소수점이 나오지 않도록 버림 처리합니다.
        """
        amount = self.to_decimal_value(value)
        if amount is None:
            amount = Decimal("0")

        eok = amount / Decimal("100000000")
        eok_int = eok.to_integral_value(rounding=ROUND_DOWN)
        return str(eok_int)

    def to_decimal_value(self, value: Any) -> Optional[Decimal]:
        if value is None:
            return None

        if isinstance(value, bool):
            return Decimal(int(value))

        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))

        text = self.clean_text(str(value))
        if not text:
            return None

        # 유니코드 마이너스/기호/단위를 정리합니다.
        # 예: "▲ 15.3%", "상승 15.3", "▼ 2.1%", "−2.1"
        negative_hint = any(token in text for token in ("▼", "하락", "하한"))
        positive_hint = any(token in text for token in ("▲", "상승", "상한"))

        text = text.replace("−", "-").replace("＋", "+")
        text = text.replace(",", "").replace("%", "").replace("배", "")
        text = text.replace("원", "").replace("억원", "").replace("억", "")
        text = text.replace("▲", "").replace("▼", "")
        text = text.replace("상승", "").replace("상한", "")
        text = text.replace("하락", "").replace("하한", "")
        text = text.strip()

        if text.startswith("+"):
            text = text[1:].strip()

        if not text or text in ("-", "+"):
            return None

        try:
            parsed = Decimal(text)
        except Exception:
            return None

        if negative_hint and parsed > 0:
            parsed = -parsed
        elif positive_hint and parsed < 0:
            parsed = abs(parsed)

        return parsed

    def to_int_nullable(self, value: Any) -> Optional[int]:
        if value is None:
            return None

        if isinstance(value, bool):
            return int(value)

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        text = self.clean_text(str(value))
        text = text.replace(",", "").replace("%", "").strip()
        if not text:
            return None

        try:
            return int(float(text))
        except Exception:
            return None

    def to_float_value(self, value: Any) -> Optional[float]:
        parsed = self.to_decimal_value(value)
        if parsed is None:
            return None
        return float(parsed)

    def to_money_won(self, value: Any) -> int:
        """
        숫자/문자열 거래대금 값을 int로 변환합니다.
        이 함수는 단위 변환을 하지 않습니다.
        단위 보정은 normalize_trade_value_won()에서 처리합니다.
        """
        parsed = self.to_decimal_value(value)
        if parsed is None:
            return 0
        return int(parsed.to_integral_value(rounding=ROUND_DOWN))

    def to_krx_trade_sum_won(self, row: Optional[Dict[str, Any]]) -> int:
        """
        KRX 거래대금 원 단위 변환.

        주의:
        - NAVER 오늘자 또는 서버 캐시 데이터에서 ACC_TRDVAL이 백만원 단위로 들어오는 경우가 있습니다.
          예) ACC_TRDVAL=1030, 현재가=782, 거래량=1,237,794
              1030은 1,030원이 아니라 1,030백만원(약 10.3억)으로 보는 것이 맞습니다.
        - 이미 원 단위로 들어온 값은 다시 곱하지 않습니다.
        """
        if not row:
            return 0

        raw_value = row.get("ACC_TRDVAL")
        price = self.pick_row_value(row, "TDD_CLSPRC", "curPrc", "현재가")
        volume = self.pick_row_value(row, "ACC_TRDVOL", "accTdQty", "거래량")

        return self.normalize_trade_value_won(raw_value, price, volume)

    def to_nxt_trade_sum_won(self, row: Optional[Dict[str, Any]]) -> int:
        """
        NXT 거래대금 원 단위 변환.

        NXT accTrval은 보통 원 단위입니다.
        그래도 가격 * 거래량과 비교해서 혹시 단위가 다른 경우를 방어합니다.
        """
        if not row:
            return 0

        raw_value = row.get("accTrval")
        price = self.pick_row_value(row, "curPrc", "TDD_CLSPRC", "현재가")
        volume = self.pick_row_value(row, "accTdQty", "ACC_TRDVOL", "거래량")

        return self.normalize_trade_value_won(raw_value, price, volume)

    def normalize_trade_value_won(self, raw_value: Any, price_value: Any = None, volume_value: Any = None) -> int:
        """
        거래대금 값을 원 단위로 정규화합니다.

        원리:
        - 거래대금 후보1: raw 그대로 원 단위라고 가정
        - 거래대금 후보2: raw가 백만원 단위라고 보고 raw * 1,000,000
        - 현재가 * 거래량으로 계산한 추정 거래대금과 더 가까운 후보를 선택

        이렇게 하면 아래 두 경우를 모두 안전하게 처리합니다.
        - KRX/NAVER: ACC_TRDVAL=1030 -> 1,030,000,000원
        - NXT: accTrval=12503331018000 -> 12,503,331,018,000원
        """
        raw_won = self.to_money_won(raw_value)
        if raw_won <= 0:
            return 0

        price = self.to_money_won(price_value)
        volume = self.to_money_won(volume_value)
        estimated_won = price * volume

        if estimated_won <= 0:
            return raw_won

        million_unit_won = raw_won * 1000000

        diff_as_won = abs(estimated_won - raw_won)
        diff_as_million = abs(estimated_won - million_unit_won)

        if diff_as_million < diff_as_won:
            return million_unit_won

        return raw_won

    def get_signed_rate_from_krx(self, row: Optional[Dict[str, Any]]) -> Optional[float]:
        if not row:
            return None

        rate = row.get("FLUC_RT")
        direction = self.pick_row_value(
            row,
            "FLUC_TP_NM",
            "FLUC_TP_CD",
            "CMPPREVDD_PRC",
            "flucTpNm",
            "flucTpCd"
        )

        # NAVER 오늘자 데이터는 이 워커에서 FLUC_TP_CD를 1=상승, 2=하락, 0=보합으로 만들었습니다.
        # KRX 서버 데이터는 보통 1=상한, 2=상승, 3=보합, 4=하한, 5=하락 체계입니다.
        crawl_type = str(row.get("CRAWL_TYPE", "")).strip().upper()
        return self.to_signed_rate_value(rate, direction, naver_style=(crawl_type == "NAVER"))

    def get_signed_rate_from_nxt(self, row: Optional[Dict[str, Any]]) -> Optional[float]:
        if not row:
            return None

        rate = self.pick_row_value(row, "upDownRate", "FLUC_RT", "flucRt", "changeRate")
        direction = self.pick_row_value(
            row,
            "upDownType",
            "upDownTp",
            "upDownTpCd",
            "flucTpCd",
            "flucTpNm",
            "risefall",
            "upDownPrice",
            "cmpprevddPrc"
        )
        return self.to_signed_rate_value(rate, direction, naver_style=False)

    def to_signed_rate_value(
            self,
            rate_value: Any,
            direction_value: Any = None,
            naver_style: bool = False
    ) -> Optional[float]:
        parsed = self.to_decimal_value(rate_value)
        if parsed is None:
            return None

        sign = self.get_direction_sign(direction_value, rate_value, naver_style=naver_style)

        if sign < 0:
            parsed = -abs(parsed)
        elif sign > 0:
            parsed = abs(parsed)

        return float(parsed)

    def get_direction_sign(self, direction_value: Any, rate_value: Any = None, naver_style: bool = False) -> int:
        """
        반환값: 상승=1, 하락=-1, 보합/불명=0
        """
        direction_text = self.clean_text(str(direction_value or ""))
        rate_text = self.clean_text(str(rate_value or ""))
        text = f"{direction_text} {rate_text}".strip()

        if any(token in text for token in ("▼", "하락", "하한", "DOWN", "Down", "down")):
            return -1
        if any(token in text for token in ("▲", "상승", "상한", "UP", "Up", "up")):
            return 1

        # 값 자체 또는 전일대비 필드에 음수 기호가 있으면 하락으로 봅니다.
        if "-" in rate_text or "−" in rate_text or "-" in direction_text or "−" in direction_text:
            return -1

        code = self.only_digits(direction_text)
        if code:
            try:
                n = int(code)
            except Exception:
                n = 0

            if naver_style:
                # 이 워커가 NAVER 데이터 생성 시 만든 코드: 1=상승, 2=하락, 0=보합
                if n == 1:
                    return 1
                if n == 2:
                    return -1
                return 0

            # KRX/NXT 계열 일반 코드: 1=상한, 2=상승, 3=보합, 4=하한, 5=하락
            if n in (1, 2):
                return 1
            if n in (4, 5):
                return -1
            if n == 3:
                return 0

        return 0

    # =========================================================
    # SQLite DB 관리 공용 모듈 파트
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)
        db_path = self.get_runtime_db_path()

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        return True

    def reset_db_job_state(self) -> None:
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None
        self.detail_success_count = 0
        self.detail_fail_count = 0

    def insert_hist_start(self) -> bool:
        if not self.sqlite_driver:
            self.log_signal_func("❌ [DB] sqlite_driver 없음")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id, table_name, site_name, worker_name, user_id,
                    start_at, status, total_count, success_count, fail_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        params = (
            self.job_id, self.detail_table_name, self.site_name, self.worker_name,
            self.get_user_id_value(),
            now, "RUNNING", 0, 0, 0, now, now,
        )

        if not self.sqlite_driver.execute(query, params):
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None
        return self.hist_id is not None

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not sqlite_driver or not self.hist_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        query = """
                UPDATE worker_job_hist
                SET end_at = ?, status = ?, total_count = ?, success_count = ?, fail_count = ?,
                    error_message = ?, updated_at = ?
                WHERE hist_id = ?
                """
        params = (
            now, self.hist_status, self.detail_success_count + self.detail_fail_count,
            self.detail_success_count, self.detail_fail_count, self.hist_error_message, now, self.hist_id,
        )
        return sqlite_driver.execute(query, params)

    def insert_detail_rows(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            self.log_signal_func("[DB] 저장할 상세 데이터 없음")
            return

        for row in rows:
            if not self.running:
                self.finish_job("STOP", "사용자 중단")
                break
            self.insert_detail_row(row)

        self.log_signal_func(
            f"[DB] 상세 저장 완료: success={self.detail_success_count}, fail={self.detail_fail_count}"
        )

    def insert_detail_row(self, rs: Dict[str, Any]) -> bool:
        if not self.sqlite_driver or not self.db_columns or not self.hist_id:
            self.detail_fail_count += 1
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        db_row = self.to_detail_db_row(rs)

        base_columns = ["hist_id", "site_name", "worker_name", "table_name", "job_id", "user_id", "row_status"]
        all_columns = base_columns + self.db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(self.quote_identifier(col) for col in all_columns)

        query = f"INSERT INTO {self.quote_identifier(self.detail_table_name)} ({column_text}) VALUES ({placeholders})"
        params = (
            self.hist_id, self.site_name, self.worker_name, self.detail_table_name, self.job_id,
            self.get_user_id_value(), "SUCCESS",
            *[db_row.get(col, "") for col in self.db_columns], now, now,
        )

        ok = self.sqlite_driver.execute(query, params)
        if ok:
            self.detail_success_count += 1
        else:
            self.detail_fail_count += 1
        return ok

    def to_detail_db_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sheet_name": self.pick_row_value(row, "sheet_name", "시트명"),
            "date": self.pick_row_value(row, "date", "날짜"),
            "rank": self.to_int_text(self.pick_row_value(row, "rank", "순위")),
            "name": self.pick_row_value(row, "name", "종목명"),

            # 거래대금합계는 억 단위 정수로 저장합니다. 예: 5000, 6000
            "sum": self.to_int_text(self.pick_row_value(row, "sum", "거래대금합계")),

            "rate": self.to_float_db_value(self.pick_row_value(row, "rate", "등락률")),
            "krx_trade_sum": self.to_int_text(
                self.pick_row_value(row, "krx_trade_sum", "KRX 거래대금", "KRX거래대금")
            ),
            "nxt_trade_sum": self.to_int_text(
                self.pick_row_value(row, "nxt_trade_sum", "NEXTRADE 거래대금", "NXT거래대금")
            ),
            "source_type": self.pick_row_value(row, "source_type", "데이터구분", "구분"),
        }

    def make_db_rows_with_sheet_name(self, rows: List[Dict[str, Any]], sheet_name: str) -> List[Dict[str, Any]]:
        final_rows: List[Dict[str, Any]] = []

        for row in rows:
            final_row = self.make_result_row(row)
            final_row["sheet_name"] = sheet_name
            final_row["시트명"] = sheet_name

            # 한글 컬럼명으로 체크했을 때도 같은 값이 나오도록 보조키를 확정합니다.
            final_row["KRX 거래대금"] = final_row.get("krx_trade_sum", "")
            final_row["NEXTRADE 거래대금"] = final_row.get("nxt_trade_sum", "")
            final_row["데이터구분"] = final_row.get("source_type", "")

            final_rows.append(final_row)

        return final_rows

    def to_excel_rows(self, rows: List[Dict[str, Any]], sheet_name: str = "") -> List[Dict[str, Any]]:
        excel_rows: List[Dict[str, Any]] = []

        for row in rows:
            excel_row = self.make_result_row(row)

            if sheet_name:
                excel_row["sheet_name"] = sheet_name
                excel_row["시트명"] = sheet_name

            # 한글 컬럼명으로 체크했을 때도 같은 값이 나오도록 보조키를 확정합니다.
            excel_row["KRX 거래대금"] = excel_row.get("krx_trade_sum", "")
            excel_row["NEXTRADE 거래대금"] = excel_row.get("nxt_trade_sum", "")
            excel_row["데이터구분"] = excel_row.get("source_type", "")

            excel_rows.append(self.map_columns(excel_row))

        return excel_rows




    def merge_unique_rows(self, rows_c1: List[Dict[str, Any]], rows_c2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        for row in rows_c1 + rows_c2:
            date_val = str(self.pick_row_value(row, "date", "날짜") or "")
            rank_val = str(self.pick_row_value(row, "rank", "순위") or "")
            name_val = str(self.pick_row_value(row, "name", "종목명") or "")
            sum_val = str(self.pick_row_value(row, "sum", "거래대금합계") or "")
            rate_val = str(self.pick_row_value(row, "rate", "등락률") or "")
            key = (date_val, rank_val, name_val, sum_val, rate_val)

            if key in seen:
                continue

            seen.add(key)
            merged.append(row)

        return merged

    def pick_row_value(self, row: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in row:
                return row.get(key)
        return ""

    def to_float_db_value(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = self.clean_text(str(value)).replace(",", "").replace("%", "")
        if not text:
            return None

        try:
            return float(text)
        except Exception:
            return None

    def quote_identifier(self, name: str) -> str:
        return '"' + str(name).replace('"', '""') + '"'

    def get_user_id_value(self) -> Any:
        if not self.user:
            return None
        return getattr(self.user, "user_id", self.user)

    def finalize_db_and_excel(self) -> None:
        temp_sqlite_driver = None
        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            if temp_sqlite_driver.connect(self.get_runtime_db_path()):
                if self.hist_id:
                    self.update_hist_end(temp_sqlite_driver)
        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")
        finally:
            if temp_sqlite_driver:
                temp_sqlite_driver.close()

    # =========================
    # utils
    # =========================
    def map_columns(self, m: Dict[str, Any]) -> Dict[str, Any]:
        mapped: Dict[str, Any] = {}

        for col in self.columns:
            key = self.get_column_code(col)
            if not key:
                continue

            source_key = self.output_key_map.get(key, key)
            mapped[key] = m.get(key, m.get(source_key, ""))

        return mapped

    def get_column_code(self, col: Any) -> str:
        """
        columns 설정이 문자열 리스트로 오든,
        {code, value, checked} 딕셔너리 리스트로 오든 동일하게 code를 뽑습니다.
        """
        if isinstance(col, dict):
            return str(col.get("code") or col.get("value") or "").strip()
        return str(col or "").strip()

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
        parsed = self.to_decimal_value(value)
        if parsed is None:
            return 0
        return int(parsed.to_integral_value(rounding=ROUND_DOWN))

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