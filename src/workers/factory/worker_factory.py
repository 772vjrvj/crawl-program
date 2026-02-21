# src/workers/factory/site.py

from __future__ import annotations

from typing import Dict, Type
from enum import Enum

from src.workers.api_base_worker import BaseApiWorker
from src.workers.main.api_naver_band_member_set_worker import (
    ApiNaverBandMemberSetLoadWorker,
)


# =========================================================
# Worker Type Enum
# =========================================================
class WorkerType(str, Enum):
    NAVER_BAND_MEMBER = "NAVER_BAND_MEMBER"


# =========================================================
# Worker Class Map
# =========================================================
WORKER_CLASS_MAP: Dict[WorkerType, Type[BaseApiWorker]] = {
    WorkerType.NAVER_BAND_MEMBER: ApiNaverBandMemberSetLoadWorker,
}


# =========================================================
# Factory Function
# =========================================================
def create_worker(worker_type: WorkerType) -> BaseApiWorker:
    """
    WorkerType 기반으로 Worker 인스턴스 생성
    """
    worker_cls = WORKER_CLASS_MAP.get(worker_type)

    if worker_cls is None:
        raise ValueError(f"Unsupported worker type: {worker_type}")

    return worker_cls()