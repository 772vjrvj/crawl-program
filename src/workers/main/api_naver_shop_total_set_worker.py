from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import wave
from typing import Optional

import pyaudiowpatch as pyaudio
import pyautogui
import pyperclip

from src.core.services.ai_whisper import get_model
from src.utils.excel_utils import ExcelUtils
from src.workers.api_base_worker import BaseApiWorker
from src.utils.sqlite_utils import SqliteUtils


class ApiNaverShopTotalSetWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None
        self.site_name: str = "naver_shop"
        self.worker_name: str = "naver_shop_total"
        self.excel_driver: Optional[ExcelUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
        self.model = None

        self.total_cnt = 0
        self.current_cnt = 0
        self.before_pro_value = 0.0

        self.detail_success_count = 0
        self.detail_fail_count = 0
        self.detail_table_name = "naver_shop_total_detail"

        self.folder_path: str = ""
        self.out_dir: str = "output_naver_shop"

        # === 신규 ===
        self.dup_yn = False
        self.seen_store_names = set()

    # =========================================================
    # lifecycle
    # =========================================================
    def init(self) -> bool:
        try:
            if sys.stdout is None:
                sys.stdout = open(os.devnull, "w")

            resource_root = self.get_resource_root()

            ffmpeg_path = os.path.join(
                resource_root,
                "resources",
                "customers",
                "naver_shop_total",
                "bin",
            )

            if os.path.exists(ffmpeg_path):
                os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]
                self.log_signal_func("✅ 환경 변수 설정 완료")
            else:
                self.log_signal_func(f"⚠️ FFmpeg 경로 없음: {ffmpeg_path}")

            pyautogui.PAUSE = 0.4
            pyautogui.FAILSAFE = True

            self.excel_driver = ExcelUtils(self.log_signal_func)
            self.sqlite_driver = SqliteUtils(self.log_signal_func)

            db_path = self.get_runtime_db_path()
            self.log_signal_func(f"[DB] 실제 경로 = {os.path.abspath(db_path)}")

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

            self.log_signal_func("✅ [DB] 스키마 초기화 완료")

            if self.model is None:
                self.model = get_model()
                self.log_signal_func("✅ Whisper AI (service) 연결 완료")

            if not self.insert_hist_start():
                return False

            return True

        except Exception as e:
            self.log_signal_func(f"❌ 초기화 에러: {e}")
            return False

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False

        if self.hist_status == "RUNNING":
            self.hist_status = "STOP"
            self.hist_error_message = "사용자 중단"

        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def cleanup(self) -> None:
        self.model = None

        try:
            if os.path.exists("captcha_audio_final.wav"):
                os.remove("captcha_audio_final.wav")
                self.log_signal_func("✅ [캡차 음성파일] 삭제")
        except Exception:
            pass

        try:
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
                self.log_signal_func("✅ [DB] 기존 연결 해제")
        except Exception as e:
            self.log_signal_func(f"[cleanup] sqlite_driver.close 실패: {e}")
        finally:
            self.sqlite_driver = None

        self.finalize_db_and_excel()

        try:
            if self.excel_driver and hasattr(self.excel_driver, "close"):
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def insert_hist_start(self) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id,
                    table_name,
                    site_name,
                    worker_name,
                    user_id,
                    start_at,
                    status,
                    total_count,
                    success_count,
                    fail_count,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

        params = (
            self.job_id,
            "naver_shop_total_detail",
            self.site_name,
            self.worker_name,
            getattr(self.user, "user_id", None) if self.user else None,
            now,
            "RUNNING",
            0,
            0,
            0,
            now,
            now,
        )

        if not self.sqlite_driver.execute(query, params):
            self.log_signal_func("❌ [DB] hist 시작 row 저장 실패")
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None

        self.log_signal_func(f"✅ [DB] hist 시작 row 저장 완료 | hist_id={self.hist_id}")
        return True

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver

        if not sqlite_driver:
            return False

        if not self.hist_id:
            self.log_signal_func("⚠️ [DB] hist_id 없음 - 종료 update 스킵")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = """
                UPDATE worker_job_hist
                SET
                    end_at = ?,
                    status = ?,
                    total_count = ?,
                    success_count = ?,
                    fail_count = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE hist_id = ?
                """

        params = (
            now,
            self.hist_status,
            self.detail_success_count + self.detail_fail_count,
            self.detail_success_count,
            self.detail_fail_count,
            self.hist_error_message,
            now,
            self.hist_id,
        )

        if not sqlite_driver.execute(query, params):
            self.log_signal_func(f"❌ [DB] hist 종료 row 수정 실패 | hist_id={self.hist_id}")
            return False

        self.log_signal_func(
            f"✅ [DB] hist 종료 row 수정 완료 | hist_id={self.hist_id} | status={self.hist_status}"
        )
        return True

    # === 신규 ===
    def load_existing_store_names(self) -> set:
        if not self.sqlite_driver:
            return set()

        query = f"""
                SELECT DISTINCT store_name
                FROM {self.detail_table_name}
                WHERE TRIM(COALESCE(store_name, '')) <> ''
                """

        rows = self.sqlite_driver.fetchall(query)
        result = set()

        for row in rows:
            store_name = str(row.get("store_name") or "").strip()
            if store_name:
                result.add(store_name)

        self.log_signal_func(f"✅ [중복] DB 스토어명 {len(result)}건 로드 완료")
        return result

    # === 신규 ===
    def filter_chunk_items(self, chunk_items_queue: list, kw: str) -> list:
        result = []

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
                self.seen_store_names.add(mall_name)

            result.append(item_data)

        if self.dup_yn:
            self.log_signal_func(
                f"🧮 상세 대상 정리 완료 | 원본={len(chunk_items_queue)} | 중복제거후={len(result)} | 키워드={kw}"
            )
        else:
            self.log_signal_func(
                f"🧮 상세 대상 정리 완료 | 원본={len(chunk_items_queue)} | 대상={len(result)} | 키워드={kw}"
            )

        return result

    def insert_detail_row(self, rs: dict) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = """
                INSERT INTO naver_shop_total_detail (
                    hist_id,
                    site_name,
                    worker_name,
                    table_name,
                    job_id,
                    user_id,
                    row_status,
                    keyword,
                    crawled_at,
                    product_name,
                    category,
                    product_no,
                    list_price,
                    low_price,
                    sale_price,
                    delivery_fee,
                    discount_ratio,
                    brand,
                    review_count,
                    purchase_count,
                    wish_count,
                    store_name,
                    mall_prod_mbl_url,
                    mall_product_url,
                    pc_url,
                    total_visit_count,
                    page,
                    no,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

        params = (
            self.hist_id,
            self.site_name,
            self.worker_name,
            self.detail_table_name,
            self.job_id,
            getattr(self.user, "user_id", None) if self.user else None,
            "SUCCESS",
            rs.get("키워드"),
            rs.get("수집일시"),
            rs.get("상품명"),
            rs.get("카테고리"),
            rs.get("상품번호"),
            rs.get("원가"),
            rs.get("최소가"),
            rs.get("판매가격"),
            rs.get("배송비"),
            rs.get("할인률"),
            rs.get("브랜드"),
            rs.get("리뷰수"),
            rs.get("구매건수"),
            rs.get("찜하기수"),
            rs.get("스토어명"),
            rs.get("스토어모바일주소"),
            rs.get("스토어PC주소"),
            rs.get("PC주소"),
            rs.get("전체방문자수"),
            rs.get("페이지"),
            rs.get("번호"),
            now,
            now,
        )

        ok = self.sqlite_driver.execute(query, params)

        if ok:
            self.detail_success_count += 1
            self.log_signal_func(
                f"✅ [DB] detail 저장 완료 | hist_id={self.hist_id} | 상품={rs.get('상품명')}"
            )
        else:
            self.detail_fail_count += 1
            self.log_signal_func(
                f"❌ [DB] detail 저장 실패 | hist_id={self.hist_id} | 상품={rs.get('상품명')}"
            )

        return ok

    def export_detail_to_excel(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver

        if not self.excel_driver:
            self.log_signal_func("❌ [엑셀] excel_driver 없음")
            return False

        if not sqlite_driver:
            self.log_signal_func("❌ [엑셀] sqlite_driver 없음")
            return False

        if not self.hist_id:
            self.log_signal_func("❌ [엑셀] hist_id 없음")
            return False

        query = """
                SELECT
                    keyword AS "키워드",
                    crawled_at AS "수집일시",
                    product_name AS "상품명",
                    category AS "카테고리",
                    product_no AS "상품번호",
                    list_price AS "원가",
                    low_price AS "최소가",
                    sale_price AS "판매가격",
                    delivery_fee AS "배송비",
                    discount_ratio AS "할인률",
                    brand AS "브랜드",
                    review_count AS "리뷰수",
                    purchase_count AS "구매건수",
                    wish_count AS "찜하기수",
                    store_name AS "스토어명",
                    mall_prod_mbl_url AS "스토어모바일주소",
                    mall_product_url AS "스토어PC주소",
                    pc_url AS "PC주소",
                    total_visit_count AS "전체방문자수",
                    page AS "페이지",
                    no AS "번호"
                FROM naver_shop_total_detail
                WHERE hist_id = ?
                ORDER BY detail_id
                """

        row_list = sqlite_driver.fetchall(query, (self.hist_id,))
        if not row_list:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        excel_columns = self.columns or [
            "키워드",
            "수집일시",
            "상품명",
            "카테고리",
            "상품번호",
            "원가",
            "최소가",
            "판매가격",
            "배송비",
            "할인률",
            "브랜드",
            "리뷰수",
            "구매건수",
            "찜하기수",
            "스토어명",
            "스토어모바일주소",
            "스토어PC주소",
            "PC주소",
            "전체방문자수",
            "페이지",
            "번호",
        ]

        excel_filename = f"{self.site_name}_{self.job_id}.xlsx"

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=excel_filename,
            row_list=row_list,
            columns=excel_columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def _log_and_return_true(self, message: str) -> bool:
        self.log_signal_func(message)
        return True

    def _sleep_or_stop(self, sec: float, message: str) -> bool:
        if not self.sleep_s(sec):
            self.log_signal_func(message)
            return False
        return True

    def finalize_db_and_excel(self) -> None:
        temp_sqlite_driver = None

        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            db_path = self.get_runtime_db_path()

            if not temp_sqlite_driver.connect(db_path):
                self.log_signal_func("❌ [DB] 최종 마감용 연결 실패")
                return

            if self.update_hist_end(temp_sqlite_driver):
                self.log_signal_func("✅ [DB] hist 최종 업데이트 완료")
            else:
                self.log_signal_func("❌ [DB] hist 최종 업데이트 실패")

            auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))
            if auto_save_yn:
                if self.export_detail_to_excel(temp_sqlite_driver):
                    self.log_signal_func("✅ [엑셀] detail 자동 저장 완료")
                else:
                    self.log_signal_func("❌ [엑셀] detail 자동 저장 실패")

        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")

        finally:
            try:
                if temp_sqlite_driver:
                    temp_sqlite_driver.close()
            except Exception:
                pass

    # =========================================================
    # main (수집 실행 로직)
    # =========================================================
    def main(self) -> bool:
        keywords_str = self.get_setting_value(self.setting, "keyword") or ""
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        start_p = int(self.get_setting_value(self.setting, "start_page") or 1)
        end_p = int(self.get_setting_value(self.setting, "end_page") or 1)
        site_total_cnt = int(self.get_setting_value(self.setting, "site_total_cnt") or 0)

        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()


        # === 신규 ===
        self.dup_yn = bool(self.get_setting_value(self.setting, "dup_yn"))
        self.seen_store_names = self.load_existing_store_names() if self.dup_yn else set()

        if self.dup_yn:
            self.log_signal_func(
                f"✅ [중복] 스토어명 중복제거 사용 | 초기 DB 건수={len(self.seen_store_names)}"
            )
        else:
            self.log_signal_func("ℹ️ [중복] 스토어명 중복제거 미사용")

        if not keywords:
            self.log_signal_func("❌ 키워드가 없습니다.")
            self.finish_job("FAIL", "키워드가 없습니다.")
            return False

        total_pages = (end_p - start_p + 1)
        self.total_cnt = len(keywords) * total_pages
        self.current_cnt = 0
        self.before_pro_value = 0.0

        self.log_signal_func(
            f"🚀 작업 시작 | 키워드수={len(keywords)} | 페이지={start_p}~{end_p} | 총 작업단위={self.total_cnt}"
        )

        completed_keywords = 0

        for kw_idx, kw in enumerate(keywords, start=1):
            if not self.running:
                return self._log_and_return_true(
                    f"🛑 사용자 중단 감지(main-키워드 시작 전) | 마지막완료키워드수={completed_keywords} | 다음키워드={kw}"
                )

            keyword_start_cnt = self.current_cnt
            self.log_signal_func(
                f"🔎 [키워드 시작 {kw_idx}/{len(keywords)}] {kw} | page={start_p}~{end_p}"
            )

            all_pages = list(range(start_p, end_p + 1))
            chunk_size = 10

            for i in range(0, len(all_pages), chunk_size):
                if not self.running:
                    return self._log_and_return_true(
                        f"🛑 사용자 중단 감지(chunk 시작 전) | 키워드={kw} | chunk_index={i}"
                    )

                current_chunk = all_pages[i: i + chunk_size]
                chunk_items_queue = []

                self.log_signal_func(
                    f"🌐 [브라우저 시작] 키워드={kw} | chunk={current_chunk[0]}p~{current_chunk[-1]}p"
                )

                pyautogui.hotkey("win", "r")
                if not self._sleep_or_stop(0.5, f"🛑 중단 또는 sleep 실패 | chrome 실행 전 대기 | 키워드={kw}"):
                    return True

                pyautogui.write("chrome")
                pyautogui.press("enter")
                if not self._sleep_or_stop(3, f"🛑 중단 또는 sleep 실패 | chrome 실행 후 대기 | 키워드={kw}"):
                    return True

                self.log_signal_func(
                    f"📂 [{kw}] {current_chunk[0]}p ~ {current_chunk[-1]}p 리스트 확보 중..."
                )

                for page in current_chunk:
                    if not self.running:
                        return self._log_and_return_true(
                            f"🛑 사용자 중단 감지(페이지 시작 전) | 키워드={kw} | page={page}"
                        )

                    target_url = (
                        f"https://msearch.shopping.naver.com/search/all?"
                        f"adQuery={kw}&npayType=2&origQuery={kw}&"
                        f"pagingIndex={page}&pagingSize=40&productSet=checkout&"
                        f"query={kw}&sort=date&viewType=list"
                    )

                    page_success = False

                    for retry in range(1, 4):
                        if not self.running:
                            return self._log_and_return_true(
                                f"🛑 사용자 중단 감지(리스트 재시도 중) | 키워드={kw} | page={page} | retry={retry}"
                            )

                        self.log_signal_func(
                            f"📄 [리스트 페이지 시도] 키워드={kw} | page={page} | retry={retry}/3"
                        )

                        pyautogui.hotkey("ctrl", "l")
                        if not self._sleep_or_stop(
                                random.uniform(0.2, 0.5),
                                f"🛑 중단 또는 sleep 실패 | 주소창 이동 후 대기 | 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        pyperclip.copy(target_url)
                        pyautogui.hotkey("ctrl", "v")
                        pyautogui.press("enter")
                        if not self._sleep_or_stop(
                                random.uniform(4.0, 5.5),
                                f"🛑 중단 또는 sleep 실패 | 페이지 이동 후 대기 | 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        captcha_result = self.handle_captcha_with_retry()
                        if captcha_result == 0:
                            self.log_signal_func(
                                f"❌ 캡차 해결 실패: 작업 중단 | 키워드={kw} | page={page} | retry={retry}"
                            )
                            pyautogui.hotkey("alt", "f4")
                            self.finish_job("FAIL", f"리스트 캡차 실패 | 키워드={kw} | page={page}")
                            return True

                        pyautogui.hotkey("ctrl", "u")
                        if not self._sleep_or_stop(
                                random.uniform(3, 4),
                                f"🛑 중단 또는 sleep 실패 | 소스보기 대기 | 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.hotkey("ctrl", "c")
                        if not self._sleep_or_stop(
                                1.5,
                                f"🛑 중단 또는 sleep 실패 | HTML 복사 대기 | 키워드={kw} | page={page} | retry={retry}",
                        ):
                            return True

                        pyautogui.hotkey("ctrl", "w")

                        extracted = self.extract_items_from_html(pyperclip.paste())
                        if extracted:
                            for item in extracted:
                                item["_page_num"] = page
                            chunk_items_queue.extend(extracted)
                            self.log_signal_func(
                                f"📄 {page}페이지 수집 완료: 상품 {len(extracted)}개 확보 | 키워드={kw} | retry={retry}"
                            )
                            page_success = True
                            break
                        else:
                            self.log_signal_func(
                                f"⚠️ 리스트 추출 실패 | 키워드={kw} | page={page} | retry={retry}/3"
                            )
                            if not self._sleep_or_stop(
                                    random.uniform(2.0, 3.5),
                                    f"🛑 중단 또는 sleep 실패 | 리스트 재시도 전 대기 | 키워드={kw} | page={page} | retry={retry}",
                            ):
                                return True

                    if not page_success:
                        self.log_signal_func(
                            f"❌ 페이지 최종 실패 | 키워드={kw} | page={page} | 3회 재시도 후 추출 실패"
                        )

                    self.current_cnt += 1

                if chunk_items_queue:
                    self.log_signal_func(f"🚀 확보된 {len(chunk_items_queue)}개 상품 상세 수집 시작...")

                    # === 기존 중복제거 부분 교체 ===
                    chunk_items_queue = self.filter_chunk_items(chunk_items_queue, kw)
                    chunk_results = []

                    for idx, item_data in enumerate(chunk_items_queue):
                        if not self.running:
                            return self._log_and_return_true(
                                f"🛑 사용자 중단 감지(상세 수집 중) | 키워드={kw} | 상세순번={idx + 1}/{len(chunk_items_queue)}"
                            )

                        item = item_data.get("item", {})
                        pc_url = item.get("mallPcUrl")
                        p_num = item_data.get("_page_num")

                        if pc_url:
                            self.log_signal_func(
                                f"🔗 [{kw}] {p_num}p - {idx + 1}/{len(chunk_items_queue)} 상세 이동"
                            )

                            pyautogui.hotkey("ctrl", "l")
                            pyperclip.copy(pc_url)
                            pyautogui.hotkey("ctrl", "v")
                            pyautogui.press("enter")
                            if not self._sleep_or_stop(
                                    random.uniform(3.5, 5.0),
                                    f"🛑 중단 또는 sleep 실패 | 상세 이동 후 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.scroll(random.randint(-600, -300))
                            if not self._sleep_or_stop(
                                    random.uniform(0.5, 1.0),
                                    f"🛑 중단 또는 sleep 실패 | 상세 스크롤1 후 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.scroll(random.randint(300, 600))

                            captcha_result = self.handle_captcha_with_retry()
                            if captcha_result == 2:
                                self.log_signal_func(
                                    f"🔄 상세 캡차 해결 후 재진입 | 키워드={kw} | page={p_num} | idx={idx + 1}"
                                )
                                pyautogui.hotkey("ctrl", "l")
                                pyperclip.copy(pc_url)
                                pyautogui.hotkey("ctrl", "v")
                                pyautogui.press("enter")
                                if not self._sleep_or_stop(
                                        random.uniform(3.0, 4.5),
                                        f"🛑 중단 또는 sleep 실패 | 상세 재진입 후 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                                ):
                                    return True
                            elif captcha_result == 0:
                                self.finish_job("FAIL", f"상세 캡차 실패 | 키워드={kw} | page={p_num} | idx={idx + 1}")
                                return True

                            pyautogui.hotkey("ctrl", "a")
                            if not self._sleep_or_stop(
                                    random.uniform(0.8, 1.2),
                                    f"🛑 중단 또는 sleep 실패 | 상세 전체선택 후 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            pyautogui.hotkey("ctrl", "c")
                            if not self._sleep_or_stop(
                                    0.6,
                                    f"🛑 중단 또는 sleep 실패 | 상세 복사 후 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True

                            detail_text = pyperclip.paste()
                            total_visit = "0"
                            v_match = re.search(r"전체\s*([\d,]+)", detail_text)
                            if v_match:
                                total_visit = v_match.group(1).replace(",", "")

                            categories = [
                                item.get("category1Name"),
                                item.get("category2Name"),
                                item.get("category3Name"),
                                item.get("category4Name"),
                            ]
                            category_str = "/".join([c for c in categories if c])

                            rs = {
                                "키워드": kw,
                                "수집일시": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "상품명": item.get("productName"),
                                "카테고리": category_str,
                                "상품번호": item.get("id"),
                                "원가": item.get("listPrice"),
                                "최소가": item.get("lowPrice"),
                                "판매가격": item.get("price"),
                                "배송비": item.get("dlvryFee"),
                                "할인률": item.get("discountRatio"),
                                "브랜드": item.get("brand"),
                                "리뷰수": item.get("reviewCount"),
                                "구매건수": item.get("purchaseCnt"),
                                "찜하기수": item.get("keepCnt"),
                                "스토어명": item.get("mallName"),
                                "스토어모바일주소": item.get("mallProdMblUrl"),
                                "스토어PC주소": item.get("mallProductUrl"),
                                "PC주소": pc_url,
                                "전체방문자수": total_visit,
                                "페이지": p_num,
                                "번호": idx + 1,
                            }

                            chunk_results.append(rs)

                            if site_total_cnt >= int(total_visit):
                                if not self.running:
                                    return self._log_and_return_true(
                                        f"🛑 사용자 중단 감지(DB 저장 직전) | 키워드={kw} | page={p_num} | idx={idx + 1}"
                                    )

                                if not self.insert_detail_row(rs):
                                    self.log_signal_func(
                                        f"❌ DB 저장 실패 | 키워드={kw} | page={p_num} | 방문자={total_visit} | 기준={site_total_cnt}"
                                    )

                            self.log_signal_func(
                                f"📦 [수집 완료] {kw} - {p_num}p | {item.get('mallName')} | 방문자: {total_visit}"
                            )

                            if not self._sleep_or_stop(
                                    random.uniform(1.0, 2.5),
                                    f"🛑 중단 또는 sleep 실패 | 상세 간 대기 | 키워드={kw} | page={p_num} | idx={idx + 1}",
                            ):
                                return True
                        else:
                            self.log_signal_func(
                                f"⚠️ 상세 URL 없음 스킵 | 키워드={kw} | page={p_num} | idx={idx + 1}"
                            )
                else:
                    self.log_signal_func(
                        f"⚠️ chunk_items_queue 비어있음 | 키워드={kw} | chunk={current_chunk[0]}p~{current_chunk[-1]}p"
                    )

                self.log_signal_func("🧹 묶음 작업 완료. 브라우저를 정리합니다.")
                pyautogui.hotkey("alt", "f4")
                if not self._sleep_or_stop(
                        2,
                        f"🛑 중단 또는 sleep 실패 | 브라우저 종료 후 대기 | 키워드={kw} | chunk={current_chunk[0]}~{current_chunk[-1]}",
                ):
                    return True

                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                self.log_signal_func(
                    f"📊 {current_chunk[-1]}p 묶음 처리 완료 ({self.current_cnt}/{self.total_cnt}) | 키워드={kw}"
                )

            completed_keywords += 1
            processed_pages = self.current_cnt - keyword_start_cnt
            self.log_signal_func(
                f"✅ [키워드 종료 {kw_idx}/{len(keywords)}] {kw} | 처리페이지수={processed_pages} | 누적진행={self.current_cnt}/{self.total_cnt}"
            )

        self.log_signal_func(
            f"🏁 전체 작업 완료 | 완료키워드수={completed_keywords}/{len(keywords)} | 총진행={self.current_cnt}/{self.total_cnt}"
        )
        self.finish_job("SUCCESS")
        return True

    # =========================================================
    # 이하 기존 메서드 동일
    # =========================================================
    def record_audio(self, filename, duration=17):
        p = pyaudio.PyAudio()
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            if not default_speakers["isLoopbackDevice"]:
                for loopback in p.get_loopback_device_info_generator():
                    if not self.running:
                        return False
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            wave_format = pyaudio.paInt16
            channels = int(default_speakers.get("maxInputChannels") or 2)
            rate = int(default_speakers["defaultSampleRate"])

            stream = p.open(
                format=wave_format,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=default_speakers["index"],
            )

            frames = []
            for _ in range(0, int(rate / 1024 * duration)):
                if not self.running:
                    return False
                frames.append(stream.read(1024, exception_on_overflow=False))

            stream.stop_stream()
            stream.close()

            with wave.open(filename, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(wave_format))
                wf.setframerate(rate)
                wf.writeframes(b"".join(frames))
            return True
        except Exception:
            return False
        finally:
            p.terminate()

    def handle_captcha_with_retry(self):
        captcha_cnt = int(self.get_setting_value(self.setting, "cpcha_cnt") or 5)
        max_tries = captcha_cnt

        for attempt in range(1, max_tries + 1):
            if not self.running:
                self.log_signal_func("🛑 handle_captcha_with_retry 중단: running=False")
                return 0

            self.log_signal_func(f"🔍 [시도 {attempt}/{max_tries}] 화면 상태 체크 중...")

            if attempt > 1:
                pyautogui.press("tab")
                if not self.sleep_s(0.5):
                    self.log_signal_func("🛑 캡차 처리 중단: tab 이후 sleep 실패")
                    return 0

            pyperclip.copy("")
            pyautogui.hotkey("ctrl", "a")
            if not self.sleep_s(random.uniform(0.6, 0.9)):
                self.log_signal_func("🛑 캡차 처리 중단: 전체선택 후 sleep 실패")
                return 0

            pyautogui.hotkey("ctrl", "c")
            if not self.sleep_s(random.uniform(0.5, 0.8)):
                self.log_signal_func("🛑 캡차 처리 중단: 복사 후 sleep 실패")
                return 0

            page_content = pyperclip.paste()
            target_text = "보안 확인을 완료해 주세요"

            if target_text not in page_content:
                if attempt == 1:
                    self.log_signal_func("✅ 캡차 없음")
                    return 1
                self.log_signal_func("✅ 캡차 해결 성공!")
                return 2

            self.log_signal_func("🚩 캡차 발견! 해결을 시작합니다.")

            if attempt == 1:
                for _ in range(5):
                    pyautogui.press("tab")
                    if not self.sleep_s(random.uniform(0.1, 0.2)):
                        self.log_signal_func("🛑 캡차 처리 중단: tab 이동 중 sleep 실패")
                        return 0
                pyautogui.press("enter")
            else:
                pyautogui.press("enter")

            if not self.sleep_s(2):
                self.log_signal_func("🛑 캡차 처리 중단: 음성재생 대기 sleep 실패")
                return 0

            filename = "captcha_audio_final.wav"
            if self.record_audio(filename, duration=17):
                result = self.model.transcribe(filename, language="ko", fp16=False)
                code = "".join(filter(str.isdigit, result["text"]))[:6]

                if not code:
                    code = "123456"
                    self.log_signal_func("⚠️ AI 인식 실패 (숫자 없음). 기본값 '123456' 입력")
                else:
                    self.log_signal_func(f"📝 AI 인식 코드: {code}")

                if attempt == 1:
                    pyautogui.press("tab")
                    if not self.sleep_s(0.5):
                        self.log_signal_func("🛑 캡차 처리 중단: 입력칸 이동 후 sleep 실패")
                        return 0
                else:
                    pyautogui.hotkey("shift", "tab")
                    if not self.sleep_s(0.5):
                        self.log_signal_func("🛑 캡차 처리 중단: shift+tab 후 sleep 실패")
                        return 0

                pyautogui.write(code, interval=random.uniform(0.1, 0.2))

                for _ in range(3):
                    pyautogui.press("tab")

                pyautogui.press("enter")

                self.log_signal_func("⏳ 결과 검증 대기 중...")
                if not self.sleep_s(random.uniform(5.0, 6.0)):
                    self.log_signal_func("🛑 캡차 처리 중단: 결과 검증 대기 sleep 실패")
                    return 0
            else:
                self.log_signal_func("❌ 캡차 음성 녹음 실패")

        self.log_signal_func(f"❌ 캡차 최대 재시도 초과: {max_tries}회")
        return 0

    def extract_items_from_html(self, html_source):
        try:
            pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
            match = re.search(pattern, html_source, re.DOTALL)
            if not match:
                return []

            json_data = json.loads(match.group(1))
            props = json_data.get("props", {}).get("pageProps", {})

            raw_list = (
                    props.get("compositeProducts", {}).get("list", [])
                    or props.get("initialState", {}).get("products", {}).get("list", [])
                    or []
            )

            normalized = []
            for x in raw_list:
                if isinstance(x, dict) and "item" in x and isinstance(x.get("item"), dict):
                    normalized.append(x)
                elif isinstance(x, dict):
                    normalized.append({"item": x})
            return normalized

        except Exception:
            return []