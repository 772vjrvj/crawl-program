# -*- coding: utf-8 -*-

import os
import time
from pprint import pprint
from typing import Dict, List, Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from src.utils.selenium_utils import SeleniumUtils


# =============================================================================
# 기본 설정
# =============================================================================

# 상세 페이지 사이 대기 시간
REQUEST_INTERVAL_SECONDS = 2.0

# URL 한 개당 최대 시도 횟수
MAX_ATTEMPTS = 2

# 페이지 로드 제한 시간
PAGE_LOAD_TIMEOUT = 60

# 첫 번째 시도의 판매자 정보 탐색 시간
FAST_SEARCH_TIMEOUT = 15

# 두 번째 시도의 판매자 정보 탐색 시간
SLOW_SEARCH_TIMEOUT = 35

# 첫 번째 시도의 스크롤 간격
FAST_SCROLL_WAIT = 0.15

# 두 번째 시도의 스크롤 간격
SLOW_SCROLL_WAIT = 0.45

# 모달 대기 시간
FAST_MODAL_TIMEOUT = 10
SLOW_MODAL_TIMEOUT = 20

# 오류 이미지 저장 폴더
ERROR_SCREENSHOT_DIR = "error_screenshots"


TARGET_FIELDS = {
    "상호",
    "대표자명",
    "주소",
    "전화번호",
    "이메일",
}


# =============================================================================
# URL 목록
# 실패했던 4개를 가장 위에 배치
# =============================================================================

URLS: List[str] = [
    # -------------------------------------------------------------------------
    # 이전 실행 실패 URL
    # -------------------------------------------------------------------------
    "https://www.yeogi.com/domestic-accommodations/4449",
    "https://www.yeogi.com/domestic-accommodations/51530",
    "https://www.yeogi.com/domestic-accommodations/1883",
    "https://www.yeogi.com/domestic-accommodations/5359",

    # -------------------------------------------------------------------------
    # 기존 성공 URL
    # -------------------------------------------------------------------------
    "https://www.yeogi.com/domestic-accommodations/895",
    "https://www.yeogi.com/domestic-accommodations/55239",
    "https://www.yeogi.com/domestic-accommodations/49680",
    "https://www.yeogi.com/domestic-accommodations/700",
    "https://www.yeogi.com/domestic-accommodations/1695",
    "https://www.yeogi.com/domestic-accommodations/2556",
    "https://www.yeogi.com/domestic-accommodations/2158",
    "https://www.yeogi.com/domestic-accommodations/49848",
    "https://www.yeogi.com/domestic-accommodations/67703",
    "https://www.yeogi.com/domestic-accommodations/49802",
    "https://www.yeogi.com/domestic-accommodations/55127",
    "https://www.yeogi.com/domestic-accommodations/3950",
    "https://www.yeogi.com/domestic-accommodations/67397",
    "https://www.yeogi.com/domestic-accommodations/48916",
    "https://www.yeogi.com/domestic-accommodations/888",
    "https://www.yeogi.com/domestic-accommodations/1887",
]


# =============================================================================
# 사용자 정의 예외
# =============================================================================

class AccessBlockedError(Exception):
    """
    사이트에서 접속을 제한한 경우 발생시키는 예외.
    """

    pass


class SellerButtonTimeoutError(Exception):
    """
    판매자 정보 버튼을 제한 시간 안에 찾지 못한 경우.
    """

    pass


class SellerModalTimeoutError(Exception):
    """
    판매자 정보 버튼 클릭 후 모달이 나타나지 않은 경우.
    """

    pass


# =============================================================================
# 결과 데이터 생성
# =============================================================================

def create_empty_result(url: str) -> Dict[str, str]:
    return {
        "url": url,
        "상호": "",
        "대표자명": "",
        "주소": "",
        "전화번호": "",
        "이메일": "",
        "수집상태": "FAIL",
        "시도횟수": "0",
        "오류내용": "",
    }


# =============================================================================
# 공통 대기
# =============================================================================

