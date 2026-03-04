import os
import sys
import numpy as np
import pyaudiowpatch as pyaudio
import wave
import pyautogui
import pyperclip
import whisper
import time
import json
import re
import random  # [추가] 랜덤 지연을 위한 모듈

# [1] 환경 설정 및 모델 로드
base_path = os.path.dirname(os.path.abspath(__file__))
ffmpeg_path = os.path.join(base_path, 'bin')
os.environ["PATH"] += os.pathsep + ffmpeg_path

pyautogui.PAUSE = 0.4
pyautogui.FAILSAFE = True

print("🤖 Whisper AI 모델 로딩 중...")
model = whisper.load_model("small")

# [2] 데이터 파싱용 함수
def extract_items_from_html(html_source):
    try:
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, html_source, re.DOTALL)
        if not match: return []
        json_data = json.loads(match.group(1))
        props = json_data.get("props", {}).get("pageProps", {})
        items = props.get("compositeProducts", {}).get("list", []) or \
                props.get("initialState", {}).get("products", {}).get("list", [])
        return items
    except Exception as e:
        print(f"⚠️ 파싱 에러: {e}")
        return []

# [3] 녹음 함수
def record_internal_audio_success(filename, duration=17):
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
        stream = p.open(format=wave_format, channels=channels, rate=rate,
                        input=True, input_device_index=default_speakers["index"])
        print(f"🔴 녹음 중... ({duration}초)")
        frames = [stream.read(1024) for _ in range(0, int(rate / 1024 * duration))]
        stream.stop_stream(); stream.close()
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(wave_format))
            wf.setframerate(rate)
            wf.writeframes(b''.join(frames))
        return True
    except Exception as e:
        print(f"❌ 녹음 실패: {e}"); return True
    finally: p.terminate()


# [4] 캡차 해결 모듈
def handle_captcha_with_retry():
    max_tries = 5
    for attempt in range(1, max_tries + 1):
        print(f"🔍 [시도 {attempt}/{max_tries}] 화면 상태 체크 중...")

        # [수정] 2번째 시도부터는 체크 전 Tab을 한 번 눌러 포커스 초기화
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
                print("✅ 정상 화면 (캡차 없음)")
                return 1
            else:
                print("✅ 캡차 해결 성공 후 정상 진입 확인!")
                return 2

        print(f"🚩 캡차 발견! 해결을 시작합니다.")
        pyautogui.press('esc')
        time.sleep(0.5)

        # --- [음성 실행 로직] ---
        if attempt == 1:
            for _ in range(5):
                pyautogui.press('tab')
                time.sleep(random.uniform(0.1, 0.2))
            pyautogui.press('enter')
        else:
            # 2회차 이상: 이미 위에서 Tab을 한 번 했으므로 바로 Enter로 리프레시
            pyautogui.press('enter')

        time.sleep(2)

        # [녹음 및 AI 인식]
        filename = "captcha_audio_final.wav"
        record_internal_audio_success(filename, duration=17)
        result = model.transcribe(filename, language="ko", fp16=False)
        code = "".join(filter(str.isdigit, result['text']))[:6]
        print(f"📝 AI 인식 코드: {code}")

        # --- [코드 입력창 이동 로직: 시도 횟수에 따라 분기] ---
        if attempt == 1:
            # 첫 번째 시도 시: 기존 방식대로 Tab 이동
            pyautogui.press('tab')
            time.sleep(0.5)
        else:
            # 2번째 시도부터: 음성/리프레시 버튼에서 코드 입력창으로 역행 이동 (Shift+Tab)
            pyautogui.hotkey('shift', 'tab')
            time.sleep(0.5)

        # [공통] 코드 타이핑
        pyautogui.write(code, interval=random.uniform(0.1, 0.2))

        # [공통] 확인 버튼으로 이동 (탭 3번) 및 엔터
        for _ in range(3):
            pyautogui.press('tab')
        pyautogui.press('enter')

        print("⏳ 결과 검증 대기 중...")
        time.sleep(random.uniform(5.0, 6.0))

    print(f"⛔ {max_tries}회 연속 실패. 프로그램을 종료합니다.")
    sys.exit()


