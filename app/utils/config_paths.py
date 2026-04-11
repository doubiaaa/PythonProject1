# -*- coding: utf-8 -*-
"""从合并后的配置解析 `paths.*`，避免各模块硬编码 data/*.json 路径。"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _project_root() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    )


def _path_or_fallback(key: str, fallback_relative: str) -> str:
    try:
        from app.utils.config import ConfigManager

        return ConfigManager().path(key)
    except Exception:
        return os.path.normpath(
            os.path.join(_project_root(), fallback_relative.replace("/", os.sep))
        )


def watchlist_records_file() -> str:
    return _path_or_fallback("watchlist_records_file", "data/watchlist_records.json")


def market_style_indices_file() -> str:
    return _path_or_fallback("market_style_indices_file", "data/market_style_indices.json")


def data_dir() -> str:
    """逻辑数据目录（默认 `data/`）。"""
    return os.path.dirname(watchlist_records_file())
