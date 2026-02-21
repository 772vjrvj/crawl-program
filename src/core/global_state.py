# src/core/global_state.py
from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional


class GlobalState:
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

    APP_CONFIG: ClassVar[str] = "app_config"
    SITE_CONFIGS: ClassVar[str] = "site_configs"

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
        pass

    def initialize(self) -> None:
        if not self._initialized:
            self._data = {
                self.COOKIES: "",
                self.NAME: "",
                self.SITE: "",
                self.COLOR: "",
                self.SETTING: None,
                self.SETTING_DETAIL: None,
                self.COLUMNS: None,
                self.REGION: None,
                self.POPUP: False,
                self.SITES: [],
                self.APP_CONFIG: {},
                self.SITE_CONFIGS: [],
            }
            self._initialized = True

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def remove(self, key: str) -> None:
        if key in self._data:
            del self._data[key]

    def clear(self) -> None:
        self._data.clear()