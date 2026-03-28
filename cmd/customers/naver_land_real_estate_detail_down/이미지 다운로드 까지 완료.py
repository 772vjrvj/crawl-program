import asyncio
import hashlib
import json
import os
import re
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from playwright_stealth import Stealth


TARGET_URL = "https://fin.land.naver.com/articles/2615948861"
SAVE_DIR = "output_media"
WAIT_AFTER_GOTO_MS = 4000
WAIT_AFTER_CLICK_MS = 1800
MAX_STEPS = 40


def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()


def guess_ext_from_url(url: str, default_ext: str = ".bin") -> str:
    path = urlparse(url).path.lower()

    for ext in [
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
        ".mp4", ".mov", ".m3u8", ".avi", ".mkv"
    ]:
        if path.endswith(ext):
            return ext

    return default_ext


async def download_file_via_playwright(page, url: str, save_path: str):
    user_agent = await page.evaluate("() => navigator.userAgent")

    headers = {
        "referer": page.url,
        "user-agent": user_agent,
        "accept": "*/*",
    }

    response = await page.context.request.get(
        url,
        headers=headers,
        timeout=30000,
        fail_on_status_code=False,
    )

    if response.status >= 400:
        raise RuntimeError(f"다운로드 실패 status={response.status} url={url}")

    body = await response.body()

    with open(save_path, "wb") as f:
        f.write(body)


async def print_frames(page):
    print("\n[INFO] 현재 frame 목록")
    for i, frame in enumerate(page.frames):
        try:
            print(f"  [{i}] name={frame.name!r} url={frame.url}")
        except Exception as e:
            print(f"  [{i}] frame 출력 실패: {e}")


async def get_element_info(locator):
    return await locator.evaluate("""
    (el) => {
        function cssPath(node) {
            const parts = [];
            while (node && node.nodeType === 1 && parts.length < 8) {
                let part = node.tagName.toLowerCase();

                if (node.id) {
                    part += "#" + node.id;
                    parts.unshift(part);
                    break;
                }

                if (typeof node.className === "string" && node.className.trim()) {
                    const cls = node.className.trim().split(/\\s+/).slice(0, 3).join(".");
                    if (cls) part += "." + cls;
                }

                const parent = node.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children).filter(x => x.tagName === node.tagName);
                    if (siblings.length > 1) {
                        const idx = siblings.indexOf(node) + 1;
                        part += `:nth-of-type(${idx})`;
                    }
                }

                parts.unshift(part);
                node = node.parentElement;
            }
            return parts.join(" > ");
        }

        const attrs = {};
        for (const a of el.attributes) {
            attrs[a.name] = a.value;
        }

        return {
            tag: el.tagName.toLowerCase(),
            id: el.id || "",
            className: typeof el.className === "string" ? el.className : "",
            role: el.getAttribute("role") || "",
            ariaLabel: el.getAttribute("aria-label") || "",
            text: (el.innerText || el.textContent || "").trim(),
            cssPath: cssPath(el),
            attrs: attrs,
            outerHTML: (el.outerHTML || "").slice(0, 1200)
        };
    }
    """)


async def try_open_popup_in_frame(frame, target_name: str):
    candidates = []

    try:
        exact_loc = frame.get_by_role("button", name=target_name, exact=True)
        exact_count = await exact_loc.count()
        for i in range(exact_count):
            candidates.append(exact_loc.nth(i))
    except Exception:
        pass

    if not candidates:
        try:
            partial_loc = frame.get_by_role("button", name=target_name, exact=False)
            partial_count = await partial_loc.count()
            for i in range(partial_count):
                candidates.append(partial_loc.nth(i))
        except Exception:
            pass

    if not candidates:
        return False

    target = candidates[0]
    await target.wait_for(state="attached", timeout=5000)
    await target.scroll_into_view_if_needed()

    info = await get_element_info(target)

    print("\n" + "=" * 100)
    print("[CLICK TARGET INFO]")
    print("=" * 100)
    print(f"frame_url : {frame.url}")
    print(f"tag       : {info['tag']}")
    print(f"id        : {info['id']}")
    print(f"className : {info['className']}")
    print(f"role      : {info['role']}")
    print(f"ariaLabel : {info['ariaLabel']}")
    print(f"text      : {info['text'][:300]}")
    print(f"cssPath   : {info['cssPath']}")
    print(f"attrs     : {info['attrs']}")
    print(f"outerHTML : {info['outerHTML']}")
    print("=" * 100)

    try:
        await target.click(timeout=5000)
        print("[OK] 팝업 열기 일반 클릭 성공")
        return True
    except Exception as e:
        print(f"[WARN] 일반 클릭 실패: {e}")

    try:
        await target.click(force=True, timeout=5000)
        print("[OK] 팝업 열기 force 클릭 성공")
        return True
    except Exception as e:
        print(f"[WARN] force 클릭 실패: {e}")

    try:
        await target.evaluate("(el) => el.click()")
        print("[OK] 팝업 열기 JS 클릭 성공")
        return True
    except Exception as e:
        print(f"[WARN] JS 클릭 실패: {e}")

    return False


async def open_media_popup(page, target_name: str = "매물 대표 이미지 1"):
    await page.wait_for_timeout(3000)
    await print_frames(page)

    for i, frame in enumerate(page.frames):
        try:
            print(f"\n[INFO] frame[{i}] 팝업 열기 시도")
            print(f"       name={frame.name!r}")
            print(f"       url={frame.url}")

            ok = await try_open_popup_in_frame(frame, target_name)
            if ok:
                await page.wait_for_timeout(WAIT_AFTER_CLICK_MS)
                print(f"[OK] frame[{i}] 에서 팝업 열기 완료")
                return True

        except Exception as e:
            print(f"[WARN] frame[{i}] 팝업 열기 실패: {e}")

    return False


