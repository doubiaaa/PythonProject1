# -*- coding: utf-8 -*-
"""
市场风格日度指数（入库）与「自然周内」严格周涨幅统计。

- 打板指数：昨日涨停股今日平均涨幅（与溢价口径一致）。
- 趋势指数：当日全市场 20 日涨跌幅列前 50 名的均值（无列则退 60 日涨跌幅）。
- 低吸指数：5 日涨跌幅最弱 50 只个股当日的平均涨跌幅（超跌反弹环境近似）。

严格本周涨幅前 20：自然周内首交易日开盘 → 末交易日收盘（前复权），全市场抽样后排序。
"""

from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import akshare as ak
import pandas as pd

from app.utils.config_paths import data_dir, market_style_indices_file

_lock = threading.Lock()


def _indices_path() -> str:
    return market_style_indices_file()


def norm_code(c: str) -> str:
    return re.sub(r"[^0-9]", "", str(c))[:6].zfill(6)


def _ensure_dir() -> None:
    os.makedirs(data_dir(), exist_ok=True)


def _load_store() -> dict[str, Any]:
    path = _indices_path()
    if not os.path.isfile(path):
        return {"version": 1, "by_date": {}, "week_strict": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "by_date": {}, "week_strict": {}}
        data.setdefault("by_date", {})
        data.setdefault("week_strict", {})
        return data
    except Exception:
        return {"version": 1, "by_date": {}, "week_strict": {}}