def wait_document_ready(
        driver: WebDriver,
        timeout: int = 15,
) -> None:
    """
    DOM이 interactive 또는 complete 상태가 될 때까지 기다린다.

    이미지, 광고 등 모든 리소스가 끝날 필요는 없고,
    화면 요소를 탐색할 수 있는 시점까지만 기다린다.
    """

    try:
        WebDriverWait(
            driver,
            timeout,
        ).until(
            lambda current_driver: (
                    current_driver.execute_script(
                        "return document.readyState"
                    )
                    in ("interactive", "complete")
            )
        )

        WebDriverWait(
            driver,
            timeout,
        ).until(
            lambda current_driver: (
                current_driver.execute_script(
                    "return document.body !== null"
                )
            )
        )

    except TimeoutException:
        # DOM 일부라도 생성됐다면 이후 탐색을 계속 진행한다.
        pass


def get_page_height(driver: WebDriver) -> int:
    """
    현재 문서의 전체 높이를 반환한다.
    """

    try:
        height = driver.execute_script(
            """
            return Math.max(
                document.body ? document.body.scrollHeight : 0,
                document.documentElement
                    ? document.documentElement.scrollHeight
                    : 0
            );
            """
        )

        return int(height or 0)

    except Exception:
        return 0


def get_scroll_position(driver: WebDriver) -> int:
    """
    현재 스크롤 Y 위치를 반환한다.
    """

    try:
        position = driver.execute_script(
            """
            return (
                window.pageYOffset
                || document.documentElement.scrollTop
                || document.body.scrollTop
                || 0
            );
            """
        )

        return int(position or 0)

    except Exception:
        return 0


# =============================================================================
# 접속 제한 확인
# =============================================================================

def is_access_blocked(driver: WebDriver) -> bool:
    """
    Selenium에서는 driver.get()의 HTTP 상태 코드를 직접 받기 어려우므로,
    페이지 제목과 본문에 접속 제한 문구가 있는지 검사한다.
    """

    title = ""
    body_text = ""
    page_source = ""

    try:
        title = driver.title.lower()
    except Exception:
        pass

    try:
        body_text = driver.find_element(
            By.TAG_NAME,
            "body",
        ).text.lower()
    except Exception:
        pass

    try:
        page_source = driver.page_source.lower()
    except Exception:
        pass

    combined_text = (
            title
            + "\n"
            + body_text
            + "\n"
            + page_source[:30_000]
    )

    blocked_keywords = [
        "403 forbidden",
        "http 403",
        "access denied",
        "request blocked",
        "temporarily blocked",
        "접근이 제한",
        "접속이 제한",
        "요청이 차단",
        "비정상적인 접근",
        "서비스 이용이 제한",
    ]

    return any(
        keyword in combined_text
        for keyword in blocked_keywords
    )


# =============================================================================
# 판매자 정보 버튼 탐색
# =============================================================================

def get_visible_element(
        elements: List[WebElement],
) -> Optional[WebElement]:
    """
    PC용과 모바일용 요소가 중복으로 존재할 수 있으므로
    실제 화면에 표시되는 요소만 반환한다.
    """

    for element in reversed(elements):
        try:
            if element.is_displayed():
                return element

        except (
                StaleElementReferenceException,
                WebDriverException,
        ):
            continue

    return None


def find_seller_button_with_selectors(
        driver: WebDriver,
) -> Optional[WebElement]:
    """
    일반 CSS 및 XPath 선택자로 판매자 정보 버튼을 찾는다.
    """

    selectors = [
        (
            By.CSS_SELECTOR,
            '[aria-label="판매자 정보"][role="button"]',
        ),
        (
            By.CSS_SELECTOR,
            '[aria-label="판매자 정보"]',
        ),
        (
            By.XPATH,
            (
                "//h2[normalize-space()='판매자 정보']"
                "/ancestor::*[@role='button'][1]"
            ),
        ),
        (
            By.XPATH,
            (
                "//*[normalize-space()='판매자 정보']"
                "/ancestor::*[@role='button'][1]"
            ),
        ),
    ]

    for by, selector in selectors:
        try:
            elements = driver.find_elements(
                by,
                selector,
            )

            visible_element = get_visible_element(
                elements
            )

            if visible_element is not None:
                return visible_element

        except Exception:
            continue

    return None


