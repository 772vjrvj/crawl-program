# src/workers/worker_factory.py
from __future__ import annotations  # === 신규 ===

import importlib
from typing import Any, Dict, Type

from src.workers.api_base_worker import BaseApiWorker

_WORKER_CLASS_CACHE: Dict[str, Type[BaseApiWorker]] = {}


def _load_worker_class(dotted: str) -> Type[BaseApiWorker]:
    """
    'pkg.module:ClassName' 형태의 문자열을 import 해서 클래스 반환
    """
    s = str(dotted or "").strip()
    if not s:
        raise ValueError("worker_class 문자열이 비어있습니다.")

    cached = _WORKER_CLASS_CACHE.get(s)
    if cached is not None:
        return cached

    if ":" not in s:
        raise ValueError(f"worker_class 형식이 잘못되었습니다. '모듈:클래스' 이어야 합니다: {s}")

    module_path, class_name = [x.strip() for x in s.split(":", 1)]
    if not module_path or not class_name:
        raise ValueError(f"worker_class 형식이 잘못되었습니다: {s}")

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise ImportError(f"worker_class를 찾을 수 없습니다: {module_path}.{class_name}")

    # BaseApiWorker 상속 체크(런타임 안정성)
    if not isinstance(cls, type) or not issubclass(cls, BaseApiWorker):
        raise TypeError(f"worker_class는 BaseApiWorker를 상속해야 합니다: {s}")

    _WORKER_CLASS_CACHE[s] = cls
    return cls


def create_worker_from_site_config(site_conf: Dict[str, Any]) -> BaseApiWorker:
    """
    site config(dict)에서 worker_class 기반으로 워커 인스턴스 생성
    """
    wc = str(site_conf.get("worker_class") or "").strip()
    cls = _load_worker_class(wc)
    return cls()