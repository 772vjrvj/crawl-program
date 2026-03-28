# 브라우저만 열기

import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # 브라우저 실행 (headless=False로 설정해야 눈으로 확인 가능)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # [핵심] 특정 경로(disable-devtool)를 포함하는 네트워크 요청 차단
        # 이 스크립트가 실행되지 않으면 F12 감지 로직 자체가 동작하지 않습니다.
        await page.route("**/disable-devtool*", lambda route: route.abort())

        # 대상 페이지 이동
        url = "https://www.childcare.go.kr/?menuno=166&sido=11000&sidoText=%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C"
        await page.goto(url)

        print("보안 스크립트가 차단되었습니다. 이제 F12를 자유롭게 누르거나 코드로 데이터를 추출할 수 있습니다.")

        # 페이지가 바로 닫히지 않게 대기 (직접 F12 눌러서 확인해보세요)
        await asyncio.sleep(1000)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())