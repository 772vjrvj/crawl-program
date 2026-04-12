import os
import sys
import shutil
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def get_base_dir() -> Path:
    # exe 빌드 대응
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_unique_path(dest_dir: Path, filename: str) -> Path:
    target = dest_dir / filename
    if not target.exists():
        return target

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    idx = 1

    while True:
        new_name = f"{stem}({idx}){suffix}"
        new_target = dest_dir / new_name
        if not new_target.exists():
            return new_target
        idx += 1


def main():
    base_dir = get_base_dir()
    notice_dir = base_dir / "notice"
    notice_img_dir = base_dir / "notice_img"

    if not notice_dir.exists() or not notice_dir.is_dir():
        print(f"[실패] notice 폴더가 없습니다: {notice_dir}")
        return

    notice_img_dir.mkdir(exist_ok=True)

    success_count = 0
    fail_count = 0
    total_found = 0
    fail_list = []

    print(f"실행 경로 : {base_dir}")
    print(f"원본 폴더 : {notice_dir}")
    print(f"대상 폴더 : {notice_img_dir}")
    print("이미지 검색 시작...\n")

    for root, dirs, files in os.walk(notice_dir):
        for file_name in files:
            ext = Path(file_name).suffix.lower()
            if ext not in IMAGE_EXTS:
                continue

            total_found += 1
            src_path = Path(root) / file_name

            try:
                dest_path = get_unique_path(notice_img_dir, file_name)
                shutil.copy2(src_path, dest_path)
                success_count += 1
                print(f"[성공] {src_path} -> {dest_path.name}")
            except Exception as e:
                fail_count += 1
                fail_list.append((str(src_path), str(e)))
                print(f"[실패] {src_path} / {e}")

    print("\n" + "=" * 60)
    print("작업 완료")
    print(f"전체 이미지 발견 수 : {total_found}")
    print(f"복사 성공 수       : {success_count}")
    print(f"복사 실패 수       : {fail_count}")
    print("=" * 60)

    if fail_list:
        print("\n실패 목록")
        for idx, (path, err) in enumerate(fail_list, 1):
            print(f"{idx}. {path}")
            print(f"   사유: {err}")


if __name__ == "__main__":
    main()