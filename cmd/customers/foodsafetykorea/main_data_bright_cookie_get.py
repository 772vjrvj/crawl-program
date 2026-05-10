import asyncio
from playwright.async_api import async_playwright

async def open_browser_for_cookie():
    async with async_playwright() as p:
        # 1. 정보 설정 (국가코드 포함)
        USER = "brd-customer-hl_7b5686a6-zone-foodsafetykorea-country-kr"
        PASS = "5iw55h83jmjv"

        # 포트를 22225로 변경 (가끔 33335보다 빠름)
        PROXY_SERVER = "http://brd.superproxy.io:22225"

        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--ignore-certificate-errors']
        )

        context = await browser.new_context(
            proxy={
                "server": PROXY_SERVER,
                "username": USER,
                "password": PASS
            },
            ignore_https_errors=True
        )

        page = await context.new_page()

        # 봇 감지 우회 스크립트 주입
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print(f"🚀 [{PROXY_SERVER}] 연결 시도 중... (최대 2분 대기)")

        try:
            target_url = "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoCompany.do?menu_grp=MENU_NEW04&menu_no=2813"

            # wait_until="commit" -> 서버가 응답을 보내기 시작하는 순간 멈춤 (로딩 뺑뺑이 무시)
            response = await page.goto(target_url, wait_until="commit", timeout=120000)

            if response:
                print(f"✅ 서버 응답 확인 (상태코드: {response.status})")
                print("화면 로딩이 덜 되었더라도 F12를 눌러보세요.")
            else:
                print("❌ 서버 응답 없음")

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            print("\n💡 만약 타임아웃 에러가 난다면 KYC 인증이 100% 필요합니다.")

        # 브라우저 유지 (강제 종료 전까지)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(open_browser_for_cookie())