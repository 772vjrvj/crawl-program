import json
import random
import re
import time
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import parse_qs, urlparse


BASE_URL = "https://www.dorus.co.kr"
LIST_URL = f"{BASE_URL}/work/resume_list.html"

START_PAGE = 1
END_PAGE = 1215

OUTPUT_FILE = Path("resume_no_list.json")
PROGRESS_FILE = Path("resume_no_progress.json")

REQUEST_TIMEOUT = 20

# 서버에 과도한 요청을 보내지 않도록 페이지 요청 간격 설정
MIN_DELAY_SEC = 0.1
MAX_DELAY_SEC = 0.2


def create_session() -> requests.Session:
    """
    재시도 설정이 적용된 requests 세션 생성
    """
    session = requests.Session()

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update(
        {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": LIST_URL,
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        }
    )

    # 로그인이 필요한 페이지라면 현재 브라우저의 PHPSESSID를 넣습니다.
    # 세션 쿠키는 만료될 수 있으므로 필요할 때만 사용하세요.
    #
    session.cookies.set(
        "PHPSESSID",
        "9cf6262413847cb4882aa20a672035b6; _fwb=30zJXu4WKYnf47JJJHKi4r.1785756039940; _gid=GA1.3.982365059.1785756040; uwrToday=46678,38,37,46768,46903,46892,46846,46437; wcs_bt=undefined:1785756593|undefined:1785756040; _ga=GA1.1.1992543861.1785756040; _ga_F71F17H2DY=GS2.1.s1785756040$o1$g1$t1785756609$j60$l0$h0",
        domain="www.dorus.co.kr",
        path="/",
    )

    return session


def find_resume_data_tbody(soup: BeautifulSoup):
    """
    사용자가 설명한 DOM 순서로 이력서 목록 tbody를 찾는다.

    1. class="list_array"인 td 탐색
    2. 직속 부모 tr
    3. 직속 부모 tbody
    4. 직속 부모 table
    5. 해당 테이블의 두 번째 tr 안 첫 번째 td 내부 table
    6. align="center"인 tbody
    """
    list_array_td = soup.find(
        "td",
        class_=lambda classes: classes and "list_array" in classes,
    )

    if list_array_td is None:
        return None

    header_tr = list_array_td.find_parent("tr")
    if header_tr is None:
        return None

    outer_tbody = header_tr.find_parent("tbody")
    if outer_tbody is None:
        return None

    outer_table = outer_tbody.find_parent("table")
    if outer_table is None:
        return None

    # outer tbody의 직속 tr만 조회
    direct_rows = outer_tbody.find_all("tr", recursive=False)

    if len(direct_rows) < 2:
        return None

    second_tr = direct_rows[1]

    # 두 번째 tr의 첫 번째 직속 td
    second_tr_tds = second_tr.find_all("td", recursive=False)

    if not second_tr_tds:
        return None

    first_td = second_tr_tds[0]

    # 첫 번째 td 내부의 이력서 목록 table
    resume_table = first_td.find("table")

    if resume_table is None:
        return None

    # tbody align="center"
    resume_tbody = resume_table.find(
        "tbody",
        attrs={"align": lambda value: value and value.lower() == "center"},
    )

    return resume_tbody


def extract_resume_nos(html: str) -> List[int]:
    """
    한 페이지 HTML에서 이력서 번호만 추출한다.

    탐색 대상:
    tbody align="center"
        > tr height="80"
        > 첫 번째 td
        > resume_detail.html?no=번호
    """
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    resume_nos: List[int] = []

    # 해당 사이트는 속성 대소문자나 공백이 섞일 수 있으므로
    # tbody 전체를 확인하면서 align=center인 것만 선택
    target_tbodies = []

    for tbody in soup.find_all("tbody"):
        align = str(
            tbody.get("align", "")
        ).strip().lower()

        if align == "center":
            target_tbodies.append(tbody)

    for tbody in target_tbodies:
        # tbody의 직속 tr만 확인
        for row in tbody.find_all(
                "tr",
                recursive=False,
        ):
            height = str(
                row.get("height", "")
            ).strip()

            if height != "80":
                continue

            direct_tds = row.find_all(
                "td",
                recursive=False,
            )

            if not direct_tds:
                continue

            first_td = direct_tds[0]

            # 첫 번째 td 안에 있는 상세 링크
            detail_link = first_td.find(
                "a",
                href=lambda href: (
                        href is not None
                        and "resume_detail.html" in href
                        and "no=" in href
                ),
            )

            if detail_link is None:
                continue

            href = detail_link.get("href", "")

            parsed_url = urlparse(href)
            query_params = parse_qs(parsed_url.query)

            no_values = query_params.get("no")

            if not no_values:
                continue

            try:
                resume_no = int(no_values[0])
            except (TypeError, ValueError):
                continue

            resume_nos.append(resume_no)

    # 한 페이지 안에서 중복 제거하면서 순서 유지
    return list(dict.fromkeys(resume_nos))


