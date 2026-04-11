"""
连板晋级率：基于昨日涨停池与当日涨停池对齐。
"""

from __future__ import annotations

from typing import Any


def _norm_code(fetcher: Any, c: Any) -> str:
    return fetcher._norm_code(c)


def compute_promotion_rates_md(
    fetcher: Any,
    date: str,
    trade_days: list[str],
    df_zt_today,
) -> str:
    """
    文本表：1进2 / 2进3 / 3进4 晋级率（昨日连板档 → 今日至少 +1 档）。
    """
    ds = str(date)[:8]
    if not trade_days or ds not in trade_days:
        return ""
    idx = trade_days.index(ds)
    if idx <= 0:
        return ""
    yd = trade_days[idx - 1]
    ydf = fetcher.get_zt_pool(yd)
    if ydf is None or getattr(ydf, "empty", True) or "lb" not in ydf.columns:
        return ""
    if df_zt_today is None or getattr(df_zt_today, "empty", True) or "lb" not in df_zt_today.columns:
        return ""

    ydf = ydf.copy()
    ydf["_c"] = ydf["code"].map(lambda x: _norm_code(fetcher, x))
    ydf["lb"] = ydf["lb"].fillna(1).astype(int).clip(lower=1)

    tdf = df_zt_today.copy()
    tdf["_c"] = tdf["code"].map(lambda x: _norm_code(fetcher, x))
    tdf["lb"] = tdf["lb"].fillna(1).astype(int).clip(lower=1)
    today_map = {row["_c"]: int(row["lb"]) for _, row in tdf.iterrows()}

    lines: list[str] = [
        "\n### 【程序】连板晋级率（昨日→今日）\n\n",
        "| 档位 | 昨日家数 | 成功晋级 | 晋级率 |\n|------|----------|----------|--------|\n",
    ]

    for from_lb, label in ((1, "1进2"), (2, "2进3"), (3, "3进4")):
        sub = ydf[ydf["lb"] == from_lb]
        denom = len(sub)
        if denom <= 0:
            lines.append(f"| {label} | 0 | — | — |\n")
            continue
        ok = 0
        for _, row in sub.iterrows():
            c = row["_c"]
            tl = today_map.get(c)
            if tl is not None and tl >= from_lb + 1:
                ok += 1
        rate = round(100.0 * ok / denom, 1)
        lines.append(f"| {label} | {denom} | {ok} | **{rate}%** |\n")

    lines.append(
        "\n> 口径：晋级指同一标的在当日涨停池中连板数较昨日至少 +1；"
        "未在当日涨停池出现视为未晋级。\n\n"
    )
    return "".join(lines)
