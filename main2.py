import os
import sys
import numpy as np
import pyaudiowpatch as pyaudio  # 성공했던 핵심 라이브러리
import wave
import pyautogui
import pyperclip
import whisper
import time
import json
import re

# [1] 환경 설정 및 모델 로드
base_path = os.path.dirname(os.path.abspath(__file__))
ffmpeg_path = os.path.join(base_path, 'bin')
os.environ["PATH"] += os.pathsep + ffmpeg_path

# 모든 동작 사이에 강제 지연 (시스템 꼬임 방지)
pyautogui.PAUSE = 0.4
pyautogui.FAILSAFE = True

print("🤖 Whisper AI 모델 로딩 중...")
model = whisper.load_model("small")

# [추가] 데이터 추출용 파서 (원본 로직 뒤에 붙을 기능)
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
    except: return []

# [2] 아까 성공했던 그 녹음 함수 (PyAudioWPatch 방식) - 원본 유지
def record_internal_audio_success(filename, duration=18):
    """성공했던 로직: WASAPI 루프백 장치를 정밀 타격하여 녹음합니다."""
    p = pyaudio.PyAudio()
    try:
        # 기본 재생 장치의 루프백 인터페이스 찾기
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if not default_speakers["isLoopbackDevice"]:
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break

        print(f"🎙️ [성공로직] 소리 가로채기 장치: {default_speakers['name']}")

        wave_format = pyaudio.paInt16
        channels = default_speakers["maxInputChannels"]
        rate = int(default_speakers["defaultSampleRate"])

        stream = p.open(format=wave_format,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=default_speakers["index"])

        print(f"🔴 녹음 중... ({duration}초)")
        frames = []
        # 버퍼 손실 없이 루프 하나로 녹음
        for _ in range(0, int(rate / 1024 * duration)):
            frames.append(stream.read(1024))

        print("✅ 녹음 끝!")
        stream.stop_stream()
        stream.close()

        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(wave_format))
            wf.setframerate(rate)
            wf.writeframes(b''.join(frames))

        return True
    except Exception as e:
        print(f"❌ 녹음 실패: {e}")
        return False
    finally:
        p.terminate()

