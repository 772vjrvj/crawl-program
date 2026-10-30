from __future__ import annotations

import csv
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.utils.selenium_utils import SeleniumUtils


# -----------------------------------------------------------------------------
# 실행 설정
# -----------------------------------------------------------------------------
NAVER_LOGIN_URL = (
    "https://nid.naver.com/nidlogin.login"
    "?mode=form&url=https://www.naver.com/"
)
CAFE_LIST_URL = "https://cafe.naver.com/f-e/cafes/10050146/menus/0"

MESSAGE_TEXT = "문의합니다."
MAX_SEND_COUNT = 10
ACCOUNT_SEND_COUNT = 0
MAX_PAGE_COUNT = 500

MIN_ACTION_DELAY_SEC = 1.0
MAX_ACTION_DELAY_SEC = 1.2
CHAT_LOADING_DELAY_SEC = 3.0

OUTPUT_CSV = Path("data") / "naver_cafe_inquiries.csv"


class NaverAccount(TypedDict):
    id: str
    password: str


# 현재는 첫 번째 계정 하나만 사용한다.
# 계정 반복이나 교체 로직은 필요할 때 이 리스트를 기준으로 추가하면 된다.
NAVER_ACCOUNTS: list[NaverAccount] = [
    # {
    #     "id": "772vjrvj",
    #     "password": "Ksh#8818510",
    # },
    {
        "id": "okimsnpartner@naver.com",
        "password": "rhkdzm23!",
    }
]

NAVER_ACCOUNTS_NUM = 0


CSV_FIELDS = [
    "updated_at",
    "page",
    "row_index",
    "td_1",
    "td_2",
    "td_3",
    "td_4",
    "td_5",
    "article_title",
    "writer",
    "article_url",
    "chat_url",
    "message",
    "status",
    "detail",
]

TERMINAL_STATUSES = {
    "sent",
    "no_chat",
    "user_skipped",
}


class NaverLoginError(RuntimeError):
    """네이버 로그인 실패."""


