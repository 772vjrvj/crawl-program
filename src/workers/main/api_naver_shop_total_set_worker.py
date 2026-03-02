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


    def destroy(self) -> None:

        if self.csv_filename and os.path.exists(self.csv_filename):
            self.excel_driver.convert_csv_to_excel_and_delete(self.csv_filename)
            self.log_signal_func("✅ 수집 및 엑셀 변환 완료")

        self.progress_signal.emit(self.before_pro_value, 1000000)
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

        # 진행률 계산 설정
        total_pages = (end_p - start_p + 1)
        self.total_cnt = len(keywords) * total_pages
        self.current_cnt = 0
        self.before_pro_value = 0.0

        self.csv_filename = self.file_driver.get_csv_filename(self.site_name)
        self.excel_driver.init_csv(self.csv_filename, self.columns)

        for kw in keywords:
            if not self.running: break

            # 페이지 번호를 10개씩 묶어서 처리
            all_pages = list(range(start_p, end_p + 1))
            chunk_size = 10

            for i in range(0, len(all_pages), chunk_size):
                if not self.running: break

                # --- [NEW] 10페이지 묶음 시작 시 브라우저 새로 실행 ---
                self.log_signal_func(f"🌐 새 브라우저 세션을 시작합니다. (Chunk 시작)")
                pyautogui.hotkey('win', 'r')
                time.sleep(0.5)
                pyautogui.write('chrome')
                pyautogui.press('enter')
                time.sleep(3) # 브라우저 로딩 대기

                current_chunk = all_pages[i : i + chunk_size]
                chunk_items_queue = [] # 10페이지 분량의 아이템을 담을 리스트

                # --- [STEP 1] 리스트 수집 구간 (10페이지) ---
                self.log_signal_func(f"📂 [{kw}] {current_chunk[0]}p ~ {current_chunk[-1]}p 리스트 확보 중...")

                for page in current_chunk:
                    if not self.running: break

                    target_url = (
                        f"https://msearch.shopping.naver.com/search/all?"
                        f"adQuery={kw}&npayType=2&origQuery={kw}&"
                        f"pagingIndex={page}&pagingSize=40&productSet=checkout&"
                        f"query={kw}&sort=rel&viewType=list"
                    )

                    for retry in range(1, 4):
                        if not self.running: break
                        pyautogui.hotkey('ctrl', 'l')
                        time.sleep(random.uniform(0.2, 0.5))
                        pyperclip.copy(target_url)
                        pyautogui.hotkey('ctrl', 'v')
                        pyautogui.press('enter')
                        time.sleep(random.uniform(4.0, 5.5))

                        if self.handle_captcha_with_retry() == 0:
                            self.log_signal_func("❌ 캡차 해결 실패: 작업을 중단하고 브라우저를 닫습니다.")
                            pyautogui.hotkey('alt', 'f4') # 캡차 실패 시에도 브라우저 닫기
                            return True

                        pyautogui.hotkey('ctrl', 'u')
                        time.sleep(random.uniform(3, 4))
                        pyautogui.hotkey('ctrl', 'a')
                        pyautogui.hotkey('ctrl', 'c')
                        time.sleep(1.5)
                        pyautogui.hotkey('ctrl', 'w')

                        extracted = self.extract_items_from_html(pyperclip.paste())
                        if extracted:
                            for item in extracted:
                                item['_page_num'] = page
                            chunk_items_queue.extend(extracted)
                            self.log_signal_func(f"📄 {page}페이지 수집 완료: 상품 {len(extracted)}개 확보")
                            break
                        else:
                            time.sleep(random.uniform(2.0, 3.5))

                # --- [STEP 2] 상세 페이지 수집 구간 ---
                if chunk_items_queue:
                    self.log_signal_func(f"🚀 확보된 {len(chunk_items_queue)}개 상품 상세 수집 시작...")
                    chunk_results = []

                    for idx, item_data in enumerate(chunk_items_queue):
                        if not self.running: break

                        if idx > 2: break

                        item = item_data.get("item", {})
                        pc_url = item.get("mallPcUrl")
                        p_num = item_data.get("_page_num")

                        if pc_url:
                            self.log_signal_func(f"🔗 [{kw}] {p_num}p - {idx+1}/{len(chunk_items_queue)} 상세 이동")
                            pyautogui.hotkey('ctrl', 'l'); pyperclip.copy(pc_url); pyautogui.hotkey('ctrl', 'v'); pyautogui.press('enter')
                            time.sleep(random.uniform(3.5, 5.0))

                            pyautogui.scroll(random.randint(-600, -300))
                            time.sleep(random.uniform(0.5, 1.0))
                            pyautogui.scroll(random.randint(300, 600))

                            if self.handle_captcha_with_retry() == 2:
                                pyautogui.hotkey('ctrl', 'l'); pyperclip.copy(pc_url); pyautogui.hotkey('ctrl', 'v'); pyautogui.press('enter')
                                time.sleep(random.uniform(3.0, 4.5))

                            pyautogui.hotkey('ctrl', 'a'); time.sleep(random.uniform(0.8, 1.2)); pyautogui.hotkey('ctrl', 'c'); time.sleep(0.6)

                            detail_text = pyperclip.paste()
                            total_visit = "0"
                            v_match = re.search(r'전체\s*([\d,]+)', detail_text)
                            if v_match:
                                total_visit = v_match.group(1).replace(",", "")

                                chunk_results.append({
                                    "키워드": kw,
                                    "수집일시": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "상품명": item.get("productName"),
                                    "상품번호": item.get("id"),
                                    "판매가격": item.get("price"),
                                    "배송비": item.get("dlvryPrice"),
                                    "리뷰수": item.get("reviewCount"),
                                    "구매건수": item.get("purchaseCnt"),
                                    "찜하기수": item.get("keepCnt"),
                                    "스토어명": item.get("mallName"),
                                    "모바일주소": item.get("mallProdMblUrl"),
                                    "PC주소": pc_url,
                                    "전체방문자수": total_visit,
                                    "페이지": p_num,
                                    "번호": idx + 1
                                })

                            self.log_signal_func(f"📦 [수집 완료] {kw} - {p_num}p | {item.get('mallName')} | 방문자: {total_visit}")
                            time.sleep(random.uniform(1.0, 2.5))

                    if chunk_results:
                        self.excel_driver.append_to_csv(self.csv_filename, chunk_results, self.columns)

                # --- [STEP 3] 10페이지 묶음 종료 후 브라우저 닫기 및 진행률 업데이트 ---
                self.log_signal_func(f"🧹 묶음 작업 완료. 브라우저를 정리합니다.")
                pyautogui.hotkey('alt', 'f4') # 현재 브라우저 종료
                time.sleep(2) # 안정성을 위한 대기

                self.current_cnt += len(current_chunk)
                pro_value = (self.current_cnt / self.total_cnt) * 1000000
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                self.log_signal_func(f"📊 {current_chunk[-1]}p 묶음 처리 완료 ({self.current_cnt}/{self.total_cnt})")

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
                # 숫자만 추출
                code = "".join(filter(str.isdigit, result['text']))[:6]

                # [추가] AI가 숫자를 하나도 못 찾았을 경우 처리
                if not code:
                    code = "123456"
                    self.log_signal_func("⚠️ AI 인식 실패 (숫자 없음). 기본값 '123456'을 입력하여 화면을 갱신합니다.")
                else:
                    self.log_signal_func(f"📝 AI 인식 코드: {code}")

                # 입력창 포커스 이동 (시도 횟수에 따른 분기)
                if attempt == 1:
                    pyautogui.press('tab')
                    time.sleep(0.5)
                else:
                    pyautogui.hotkey('shift', 'tab')
                    time.sleep(0.5)

                # 코드 타이핑
                pyautogui.write(code, interval=random.uniform(0.1, 0.2))

                # 확인 버튼으로 이동 (탭 3번) 및 엔터
                for _ in range(3):
                    pyautogui.press('tab')

                pyautogui.press('enter')

                self.log_signal_func("⏳ 결과 검증 대기 중...")
                time.sleep(random.uniform(5.0, 6.0))

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