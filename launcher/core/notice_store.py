# launcher/core/notice_store.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class NoticeAck:
    notice_id: str
    hide_until_epoch: int


def _now_epoch() -> int:
    """
    현재 시간을 epoch 초 단위로 반환한다.
    """
    return int(time.time())


def _next_day_start_epoch() -> int:
    """
    사용자 PC의 현지 시간을 기준으로
    다음 날 00:00의 epoch 값을 반환한다.

    예:
    2026-07-15 오후에 체크
    -> 2026-07-16 00:00까지 자동 팝업 숨김
    """
    now = datetime.now().astimezone()
    tomorrow = now.date() + timedelta(days=1)

    next_day_start = datetime.combine(
        tomorrow,
        datetime_time.min,
        tzinfo=now.tzinfo,
    )

    return int(next_day_start.timestamp())


def load_ack_map(path: Path) -> Dict[str, int]:
    """
    공지 숨김 정보를 읽는다.

    반환 형식:
    {
        "공지 ID": 숨김 종료 epoch
    }
    """
    if not path.exists():
        return {}

    try:
        obj = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return {}

    if not isinstance(obj, dict):
        return {}

    result: Dict[str, int] = {}

    for notice_id, hide_until in obj.items():
        if not isinstance(notice_id, str):
            continue

        notice_id = notice_id.strip()

        if not notice_id:
            continue

        if not isinstance(hide_until, int):
            continue

        result[notice_id] = hide_until

    return result


def save_ack_map(
        path: Path,
        ack_map: Dict[str, int],
) -> None:
    """
    공지 숨김 정보를 임시 파일에 저장한 뒤
    원본 파일로 교체한다.
    """
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp_path = path.with_suffix(".tmp")

    tmp_path.write_text(
        json.dumps(
            ack_map,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp_path.replace(path)


def is_hidden(
        path: Path,
        notice_id: str,
) -> bool:
    """
    해당 공지가 현재 자동 숨김 상태인지 확인한다.
    """
    notice_id = (notice_id or "").strip()

    if not notice_id:
        return False

    ack_map = load_ack_map(path)
    hide_until = ack_map.get(notice_id)

    if hide_until is None:
        return False

    return hide_until > _now_epoch()


def hide_for_day(
        path: Path,
        notice_id: str,
) -> None:
    """
    해당 공지를 오늘 자정까지만 자동으로 숨긴다.

    24시간을 더하는 방식이 아니라
    사용자 PC의 다음 날 00:00까지 숨긴다.
    """
    notice_id = (notice_id or "").strip()

    if not notice_id:
        return

    now_epoch = _now_epoch()
    ack_map = load_ack_map(path)

    # 이미 만료된 기록은 저장할 때 정리한다.
    ack_map = {
        key: hide_until
        for key, hide_until in ack_map.items()
        if hide_until > now_epoch
    }

    ack_map[notice_id] = _next_day_start_epoch()

    save_ack_map(
        path,
        ack_map,
    )