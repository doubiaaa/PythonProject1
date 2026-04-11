"""
市场 KPI 辅助：昨日涨停溢价相对近 5 个交易日的动态评级与展示文案。
"""

from __future__ import annotations

from typing import Any


def _band_vs_mean(mean_5: float) -> float:
    """相对均值的「正常带」半宽：不低于 0.4pct，并随均值尺度略放大。"""
    return max(0.4, abs(float(mean_5)) * 0.12)


def premium_analysis(
    premium: float,
    premium_note: str,
    date: str,
    trade_days: list[str],
    fetcher: Any,
) -> dict[str, Any]:
    """
    基于当日溢价与此前 **最多 5 个交易日** 的日度溢价序列，计算：
    - 近 5 日（交易日）均值（不含当日）
    - 当日值在该历史序列中的经验分位（0～100）
    - 相对均值的动态档位：偏低 / 正常 / 偏高，并附 偏弱 / 中性 / 偏强

    展示示例：``2.11%（低于近5日均值，偏弱；历史分位约 20%）``
    """
    ds = str(date)[:8]
    out: dict[str, Any] = {
        "premium": premium,
        "premium_note": premium_note,
        "mean_5": None,
        "percentile": None,
        "past_sample_n": 0,
        "rating": "",
        "strength": "",
        "display_line": "",
    }

    if premium == -99.0 or not trade_days or ds not in trade_days:
        out["rating"] = "不可用"
        out["strength"] = ""
        out["display_line"] = str(premium_note)
        return out

    idx = trade_days.index(ds)
    past_days = trade_days[max(0, idx - 5) : idx]
    vals: list[float] = []
    for d in past_days:
        p, _n = fetcher.get_yest_zt_premium(d, trade_days)
        if p != -99.0:
            try:
                vals.append(float(p))
            except (TypeError, ValueError):
                continue

    out["past_sample_n"] = len(vals)
    if not vals:
        out["rating"] = "数据不足"
        out["display_line"] = f"{premium}%（{premium_note}；近5日无有效参考样本）"
        return out

    mean_5 = round(sum(vals) / len(vals), 2)
    out["mean_5"] = mean_5

    below = sum(1 for x in vals if float(premium) > x)
    equal = sum(1 for x in vals if float(premium) == x)
    out["percentile"] = round((below + 0.5 * equal) / len(vals) * 100.0, 0)

    band = _band_vs_mean(mean_5)
    diff = float(premium) - mean_5
    if diff < -band:
        out["rating"], out["strength"] = "偏低", "偏弱"
        rel_cn = "低于均值"
    elif diff > band:
        out["rating"], out["strength"] = "偏高", "偏强"
        rel_cn = "高于均值"
    else:
        out["rating"], out["strength"] = "正常", "中性"
        rel_cn = "接近均值"

    pct_s = (
        f"；历史分位约 **{out['percentile']:.0f}%**"
        if out["percentile"] is not None
        else ""
    )
    # 示例：2.11%（近5日均 1.80%，低于均值，偏弱；历史分位约 20%）
    out["display_line"] = (
        f"{premium}%（近5日均 **{mean_5}%**，{rel_cn}，{out['strength']}{pct_s}）"
    )

    return out


def big_loss_metrics(big_face_count: int) -> dict[str, Any]:
    """亏钱效应（大面）展示字段，与 DataFetcher.compute_big_face_count 口径一致。"""
    n = max(0, int(big_face_count))
    return {
        "big_loss_count": n,
        "display_line": f"大面: {n}只（昨日涨停今跌超5%或跌停）",
    }
