"""
建议仓位：规则在 config/strategy.json，由 StrategyEngine 解析。
"""

from __future__ import annotations

from typing import Optional


def calc_position(
    cycle: str,
    zhaban_rate: float,
    zt_count: int,
    *,
    zt_percentile: Optional[float] = None,
    zb_percentile: Optional[float] = None,
) -> str:
    from app.services.strategy_engine import get_strategy_engine

    return get_strategy_engine().calc_position(
        cycle,
        zhaban_rate,
        zt_count,
        zt_percentile=zt_percentile,
        zb_percentile=zb_percentile,
    )
