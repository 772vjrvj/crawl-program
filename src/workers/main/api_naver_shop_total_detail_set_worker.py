from __future__ import annotations

import json
import os
import random
import re
import sys
import threading
import time
import wave
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pyaudiowpatch as pyaudio
import pyautogui
import pyperclip

from src.core.services.ai_whisper import get_model
from src.repositories.worker_db_repository import WorkerDbRepository
from src.utils.excel_utils import ExcelUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverShopTotalDetailSetWorker(BaseApiWorker):
    """네이버 쇼핑 상품과 스토어 방문자 수를 수집한다."""

    CAPTCHA_FAIL = 0
    CAPTCHA_NONE = 1
    CAPTCHA_SOLVED = 2
    ACCESS_LIMITED = 3

    # 1차 12시간 + 2차 추가 12시간 = 최대 총 24시간 대기한다.
    ACCESS_LIMIT_WAIT_STEPS: Tuple[int, ...] = (
        12 * 60 * 60,
        12 * 60 * 60,
    )

    ACCESS_LIMIT_TEXTS: Tuple[str, ...] = (
        "쇼핑 서비스 접속이 일시적으로 제한되었습니다",
        "해당 네트워크의 접속을 일시적으로 제한",
        "비정상적인 접근이 감지",
    )

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        if setting is not None:
            self.setting = setting

        self.site_name: str = "naver_shop"
        self.worker_name: str = "naver_shop_total_detail"
        self.detail_table_name: str = "naver_shop_total_detail"
        self.detail_log_fields: Tuple[str, ...] = (
            "product_name",
            "store_name",
        )

        self.running: bool = True
        self.init_flag: bool = False
        self._cleaned_up: bool = False
        self._stop_event = threading.Event()
        self._browser_open: bool = False

        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0

        self.folder_path: str = ""
        self.out_dir: str = "output"
        self.auto_save_yn: bool = False

        self.dup_yn: bool = False
        self.seen_store_names: Set[str] = set()

        # 연속 접속 제한 복구 단계.
        # 정상 페이지가 확인되면 0으로 초기화한다.
        self.access_limit_wait_index: int = 0

        self.excel_driver: Optional[ExcelUtils] = None
        self.db_repository: Optional[WorkerDbRepository] = None
        self.columns: List[str] = []
        self.model: Any = None

    # =========================================================
    # 초기화
    # =========================================================
    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화가 완료되었습니다.")
                return True

            self.running = True
            self._cleaned_up = False
            self._stop_event.clear()
            self._browser_open = False
            self.access_limit_wait_index = 0

            if sys.stdout is None:
                sys.stdout = open(os.devnull, "w")

            self.folder_path = str(
                self.get_setting_value(self.setting, "folder_path") or ""
            ).strip()
            self.auto_save_yn = self._to_bool(
                self.get_setting_value(self.setting, "auto_save_yn")
            )

            self.log_signal_func(f"저장경로 : {self.folder_path}")
            self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")

            self._set_ffmpeg_path()

            pyautogui.PAUSE = 0.4
            pyautogui.FAILSAFE = True

            self.excel_driver = ExcelUtils(self.log_signal_func)

            if self.model is None:
                self.model = get_model()
                self.log_signal_func("✅ Whisper AI (service) 연결 완료")

            if not self.db_set():
                return False

            self.init_flag = True
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 초기화 에러: {e}")
            self.finish_job("FAIL", str(e))
            return False

    def _set_ffmpeg_path(self) -> None:
        resource_root = self.get_resource_root()
        ffmpeg_path = os.path.join(
            resource_root,
            "resources",
            "customers",
            self.worker_name,
            "bin",
        )

        if os.path.exists(ffmpeg_path):
            os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]
            self.log_signal_func("✅ 환경 변수 설정 완료")
        else:
            self.log_signal_func(f"⚠️ FFmpeg 경로 없음: {ffmpeg_path}")

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {
            "true",
            "1",
            "y",
            "yes",
            "on",
        }

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    # =========================================================
    # DB Repository
    # =========================================================
    def db_set(self) -> bool:
        config_data = self.read_runtime_customer_config(
            customer_name=self.worker_name
        )
        column_defs = config_data.get("columns") or []

        if not isinstance(column_defs, list) or not column_defs:
            self.log_signal_func(
                "❌ [config] columns가 없거나 형식이 올바르지 않습니다."
            )
            return False

        try:
            user = getattr(self, "user", None)
            user_id = getattr(user, "user_id", user)

            self.db_repository = WorkerDbRepository(
                db_path=self.get_runtime_db_path(),
                site_name=self.site_name,
                worker_name=self.worker_name,
                detail_table_name=self.detail_table_name,
                column_defs=column_defs,
                user_id=user_id,
                log_func=self.log_signal_func,
                detail_log_fields=self.detail_log_fields,
            )
        except Exception as e:
            self.log_signal_func(f"❌ [DB] Repository 생성 실패: {e}")
            return False

        schema_files = [
            os.path.join(
                "resources",
                "customers",
                "common",
                "db",
                "schema_hist.sql",
            ),
            os.path.join(
                "resources",
                "customers",
                self.worker_name,
                "db",
                "schema_detail.sql",
            ),
        ]

        if not self.db_repository.initialize(schema_files, start_job=True):
            return False

        self.columns = list(self.db_repository.excel_columns)

        self.log_signal_func(
            f"✅ [config] DB 컬럼 수={len(self.db_repository.db_columns)} / "
            f"엑셀 컬럼 수={len(self.db_repository.excel_columns)}"
        )
        return True

    def finish_job(
            self,
            status: str,
            error_message: Optional[str] = None,
    ) -> None:
        if self.db_repository:
            self.db_repository.set_job_result(status, error_message)

    def insert_detail_row(
            self,
            row: Dict[str, Any],
            *,
            row_status: str = "SUCCESS",
            row_error_message: Optional[str] = None,
            row_start_at: Optional[str] = None,
            row_end_at: Optional[str] = None,
    ) -> bool:
        if not self.db_repository:
            self.log_signal_func("❌ [DB] Repository 없음 - detail 저장 실패")
            return False

        return self.db_repository.insert_detail(
            row,
            row_status=row_status,
            row_error_message=row_error_message,
            row_start_at=row_start_at,
            row_end_at=row_end_at,
        )

    def insert_detail_rows(
            self,
            rows: Sequence[Dict[str, Any]],
            *,
            row_status: str = "SUCCESS",
    ) -> bool:
        if not self.db_repository:
            self.log_signal_func("❌ [DB] Repository 없음 - detail 일괄 저장 실패")
            return False

        return self.db_repository.insert_details(rows, row_status=row_status)

    @staticmethod
    def _now_db() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def load_existing_store_names(self) -> Set[str]:
        """
        기존 전체 작업의 store_name을 읽는다.

        공통 DB 생명주기와 저장은 WorkerDbRepository가 담당한다.
        현재 Repository에는 전체 작업 대상 DISTINCT 조회 메서드가 없으므로,
        같은 Repository 연결을 사용해 이 Worker 전용 조회만 수행한다.
        """
        if not self.db_repository:
            return set()

        query = f"""
            SELECT DISTINCT store_name
            FROM {self.detail_table_name}
            WHERE TRIM(COALESCE(store_name, '')) <> ''
        """

        rows = self.db_repository.sqlite.fetchall(query)
        result = {
            str(row.get("store_name") or "").strip()
            for row in rows
            if str(row.get("store_name") or "").strip()
        }

        self.log_signal_func(
            f"✅ [중복] DB 스토어명 {len(result)}건 로드 완료"
        )
        return result

    # =========================================================
    # Excel / 작업 마감
    # =========================================================
    def export_detail_to_excel(self) -> bool:
        if not self.excel_driver:
            self.log_signal_func("❌ [엑셀] excel_driver 없음")
            return False

        if not self.db_repository:
            self.log_signal_func("❌ [엑셀] DB Repository 없음")
            return False

        excel_columns, excel_rows = self.db_repository.get_excel_data()
        if not excel_rows:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        job_id = self.db_repository.job_id or datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        excel_filename = f"{self.site_name}_{job_id}.xlsx"

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=excel_filename,
            row_list=excel_rows,
            columns=excel_columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def finalize_db_and_excel(self) -> None:
        if not self.db_repository:
            return

        try:
            if self.db_repository.status == "RUNNING":
                self.db_repository.set_job_result("FAIL", "비정상 종료")

            if self.db_repository.finish_job():
                self.log_signal_func("✅ [DB] hist 최종 업데이트 완료")
            else:
                self.log_signal_func("❌ [DB] hist 최종 업데이트 실패")

            if self.auto_save_yn:
                if self.export_detail_to_excel():
                    self.log_signal_func("✅ [엑셀] detail 자동 저장 완료")
                else:
                    self.log_signal_func("❌ [엑셀] detail 자동 저장 실패")
            else:
                self.log_signal_func(
                    "ℹ️ [엑셀] 자동 저장 미사용(auto_save_yn=False)"
                )

        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")

    # =========================================================
    # 종료 / 정리
    # =========================================================
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()

        if self.db_repository and self.db_repository.status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        self._close_browser()
        time.sleep(1)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.cleanup()
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        self._close_browser()

        try:
            if os.path.exists("captcha_audio_final.wav"):
                os.remove("captcha_audio_final.wav")
                self.log_signal_func("✅ [캡차 음성파일] 삭제")
        except Exception:
            pass

        # Repository 연결 종료 전에 hist 마감 및 엑셀 저장
        self.finalize_db_and_excel()

        try:
            if self.db_repository:
                self.db_repository.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] db_repository.close 실패: {e}")
        finally:
            self.db_repository = None

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

        self.model = None
        self._cleaned_up = True

    # =========================================================
    # 브라우저 / 접속 제한
    # =========================================================
    def _open_chrome(self) -> bool:
        if not self.running or self._stop_event.is_set():
            return False

        pyautogui.hotkey("win", "r")
        if not self._sleep_or_stop(
                0.5,
                "🛑 중단 또는 sleep 실패 | chrome 실행 전 대기",
        ):
            return False

        pyautogui.write("chrome")
        pyautogui.press("enter")
        if not self._sleep_or_stop(
                3,
                "🛑 중단 또는 sleep 실패 | chrome 실행 후 대기",
        ):
            return False

        self._browser_open = True
        return True

    def _close_browser(self) -> None:
        if not self._browser_open:
            return

        try:
            pyautogui.hotkey("alt", "f4")
        except Exception:
            pass
        finally:
            self._browser_open = False

    def is_access_limited(self, page_content: str) -> bool:
        text = str(page_content or "")
        return any(limit_text in text for limit_text in self.ACCESS_LIMIT_TEXTS)

    def _reset_access_limit_state(self) -> None:
        if self.access_limit_wait_index > 0:
            self.log_signal_func(
                "✅ 네이버 쇼핑 접속 제한 해제 확인 - 대기 단계를 초기화합니다."
            )
        self.access_limit_wait_index = 0

    def _wait_after_access_limit(self, context: str) -> bool:
        """
        접속 제한 감지 시 브라우저를 닫고 12시간씩 최대 두 번 대기한다.

        반환값
        - True: 대기 완료 후 동일 URL을 다시 시도
        - False: 사용자 중단 또는 총 24시간 후에도 제한이 지속됨
        """
        self._close_browser()

        if not self.running or self._stop_event.is_set():
            return False

        if self.access_limit_wait_index >= len(self.ACCESS_LIMIT_WAIT_STEPS):
            error_message = (
                "네이버 쇼핑 접속 제한 지속 | "
                f"{context} | 12시간 + 추가 12시간(총 24시간) 대기 후에도 미해제"
            )
            self.log_signal_func(f"❌ {error_message}")
            self.finish_job("FAIL", error_message)
            return False

        wait_seconds = self.ACCESS_LIMIT_WAIT_STEPS[
            self.access_limit_wait_index
        ]
        self.access_limit_wait_index += 1

        wait_hours = wait_seconds / 3600
        next_check_at = datetime.now() + timedelta(seconds=wait_seconds)

        self.log_signal_func(
            f"🚫 네이버 쇼핑 접속 제한 감지 | {context}"
        )
        self.log_signal_func(
            f"⏸️ 자동 대기 시작 "
            f"| 단계={self.access_limit_wait_index}/{len(self.ACCESS_LIMIT_WAIT_STEPS)} "
            f"| 대기={wait_hours:g}시간 "
            f"| 재확인예정={next_check_at:%Y-%m-%d %H:%M:%S}"
        )
        self.log_signal_func(
            "ℹ️ 대기 중에는 네이버 쇼핑 요청을 보내지 않습니다."
        )

        # Event.wait를 사용하므로 중지 버튼을 누르면 즉시 대기가 해제된다.
        stopped = self._stop_event.wait(wait_seconds)
        if stopped or not self.running:
            self.log_signal_func("🛑 접속 제한 대기 중 사용자 중단")
            return False

        self.log_signal_func(
            f"⏰ 접속 제한 대기 완료 "
            f"| 누적단계={self.access_limit_wait_index}/"
            f"{len(self.ACCESS_LIMIT_WAIT_STEPS)} "
            "| 제한이 발생했던 동일 위치를 1회 재확인합니다."
        )

        if not self._open_chrome():
            return False

        return True

    # =========================================================
    # 중복 제거
    # =========================================================
    def filter_chunk_items(
            self,
            chunk_items_queue: List[Dict[str, Any]],
            kw: str,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        for item_data in chunk_items_queue:
            item = item_data.get("item", {})
            mall_name = str(item.get("mallName") or "").strip()

            if not mall_name:
                self.log_signal_func("⏭️ 스토어명 없음 스킵")
                continue

            if self.dup_yn and mall_name in self.seen_store_names:
                self.log_signal_func(f"⏭️ 스토어명 중복 스킵: {mall_name}")
                continue

            if self.dup_yn:
                # 현재 실행에서 동일 스토어 상세 요청을 반복하지 않는다.
                self.seen_store_names.add(mall_name)

            result.append(item_data)

        if self.dup_yn:
            self.log_signal_func(
                f"🧮 상세 대상 정리 완료 "
                f"| 원본={len(chunk_items_queue)} "
                f"| 중복제거후={len(result)} "
                f"| 키워드={kw}"
            )
        else:
            self.log_signal_func(
                f"🧮 상세 대상 정리 완료 "
                f"| 원본={len(chunk_items_queue)} "
                f"| 대상={len(result)} "
                f"| 키워드={kw}"
            )

        return result

    # =========================================================
    # 공통 보조 함수
    # =========================================================
    def _log_and_return_true(self, message: str) -> bool:
        self.log_signal_func(message)

        if self.db_repository and self.db_repository.status == "RUNNING":
            if self.running:
                self.finish_job("FAIL", message)
            else:
                self.finish_job("STOP", "사용자 중단")

        return True

    def _sleep_or_stop(self, sec: float, message: str) -> bool:
        if not self.sleep_s(sec):
            self.log_signal_func(message)
            return False
        return True

    # =========================================================
    # main
    # =========================================================
    def main(self) -> bool:
        try:
            return self._main_impl()
        except Exception as e:
            error_message = str(e)
            self.log_signal_func(f"❌ 전체 실행 중 예외 발생: {error_message}")
            self.finish_job("FAIL", error_message)
            self._close_browser()
            return False

    def _main_impl(self) -> bool:
        keywords_str = str(
            self.get_setting_value(self.setting, "keyword") or ""
        )

        # 고객이 동일 키워드를 여러 바퀴 실행하려는 현재 운영 방식은 유지한다.
        # 따라서 콤마 분리만 하고 키워드 중복은 제거하지 않는다.
        keywords = [
            keyword.strip()
            for keyword in keywords_str.split(",")
            if keyword.strip()
        ]

        start_p = self._to_int(
            self.get_setting_value(self.setting, "start_page"),
            1,
        )
        end_p = self._to_int(
            self.get_setting_value(self.setting, "end_page"),
            start_p,
        )
        site_total_cnt = self._to_int(
            self.get_setting_value(self.setting, "site_total_cnt"),
            0,
        )

        self.folder_path = str(
            self.get_setting_value(self.setting, "folder_path") or ""
        ).strip()

        self.dup_yn = self._to_bool(
            self.get_setting_value(self.setting, "dup_yn")
        )
        self.seen_store_names = (
            self.load_existing_store_names()
            if self.dup_yn
            else set()
        )

        if self.dup_yn:
            self.log_signal_func(
                f"✅ [중복] 스토어명 중복제거 사용 "
                f"| 초기 DB 건수={len(self.seen_store_names)}"
            )
        else:
            self.log_signal_func("ℹ️ [중복] 스토어명 중복제거 미사용")

        if not keywords:
            self.log_signal_func("❌ 키워드가 없습니다.")
            self.finish_job("FAIL", "키워드가 없습니다.")
            return False

        if start_p < 1:
            start_p = 1

        if end_p < start_p:
            error_message = "종료페이지가 시작페이지보다 작습니다."
            self.log_signal_func(f"❌ {error_message}")
            self.finish_job("FAIL", error_message)
            return False

        total_pages = end_p - start_p + 1
        self.total_cnt = len(keywords) * total_pages
        self.current_cnt = 0
        self.before_pro_value = 0.0

        self.log_signal_func(
            f"🚀 작업 시작 "
            f"| 키워드수={len(keywords)} "
            f"| 페이지={start_p}~{end_p} "
            f"| 총 작업단위={self.total_cnt}"
        )

        completed_keywords = 0

        for kw_idx, kw in enumerate(keywords, start=1):
            if not self.running:
                return self._log_and_return_true(
                    f"🛑 사용자 중단 감지(main-키워드 시작 전) "
                    f"| 마지막완료키워드수={completed_keywords} "
                    f"| 다음키워드={kw}"
                )

            keyword_start_cnt = self.current_cnt
            self.log_signal_func(
                f"🔎 [키워드 시작 {kw_idx}/{len(keywords)}] "
                f"{kw} | page={start_p}~{end_p}"
            )

            all_pages = list(range(start_p, end_p + 1))
            chunk_size = 10

            for i in range(0, len(all_pages), chunk_size):
                if not self.running:
                    return self._log_and_return_true(
                        f"🛑 사용자 중단 감지(chunk 시작 전) "
                        f"| 키워드={kw} | chunk_index={i}"
                    )

                current_chunk = all_pages[i: i + chunk_size]
                chunk_items_queue: List[Dict[str, Any]] = []

                self.log_signal_func(
                    f"🌐 [브라우저 시작] 키워드={kw} "
                    f"| chunk={current_chunk[0]}p~{current_chunk[-1]}p"
                )

                if not self._open_chrome():
                    return self._log_and_return_true(
                        f"🛑 Chrome 실행 실패 또는 사용자 중단 | 키워드={kw}"
                    )

                self.log_signal_func(
                    f"📂 [{kw}] {current_chunk[0]}p ~ "
                    f"{current_chunk[-1]}p 리스트 확보 중..."
                )

                for page in current_chunk:
                    if not self.running:
                        return self._log_and_return_true(
                            f"🛑 사용자 중단 감지(페이지 시작 전) "
                            f"| 키워드={kw} | page={page}"
                        )

                    target_url = (
                        "https://msearch.shopping.naver.com/search/all?"
                        f"adQuery={kw}&npayType=2&origQuery={kw}&"
                        f"pagingIndex={page}&pagingSize=40&productSet=checkout&"
                        f"query={kw}&sort=date&viewType=list"
                    )

                    page_success = False
                    retry = 1

                    # 접속 제한은 일반 추출 재시도 횟수에 포함하지 않는다.
                    while retry <= 3:
                        if not self.running:
                            return self._log_and_return_true(
                                f"🛑 사용자 중단 감지(리스트 재시도 중) "
                                f"| 키워드={kw} | page={page} | retry={retry}"
                            )

                        self.log_signal_func(
                            f"📄 [리스트 페이지 시도] "
                            f"키워드={kw} | page={page} | retry={retry}/3"
                        )

                        pyautogui.hotkey("ctrl", "l")
                        if not self._sleep_or_stop(
                                random.uniform(0.2, 0.5),
                                "🛑 중단 또는 sleep 실패 | 주소창 이동 후 대기 "
                                f"| 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        pyperclip.copy(target_url)
                        pyautogui.hotkey("ctrl", "v")
                        pyautogui.press("enter")
                        if not self._sleep_or_stop(
                                random.uniform(4.0, 5.5),
                                "🛑 중단 또는 sleep 실패 | 페이지 이동 후 대기 "
                                f"| 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        captcha_result = self.handle_captcha_with_retry()

                        if captcha_result == self.ACCESS_LIMITED:
                            if not self._wait_after_access_limit(
                                    f"목록 | 키워드={kw} | page={page}"
                            ):
                                return not self.running
                            # 동일 키워드/동일 페이지를 다시 요청한다.
                            continue

                        if captcha_result == self.CAPTCHA_FAIL:
                            if not self.running:
                                return self._log_and_return_true(
                                    "🛑 사용자 중단 감지(리스트 캡차 처리 중) "
                                    f"| 키워드={kw} | page={page}"
                                )

                            error_message = (
                                "리스트 캡차 실패 "
                                f"| 키워드={kw} | page={page}"
                            )
                            self.log_signal_func(f"❌ {error_message}")
                            self._close_browser()
                            self.finish_job("FAIL", error_message)
                            return False

                        pyautogui.hotkey("ctrl", "u")
                        if not self._sleep_or_stop(
                                random.uniform(3.0, 4.0),
                                "🛑 중단 또는 sleep 실패 | 소스보기 대기 "
                                f"| 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.hotkey("ctrl", "c")
                        if not self._sleep_or_stop(
                                1.5,
                                "🛑 중단 또는 sleep 실패 | HTML 복사 대기 "
                                f"| 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        html_source = pyperclip.paste()
                        pyautogui.hotkey("ctrl", "w")

                        # 화면 복사에서 놓친 경우를 대비해 소스에서도 한 번 더 확인한다.
                        if self.is_access_limited(html_source):
                            if not self._wait_after_access_limit(
                                    f"목록 소스 | 키워드={kw} | page={page}"
                            ):
                                return not self.running
                            continue

                        extracted = self.extract_items_from_html(html_source)
                        if extracted:
                            # 실제 상품 목록까지 확인된 경우에만 제한 복구 단계를 초기화한다.
                            self._reset_access_limit_state()
                            for item in extracted:
                                item["_page_num"] = page

                            chunk_items_queue.extend(extracted)
                            self.log_signal_func(
                                f"📄 {page}페이지 수집 완료: "
                                f"상품 {len(extracted)}개 확보 "
                                f"| 키워드={kw} | retry={retry}"
                            )
                            page_success = True
                            break

                        self.log_signal_func(
                            f"⚠️ 리스트 추출 실패 "
                            f"| 키워드={kw} | page={page} | retry={retry}/3"
                        )

                        retry += 1
                        if retry <= 3:
                            if not self._sleep_or_stop(
                                    random.uniform(2.0, 3.5),
                                    "🛑 중단 또는 sleep 실패 | 리스트 재시도 전 대기 "
                                    f"| 키워드={kw} | page={page} "
                                    f"| retry={retry - 1}",
                            ):
                                return True

                    if not page_success:
                        self.log_signal_func(
                            f"❌ 페이지 최종 실패 "
                            f"| 키워드={kw} | page={page} "
                            "| 3회 재시도 후 추출 실패"
                        )

                    # 접속 제한 대기 중에는 이 위치까지 오지 않으므로 진행률이 증가하지 않는다.
                    self.current_cnt += 1

                if chunk_items_queue:
                    self.log_signal_func(
                        f"🚀 확보된 {len(chunk_items_queue)}개 상품 "
                        "상세 수집 시작..."
                    )

                    chunk_items_queue = self.filter_chunk_items(
                        chunk_items_queue,
                        kw,
                    )

                    for idx, item_data in enumerate(chunk_items_queue):
                        if not self.running:
                            return self._log_and_return_true(
                                f"🛑 사용자 중단 감지(상세 수집 중) "
                                f"| 키워드={kw} "
                                f"| 상세순번={idx + 1}/{len(chunk_items_queue)}"
                            )

                        item = item_data.get("item", {})
                        pc_url = str(item.get("mallPcUrl") or "").strip()
                        p_num = item_data.get("_page_num")

                        if not pc_url:
                            self.log_signal_func(
                                f"⚠️ 상세 URL 없음 스킵 "
                                f"| 키워드={kw} | page={p_num} | idx={idx + 1}"
                            )
                            continue

                        row_start_at = self._now_db()

                        # 접속 제한이 발생하면 동일 상품 URL부터 다시 시작한다.
                        while True:
                            if not self.running:
                                return self._log_and_return_true(
                                    f"🛑 사용자 중단 감지(상세 재시도 중) "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}"
                                )

                            self.log_signal_func(
                                f"🔗 [{kw}] {p_num}p - "
                                f"{idx + 1}/{len(chunk_items_queue)} 상세 이동"
                            )

                            pyautogui.hotkey("ctrl", "l")
                            pyperclip.copy(pc_url)
                            pyautogui.hotkey("ctrl", "v")
                            pyautogui.press("enter")
                            if not self._sleep_or_stop(
                                    random.uniform(3.5, 5.0),
                                    "🛑 중단 또는 sleep 실패 | 상세 이동 후 대기 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.scroll(random.randint(-600, -300))
                            if not self._sleep_or_stop(
                                    random.uniform(0.5, 1.0),
                                    "🛑 중단 또는 sleep 실패 | 상세 스크롤 후 대기 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.scroll(random.randint(300, 600))

                            captcha_result = self.handle_captcha_with_retry()

                            if captcha_result == self.ACCESS_LIMITED:
                                if not self._wait_after_access_limit(
                                        f"상세 | 키워드={kw} | page={p_num} "
                                        f"| idx={idx + 1}"
                                ):
                                    return not self.running
                                continue

                            if captcha_result == self.CAPTCHA_SOLVED:
                                self.log_signal_func(
                                    f"🔄 상세 캡차 해결 후 재진입 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}"
                                )
                                pyautogui.hotkey("ctrl", "l")
                                pyperclip.copy(pc_url)
                                pyautogui.hotkey("ctrl", "v")
                                pyautogui.press("enter")
                                if not self._sleep_or_stop(
                                        random.uniform(3.0, 4.5),
                                        "🛑 중단 또는 sleep 실패 | 상세 재진입 후 대기 "
                                        f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                                ):
                                    return True

                            elif captcha_result == self.CAPTCHA_FAIL:
                                if not self.running:
                                    return self._log_and_return_true(
                                        "🛑 사용자 중단 감지(상세 캡차 처리 중) "
                                        f"| 키워드={kw} | page={p_num} "
                                        f"| idx={idx + 1}"
                                    )

                                error_message = (
                                    "상세 캡차 실패 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}"
                                )
                                self.log_signal_func(f"❌ {error_message}")
                                self._close_browser()
                                self.finish_job("FAIL", error_message)
                                return False

                            pyautogui.hotkey("ctrl", "a")
                            if not self._sleep_or_stop(
                                    random.uniform(0.8, 1.2),
                                    "🛑 중단 또는 sleep 실패 | 상세 전체선택 후 대기 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.hotkey("ctrl", "c")
                            if not self._sleep_or_stop(
                                    0.6,
                                    "🛑 중단 또는 sleep 실패 | 상세 복사 후 대기 "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            detail_text = pyperclip.paste()

                            if self.is_access_limited(detail_text):
                                if not self._wait_after_access_limit(
                                        f"상세 본문 | 키워드={kw} | page={p_num} "
                                        f"| idx={idx + 1}"
                                ):
                                    return not self.running
                                continue

                            self._reset_access_limit_state()
                            break

                        total_visit = "0"
                        visit_match = re.search(
                            r"전체\s*([\d,]+)",
                            detail_text,
                        )
                        if visit_match:
                            total_visit = visit_match.group(1).replace(",", "")

                        if int(total_visit or 0) <= 0:
                            self.log_signal_func(
                                f"⏭️ 전체방문자수 0 스킵 "
                                f"| 키워드={kw} | page={p_num} "
                                f"| 스토어={item.get('mallName')}"
                            )
                            continue

                        categories = [
                            item.get("category1Name"),
                            item.get("category2Name"),
                            item.get("category3Name"),
                            item.get("category4Name"),
                        ]
                        category_str = "/".join(
                            str(category).strip()
                            for category in categories
                            if str(category or "").strip()
                        )

                        # Repository는 config.json columns[].code 기준 dict를 저장한다.
                        row = {
                            "keyword": kw,
                            "crawled_at": datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "product_name": item.get("productName"),
                            "category": category_str,
                            "product_no": item.get("id"),
                            "list_price": item.get("listPrice"),
                            "low_price": item.get("lowPrice"),
                            "sale_price": item.get("price"),
                            "delivery_fee": item.get("dlvryFee"),
                            "discount_ratio": item.get("discountRatio"),
                            "brand": item.get("brand"),
                            "review_count": item.get("reviewCount"),
                            "purchase_count": item.get("purchaseCnt"),
                            "wish_count": item.get("keepCnt"),
                            "store_name": item.get("mallName"),
                            "mall_prod_mbl_url": item.get("mallProdMblUrl"),
                            "mall_product_url": item.get("mallProductUrl"),
                            "pc_url": pc_url,
                            "total_visit_count": total_visit,
                            "page": p_num,
                            "no": idx + 1,
                        }

                        if site_total_cnt >= int(total_visit):
                            if not self.running:
                                return self._log_and_return_true(
                                    f"🛑 사용자 중단 감지(DB 저장 직전) "
                                    f"| 키워드={kw} | page={p_num} | idx={idx + 1}"
                                )

                            if not self.insert_detail_row(
                                    row,
                                    row_status="SUCCESS",
                                    row_start_at=row_start_at,
                                    row_end_at=self._now_db(),
                            ):
                                self.log_signal_func(
                                    f"❌ DB 저장 실패 "
                                    f"| 키워드={kw} | page={p_num} "
                                    f"| 방문자={total_visit} "
                                    f"| 기준={site_total_cnt}"
                                )

                        self.log_signal_func(
                            f"📦 [수집 완료] {kw} - {p_num}p "
                            f"| {item.get('mallName')} "
                            f"| 방문자: {total_visit}"
                        )

                        if not self._sleep_or_stop(
                                random.uniform(1.0, 2.5),
                                "🛑 중단 또는 sleep 실패 | 상세 간 대기 "
                                f"| 키워드={kw} | page={p_num} | idx={idx + 1}",
                        ):
                            return True

                else:
                    self.log_signal_func(
                        f"⚠️ chunk_items_queue 비어있음 "
                        f"| 키워드={kw} "
                        f"| chunk={current_chunk[0]}p~{current_chunk[-1]}p"
                    )

                self.log_signal_func(
                    "🧹 묶음 작업 완료. 브라우저를 정리합니다."
                )
                self._close_browser()
                if not self._sleep_or_stop(
                        2,
                        "🛑 중단 또는 sleep 실패 | 브라우저 종료 후 대기 "
                        f"| 키워드={kw} "
                        f"| chunk={current_chunk[0]}~{current_chunk[-1]}",
                ):
                    return True

                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                self.log_signal_func(
                    f"📊 {current_chunk[-1]}p 묶음 처리 완료 "
                    f"({self.current_cnt}/{self.total_cnt}) "
                    f"| 키워드={kw}"
                )

            completed_keywords += 1
            processed_pages = self.current_cnt - keyword_start_cnt
            self.log_signal_func(
                f"✅ [키워드 종료 {kw_idx}/{len(keywords)}] "
                f"{kw} | 처리페이지수={processed_pages} "
                f"| 누적진행={self.current_cnt}/{self.total_cnt}"
            )

        self.log_signal_func(
            f"🏁 전체 작업 완료 "
            f"| 완료키워드수={completed_keywords}/{len(keywords)} "
            f"| 총진행={self.current_cnt}/{self.total_cnt}"
        )

        if self.db_repository and self.db_repository.status == "RUNNING":
            self.finish_job("SUCCESS")

        return True

    # =========================================================
    # 캡차
    # =========================================================
    def record_audio(self, filename: str, duration: int = 17) -> bool:
        audio = pyaudio.PyAudio()

        try:
            wasapi_info = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = audio.get_device_info_by_index(
                wasapi_info["defaultOutputDevice"]
            )

            if not default_speakers["isLoopbackDevice"]:
                for loopback in audio.get_loopback_device_info_generator():
                    if not self.running:
                        return False
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            wave_format = pyaudio.paInt16
            channels = int(default_speakers.get("maxInputChannels") or 2)
            rate = int(default_speakers["defaultSampleRate"])

            stream = audio.open(
                format=wave_format,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=default_speakers["index"],
            )

            frames: List[bytes] = []
            for _ in range(0, int(rate / 1024 * duration)):
                if not self.running:
                    stream.stop_stream()
                    stream.close()
                    return False
                frames.append(
                    stream.read(1024, exception_on_overflow=False)
                )

            stream.stop_stream()
            stream.close()

            with wave.open(filename, "wb") as wave_file:
                wave_file.setnchannels(channels)
                wave_file.setsampwidth(
                    audio.get_sample_size(wave_format)
                )
                wave_file.setframerate(rate)
                wave_file.writeframes(b"".join(frames))

            return True

        except Exception as e:
            self.log_signal_func(f"❌ 캡차 음성 녹음 예외: {e}")
            return False

        finally:
            audio.terminate()

    def handle_captcha_with_retry(self) -> int:
        captcha_cnt = self._to_int(
            self.get_setting_value(self.setting, "cpcha_cnt"),
            5,
        )
        max_tries = max(1, captcha_cnt)

        for attempt in range(1, max_tries + 1):
            if not self.running:
                self.log_signal_func(
                    "🛑 handle_captcha_with_retry 중단: running=False"
                )
                return self.CAPTCHA_FAIL

            self.log_signal_func(
                f"🔍 [시도 {attempt}/{max_tries}] 화면 상태 체크 중..."
            )

            if attempt > 1:
                pyautogui.press("tab")
                if not self.sleep_s(0.5):
                    self.log_signal_func(
                        "🛑 캡차 처리 중단: tab 이후 sleep 실패"
                    )
                    return self.CAPTCHA_FAIL

            pyperclip.copy("")
            pyautogui.hotkey("ctrl", "a")
            if not self.sleep_s(random.uniform(0.6, 0.9)):
                self.log_signal_func(
                    "🛑 캡차 처리 중단: 전체선택 후 sleep 실패"
                )
                return self.CAPTCHA_FAIL

            pyautogui.hotkey("ctrl", "c")
            if not self.sleep_s(random.uniform(0.5, 0.8)):
                self.log_signal_func(
                    "🛑 캡차 처리 중단: 복사 후 sleep 실패"
                )
                return self.CAPTCHA_FAIL

            page_content = pyperclip.paste()

            if self.is_access_limited(page_content):
                self.log_signal_func(
                    "🚫 네이버 쇼핑 접속 제한 화면을 확인했습니다."
                )
                return self.ACCESS_LIMITED

            target_text = "보안 확인을 완료해 주세요"

            if target_text not in page_content:
                if attempt == 1:
                    self.log_signal_func("✅ 캡차 없음")
                    return self.CAPTCHA_NONE

                self.log_signal_func("✅ 캡차 해결 성공!")
                return self.CAPTCHA_SOLVED

            self.log_signal_func("🚩 캡차 발견! 해결을 시작합니다.")

            if attempt == 1:
                for _ in range(5):
                    pyautogui.press("tab")
                    if not self.sleep_s(random.uniform(0.1, 0.2)):
                        self.log_signal_func(
                            "🛑 캡차 처리 중단: tab 이동 중 sleep 실패"
                        )
                        return self.CAPTCHA_FAIL
                pyautogui.press("enter")
            else:
                pyautogui.press("enter")

            if not self.sleep_s(2):
                self.log_signal_func(
                    "🛑 캡차 처리 중단: 음성재생 대기 sleep 실패"
                )
                return self.CAPTCHA_FAIL

            filename = "captcha_audio_final.wav"
            if self.record_audio(filename, duration=17):
                result = self.model.transcribe(
                    filename,
                    language="ko",
                    fp16=False,
                )
                code = "".join(
                    filter(str.isdigit, result["text"])
                )[:6]

                if not code:
                    code = "123456"
                    self.log_signal_func(
                        "⚠️ AI 인식 실패 (숫자 없음). "
                        "기본값 '123456' 입력"
                    )
                else:
                    self.log_signal_func(f"📝 AI 인식 코드: {code}")

                if attempt == 1:
                    pyautogui.press("tab")
                    if not self.sleep_s(0.5):
                        self.log_signal_func(
                            "🛑 캡차 처리 중단: 입력칸 이동 후 sleep 실패"
                        )
                        return self.CAPTCHA_FAIL
                else:
                    pyautogui.hotkey("shift", "tab")
                    if not self.sleep_s(0.5):
                        self.log_signal_func(
                            "🛑 캡차 처리 중단: shift+tab 후 sleep 실패"
                        )
                        return self.CAPTCHA_FAIL

                pyautogui.write(
                    code,
                    interval=random.uniform(0.1, 0.2),
                )

                for _ in range(3):
                    pyautogui.press("tab")

                pyautogui.press("enter")

                self.log_signal_func("⏳ 결과 검증 대기 중...")
                if not self.sleep_s(random.uniform(5.0, 6.0)):
                    self.log_signal_func(
                        "🛑 캡차 처리 중단: 결과 검증 대기 sleep 실패"
                    )
                    return self.CAPTCHA_FAIL
            else:
                self.log_signal_func("❌ 캡차 음성 녹음 실패")

        self.log_signal_func(
            f"❌ 캡차 최대 재시도 초과: {max_tries}회"
        )
        return self.CAPTCHA_FAIL

    # =========================================================
    # 목록 HTML 파싱
    # =========================================================
    def extract_items_from_html(
            self,
            html_source: str,
    ) -> List[Dict[str, Any]]:
        try:
            pattern = (
                r'<script id="__NEXT_DATA__" '
                r'type="application/json">(.*?)</script>'
            )
            match = re.search(pattern, html_source, re.DOTALL)
            if not match:
                return []

            json_data = json.loads(match.group(1))
            props = json_data.get("props", {}).get("pageProps", {})

            raw_list = (
                    props.get("compositeProducts", {}).get("list", [])
                    or props.get("initialState", {})
                    .get("products", {})
                    .get("list", [])
                    or []
            )

            normalized: List[Dict[str, Any]] = []
            for value in raw_list:
                if (
                        isinstance(value, dict)
                        and "item" in value
                        and isinstance(value.get("item"), dict)
                ):
                    normalized.append(value)
                elif isinstance(value, dict):
                    normalized.append({"item": value})

            return normalized

        except Exception as e:
            self.log_signal_func(f"⚠️ 목록 HTML 파싱 예외: {e}")
            return []