def find_seller_button_with_javascript(
        driver: WebDriver,
) -> Optional[WebElement]:
    """
    일반 선택자로 못 찾는 경우 JavaScript로 보이는 판매자 정보 버튼을 찾는다.
    """

    try:
        element = driver.execute_script(
            """
            const candidates = Array.from(
                document.querySelectorAll(
                    '[role="button"], [aria-label="판매자 정보"]'
                )
            );

            for (let i = candidates.length - 1; i >= 0; i--) {
                const element = candidates[i];

                const ariaLabel = (
                    element.getAttribute("aria-label") || ""
                ).trim();

                const text = (
                    element.innerText
                    || element.textContent
                    || ""
                ).trim();

                const rect = element.getBoundingClientRect();

                const style = window.getComputedStyle(element);

                const visible = (
                    rect.width > 0
                    && rect.height > 0
                    && style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0
                );

                if (
                    visible
                    && (
                        ariaLabel === "판매자 정보"
                        || text === "판매자 정보"
                        || text.startsWith("판매자 정보")
                    )
                ) {
                    return element;
                }
            }

            return null;
            """
        )

        if element is not None:
            return element

    except Exception:
        pass

    return None


def find_visible_seller_button(
        driver: WebDriver,
) -> Optional[WebElement]:
    """
    선택자 방식과 JavaScript 방식을 차례대로 사용한다.
    """

    button = find_seller_button_with_selectors(
        driver
    )

    if button is not None:
        return button

    return find_seller_button_with_javascript(
        driver
    )


def scroll_to_bottom_with_lazy_loading(
        driver: WebDriver,
        slow_mode: bool,
) -> Optional[WebElement]:
    """
    페이지 최하단으로 여러 번 이동하면서 동적 콘텐츠가 추가되는지 확인한다.

    일부 상세 페이지는 한 번에 최하단으로 이동해도
    판매자 정보 영역이 바로 렌더링되지 않을 수 있다.
    """

    wait_seconds = (
        0.8 if slow_mode else 0.35
    )

    previous_height = -1
    same_height_count = 0

    max_cycles = 8 if slow_mode else 4

    for _ in range(max_cycles):
        button = find_visible_seller_button(
            driver
        )

        if button is not None:
            return button

        current_height = get_page_height(
            driver
        )

        try:
            driver.execute_script(
                """
                window.scrollTo(
                    0,
                    Math.max(
                        document.body
                            ? document.body.scrollHeight
                            : 0,
                        document.documentElement
                            ? document.documentElement.scrollHeight
                            : 0
                    )
                );
                """
            )
        except JavascriptException:
            pass

        time.sleep(wait_seconds)

        button = find_visible_seller_button(
            driver
        )

        if button is not None:
            return button

        new_height = get_page_height(
            driver
        )

        if new_height == previous_height:
            same_height_count += 1
        else:
            same_height_count = 0

        previous_height = new_height

        if same_height_count >= 2:
            break

    return None


