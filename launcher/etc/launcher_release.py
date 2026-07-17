from __future__ import annotations

import hashlib
from pathlib import Path


FILE_PATH = Path(r"E:\배포파일\v1_0_2.zip")


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            sha256.update(chunk)

    return sha256.hexdigest()


def main() -> None:
    if not FILE_PATH.is_file():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {FILE_PATH}"
        )

    print(f"파일명     : {FILE_PATH.name}")
    print(f"SHA256     : {calculate_sha256(FILE_PATH)}")
    print(f"SIZE_BYTES : {FILE_PATH.stat().st_size}")


if __name__ == "__main__":
    main()