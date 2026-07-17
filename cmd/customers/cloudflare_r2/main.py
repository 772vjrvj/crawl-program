from __future__ import annotations

from getpass import getpass
from pathlib import Path
from urllib.request import urlretrieve

import boto3
from botocore.exceptions import BotoCoreError, ClientError


BUCKET_NAME = "gb7-launcher-files"
OBJECT_KEY = "test.txt"
DOWNLOAD_PATH = Path("downloaded_test.txt")


def main() -> None:
    print("=== Cloudflare R2 연결 테스트 ===")

    endpoint = input("R2 Endpoint: ").strip()
    access_key = input("Access Key ID: ").strip()
    secret_key = getpass("Secret Access Key: ")

    s3 = boto3.client(
        service_name="s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    print("\n[1] 버킷 파일 목록 확인")

    response = s3.list_objects_v2(
        Bucket=BUCKET_NAME,
    )

    objects = response.get("Contents", [])

    if not objects:
        print("버킷에 파일이 없습니다.")
        return

    object_keys = []

    for item in objects:
        key = item["Key"]
        size = item["Size"]

        object_keys.append(key)
        print(f"- {key} ({size} bytes)")

    if OBJECT_KEY not in object_keys:
        print(f"\n'{OBJECT_KEY}' 파일을 찾지 못했습니다.")
        print("업로드한 실제 파일명으로 OBJECT_KEY를 수정하세요.")
        return

    print("\n[2] 600초 Presigned URL 생성")

    download_url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": OBJECT_KEY,
        },
        ExpiresIn=600,
    )

    print("Presigned URL 생성 성공")

    print("\n[3] Presigned URL로 파일 다운로드")

    urlretrieve(
        download_url,
        DOWNLOAD_PATH,
    )

    print(f"다운로드 성공: {DOWNLOAD_PATH.resolve()}")
    print(f"파일 크기: {DOWNLOAD_PATH.stat().st_size} bytes")


if __name__ == "__main__":
    try:
        main()
    except (ClientError, BotoCoreError) as exc:
        print("\nR2 API 오류가 발생했습니다.")
        print(exc)
    except Exception as exc:
        print("\n테스트 중 오류가 발생했습니다.")
        print(exc)