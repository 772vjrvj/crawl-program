from __future__ import annotations

import json
import math
import socket
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


# -----------------------------------------------------------------------------
# 설정값: 아래 두 값만 수정한 뒤 실행하세요.
# -----------------------------------------------------------------------------
SERVICE_KEY = "3E2rNn6VTtra%2BXLH74ajtq3adwudxdzzJgF9YK%2Bdf4VrstQkauRiWM0l4bjzSq3lIG4Pa3cKJr1epN4HFp9M2Q%3D%3D"
PNU = "1168010300100130003"

BASE_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService"
MAJOR_REPAIR_ENDPOINT = "/getApImprprInfo"      # 대수선 조회
PERMIT_BASIS_ENDPOINT = "/getApBasisOulnInfo"  # 건축인허가 기본개요 조회

NUM_OF_ROWS = 100
TIMEOUT_SECONDS = 30
INCLUDE_RAW_ITEMS = False

KST = timezone(timedelta(hours=9))


class ArchHubApiError(Exception):
    """프로그램 응답으로 변환할 수 있는 건축HUB API 오류입니다."""

    def __init__(
            self,
            status: str,
            message: str,
            result_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.result_code = result_code


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_text(value: Any) -> str | None:
    """공백 또는 값이 없는 항목을 None으로 정리합니다."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def format_yyyymmdd(value: Any) -> str | None:
    """20220813 형식을 2022-08-13 형식으로 변환합니다."""
    text = clean_text(value)
    if not text:
        return None

    digits = "".join(char for char in text if char.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def parse_pnu(pnu: str) -> dict[str, str]:
    """19자리 PNU를 건축HUB API 요청 파라미터로 변환합니다."""
    pnu = pnu.strip()

    if len(pnu) != 19 or not pnu.isdigit():
        raise ValueError("PNU는 숫자 19자리여야 합니다.")

    # PNU의 11번째 자리: 1=일반, 2=산
    # 건축HUB API의 platGbCd: 0=대지, 1=산
    plat_gb_cd = {"1": "0", "2": "1"}.get(pnu[10])
    if plat_gb_cd is None:
        raise ValueError(f"지원하지 않는 PNU 필지 구분값입니다: {pnu[10]}")

    return {
        "sigunguCd": pnu[:5],
        "bjdongCd": pnu[5:10],
        "platGbCd": plat_gb_cd,
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }


def classify_api_error(
        result_code: str | None,
        message: str,
) -> ArchHubApiError:
    """공공데이터 API 오류를 프로그램용 상태값으로 변환합니다."""
    code = clean_text(result_code)
    upper_message = message.upper()

    if code == "22" or "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in upper_message:
        return ArchHubApiError(
            "DAILY_LIMIT_EXCEEDED",
            "공공데이터 API 일일 호출 한도를 초과했습니다.",
            code,
        )

    if (
            code == "23"
            or "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS"
            in upper_message
    ):
        return ArchHubApiError(
            "RATE_LIMIT_EXCEEDED",
            "공공데이터 API의 초당 호출 한도를 초과했습니다.",
            code,
        )

    if code == "05" or "SERVICETIMEOUT" in upper_message:
        return ArchHubApiError(
            "TIMEOUT",
            "공공데이터 API 응답 시간이 초과됐습니다.",
            code,
        )

    if code in {"20", "30", "31"} or any(
            keyword in upper_message
            for keyword in (
                    "SERVICE_KEY_IS_NULL",
                    "SERVICE_KEY_IS_NOT_REGISTERED",
                    "SERVICE_ACCESS_DENIED",
                    "DEADLINE_HAS_EXPIRED",
            )
    ):
        return ArchHubApiError(
            "AUTH_ERROR",
            f"공공데이터 API 인증 오류입니다: {message}",
            code,
        )

    return ArchHubApiError(
        "API_ERROR",
        f"공공데이터 API 오류입니다: {message}",
        code,
    )


def request_json(endpoint: str, request_params: dict[str, str]) -> dict[str, Any]:
    """건축HUB API를 호출하고 JSON 응답을 반환합니다."""
    params = urlencode(
        {
            # Encoding 키와 Decoding 키를 모두 입력할 수 있도록 한 번 정리합니다.
            "serviceKey": unquote(SERVICE_KEY.strip()),
            **request_params,
            "_type": "json",
        }
    )
    request = Request(
        f"{BASE_URL}{endpoint}?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise classify_api_error(str(exc.code), body) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ArchHubApiError(
            "TIMEOUT",
            "공공데이터 API 응답 시간이 초과됐습니다.",
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ArchHubApiError(
                "TIMEOUT",
                "공공데이터 API 응답 시간이 초과됐습니다.",
            ) from exc
        raise ArchHubApiError(
            "API_ERROR",
            f"공공데이터 API 연결에 실패했습니다: {exc.reason}",
        ) from exc
    except OSError as exc:
        raise ArchHubApiError(
            "API_ERROR",
            f"공공데이터 API 연결에 실패했습니다: {exc}",
        ) from exc

    # 공공데이터 게이트웨이 오류는 _type=json이어도 XML로 올 수 있습니다.
    upper_raw = raw.upper()
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in upper_raw:
        raise classify_api_error("22", raw)
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS" in upper_raw:
        raise classify_api_error("23", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArchHubApiError(
            "API_ERROR",
            f"공공데이터 API가 JSON이 아닌 응답을 반환했습니다: {raw[:500]}",
        ) from exc

    header = data.get("response", {}).get("header", {}) or {}
    result_code = clean_text(header.get("resultCode"))
    result_message = clean_text(header.get("resultMsg")) or "알 수 없는 오류"

    if result_code not in {"0", "00"}:
        raise classify_api_error(result_code, result_message)

    return data


def extract_items(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """응답에서 item 배열과 전체 건수를 꺼냅니다."""
    body = data.get("response", {}).get("body", {}) or {}
    item = (body.get("items") or {}).get("item", [])

    if isinstance(item, dict):
        item_list = [item]
    elif isinstance(item, list):
        item_list = item
    else:
        item_list = []

    try:
        total_count = int(body.get("totalCount", len(item_list)))
    except (TypeError, ValueError):
        total_count = len(item_list)

    return item_list, total_count


def fetch_all_items(
        endpoint: str,
        pnu_params: dict[str, str],
) -> list[dict[str, Any]]:
    """페이지가 여러 개인 경우 마지막 페이지까지 모두 조회합니다."""
    first_response = request_json(
        endpoint,
        {
            **pnu_params,
            "numOfRows": str(NUM_OF_ROWS),
            "pageNo": "1",
        },
    )
    all_items, total_count = extract_items(first_response)

    total_pages = math.ceil(total_count / NUM_OF_ROWS) if total_count else 1
    for page_no in range(2, total_pages + 1):
        response = request_json(
            endpoint,
            {
                **pnu_params,
                "numOfRows": str(NUM_OF_ROWS),
                "pageNo": str(page_no),
            },
        )
        page_items, _ = extract_items(response)
        all_items.extend(page_items)

    return all_items


def empty_result(
        pnu: str,
        lookup_status: str,
        lookup_message: str,
) -> dict[str, Any]:
    """조회하지 못한 경우 Y/N을 판단하지 않고 null로 반환합니다."""
    return {
        "pnu": pnu,
        "건물 정보_대수선조회상태": lookup_status,
        "건물 정보_대수선조회메시지": lookup_message,
        "건물 정보_대수선여부": None,
        "건물 정보_대수선건수": None,
        "건물 정보_최근대수선허가일": None,
        "건물 정보_대수선이력": None,
        "건물 정보_대수선조회일시": now_kst(),
    }


def make_result(
        pnu: str,
        repair_items: list[dict[str, Any]],
        basis_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """대수선 이력과 기본개요를 관리허가대장 PK로 결합합니다."""
    basis_by_pk: dict[str, dict[str, Any]] = {}
    for item in basis_items:
        pk = clean_text(item.get("mgmPmsrgstPk"))
        if pk:
            basis_by_pk[pk] = item

    confirmed_history: list[dict[str, Any]] = []
    debug_history: list[dict[str, Any]] = []
    matched_permit_count = 0

    for repair in repair_items:
        pk = clean_text(repair.get("mgmPmsrgstPk"))
        basis = basis_by_pk.get(pk or "", {})
        repair_type = clean_text(repair.get("imprprGbCdNm"))
        permit_work_type = clean_text(basis.get("archGbCdNm"))
        permit_date = format_yyyymmdd(basis.get("archPmsDay"))

        # 대수선 상세 종류가 있거나 기본개요의 건축구분이 대수선인 경우만
        # 최종 대수선 이력에 포함합니다.
        major_repair_confirmed = bool(repair_type) or permit_work_type == "대수선"

        if basis:
            matched_permit_count += 1

        if major_repair_confirmed:
            confirmed_history.append(
                {
                    "허가일": permit_date,
                    "대수선종류": repair_type,
                    "변경구분": clean_text(repair.get("imprprChangGbCdNm")),
                    "사용승인일": format_yyyymmdd(basis.get("useAprDay")),
                }
            )

        if INCLUDE_RAW_ITEMS:
            debug_history.append(
                {
                    "관리허가대장PK": pk,
                    "건물명": clean_text(repair.get("bldNm"))
                           or clean_text(basis.get("bldNm")),
                    "건축구분": permit_work_type,
                    "대수선확정": major_repair_confirmed,
                    "허가일": permit_date,
                    "기록생성일": format_yyyymmdd(repair.get("crtnDay")),
                }
            )

    # 허가일이 있는 항목을 최신순으로 정렬하고, 날짜가 없으면 마지막으로 보냅니다.
    confirmed_history.sort(
        key=lambda item: item.get("허가일") or "",
        reverse=True,
    )

    permit_dates = [
        item["허가일"]
        for item in confirmed_history
        if item.get("허가일")
    ]
    latest_permit_date = max(permit_dates) if permit_dates else None

    lookup_message = None
    if confirmed_history and len(permit_dates) < len(confirmed_history):
        lookup_message = "일부 대수선 이력에는 허가일 정보가 없습니다."

    result: dict[str, Any] = {
        "pnu": pnu,
        "건물 정보_대수선조회상태": "SUCCESS",
        "건물 정보_대수선조회메시지": lookup_message,
        "건물 정보_대수선여부": "Y" if confirmed_history else "N",
        "건물 정보_대수선건수": len(confirmed_history),
        "건물 정보_최근대수선허가일": latest_permit_date,
        "건물 정보_대수선이력": confirmed_history,
        "건물 정보_대수선조회일시": now_kst(),
    }

    if INCLUDE_RAW_ITEMS:
        result["_debug"] = {
            "대수선API원본건수": len(repair_items),
            "기본개요연결건수": matched_permit_count,
            "제외건수": len(repair_items) - len(confirmed_history),
            "판정이력": debug_history,
            "raw_major_repair_items": repair_items,
            "raw_permit_basis_items": basis_items,
        }

    return result


def main() -> int:
    if (
            not SERVICE_KEY.strip()
            or SERVICE_KEY == "발급받은 일반 인증키를 여기에 입력"
    ):
        result = empty_result(
            PNU,
            "CONFIG_ERROR",
            "파일 상단의 SERVICE_KEY에 인증키를 입력하세요.",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3

    try:
        pnu_params = parse_pnu(PNU)

        # 1. 해당 PNU의 대수선 내역 조회
        repair_items = fetch_all_items(MAJOR_REPAIR_ENDPOINT, pnu_params)

        # 대수선 상세가 없으면 기본개요 API를 호출할 필요가 없습니다.
        if not repair_items:
            basis_items: list[dict[str, Any]] = []
        else:
            # 2. 대수선 관련 건이 있을 때만 건축인허가 기본개요 조회
            basis_items = fetch_all_items(PERMIT_BASIS_ENDPOINT, pnu_params)

        # 3. mgmPmsrgstPk를 기준으로 결합
        result = make_result(PNU, repair_items, basis_items)

    except ValueError as exc:
        result = empty_result(PNU, "INVALID_PNU", str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    except ArchHubApiError as exc:
        result = empty_result(PNU, exc.status, exc.message)
        if INCLUDE_RAW_ITEMS and exc.result_code:
            result["_debug_result_code"] = exc.result_code
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
