# -*- coding: utf-8 -*-
"""
统一配置：深度合并 JSON、策略 profile、环境变量。

合并顺序（后者覆盖前者）：
1. 代码内 defaults
2. `strategy_profiles[active_strategy_profile]`（与 defaults 深度合并）
3. `replay_config.json`（或 REPLAY_CONFIG_FILE 指定路径）
4. 显式环境变量映射（见 ENV_FLAT_BINDINGS）
5. 嵌套覆盖：`REPLAY__` 前缀 + `__` 分隔的路径，如 REPLAY__data_source__timeout=12
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Optional

# --- 环境变量 → 顶层配置键（值会按类型转换）---
# 兼容历史：同时保留 LLM_/SMTP_/STRATEGY_ 等与代码库既有脚本一致的名字。
ENV_FLAT_BINDINGS: list[tuple[str, str, Callable[[str], Any]]] = [
    ("DEEPSEEK_API_KEY", "deepseek_api_key", str),
    ("LLM_API_KEY", "llm_api_key", str),
    ("LLM_MODEL_NAME", "llm_model_name", str),
    ("DEEPSEEK_MODEL_NAME", "deepseek_model_name", str),
    ("LLM_API_BASE", "llm_api_base", str),
    ("DEEPSEEK_API_URL", "llm_default_url", str),
    ("LLM_TIMEOUT_SEC", "llm_transport_timeout_sec", float),
    ("LLM_RETRY_ATTEMPTS", "llm_retry_attempts", lambda s: max(1, int(s))),
    ("LLM_RETRY_429", "llm_retry_429", lambda s: max(0, int(s))),
    ("LLM_RETRY_429_WAIT_SEC", "llm_retry_429_wait_sec", lambda s: max(5, int(s))),
    ("LLM_RETRY_429_WAIT_MAX_SEC", "llm_retry_429_wait_max_sec", lambda s: max(30, int(s))),
    ("SMTP_HOST", "smtp_host", str),
    ("SMTP_PORT", "smtp_port", lambda s: int(s)),
    ("SMTP_USER", "smtp_user", str),
    ("SMTP_PASSWORD", "smtp_password", str),
    ("SMTP_FROM", "smtp_from", str),
    ("MAIL_TO", "mail_to", str),
    ("STRATEGY_WEIGHT_CLIP_LOW", "strategy_weight_clip_low", float),
    ("STRATEGY_WEIGHT_CLIP_HIGH", "strategy_weight_clip_high", float),
    ("STRATEGY_MAX_WEIGHT_DELTA", "strategy_max_weight_delta_per_update", float),
    ("STRATEGY_WEIGHT_HISTORY_MAX", "strategy_weight_history_max", int),
    ("STRATEGY_WEEK_DECAY_FACTOR", "strategy_week_decay_factor", float),
    ("STRATEGY_MULTI_WEEK_LOOKBACK", "multi_week_lookback", int),
]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并字典；override 覆盖 base，子 dict 递归合并。"""
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_json(path: str) -> Optional[dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def apply_strategy_profile_overlay(cfg: dict[str, Any]) -> dict[str, Any]:
    """将 `strategy_profiles[active_strategy_profile]` 中非元数据键深度合并进 cfg。"""
    name = (cfg.get("active_strategy_profile") or "default") or "default"
    profiles = cfg.get("strategy_profiles")
    if not isinstance(profiles, dict):
        return cfg
    overlay = profiles.get(name)
    if not isinstance(overlay, dict) or not overlay:
        return cfg
    safe = {
        k: v
        for k, v in overlay.items()
        if k not in ("strategy_profiles", "active_strategy_profile")
    }
    return deep_merge(cfg, safe)


def _apply_flat_env(cfg: dict[str, Any]) -> None:
    for env_name, key, cast in ENV_FLAT_BINDINGS:
        raw = os.environ.get(env_name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            cfg[key] = cast(str(raw).strip())
        except (TypeError, ValueError):
            cfg[key] = raw


def _apply_nested_replay_env(cfg: dict[str, Any], prefix: str = "REPLAY__") -> None:
    """
    REPLAY__data_source__timeout → cfg["data_source"]["timeout"]
    值：尝试 int / float / bool / str

    前缀匹配不区分大小写（兼容 Windows 对环境变量键的大小写处理）。
    """
    pfx_u = prefix.upper()
    plen = len(prefix)
    for k, v in os.environ.items():
        ku = k.upper()
        if not ku.startswith(pfx_u):
            continue
        raw_parts = k[plen:].split("__")
        path = [p.lower() for p in raw_parts if p]
        if not path:
            continue
        _set_path(cfg, path, _parse_env_value(v))


def _parse_env_value(v: str) -> Any:
    s = v.strip()
    low = s.lower()
    if low in ("true", "yes", "1"):
        return True
    if low in ("false", "no", "0"):
        return False
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return v


def _set_path(cfg: dict[str, Any], parts: list[str], value: Any) -> None:
    cur: Any = cfg
    for i, p in enumerate(parts):
        if not re.match(r"^[a-zA-Z0-9_]+$", p):
            return
        if i == len(parts) - 1:
            if isinstance(cur, dict):
                cur[p] = value
            return
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]


def inject_project_paths(cfg: dict[str, Any], project_root: str) -> None:
    """写入 paths.project_root，并保证 paths 存在。"""
    paths = cfg.get("paths")
    if not isinstance(paths, dict):
        paths = {}
        cfg["paths"] = paths
    paths["project_root"] = project_root


def build_effective_config(
    *,
    defaults: dict[str, Any],
    config_file: str,
    project_root: str,
) -> dict[str, Any]:
    """
    构建运行期有效配置（不落盘）。

    顺序：defaults → JSON 文件 → `strategy_profiles[active_strategy_profile]`
    （profile 覆盖同名键）→ 注入路径 → 环境变量。
    """
    base = deep_merge({}, defaults)

    path = (os.environ.get("REPLAY_CONFIG_FILE") or "").strip() or config_file
    user = _load_json(path)
    if user:
        base = deep_merge(base, user)

    base = apply_strategy_profile_overlay(base)

    inject_project_paths(base, project_root)
    _apply_flat_env(base)
    _apply_nested_replay_env(base)
    return base
