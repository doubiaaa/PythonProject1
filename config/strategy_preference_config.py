# -*- coding: utf-8 -*-
"""
策略权重边界与历史条数：统一从 `replay_config.json` + 环境变量合并结果读取。

勿在业务代码中写死数值；请改配置或 `strategy_profiles`。
"""
from __future__ import annotations

from app.utils.config import ConfigManager


def _cm() -> ConfigManager:
    return ConfigManager()


def get_weight_clip_low() -> float:
    return float(_cm().get("strategy_weight_clip_low", 0.01))


def get_weight_clip_high() -> float:
    return float(_cm().get("strategy_weight_clip_high", 0.99))


def get_max_weight_delta_per_update() -> float:
    return float(_cm().get("strategy_max_weight_delta_per_update", 0.10))


def get_weight_history_max() -> int:
    return int(_cm().get("strategy_weight_history_max", 10))


def get_multi_week_decay_default() -> float:
    return float(_cm().get("strategy_week_decay_factor", 0.75))


def get_multi_week_lookback_default() -> int:
    return int(_cm().get("multi_week_lookback", 4))