def scroll_page_step_by_step(
        driver: WebDriver,
        slow_mode: bool,
) -> Optional[WebElement]:
    """
    페이지 위에서부터 아래까지 조금씩 스크롤하면서
    판매자 정보 영역의 지연 렌더링을 유도한다.
    """

    search_timeout = (
        SLOW_SEARCH_TIMEOUT
        if slow_mode
        else FAST_SEARCH_TIMEOUT
    )

    scroll_wait = (
        SLOW_SCROLL_WAIT
        if slow_mode
        else FAST_SCROLL_WAIT
    )

    scroll_step = 500 if slow_mode else 900

    start_time = time.monotonic()

    driver.execute_script(
        "window.scrollTo(0, 0);"
    )

    time.sleep(
        0.8 if slow_mode else 0.2
    )

    while (
            time.monotonic() - start_time
            < search_timeout
    ):
        button = find_visible_seller_button(
            driver
        )

        if button is not None:
            return button

        if is_access_blocked(driver):
            raise AccessBlockedError(
                "사이트에서 접속을 제한했습니다."
            )

        current_position = get_scroll_position(
            driver
        )

        page_height = get_page_height(
            driver
        )

        viewport_height = int(
            driver.execute_script(
                "return window.innerHeight || 900;"
            )
            or 900
        )

        next_position = (
                current_position + scroll_step
        )

        driver.execute_script(
            "window.scrollTo(0, arguments[0]);",
            next_position,
        )

        time.sleep(scroll_wait)

        new_position = get_scroll_position(
            driver
        )

        # 최하단에 도착한 경우
        if (
                new_position + viewport_height
                >= page_height - 100
        ):
            # 하단에서 콘텐츠가 추가 렌더링될 시간을 준다.
            time.sleep(
                1.5 if slow_mode else 0.5
            )

            button = find_visible_seller_button(
                driver
            )

            if button is not None:
                return button

            # 스크롤을 살짝 올렸다가 다시 내리면
            # IntersectionObserver가 반응하는 페이지가 있다.
            driver.execute_script(
                """
                window.scrollBy(0, -500);
                """
            )

            time.sleep(
                0.5 if slow_mode else 0.2
            )

            driver.execute_script(
                """
                window.scrollTo(
                    0,
                    Math.max(
                        document.body
                            ? document.body.scrollHeight
                            : 0,
                        document.documentElement
                            ? document.documentElement.scrollHeight
                            : 0
                    )
                );
                """
            )

            time.sleep(
                1.5 if slow_mode else 0.5
            )

            button = find_visible_seller_button(
                driver
            )

            if button is not None:
                return button

            # 페이지 높이가 늘어났다면 계속 스크롤한다.
            new_page_height = get_page_height(
                driver
            )

            if new_page_height <= page_height:
                break

    return None


def find_seller_button(
        driver: WebDriver,
        slow_mode: bool,
) -> WebElement:
    """
    판매자 정보 버튼을 여러 단계로 탐색한다.

    1. 현재 화면
    2. 최하단 반복 이동
    3. 위에서부터 단계별 스크롤
    4. 최하단에서 마지막 재확인
    """

    button = find_visible_seller_button(
        driver
    )

    if button is not None:
        return button

    button = scroll_to_bottom_with_lazy_loading(
        driver=driver,
        slow_mode=slow_mode,
    )

    if button is not None:
        return button

    button = scroll_page_step_by_step(
        driver=driver,
        slow_mode=slow_mode,
    )

    if button is not None:
        return button

    # 최종적으로 한 번 더 최하단 이동 후 확인
    driver.execute_script(
        """
        window.scrollTo(
            0,
            Math.max(
                document.body
                    ? document.body.scrollHeight
                    : 0,
                document.documentElement
                    ? document.documentElement.scrollHeight
                    : 0
            )
        );
        """
    )

    time.sleep(
        2.0 if slow_mode else 0.7
    )

    button = find_visible_seller_button(
        driver
    )

    if button is not None:
        return button

    if is_access_blocked(driver):
        raise AccessBlockedError(
            "사이트에서 접속을 제한했습니다."
        )

    raise SellerButtonTimeoutError(
        "페이지 하단까지 스크롤했지만 판매자 정보 버튼을 찾지 못했습니다."
    )


# =============================================================================
# 판매자 정보 버튼 클릭
# =============================================================================

def click_seller_button(
        driver: WebDriver,
        button: WebElement,
) -> None:
    """
    버튼을 화면 중앙으로 이동한 후 클릭한다.
    """

    try:
        driver.execute_script(
            """
            arguments[0].scrollIntoView({
                block: "center",
                inline: "center"
            });
            """,
            button,
        )

    except Exception:
        pass

    time.sleep(0.3)

    try:
        ActionChains(driver).move_to_element(
            button
        ).pause(
            0.1
        ).click().perform()

        return

    except (
            ElementClickInterceptedException,
            ElementNotInteractableException,
            StaleElementReferenceException,
            WebDriverException,
    ):
        pass

    # 일반 클릭이 실패하면 JavaScript 클릭
    try:
        driver.execute_script(
            "arguments[0].click();",
            button,
        )

    except Exception as error:
        raise RuntimeError(
            f"판매자 정보 버튼 클릭 실패: {error}"
        )


