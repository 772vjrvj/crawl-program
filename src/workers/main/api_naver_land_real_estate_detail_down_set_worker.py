# src/workers/main/api_naver_land_real_estate_detail_down_set_worker.py
import hashlib
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
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.folder_path: str = ""
        self.fin_land_article_url: str = "https://fin.land.naver.com/articles"

        # 저장 하위 폴더
        self.out_dir: str = "output_naver_land_real_estate_detail_down"

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func(" main 시작")

            # 저장경로
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            # 파일명
            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            # 초기 파일 생성
            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            total_len = len(self.excel_data_list) if self.excel_data_list else 0

            for index, data in enumerate(self.excel_data_list, start=1):
                try:
                    if not self.running:
                        return True

                    self.log_signal_func(f"✅ data : {data}")
                    self.log_signal_func(f"✅ 네이버부동산 : {data['네이버부동산']}")

                    atcl_no = str(data["네이버부동산"]).strip()
                    detail_url = f"{self.fin_land_article_url}/{atcl_no}"

                    self.driver.get(detail_url)
                    self._wait_ready_state_complete(7)
                    time.sleep(random.uniform(3, 5))

                    opened = self._open_media_popup_any_frame(
                        target_name="매물 대표 이미지 1",
                        timeout_sec=12,
                    )

                    if opened:
                        self.log_signal_func("✅ 썸네일 클릭 완료 - 팝업 열림")

                        media_items = self._scan_all_media_current_popup(max_steps=40)

                        if not media_items:
                            save_list = [{
                                "건물명": str(data.get("건물명") or ""),
                                "호수": str(data.get("호수") or ""),
                                "네이버부동산": atcl_no,
                                "미디어 번호": "",
                                "유형": "",
                                "URL": "",
                                "저장경로": "",
                                "상태": "fail",
                                "메세지": "팝업에서 미디어를 찾지 못함",
                            }]
                            self.excel_driver.append_to_csv(
                                self.csv_filename,
                                save_list,
                                self.columns,
                                folder_path=self.folder_path,
                                sub_dir=self.out_dir,
                            )
                        else:
                            self._download_and_append_result_rows(
                                data=data,
                                atcl_no=atcl_no,
                                media_items=media_items,
                            )
                    else:
                        self.log_signal_func("❌ 썸네일 클릭 실패 - 팝업 못 열음")

                        save_list = [{
                            "건물명": str(data.get("건물명") or ""),
                            "호수": str(data.get("호수") or ""),
                            "네이버부동산": atcl_no,
                            "미디어 번호": "",
                            "유형": "",
                            "URL": "",
                            "저장경로": "",
                            "상태": "fail",
                            "메세지": "썸네일 클릭 실패 - 팝업 못 열음",
                        }]
                        self.excel_driver.append_to_csv(
                            self.csv_filename,
                            save_list,
                            self.columns,
                            folder_path=self.folder_path,
                            sub_dir=self.out_dir,
                        )

                except Exception as e:
                    self.log_signal_func(f"[item 처리 실패] {e}")

                    save_list = [{
                        "건물명": str(data.get("건물명") or ""),
                        "호수": str(data.get("호수") or ""),
                        "네이버부동산": str(data.get("네이버부동산") or ""),
                        "미디어 번호": "",
                        "유형": "",
                        "URL": "",
                        "저장경로": "",
                        "상태": "fail",
                        "메세지": f"item 처리 실패: {e}",
                    }]
                    try:
                        self.excel_driver.append_to_csv(
                            self.csv_filename,
                            save_list,
                            self.columns,
                            folder_path=self.folder_path,
                            sub_dir=self.out_dir,
                        )
                    except Exception as inner_e:
                        self.log_signal_func(f"[append_to_csv 실패] {inner_e}")

                if total_len > 0:
                    pro_value = (index / total_len) * 1000000
                    self.progress_signal.emit(self.before_pro_value, pro_value)
                    self.before_pro_value = pro_value

                time.sleep(random.uniform(2, 4))

            self.log_signal_func("✅ main 종료")

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")

        self.log_signal_func("✅ main 종료")
        return True

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(1200)

        self.log_signal_func("✅ stop 완료")

    # 정지
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
                try:
                    self.driver.quit()
                except Exception:
                    pass
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
                lambda d: self._is_ready_state_complete(d)
            )
        except TimeoutException:
            self.log_signal_func("readyState complete 대기 timeout")

    def _is_ready_state_complete(self, driver: Any) -> bool:
        try:
            return driver.execute_script("return document.readyState") == "complete"
        except Exception:
            return False

    def _wait_current_frame_ready(self, timeout_sec: int = 8) -> bool:
        try:
            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )

            WebDriverWait(self.driver, timeout_sec).until(
                lambda d: d.execute_script("return !!document.body")
            )

            return True
        except Exception as e:
            self.log_signal_func(f"frame ready 대기 실패: {e}")
            return False

    def _xpath_literal(self, value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join([f"'{part}'" for part in parts]) + ")"

    def _try_click_elements(self, by: By, selector: str) -> bool:
        try:
            elements = self.driver.find_elements(by, selector)
        except Exception as e:
            self.log_signal_func(f"[selector 실패] {selector} / {e}")
            return False

        if not elements:
            return False

        for idx, element in enumerate(elements, start=1):
            try:
                if not element.is_displayed():
                    continue

                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                    element
                )
                time.sleep(0.3)

                try:
                    element.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", element)

                self.log_signal_func(f"클릭 성공 selector={selector} index={idx}")
                return True

            except Exception as e:
                self.log_signal_func(f"클릭 실패 selector={selector} index={idx} / {e}")
                continue

        return False

    def _click_media_thumb_in_current_frame(self, target_name: str = "매물 대표 이미지 1") -> bool:
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
            if self._try_click_elements(by, selector):
                return True

        return False

    def _click_visible_media_fallback_in_current_frame(self) -> bool:
        try:
            clicked = self.driver.execute_script("""
                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
                        return false;
                    }
                    return r.width > 40 && r.height > 40;
                }

                function scoreImage(img) {
                    const r = img.getBoundingClientRect();
                    const src = (img.currentSrc || img.src || "").toLowerCase();
                    const alt = (img.alt || "").toLowerCase();
                    let score = r.width * r.height;

                    if (alt.includes("매물")) score += 500000;
                    if (alt.includes("대표")) score += 500000;
                    if (alt.includes("사진")) score += 300000;
                    if (src.includes("pstatic")) score += 100000;
                    if (src.includes("land")) score += 100000;

                    return score;
                }

                const items = [];

                document.querySelectorAll("img").forEach((img) => {
                    if (!isVisible(img)) return;

                    const src = img.currentSrc || img.src || "";
                    const lower = src.toLowerCase();
                    if (!src) return;
                    if (lower.startsWith("data:image")) return;
                    if (lower.includes("icon")) return;
                    if (lower.includes("logo")) return;
                    if (lower.includes("sprite")) return;

                    const r = img.getBoundingClientRect();
                    if (r.width < 60 || r.height < 60) return;

                    const clickable = img.closest("button, a, [role='button'], [tabindex]") || img;
                    items.push({
                        el: clickable,
                        score: scoreImage(img)
                    });
                });

                items.sort((a, b) => b.score - a.score);

                if (!items.length) return false;

                const target = items[0].el;
                target.scrollIntoView({block: "center", inline: "center"});

                try {
                    target.click();
                    return true;
                } catch (e) {
                    try {
                        target.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true}));
                        return true;
                    } catch (e2) {
                        return false;
                    }
                }
            """)
            return bool(clicked)
        except Exception as e:
            self.log_signal_func(f"fallback 클릭 실패: {e}")
            return False

    def _open_media_popup_any_frame(
            self,
            target_name: str = "매물 대표 이미지 1",
            timeout_sec: int = 12,
    ) -> bool:
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
                        self.log_signal_func(f"[iframe {idx}] 진입")

                        self._wait_current_frame_ready(5)
                        time.sleep(0.8 + (round_idx * 0.3))

                        if self._click_media_thumb_in_current_frame(target_name):
                            self.log_signal_func(f"[iframe {idx}] 썸네일 클릭 성공")
                            time.sleep(1.5)
                            return True

                        if self._click_visible_media_fallback_in_current_frame():
                            self.log_signal_func(f"[iframe {idx}] fallback 클릭 성공")
                            time.sleep(1.5)
                            return True

                        self.log_signal_func(f"[iframe {idx}] 대상 없음")

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

    def _get_today_text(self) -> str:
        try:
            if ZoneInfo is not None:
                now = datetime.now(ZoneInfo("Asia/Seoul"))
            else:
                now = datetime.now()
            return now.strftime("%y.%m.%d")
        except Exception:
            return datetime.now().strftime("%y.%m.%d")

    def _sanitize_filename(self, name: str) -> str:
        text = str(name or "").strip()
        text = re.sub(r'[\\/:*?"<>|]+', "_", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _build_folder_base_name(self, building_name: str, ho: str) -> str:
        today_text = self._get_today_text()
        base_name = f"{building_name} {ho} (N) {today_text}"
        return self._sanitize_filename(base_name)

    def _build_media_file_base_name(self, building_name: str, ho: str, is_video: bool) -> str:
        today_text = self._get_today_text()
        prefix = "(동)" if is_video else ""
        base_name = f"{prefix}{building_name} {ho} (N) {today_text}"
        return self._sanitize_filename(base_name)

    def _make_target_dir(self, building_name: str, ho: str) -> str:
        root_dir = os.path.join(self.folder_path, self.out_dir)
        os.makedirs(root_dir, exist_ok=True)

        folder_base_name = self._build_folder_base_name(building_name, ho)

        candidate = os.path.join(root_dir, folder_base_name)
        if not os.path.exists(candidate):
            os.makedirs(candidate, exist_ok=True)
            return candidate

        index = 1
        while True:
            candidate = os.path.join(root_dir, f"{folder_base_name}({index})")
            if not os.path.exists(candidate):
                os.makedirs(candidate, exist_ok=True)
                return candidate
            index += 1

    def _make_unique_file_path(self, target_dir: str, file_base_name: str, ext: str) -> str:
        ext = str(ext or "").strip()
        if not ext.startswith("."):
            ext = "." + ext

        candidate = os.path.join(target_dir, f"{file_base_name}{ext}")
        if not os.path.exists(candidate):
            return candidate

        index = 1
        while True:
            candidate = os.path.join(target_dir, f"{file_base_name}({index}){ext}")
            if not os.path.exists(candidate):
                return candidate
            index += 1

    def _guess_ext_from_url(self, url: str, default_ext: str = ".bin") -> str:
        try:
            path = urlparse(url).path.lower()
        except Exception:
            return default_ext

        for ext in [
            ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
            ".mp4", ".mov", ".m3u8", ".avi", ".mkv"
        ]:
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

    def _get_browser_user_agent(self) -> str:
        try:
            ua = self.driver.execute_script("return navigator.userAgent")
            return str(ua or "").strip()
        except Exception:
            return ""

    def _build_requests_session_from_driver(self) -> requests.Session:
        session = requests.Session()

        try:
            for cookie in self.driver.get_cookies():
                name = cookie.get("name")
                value = cookie.get("value")
                domain = cookie.get("domain")
                if name and value is not None:
                    session.cookies.set(name, value, domain=domain)
        except Exception as e:
            self.log_signal_func(f"쿠키 세팅 실패: {e}")

        return session

    def _request_media_bytes(self, media_url: str) -> Tuple[bool, bytes, str, str]:
        session = self._build_requests_session_from_driver()
        ua = self._get_browser_user_agent()

        headers = {
            "referer": self.driver.current_url,
            "user-agent": ua,
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
        ok, raw, content_type, msg = self._request_media_bytes(media_url)
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
            except Exception as e:
                self.log_signal_func(f"JPG 변환 실패, 원본 저장 시도: {e}")

        try:
            ext = self._guess_ext_from_content_type(content_type, media_url)
            fallback_path = os.path.splitext(save_path_jpg)[0] + ext

            with open(fallback_path, "wb") as f:
                f.write(raw)

            if ext.lower() == ".jpg":
                return True, fallback_path, ""
            return True, fallback_path, f"JPG 변환 실패 또는 Pillow 미설치로 원본 확장자 저장({ext})"
        except Exception as e:
            return False, "", f"이미지 저장 실패: {e}"

    def _get_popup_state(self) -> Dict[str, Any]:
        try:
            data = self.driver.execute_script("""
                function visibleArea(el) {
                    const r = el.getBoundingClientRect();
                    const w = Math.max(0, Math.min(r.right, window.innerWidth) - Math.max(r.left, 0));
                    const h = Math.max(0, Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0));
                    return w * h;
                }

                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
                        return false;
                    }
                    return r.width > 20 && r.height > 20;
                }

                const results = [];

                document.querySelectorAll("video").forEach((el) => {
                    if (!isVisible(el)) return;

                    let src = el.currentSrc || el.src || "";
                    if (!src) {
                        const s = el.querySelector("source");
                        if (s) src = s.src || "";
                    }

                    if (!src) return;

                    const r = el.getBoundingClientRect();
                    results.push({
                        media_type: "video",
                        media_url: src,
                        area: visibleArea(el),
                        width: r.width,
                        height: r.height,
                        tag: el.tagName.toLowerCase(),
                        className: el.className || "",
                        ariaLabel: el.getAttribute("aria-label") || "",
                        alt: el.getAttribute("alt") || ""
                    });
                });

                document.querySelectorAll("img").forEach((el) => {
                    if (!isVisible(el)) return;

                    const src = el.currentSrc || el.src || "";
                    if (!src) return;

                    const lower = src.toLowerCase();
                    if (lower.startsWith("data:image")) return;
                    if (lower.includes("icon")) return;
                    if (lower.includes("sprite")) return;
                    if (lower.includes("logo")) return;

                    const r = el.getBoundingClientRect();
                    results.push({
                        media_type: "image",
                        media_url: src,
                        area: visibleArea(el),
                        width: r.width,
                        height: r.height,
                        tag: el.tagName.toLowerCase(),
                        className: el.className || "",
                        ariaLabel: el.getAttribute("aria-label") || "",
                        alt: el.getAttribute("alt") || ""
                    });
                });

                results.sort((a, b) => b.area - a.area);
                return results;
            """)
        except Exception as e:
            self.log_signal_func(f"_get_popup_state JS 실패: {e}")
            data = []

        if not data:
            return {
                "media_type": "",
                "media_url": "",
                "fingerprint": "",
                "debug_candidates": [],
            }

        best = data[0]
        best["fingerprint"] = hashlib.md5(
            f"{best.get('media_type', '')}|{best.get('media_url', '')}".encode("utf-8")
        ).hexdigest()
        best["debug_candidates"] = data[:5]
        return best

    def _is_next_disabled(self) -> Optional[bool]:
        try:
            value = self.driver.execute_script("""
                const selectors = [
                    "button[aria-label*='다음']",
                    "button[aria-label*='next' i]",
                    "[role='button'][aria-label*='다음']",
                    "[role='button'][aria-label*='next' i]"
                ];

                for (const sel of selectors) {
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
            return value
        except Exception as e:
            self.log_signal_func(f"_is_next_disabled 실패: {e}")
            return None

    def _click_next(self) -> bool:
        selectors = [
            "button[aria-label*='다음']",
            "button[aria-label*='next' i]",
            "[role='button'][aria-label*='다음']",
            "[role='button'][aria-label*='next' i]",
        ]

        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if not elements:
                    continue

                for idx, btn in enumerate(elements, start=1):
                    try:
                        if not btn.is_displayed():
                            continue

                        disabled = btn.get_attribute("disabled")
                        aria_disabled = btn.get_attribute("aria-disabled")
                        if disabled is not None or str(aria_disabled).lower() == "true":
                            continue

                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                            btn
                        )
                        time.sleep(0.2)

                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)

                        self.log_signal_func(f"다음 버튼 클릭 성공 selector={selector} index={idx}")
                        time.sleep(1.8)
                        return True

                    except Exception:
                        continue
            except Exception:
                pass

        try:
            from selenium.webdriver.common.keys import Keys
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ARROW_RIGHT)
            self.log_signal_func("ArrowRight 이동 성공")
            time.sleep(1.8)
            return True
        except Exception as e:
            self.log_signal_func(f"다음 이동 실패: {e}")
            return False

    def _scan_all_media_current_popup(self, max_steps: int = 40) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_urls = set()
        prev_url = ""
        unchanged_count = 0

        for step in range(max_steps):
            if not self.running:
                return []

            state = self._get_popup_state()

            media_type = str(state.get("media_type") or "")
            media_url = str(state.get("media_url") or "")

            self.log_signal_func("=" * 80)
            self.log_signal_func(f"[STEP] {step + 1}")
            self.log_signal_func(f"media_type : {media_type}")
            self.log_signal_func(f"media_url  : {media_url}")

            if not media_url:
                self.log_signal_func("현재 팝업에서 media_url을 찾지 못했습니다.")
            else:
                if media_url not in seen_urls:
                    seen_urls.add(media_url)
                    results.append({
                        "seq": len(results) + 1,
                        "media_type": media_type,
                        "media_url": media_url,
                    })

            if media_url and media_url == prev_url:
                unchanged_count += 1
            else:
                unchanged_count = 0

            if unchanged_count >= 1:
                self.log_signal_func("같은 media_url 반복 -> 마지막으로 판단")
                break

            prev_url = media_url

            next_disabled = self._is_next_disabled()
            if next_disabled is True:
                self.log_signal_func("다음 버튼 비활성화 -> 마지막으로 판단")
                break

            moved = self._click_next()
            if not moved:
                self.log_signal_func("다음 이동 실패")
                break

            next_state = self._get_popup_state()
            next_url = str(next_state.get("media_url") or "")
            if media_url and next_url and media_url == next_url:
                self.log_signal_func("다음으로 이동했지만 media_url 변화 없음 -> 마지막으로 판단")
                break

        return results

    def _append_result_row(
            self,
            data: Dict[str, Any],
            atcl_no: str,
            seq: Any,
            media_type_text: str,
            media_url: str,
            saved_path: str,
            status: str,
            message: str,
    ) -> None:
        save_list = [{
            "건물명": str(data.get("건물명") or ""),
            "호수": str(data.get("호수") or ""),
            "네이버부동산": str(atcl_no or ""),
            "미디어 번호": seq,
            "유형": media_type_text,
            "URL": str(media_url or ""),
            "저장경로": str(saved_path or ""),
            "상태": str(status or ""),
            "메세지": str(message or ""),
        }]

        self.excel_driver.append_to_csv(
            self.csv_filename,
            save_list,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def _download_and_append_result_rows(
            self,
            data: Dict[str, Any],
            atcl_no: str,
            media_items: List[Dict[str, Any]],
    ) -> None:
        building_name = str(data.get("건물명") or "").strip()
        ho = str(data.get("호수") or "").strip()

        image_items = [x for x in media_items if str(x.get("media_type") or "") == "image"]
        image_count = len(image_items)

        if image_count <= 8:
            msg = f"사진 {image_count}장으로 8장 이하라 다운로드 스킵"
            self.log_signal_func(msg)
            self._append_result_row(
                data=data,
                atcl_no=atcl_no,
                seq="",
                media_type_text="",
                media_url="",
                saved_path="",
                status="skip",
                message=msg,
            )
            return

        target_dir = self._make_target_dir(building_name, ho)
        self.log_signal_func(f"저장 폴더: {target_dir}")

        for idx, item in enumerate(media_items, start=1):
            media_type = str(item.get("media_type") or "")
            media_url = str(item.get("media_url") or "")

            if not media_url:
                self._append_result_row(
                    data=data,
                    atcl_no=atcl_no,
                    seq=idx,
                    media_type_text="동영상" if media_type == "video" else "사진",
                    media_url="",
                    saved_path="",
                    status="fail",
                    message="media_url 없음",
                )
                continue

            if media_type == "video":
                file_base_name = self._build_media_file_base_name(
                    building_name=building_name,
                    ho=ho,
                    is_video=True,
                )
                save_path = self._make_unique_file_path(target_dir, file_base_name, ".mp4")

                ok, final_path, msg = self._save_video_file(media_url, save_path)

                self._append_result_row(
                    data=data,
                    atcl_no=atcl_no,
                    seq=idx,
                    media_type_text="동영상",
                    media_url=media_url,
                    saved_path=final_path if ok else "",
                    status="success" if ok else "fail",
                    message=msg if msg else ("저장 완료" if ok else "저장 실패"),
                )
                continue

            file_base_name = self._build_media_file_base_name(
                building_name=building_name,
                ho=ho,
                is_video=False,
            )
            save_path = self._make_unique_file_path(target_dir, file_base_name, ".jpg")

            ok, final_path, msg = self._save_image_file_as_jpg(media_url, save_path)

            self._append_result_row(
                data=data,
                atcl_no=atcl_no,
                seq=idx,
                media_type_text="사진",
                media_url=media_url,
                saved_path=final_path if ok else "",
                status="success" if ok else "fail",
                message=msg if msg else ("저장 완료" if ok else "저장 실패"),
            )