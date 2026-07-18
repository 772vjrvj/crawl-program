# launcher/etc/cloudflare.py
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import urlretrieve

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError
from requests.exceptions import RequestException


# ============================================================
# Cloudflare R2 접속 정보
# ============================================================

# Cloudflare R2 Endpoint
#
# 예:
# https://xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.r2.cloudflarestorage.com
R2_ENDPOINT = (
    "https://f68db01425de9db33962c6711739eb80"
    ".r2.cloudflarestorage.com"
)

# Cloudflare R2 API Access Key
#
# 주의:
# - 관리자 PC에서만 사용한다.
# - 고객에게 배포하는 런처에는 넣지 않는다.
# - GitHub 등 공개 저장소에 올리지 않는다.
R2_ACCESS_KEY = "aecd6b971cfa8aa5913cf9024e3df1eb"

# Cloudflare R2 API Secret Key
R2_SECRET_KEY = "4cf50848f49de1f3c8d8395d16e96444bb088411b0b3341732e3784ff34b334b"


# ============================================================
# 웹서버 릴리스 등록 API 정보
# ============================================================

# Spring Boot 웹서버 기본 주소
#
# 마지막에 /를 넣지 않는다.
WEB_SERVER_URL = "https://goodbye772.com"
# WEB_SERVER_URL = "http://localhost"

# 배포 등록 API 전용 키
#
# 서버의 launcher.release-key 값과 같아야 한다.
#
# API 요청 시 다음 헤더로 전송된다.
# X-Release-Key: RELEASE_KEY
RELEASE_KEY = "gb7-admin-update-key-1234"

# 웹서버 요청 제한 시간
API_TIMEOUT_SEC = 30


# ============================================================
# 프로그램 배포 정보
# ============================================================

# 배포 대상 프로그램 ID
PROGRAM_ID = "NAVER_PLACE_LOC_ALL"

# 프로그램 버전
VERSION = "2.0.2"

# Cloudflare R2 버전 폴더명
DIR_NAME = "v2_0_2"

# Cloudflare R2 ZIP 파일명
FILE_NAME = "v2_0_2.zip"

# 신규 릴리스 사용 여부
ENABLED = True

# ============================================================
# 로컬 Cloudflare 버전 관리 폴더
# ============================================================

# 모든 프로그램의 배포 ZIP 파일이 저장되는 최상위 폴더
VERSION_ROOT_DIR = Path(
    r"E:\나의 목록\cloudflare\version"
)



# ============================================================
# Cloudflare R2 파일 정보
# ============================================================

# Cloudflare R2 버킷 이름
BUCKET_NAME = "gb7-launcher-files"

# R2 버킷 내부의 실제 객체 경로
#
# 결과:
# NAVER_BAND_MEMBER/v1_0_2/v1_0_2.zip
#
# 버킷 이름은 포함하지 않는다.
OBJECT_KEY = (
    f"{PROGRAM_ID}/"
    f"{DIR_NAME}/"
    f"{FILE_NAME}"
)


# ============================================================
# 로컬 원본 ZIP 파일
# ============================================================

# 결과 예시:
# E:\나의 목록\cloudflare\version
# \NAVER_PLACE_LOC_ALL\v2_0_2\v2_0_2.zip
SOURCE_PATH = (
        VERSION_ROOT_DIR
        / PROGRAM_ID
        / DIR_NAME
        / FILE_NAME
)

# ============================================================
# 다운로드 테스트 경로
# ============================================================

# 결과 예시:
# E:\나의 목록\cloudflare\version
# \NAVER_PLACE_LOC_ALL\v2_0_2\test
DOWNLOAD_DIR = (
        VERSION_ROOT_DIR
        / PROGRAM_ID
        / DIR_NAME
        / "test"
)

# 실제 다운로드될 테스트 파일 경로
DOWNLOAD_PATH = (
        DOWNLOAD_DIR
        / FILE_NAME
)



def calculate_sha256(
        file_path: Path,
) -> str:
    """
    지정한 파일의 SHA-256 해시값을 계산한다.

    파일 전체를 한 번에 메모리에 올리지 않고
    1MB씩 읽으면서 SHA-256을 계산한다.

    Args:
        file_path:
            SHA-256을 계산할 파일 경로

    Returns:
        64자리 SHA-256 문자열
    """

    # SHA-256 계산 객체를 생성한다.
    sha256 = hashlib.sha256()

    # 파일을 바이너리 읽기 모드로 연다.
    #
    # r:
    # 텍스트 읽기
    #
    # rb:
    # 바이너리 읽기
    #
    # ZIP, EXE, 이미지 등의 파일은
    # 바이너리 파일이므로 rb 모드를 사용한다.
    with file_path.open("rb") as file:

        # 파일을 1MB씩 반복해서 읽는다.
        while chunk := file.read(
                1024 * 1024
        ):
            # 현재 읽은 데이터를
            # SHA-256 계산에 추가한다.
            sha256.update(chunk)

    # 계산 결과를 16진수 문자열로 반환한다.
    return sha256.hexdigest()


