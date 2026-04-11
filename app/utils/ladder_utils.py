# -*- coding: utf-8 -*-
"""
连板梯队：最高连板高度与分档家数（兼容 JSON 反序列化后的字符串键）。
「最高」应为当日涨停池中连板数的最大值，非 0/1 标记。
"""
from __future__ import annotations

from typing import Any, Optional


def ladder_level_count(ladder: Optional[dict[Any, Any]], level: int) -> int:
    """梯队分布中某一连板档的家数。"""
    if not ladder:
        return 0
    for k, v in ladder.items():
        try:
            if int(k) == level:
                return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def max_lb_from_ladder_dict(ladder: Optional[dict[Any, Any]]) -> int:
    """从 {连板数: 家数} 取最大连板数（键的最大值）。"""
    if not ladder:
        return 0
    mx = 0
    for k in ladder:
        try:
            kk = int(k)
            if kk > 0:
                mx = max(mx, kk)
        except (TypeError, ValueError):
            continue
    return mx


def display_max_lb_row(row: dict[str, Any]) -> int:
    """表格「最高」列：优先 max_lb，缺失或为 0 时从 ladder 键恢复。"""
    m = row.get("max_lb")
    try:
        iv = int(m) if m is not None else 0
    except (TypeError, ValueError):
        iv = 0
    if iv > 0:
        return iv
    return max_lb_from_ladder_dict(row.get("ladder") or {})
