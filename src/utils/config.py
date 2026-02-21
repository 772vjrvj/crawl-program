# src/utils/config.py
# -*- coding: utf-8 -*-
from __future__ import annotations  # === 신규 ===

from typing import Final

# 기본값(안전용)
server_url: str = ""
server_name: str = ""

def set_app_server_config(url: str, name: str) -> None:
    global server_url, server_name
    server_url = url or ""
    server_name = name or ""