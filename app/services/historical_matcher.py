"""
历史相似形态：近若干交易日中与当日结构最接近的样本及其后 T+1～T+3 概况。
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def _metrics_for_day(fetcher: Any, d: str) -> Optional[tuple[int, float, int]]:
    df_zt = fetcher.get_zt_pool(d)
    df_zb = fetcher.get_zb_pool(d)
    zn = len(df_zt) if df_zt is not None and not getattr(df_zt, "empty", True) else 0
    bn = len(df_zb) if df_zb is not None and not getattr(df_zb, "empty", True) else 0
    tot = zn + bn
    zhr = round(bn / tot * 100, 2) if tot > 0 else 0.0
    mx = 0
    if df_zt is not None and not df_zt.empty and "lb" in df_zt.columns:
        try:
            s = pd.to_numeric(df_zt["lb"], errors="coerce").fillna(1).astype(int)
            mx = int(s.max())
        except Exception:
            mx = 0
    return zn, zhr, mx


def _metrics_cache_for_days(
    fetcher: Any, days: list[str]
) -> dict[str, tuple[int, float, int]]:
    """逐日拉取（依赖 DataFetcher 内存/磁盘缓存）；同一日只请求一次。"""
    out: dict[str, tuple[int, float, int]] = {}
    seen: set[str] = set()
    for d in days:
        if d in seen:
            continue
        seen.add(d)
        m = _metrics_for_day(fetcher, d)
        if m is not None:
            out[d] = m
    return out


def _dist(
    a: tuple[int, float, int],
    b: tuple[int, float, int],
    scale: tuple[float, float, float],
) -> float:
    return (
        abs(a[0] - b[0]) / scale[0]
        + abs(a[1] - b[1]) / scale[1]
        + abs(a[2] - b[2]) / max(scale[2], 1e-6)
    )


def find_similar_trading_days(
    fetcher: Any,
    date: str,
    trade_days: list[str],
    *,
    lookback: int = 60,
    top_k: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, float, int]]]:
    """
    在 ``date`` 之前最多 lookback 个交易日内，按 (涨停家数, 炸板率, 最高连板) 的归一化距离找最相似日。
    返回 (结果列表, 已计算的 metrics 缓存)，供后续 T+1～T+3 行复用，避免对同一交易日重复请求。
    """
    ds = str(date)[:8]
    if not trade_days or ds not in trade_days:
        return [], {}
    idx = trade_days.index(ds)
    start = max(0, idx - lookback)
    window_days = [trade_days[j] for j in range(start, idx)]
    need = list(dict.fromkeys(window_days + [ds]))
    cache = _metrics_cache_for_days(fetcher, need)
    cur = cache.get(ds)
    if cur is None:
        return [], cache

    zt_vals: list[int] = []
    zh_vals: list[float] = []
    mx_vals: list[int] = []
    for j in range(start, idx):
        d = trade_days[j]
        m = cache.get(d)
        if m is None:
            continue
        zt_vals.append(m[0])
        zh_vals.append(m[1])
        mx_vals.append(m[2])
    if not zt_vals:
        return [], cache

    zt0, zhr0, mx0 = cur
    scale_zt = max(max(zt_vals) - min(zt_vals), 1.0)
    scale_zh = max(max(zh_vals) - min(zh_vals), 1.0)
    scale_mx = max(max(mx_vals) - min(mx_vals), 1.0)

    candidates: list[tuple[float, str, tuple[int, float, int]]] = []
    for j in range(start, idx):
        d = trade_days[j]
        m = cache.get(d)
        if m is None:
            continue
        di = _dist((zt0, zhr0, mx0), m, (scale_zt, scale_zh, float(scale_mx)))
        candidates.append((di, d, m))
    candidates.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    for di, d, m in candidates[:top_k]:
        out.append({"date": d, "distance": round(di, 4), "metrics": m})
    return out, cache


def _forward_snapshot_from_cache(
    cache: dict[str, tuple[int, float, int]],
    trade_days: list[str],
    di: int,
    off: int,
) -> str:
    if di + off >= len(trade_days):
        return "—"
    d = trade_days[di + off]
    m = cache.get(d)
    if m is None:
        return "—"
    zt, zhr, mx = m
    return f"涨停 {zt}｜炸板率 {zhr}%｜最高 {mx} 板"


def format_similar_days_markdown(
    fetcher: Any,
    date: str,
    trade_days: list[str],
    *,
    lookback: int = 60,
) -> str:
    ds = str(date)[:8]
    if ds not in trade_days:
        return ""
    sims, cache = find_similar_trading_days(
        fetcher, ds, trade_days, lookback=lookback, top_k=3
    )
    if not sims:
        return ""

    fwd: list[str] = []
    for s in sims:
        d0 = s["date"]
        di = trade_days.index(d0)
        for off in (1, 2, 3):
            if di + off < len(trade_days):
                dd = trade_days[di + off]
                if dd not in cache:
                    fwd.append(dd)
    if fwd:
        extra = _metrics_cache_for_days(fetcher, fwd)
        cache.update(extra)

    lines = [
        "\n### 【程序】历史相似形态回溯\n\n",
        "> 对比窗口默认约 **60** 个交易日（可在 `replay_config.json` 调整 "
        "`historical_similarity_lookback`）。以涨停家数、炸板率、最高连板三维距离最小为「最相似」；"
        "后续表现为程序快照概括，非收益承诺。\n\n",
        "| 相似日 | 当日结构 | T+1 | T+2 | T+3 |\n",
        "|--------|----------|-----|-----|-----|\n",
    ]
    for s in sims:
        d = s["date"]
        zt, zhr, mx = s["metrics"]
        di = trade_days.index(d)
        t1 = _forward_snapshot_from_cache(cache, trade_days, di, 1)
        t2 = _forward_snapshot_from_cache(cache, trade_days, di, 2)
        t3 = _forward_snapshot_from_cache(cache, trade_days, di, 3)
        lines.append(
            f"| {d} | 涨停 {zt} / 炸板 {zhr}% / 最高 {mx} 板 | {t1} | {t2} | {t3} |\n"
        )
    lines.append("\n")
    return "".join(lines)


def append_historical_similarity_block(
    report_md: str,
    fetcher: Any,
    date: str,
) -> str:
    """在「免责声明」前插入相似形态块（若启用且可计算）。"""
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    if not cm.get("enable_historical_similarity", True):
        return report_md
    td = fetcher.get_trade_cal()
    if not td:
        return report_md
    lb = int(cm.get("historical_similarity_lookback", 60) or 60)
    lb = max(20, min(250, lb))
    block = format_similar_days_markdown(
        fetcher, str(date)[:8], td, lookback=lb
    )
    if not block.strip():
        return report_md
    marker = "### 免责声明"
    if marker in report_md:
        parts = report_md.split(marker, 1)
        return parts[0].rstrip() + "\n\n" + block + "\n" + marker + parts[1]
    return report_md.rstrip() + "\n\n" + block