@dataclass
class NaverAuthClient:
    driver: WebDriver
    login_url: str = NAVER_LOGIN_URL
    timeout: int = 20

    def login(
            self,
            username: str,
            password: str,
            allow_manual_verification: bool = True,
    ) -> None:
        if not username or not password:
            raise NaverLoginError("계정 아이디 또는 비밀번호가 비어 있습니다.")

        self.driver.get(self.login_url)

        wait = WebDriverWait(self.driver, self.timeout)
        id_input = wait.until(EC.presence_of_element_located((By.ID, "id")))
        password_input = wait.until(EC.presence_of_element_located((By.ID, "pw")))

        self._set_input_value(id_input, username)
        human_delay()
        self._set_input_value(password_input, password)
        human_delay()

        login_button = wait.until(self._find_visible_login_button())
        login_button.click()

        try:
            WebDriverWait(self.driver, self.timeout).until(self._login_completed)
            return
        except TimeoutException:
            if not allow_manual_verification:
                raise NaverLoginError(self._get_login_error_message())

        print(
            "추가 인증, CAPTCHA 또는 기기 확인이 표시되었다면 "
            "브라우저에서 직접 완료해 주세요."
        )
        input("로그인이 완료되면 Enter를 누르세요...")

        if not self._login_completed(self.driver):
            raise NaverLoginError(self._get_login_error_message())

    def _set_input_value(self, element: WebElement, value: str) -> None:
        self.driver.execute_script(
            """
            const element = arguments[0];
            const value = arguments[1];
            const valueSetter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype,
                'value'
            ).set;

            element.focus();
            valueSetter.call(element, value);
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            element,
            value,
        )

    @staticmethod
    def _find_visible_login_button() -> Callable[[WebDriver], WebElement | bool]:
        selectors = (
            "#loginBtn_column",
            "#loginBtn_row",
            r"#log\.login",
            "button[type='submit']",
        )

        def find(driver: WebDriver) -> WebElement | bool:
            for selector in selectors:
                for element in driver.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed() and element.is_enabled():
                        return element
            return False

        return find

    @staticmethod
    def _login_completed(driver: WebDriver) -> bool:
        current_url = driver.current_url.lower()

        if "nidlogin.login" in current_url:
            return False

        if driver.get_cookie("NID_AUT") or driver.get_cookie("NID_SES"):
            return True

        return "naver.com" in current_url and "nid.naver.com" not in current_url

    def _get_login_error_message(self) -> str:
        for selector in (".form_message.error", "#err_common", ".error_message"):
            for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                text = clean_text(element.text)
                if element.is_displayed() and text:
                    return f"네이버 로그인 실패: {text}"

        return "네이버 로그인이 완료되지 않았습니다. 브라우저 화면을 확인하세요."


class CsvRecordStore:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.records: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.csv_path.exists():
            return

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            for record in csv.DictReader(file):
                article_url = record.get("article_url", "").strip()
                if article_url:
                    self.records[article_url] = {
                        field: record.get(field, "") for field in CSV_FIELDS
                    }

    def is_terminal(self, article_url: str) -> bool:
        record = self.records.get(article_url)
        return bool(record and record.get("status") in TERMINAL_STATUSES)

    def upsert(self, record: dict[str, str]) -> None:
        article_url = record["article_url"]
        previous = self.records.get(article_url, {})
        merged = {field: previous.get(field, "") for field in CSV_FIELDS}
        merged.update(record)
        merged["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.records[article_url] = merged
        self._save()

    def update_status(
            self,
            article_url: str,
            status: str,
            detail: str = "",
            chat_url: str = "",
    ) -> None:
        record = self.records[article_url]
        record["status"] = status
        record["detail"] = detail
        record["message"] = MESSAGE_TEXT
        if chat_url:
            record["chat_url"] = chat_url
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def _save(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        with self.csv_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in self.records.values():
                writer.writerow({field: record.get(field, "") for field in CSV_FIELDS})


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def human_delay() -> None:
    time.sleep(random.uniform(MIN_ACTION_DELAY_SEC, MAX_ACTION_DELAY_SEC))


def build_list_url(page: int) -> str:
    parts = urlsplit(CAFE_LIST_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page)
    query["t"] = str(int(time.time() * 1000))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def wait_document_ready(driver: WebDriver, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script(
            "return document.readyState"
        )
                               in ("interactive", "complete")
    )


def collect_page_rows(driver: WebDriver, page: int) -> list[dict[str, str]]:
    list_url = build_list_url(page)
    print(f"\n[목록] {page}페이지 이동: {list_url}")
    driver.get(list_url)
    wait_document_ready(driver)

    table = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.article-table"))
    )
    tbodies = table.find_elements(By.CSS_SELECTOR, ":scope > tbody")

    if not tbodies:
        return []

    # 사용자 제공 구조:
    # 1페이지는 공지 tbody 다음인 두 번째 tbody가 실제 목록이다.
    # 2페이지부터는 tbody가 하나이므로 첫 번째 tbody를 사용한다.
    if page == 1 and len(tbodies) >= 2:
        target_tbody = tbodies[1]
    else:
        target_tbody = tbodies[0]

    rows = target_tbody.find_elements(By.CSS_SELECTOR, ":scope > tr")
    collected: list[dict[str, str]] = []

    for row_index, row in enumerate(rows, start=1):
        article_links = row.find_elements(By.CSS_SELECTOR, "a.article")
        if not article_links:
            continue

        article_link = article_links[0]
        article_url = (article_link.get_attribute("href") or "").strip()
        if not article_url:
            continue

        td_values = [
            clean_text(td.text)
            for td in row.find_elements(By.CSS_SELECTOR, ":scope > td")
        ]
        td_values += [""] * (5 - len(td_values))

        nickname_elements = row.find_elements(By.CSS_SELECTOR, ".nickname")
        writer = (
            clean_text(nickname_elements[0].text)
            if nickname_elements
            else td_values[2]
        )

        collected.append(
            {
                "page": str(page),
                "row_index": str(row_index),
                "td_1": td_values[0],
                "td_2": td_values[1],
                "td_3": td_values[2],
                "td_4": td_values[3],
                "td_5": td_values[4],
                "article_title": clean_text(article_link.text) or td_values[1],
                "writer": writer,
                "article_url": article_url,
                "chat_url": "",
                "message": MESSAGE_TEXT,
                "status": "collected",
                "detail": "",
            }
        )

    return collected


def click_joongna_naver_login_if_needed(driver: WebDriver) -> bool:
    """중고나라 최초 연동 화면이면 '네이버로 시작하기'를 클릭한다."""
    selector = (
        By.XPATH,
        "//button[.//span[normalize-space()='네이버로 시작하기']]",
    )
    wait_seconds = 20 if "/signin" in driver.current_url.lower() else 5

    try:
        login_button = WebDriverWait(driver, wait_seconds).until(
            EC.element_to_be_clickable(selector)
        )
    except TimeoutException:
        return False

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        login_button,
    )
    human_delay()

    before_url = driver.current_url
    try:
        login_button.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", login_button)

    print("[중고나라 로그인] 네이버로 시작하기를 클릭했습니다.")

    try:
        WebDriverWait(driver, 30).until(
            lambda current_driver: current_driver.current_url != before_url
                                   or bool(
                current_driver.find_elements(
                    By.CSS_SELECTOR,
                    "textarea[name='message']",
                )
            )
        )
    except TimeoutException:
        print("[중고나라 로그인] 인증 화면 전환을 확인하지 못했습니다.")

    time.sleep(CHAT_LOADING_DELAY_SEC)
    return True


def open_chat_page(driver: WebDriver, article_url: str) -> tuple[str, str | None]:
    driver.switch_to.default_content()
    driver.get(article_url)
    wait_document_ready(driver)
    human_delay()

    # 구형 네이버 카페 게시글 주소는 실제 본문을 iframe#cafe_main 안에
    # 렌더링한다. iframe이 있는 경우 본문 프레임으로 전환하고,
    # 신형 /f-e 페이지처럼 iframe이 없으면 최상위 문서를 그대로 사용한다.
    try:
        WebDriverWait(driver, 10).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main"))
        )
        wait_document_ready(driver, timeout=15)
        print("[게시글] cafe_main iframe으로 전환했습니다.")
    except TimeoutException:
        driver.switch_to.default_content()
        print("[게시글] iframe이 없어 현재 문서에서 채팅 버튼을 찾습니다.")

    try:
        chat_button = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.ID, "more-button"))
        )
    except TimeoutException:
        return "", None

    chat_url = (chat_button.get_attribute("href") or "").strip()
    if not chat_url:
        return "", None

    article_handle = driver.current_window_handle
    handles_before = set(driver.window_handles)

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        chat_button,
    )
    human_delay()

    try:
        chat_button.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", chat_button)

    try:
        WebDriverWait(driver, 10).until(
            lambda current_driver: len(current_driver.window_handles)
                                   > len(handles_before)
        )
    except TimeoutException:
        # target=_blank 클릭이 막힌 환경에서는 같은 세션의 새 탭을 직접 연다.
        driver.execute_script("window.open(arguments[0], '_blank');", chat_url)
        WebDriverWait(driver, 10).until(
            lambda current_driver: len(current_driver.window_handles)
                                   > len(handles_before)
        )

    new_handles = [
        handle for handle in driver.window_handles if handle not in handles_before
    ]
    if new_handles:
        driver.switch_to.window(new_handles[-1])

    # tracking.joongna.com 리다이렉트 후 표시되는 상품 상세 화면에서는
    # 하단의 '채팅하기' 버튼을 한 번 더 눌러야 실제 채팅방으로 이동한다.
    time.sleep(CHAT_LOADING_DELAY_SEC)
    wait_document_ready(driver)

    product_chat_button = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button[aria-label='채팅하기']")
        )
    )
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        product_chat_button,
    )
    human_delay()

    try:
        product_chat_button.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", product_chat_button)

    print("[상품 상세] 채팅하기 버튼을 클릭했습니다.")
    time.sleep(CHAT_LOADING_DELAY_SEC)
    wait_document_ready(driver)

    first_login_completed = click_joongna_naver_login_if_needed(driver)

    # 최초 인증 때는 callbackUrl의 상품 상세로 다시 돌아온다.
    # 이 경우 상품 상세의 채팅하기 버튼을 한 번 더 눌러야 채팅방이 열린다.
    if first_login_completed:
        try:
            product_chat_button = WebDriverWait(driver, 60).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[aria-label='채팅하기']")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                product_chat_button,
            )
            human_delay()

            try:
                product_chat_button.click()
            except ElementClickInterceptedException:
                driver.execute_script(
                    "arguments[0].click();",
                    product_chat_button,
                )

            print("[최초 인증 완료] 채팅하기 버튼을 다시 클릭했습니다.")
            time.sleep(CHAT_LOADING_DELAY_SEC)
            wait_document_ready(driver)

        except TimeoutException:
            # 인증 후 바로 채팅방으로 이동한 경우에는 textarea가 이미 보인다.
            if not driver.find_elements(
                    By.CSS_SELECTOR,
                    "textarea[name='message']",
            ):
                raise

    return chat_url, article_handle


def close_chat_tab(driver: WebDriver, article_handle: str | None) -> None:
    if not article_handle:
        return

    if driver.current_window_handle != article_handle:
        driver.close()

    if article_handle in driver.window_handles:
        driver.switch_to.window(article_handle)


from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

# 업로드할 이미지의 전체 경로
IMAGE_PATH = r"E:\git\crawl-program\joonggonara_ad.png"


def fill_and_confirm_message(driver: WebDriver) -> str:
    textarea = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "textarea[name='message'][placeholder='메시지를 입력해 주세요.']",
            )
        )
    )

    textarea.click()
    human_delay()
    textarea.clear()

    # 이미지 업로드
    # 숨겨진 input 요소이므로 클릭하지 않고 파일 경로를 전달합니다.
    file_input = driver.find_element(
        By.CSS_SELECTOR,
        "form input[type='file']",
    )
    file_input.send_keys(IMAGE_PATH)

    human_delay()

    # 메시지 입력
    # textarea.send_keys(MESSAGE_TEXT)

    # human_delay()

    # 전송 버튼 클릭
    submit_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "textarea[name='message'] ~ button[type='submit']",
            )
        )
    )

    human_delay()
    submit_button.click()

    try:
        WebDriverWait(driver, 10).until(
            lambda current_driver: (
                                           current_driver.find_element(
                                               By.CSS_SELECTOR,
                                               "textarea[name='message']",
                                           ).get_attribute("value")
                                           or ""
                                   ) == ""
        )
    except TimeoutException:
        return "unconfirmed"

    human_delay()
    return "sent"


def on_account_send_limit_reached(driver: WebDriver) -> int:
    """계정의 전송 한도 도달 시 카운트를 초기화하고 작업을 종료한다."""
    global ACCOUNT_SEND_COUNT, NAVER_ACCOUNTS_NUM

    completed_count = ACCOUNT_SEND_COUNT
    print(
        f"[계정 작업 종료] 전송 {completed_count}건에 도달했습니다. "
        "카운트를 0으로 초기화합니다."
    )
    ACCOUNT_SEND_COUNT = 0

    NAVER_ACCOUNTS_NUM = (NAVER_ACCOUNTS_NUM + 1) % len(NAVER_ACCOUNTS)

    account = NAVER_ACCOUNTS[NAVER_ACCOUNTS_NUM]


    print("네이버 로그인을 시작합니다.")
    NaverAuthClient(driver=driver).login(
        username=account["id"],
        password=account["password"],
        allow_manual_verification=True,
    )

    return completed_count


def process_articles(
        driver: WebDriver,
        store: CsvRecordStore,
) -> int:
    global ACCOUNT_SEND_COUNT

    previous_page_signature: tuple[str, ...] | None = None

    for page in range(1, MAX_PAGE_COUNT + 1):
        if ACCOUNT_SEND_COUNT >= MAX_SEND_COUNT:
            on_account_send_limit_reached(driver)

        page_rows = collect_page_rows(driver, page)
        if not page_rows:
            print(f"[{page}페이지] 처리할 게시글이 없어 종료합니다.")
            break

        page_signature = tuple(row["article_url"] for row in page_rows)
        if page_signature == previous_page_signature:
            print(
                "페이지를 변경했지만 같은 게시글 목록이 표시됩니다. "
                "페이지 URL 구조를 확인해 주세요."
            )
            break
        previous_page_signature = page_signature

        print(f"[{page}페이지] 일반 게시글 {len(page_rows)}개를 확인했습니다.")

        for record in page_rows:
            if ACCOUNT_SEND_COUNT >= MAX_SEND_COUNT:
                on_account_send_limit_reached(driver)

            article_url = record["article_url"]

            # td 데이터는 처리 여부와 관계없이 먼저 저장한다.
            if article_url not in store.records:
                store.upsert(record)

            if store.is_terminal(article_url):
                print(f"[건너뜀] 이미 처리됨: {record['article_title']}")
                continue

            print(
                f"\n[{ACCOUNT_SEND_COUNT + 1}/{MAX_SEND_COUNT}] "
                f"{record['article_title']} / {record['writer']}"
            )
            print(article_url)

            article_handle: str | None = None

            try:
                chat_url, article_handle = open_chat_page(driver, article_url)
                if not chat_url:
                    print("[건너뜀] 채팅하기 버튼이 없습니다.")
                    store.update_status(
                        article_url,
                        status="no_chat",
                        detail="채팅하기 버튼 없음",
                    )
                    continue

                store.update_status(
                    article_url,
                    status="chat_opened",
                    chat_url=chat_url,
                )

                result = fill_and_confirm_message(driver)


                if result == "unconfirmed":
                    print("[확인 필요] 전송 완료 상태를 확인하지 못했습니다.")
                    store.update_status(
                        article_url,
                        status="send_unconfirmed",
                        detail="전송 후 입력창 초기화 확인 실패",
                        chat_url=chat_url,
                    )
                    continue

                ACCOUNT_SEND_COUNT += 1
                store.update_status(
                    article_url,
                    status="sent",
                    detail=f"현재 계정에서 {ACCOUNT_SEND_COUNT}번째 전송",
                    chat_url=chat_url,
                )
                print(
                    f"[전송 완료] 현재 "
                    f"{ACCOUNT_SEND_COUNT}/{MAX_SEND_COUNT}건"
                )

                if ACCOUNT_SEND_COUNT >= MAX_SEND_COUNT:
                    on_account_send_limit_reached(driver)

            except (TimeoutException, WebDriverException) as exc:
                error_text = clean_text(str(exc))[:500]
                print(f"[오류] {error_text}")
                store.update_status(
                    article_url,
                    status="error",
                    detail=error_text,
                )
            finally:
                try:
                    close_chat_tab(driver, article_handle)
                except WebDriverException:
                    pass

    return ACCOUNT_SEND_COUNT


def main() -> None:
    if not NAVER_ACCOUNTS:
        raise RuntimeError("NAVER_ACCOUNTS에 계정이 없습니다.")

    # 요청대로 현재는 배열의 첫 번째 계정 하나만 사용한다.
    account = NAVER_ACCOUNTS[0]
    store = CsvRecordStore(OUTPUT_CSV)
    selenium = SeleniumUtils(headless=False, debug=True)

    try:
        driver = selenium.start_driver(
            timeout=30,
            view_mode="browser",
            window_size=(1280, 900),
        )

        print("네이버 로그인을 시작합니다.")
        NaverAuthClient(driver=driver).login(
            username=account["id"],
            password=account["password"],
            allow_manual_verification=True,
        )

        sent_count = process_articles(driver, store)
        print(f"\n작업 종료: 이번 실행에서 전송 확인된 메시지 {sent_count}건")
        print(f"저장 파일: {OUTPUT_CSV.resolve()}")

        input("브라우저를 종료하려면 Enter를 누르세요...")

    except (NaverLoginError, TimeoutException, WebDriverException) as exc:
        print(f"실행 실패: {clean_text(str(exc))}")
        try:
            input("브라우저 상태를 확인한 뒤 Enter를 누르세요...")
        except (EOFError, KeyboardInterrupt):
            pass
    finally:
        selenium.quit()


if __name__ == "__main__":
    main()