def validate_source_file() -> None:
    """
    로컬 원본 ZIP 파일이 정상적으로 존재하는지 확인한다.
    """

    # 지정한 경로에 파일이 없으면 실행을 중단한다.
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            "원본 ZIP 파일을 찾을 수 없습니다.\n"
            f"경로: {SOURCE_PATH}"
        )


def validate_release_settings() -> None:
    """
    웹서버 릴리스 등록에 필요한 설정값을 확인한다.
    """

    if not WEB_SERVER_URL.strip():
        raise ValueError(
            "WEB_SERVER_URL이 설정되지 않았습니다."
        )

    if not RELEASE_KEY.strip():
        raise ValueError(
            "RELEASE_KEY가 설정되지 않았습니다."
        )

    if not PROGRAM_ID.strip():
        raise ValueError(
            "PROGRAM_ID가 설정되지 않았습니다."
        )

    if not VERSION.strip():
        raise ValueError(
            "VERSION이 설정되지 않았습니다."
        )

    if not DIR_NAME.strip():
        raise ValueError(
            "DIR_NAME이 설정되지 않았습니다."
        )

    if not FILE_NAME.strip():
        raise ValueError(
            "FILE_NAME이 설정되지 않았습니다."
        )

    # 버전을 기준으로 예상되는 폴더명을 계산한다.
    #
    # 예:
    # 1.0.2
    # -> v1_0_2
    expected_dir_name = (
            "v"
            + VERSION.replace(".", "_")
    )

    # 버전과 폴더명이 서로 다르면
    # 잘못된 R2 경로가 만들어질 수 있으므로 중단한다.
    if DIR_NAME != expected_dir_name:
        raise ValueError(
            "VERSION과 DIR_NAME이 일치하지 않습니다.\n"
            f"VERSION          : {VERSION}\n"
            f"현재 DIR_NAME   : {DIR_NAME}\n"
            f"예상 DIR_NAME   : {expected_dir_name}"
        )

    # 업데이트 파일은 ZIP 파일만 허용한다.
    if not FILE_NAME.lower().endswith(".zip"):
        raise ValueError(
            "FILE_NAME은 .zip 파일이어야 합니다."
        )