# =============================================================================
# 판매자 정보 모달
# =============================================================================

def get_visible_seller_dialog(
        driver: WebDriver,
) -> Optional[WebElement]:
    """
    현재 화면에 표시된 판매자 정보 모달을 찾는다.
    """

    selectors = [
        '#modal-wrapper [role="dialog"]',
        '[role="dialog"]',
    ]

    for selector in selectors:
        try:
            dialogs = driver.find_elements(
                By.CSS_SELECTOR,
                selector,
            )

            for dialog in reversed(dialogs):
                try:
                    if not dialog.is_displayed():
                        continue

                    dialog_text = dialog.text.strip()

                    if "판매자 정보" in dialog_text:
                        return dialog

                except (
                        StaleElementReferenceException,
                        WebDriverException,
                ):
                    continue

        except Exception:
            continue

    return None


def wait_seller_dialog(
        driver: WebDriver,
        slow_mode: bool,
) -> WebElement:
    """
    판매자 정보 모달이 나타날 때까지 기다린다.
    """

    timeout = (
        SLOW_MODAL_TIMEOUT
        if slow_mode
        else FAST_MODAL_TIMEOUT
    )

    try:
        return WebDriverWait(
            driver,
            timeout,
        ).until(
            lambda current_driver: (
                get_visible_seller_dialog(
                    current_driver
                )
            )
        )

    except TimeoutException as error:
        raise SellerModalTimeoutError(
            "판매자 정보 버튼은 클릭했지만 모달이 나타나지 않았습니다."
        ) from error


def open_seller_dialog(
        driver: WebDriver,
        slow_mode: bool,
) -> WebElement:
    """
    판매자 정보 버튼을 클릭하고 모달을 연다.

    모달이 열리지 않으면 버튼을 다시 찾아 한 번 더 클릭한다.
    """

    seller_button = find_seller_button(
        driver=driver,
        slow_mode=slow_mode,
    )

    click_seller_button(
        driver=driver,
        button=seller_button,
    )

    try:
        return wait_seller_dialog(
            driver=driver,
            slow_mode=slow_mode,
        )

    except SellerModalTimeoutError:
        # 클릭 직후 React 렌더링 문제 또는 stale 상태일 수 있으므로
        # 버튼을 다시 찾아 JavaScript 클릭을 수행한다.
        time.sleep(
            1.5 if slow_mode else 0.5
        )

        seller_button = find_seller_button(
            driver=driver,
            slow_mode=slow_mode,
        )

        driver.execute_script(
            "arguments[0].click();",
            seller_button,
        )

        return wait_seller_dialog(
            driver=driver,
            slow_mode=True,
        )


# =============================================================================
# 판매자 정보 추출
# =============================================================================

def extract_seller_info(
        driver: WebDriver,
        dialog: WebElement,
) -> Dict[str, str]:
    """
    판매자 정보 모달 표에서 필요한 정보를 추출한다.
    """

    def table_rows_loaded(
            current_driver: WebDriver,
    ) -> bool:
        try:
            rows = dialog.find_elements(
                By.CSS_SELECTOR,
                "table tbody tr",
            )

            return len(rows) > 0

        except StaleElementReferenceException:
            return False

    try:
        WebDriverWait(
            driver,
            10,
        ).until(
            table_rows_loaded
        )

    except TimeoutException as error:
        raise SellerModalTimeoutError(
            "판매자 정보 모달은 열렸지만 표 데이터가 로드되지 않았습니다."
        ) from error

    rows = dialog.find_elements(
        By.CSS_SELECTOR,
        "table tbody tr",
    )

    result: Dict[str, str] = {
        "상호": "",
        "대표자명": "",
        "주소": "",
        "전화번호": "",
        "이메일": "",
    }

    for row in rows:
        try:
            header = row.find_element(
                By.TAG_NAME,
                "th",
            ).text.strip()

            value = row.find_element(
                By.TAG_NAME,
                "td",
            ).text.strip()

            if header in TARGET_FIELDS:
                result[header] = value

        except (
                NoSuchElementException,
                StaleElementReferenceException,
        ):
            continue

    # 상호까지 비어 있으면 실제 데이터 추출 실패로 처리
    if not result["상호"]:
        raise RuntimeError(
            "판매자 정보 표는 찾았지만 상호 값이 비어 있습니다."
        )

    return result


