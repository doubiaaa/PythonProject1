# -*- coding: utf-8 -*-
"""
策略权重：边界、单周变化上限、多周衰减（可由 replay_config.json 覆盖同名键）。
"""
from __future__ import annotations

import os

# 归一化前每桶上下界（与 _apply_floor_cap 不同：先 clip 再归一）
WEIGHT_CLIP_LOW: float = float(os.environ.get("STRATEGY_WEIGHT_CLIP_LOW", "0.01"))
WEIGHT_CLIP_HIGH: float = float(os.environ.get("STRATEGY_WEIGHT_CLIP_HIGH", "0.99"))

# 单次更新相对上一版合并权重的最大绝对变化（默认 10%）
MAX_WEIGHT_DELTA_PER_UPDATE: float = float(
    os.environ.get("STRATEGY_MAX_WEIGHT_DELTA", "0.10")
)

# 保留在 strategy_preference.json 中的历史权重条数
WEIGHT_HISTORY_MAX: int = int(os.environ.get("STRATEGY_WEIGHT_HISTORY_MAX", "10"))

# 多周衰减：近一周权重 1.0、前一周 factor、再前 factor^2 …（逻辑在 strategy_preference 内）
MULTI_WEEK_DECAY_DEFAULT: float = float(os.environ.get("STRATEGY_WEEK_DECAY_FACTOR", "0.75"))
MULTI_WEEK_LOOKBACK_DEFAULT: int = int(os.environ.get("STRATEGY_MULTI_WEEK_LOOKBACK", "4"))
