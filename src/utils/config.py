# src/utils/config.py
from __future__ import annotations  # === 신규 ===

from typing import List, Literal, TypedDict, Final
from src.models.site import Site


# === 신규 === setting/columns dict schema 타입 고정
SettingType = Literal["input", "select", "checkbox"]  # 필요하면 확장

class SettingItem(TypedDict, total=False):
    name: str
    code: str
    value: str
    type: SettingType

class ColumnItem(TypedDict, total=False):
    checked: bool
    code: str
    value: str


SITE_LIST: List[Site] = [
    Site(
        "네이버 밴드 멤버",
        "NAVER_BAND_MEMBER",
        "#ccc",
        enabled=True,
        popup=False,
        setting=[
            {"name": "밴드ID", "code": "band_id", "value": "", "type": "input"},
            {"name": "JSON 폴더", "code": "hook_inbox_dir", "value": "C:/hook_server/out/inbox", "type": "input"},
            {"name": "JSON 파일명", "code": "hook_json_filename", "value": "naver_band_member.json", "type": "input"},
        ],
        columns=[
            {"checked": True, "code": "band_name",   "value": "밴드명"},
            {"checked": True, "code": "user_no",     "value": "유저번호"},
            {"checked": True, "code": "role",        "value": "직책"},
            {"checked": True, "code": "created_at",  "value": "등록일"},
            {"checked": True, "code": "name",        "value": "이름"},
            {"checked": True, "code": "description", "value": "설명"},
            {"checked": True, "code": "phone",       "value": "전화번호"},
        ],
    ),
]

# 전역 변수
server_url: Final[str] = "http://vjrvj.cafe24.com"
# server_url: Final[str] = "http://localhost"

server_name: Final[str] = "MyAppAutoLogin"