# =============================================================================
# URL 한 건 수집
# =============================================================================

def collect_one(
        driver: WebDriver,
        url: str,
        slow_mode: bool,
) -> Dict[str, str]:
    """
    상세 URL 한 곳에서 판매자 정보를 수집한다.
    """

    try:
        driver.get(url)

    except TimeoutException:
        # 모든 이미지 등의 로딩은 끝나지 않았지만
        # 현재까지 생성된 DOM으로 계속 진행한다.
        try:
            driver.execute_script(
                "window.stop();"
            )
        except Exception:
            pass

    wait_document_ready(
        driver=driver,
        timeout=20 if slow_mode else 10,
    )

    # 두 번째 시도에서는 동적 콘텐츠가 초기화될 시간을 더 준다.
    if slow_mode:
        time.sleep(2.0)
    else:
        time.sleep(0.5)

    if is_access_blocked(driver):
        raise AccessBlockedError(
            "사이트에서 접속을 제한했습니다."
        )

    dialog = open_seller_dialog(
        driver=driver,
        slow_mode=slow_mode,
    )

    return extract_seller_info(
        driver=driver,
        dialog=dialog,
    )


# =============================================================================
# 재시도
# =============================================================================

def collect_with_retry(
        driver: WebDriver,
        url: str,
        current: int,
        total: int,
) -> Dict[str, str]:
    """
    URL 한 개를 최대 2회 시도한다.

    1차 실패 시 about:blank로 이동한 뒤
    더 긴 대기와 느린 스크롤로 다시 수집한다.
    """

    result = create_empty_result(
        url
    )

    last_error = ""

    for attempt in range(
            1,
            MAX_ATTEMPTS + 1,
    ):
        slow_mode = attempt >= 2

        result["시도횟수"] = str(
            attempt
        )

        mode_text = (
            "느린 재시도"
            if slow_mode
            else "일반 시도"
        )

        print(
            f"[수집 시도] "
            f"{current}/{total} | "
            f"{attempt}/{MAX_ATTEMPTS} | "
            f"{mode_text}"
        )

        try:
            seller_data = collect_one(
                driver=driver,
                url=url,
                slow_mode=slow_mode,
            )

            result.update(
                seller_data
            )

            result["수집상태"] = "SUCCESS"
            result["오류내용"] = ""

            return result

        except AccessBlockedError:
            # 접속 제한은 반복 요청하지 않고 즉시 상위로 전달
            raise

        except Exception as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            print(
                f"[시도 실패] "
                f"{current}/{total} | "
                f"{last_error}"
            )

            if attempt < MAX_ATTEMPTS:
                try:
                    driver.get(
                        "about:blank"
                    )
                except Exception:
                    pass

                # 이전 페이지의 네트워크 및 React 상태가 정리될 시간
                time.sleep(2.0)

    result["오류내용"] = last_error

    return result


# =============================================================================
# 스크린샷
# =============================================================================

def save_error_screenshot(
        driver: WebDriver,
        index: int,
        url: str,
) -> None:
    """
    최종 실패한 페이지의 화면을 저장한다.
    """

    try:
        os.makedirs(
            ERROR_SCREENSHOT_DIR,
            exist_ok=True,
        )

        accommodation_id = (
            url.rstrip("/").split("/")[-1]
        )

        file_name = (
            f"yeogi_error_"
            f"{index}_"
            f"{accommodation_id}.png"
        )

        file_path = os.path.join(
            ERROR_SCREENSHOT_DIR,
            file_name,
        )

        driver.save_screenshot(
            file_path
        )

        print(
            f"[오류 화면 저장] {file_path}"
        )

    except Exception as error:
        print(
            f"[오류 화면 저장 실패] {error}"
        )


