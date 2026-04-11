"""
建议仓位：与周期阶段、炸板率与涨停家数分位挂钩（区间字符串）。
"""

from __future__ import annotations


def _clamp_pct(low: float, high: float, zhaban_rate: float, zb_pctile: float | None) -> tuple[float, float]:
    """炸板率偏高时在区间上沿再压一档。"""
    lo, hi = low, high
    if zhaban_rate > 30 and (zb_pctile is None or zb_pctile >= 60.0):
        hi = max(lo, hi - 10.0)
    if zhaban_rate > 40:
        hi = max(lo, hi - 5.0)
    return lo, hi


def calc_position(
    cycle: str,
    zhaban_rate: float,
    zt_count: int,
    *,
    zt_percentile: float | None = None,
    zb_percentile: float | None = None,
) -> str:
    """
    根据程序 **市场阶段** 与当日炸板率、涨停家数分位（0～100，近若干交易日经验分位）给出建议仓位区间。
    """
    c = (cycle or "").strip()
    zb = float(zhaban_rate)
    zt_pct = zt_percentile
    # 分位缺失时用涨停家数粗分档
    if zt_pct is None:
        if zt_count >= 40:
            zt_pct = 75.0
        elif zt_count >= 25:
            zt_pct = 50.0
        else:
            zt_pct = 30.0

    if "主升" in c:
        lo, hi = 60.0, 80.0
    elif "震荡" in c:
        lo, hi = 20.0, 40.0
    elif "冰点" in c or "退潮" in c:
        lo, hi = 0.0, 10.0
    elif "混沌" in c or "试错" in c:
        lo, hi = 15.0, 25.0
    else:
        lo, hi = 20.0, 40.0

    # 涨停家数处于近期低位 → 区间下移
    if zt_pct is not None and zt_pct < 25:
        lo = max(0.0, lo - 5.0)
        hi = max(lo, hi - 10.0)
    elif zt_pct is not None and zt_pct > 80:
        hi = min(95.0, hi + 5.0)

    lo, hi = _clamp_pct(lo, hi, zb, zb_percentile)
    if lo >= hi:
        hi = lo + 5.0
    return f"{int(round(lo))}-{int(round(hi))}%"
