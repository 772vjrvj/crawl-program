from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time


def get_lat_lon(keyword: str) -> None:
    target_api = "https://dapi.kakao.com/v2/local/search/address.json"
    captured = {"data": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=300
        )

        context = browser.new_context(
            permissions=["geolocation"],
            geolocation={"latitude": 37.5665, "longitude": 126.9780},
            viewport={"width": 1400, "height": 900}
        )

        page = context.new_page()

        def handle_response(response):
            try:
                if target_api in response.url and response.status == 200:
                    data = response.json()
                    docs = data.get("documents", [])
                    if docs:
                        captured["data"] = data
                        print("Kakao 주소 API 응답 잡음")
            except Exception as e:
                print("response 처리 에러:", e)

        page.on("response", handle_response)

        try:
            page.goto("https://bigdata.sbiz.or.kr/#/hotplace/gis", wait_until="load", timeout=60000)
            page.wait_for_timeout(3000)

            # iframe 내부 접근
            frame = page.frame_locator("#iframe")

            search_input = frame.locator("#searchAddress")
            search_btn = frame.locator("#searchBtn")

            search_input.wait_for(state="visible", timeout=30000)

            search_input.click()
            search_input.fill("")
            search_input.type(keyword, delay=100)
            page.wait_for_timeout(800)

            # 엔터 + 버튼 클릭 둘 다 시도
            try:
                search_input.press("Enter")
            except Exception:
                pass

            try:
                search_btn.click()
            except Exception:
                pass

            # 응답 대기
            for _ in range(40):
                if captured["data"] is not None:
                    break
                time.sleep(0.5)

            if captured["data"] is None:
                print("Kakao 주소 API 응답을 못 잡았습니다.")
                print("현재 URL:", page.url)
                page.screenshot(path="debug_bigdata_timeout.png", full_page=True)
                print("스크린샷 저장: debug_bigdata_timeout.png")
                return

            data = captured["data"]
            first = data["documents"][0]

            lon = first.get("x") or first.get("address", {}).get("x")
            lat = first.get("y") or first.get("address", {}).get("y")

            print(lat)
            print(lon)

        except PlaywrightTimeoutError as e:
            print("타임아웃 발생:", e)
        except Exception as e:
            print("에러 발생:", e)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    get_lat_lon("서울시 강남구 역삼1동")