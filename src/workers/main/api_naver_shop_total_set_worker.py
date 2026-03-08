# src/workers/main/api_naver_shop_total_set_worker.py
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
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverShopTotalSetWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()
        self.site_name: str = "naver_shop"
        self.csv_filename: Optional[str] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.file_driver: Optional[FileUtils] = None
        self.model = None

        self.total_cnt = 0
        self.current_cnt = 0
        self.before_pro_value = 0.0

        # === 신규 === 저장 폴더/하위 폴더 보관
        self.folder_path: str = ""
        self.out_dir: str = "output_naver_shop"

    # =========================================================
    # lifecycle
    # =========================================================
    def init(self) -> bool:
        try:
            if sys.stdout is None:
                sys.stdout = open(os.devnull, "w")

            if getattr(sys, "frozen", False):
                root_path = sys._MEIPASS
            else:
                root_path = os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(os.path.abspath(__file__))
                        )
                    )
                )

            ffmpeg_path = os.path.join(
                root_path,
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
            self.file_driver = FileUtils(self.log_signal_func)

            if self.model is None:
                self.model = get_model()
                self.log_signal_func("✅ Whisper AI (service) 연결 완료")

            return True

        except Exception as e:
            self.log_signal_func(f"❌ 초기화 에러: {e}")
            return False

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    def cleanup(self) -> None:
        # 1. CSV → Excel 변환
        try:
            if self.csv_filename and self.excel_driver:
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir,
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        # 2. Whisper 모델 해제
        self.model = None

        # 3. 캡차 음성파일 삭제
        try:
            if os.path.exists("captcha_audio_final.wav"):
                os.remove("captcha_audio_final.wav")
                self.log_signal_func("✅ [캡차 음성파일] 삭제")
        except Exception:
            pass

        # 4. file driver
        try:
            if self.file_driver and hasattr(self.file_driver, "close"):
                self.file_driver.close()
                self.log_signal_func("✅ [파일] 해재")
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")
        finally:
            self.file_driver = None

        # 5. excel driver
        try:
            if self.excel_driver and hasattr(self.excel_driver, "close"):
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

    # =========================================================
    # main (수집 실행 로직)
    # =========================================================
    def main(self) -> bool:
        keywords_str = self.get_setting_value(self.setting, "keyword") or ""
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        start_p = int(self.get_setting_value(self.setting, "start_page") or 1)
        end_p = int(self.get_setting_value(self.setting, "end_page") or 1)
        site_total_cnt = int(self.get_setting_value(self.setting, "site_total_cnt") or 0)

        # === 신규 === 저장 폴더 설정값 확보
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        if not keywords:
            self.log_signal_func("❌ 키워드가 없습니다.")
            return False

        # 진행률 계산 설정
        total_pages = (end_p - start_p + 1)
        self.total_cnt = len(keywords) * total_pages
        self.current_cnt = 0
        self.before_pro_value = 0.0

        # === 수정 === 파일명은 이름만 보관하고 실제 저장경로는 ExcelUtils 에 맡김
        self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

        self.excel_driver.init_csv(
            self.csv_filename,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

        for kw in keywords:
            if not self.running:
                return True

            all_pages = list(range(start_p, end_p + 1))
            chunk_size = 10

            for i in range(0, len(all_pages), chunk_size):
                if not self.running:
                    return True

                self.log_signal_func("🌐 새 브라우저 세션을 시작합니다. (Chunk 시작)")
                pyautogui.hotkey("win", "r")
                if not self.sleep_s(0.5):
                    return True
                pyautogui.write("chrome")
                pyautogui.press("enter")
                if not self.sleep_s(3):
                    return True

                current_chunk = all_pages[i: i + chunk_size]
                chunk_items_queue = []

                self.log_signal_func(
                    f"📂 [{kw}] {current_chunk[0]}p ~ {current_chunk[-1]}p 리스트 확보 중..."
                )

                for page in current_chunk:
                    if not self.running:
                        return True

                    target_url = (
                        f"https://msearch.shopping.naver.com/search/all?"
                        f"adQuery={kw}&npayType=2&origQuery={kw}&"
                        f"pagingIndex={page}&pagingSize=40&productSet=checkout&"
                        f"query={kw}&sort=rel&viewType=list"
                    )

                    for retry in range(1, 4):
                        if not self.running:
                            return True

                        pyautogui.hotkey("ctrl", "l")
                        if not self.sleep_s(random.uniform(0.2, 0.5)):
                            return True
                        pyperclip.copy(target_url)
                        pyautogui.hotkey("ctrl", "v")
                        pyautogui.press("enter")
                        if not self.sleep_s(random.uniform(4.0, 5.5)):
                            return True

                        if self.handle_captcha_with_retry() == 0:
                            self.log_signal_func("❌ 캡차 해결 실패: 작업을 중단하고 브라우저를 닫습니다.")
                            pyautogui.hotkey("alt", "f4")
                            return True

                        pyautogui.hotkey("ctrl", "u")
                        if not self.sleep_s(random.uniform(3, 4)):
                            return True
                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.hotkey("ctrl", "c")
                        if not self.sleep_s(1.5):
                            return True
                        pyautogui.hotkey("ctrl", "w")

                        extracted = self.extract_items_from_html(pyperclip.paste())
                        if extracted:
                            for item in extracted:
                                item["_page_num"] = page
                            chunk_items_queue.extend(extracted)
                            self.log_signal_func(f"📄 {page}페이지 수집 완료: 상품 {len(extracted)}개 확보")
                            break
                        else:
                            if not self.sleep_s(random.uniform(2.0, 3.5)):
                                return True

                    self.current_cnt += 1

                if chunk_items_queue:
                    self.log_signal_func(f"🚀 확보된 {len(chunk_items_queue)}개 상품 상세 수집 시작...")
                    chunk_results = []

                    for idx, item_data in enumerate(chunk_items_queue):
                        if not self.running:
                            return True

                        item = item_data.get("item", {})
                        pc_url = item.get("mallPcUrl")
                        p_num = item_data.get("_page_num")

                        if pc_url:
                            self.log_signal_func(f"🔗 [{kw}] {p_num}p - {idx + 1}/{len(chunk_items_queue)} 상세 이동")
                            pyautogui.hotkey("ctrl", "l")
                            pyperclip.copy(pc_url)
                            pyautogui.hotkey("ctrl", "v")
                            pyautogui.press("enter")
                            if not self.sleep_s(random.uniform(3.5, 5.0)):
                                return True

                            pyautogui.scroll(random.randint(-600, -300))
                            if not self.sleep_s(random.uniform(0.5, 1.0)):
                                return True
                            pyautogui.scroll(random.randint(300, 600))

                            if self.handle_captcha_with_retry() == 2:
                                pyautogui.hotkey("ctrl", "l")
                                pyperclip.copy(pc_url)
                                pyautogui.hotkey("ctrl", "v")
                                pyautogui.press("enter")
                                if not self.sleep_s(random.uniform(3.0, 4.5)):
                                    return True

                            pyautogui.hotkey("ctrl", "a")
                            if not self.sleep_s(random.uniform(0.8, 1.2)):
                                return True
                            pyautogui.hotkey("ctrl", "c")
                            if not self.sleep_s(0.6):
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
                                        return True

                                    self.excel_driver.append_to_csv(
                                        self.csv_filename,
                                        [rs],
                                        self.columns,
                                        folder_path=self.folder_path,
                                        sub_dir=self.out_dir,
                                    )

                            self.log_signal_func(
                                f"📦 [수집 완료] {kw} - {p_num}p | {item.get('mallName')} | 방문자: {total_visit}"
                            )
                            if not self.sleep_s(random.uniform(1.0, 2.5)):
                                return True

                self.log_signal_func("🧹 묶음 작업 완료. 브라우저를 정리합니다.")
                pyautogui.hotkey("alt", "f4")
                if not self.sleep_s(2):
                    return True

                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                self.log_signal_func(
                    f"📊 {current_chunk[-1]}p 묶음 처리 완료 ({self.current_cnt}/{self.total_cnt})"
                )

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
        max_tries = 5
        for attempt in range(1, max_tries + 1):
            if not self.running:
                return 0

            self.log_signal_func(f"🔍 [시도 {attempt}/{max_tries}] 화면 상태 체크 중...")

            if attempt > 1:
                pyautogui.press("tab")
                if not self.sleep_s(0.5):
                    return 0

            pyperclip.copy("")
            pyautogui.hotkey("ctrl", "a")
            if not self.sleep_s(random.uniform(0.6, 0.9)):
                return 0
            pyautogui.hotkey("ctrl", "c")
            if not self.sleep_s(random.uniform(0.5, 0.8)):
                return 0

            page_content = pyperclip.paste()
            target_text = "보안 확인을 완료해 주세요"

            if target_text not in page_content:
                if attempt == 1:
                    return 1
                self.log_signal_func("✅ 캡차 해결 성공!")
                return 2

            self.log_signal_func("🚩 캡차 발견! 해결을 시작합니다.")

            if attempt == 1:
                for _ in range(5):
                    pyautogui.press("tab")
                    if not self.sleep_s(random.uniform(0.1, 0.2)):
                        return 0
                pyautogui.press("enter")
            else:
                pyautogui.press("enter")

            if not self.sleep_s(2):
                return 0

            filename = "captcha_audio_final.wav"
            if self.record_audio(filename, duration=17):
                result = self.model.transcribe(filename, language="ko", fp16=False)
                code = "".join(filter(str.isdigit, result["text"]))[:6]

                if not code:
                    code = "123456"
                    self.log_signal_func("⚠️ AI 인식 실패 (숫자 없음). 기본값 '123456'을 입력하여 화면을 갱신합니다.")
                else:
                    self.log_signal_func(f"📝 AI 인식 코드: {code}")

                if attempt == 1:
                    pyautogui.press("tab")
                    if not self.sleep_s(0.5):
                        return 0
                else:
                    pyautogui.hotkey("shift", "tab")
                    if not self.sleep_s(0.5):
                        return 0

                pyautogui.write(code, interval=random.uniform(0.1, 0.2))

                for _ in range(3):
                    pyautogui.press("tab")

                pyautogui.press("enter")

                self.log_signal_func("⏳ 결과 검증 대기 중...")
                if not self.sleep_s(random.uniform(5.0, 6.0)):
                    return 0

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