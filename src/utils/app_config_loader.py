# src/utils/app_config_loader.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(slots=True)
class SiteMeta:
    key: str
    config_path: str


@dataclass(slots=True)
class AppConfig:
    server_url: str
    server_name: str
    site_list_use: List[str]
    site_list: List[SiteMeta]


class AppConfigLoader:
    def __init__(self, app_json_path: str = "runtime/app.json"):
        self.app_json_path = Path(app_json_path).resolve()
        self.runtime_dir = self.app_json_path.parent  # runtime 폴더

    def load_app_config(self) -> AppConfig:
        data = self._read_json(self.app_json_path)

        site_list: List[SiteMeta] = []
        for it in data.get("site_list", []) or []:
            site_list.append(
                SiteMeta(
                    key=str(it.get("key") or "").strip(),
                    config_path=str(it.get("config_path") or "").strip(),
                )
            )

        return AppConfig(
            server_url=str(data.get("server_url") or "").strip(),
            server_name=str(data.get("server_name") or "").strip(),
            site_list_use=[str(x).strip() for x in (data.get("site_list_use") or [])],
            site_list=site_list,
        )

    def load_site_config(self, config_path: str) -> Dict[str, Any]:
        # runtime 기준으로만 결합
        rel = str(config_path or "").strip().lstrip("/\\")
        if not rel:
            raise ValueError("config_path is empty")

        path = (self.runtime_dir / rel).resolve()
        return self._read_json(path)

    def get_enabled_site_configs(self) -> List[Dict[str, Any]]:
        app_conf = self.load_app_config()
        use_set = set(app_conf.site_list_use or [])

        out: List[Dict[str, Any]] = []
        for meta in app_conf.site_list:
            if not meta.key:
                continue
            if meta.key not in use_set:
                continue

            out.append(self.load_site_config(meta.config_path))

        return out

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"설정 파일이 없습니다: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)