def create_r2_client():
    """
    Cloudflare R2에 접근할 boto3 S3 클라이언트를 생성한다.

    Cloudflare R2는 AWS S3 호환 API를 제공하므로
    boto3의 S3 클라이언트를 사용할 수 있다.
    """

    return boto3.client(
        service_name="s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )


def print_file_information(
        title: str,
        file_path: Path,
) -> tuple[int, str]:
    """
    로컬 파일의 경로, 크기, SHA-256을 출력한다.

    Args:
        title:
            출력할 구분 제목

        file_path:
            확인할 파일 경로

    Returns:
        파일 크기와 SHA-256 튜플
    """

    # 파일 크기를 Byte 단위로 가져온다.
    file_size = file_path.stat().st_size

    # 파일 SHA-256을 계산한다.
    file_sha256 = calculate_sha256(
        file_path
    )

    print(f"\n[{title}]")
    print(f"파일 경로 : {file_path.resolve()}")
    print(f"파일 크기 : {file_size} bytes")
    print(f"SHA-256   : {file_sha256}")

    return file_size, file_sha256


def register_release(
        size_bytes: int,
        sha256: str,
) -> str:
    """
    웹서버 릴리스 등록 API를 호출한다.

    R2 파일 검증이 모두 성공한 뒤에만 호출한다.

    Args:
        size_bytes:
            검증 완료된 ZIP 파일 크기

        sha256:
            검증 완료된 ZIP 파일 SHA-256

    Returns:
        CREATED:
            신규 릴리스 등록 성공

        ALREADY_EXISTS:
            같은 프로그램과 버전이 이미 등록됨
    """

    # API에 전달할 설정값을 확인한다.
    validate_release_settings()

    # 릴리스 등록 API 주소
    #
    # 예:
    # https://goodbye772.com
    # /launcher/api/v1
    # /programs/NAVER_BAND_MEMBER/releases
    api_url = (
        f"{WEB_SERVER_URL.rstrip('/')}"
        f"/launcher/api/v1"
        f"/programs/{PROGRAM_ID}"
        f"/releases"
    )

    # API 요청 헤더
    headers = {
        "Content-Type": "application/json",
        "X-Release-Key": RELEASE_KEY,
    }

    # LAUNCHER_RELEASE 테이블에 저장할 데이터
    payload = {
        "version": VERSION,
        "dirName": DIR_NAME,
        "fileName": FILE_NAME,
        "sha256": sha256,
        "sizeBytes": size_bytes,
        "enabled": ENABLED,
    }

    print("\n[13] 웹서버 릴리스 등록")

    print(f"API 주소    : {api_url}")
    print(f"프로그램 ID : {PROGRAM_ID}")
    print(f"버전        : {VERSION}")
    print(f"폴더명      : {DIR_NAME}")
    print(f"파일명      : {FILE_NAME}")
    print(f"파일 크기   : {size_bytes} bytes")
    print(f"SHA-256     : {sha256}")
    print(f"활성화 여부 : {ENABLED}")

    # 웹서버에 신규 릴리스 등록을 요청한다.
    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=API_TIMEOUT_SEC,
    )

    # 신규 INSERT에 성공한 경우
    if response.status_code == 201:
        print(
            "웹서버 릴리스 등록에 성공했습니다."
        )

        return "CREATED"

    # 동일한 PROGRAM_ID와 VERSION이
    # 이미 등록되어 있는 경우
    if response.status_code == 409:
        print(
            "동일한 프로그램 버전이 "
            "이미 웹서버에 등록되어 있습니다."
        )

        return "ALREADY_EXISTS"

    # 오류 응답 내용이 있으면 출력에 포함한다.
    response_body = response.text.strip()

    if not response_body:
        response_body = "(응답 내용 없음)"

    # 예상하지 못한 상태코드는 실패로 처리한다.
    raise RuntimeError(
        "웹서버 릴리스 등록에 실패했습니다.\n"
        f"HTTP 상태 : {response.status_code}\n"
        f"응답 내용 : {response_body}"
    )