# =============================================================================
# 출력
# =============================================================================

def print_result(
        result: Dict[str, str],
        current: int,
        total: int,
) -> None:
    print("=" * 90)
    print(f"진행      : {current}/{total}")
    print(f"수집상태  : {result.get('수집상태', '')}")
    print(f"시도횟수  : {result.get('시도횟수', '')}")
    print(f"URL       : {result.get('url', '')}")
    print(f"상호      : {result.get('상호', '')}")
    print(f"대표자명  : {result.get('대표자명', '')}")
    print(f"주소      : {result.get('주소', '')}")
    print(f"전화번호  : {result.get('전화번호', '')}")
    print(f"이메일    : {result.get('이메일', '')}")

    if result.get("오류내용"):
        print(
            f"오류내용  : "
            f"{result['오류내용']}"
        )

    print("=" * 90)


# =============================================================================
# main
# =============================================================================

def main() -> None:
    results: List[Dict[str, str]] = []

    total_count = len(URLS)

    selenium_utils = SeleniumUtils(
        # 실제 Chrome 창 표시
        headless=False,

        # SeleniumUtils 기동 로그 표시
        debug=True,
    )

    # 정상 브라우저와 동일하게 이미지도 로드한다.
    selenium_utils.set_capture_options(
        enabled=False,
        block_images=False,
    )

    driver: Optional[WebDriver] = None

    print(
        f"전체 수집 시작 | "
        f"대상={total_count}개 | "
        f"실패 URL 우선 처리"
    )

    try:
        driver = selenium_utils.start_driver(
            timeout=PAGE_LOAD_TIMEOUT,
            view_mode="browser",
            window_size=(1400, 1000),
        )

        print(
            "[초기 접속] "
            "https://www.yeogi.com/"
        )

        try:
            driver.get(
                "https://www.yeogi.com/"
            )

        except TimeoutException:
            try:
                driver.execute_script(
                    "window.stop();"
                )
            except Exception:
                pass

        wait_document_ready(
            driver=driver,
            timeout=15,
        )

        if is_access_blocked(driver):
            print(
                "[초기 접속 실패] "
                "메인 페이지부터 접속이 제한되었습니다."
            )

            return

        time.sleep(2.0)

        for index, url in enumerate(
                URLS,
                start=1,
        ):
            print()
            print(
                f"[접속 시작] "
                f"{index}/{total_count} | "
                f"{url}"
            )

            try:
                result = collect_with_retry(
                    driver=driver,
                    url=url,
                    current=index,
                    total=total_count,
                )

            except AccessBlockedError as error:
                result = create_empty_result(
                    url
                )

                result["오류내용"] = str(
                    error
                )

                results.append(
                    result
                )

                print_result(
                    result=result,
                    current=index,
                    total=total_count,
                )

                print()
                print(
                    "[수집 중단] "
                    "접속 제한이 확인되어 "
                    "추가 요청을 중단합니다."
                )

                break

            results.append(
                result
            )

            if (
                    result["수집상태"]
                    == "FAIL"
            ):
                save_error_screenshot(
                    driver=driver,
                    index=index,
                    url=url,
                )

            print_result(
                result=result,
                current=index,
                total=total_count,
            )

            if index < total_count:
                time.sleep(
                    REQUEST_INTERVAL_SECONDS
                )

    except Exception as error:
        print(
            f"[프로그램 오류] "
            f"{type(error).__name__}: "
            f"{error}"
        )

    finally:
        selenium_utils.quit()

    success_count = sum(
        1
        for item in results
        if item["수집상태"] == "SUCCESS"
    )

    fail_count = (
            len(results) - success_count
    )

    print()
    print("#" * 90)
    print("수집 종료")
    print(f"실행 : {len(results)}개")
    print(f"성공 : {success_count}개")
    print(f"실패 : {fail_count}개")
    print("#" * 90)

    print("\n최종 배열:")

    pprint(
        results,
        sort_dicts=False,
        width=220,
    )


if __name__ == "__main__":
    main()