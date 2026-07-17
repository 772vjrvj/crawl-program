from __future__ import annotations

import json
from typing import Any

import requests


# ============================================================
# 직접 수정하는 설정값
# ============================================================

# 로컬 Spring Boot 서버
BASE_URL = "http://localhost"

# 서버가 8080 포트라면:
# BASE_URL = "http://localhost:8080"

# application-local.yaml의 app.admin.update-key와 동일한 값
ADMIN_KEY = "gb7-admin-update-key-1234"

# 키를 발급할 프로그램 ID
PROGRAM_ID = "NAVER_BAND_MEMBER"

# 관리자 확인용 이름
KEY_NAME = "고객 A 1번 아이디"

# 만료일
# 형식: YYYY-MM-DDTHH:MM:SS
EXPIRE_AT: str | None = "2027-07-17T23:59:59"

# 만료일 없이 계속 사용하려면:
# EXPIRE_AT = None

# 요청 제한 시간
TIMEOUT_SECONDS = 30


# ============================================================
# API 설정
# ============================================================

API_URL = (
    f"{BASE_URL}"
    "/launcher/admin/api/v1/program-keys"
)


def create_launcher_key() -> dict[str, Any]:
    """
    Spring Boot 관리자 API를 호출해
    새로운 런처 프로그램 키를 생성한다.
    """

    payload: dict[str, Any] = {
        "programId": PROGRAM_ID,
        "keyName": KEY_NAME,
        "expireAt": EXPIRE_AT,
    }

    headers = {
        "X-Admin-Key": ADMIN_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    print("=" * 80)
    print("GB7 런처 프로그램 키 생성")
    print("=" * 80)

    print(f"\nAPI URL    : {API_URL}")
    print(f"PROGRAM_ID : {PROGRAM_ID}")
    print(f"KEY_NAME   : {KEY_NAME}")
    print(f"EXPIRE_AT  : {EXPIRE_AT}")

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )

    print(f"\nHTTP 상태 코드: {response.status_code}")

    if response.status_code == 401:
        raise RuntimeError(
            "401 Unauthorized: ADMIN_KEY를 확인하세요."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "403 Forbidden: Spring Security 또는 CSRF 설정을 확인하세요."
        )

    if response.status_code != 201:
        try:
            error_data = response.json()

            raise RuntimeError(
                json.dumps(
                    error_data,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        except ValueError:
            raise RuntimeError(response.text)

    try:
        return response.json()

    except ValueError as exc:
        raise RuntimeError(
            f"JSON 응답이 아닙니다.\n{response.text}"
        ) from exc


def print_result(result: dict[str, Any]) -> None:
    """
    생성된 키 정보를 출력한다.
    """

    launcher_key = result.get("launcherKey")

    print("\n" + "=" * 80)
    print("런처 키 생성 성공")
    print("=" * 80)

    print(f"DB ID        : {result.get('id')}")
    print(f"PROGRAM_ID   : {result.get('programId')}")
    print(f"KEY_NAME     : {result.get('keyName')}")
    print(f"KEY_PREFIX   : {result.get('keyPrefix')}")
    print(f"ENABLED      : {result.get('enabled')}")
    print(f"EXPIRE_AT    : {result.get('expireAt')}")
    print(f"CREATED_AT   : {result.get('createdAt')}")

    print("\n[중요] 아래 원본 키는 지금 한 번만 확인할 수 있습니다.")
    print("-" * 80)
    print(launcher_key)
    print("-" * 80)

    print(
        "\n런처 app.json의 launcher_key에 "
        "위 값을 입력하세요."
    )


def main() -> None:
    """
    프로그램 시작 함수
    """

    try:
        result = create_launcher_key()
        print_result(result)

    except requests.ConnectionError:
        print(
            "\n[실패] Spring Boot 서버에 연결할 수 없습니다."
        )

    except requests.Timeout:
        print("\n[실패] API 요청 시간이 초과되었습니다.")

    except Exception as exc:
        print(f"\n[실패] {exc}")


if __name__ == "__main__":
    main()