def main() -> None:
    """
    Cloudflare R2 다운로드 및 웹서버 등록 테스트를 실행한다.

    실행 순서:

    1. 로컬 원본 ZIP 확인
    2. 로컬 원본 크기 및 SHA-256 계산
    3. Cloudflare R2 객체 존재 여부 확인
    4. R2 객체 크기와 원본 크기 비교
    5. Presigned URL 생성
    6. Presigned URL로 파일 다운로드
    7. 다운로드 파일 크기 및 SHA-256 계산
    8. 원본 파일과 다운로드 파일 비교
    9. 모든 검증 성공
    10. 웹서버 릴리스 등록 API 호출
    """

    print(
        "========================================"
    )
    print(
        " Cloudflare R2 파일 다운로드 검증"
    )
    print(
        "========================================"
    )

    # ========================================================
    # 1. 로컬 원본 파일 확인
    # ========================================================

    print("\n[1] 로컬 원본 파일 확인")

    validate_source_file()

    print("로컬 원본 파일을 확인했습니다.")
    print(f"원본 경로: {SOURCE_PATH}")

    # ========================================================
    # 2. 로컬 원본 파일 정보 계산
    # ========================================================

    print("\n[2] 로컬 원본 파일 정보 계산")

    source_size, source_sha256 = (
        print_file_information(
            title="로컬 원본 파일",
            file_path=SOURCE_PATH,
        )
    )

    # ========================================================
    # 3. Cloudflare R2 클라이언트 생성
    # ========================================================

    print("\n[3] Cloudflare R2 연결")

    s3 = create_r2_client()

    print(
        "Cloudflare R2 클라이언트를 생성했습니다."
    )

    # ========================================================
    # 4. R2 객체 존재 여부 및 정보 확인
    # ========================================================

    print("\n[4] R2 객체 확인")

    # head_object는 파일 전체를 다운로드하지 않고
    # 객체의 존재 여부와 메타데이터만 확인한다.
    object_info = s3.head_object(
        Bucket=BUCKET_NAME,
        Key=OBJECT_KEY,
    )

    # R2에 저장된 파일 크기
    r2_size = object_info[
        "ContentLength"
    ]

    # R2 객체의 Content-Type
    content_type = object_info.get(
        "ContentType",
        "",
    )

    # R2 객체의 최종 수정 시간
    last_modified = object_info.get(
        "LastModified"
    )

    print(f"버킷       : {BUCKET_NAME}")
    print(f"객체 경로  : {OBJECT_KEY}")
    print(f"파일 타입  : {content_type}")
    print(f"R2 크기    : {r2_size} bytes")
    print(f"수정 시간  : {last_modified}")

    # ========================================================
    # 5. 로컬 원본과 R2 객체 크기 비교
    # ========================================================

    print(
        "\n[5] 원본 파일과 R2 객체 크기 비교"
    )

    if source_size != r2_size:
        raise ValueError(
            "로컬 원본 파일과 "
            "R2 객체 크기가 다릅니다.\n"
            f"로컬 원본 크기: {source_size} bytes\n"
            f"R2 객체 크기  : {r2_size} bytes"
        )

    print(
        "로컬 원본 파일과 R2 객체의 "
        "크기가 일치합니다."
    )

    # ========================================================
    # 6. Presigned URL 생성
    # ========================================================

    print("\n[6] Presigned URL 생성")

    # 지정된 R2 객체를 다운로드할 수 있는
    # 임시 URL을 생성한다.
    #
    # 이 URL을 사용하는 쪽에서는
    # Access Key나 Secret Key가 필요하지 않다.
    download_url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": OBJECT_KEY,
        },

        # URL 유효 시간
        #
        # 600초 = 10분
        ExpiresIn=600,
    )

    print("Presigned URL을 생성했습니다.")
    print("유효 시간: 600초")

    # 필요할 때만 아래 주석을 해제해서 URL을 확인한다.
    #
    # Presigned URL에는 임시 인증 정보가 포함되므로
    # 불필요하게 로그에 남기지 않는 것이 좋다.
    #
    # print(download_url)

    # ========================================================
    # 7. 다운로드 폴더 준비
    # ========================================================

    print("\n[7] 다운로드 폴더 준비")

    # 다운로드 폴더가 없으면 생성한다.
    DOWNLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 이전 테스트 파일이 존재하면 삭제한다.
    if DOWNLOAD_PATH.exists():
        DOWNLOAD_PATH.unlink()

        print(
            "기존 다운로드 테스트 파일을 삭제했습니다."
        )

    print(f"다운로드 경로: {DOWNLOAD_PATH}")

    # ========================================================
    # 8. Presigned URL로 파일 다운로드
    # ========================================================

    print("\n[8] R2 파일 다운로드")

    # 생성된 Presigned URL을 사용해
    # R2 파일을 로컬 테스트 폴더에 다운로드한다.
    urlretrieve(
        download_url,
        str(DOWNLOAD_PATH),
    )

    print("파일 다운로드가 완료되었습니다.")

    # 다운로드 결과 파일이
    # 실제로 생성됐는지 확인한다.
    if not DOWNLOAD_PATH.is_file():
        raise FileNotFoundError(
            "다운로드 결과 파일이 "
            "생성되지 않았습니다.\n"
            f"경로: {DOWNLOAD_PATH}"
        )

    # ========================================================
    # 9. 다운로드 파일 정보 계산
    # ========================================================

    print("\n[9] 다운로드 파일 정보 계산")

    downloaded_size, downloaded_sha256 = (
        print_file_information(
            title="R2 다운로드 파일",
            file_path=DOWNLOAD_PATH,
        )
    )

    # ========================================================
    # 10. R2 객체 크기와 다운로드 파일 크기 비교
    # ========================================================

    print(
        "\n[10] R2 객체와 다운로드 파일 크기 비교"
    )

    if downloaded_size != r2_size:
        raise ValueError(
            "R2 객체와 다운로드 파일의 "
            "크기가 다릅니다.\n"
            f"R2 객체 크기   : {r2_size} bytes\n"
            f"다운로드 크기 : {downloaded_size} bytes"
        )

    print(
        "R2 객체와 다운로드 파일의 "
        "크기가 일치합니다."
    )

    # ========================================================
    # 11. 원본과 다운로드 파일 크기 비교
    # ========================================================

    print(
        "\n[11] 원본과 다운로드 파일 크기 비교"
    )

    if downloaded_size != source_size:
        raise ValueError(
            "원본과 다운로드 파일의 "
            "크기가 다릅니다.\n"
            f"원본 크기     : {source_size} bytes\n"
            f"다운로드 크기 : {downloaded_size} bytes"
        )

    print(
        "원본과 다운로드 파일의 "
        "크기가 일치합니다."
    )

    # ========================================================
    # 12. 원본과 다운로드 파일 SHA-256 비교
    # ========================================================

    print(
        "\n[12] 원본과 다운로드 파일 SHA-256 비교"
    )

    if downloaded_sha256 != source_sha256:
        raise ValueError(
            "원본과 다운로드 파일의 "
            "SHA-256이 다릅니다.\n"
            f"원본 SHA-256:\n"
            f"{source_sha256}\n\n"
            f"다운로드 SHA-256:\n"
            f"{downloaded_sha256}"
        )

    print(
        "원본과 다운로드 파일의 "
        "SHA-256이 일치합니다."
    )

    # ========================================================
    # 13. 웹서버 릴리스 등록
    #
    # 여기까지 도달했다는 것은 아래 검증이
    # 모두 성공했다는 뜻이다.
    #
    # - R2 객체 존재
    # - 원본과 R2 객체 크기 일치
    # - Presigned URL 다운로드 성공
    # - 다운로드 파일 크기 일치
    # - 다운로드 파일 SHA-256 일치
    #
    # 따라서 마지막에만 DB 등록 API를 호출한다.
    # ========================================================

    release_result = register_release(
        size_bytes=source_size,
        sha256=source_sha256,
    )

    # ========================================================
    # 최종 결과
    # ========================================================

    print(
        "\n========================================"
    )
    print(
        " Cloudflare R2 배포 검증 완료"
    )
    print(
        "========================================"
    )

    print(
        "\n다음 항목이 모두 정상입니다."
    )
    print("- R2 연결")
    print("- R2 객체 존재")
    print("- Presigned URL 생성")
    print("- Presigned URL 다운로드")
    print("- 파일 크기 일치")
    print("- SHA-256 일치")

    if release_result == "CREATED":
        print("- 웹서버 신규 릴리스 등록 성공")

    elif release_result == "ALREADY_EXISTS":
        print("- 웹서버에 동일 버전 등록 확인")

    print(
        "\n서버 등록 정보"
    )
    print(f"PROGRAM_ID : {PROGRAM_ID}")
    print(f"VERSION    : {VERSION}")
    print(f"DIR_NAME   : {DIR_NAME}")
    print(f"FILE_NAME  : {FILE_NAME}")
    print(f"SIZE_BYTES : {source_size}")
    print(f"SHA256     : {source_sha256}")


