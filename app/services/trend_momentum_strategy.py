# -*- coding: utf-8 -*-
"""
趋势 + 动量策略（与文档一致的可调参数）
- 趋势：长周期 EMA 过滤
- 动能：EMA 短/中排列 + RSI 超卖回升 / 非极端超买
- 风控参考：ATR（用于展示波动，下单需实盘接口）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from app.services.technical_indicators import atr_wilder, ema, rsi_wilder


@dataclass
class TrendMomentumParams:
    ema_long: int = 200
    ema_mid: int = 50
    ema_short: int = 20
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    atr_multiplier: float = 2.0


def _need_rows(p: TrendMomentumParams) -> int:
    return max(p.ema_long, p.ema_mid, p.ema_short, p.rsi_period + 5, p.atr_period + 5) + 5


def analyze_ohlcv(
    df: pd.DataFrame,
    params: Optional[TrendMomentumParams] = None,
) -> dict[str, Any]:
    """
    对日 K（东财列名：收盘/最高/最低）做多头友好评分 0~5 分 + 详情。
    A 股短线复盘默认只评估「做多侧」逻辑契合度（价在长期均线之上、短强于中、RSI 不过热或超卖修复）。
    """
    p = params or TrendMomentumParams()
    need = _need_rows(p)
    out: dict[str, Any] = {
        "score": 2.5,
        "detail": "数据不足",
        "rsi": None,
        "atr": None,
        "trend_long_ok": None,
        "ema_bull": None,
    }
    if df is None or df.empty or len(df) < need:
        return out

    for col in ("收盘", "最高", "最低"):
        if col not in df.columns:
            return {**out, "detail": "缺少 OHLC 列"}

    close = pd.to_numeric(df["收盘"], errors="coerce")
    high = pd.to_numeric(df["最高"], errors="coerce")
    low = pd.to_numeric(df["最低"], errors="coerce")
    if close.isna().all():
        return out

    ema_l = ema(close, p.ema_long)
    ema_m = ema(close, p.ema_mid)
    ema_s = ema(close, p.ema_short)
    rsi = rsi_wilder(close, p.rsi_period)
    atr_s = atr_wilder(high, low, close, p.atr_period)

    last = close.iloc[-1]
    el, em_, es = ema_l.iloc[-1], ema_m.iloc[-1], ema_s.iloc[-1]
    r = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0
    r_prev = float(rsi.iloc[-2]) if len(rsi) > 1 and pd.notna(rsi.iloc[-2]) else r
    atrv = float(atr_s.iloc[-1]) if pd.notna(atr_s.iloc[-1]) else 0.0

    trend_long_ok = last > el
    ema_bull = es > em_

    # 超卖回升：近 5 日内曾贴近超卖区且当前 RSI 拐头向上
    rsi_tail = rsi.iloc[-6:-1].dropna()
    was_oversold = bool((rsi_tail < p.rsi_oversold + 5).any()) if len(rsi_tail) else False
    rsi_recovery = was_oversold and r > r_prev and r < p.rsi_overbought

    score = 0.0
    parts: list[str] = []

    if trend_long_ok:
        score += 2.0
        parts.append("收盘>EMA200")
    elif last > em_:
        score += 1.0
        parts.append("收盘>EMA50未站稳EMA200")

    if ema_bull:
        score += 1.5
        parts.append("EMA20>EMA50")
    if ema_bull and last > es:
        score += 0.5
        parts.append("收盘>EMA20")

    if rsi_recovery:
        score += 1.0
        parts.append("RSI超卖区回升")
    elif p.rsi_oversold <= r <= 48:
        score += 0.5
        parts.append("RSI中性偏低")
    elif r >= p.rsi_overbought:
        score -= 0.5
        parts.append("RSI超买区")

    score = max(0.0, min(5.0, score))
    detail = "；".join(parts) if parts else "中性"

    return {
        "score": round(score, 2),
        "detail": detail,
        "rsi": round(r, 2),
        "atr": round(atrv, 4),
        "trend_long_ok": trend_long_ok,
        "ema_bull": ema_bull,
        "stop_atr_hint": round(atrv * p.atr_multiplier, 4) if atrv > 0 else None,
    }


def fetch_stock_hist_daily(
    code: str,
    end_date: str,
    lookback_calendar_days: int = 450,
) -> Optional[pd.DataFrame]:
    """拉取足够长的前复权日 K，供 EMA200 使用。"""
    import akshare as ak
    from datetime import datetime, timedelta

    try:
        end = datetime.strptime(end_date, "%Y%m%d")
        start = (end - timedelta(days=lookback_calendar_days)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(
            symbol=code.strip().zfill(6)[:6],
            period="daily",
            start_date=start,
            end_date=end_date,
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None