# [3] 메인 실행 로직 - 원본 코드 100% 동일 유지
def run_naver_macro():
    # --- STEP 1: 페이지 접속 및 로딩 ---
    print("🚀 1단계: 브라우저 실행 및 접속")
    pyautogui.hotkey('win', 'r')
    pyautogui.write('chrome')
    pyautogui.press('enter')
    time.sleep(2)

    pyautogui.hotkey('ctrl', 'l')
    target_url = "https://msearch.shopping.naver.com/search/all?adQuery=%EC%B4%88%EC%BD%9C%EB%A6%BF&npayType=2&origQuery=%EC%B4%88%EC%BD%9C%EB%A6%BF&pagingIndex=1&pagingSize=40&productSet=checkout&query=%EC%B4%88%EC%BD%9C%EB%A6%BF&sort=rel&timestamp=&viewType=list"
    pyperclip.copy(target_url)
    pyautogui.hotkey('ctrl', 'v')
    pyautogui.press('enter')

    print("⏳ 페이지 로딩 대기 (3초)...")
    time.sleep(3)

    # --- STEP 2: 텍스트 기반 캡차 판독 ---
    print("🔍 캡차 발생 여부 확인 중 (텍스트 스캔)...")
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.5)

    page_content = pyperclip.paste()
    target_text = "보안 확인을 완료해 주세요"

    if target_text in page_content:
        print(f"🚩 캡차 발견! ['{target_text}'] 문구 확인됨.")

        # 캡차 해제를 위해 전체 선택 해제 (화면 중앙 클릭 한 번 권장)
        # 클릭이 어려우면 ESC를 한 번 눌러 선택 영역을 해제합니다.
        pyautogui.press('esc')
        time.sleep(0.5)

        print("🎹 음성 재생 버튼으로 이동 및 클릭 (Tab 5회)")
        for _ in range(5):
            pyautogui.press('tab')
            time.sleep(0.2)

        pyautogui.press('enter')
        time.sleep(2) # 소리 재생 시작 대기

        # 3-2. 검증된 18초 녹음 진행
        filename = "captcha_audio_final.wav"
        if record_internal_audio_success(filename, duration=18):

            # 3-3. 분석 단계 (Whisper 정밀 모드)
            print("🧠 AI 분석 단계 진입...")
            result = model.transcribe(filename, language="ko", fp16=False)

            # 숫자만 추출
            code = "".join(filter(str.isdigit, result['text']))[:6]
            print(f"📝 AI 인식 결과: {result['text']}")
            print(f"🔢 최종 보안코드: {code}")

            if len(code) >= 4:
                # 3-4. 입력창 이동 및 입력
                pyautogui.press('tab')
                time.sleep(0.5)
                pyautogui.write(code, interval=0.15)

                # 확인 버튼 이동 및 엔터 (보통 3회)
                for _ in range(3):
                    pyautogui.press('tab')
                pyautogui.press('enter')
                print("🎉 캡차 해결 시도 완료!")
                time.sleep(5) # 페이지 전환 대기
            else:
                print("❌ 숫자를 인식하지 못했습니다. 오디오 파일을 확인하세요.")
                return # 실패 시 중단
    else:
        print("✅ 정상 스토어 화면 감지 - 크롤링을 시작합니다.")

    # ---------------------------------------------------------
    # [여기서부터 새로 추가되는 크롤링 로직입니다]
    # ---------------------------------------------------------
    print("📄 페이지 소스에서 상품 정보를 추출합니다...")
    pyautogui.hotkey('ctrl', 'u') # 소스 보기
    time.sleep(2)
    pyautogui.hotkey('ctrl', 'a') # 전체 선택
    pyautogui.hotkey('ctrl', 'c') # 복사
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'w') # 소스 탭 닫기

    html_source = pyperclip.paste()
    items = extract_items_from_html(html_source)

    final_results = []
    for i, item_data in enumerate(items):
        item = item_data.get("item", {})
        print(f"{item}")
        refined_item = {
            "수집일시": time.strftime("%Y-%m-%d %H:%M:%S"),
            "상품명": item.get("productName"),
            "상품번호": item.get("id"),
            "판매가격": item.get("price"),
            "배송비": item.get("dlvryPrice"),
            "리뷰수": item.get("reviewCount"),
            "구매건수": item.get("purchaseCnt"),
            "찜하기수": item.get("keepCnt"),
            "스토어명": item.get("mallName"),
            "스토어등급": item.get("mallInfoCache", {}).get("mallGrade", "정보없음"),
            "모바일주소": item.get("mallProdMblUrl"),
            "상품상세주소": item.get("mallProductUrl"),
            "PC주소": item.get("mallPcUrl")
        }

        mb_url = refined_item.get("모바일주소")
        if mb_url:
            print(f"🔗 상세 페이지 접속 중: {mb_url}")
            # 1. 주소창으로 이동하여 PC주소 입력
            pyautogui.hotkey('ctrl', 'l')
            pyperclip.copy(mb_url)
            pyautogui.hotkey('ctrl', 'v')
            pyautogui.press('enter')

            # 2. 로딩 대기 (요청하신 2.5초)
            time.sleep(2.5)

            # 3. 전체 텍스트 복사 (Ctrl+A, Ctrl+C)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.5)

            # 4. 텍스트 분석 및 숫자 추출
            detail_text = pyperclip.paste()
            # 정규표현식 설명: '오늘' 뒤에 오는 숫자와 콤마를 찾습니다.
            visitor_match = re.search(r'오늘\s*([\d,]+)', detail_text)

            if visitor_match:
                # 콤마 제거 후 숫자만 추출
                today_visitor = visitor_match.group(1).replace(",", "")
                refined_item["오늘방문자수"] = today_visitor
                print(f"📈 [추출 성공] {refined_item['상품명'][:10]}... -> 오늘 방문자: {today_visitor}")
            else:
                refined_item["오늘방문자수"] = "0"
                # print(f"⚪ [정보 없음] 방문자수 데이터가 화면에 보이지 않습니다.")

        final_results.append(refined_item)

        # 너무 빠른 접속으로 인한 차단 방지 (선택 사항)
        time.sleep(1)

        final_results.append(refined_item)
    print(f"💾 수집 완료! ")
    print(f"{final_results}")

if __name__ == "__main__":
    run_naver_macro()