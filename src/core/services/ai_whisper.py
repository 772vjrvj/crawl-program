from __future__ import annotations

import threading
from typing import Optional

_model: Optional[object] = None
_lock = threading.Lock()


def init(model_size: str = "small") -> None:
    """
    프로그램 시작 시 Whisper 모델을 1회 로딩합니다.
    """
    global _model

    if _model is not None:
        return

    with _lock:
        if _model is not None:
            return

        import whisper

        print("🤖 Whisper 모델 로딩 중...")
        _model = whisper.load_model(model_size)
        print("✅ Whisper 모델 로딩 완료")


def get_model():
    """
    Whisper 모델을 반환합니다.
    init()이 먼저 호출되어 있어야 합니다.
    """
    if _model is None:
        raise RuntimeError("Whisper 모델이 초기화되지 않았습니다. init()을 먼저 호출하세요.")
    return _model


def transcribe(audio_path: str, language: str = "ko"):
    """
    편의 함수: 음성 파일을 바로 텍스트로 변환합니다.
    """
    model = get()
    return model.transcribe(audio_path, language=language, fp16=False)