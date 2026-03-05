from __future__ import annotations

import importlib
from typing import Iterable, Set


_loaded_services: Set[str] = set()


def load_services(service_names: Iterable[str]) -> None:
    """
    서비스 이름 목록을 받아서 해당 services 모듈을 로딩하고 init() 실행
    예: "ai_whisper" -> src.core.services.ai_whisper
    """

    for name in service_names:

        if name in _loaded_services:
            continue

        module_path = f"src.core.services.{name}"

        module = importlib.import_module(module_path)

        if hasattr(module, "init"):
            module.init()

        _loaded_services.add(name)

        print(f"[service] loaded: {name}")