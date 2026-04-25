import json
import os
from functools import lru_cache
from typing import Any, Optional

# 尝试导入新的配置管理器
try:
    from backend.app.utils.config_manager import config_manager as new_config_manager
    use_new_config = True
except ImportError:
    # 回退到旧的配置管理器
    from app.infrastructure.config_defaults import frozen_defaults
    from app.infrastructure.unified_config import build_effective_config
    use_new_config = False

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
    """配置管理类：优先从数据库读取，回退到 defaults + 策略 profile + JSON + 环境变量。"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        if not use_new_config:
            self.config = self.load_config()

    def load_config(self) -> dict[str, Any]:
        return _build_merged_config(self.config_file)

    def save_config(self) -> None:
        """仅将当前内存中的可序列化片段写回 JSON（不含环境-only 覆盖说明）。"""
        if not use_new_config:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        if use_new_config:
            # 从新的配置管理器获取
            value = new_config_manager.get_config(key, default)
            if value is not None:
                return value

        # 回退到旧的配置方式
        if not use_new_config:
            return self.config.get(key, default)

        return default

    def set(self, key: str, value: Any) -> None:
        if use_new_config:
            # 使用新的配置管理器设置
            new_config_manager.set_config(key, value)
        else:
            # 回退到旧的配置方式
            self.config[key] = value
            self.save_config()

    def path(self, *keys: str) -> str:
        """
        解析 `paths` 下相对路径为绝对路径（基于 paths.project_root）。
        例：cm.path('strategy_preference_file')
        """
        if use_new_config:
            # 从新的配置管理器获取 paths
            paths = new_config_manager.get_config("paths", {})
        else:
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
