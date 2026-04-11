# -*- coding: utf-8 -*-
"""
周度/月度：对「信号日」龙头池计算区间收益。
口径：信号日 **次一交易日开盘价** → 该开盘价所在自然周 **最后一个交易日收盘价**
（与「次日竞价半路」介入、周内观察的简化一致；周五信号则买入多为下周一，落在下一自然周）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import akshare as ak
import pandas as pd

from app.services.watchlist_store import load_all_records


def norm_code(c: str) -> str:
    return re.sub(r"[^0-9]", "", str(c))[:6].zfill(6)


def first_trade_day_after(signal_date: str, trade_days: list[str]) -> Optional[str]:
    if signal_date not in trade_days:
        return None
    i = trade_days.index(signal_date)
    if i + 1 >= len(trade_days):
        return None
    return trade_days[i + 1]


def friday_of_same_week(d: datetime) -> datetime:
    """自然周周五（周一为一周起点）。"""
    days_ahead = (4 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def last_trade_day_on_or_before(
    trade_days: list[str], end_cap: str
) -> Optional[str]:
    """不超过 end_cap 的最后一个交易日。"""
    cand = [t for t in trade_days if t <= end_cap]
    return cand[-1] if cand else None


def entry_exit_for_signal(
    signal_date: str, trade_days: list[str]
) -> tuple[Optional[str], Optional[str]]:
    """
    买入日 = 信号日次一交易日；卖出日 = 买入日所在自然周周五及之前的最后一个交易日。
    """
    entry = first_trade_day_after(signal_date, trade_days)
    if not entry:
        return None, None
    ed = datetime.strptime(entry, "%Y%m%d")
    fri = friday_of_same_week(ed)
    fri_s = fri.strftime("%Y%m%d")
    exit_day = last_trade_day_on_or_before(trade_days, fri_s)
    if not exit_day or exit_day < entry:
        return entry, None
    return entry, exit_day


def fetch_open_close_qfq(
    code: str, d_entry: str, d_exit: str
) -> tuple[Optional[float], Optional[float]]:
    """前复权 开盘(买入日) / 收盘(卖出日)。"""
    from app.services.price_cache import fetch_open_close_qfq_cached
    c = norm_code(code)
    return fetch_open_close_qfq_cached(c, d_entry, d_exit)


@dataclass
class SignalReturnRow:
    signal_date: str
    code: str
    name: str
    rank: int
    entry_date: Optional[str]
    exit_date: Optional[str]
    ret_pct: Optional[float]
    note: str
    tag: str = ""
    sector: str = ""


def _iso_week_key(dstr: str) -> tuple[int, int]:
    dt = datetime.strptime(dstr, "%Y%m%d")
    y, w, _ = dt.isocalendar()
    return y, w


def records_for_iso_week(
    records: list[dict[str, Any]], iso_year: int, iso_week: int
) -> list[dict[str, Any]]:
    out = []
    for r in records:
        sd = r.get("signal_date")
        if not sd:
            continue
        y, w = _iso_week_key(sd)
        if y == iso_year and w == iso_week:
            out.append(r)
    return out


def compute_returns_for_records(
    records: list[dict[str, Any]], trade_days: list[str], as_of_trade: str
) -> list[SignalReturnRow]:
    """
    as_of_trade: 报告锚点交易日（一般为上一周五）；卖出日若晚于该日则视为尚未到期。
    """
    rows: list[SignalReturnRow] = []
    for r in records:
        code = norm_code(str(r.get("code") or ""))
        name = str(r.get("name") or "")
        signal_date = str(r.get("signal_date") or "")
        rank = int(r.get("rank") or 0)
        tag = str(r.get("tag") or "").strip()
        sector = str(r.get("sector") or "").strip()
        entry, exit_day = entry_exit_for_signal(signal_date, trade_days)
        if not entry:
            rows.append(
                SignalReturnRow(
                    signal_date,
                    code,
                    name,
                    rank,
                    None,
                    None,
                    None,
                    "无次一交易日（数据不足）",
                    tag=tag,
                    sector=sector,
                )
            )
            continue
        if not exit_day:
            rows.append(
                SignalReturnRow(
                    signal_date,
                    code,
                    name,
                    rank,
                    entry,
                    None,
                    None,
                    "无法确定周内卖出日",
                    tag=tag,
                    sector=sector,
                )
            )
            continue
        if exit_day > as_of_trade:
            rows.append(
                SignalReturnRow(
                    signal_date,
                    code,
                    name,
                    rank,
                    entry,
                    exit_day,
                    None,
                    f"尚未到期（卖出日 {exit_day} 晚于报告锚点 {as_of_trade}）",
                    tag=tag,
                    sector=sector,
                )
            )
            continue
        o, cl = fetch_open_close_qfq(code, entry, exit_day)
        if o is None or cl is None:
            rows.append(
                SignalReturnRow(
                    signal_date,
                    code,
                    name,
                    rank,
                    entry,
                    exit_day,
                    None,
                    "行情获取失败",
                    tag=tag,
                    sector=sector,
                )
            )
            continue
        ret = (cl - o) / o * 100.0
        rows.append(
            SignalReturnRow(
                signal_date,
                code,
                name,
                rank,
                entry,
                exit_day,
                round(ret, 2),
                "ok",
                tag=tag,
                sector=sector,
            )
        )
    return rows


def aggregate_completed(rows: list[SignalReturnRow]) -> dict[str, Any]:
    done = [r for r in rows if r.ret_pct is not None]
    if not done:
        return {
            "n": 0,
            "pos_n": 0,
            "neg_n": 0,
            "avg_pct": None,
            "sum_pct": None,
        }
    pos = [r.ret_pct for r in done if r.ret_pct > 0]
    neg = [r.ret_pct for r in done if r.ret_pct < 0]
    zeros = [r.ret_pct for r in done if r.ret_pct == 0]
    return {
        "n": len(done),
        "pos_n": len(pos),
        "neg_n": len(neg),
        "zero_n": len(zeros),
        "avg_pct": round(sum(r.ret_pct for r in done) / len(done), 2),
        "sum_pct": round(sum(r.ret_pct for r in done), 2),
    }


def build_attribution_markdown(rows: list[SignalReturnRow]) -> str:
    """按程序龙头池标签分组，做策略归因（可结算样本）。"""
    done = [r for r in rows if r.ret_pct is not None and r.note == "ok"]
    by_tag: dict[str, list[float]] = {}
    for r in done:
        t = r.tag or "（未标注）"
        by_tag.setdefault(t, []).append(float(r.ret_pct))
    if not by_tag:
        return ""
    lines = [
        "### 策略归因（程序龙头池标签）\n\n",
        "> 按选股时的 **标签**（人气龙头/活口核心等）分组，比较平均涨跌；"
        "样本过少时仅作风格参考。\n\n",
    ]
    for tag, vals in sorted(by_tag.items(), key=lambda x: -len(x[1])):
        avg = sum(vals) / len(vals)
        up = sum(1 for v in vals if v > 0)
        dn = sum(1 for v in vals if v < 0)
        lines.append(
            f"- **{tag}**：{len(vals)} 条，平均 **{round(avg, 2)}%**（涨{up}/跌{dn}）\n"
        )
    lines.append("\n")
    return "".join(lines)


def build_weekly_report_markdown(
    iso_year: int,
    iso_week: int,
    trade_days: list[str],
    anchor_trade: str,
    four_week_stats: Optional[list[dict[str, Any]]] = None,
    fetcher: Any = None,
) -> str:
    """anchor_trade: 一般为上一交易日（周五），用于截断未到期信号。"""
    all_recs = load_all_records()
    week_recs = records_for_iso_week(all_recs, iso_year, iso_week)
    rows = compute_returns_for_records(week_recs, trade_days, anchor_trade)
    agg = aggregate_completed(rows)

    lines: list[str] = []
    lines.append(f"## 龙头池周度表现 · {iso_year} 年第 {iso_week} 周\n\n")
    lines.append(
        "> **收益口径**：信号日次一交易日 **开盘价（前复权）** → 当周最后一个交易日 **收盘价（前复权）**；"
        "与实盘滑点、手续费无关，仅供回顾。\n\n"
    )
    lines.append(
        f"- 报告锚点交易日：**{anchor_trade}**（未到期信号已排除在均值外）\n"
        f"- 本周存档信号条数：**{len(week_recs)}**，可结算：**{agg['n']}**\n"
        f"- 收涨：**{agg['pos_n']}** ；收跌：**{agg['neg_n']}**"
        + (
            f" ；平均收益：**{agg['avg_pct']}%**"
            if agg["avg_pct"] is not None
            else ""
        )
        + "\n\n"
    )

    snapshot_md = ""
    if fetcher is not None:
        from app.utils.config import ConfigManager

        if ConfigManager().get("enable_weekly_market_snapshot", True):
            from app.services.weekly_market_snapshot import (
                collect_week_snapshot,
                format_snapshot_markdown,
            )

            snap = collect_week_snapshot(
                fetcher, trade_days, iso_year, iso_week, anchor_trade
            )
            snapshot_md = format_snapshot_markdown(snap)
    lines.append(snapshot_md)
    lines.append(build_attribution_markdown(rows))

    lines.append("### 明细\n\n")
    lines.append(
        "| 信号日 | 代码 | 名称 | 标签 | 买入日 | 卖出日 | 区间涨跌 | 备注 |\n"
        "|--------|------|------|------|--------|--------|----------|------|\n"
    )
    for r in sorted(rows, key=lambda x: (x.signal_date, x.code)):
        rp = f"{r.ret_pct}%" if r.ret_pct is not None else "—"
        tag_s = r.tag or "—"
        lines.append(
            f"| {r.signal_date} | {r.code} | {r.name} | {r.tag or '—'} | {r.entry_date or '—'} | "
            f"{r.exit_date or '—'} | {rp} | {r.note} |\n"
        )
    lines.append("\n")

    if four_week_stats:
        lines.append("### 近四周合并（按周可结算样本）\n\n")
        lines.append("| 年份 | 周 | 样本数 | 涨/跌 | 平均涨跌% |\n")
        lines.append("|------|-----|--------|-------|----------|\n")
        for s in four_week_stats:
            avg = s.get("avg_pct")
            avg_s = f"{avg}" if avg is not None else "—"
            lines.append(
                f"| {s.get('iso_year')} | {s.get('iso_week')} | {s.get('n')} | "
                f"{s.get('pos_n')}/{s.get('neg_n')} | {avg_s} |\n"
            )
        lines.append("\n")

    lines.append(
        "### 使用说明\n\n"
        "- 数据来自本地 `data/watchlist_records.json`（每次复盘成功且程序产出龙头池时追加）。\n"
        "- 市场快照与标签归因由程序汇总；**风格诊断与下周侧重**见文末大模型分析（若已开启 `enable_weekly_ai_insight`）。\n\n"
    )
    return "".join(lines)


def _prev_iso_week(y: int, w: int) -> tuple[int, int]:
    d = datetime.fromisocalendar(y, w, 1) - timedelta(days=7)
    ny, nw, _ = d.isocalendar()
    return ny, nw


def compute_four_week_rollup(
    trade_days: list[str], anchor_trade: str, end_iso_year: int, end_iso_week: int
) -> list[dict[str, Any]]:
    """从 end 周往前共 4 个自然周（含当周），每周一条 aggregate。"""
    all_recs = load_all_records()
    out: list[dict[str, Any]] = []
    y, w = end_iso_year, end_iso_week
    for _ in range(4):
        recs = records_for_iso_week(all_recs, y, w)
        rows = compute_returns_for_records(recs, trade_days, anchor_trade)
        agg = aggregate_completed(rows)
        out.append(
            {
                "iso_year": y,
                "iso_week": w,
                "n": agg["n"],
                "pos_n": agg["pos_n"],
                "neg_n": agg["neg_n"],
                "avg_pct": agg["avg_pct"],
            }
        )
        y, w = _prev_iso_week(y, w)
    return out


def build_monthly_section(trade_days: list[str], anchor_trade: str) -> str:
    """锚点所在自然月：本月内所有存档信号的区间收益汇总。"""
    dt = datetime.strptime(anchor_trade, "%Y%m%d")
    prefix = f"{dt.year:04d}{dt.month:02d}"
    all_recs = load_all_records()
    mrecs = [
        r
        for r in all_recs
        if str(r.get("signal_date", "")).startswith(prefix)
    ]
    if not mrecs:
        return ""
    rows = compute_returns_for_records(mrecs, trade_days, anchor_trade)
    agg = aggregate_completed(rows)
    lines = [
        f"### 自然月汇总（{dt.year} 年 {dt.month} 月，信号落在本月）\n\n",
        f"- 可结算样本：**{agg['n']}**；涨 **{agg['pos_n']}** / 跌 **{agg['neg_n']}**",
    ]
    if agg.get("avg_pct") is not None:
        lines.append(f"；平均：**{agg['avg_pct']}%**\n\n")
    else:
        lines.append("\n\n")
    lines.append(
        "> *注：月度收益按信号触发日归属，未对跨月持仓进行收益拆分，"
        "实际收益可能与月度区间存在偏差。*\n\n"
    )
    return "".join(lines)


def build_weekly_report_markdown_auto(
    trade_days: list[str],
    anchor_trade: str,
    iso_year: int,
    iso_week: int,
    fetcher: Any = None,
) -> str:
    """生成周报 Markdown（市场快照 + 标签归因 + 明细 + 近四周 + 自然月）。"""
    four = compute_four_week_rollup(
        trade_days, anchor_trade, iso_year, iso_week
    )
    md = build_weekly_report_markdown(
        iso_year,
        iso_week,
        trade_days,
        anchor_trade,
        four_week_stats=four,
        fetcher=fetcher,
    )
    md += build_monthly_section(trade_days, anchor_trade)
    return md
