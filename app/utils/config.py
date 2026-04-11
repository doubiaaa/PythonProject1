import json
import os
from functools import lru_cache
from typing import Any, Optional

from app.infrastructure.config_defaults import frozen_defaults
from app.infrastructure.unified_config import build_effective_config

# config.py 位于 app/utils/，项目根需上溯三级
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "replay_config.json")


def _build_merged_config(config_file: Optional[str] = None) -> dict[str, Any]:
    path = config_file or CONFIG_FILE
    return build_effective_config(
        defaults=frozen_defaults(),
        config_file=path,
        project_root=_PROJECT_ROOT,
    )


class ConfigManager:
    """配置管理类：defaults + 策略 profile + JSON + 环境变量（见 unified_config）。"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self) -> dict[str, Any]:
        return _build_merged_config(self.config_file)

    def save_config(self) -> None:
        """仅将当前内存中的可序列化片段写回 JSON（不含环境-only 覆盖说明）。"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.save_config()

    def path(self, *keys: str) -> str:
        """
        解析 `paths` 下相对路径为绝对路径（基于 paths.project_root）。
        例：cm.path('strategy_preference_file')
        """
        paths = self.config.get("paths") or {}
        if not isinstance(paths, dict):
            paths = {}
        root = paths.get("project_root") or _PROJECT_ROOT
        if len(keys) == 1:
            rel = paths.get(keys[0])
        else:
            cur: Any = paths
            for k in keys:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(k)
            rel = cur
        if not rel or not isinstance(rel, str):
            raise KeyError(keys)
        return os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))


@lru_cache(maxsize=1)
def get_project_root() -> str:
    return _PROJECT_ROOT
