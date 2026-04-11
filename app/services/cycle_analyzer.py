"""
周期与情绪：基于当日可观测指标的次日情绪定性预判（非预测涨跌）。
"""

from __future__ import annotations


def sentiment_forecast(
    *,
    zhaban_rate: float,
    zhaban_rate_prev: float | None,
    premium: float,
    dt_count: int,
    market_phase: str,
) -> str:
    """
    输出一两句「明日情绪推演」文案，供写入市场摘要与 prompt。
    """
    parts: list[str] = []
    zb = float(zhaban_rate)
    zp = float(zhaban_rate_prev) if zhaban_rate_prev is not None else None
    pr = float(premium) if premium != -99 else None
    dt = int(dt_count)

    if zp is not None and zb > zp + 2.5:
        parts.append("炸板率较前一日抬升，分歧有所加大")
    elif zp is not None and zb + 2.5 < zp:
        parts.append("炸板率较前一日回落，接力容错略改善")

    if pr is not None:
        if pr < 0:
            parts.append("昨日涨停溢价为负，接力意愿偏弱")
        elif pr > 2.5:
            parts.append("溢价偏高，接力情绪仍偏强（注意一致性风险）")

    if dt >= 25:
        parts.append("跌停家数偏高，亏钱效应易扩散")
    elif dt <= 5:
        parts.append("跌停家数可控，极端亏钱效应有限")

    phase = market_phase or ""
    if "主升" in phase:
        tail = "预计情绪仍以强势震荡为主，关注分歧是否加剧。"
    elif "冰点" in phase or "退潮" in phase:
        tail = "预计延续弱势与分歧，弱修复需见炸板率与跌停数同步收敛。"
    elif "混沌" in phase or "试错" in phase:
        tail = "预计仍以试错与快速轮动为主，宜控节奏。"
    else:
        tail = "预计延续分歧震荡，若炸板率继续走高则偏「延续分歧」，反之为「弱修复」概率上升。"

    head = "；".join(parts) if parts else "指标互有抵消"
    return f"{head}。**预判**：{tail}"
