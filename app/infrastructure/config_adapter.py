# -*- coding: utf-8 -*-
"""配置：将 ConfigManager 适配为 AppConfigPort。"""

from __future__ import annotations

from typing import Any, Optional

from app.domain.ports import AppConfigPort
from app.utils.config import ConfigManager


class ConfigManagerAppAdapter(AppConfigPort):
    """运行期默认使用全局配置；测试可注入内存 dict 或 Fake。"""

    __slots__ = ("_cm",)

    def __init__(self, manager: Optional[ConfigManager] = None) -> None:
        self._cm = manager or ConfigManager()

    def get(self, key: str, default: Any = None) -> Any:
        return self._cm.get(key, default)
