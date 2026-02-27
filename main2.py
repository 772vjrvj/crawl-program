# -*- coding: utf-8 -*-
import os, sys, json, random, time, re
from pathlib import Path
from urllib.parse import quote

# [1] 환경 설정
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(BASE_PATH, "bin")
if os.path.exists(FFMPEG_DIR):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]

import whisper
from playwright.sync_api import sync_playwright
from pydub import AudioSegment

# FFmpeg 경로 확정
ffmpeg_exe = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
AudioSegment.converter = ffmpeg_exe
AudioSegment.ffprobe = os.path.join(FFMPEG_DIR, "ffprobe.exe")

print(f"✅ 환경 설정 완료: {ffmpeg_exe}")
print("🤖 AI 모델(Whisper) 로딩 중... (Small 모델 사용)")
model = whisper.load_model("small")

# ====================================================
# 2. 오디오 분석 엔진
# ====================================================
def solve_audio_captcha(wav_path):
    try:
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000: return ""
        result = model.transcribe(wav_path, language="ko", fp16=False, temperature=0, best_of=5, beam_size=5)
        raw_text = result['text'].replace(" ", "")

        num_map = {
            '영':'0','공':'0','일':'1','하나':'1','이':'2','둘':'2','삼':'3','셋':'3','사':'4','넷':'4',
            '오':'5','다섯':'5','육':'6','여섯':'6','칠':'7','일곱':'7','팔':'8','여덟':'8','구':'9','아홉':'9'
        }
        pattern = "|".join([re.escape(k) for k in num_map.keys()] + [r'\d'])
        found = re.findall(pattern, raw_text)
        code = "".join([num_map.get(item, item) for item in found])

        if len(code) != 6:
            print(f"  ⚠️ 자리수 오류({len(code)}자리): {code}")
            return ""
        return code
    except Exception as e:
        print(f"  ⚠️ 분석 에러: {e}"); return ""

# ====================================================
# 3. 캡차 핸들러
# ====================================================
def handle_captcha_combined(page):
    page.wait_for_timeout(1000)
    cpt = page.locator("div[data-component='cpt_main']")
    if cpt.count() == 0 or not cpt.is_visible(): return False

    print("\n🛡️ 보안 확인 해결 프로세스 시작")
    audio_storage = {"data": None, "new_arrival": False, "catch_time": 0}
    def catch_audio(res):
        if "sound/question" in res.url:
            try:
                audio_storage["data"] = res.body()
                audio_storage["new_arrival"] = True
                audio_storage["catch_time"] = time.time()
                print("  🎵 음성 포착 (17초 대기 시작)")
            except: pass
    page.on("response", catch_audio)

    try:
        for attempt in range(1, 11):
            if not cpt.is_visible(): return True
            audio_storage["new_arrival"] = False
            reload_btn = page.locator("#vcpt_reload")
            if reload_btn.is_visible(): reload_btn.click()
            else: page.locator("#rcpt_swap").click()

            for _ in range(50):
                if audio_storage["new_arrival"]: break
                page.wait_for_timeout(200)

            if audio_storage["new_arrival"]:
                temp_file = f"cpt_{int(time.time())}.wav"
                with open(temp_file, "wb") as f: f.write(audio_storage["data"])
                code = solve_audio_captcha(temp_file)
                if os.path.exists(temp_file): os.remove(temp_file)

                if code:
                    print(f"  📝 분석된 캡차 코드: {code}")
                    elapsed = time.time() - audio_storage["catch_time"]
                    wait_needed = 17.2 - elapsed
                    if wait_needed > 0:
                        print(f"  ⏳ 서버 동기화 대기 ({wait_needed:.1f}초)")
                        page.wait_for_timeout(wait_needed * 1000)

                    print(f"  👉 번호 입력 중: {code}")
                    page.locator("#vcpt_answer").fill(code)
                    page.wait_for_timeout(1500)
                    page.locator("#cpt_confirm").click()
                    page.wait_for_timeout(3000)
                    if not cpt.is_visible():
                        print("  ✅ 캡차 해결 성공!")
                        return True
                print("  ❌ 오답/인식실패: 5초 대기 후 재시도")
                page.wait_for_timeout(5000)
    finally:
        page.remove_listener("response", catch_audio)
    return False

