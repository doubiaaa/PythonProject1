# -*- coding: utf-8 -*-
"""输入与中间数据校验（脏数据拦截）。"""

from __future__ import annotations

import re
from typing import Any, Optional

_TRADE_DATE_RE = re.compile(r"^\d{8}$")


def normalize_trade_date_str(raw: Any) -> Optional[str]:
    """返回 8 位 YYYYMMDD 或 None。"""
    if raw is None:
        return None
    s = str(raw).strip()[:8]
    if not _TRADE_DATE_RE.match(s):
        return None
    return s


def is_reasonable_ohlc_row(
    open_v: Any, high: Any, low: Any, close_v: Any
) -> bool:
    """粗筛价格行：非负且 high>=low（用于拦截明显脏行）。"""
    try:
        o, h, l, c = float(open_v), float(high), float(low), float(close_v)
    except (TypeError, ValueError):
        return False
    if min(o, h, l, c) < 0:
        return False
    if h < l:
        return False
    return True