def _save_store(data: dict[str, Any]) -> None:
    _ensure_dir()
    path = _indices_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _find_trend_column(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        s = str(c)
        if "20" in s and "涨" in s and "幅" in s:
            return c
    for c in df.columns:
        s = str(c)
        if "60" in s and "涨" in s and "幅" in s:
            return c
    return None


def _find_5d_column(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        s = str(c)
        if "5" in s and "日" in s and "涨" in s and "幅" in s:
            return c
    return None


def compute_daban_index(fetcher: Any, date: str, trade_days: list[str]) -> tuple[Optional[float], str]:
    p, note = fetcher.get_yest_zt_premium(date, trade_days)
    if isinstance(p, (int, float)) and float(p) == -99.0:
        return None, str(note)
    if p is None:
        return None, str(note)
    return round(float(p), 4), str(note)


def compute_qushi_index(fetcher: Any) -> tuple[Optional[float], str]:
    """趋势：20日/60日涨幅领先组的均值。"""
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
        if df is None or df.empty:
            return None, "spot空"
        col = _find_trend_column(df)
        if not col:
            return None, "无20/60日涨跌幅列"
        s = pd.to_numeric(df[col], errors="coerce")
        df = df.assign(_t=s)
        sub = df.nlargest(50, "_t")
        m = float(pd.to_numeric(sub[col], errors="coerce").mean())
        if pd.isna(m):
            return None, "趋势列无效"
        return round(m, 4), "ok"
    except Exception as e:
        return None, str(e)[:80]


def compute_dixi_index(fetcher: Any) -> tuple[Optional[float], str]:
    """低吸环境近似：5日涨幅最弱50只当日表现。"""
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
        if df is None or df.empty:
            return None, "spot空"
        col5 = _find_5d_column(df)
        if not col5 or "涨跌幅" not in df.columns:
            return None, "无5日涨跌幅或当日涨跌幅列"
        s5 = pd.to_numeric(df[col5], errors="coerce")
        df = df.assign(_s5=s5)
        sub = df.nsmallest(50, "_s5")
        m = float(pd.to_numeric(sub["涨跌幅"], errors="coerce").mean())
        if pd.isna(m):
            return None, "低吸样本无效"
        return round(m, 4), "ok"
    except Exception as e:
        return None, str(e)[:80]


def persist_daily_indices(fetcher: Any, date: str, trade_days: list[str]) -> None:
    """写入当日三指数（复盘成功后调用）。"""
    db, qs, dx = (
        compute_daban_index(fetcher, date, trade_days),
        compute_qushi_index(fetcher),
        compute_dixi_index(fetcher),
    )
    with _lock:
        store = _load_store()
        store["by_date"][date] = {
            "daban": db[0],
            "qushi": qs[0],
            "dixi": dx[0],
            "daban_note": db[1],
            "qushi_note": qs[1],
            "dixi_note": dx[1],
        }
        _save_store(store)


def get_indices_for_dates(dates: list[str]) -> dict[str, dict[str, Any]]:
    """读取若干日期的已存指数。"""
    with _lock:
        store = _load_store()
        bd = store.get("by_date") or {}
    return {d: bd[d] for d in dates if d in bd}


def weekly_return_qfq(
    code: str, week_days: list[str], fetcher: Any,
) -> Optional[float]:
    """自然周内：首交易日开盘 → 末交易日收盘，前复权（经 fetcher 统一熔断/重试）。"""
    if len(week_days) < 1:
        return None
    start, end = week_days[0], week_days[-1]
    try:
        df = fetcher.fetch_with_retry(
            ak.stock_zh_a_hist,
            symbol=norm_code(code),
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
        if df is None or df.empty or "日期" not in df.columns:
            return None
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y%m%d")
        df = df[df["日期"].isin(week_days)].sort_values("日期")
        if len(df) < 1:
            return None
        o = float(pd.to_numeric(df.iloc[0]["开盘"], errors="coerce"))
        cl = float(pd.to_numeric(df.iloc[-1]["收盘"], errors="coerce"))
        if pd.isna(o) or pd.isna(cl) or o <= 0:
            return None
        return (cl - o) / o * 100.0
    except Exception:
        return None


def _one_code_return(
    code: str, week_days: list[str], fetcher: Any,
) -> tuple[str, Optional[float]]:
    return code, weekly_return_qfq(code, week_days, fetcher)


def compute_strict_week_top20_profile(
    fetcher: Any,
    trade_days: list[str],
    iso_year: int,
    iso_week: int,
    anchor_date: str,
    *,
    max_universe: int = 2800,
    max_workers: int = 24,
) -> dict[str, Any]:
    """
    全市场（抽样）计算自然周涨跌幅，取前 20；与锚点日 spot 合并市值、换手。
    结果缓存 week_strict 键： YYYY-Www
    """
    from app.services.weekly_market_snapshot import trade_days_in_iso_week

    week_days = trade_days_in_iso_week(trade_days, iso_year, iso_week)
    if len(week_days) < 1:
        return {"error": "本周无交易日"}

    cache_key = f"{iso_year}-W{iso_week:02d}"
    with _lock:
        store = _load_store()
        cached = (store.get("week_strict") or {}).get(cache_key)
    if cached and cached.get("anchor") == anchor_date:
        return cached

    try:
        spot = fetcher.get_stock_zh_a_spot_em_cached()
        if spot is None or spot.empty or "代码" not in spot.columns:
            return {"error": "spot不可用"}
        spot = spot.copy()
        spot["code"] = spot["代码"].astype(str).map(norm_code)
        codes = spot["code"].drop_duplicates().tolist()
        if len(codes) > max_universe:
            codes = codes[:max_universe]
        rets: list[tuple[str, float]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [
                ex.submit(_one_code_return, c, week_days, fetcher) for c in codes
            ]
            for fut in as_completed(futs):
                c, r = fut.result()
                if r is not None:
                    rets.append((c, r))
        rets.sort(key=lambda x: x[1], reverse=True)
        top20 = rets[:20]
        code_set = {c for c, _ in top20}
        sub = spot[spot["code"].isin(code_set)]
        mcol = "流通市值" if "流通市值" in sub.columns else None
        tcol = "换手率" if "换手率" in sub.columns else None
        name_col = "名称" if "名称" in sub.columns else None
        avg_m = avg_t = None
        if mcol:
            avg_m = round(
                float(pd.to_numeric(sub[mcol], errors="coerce").mean()), 2
            )
        if tcol:
            avg_t = round(
                float(pd.to_numeric(sub[tcol], errors="coerce").mean()), 2
            )
        rows = []
        for c, rp in top20:
            row = sub[sub["code"] == c].head(1)
            nm = str(row[name_col].iloc[0]) if name_col and not row.empty else ""
            rows.append(
                {
                    "code": c,
                    "name": nm,
                    "week_pct": round(rp, 2),
                    "mcap_yi": float(pd.to_numeric(row[mcol], errors="coerce").iloc[0])
                    if mcol and not row.empty
                    else None,
                    "turnover": float(pd.to_numeric(row[tcol], errors="coerce").iloc[0])
                    if tcol and not row.empty
                    else None,
                }
            )
        out = {
            "iso_year": iso_year,
            "iso_week": iso_week,
            "anchor": anchor_date,
            "week_first": week_days[0],
            "week_last": week_days[-1],
            "universe_n": len(codes),
            "strict_top20_avg_mcap_yi": avg_m,
            "strict_top20_avg_turnover_pct": avg_t,
            "strict_top20": rows,
        }
        with _lock:
            store = _load_store()
            store.setdefault("week_strict", {})[cache_key] = out
            _save_store(store)
        return out
    except Exception as e:
        return {"error": str(e)[:200]}


def format_indices_trend_md(recent_dates: list[str]) -> str:
    """最近若干日指数走势（Markdown 表）。"""
    data = get_indices_for_dates(recent_dates)
    if not data:
        return ""
    lines = [
        "### 风格指数近日走势（入库）\n\n",
        "| 日期 | 打板指数 | 趋势指数 | 低吸指数 |\n",
        "|------|----------|----------|----------|\n",
    ]
    for d in recent_dates:
        if d not in data:
            continue
        row = data[d]
        a = row.get("daban")
        b = row.get("qushi")
        c = row.get("dixi")
        lines.append(
            f"| {d} | {a if a is not None else '—'} | {b if b is not None else '—'} | {c if c is not None else '—'} |\n"
        )
    lines.append(
        "\n> **口径**：打板=昨日涨停溢价%；趋势=20/60 日涨跌幅领先 50 均值；"
        "低吸=5 日涨跌幅最弱 50 当日涨跌%。\n\n"
    )
    return "".join(lines)


def format_strict_week_top20_md(profile: dict[str, Any]) -> str:
    if not profile or profile.get("error"):
        err = profile.get("error", "未知") if profile else "无数据"
        return f"\n> **严格周涨幅前 20**：{err}\n\n"
    lines = [
        "\n### 严格意义·本周涨幅前 20（自然周 "
        f"{profile.get('week_first')}～{profile.get('week_last')}，前复权周涨跌）\n\n",
        f"> 抽样全市场约 **{profile.get('universe_n')}** 只；与截面近似可对照。\n\n",
    ]
    if profile.get("strict_top20_avg_mcap_yi") is not None:
        lines.append(
            f"- 前 20 平均流通市值约 **{profile['strict_top20_avg_mcap_yi']} 亿**、"
            f"平均换手率约 **{profile['strict_top20_avg_turnover_pct']}%**\n\n"
        )
    lines.append("| 排名 | 代码 | 名称 | 本周涨跌% | 流通市值(亿) | 换手% |\n")
    lines.append("|------|------|------|-----------|-------------|-------|\n")
    for i, r in enumerate(profile.get("strict_top20") or [], start=1):
        mv = r.get("mcap_yi")
        tr = r.get("turnover")
        lines.append(
            f"| {i} | {r.get('code')} | {r.get('name', '')} | {r.get('week_pct')} | "
            f"{mv if mv is not None else '—'} | {tr if tr is not None else '—'} |\n"
        )
    lines.append("\n")
    return "".join(lines)
