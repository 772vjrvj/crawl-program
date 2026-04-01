# src/workers/main/api_naver_land_real_estate_detail_down_set_worker.py
import io
import os
import random
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False


class ApiNaverLandRealEstateDetailDownSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.driver = None
        self.selenium_driver = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "네이버 부동산 미디어"
        self.before_pro_value: float = 0.0

        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None

        self.folder_path: str = ""
        self.out_dir: str = "output_naver_land_real_estate_detail_down"

        self.fin_land_article_url: str = "https://fin.land.naver.com/articles"
        self.gallery_image_api_url: str = "https://fin.land.naver.com/front-api/v1/article/galleryImages"

        # 개별 팝업 수집 재시도
        self.collect_retry_count: int = 5

        # 전체 라운드 수 (처음 1회 포함 총 3바퀴)
        self.total_round_count: int = 3

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func("main 시작")

            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir,
            )

            source_items = list(self.excel_data_list or [])
            total_count = len(source_items)
            finalized_count = 0

            tasks: List[Dict[str, Any]] = [self._make_task(data) for data in source_items]

            for round_no in range(1, self.total_round_count + 1):
                if not self.running:
                    return True

                target_tasks = [task for task in tasks if not task["finalized"]]
                if not target_tasks:
                    break

                self.log_signal_func(
                    f"[전체 처리 라운드] {round_no}/{self.total_round_count} / 대상={len(target_tasks)}"
                )

                for task in target_tasks:
                    if not self.running:
                        return True

                    self._process_task_round(task)

                    if task["finalized"]:
                        finalized_count += 1
                        self._emit_progress(finalized_count, total_count)

                    time.sleep(random.uniform(2, 4))

                if round_no < self.total_round_count:
                    remain_count = len([task for task in tasks if not task["finalized"]])
                    self.log_signal_func(f"[전체 재시도 이동] 남은 실패 항목 수={remain_count}")
                    if remain_count > 0:
                        time.sleep(random.uniform(2.5, 4.0))

            for task in tasks:
                rows = task.get("rows") or []
                if rows:
                    self.excel_driver.append_to_csv(
                        self.csv_filename,
                        rows,
                        self.columns,
                        folder_path=self.folder_path,
                        sub_dir=self.out_dir,
                    )

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")
            return True

    def _make_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        atcl_no = str(data.get("네이버부동산") or "").strip()

        return {
            "data": data,
            "atcl_no": atcl_no,
            "detail_url": f"{self.fin_land_article_url}/{atcl_no}" if atcl_no else "",
            "rows": [],
            "expected_count": None,
            "target_dir": "",
            "skip": False,
            "finalized": False,
            "last_message": "",
        }

    def _process_task_round(self, task: Dict[str, Any]) -> None:
        data = task["data"]
        atcl_no = task["atcl_no"]
        detail_url = task["detail_url"]

        if not atcl_no:
            task["rows"] = [self._make_result_row(
                data=data,
                atcl_no="",
                seq="",
                media_type_text="",
                media_url="",
                saved_path="",
                status="fail",
                message="네이버부동산 값 없음",
            )]
            task["last_message"] = "네이버부동산 값 없음"
            return

        try:
            min_cnt = self._get_min_image_count_setting(default=8)

            self.log_signal_func(
                f"건물명={data.get('건물명')} / 호수={data.get('호수')} / 번호={atcl_no}"
            )

            self.driver.get(detail_url)
            self._wait_ready_state_complete(7)
            time.sleep(random.uniform(3, 5))

            gallery_count = task["expected_count"]
            if gallery_count is None:
                gallery_count = self._get_gallery_image_count(atcl_no)
                task["expected_count"] = gallery_count

            self.log_signal_func(f"[이미지 개수] gallery_count={gallery_count} / 기준={min_cnt}")

            if gallery_count is not None and gallery_count <= min_cnt:
                msg = f"이미지 개수 {gallery_count}개로 기준({min_cnt}) 이하라 스킵"
                task["skip"] = True
                task["rows"] = [self._make_result_row(
                    data=data,
                    atcl_no=atcl_no,
                    seq="",
                    media_type_text="",
                    media_url="",
                    saved_path="",
                    status="skip",
                    message=msg,
                )]
                task["finalized"] = True
                task["last_message"] = msg
                return

            media_items = self._collect_media_items_with_retry(
                atcl_no=atcl_no,
                detail_url=detail_url,
                gallery_count=gallery_count,
                max_retry=self.collect_retry_count,
            )

            if task["expected_count"] is None:
                task["expected_count"] = len(media_items) if media_items else 1

            if not task["rows"]:
                task["rows"] = self._build_pending_rows(
                    data=data,
                    atcl_no=atcl_no,
                    expected_count=int(task["expected_count"] or 1),
                )

            if media_items:
                task["target_dir"] = self._ensure_target_dir(
                    task=task,
                    media_items=media_items,
                )
                self._fill_rows_with_media_items(task, media_items)
            else:
                self._mark_empty_rows_fail(task, "팝업에서 미디어를 찾지 못함")

            if self._is_task_success(task):
                task["finalized"] = True
                task["last_message"] = "success"
            else:
                task["last_message"] = self._build_task_fail_message(task)

        except Exception as e:
            if not task["rows"]:
                task["rows"] = [self._make_result_row(
                    data=data,
                    atcl_no=atcl_no,
                    seq="",
                    media_type_text="",
                    media_url="",
                    saved_path="",
                    status="fail",
                    message=f"item 처리 실패: {e}",
                )]
            else:
                self._mark_empty_rows_fail(task, f"item 처리 실패: {e}")

            task["last_message"] = f"item 처리 실패: {e}"

    def _emit_progress(self, finalized_count: int, total_count: int) -> None:
        if total_count <= 0:
            return

        pro_value = (finalized_count / total_count) * 1000000
        self.progress_signal.emit(self.before_pro_value, pro_value)
        self.before_pro_value = pro_value

    def _is_task_success(self, task: Dict[str, Any]) -> bool:
        rows = task.get("rows") or []
        if not rows:
            return False

        for row in rows:
            status = str(row.get("상태") or "").strip()
            if status not in ("success", "skip"):
                return False
        return True

    def _build_task_fail_message(self, task: Dict[str, Any]) -> str:
        rows = task.get("rows") or []
        success_count = 0
        fail_count = 0

        for row in rows:
            if str(row.get("상태") or "").strip() == "success":
                success_count += 1
            else:
                fail_count += 1

        return f"success={success_count}, fail={fail_count}"

    def _build_pending_rows(
            self,
            data: Dict[str, Any],
            atcl_no: str,
            expected_count: int,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        for seq in range(1, expected_count + 1):
            rows.append(self._make_result_row(
                data=data,
                atcl_no=atcl_no,
                seq=seq,
                media_type_text="",
                media_url="",
                saved_path="",
                status="fail",
                message="미수집",
            ))

        return rows

    def _make_result_row(
            self,
            data: Dict[str, Any],
            atcl_no: str,
            seq: Any,
            media_type_text: str,
            media_url: str,
            saved_path: str,
            status: str,
            message: str,
    ) -> Dict[str, Any]:
        return {
            "건물명": str(data.get("건물명") or ""),
            "호수": str(data.get("호수") or ""),
            "네이버부동산": str(atcl_no or ""),
            "미디어 번호": seq,
            "유형": str(media_type_text or ""),
            "URL": str(media_url or ""),
            "저장경로": str(saved_path or ""),
            "상태": str(status or ""),
            "메세지": str(message or ""),
        }

    def _ensure_target_dir(
            self,
            task: Dict[str, Any],
            media_items: List[Dict[str, Any]],
    ) -> str:
        if task.get("target_dir"):
            return str(task["target_dir"])

        data = task["data"]
        building_name = str(data.get("건물명") or "").strip()
        ho = str(data.get("호수") or "").strip()
        has_video = any(str(x.get("media_type") or "").strip() == "video" for x in media_items)

        target_dir = self._make_target_dir(building_name, ho, has_video)
        task["target_dir"] = target_dir
        self.log_signal_func(f"저장 폴더: {target_dir}")
        return target_dir

    def _fill_rows_with_media_items(
            self,
            task: Dict[str, Any],
            media_items: List[Dict[str, Any]],
    ) -> None:
        rows = task.get("rows") or []
        atcl_no = task["atcl_no"]
        target_dir = str(task.get("target_dir") or "")

        for idx, item in enumerate(media_items, start=1):
            if idx > len(rows):
                break

            row = rows[idx - 1]
            if str(row.get("상태") or "").strip() == "success":
                continue

            media_type = str(item.get("media_type") or "").strip()
            media_url = str(item.get("media_url") or "").strip()
            media_type_text = "동영상" if media_type == "video" else "사진"

            row["유형"] = media_type_text
            row["URL"] = media_url

            if not media_url:
                row["상태"] = "fail"
                row["메세지"] = "media_url 없음"
                continue

            file_base_name = self._build_media_file_base_name(atcl_no, idx)

            if media_type == "video":
                save_path = self._make_unique_file_path(target_dir, file_base_name, ".mp4")
                ok, final_path, msg = self._save_video_file(media_url, save_path)
            else:
                save_path = self._make_unique_file_path(target_dir, file_base_name, ".jpg")
                ok, final_path, msg = self._save_image_file_as_jpg(media_url, save_path)

            row["저장경로"] = final_path if ok else ""
            row["상태"] = "success" if ok else "fail"
            row["메세지"] = msg if msg else ("저장 완료" if ok else "저장 실패")

        for idx in range(len(media_items) + 1, len(rows) + 1):
            row = rows[idx - 1]
            if str(row.get("상태") or "").strip() == "success":
                continue
            if not str(row.get("메세지") or "").strip() or row["메세지"] == "미수집":
                row["상태"] = "fail"
                row["메세지"] = "미디어 미수집"

    def _mark_empty_rows_fail(self, task: Dict[str, Any], message: str) -> None:
        rows = task.get("rows") or []

        if not rows:
            task["rows"] = [self._make_result_row(
                data=task["data"],
                atcl_no=task["atcl_no"],
                seq="",
                media_type_text="",
                media_url="",
                saved_path="",
                status="fail",
                message=message,
            )]
            return

        for row in rows:
            if str(row.get("상태") or "").strip() == "success":
                continue
            if not str(row.get("URL") or "").strip():
                row["상태"] = "fail"
                row["메세지"] = message

    def _collect_media_items_with_retry(
            self,
            atcl_no: str,
            detail_url: str,
            gallery_count: Optional[int],
            max_retry: int = 3,
    ) -> List[Dict[str, Any]]:
        best_items: List[Dict[str, Any]] = []

        for attempt in range(1, max_retry + 1):
            if not self.running:
                return best_items

            self.log_signal_func(f"[개별 수집 재시도] {attempt}/{max_retry}")

            try:
                self.driver.get(detail_url)
                self._wait_ready_state_complete(7)
                time.sleep(random.uniform(2.8, 4.2))

                opened = self._open_media_popup_any_frame(
                    target_name="매물 대표 이미지 1",
                    timeout_sec=12,
                )

                if not opened:
                    self.log_signal_func("팝업 열기 실패")
                    time.sleep(random.uniform(1.0, 1.6))
                    continue

                if not self._wait_popup_viewer_ready(timeout_sec=8):
                    self.log_signal_func("팝업 준비 timeout")

                self._focus_popup_viewer()
                time.sleep(0.4)

                scan_steps = 40
                if gallery_count is not None:
                    scan_steps = max(40, int(gallery_count) + 5)

                media_items = self._scan_all_media_current_popup(max_steps=scan_steps)

                if len(media_items) > len(best_items):
                    best_items = [dict(x) for x in media_items]

                self.log_signal_func(
                    f"[개별 수집 결과] expected={gallery_count} / actual={len(media_items)}"
                )

                if gallery_count is None and media_items:
                    return media_items

                if gallery_count is not None and len(media_items) == gallery_count:
                    return media_items

            except Exception as e:
                self.log_signal_func(f"[개별 수집 실패] attempt={attempt}/{max_retry} / {e}")

            time.sleep(random.uniform(1.0, 1.8))

        return best_items

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(
            timeout=1200,
            view_mode="mobile",
            window_size=(520, 980),
            mobile_metrics=(430, 932),
        )

        self.log_signal_func("✅ driver_set 완료")

    def cleanup(self) -> None:
        try:
            if self.csv_filename and self.excel_driver:
                self.excel_driver.convert_csv_to_excel_and_delete(
                    csv_filename=self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
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

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def _wait_ready_state_complete(self, timeout_sec: int = 7) -> None:
        try:
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            self.log_signal_func("readyState complete timeout")

    def _wait_current_frame_ready(self, timeout_sec: int = 5) -> bool:
        try:
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: d.execute_script("return !!document.body")
            )
            return True
        except Exception:
            return False

    def _extract_number_from_text(self, text: str) -> Optional[int]:
        s = str(text or "").strip().replace(",", "")
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else None

    def _find_count_in_current_frame(self) -> Optional[int]:
        selectors = [
            "span.ThumbnailMapGroup_quantity__2GMil",
            "span[class*='ThumbnailMapGroup_quantity']",
        ]

        for selector in selectors:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = str(el.text or "").strip()
                count = self._extract_number_from_text(text)
                if count is not None:
                    self.log_signal_func(f"[DOM count] selector={selector} text={text} count={count}")
                    return count

        return None

    def _get_gallery_count_from_dom_any_frame(self) -> Optional[int]:
        try:
            self.driver.switch_to.default_content()

            count = self._find_count_in_current_frame()
            if count is not None:
                return count

            frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            for idx in range(len(frames)):
                self.driver.switch_to.default_content()
                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                if idx >= len(frames):
                    break

                self.driver.switch_to.frame(frames[idx])
                self._wait_current_frame_ready(3)

                count = self._find_count_in_current_frame()
                if count is not None:
                    self.driver.switch_to.default_content()
                    return count

            self.driver.switch_to.default_content()
            return None

        except Exception as e:
            self.log_signal_func(f"[DOM count 실패] {e}")
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return None

    def _get_browser_user_agent(self) -> str:
        try:
            return str(self.driver.execute_script("return navigator.userAgent") or "").strip()
        except Exception:
            return ""

    def _build_cookie_header_from_driver(self) -> str:
        try:
            cookies = self.driver.get_cookies() or []
            return "; ".join(
                f"{str(c.get('name') or '').strip()}={str(c.get('value') or '').strip()}"
                for c in cookies
                if str(c.get("name") or "").strip()
            )
        except Exception:
            return ""

    def _build_gallery_request_headers(self, atcl_no: str) -> Dict[str, str]:
        referer = ""
        try:
            referer = str(self.driver.current_url or "").strip()
        except Exception:
            pass

        if not referer:
            referer = f"{self.fin_land_article_url}/{atcl_no}"

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": referer,
            "origin": "https://fin.land.naver.com",
            "user-agent": self._get_browser_user_agent(),
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

        cookie_header = self._build_cookie_header_from_driver()
        if cookie_header:
            headers["cookie"] = cookie_header

        return headers

    def _get_gallery_count_from_api(self, atcl_no: str) -> Optional[int]:
        try:
            res = requests.get(
                self.gallery_image_api_url,
                params={"articleNumber": str(atcl_no or "").strip()},
                headers=self._build_gallery_request_headers(atcl_no),
                timeout=20,
                allow_redirects=True,
            )

            self.log_signal_func(f"[API count] status={res.status_code}")

            if res.status_code >= 400:
                return None

            if "json" not in str(res.headers.get("content-type") or "").lower():
                return None

            body = res.json()
            result = body.get("result")
            if not isinstance(result, list):
                return None

            return len(result)

        except Exception as e:
            self.log_signal_func(f"[API count 실패] {e}")
            return None

    def _get_gallery_image_count(self, atcl_no: str) -> Optional[int]:
        dom_count = self._get_gallery_count_from_dom_any_frame()
        if dom_count is not None:
            self.log_signal_func(f"[gallery count] DOM 사용: {dom_count}")
            return dom_count

        api_count = self._get_gallery_count_from_api(atcl_no)
        if api_count is not None:
            self.log_signal_func(f"[gallery count] API 사용: {api_count}")
            return api_count

        self.log_signal_func("[gallery count] DOM/API 모두 실패")
        return None

    def _xpath_literal(self, value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join([f"'{part}'" for part in parts]) + ")"

    def _click_media_thumb_in_current_frame(self, target_name: str) -> bool:
        target_xpath = self._xpath_literal(target_name)

        selectors = [
            (By.CSS_SELECTOR, f'button[aria-label="{target_name}"]'),
            (By.CSS_SELECTOR, f'button[aria-label*="{target_name}"]'),
            (By.CSS_SELECTOR, f'[role="button"][aria-label="{target_name}"]'),
            (By.CSS_SELECTOR, f'[role="button"][aria-label*="{target_name}"]'),
            (By.CSS_SELECTOR, f'img[alt="{target_name}"]'),
            (By.CSS_SELECTOR, f'img[alt*="{target_name}"]'),
            (By.XPATH, f'//img[contains(@alt, {target_xpath})]'),
            (
                By.XPATH,
                f'//img[contains(@alt, {target_xpath})]/ancestor::*['
                f'self::button or self::a or @role="button" or @tabindex][1]'
            ),
            (By.XPATH, f'//*[@aria-label and contains(@aria-label, {target_xpath})]'),
            (
                By.XPATH,
                f'//*[contains(normalize-space(.), {target_xpath}) and '
                f'(self::button or self::a or @role="button")]'
            ),
        ]

        for by, selector in selectors:
            elements = self.driver.find_elements(by, selector)
            for el in elements:
                try:
                    if not el.is_displayed():
                        continue
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                        el
                    )
                    time.sleep(0.3)
                    try:
                        el.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", el)
                    return True
                except Exception:
                    continue

        return False

    def _click_visible_media_fallback_in_current_frame(self) -> bool:
        try:
            return bool(self.driver.execute_script("""
                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' &&
                           Number(s.opacity) !== 0 && r.width > 40 && r.height > 40;
                }

                function score(img) {
                    const r = img.getBoundingClientRect();
                    const src = (img.currentSrc || img.src || "").toLowerCase();
                    const alt = (img.alt || "").toLowerCase();
                    let v = r.width * r.height;
                    if (alt.includes("매물")) v += 500000;
                    if (alt.includes("대표")) v += 500000;
                    if (alt.includes("사진")) v += 300000;
                    if (src.includes("land")) v += 100000;
                    if (src.includes("pstatic")) v += 100000;
                    return v;
                }

                const list = [];
                document.querySelectorAll("img").forEach((img) => {
                    if (!isVisible(img)) return;
                    const src = img.currentSrc || img.src || "";
                    const lower = src.toLowerCase();
                    if (!src) return;
                    if (lower.startsWith("data:image")) return;
                    if (lower.includes("icon") || lower.includes("logo") || lower.includes("sprite")) return;

                    const clickable = img.closest("button, a, [role='button'], [tabindex]") || img;
                    list.push({ el: clickable, score: score(img) });
                });

                list.sort((a, b) => b.score - a.score);
                if (!list.length) return false;

                const target = list[0].el;
                target.scrollIntoView({block: "center", inline: "center"});
                try { target.click(); return true; } catch (e) {}
                try {
                    target.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true}));
                    return true;
                } catch (e) {}
                return false;
            """))
        except Exception:
            return False

    def _open_media_popup_any_frame(self, target_name: str = "매물 대표 이미지 1", timeout_sec: int = 12) -> bool:
        try:
            for round_idx in range(4):
                self.driver.switch_to.default_content()

                wait_sec = 1.2 + (round_idx * 1.0)
                self.log_signal_func(f"[팝업 탐색 재시도] round={round_idx + 1} wait={wait_sec:.1f}s")
                time.sleep(wait_sec)

                try:
                    self.log_signal_func("[main frame] 탐색 시작")

                    if self._click_media_thumb_in_current_frame(target_name):
                        self.log_signal_func("[main frame] 썸네일 클릭 성공")
                        time.sleep(1.5)
                        return True

                    if self._click_visible_media_fallback_in_current_frame():
                        self.log_signal_func("[main frame] fallback 클릭 성공")
                        time.sleep(1.5)
                        return True
                except Exception as e:
                    self.log_signal_func(f"[main frame] 탐색 실패: {e}")

                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                self.log_signal_func(f"iframe 개수 : {len(frames)}")

                for idx in range(len(frames)):
                    try:
                        self.driver.switch_to.default_content()
                        frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                        if idx >= len(frames):
                            break

                        self.driver.switch_to.frame(frames[idx])
                        self._wait_current_frame_ready(5)
                        time.sleep(0.8 + (round_idx * 0.3))

                        if self._click_media_thumb_in_current_frame(target_name):
                            self.log_signal_func(f"[iframe {idx}] 썸네일 클릭 성공")
                            time.sleep(1.5)
                            self.driver.switch_to.default_content()
                            return True

                        if self._click_visible_media_fallback_in_current_frame():
                            self.log_signal_func(f"[iframe {idx}] fallback 클릭 성공")
                            time.sleep(1.5)
                            self.driver.switch_to.default_content()
                            return True

                    except Exception as e:
                        self.log_signal_func(f"[iframe {idx}] 처리 실패: {e}")
                        continue

                try:
                    self.driver.switch_to.default_content()
                    time.sleep(0.7)

                    if self._click_media_thumb_in_current_frame(target_name):
                        self.log_signal_func("[main frame 재탐색] 썸네일 클릭 성공")
                        time.sleep(1.5)
                        return True

                    if self._click_visible_media_fallback_in_current_frame():
                        self.log_signal_func("[main frame 재탐색] fallback 클릭 성공")
                        time.sleep(1.5)
                        return True
                except Exception as e:
                    self.log_signal_func(f"[main frame 재탐색] 실패: {e}")

            self.driver.switch_to.default_content()
            return False

        except Exception as e:
            self.log_signal_func(f"_open_media_popup_any_frame 오류: {e}")
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False

    def _get_popup_state(self) -> Dict[str, Any]:
        try:
            rows = self.driver.execute_script("""
                function visibleArea(el) {
                    const r = el.getBoundingClientRect();
                    const w = Math.max(0, Math.min(r.right, window.innerWidth) - Math.max(r.left, 0));
                    const h = Math.max(0, Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0));
                    return w * h;
                }

                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' &&
                           Number(s.opacity) !== 0 && r.width > 20 && r.height > 20;
                }

                const out = [];

                document.querySelectorAll("video").forEach((el) => {
                    if (!isVisible(el)) return;
                    let src = el.currentSrc || el.src || "";
                    if (!src) {
                        const source = el.querySelector("source");
                        if (source) src = source.src || "";
                    }
                    if (!src) return;

                    out.push({
                        media_type: "video",
                        media_url: src,
                        area: visibleArea(el),
                    });
                });

                document.querySelectorAll("img").forEach((el) => {
                    if (!isVisible(el)) return;
                    const src = el.currentSrc || el.src || "";
                    if (!src) return;

                    const lower = src.toLowerCase();
                    if (lower.startsWith("data:image")) return;
                    if (lower.includes("icon") || lower.includes("sprite") || lower.includes("logo")) return;

                    out.push({
                        media_type: "image",
                        media_url: src,
                        area: visibleArea(el),
                    });
                });

                out.sort((a, b) => b.area - a.area);
                return out;
            """)
        except Exception:
            rows = []

        if not rows:
            return {"media_type": "", "media_url": ""}

        return {
            "media_type": str(rows[0].get("media_type") or "").strip(),
            "media_url": str(rows[0].get("media_url") or "").strip(),
        }

    def _wait_popup_viewer_ready(self, timeout_sec: float = 8.0) -> bool:
        end_time = time.time() + timeout_sec

        while time.time() < end_time:
            if not self.running:
                return False

            state = self._get_popup_state()
            if str(state.get("media_url") or "").strip():
                return True

            time.sleep(0.25)

        return False

    def _focus_popup_viewer(self) -> bool:
        try:
            return bool(self.driver.execute_script("""
                function visibleArea(el) {
                    const r = el.getBoundingClientRect();
                    return Math.max(0, r.width) * Math.max(0, r.height);
                }

                function isVisible(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' &&
                           Number(s.opacity) !== 0 && r.width > 20 && r.height > 20;
                }

                const candidates = [];
                document.querySelectorAll("video, img, [role='dialog'], [aria-modal='true'], [tabindex], body").forEach((el) => {
                    if (!isVisible(el)) return;
                    candidates.push({ el: el, area: visibleArea(el) });
                });

                candidates.sort((a, b) => b.area - a.area);

                const target = candidates.length ? candidates[0].el : document.body;
                if (!target) return false;

                try { target.scrollIntoView({block: "center", inline: "center"}); } catch (e) {}
                try { target.click(); } catch (e) {}
                try { target.focus(); } catch (e) {}
                try { document.body.focus(); } catch (e) {}

                return true;
            """))
        except Exception:
            return False

    def _is_next_disabled(self) -> Optional[bool]:
        try:
            return self.driver.execute_script("""
                const sels = [
                    "button[aria-label*='다음']",
                    "button[aria-label*='next' i]",
                    "[role='button'][aria-label*='다음']",
                    "[role='button'][aria-label*='next' i]"
                ];

                for (const sel of sels) {
                    const nodes = Array.from(document.querySelectorAll(sel));
                    for (const el of nodes) {
                        const r = el.getBoundingClientRect();
                        if (r.width < 10 || r.height < 10) continue;

                        const disabled = el.hasAttribute("disabled");
                        const ariaDisabled = el.getAttribute("aria-disabled") === "true";
                        return disabled || ariaDisabled;
                    }
                }

                return null;
            """)
        except Exception:
            return None

    def _send_arrow_right(self) -> bool:
        self._focus_popup_viewer()
        time.sleep(0.2)

        try:
            active_el = self.driver.switch_to.active_element
            active_el.send_keys(Keys.ARROW_RIGHT)
            return True
        except Exception:
            pass

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ARROW_RIGHT)
            return True
        except Exception:
            pass

        try:
            return bool(self.driver.execute_script("""
                function fire(target) {
                    try {
                        target.dispatchEvent(new KeyboardEvent("keydown", {
                            key: "ArrowRight", code: "ArrowRight", keyCode: 39, which: 39, bubbles: true
                        }));
                        target.dispatchEvent(new KeyboardEvent("keyup", {
                            key: "ArrowRight", code: "ArrowRight", keyCode: 39, which: 39, bubbles: true
                        }));
                        return true;
                    } catch (e) {
                        return false;
                    }
                }
                return fire(document.activeElement || document.body) || fire(document.body) || fire(document);
            """))
        except Exception:
            return False

    def _click_next(self, current_media_type: str = "") -> bool:
        selectors = [
            "button[aria-label*='다음']",
            "button[aria-label*='next' i]",
            "[role='button'][aria-label*='다음']",
            "[role='button'][aria-label*='next' i]",
        ]

        self._focus_popup_viewer()
        time.sleep(0.15)

        for selector in selectors:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in buttons:
                try:
                    if not btn.is_displayed():
                        continue

                    disabled = btn.get_attribute("disabled")
                    aria_disabled = btn.get_attribute("aria-disabled")
                    if disabled is not None or str(aria_disabled).lower() == "true":
                        continue

                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                        btn,
                    )
                    time.sleep(0.2)

                    try:
                        btn.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", btn)

                    time.sleep(2.0 if current_media_type == "video" else 1.0)
                    return True
                except Exception:
                    continue

        if self._send_arrow_right():
            time.sleep(2.0 if current_media_type == "video" else 1.0)
            return True

        return False

    def _wait_until_media_changed(
            self,
            prev_url: str,
            prev_media_type: str = "",
            timeout_sec: float = 5.0,
    ) -> Tuple[str, str]:
        end_time = time.time() + timeout_sec + (3.0 if prev_media_type == "video" else 0.0)

        while time.time() < end_time:
            if not self.running:
                return "", ""

            state = self._get_popup_state()
            media_type = str(state.get("media_type") or "").strip()
            media_url = str(state.get("media_url") or "").strip()

            if media_url and media_url != prev_url:
                return media_type, media_url

            time.sleep(0.25)

        return "", ""

    def _scan_all_media_current_popup(self, max_steps: int = 40) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_urls = set()
        timeout_streak = 0

        for step in range(max_steps):
            if not self.running:
                return []

            state = self._get_popup_state()
            media_type = str(state.get("media_type") or "").strip()
            media_url = str(state.get("media_url") or "").strip()

            self.log_signal_func(f"[STEP {step + 1}] type={media_type} / url={media_url}")

            if media_url and media_url not in seen_urls:
                seen_urls.add(media_url)
                results.append({
                    "seq": len(results) + 1,
                    "media_type": media_type,
                    "media_url": media_url,
                })

            next_disabled = self._is_next_disabled()
            if next_disabled is True:
                break

            prev_url = media_url
            moved = self._click_next(current_media_type=media_type)
            if not moved:
                break

            _, changed_url = self._wait_until_media_changed(
                prev_url=prev_url,
                prev_media_type=media_type,
                timeout_sec=5.0,
            )

            if not changed_url and (len(results) <= 1 or media_type == "video"):
                self._focus_popup_viewer()
                time.sleep(0.3)

                if self._send_arrow_right():
                    time.sleep(2.0 if media_type == "video" else 1.0)
                    _, changed_url = self._wait_until_media_changed(
                        prev_url=prev_url,
                        prev_media_type=media_type,
                        timeout_sec=5.0,
                    )

            if not changed_url:
                timeout_streak += 1
                if timeout_streak >= 2:
                    break
                continue

            timeout_streak = 0

        return results

    def _get_today_text(self) -> str:
        try:
            if ZoneInfo is not None:
                return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%y.%m.%d")
        except Exception:
            pass
        return datetime.now().strftime("%y.%m.%d")

    def _sanitize_filename(self, name: str) -> str:
        text = str(name or "").strip()
        text = re.sub(r'[\\/:*?"<>|]+', "_", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _get_min_image_count_setting(self, default: int = 8) -> int:
        raw = self.get_setting_value(self.setting, "cnt")
        try:
            value = int(str(raw).strip())
            return value if value >= 0 else default
        except Exception:
            return default

    def _build_folder_base_name(self, building_name: str, ho: str, has_video: bool = False) -> str:
        suffix = " (동)" if has_video else ""
        return self._sanitize_filename(f"{building_name} {ho} (N) {self._get_today_text()}{suffix}")

    def _build_media_file_base_name(self, atcl_no: str, seq: int) -> str:
        return self._sanitize_filename(f"{str(atcl_no).strip()}_{int(seq):02d}")

    def _make_target_dir(self, building_name: str, ho: str, has_video: bool = False) -> str:
        root_dir = os.path.join(self.folder_path, self.out_dir)
        os.makedirs(root_dir, exist_ok=True)

        base_name = self._build_folder_base_name(building_name, ho, has_video)
        candidate = os.path.join(root_dir, base_name)

        if not os.path.exists(candidate):
            os.makedirs(candidate, exist_ok=True)
            return candidate

        idx = 1
        while True:
            candidate = os.path.join(root_dir, f"{base_name}({idx})")
            if not os.path.exists(candidate):
                os.makedirs(candidate, exist_ok=True)
                return candidate
            idx += 1

    def _make_unique_file_path(self, target_dir: str, file_base_name: str, ext: str) -> str:
        ext = str(ext or "").strip()
        if not ext.startswith("."):
            ext = "." + ext

        candidate = os.path.join(target_dir, f"{file_base_name}{ext}")
        if not os.path.exists(candidate):
            return candidate

        idx = 1
        while True:
            candidate = os.path.join(target_dir, f"{file_base_name}({idx}){ext}")
            if not os.path.exists(candidate):
                return candidate
            idx += 1

    def _guess_ext_from_url(self, url: str, default_ext: str = ".bin") -> str:
        try:
            path = urlparse(url).path.lower()
        except Exception:
            return default_ext

        for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".mp4", ".mov", ".m3u8", ".avi", ".mkv"]:
            if path.endswith(ext):
                return ext

        return default_ext

    def _guess_ext_from_content_type(self, content_type: str, media_url: str = "") -> str:
        ct = str(content_type or "").lower()

        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
        if "bmp" in ct:
            return ".bmp"
        if "mp4" in ct:
            return ".mp4"
        if "quicktime" in ct:
            return ".mov"

        return self._guess_ext_from_url(media_url, ".bin")

    def _build_requests_session_from_driver(self) -> requests.Session:
        session = requests.Session()
        try:
            for cookie in self.driver.get_cookies():
                name = cookie.get("name")
                value = cookie.get("value")
                domain = cookie.get("domain")
                if name and value is not None:
                    session.cookies.set(name, value, domain=domain)
        except Exception:
            pass
        return session

    def _request_media_bytes(self, media_url: str) -> Tuple[bool, bytes, str, str]:
        session = self._build_requests_session_from_driver()
        headers = {
            "referer": str(self.driver.current_url or ""),
            "user-agent": self._get_browser_user_agent(),
            "accept": "*/*",
        }

        try:
            res = session.get(
                media_url,
                headers=headers,
                timeout=30,
                allow_redirects=True,
            )
            if res.status_code >= 400:
                return False, b"", "", f"다운로드 실패 status={res.status_code}"
            return True, res.content, str(res.headers.get("content-type") or ""), ""
        except Exception as e:
            return False, b"", "", f"다운로드 예외: {e}"

    def _save_video_file(self, media_url: str, save_path: str) -> Tuple[bool, str, str]:
        ok, raw, _, msg = self._request_media_bytes(media_url)
        if not ok:
            return False, "", msg

        try:
            with open(save_path, "wb") as f:
                f.write(raw)
            return True, save_path, ""
        except Exception as e:
            return False, "", f"동영상 저장 실패: {e}"

    def _save_image_file_as_jpg(self, media_url: str, save_path_jpg: str) -> Tuple[bool, str, str]:
        ok, raw, content_type, msg = self._request_media_bytes(media_url)
        if not ok:
            return False, "", msg

        if PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(raw))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(save_path_jpg, format="JPEG", quality=95)
                return True, save_path_jpg, ""
            except Exception:
                pass

        try:
            ext = self._guess_ext_from_content_type(content_type, media_url)
            fallback_path = os.path.splitext(save_path_jpg)[0] + ext
            with open(fallback_path, "wb") as f:
                f.write(raw)
            return True, fallback_path, f"JPG 변환 실패 또는 Pillow 미설치로 원본 저장({ext})"
        except Exception as e:
            return False, "", f"이미지 저장 실패: {e}"