# [5] 메인 실행 로직
# [5] 메인 실행 로직
def run_naver_macro(keywords, startPage, endPage):
    # 브라우저 최초 실행 (한 번만 실행)
    pyautogui.hotkey('win', 'r')
    pyautogui.write('chrome')
    pyautogui.press('enter')
    time.sleep(2)

    total_final_results = []

    # [수정] 키워드 리스트를 순회하는 최상위 루프 추가
    for keyword in keywords:
        print(f"\n{'='*50}")
        print(f"🚀 [키워드 시작] 현재 키워드: {keyword}")
        print(f"{'='*50}")

        for current_page in range(startPage, endPage + 1):
            print(f"\n--- 📂 {keyword} / 현재 {current_page} 페이지 진행 중 ---")
            target_url = (f"https://msearch.shopping.naver.com/search/all?"
                          f"adQuery={keyword}&npayType=2&origQuery={keyword}&"
                          f"pagingIndex={current_page}&pagingSize=40&productSet=checkout&"
                          f"query={keyword}&sort=rel&viewType=list")

            items = []
            max_extract_retries = 3

            for extract_attempt in range(1, max_extract_retries + 1):
                pyautogui.hotkey('ctrl', 'l')
                pyperclip.copy(target_url)
                pyautogui.hotkey('ctrl', 'v')
                pyautogui.press('enter')
                time.sleep(random.uniform(4.0, 5.5))

                handle_captcha_with_retry()

                print(f"📄 {current_page}p 상품 목록 추출 중... (시도 {extract_attempt}/{max_extract_retries})")
                pyautogui.hotkey('ctrl', 'u')
                time.sleep(random.uniform(3.0, 4.0))
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.5)
                pyautogui.hotkey('ctrl', 'w')

                html_source = pyperclip.paste()
                items = extract_items_from_html(html_source)

                if items:
                    print(f"✅ {len(items)}개의 상품을 성공적으로 확보했습니다.")
                    break
                else:
                    print(f"⚠️ {current_page}p 데이터 없음. 재시도 중...")
                    time.sleep(random.uniform(2.0, 3.5))

            if not items:
                print(f"⛔ {current_page}p 최종 추출 실패. 다음 키워드 혹은 페이지로 넘어갑니다.")
                break

            # 상세 페이지 루프
            for i, item_data in enumerate(items):
                item = item_data.get("item", {})
                refined_item = {
                    "키워드": keyword, # 키워드 정보 추가
                    "수집일시": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "페이지": current_page,
                    "상품명": item.get("productName"),
                    "상품번호": item.get("id"),
                    "판매가격": item.get("price"),
                    "배송비": item.get("dlvryPrice"),
                    "리뷰수": item.get("reviewCount"),
                    "구매건수": item.get("purchaseCnt"),
                    "찜하기수": item.get("keepCnt"),
                    "스토어명": item.get("mallName"),
                    "모바일주소": item.get("mallProdMblUrl"),
                    "PC주소": item.get("mallPcUrl"),
                    "전체방문자수": "0"
                }

                pc_url = refined_item.get("PC주소")
                if pc_url:
                    print(f"🔗 [{keyword} - {current_page}p - {i+1}/{len(items)}] 상세 이동: {pc_url}")
                    pyautogui.hotkey('ctrl', 'l'); pyperclip.copy(pc_url); pyautogui.hotkey('ctrl', 'v'); pyautogui.press('enter')

                    time.sleep(random.uniform(3.5, 5.0))
                    pyautogui.scroll(random.randint(-600, -300))
                    time.sleep(random.uniform(0.5, 1.0))
                    pyautogui.scroll(random.randint(300, 600))

                    if handle_captcha_with_retry() == 2:
                        pyautogui.hotkey('ctrl', 'l'); pyperclip.copy(pc_url); pyautogui.hotkey('ctrl', 'v'); pyautogui.press('enter')
                        time.sleep(random.uniform(3.0, 4.5))

                    pyautogui.hotkey('ctrl', 'a'); time.sleep(random.uniform(0.8, 1.2)); pyautogui.hotkey('ctrl', 'c'); time.sleep(0.6)

                    detail_text = pyperclip.paste()
                    visitor_match = re.search(r'전체\s*([\d,]+)', detail_text)
                    if visitor_match:
                        today_val = visitor_match.group(1).replace(",", "")
                        refined_item["전체방문자수"] = today_val
                        print(f"📈 추출 성공: {today_val}")

                total_final_results.append(refined_item)
                time.sleep(random.uniform(1.0, 2.5))

        print(f"✨ 키워드 [{keyword}] 수집 완료!")

    print(f"\n💾 전체 키워드 수집 완료! 총 {len(total_final_results)}개 누적됨.")
    # 필요 시 여기서 JSON이나 CSV로 저장하는 로직을 넣으면 좋습니다.


if __name__ == "__main__":
    # 수집하고 싶은 키워드들을 배열로 입력하세요.
    target_keywords = ["풋살화", "축구화", "골프화"]
    start_p = 1
    end_p = 3 # 테스트를 위해 범위를 좁혀두었습니다. 필요시 50으로 수정하세요.

    run_naver_macro(target_keywords, start_p, end_p)