def load_progress() -> tuple[int, List[int]]:
    """
    기존 진행 파일이 있으면 마지막 처리 페이지와 수집 번호를 불러온다.
    """
    if not PROGRESS_FILE.exists():
        return START_PAGE, []

    try:
        with PROGRESS_FILE.open("r", encoding="utf-8") as file:
            progress = json.load(file)

        last_completed_page = int(
            progress.get("last_completed_page", START_PAGE - 1)
        )
        resume_nos = [
            int(value)
            for value in progress.get("resume_nos", [])
        ]

        return last_completed_page + 1, resume_nos

    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return START_PAGE, []


def save_progress(
        last_completed_page: int,
        resume_nos: List[int],
) -> None:
    """
    중간 진행 상태 저장
    """
    progress_data = {
        "last_completed_page": last_completed_page,
        "resume_nos": resume_nos,
    }

    with PROGRESS_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            progress_data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_result(resume_nos: List[int]) -> None:
    """
    최종 JSON 배열 저장
    """
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            resume_nos,
            file,
            ensure_ascii=False,
            indent=2,
        )


def request_page(
        session: requests.Session,
        page: int,
) -> str:
    """
    목록 페이지 HTML 요청

    해당 사이트는 오래된 한글 인코딩을 사용하므로
    응답 바이트를 CP949로 직접 디코딩한다.
    """
    response = session.get(
        LIST_URL,
        params={"page": page},
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return response.content.decode(
        "cp949",
        errors="replace",
    )

def main() -> None:
    session = create_session()

    current_page, loaded_nos = load_progress()

    # 순서를 유지하면서 중복 방지
    resume_nos = list(dict.fromkeys(loaded_nos))
    resume_no_set = set(resume_nos)

    print(
        f"[시작] 페이지={current_page}~{END_PAGE}, "
        f"기존 번호={len(resume_nos)}개"
    )

    try:
        for page in range(current_page, END_PAGE + 1):
            html = request_page(session, page)
            page_resume_nos = extract_resume_nos(html)

            added_count = 0

            for resume_no in page_resume_nos:
                if resume_no in resume_no_set:
                    continue

                resume_no_set.add(resume_no)
                resume_nos.append(resume_no)
                added_count += 1

            save_progress(
                last_completed_page=page,
                resume_nos=resume_nos,
            )

            print(
                f"[{page:04d}/{END_PAGE}] "
                f"페이지 추출={len(page_resume_nos)}개, "
                f"신규={added_count}개, "
                f"누적={len(resume_nos)}개"
            )

            if page < END_PAGE:
                time.sleep(
                    random.uniform(
                        MIN_DELAY_SEC,
                        MAX_DELAY_SEC,
                    )
                )

    except KeyboardInterrupt:
        print("\n[중단] 현재까지의 진행 상태를 저장했습니다.")

    except requests.RequestException as error:
        print(f"\n[요청 오류] {error}")
        print("[안내] 현재까지의 진행 상태는 저장되어 있습니다.")

    except Exception as error:
        print(f"\n[처리 오류] {type(error).__name__}: {error}")
        print("[안내] 현재까지의 진행 상태는 저장되어 있습니다.")

    finally:
        save_result(resume_nos)
        session.close()

        print(f"[저장 완료] {OUTPUT_FILE.resolve()}")
        print(f"[최종 개수] {len(resume_nos)}개")


if __name__ == "__main__":
    main()