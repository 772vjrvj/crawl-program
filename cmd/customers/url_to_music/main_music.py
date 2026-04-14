# mp4_url_to_mp3.py
from pathlib import Path
import subprocess

# 네이버 링크
VIDEO_URL = r"https://b01-kr-naver-vod.pstatic.net/blog/a/read/v2/VOD_ALPHA/blog9_2009_03_15_1400/899ebe26fa83ce4f6f2f0d67c0375456_wodrlgo.mp4?_lsu_sa_=6f5505f6f1a969b6c3dcd54a6fa5dab26ebf3ff8830d5f40393741c5870436e5b3269aa568d5ae03a0bd3f621e3ecbea4bbe8d3db371b82e5f3f9c09f2c63366339cb0aa7e0a0c962e9e8e27c7b3d346&ratio=280"


OUTPUT_MP3 = "naver_blog_audio.mp3"


def get_ffmpeg_path() -> Path:
    # 실행경로 기준
    ffmpeg_path = Path.cwd() / "resources" / "customers" / "naver_shop_total" / "bin" / "ffmpeg.exe"
    if not ffmpeg_path.exists():
        raise FileNotFoundError(f"ffmpeg.exe 파일을 찾을 수 없습니다: {ffmpeg_path}")
    return ffmpeg_path


def mp4_url_to_mp3(video_url: str, output_mp3: str) -> None:
    ffmpeg_path = get_ffmpeg_path()
    output_path = Path.cwd() / output_mp3

    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", video_url,
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        str(output_path),
    ]

    print(f"[시작] ffmpeg: {ffmpeg_path}")
    print(f"[시작] 저장파일: {output_path}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    if result.returncode != 0:
        print("[실패] MP3 변환 실패")
        print(result.stderr)

        if "403" in result.stderr:
            print("[안내] URL 토큰이 만료됐거나 접근이 막혔습니다. 새 mp4 URL로 다시 시도하세요.")
        elif "404" in result.stderr:
            print("[안내] mp4 주소가 더 이상 유효하지 않습니다.")
        return

    print(f"[완료] MP3 저장 완료: {output_path}")


if __name__ == "__main__":
    mp4_url_to_mp3(VIDEO_URL, OUTPUT_MP3)