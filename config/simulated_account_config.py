# -*- coding: utf-8 -*-
"""
模拟账户：手续费、滑点、卖出信号优先级标签（业务含义由 check_sell_signals 解释）。
"""
from __future__ import annotations

# 费率：万三 = 0.0003；滑点：千一 = 0.001（买入加价、卖出减价）
DEFAULT_COMMISSION_RATE: float = 0.0003
DEFAULT_SLIPPAGE_RATE: float = 0.001

# 卖出信号优先级（仅用于文档/日志；实际顺序由代码固定：止盈 > 止损 > 天数）
SIGNAL_PRIORITY_LABELS: tuple[str, ...] = ("止盈", "止损", "持有天数上限")
