# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
import json
import re
import random
import threading
import wave
import pyperclip
import pyautogui
import whisper
import pyaudiowpatch as pyaudio
from typing import Optional, List, Dict, Any

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

    # =========================================================
    # lifecycle
    # =========================================================
    def init(self) -> bool:
        try:
            if getattr(sys, 'frozen', False):
                root_path = sys._MEIPASS
            else:
                root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

            ffmpeg_path = os.path.join(root_path, 'resources', 'bin')

            if os.path.exists(ffmpeg_path):
                os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]
                self.log_signal_func(f"✅ 환경 변수 설정 완료")
            else:
                self.log_signal_func(f"⚠️ FFmpeg 경로 없음: {ffmpeg_path}")

            pyautogui.PAUSE = 0.4
            pyautogui.FAILSAFE = True

            self.excel_driver = ExcelUtils(self.log_signal_func)
            self.file_driver = FileUtils(self.log_signal_func)

            if self.model is None:
                self.log_signal_func("🤖 Whisper AI 모델 로딩 중...")
                self.model = whisper.load_model("small")
                self.log_signal_func("✅ Whisper AI 로드 완료")

            return True
        except Exception as e:
            self.log_signal_func(f"❌ 초기화 에러: {e}")
            return False

    def stop(self) -> None:
        self.running = False
        self.log_signal_func("🛑 중지 요청됨. 현재 작업을 마치고 종료합니다.")
        self.destroy()


    def destroy(self) -> None:

        if self.csv_filename and os.path.exists(self.csv_filename):
            self.excel_driver.convert_csv_to_excel_and_delete(self.csv_filename)
            self.log_signal_func("✅ 수집 및 엑셀 변환 완료")

        self.progress_signal.emit(0.0, 1000000)
        self.log_signal_func("크롤링 종료 중...")
        time.sleep(1.5)
        self.progress_end_signal.emit()

    # =========================================================
    # main (수집 실행 로직)
    # =========================================================
    def main(self) -> bool:
        keywords_str = self.get_setting_value(self.setting, "keyword") or ""
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        start_p = int(self.get_setting_value(self.setting, "start_page") or 1)
        end_p = int(self.get_setting_value(self.setting, "end_page") or 1)

        if not keywords:
            self.log_signal_func("❌ 키워드가 없습니다.")
            return False

        pages_per_keyword = (end_p - start_p + 1)
        self.total_cnt = len(keywords) * pages_per_keyword
        self.current_cnt = 0
        self.before_pro_value = 0.0

        self.csv_filename = self.file_driver.get_csv_filename(self.site_name)
        self.excel_driver.init_csv(self.csv_filename, self.columns)

        pyautogui.hotkey('win', 'r')
        time.sleep(0.5)
        pyautogui.write('chrome')
        pyautogui.press('enter')
        time.sleep(3)

        for kw in keywords:
            if not self.running:
                break

            for page in range(start_p, end_p + 1):
                if not self.running:
                    break

                target_url = (
                    f"https://msearch.shopping.naver.com/search/all?"
                    f"adQuery={kw}&"
                    f"npayType=2&"
                    f"origQuery={kw}&"
                    f"pagingIndex={page}&"
                    f"pagingSize=40&"
                    f"productSet=checkout&"
                    f"query={kw}&"
                    f"sort=rel&"
                    f"viewType=list"
                )

                items = []
                for retry in range(1, 4):
                    if not self.running:
                        break

                    pyautogui.hotkey('ctrl', 'l')
                    pyperclip.copy(target_url)
                    pyautogui.hotkey('ctrl', 'v')
                    pyautogui.press('enter')

                    time.sleep(random.uniform(4.0, 5.5))

                    captcha_result = self.handle_captcha_with_retry()
                    if captcha_result == 0:  # 0은 5회 시도 모두 실패 또는 중단 시 반환값
                        self.log_signal_func("❌ 캡차 해결 실패: 작업을 중단합니다.")
                        return True  # 작업 실패로 종료

                    pyautogui.hotkey('ctrl', 'u')
                    time.sleep(random.uniform(3, 4))

                    pyautogui.hotkey('ctrl', 'a')
                    pyautogui.hotkey('ctrl', 'c')
                    time.sleep(1.5)
                    pyautogui.hotkey('ctrl', 'w')

                    html_source = pyperclip.paste()
                    items = self.extract_items_from_html(html_source)

                    if items:
                        break
                    else:
                        time.sleep(random.uniform(2.0, 3.5))

                if not items:
                    self.current_cnt += 1
                    continue

                page_results = []
                for i, item_data in enumerate(items):
                    if not self.running:
                        break

                    item = item_data.get("item", {})
                    pc_url = item.get("mallPcUrl")

                    if pc_url:
                        self.log_signal_func(f"🔗 [{kw} - {page}p - {i+1}/{len(items)}] 상세 이동")

                        pyautogui.hotkey('ctrl', 'l')
                        pyperclip.copy(pc_url)
                        pyautogui.hotkey('ctrl', 'v')
                        pyautogui.press('enter')

                        time.sleep(random.uniform(3.5, 5.0))

                        pyautogui.scroll(random.randint(-600, -300))
                        time.sleep(random.uniform(0.5, 1.0))
                        pyautogui.scroll(random.randint(300, 600))

                        if self.handle_captcha_with_retry() == 2:
                            pyautogui.hotkey('ctrl', 'l')
                            pyperclip.copy(pc_url)
                            pyautogui.hotkey('ctrl', 'v')
                            pyautogui.press('enter')
                            time.sleep(random.uniform(3.0, 4.5))

                        pyautogui.hotkey('ctrl', 'a')
                        time.sleep(random.uniform(0.8, 1.2))
                        pyautogui.hotkey('ctrl', 'c')
                        time.sleep(0.6)

                        detail_text = pyperclip.paste()
                        total_visit = "0"
                        v_match = re.search(r'전체\s*([\d,]+)', detail_text)

                        if v_match:
                            total_visit = v_match.group(1).replace(",", "")

                        page_results.append({
                            "keyword": kw,
                            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "page": page,
                            "product_name": item.get("productName"),
                            "product_no": item.get("id"),
                            "sale_price": item.get("price"),
                            "delivery_fee": item.get("dlvryPrice"),
                            "review_count": item.get("reviewCount"),
                            "purchase_count": item.get("purchaseCnt"),
                            "wish_count": item.get("keepCnt"),
                            "store_name": item.get("mallName"),
                            "mobile_url": item.get("mallProdMblUrl"),
                            "pc_url": pc_url,
                            "total_visit_count": total_visit,
                            "no": i+1
                        })
                        self.log_signal_func(f"📦 [수집 완료] {kw} - {page}p  {i+1}번 상품 | {item.get('mallName')} | 방문자수: {total_visit}")
                        time.sleep(random.uniform(1.0, 2.5))

                if page_results:
                    self.excel_driver.append_to_csv(self.csv_filename, page_results, self.columns)

                self.current_cnt += 1
                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                self.log_signal_func(f"📊 수집 완료: {kw} - {page}p ({self.current_cnt}/{self.total_cnt})")

        return True

    # =========================================================
    # 캡차 해결 로직
    # =========================================================
    def record_audio(self, filename, duration=17):
        p = pyaudio.PyAudio()
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            if not default_speakers["isLoopbackDevice"]:
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            wave_format = pyaudio.paInt16
            channels = default_speakers["maxInputChannels"]
            rate = int(default_speakers["defaultSampleRate"])

            stream = p.open(
                format=wave_format,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=default_speakers["index"]
            )

            frames = [stream.read(1024) for _ in range(0, int(rate / 1024 * duration))]

            stream.stop_stream()
            stream.close()

            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(wave_format))
                wf.setframerate(rate)
                wf.writeframes(b''.join(frames))
            return True
        except Exception:
            return False
        finally:
            p.terminate()

    # =========================================================
    # 캡차 AI 처리
    # =========================================================
    def handle_captcha_with_retry(self):
        max_tries = 5
        for attempt in range(1, max_tries + 1):
            if not self.running:
                return 0

            self.log_signal_func(f"🔍 [시도 {attempt}/{max_tries}] 화면 상태 체크 중...")

            if attempt > 1:
                pyautogui.press('tab')
                time.sleep(0.5)

            pyperclip.copy("")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(random.uniform(0.6, 0.9))
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(random.uniform(0.5, 0.8))

            page_content = pyperclip.paste()
            target_text = "보안 확인을 완료해 주세요"

            if target_text not in page_content:
                if attempt == 1:
                    return 1
                else:
                    self.log_signal_func("✅ 캡차 해결 성공!")
                    return 2

            self.log_signal_func("🚩 캡차 발견! 해결을 시작합니다.")

            if attempt == 1:
                for _ in range(5):
                    pyautogui.press('tab')
                    time.sleep(random.uniform(0.1, 0.2))
                pyautogui.press('enter')
            else:
                pyautogui.press('enter')

            time.sleep(2)

            filename = "captcha_audio_final.wav"
            if self.record_audio(filename, duration=17):
                result = self.model.transcribe(filename, language="ko", fp16=False)
                code = "".join(filter(str.isdigit, result['text']))[:6]
                self.log_signal_func(f"📝 AI 인식 코드: {code}")

                if attempt == 1:
                    pyautogui.press('tab')
                    time.sleep(0.5)
                else:
                    pyautogui.hotkey('shift', 'tab')
                    time.sleep(0.5)

                pyautogui.write(code, interval=random.uniform(0.1, 0.2))

                for _ in range(3):
                    pyautogui.press('tab')

                pyautogui.press('enter')

                self.log_signal_func("⏳ 결과 검증 대기 중...")
                time.sleep(random.uniform(5.0, 6))

        return 0

    # =========================================================
    # JSON 파싱
    # =========================================================
    def extract_items_from_html(self, html_source):
        try:
            pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
            match = re.search(pattern, html_source, re.DOTALL)
            if not match:
                return []
            json_data = json.loads(match.group(1))
            props = json_data.get("props", {}).get("pageProps", {})
            return props.get("compositeProducts", {}).get("list", []) or \
                props.get("initialState", {}).get("products", {}).get("list", [])
        except:
            return []