if __name__ == "__main__":
    try:
        main()

    except ClientError as error:
        # boto3를 통해 R2에서 반환된 API 오류
        print(
            "\n========================================"
        )
        print(
            " R2 API 오류"
        )
        print(
            "========================================"
        )

        error_response = error.response.get(
            "Error",
            {},
        )

        error_code = error_response.get(
            "Code",
            "",
        )

        error_message = error_response.get(
            "Message",
            str(error),
        )

        print(f"오류 코드: {error_code}")
        print(f"오류 내용: {error_message}")

    except BotoCoreError as error:
        # boto3 내부 연결 및 설정 오류
        print(
            "\n========================================"
        )
        print(
            " boto3 연결 오류"
        )
        print(
            "========================================"
        )

        print(error)

    except RequestException as error:
        # 웹서버 API 연결 실패
        #
        # 예:
        # - 서버 접속 실패
        # - 연결 시간 초과
        # - SSL 연결 오류
        print(
            "\n========================================"
        )
        print(
            " 웹서버 API 연결 오류"
        )
        print(
            "========================================"
        )

        print(error)

    except FileNotFoundError as error:
        # 로컬 원본 파일이나
        # 다운로드 파일이 없는 경우
        print(
            "\n========================================"
        )
        print(
            " 파일 오류"
        )
        print(
            "========================================"
        )

        print(error)

    except ValueError as error:
        # 설정값, 크기 또는 SHA-256이
        # 올바르지 않은 경우
        print(
            "\n========================================"
        )
        print(
            " 파일 검증 실패"
        )
        print(
            "========================================"
        )

        print(error)

    except RuntimeError as error:
        # 웹서버가 201 또는 409가 아닌
        # 오류 상태를 반환한 경우
        print(
            "\n========================================"
        )
        print(
            " 웹서버 릴리스 등록 실패"
        )
        print(
            "========================================"
        )

        print(error)

    except Exception as error:
        # 위에서 처리하지 못한 기타 오류
        print(
            "\n========================================"
        )
        print(
            " 테스트 중 오류 발생"
        )
        print(
            "========================================"
        )

        print(error)