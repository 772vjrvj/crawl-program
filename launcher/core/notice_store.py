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
    공지 숨김 정보를 JSON 파일로 저장한다.

    원본 파일에 바로 저장하지 않고 임시 파일에 먼저 저장한 뒤
    임시 파일을 원본 파일로 교체하여 파일 손상 가능성을 줄인다.

    Args:
        path:
            공지 숨김 정보를 저장할 파일 경로
            예: data/notice_ack.json

        ack_map:
            공지 ID와 숨김 처리 시간을 담은 딕셔너리
            예: {"NOTICE_001": 1784371234}
    """

    # 저장할 파일의 상위 폴더가 없으면 생성한다.
    # parents=True: 상위 폴더까지 함께 생성
    # exist_ok=True: 폴더가 이미 있어도 오류를 발생시키지 않음
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 원본 파일의 확장자를 .tmp로 변경하여 임시 파일 경로를 만든다.
    # 예: notice_ack.json → notice_ack.tmp
    tmp_path = path.with_suffix(".tmp")

    # 공지 숨김 정보를 JSON 문자열로 변환한 뒤 임시 파일에 저장한다.
    tmp_path.write_text(
        json.dumps(
            ack_map,

            # 한글을 유니코드 코드가 아닌 실제 한글로 저장한다.
            ensure_ascii=False,

            # JSON 내용을 두 칸 들여쓰기로 보기 좋게 저장한다.
            indent=2,
        ),

        # 한글이 깨지지 않도록 UTF-8 인코딩을 사용한다.
        encoding="utf-8",
    )

    # 임시 파일 저장이 정상적으로 완료되면
    # 임시 파일을 원본 파일 경로로 이동하여 기존 파일을 교체한다.
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
    # NOTICE_001 → 1000 → 이미 만료됨 → 삭제
    # NOTICE_002 → 3000 → 아직 유효함 → 유지
    # NOTICE_003 → 5000 → 아직 유효함 → 유지
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