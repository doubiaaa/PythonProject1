# -*- coding: utf-8 -*-
"""周报用：本周交易日市场快照（涨停/跌停/炸板/溢价/连板高度/板块轮动/强势股特征）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

import pandas as pd

if TYPE_CHECKING:
    from app.services.data_fetcher import DataFetcher


def trade_days_in_iso_week(
    trade_days: list[str], iso_year: int, iso_week: int
) -> list[str]:
    out: list[str] = []
    for d in trade_days:
        dt = datetime.strptime(d, "%Y%m%d")
        y, w, _ = dt.isocalendar()
        if y == iso_year and w == iso_week:
            out.append(d)
    return out


def _prev_iso_week(y: int, w: int) -> tuple[int, int]:
    d = datetime.fromisocalendar(y, w, 1) - timedelta(days=7)
    ny, nw, _ = d.isocalendar()
    return ny, nw


def snapshot_one_day(
    fetcher: Any, date: str, trade_days: list[str]
) -> dict[str, Any]:
    """单日：涨停家数、跌停、炸板、炸板率、溢价、最高连板。"""
    df_zt = fetcher.get_zt_pool(date)
    df_dt = fetcher.get_dt_pool(date)
    df_zb = fetcher.get_zb_pool(date)
    zt_n = len(df_zt)
    dt_n = len(df_dt)
    zb_n = len(df_zb)
    tot = zt_n + zb_n
    zhaban_rate = round(zb_n / tot * 100, 2) if tot > 0 else 0.0
    premium, prem_note = fetcher.get_yest_zt_premium(date, trade_days)
    max_lb = int(df_zt["lb"].max()) if not df_zt.empty and "lb" in df_zt.columns else 0
    top3_ind = ""
    if not df_zt.empty and "industry" in df_zt.columns:
        vc = df_zt["industry"].value_counts().head(3)
        top3_ind = "、".join(f"{k}({v})" for k, v in vc.items())
    return {
        "date": date,
        "zt_n": zt_n,
        "dt_n": dt_n,
        "zb_n": zb_n,
        "zhaban_rate": zhaban_rate,
        "premium": premium,
        "premium_note": str(prem_note),
        "max_lb": max_lb,
        "top3_zt_industry": top3_ind,
    }


def top20_strong_avg_mcap_turnover(fetcher: Any, date: str) -> tuple[Optional[float], Optional[float]]:
    """
    锚点周最后交易日：全市场涨幅前 20 名的平均流通市值（亿）、平均换手率（%）。
    作为「当周强势风格」的近似（非严格本周涨幅前 20）。
    """
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
        if df is None or df.empty:
            return None, None
        if "涨跌幅" not in df.columns:
            return None, None
        sub = df.nlargest(20, "涨跌幅").copy()
        mcol = "流通市值" if "流通市值" in sub.columns else None
        tcol = "换手率" if "换手率" in sub.columns else None
        if not mcol or not tcol:
            return None, None
        mv = pd.to_numeric(sub[mcol], errors="coerce")
        tr = pd.to_numeric(sub[tcol], errors="coerce")
        am = float(mv.mean()) if mv.notna().any() else None
        at = float(tr.mean()) if tr.notna().any() else None
        return (round(am, 2) if am is not None else None, round(at, 2) if at is not None else None)
    except Exception:
        return None, None


def collect_week_snapshot(
    fetcher: Any,
    trade_days: list[str],
    iso_year: int,
    iso_week: int,
    anchor_date: str,
) -> dict[str, Any]:
    """
    本周每个交易日一行快照；锚点日强势股前 20 的市值/换手均值。
    anchor_date 一般为本周最后一个交易日（周五）。
    """
    days = trade_days_in_iso_week(trade_days, iso_year, iso_week)
    daily: list[dict[str, Any]] = []
    for d in days:
        try:
            daily.append(snapshot_one_day(fetcher, d, trade_days))
        except Exception as e:
            daily.append(
                {
                    "date": d,
                    "error": str(e)[:120],
                }
            )
    mcap20, turn20 = top20_strong_avg_mcap_turnover(fetcher, anchor_date)
    py, pw = _prev_iso_week(iso_year, iso_week)
    prev_days = trade_days_in_iso_week(trade_days, py, pw)
    prev_premiums: list[float] = []
    for d in prev_days:
        try:
            p, note = fetcher.get_yest_zt_premium(d, trade_days)
            if isinstance(p, (int, float)) and p != -99.0 and "非交易日" not in str(note):
                prev_premiums.append(float(p))
        except Exception:
            pass
    prev_avg_prem = round(sum(prev_premiums) / len(prev_premiums), 2) if prev_premiums else None
    cur_premiums = []
    for d in days:
        try:
            p, note = fetcher.get_yest_zt_premium(d, trade_days)
            if isinstance(p, (int, float)) and p != -99.0 and "非交易日" not in str(note):
                cur_premiums.append(float(p))
        except Exception:
            pass
    cur_avg_prem = round(sum(cur_premiums) / len(cur_premiums), 2) if cur_premiums else None

    return {
        "iso_year": iso_year,
        "iso_week": iso_week,
        "anchor_date": anchor_date,
        "trade_days": days,
        "daily": daily,
        "anchor_top20_avg_mcap_yi": mcap20,
        "anchor_top20_avg_turnover_pct": turn20,
        "week_avg_yesterday_zt_premium": cur_avg_prem,
        "prev_week_avg_yesterday_zt_premium": prev_avg_prem,
    }


def format_snapshot_markdown(snap: Optional[dict[str, Any]]) -> str:
    if not snap:
        return ""
    lines = [
        "### 本周市场快照（程序统计）\n\n",
        "> 用于风格归纳：涨停家数、炸板率、溢价、连板高度、涨停行业分布；"
        "「锚点日涨幅前 20」的市值与换手为**当日截面**，近似反映当周资金偏好的体量与活跃。\n\n",
    ]
    for row in snap.get("daily") or []:
        if row.get("error"):
            lines.append(f"- **{row.get('date')}**：拉取失败 {row.get('error')}\n")
            continue
        lines.append(
            f"- **{row['date']}**：涨停 **{row['zt_n']}** / 跌停 **{row['dt_n']}** / 炸板 **{row['zb_n']}** "
            f"｜炸板率 **{row['zhaban_rate']}%** ｜最高连板 **{row['max_lb']}** 板"
        )
        prem = row["premium"]
        if isinstance(prem, (int, float)) and prem == -99.0:
            lines.append(f" ｜溢价：{row.get('premium_note', '')}\n")
        else:
            lines.append(f" ｜昨日涨停溢价 **{prem}%**（{row.get('premium_note', '')}）\n")
        if row.get("top3_zt_industry"):
            lines.append(f"  - 涨停行业 TOP3：{row['top3_zt_industry']}\n")
    lines.append("\n")
    ad = snap.get("anchor_date") or (snap.get("trade_days") or [""])[-1]
    if snap.get("anchor_top20_avg_mcap_yi") is not None:
        lines.append(
            f"- **锚点日 {ad}** 全市场涨幅前 20：平均流通市值约 **{snap['anchor_top20_avg_mcap_yi']} 亿**、"
            f"平均换手率约 **{snap['anchor_top20_avg_turnover_pct']}%**\n\n"
        )
    if snap.get("week_avg_yesterday_zt_premium") is not None:
        lines.append(
            f"- **本周**各交易日可算溢价的均值约 **{snap['week_avg_yesterday_zt_premium']}%**"
        )
        if snap.get("prev_week_avg_yesterday_zt_premium") is not None:
            lines.append(
                f"；**上周**同口径约 **{snap['prev_week_avg_yesterday_zt_premium']}%**（可对比情绪变化）"
            )
        lines.append("\n\n")
    return "".join(lines)
