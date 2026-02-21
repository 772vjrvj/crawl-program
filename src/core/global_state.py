# src/core/global_state.py
from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional


class GlobalState:
    """
    앱 전역 상태 싱글톤.

    - GlobalState()를 여러 번 호출해도 동일 인스턴스를 반환
    - initialize()를 앱 시작 시 1회 호출하여 기본값 세팅
    """

    # 전역에서 사용하는 고정된 키 상수들 (문자열 오타 방지용)
    NAME: ClassVar[str] = "name"
    SITE: ClassVar[str] = "site"
    COLOR: ClassVar[str] = "color"
    COOKIES: ClassVar[str] = "cookies"
    SETTING: ClassVar[str] = "setting"
    SETTING_DETAIL: ClassVar[str] = "setting_detail"
    COLUMNS: ClassVar[str] = "columns"
    REGION: ClassVar[str] = "region"
    POPUP: ClassVar[str] = "popup"
    SITES: ClassVar[str] = "sites"

    _instance: ClassVar[Optional["GlobalState"]] = None

    _data: Dict[str, Any]
    _initialized: bool

    def __new__(cls, *args: Any, **kwargs: Any) -> "GlobalState":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._data = {}
            inst._initialized = False
            cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        # 싱글톤은 __init__이 여러 번 호출될 수 있으므로 여기서는 덮어쓰지 않음
        pass

    def initialize(self) -> None:
        """초기화되지 않았으면 기본 상태값을 채운다."""
        if not self._initialized:
            self._data = {
                self.COOKIES: "",
                self.NAME: "",
                self.SITE: "",
                self.COLOR: "",
                self.SETTING: "",
                self.SETTING_DETAIL: "",
                self.COLUMNS: "",
                self.REGION: "",
                self.POPUP: "",
                self.SITES: "",
            }
            self._initialized = True

    def set(self, key: str, value: Any) -> None:
        """상태 값을 저장한다."""
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """상태 값을 가져온다. 없으면 default 반환."""
        return self._data.get(key, default)

    def remove(self, key: str) -> None:
        """특정 키 삭제."""
        if key in self._data:
            del self._data[key]

    def clear(self) -> None:
        """전체 상태 초기화."""
        self._data.clear()