async def get_popup_state(page):
    """
    현재 팝업에서 화면에 크게 보이는 media(video/img)를 찾는다.
    가장 큰 visible media를 고르는 방식이라 index selector가 틀려도 비교적 안정적이다.
    """
    data = await page.evaluate("""
    () => {
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

        // video 우선
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

        // img
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
    }
    """)

    if not data:
        return {
            "media_type": "",
            "media_url": "",
            "fingerprint": "",
            "debug_candidates": []
        }

    best = data[0]
    best["fingerprint"] = hashlib.md5(
        f"{best['media_type']}|{best['media_url']}".encode("utf-8")
    ).hexdigest()
    best["debug_candidates"] = data[:5]
    return best


async def is_next_disabled(page):
    js = await page.evaluate("""
    () => {
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
    }
    """)
    return js


async def click_next(page):
    selectors = [
        "button[aria-label*='다음']",
        "button[aria-label*='next' i]",
        "[role='button'][aria-label*='다음']",
        "[role='button'][aria-label*='next' i]",
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            if count == 0:
                continue

            for i in range(count):
                btn = loc.nth(i)
                try:
                    box = await btn.bounding_box()
                    if not box or box["width"] < 10 or box["height"] < 10:
                        continue

                    disabled = await btn.get_attribute("disabled")
                    aria_disabled = await btn.get_attribute("aria-disabled")
                    if disabled is not None or aria_disabled == "true":
                        continue

                    await btn.scroll_into_view_if_needed()
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(WAIT_AFTER_CLICK_MS)
                    print(f"[OK] 다음 버튼 클릭 성공 selector={sel}")
                    return True
                except Exception:
                    continue
        except Exception:
            pass

    # fallback: ArrowRight
    try:
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(WAIT_AFTER_CLICK_MS)
        print("[OK] ArrowRight 이동 성공")
        return True
    except Exception as e:
        print(f"[WARN] ArrowRight 이동 실패: {e}")
        return False


async def collect_all_media(page):
    ensure_dir(SAVE_DIR)

    results = []
    seen_urls = set()
    prev_url = ""
    unchanged_count = 0

    for step in range(MAX_STEPS):
        state = await get_popup_state(page)

        print("\n" + "=" * 100)
        print(f"[STEP] {step + 1}")
        print(f"media_type : {state.get('media_type', '')}")
        print(f"media_url  : {state.get('media_url', '')}")

        debug_candidates = state.get("debug_candidates", [])
        if debug_candidates:
            print("[DEBUG] 상위 후보:")
            for i, item in enumerate(debug_candidates[:3], 1):
                print(
                    f"  {i}. type={item.get('media_type')} "
                    f"area={item.get('area')} "
                    f"size=({int(item.get('width', 0))}x{int(item.get('height', 0))}) "
                    f"url={item.get('media_url', '')[:180]}"
                )

        media_type = state.get("media_type", "")
        media_url = state.get("media_url", "")

        if not media_url:
            print("[WARN] 현재 팝업에서 media_url을 찾지 못했습니다.")
        else:
            if media_url not in seen_urls:
                seen_urls.add(media_url)

                ext = guess_ext_from_url(
                    media_url,
                    ".mp4" if media_type == "video" else ".jpg"
                )
                save_name = sanitize_filename(f"{len(results) + 1:02d}_{media_type}{ext}")
                save_path = os.path.join(SAVE_DIR, save_name)

                try:
                    await download_file_via_playwright(page, media_url, save_path)
                    print(f"[OK] 저장 완료: {save_path}")

                    results.append({
                        "seq": len(results) + 1,
                        "media_type": media_type,
                        "media_url": media_url,
                        "save_path": save_path,
                    })
                except Exception as e:
                    print(f"[WARN] 다운로드 실패: {e}")

        if media_url and media_url == prev_url:
            unchanged_count += 1
        else:
            unchanged_count = 0

        if unchanged_count >= 1:
            print("[END] 같은 media_url 반복 -> 마지막으로 판단")
            break

        prev_url = media_url

        next_disabled = await is_next_disabled(page)
        if next_disabled is True:
            print("[END] 다음 버튼이 비활성화 상태 -> 마지막으로 판단")
            break

        moved = await click_next(page)
        if not moved:
            print("[END] 다음 이동 실패")
            break

        next_state = await get_popup_state(page)
        next_url = next_state.get("media_url", "")

        if media_url and next_url and media_url == next_url:
            print("[END] 다음으로 이동했지만 media_url 변화 없음 -> 마지막으로 판단")
            break

    return results


async def save_metadata(results):
    json_path = os.path.join(SAVE_DIR, "media_list.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[OK] 메타데이터 저장 완료: {json_path}")


async def run():
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=False,
            # channel="chrome",
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
            locale="ko-KR",
            ignore_https_errors=True,
        )

        page = await context.new_page()

        try:
            print(f"[INFO] 접속 시작: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(WAIT_AFTER_GOTO_MS)
            print("[OK] 접속 성공")

            opened = await open_media_popup(page, "매물 대표 이미지 1")
            if not opened:
                print("[FAIL] 팝업을 열지 못했습니다.")
                await page.pause()
                return

            await page.wait_for_timeout(2000)

            results = await collect_all_media(page)
            await save_metadata(results)

            print("\n" + "=" * 100)
            print(f"[DONE] 총 수집 개수: {len(results)}")
            for item in results:
                print(item)

            await page.pause()

        except Exception as e:
            print(f"[ERROR] 오류 발생: {e}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())