# ====================================================
# 4. 데이터 추출 및 수치 반환
# ====================================================
def get_today_value(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        if "nid.naver.com" in page.url or page.locator("div[data-component='cpt_main']").is_visible():
            if not handle_captcha_combined(page): return None

        page.wait_for_timeout(2000)
        content = page.content()
        val = None
        match = re.search(r'\"visitorCount\":\s*\{\"today\":(\d+)', content)
        if match:
            val = match.group(1)
        else:
            try:
                body_text = page.locator("body").inner_text()
                txt_match = re.search(r'오늘\s*([\d,]+)', body_text)
                if txt_match: val = txt_match.group(1).replace(",", "")
            except: pass
        return val
    except Exception as e:
        print(f"❌ 페이지 에러: {e}")
        return None

# ====================================================
# 5. 실행부 (페이징 및 수집 로직)
# ====================================================
def run(keywords):
    PROFILE_DIR = Path("./naver_crawl_profile")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    final_results = [] # 전체 결과 저장

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), channel="chrome", headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            locale="ko-KR"
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for kw in keywords:
            # 1페이지부터 5페이지까지 반복
            for p_idx in range(1, 6):
                search_url = (f"https://msearch.shopping.naver.com/search/all?"
                              f"adQuery={quote(kw)}&naverPay=true&origQuery={quote(kw)}&"
                              f"pagingIndex={p_idx}&pagingSize=40&productSet=total&"
                              f"query={quote(kw)}&sort=rel&viewType=list")

                print(f"\n🚀 검색어: [{kw}] | 현재 페이지: {p_idx}")
                page.goto(search_url, wait_until="domcontentloaded")
                handle_captcha_combined(page)

                try:
                    page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)
                    json_data = json.loads(page.locator("#__NEXT_DATA__").text_content())

                    props = json_data.get("props", {}).get("pageProps", {})
                    items = []
                    if "compositeProducts" in props:
                        items = props["compositeProducts"].get("list", [])
                    elif "initialState" in props:
                        items = props["initialState"].get("products", {}).get("list", [])

                    print(f"✅ {len(items)}개의 상품을 분석 대상으로 발견했습니다.")
                    for i, item_data in enumerate(items, 1):
                        item = item_data.get("item", {})
                        u = item.get("mallProdMblUrl")
                        p_name = item.get('productName', '상품명 없음')[:20]

                        if u:
                            val = get_today_value(page, u)

                            # [로그 추가] 수치가 있든 없든 현재 진행 상태를 출력합니다.
                            if val and val != "N/A":
                                print(f"🔎 [{p_idx}p-{i}] 오늘 수치: {val} | 상품명: {p_name}...")
                                print(f"🔎 [{p_idx}p-{i}] 오늘 수치 item_data: {item_data}")
                                # 수치가 있는 아이템만 결과 리스트에 담음
                                item['todayVisitor'] = val
                                final_results.append(item)
                            else:
                                # [수정] 수치가 없는 경우에도 현재 위치를 알 수 있도록 로그 출력
                                print(f"⚪ [{p_idx}p-{i}] 수치 없음 | 상품명: {p_name}...")
                                print(f"🔎 [{p_idx}p-{i}] 수치 없음 item_data: {item_data}")

                            # 페이지 간 랜덤 대기 (서버 부하 방지)
                            time.sleep(random.uniform(2.5, 4.5))
                        else:
                            # URL 자체가 없는 경우
                            print(f"➖ [{p_idx}p-{i}] URL 없음 | 상품명: {p_name}...")
                except Exception as e:
                    print(f"❌ 목록 처리 중 에러: {e}")

        ctx.close()

    print(f"\n✨ 수집 완료! 총 {len(final_results)}개의 유효한 데이터를 수집했습니다.")
    return final_results

if __name__ == "__main__":
    results = run(["초콜릿"])
    # 결과 확인을 위해 첫 번째 데이터만 출력해보기
    if results:
        print("\n첫 번째 결과 데이터 샘플:")
        print(json.dumps(results[0], indent=2, ensure_ascii=False))