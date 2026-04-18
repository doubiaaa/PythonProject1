# -*- coding: utf-8 -*-
"""
悟道 OpenClaw 全量扩展：在「市场摘要」中追加 Markdown，协助 AI 与人工复盘。
仅在 data_source.use_lb_openclaw 且已配置 LB_API_KEY 时由 get_market_summary 注入。

各子块独立 try/容错，单接口失败不影响其余。
"""
from __future__ import annotations

import html
from typing import Any

from app.services.lb_openclaw_client import lb_get_safe
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _iso(ds: str) -> str:
    d = (ds or "")[:8]
    if len(d) != 8:
        return d
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _compact(ds: str) -> str:
    return "".join(c for c in str(ds) if c.isdigit())[:8]


def _esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))[:200]


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    w = [f"| {' | '.join(headers)} |\n", f"| {' | '.join(['---'] * len(headers))} |\n"]
    for r in rows:
        w.append(f"| {' | '.join(r)} |\n")
    return "".join(w)


def _block_calendar(ds: str) -> str:
    raw = lb_get_safe("/trading-calendar", {"date": _iso(ds)})
    if not isinstance(raw, dict):
        return ""
    ok = raw.get("isTradingDay")
    pre = (
        raw.get("prev_trade_date")
        or raw.get("previous_trade_date")
        or raw.get("pretrade_date")
    )
    line = f"- 交易日校验：**{'是' if ok else '否'}**"
    if pre:
        line += f"；上一交易日：`{pre}`"
    return line + "\n"


def _block_market_overview(ds: str) -> str:
    raw = lb_get_safe("/market-overview", {"date": _iso(ds)})
    if not isinstance(raw, dict):
        return ""
    rows = [
        ["上涨家数", str(raw.get("rise_count", "—"))],
        ["下跌家数", str(raw.get("fall_count", "—"))],
        ["涨停家数", str(raw.get("limit_up_count", "—"))],
        ["跌停家数", str(raw.get("limit_down_count", "—"))],
        ["炸板家数", str(raw.get("limit_up_broken_count", "—"))],
        ["炸板率", str(raw.get("limit_up_broken_ratio", "—"))],
        ["昨涨停今均涨幅%", str(raw.get("yesterday_limit_up_avg_pcp", "—"))],
        ["市场温度", str(raw.get("market_temperature", "—"))],
    ]
    return _md_table(["项目", "悟道·市场概况"], rows)


def _block_limit_stats(ds: str) -> str:
    raw = lb_get_safe("/limit-stats", {"date": _iso(ds)})
    if not isinstance(raw, dict):
        return ""
    lines = ["| 项 | 今日 | 昨日 |\n| --- | --- | --- |\n"]
    lu = raw.get("limitUp") or {}
    ld = raw.get("limitDown") or {}
    for label, key in (("涨停封板数", "num"), ("触及涨停总数", "history_num"), ("封板率", "rate"), ("炸板数", "open_num")):
        t = (lu.get("today") or {}) if isinstance(lu, dict) else {}
        y = (lu.get("yesterday") or {}) if isinstance(lu, dict) else {}
        if isinstance(t, dict) and key in t:
            tv = t.get(key)
            yv = y.get(key) if isinstance(y, dict) else "—"
            lines.append(f"| 涨停·{label} | {tv} | {yv} |\n")
    for label, key in (("跌停封板数", "num"), ("触及跌停总数", "history_num"), ("封板率", "rate"), ("开板", "open_num")):
        t = (ld.get("today") or {}) if isinstance(ld, dict) else {}
        y = (ld.get("yesterday") or {}) if isinstance(ld, dict) else {}
        if isinstance(t, dict) and key in t:
            tv = t.get(key)
            yv = y.get(key) if isinstance(y, dict) else "—"
            lines.append(f"| 跌停·{label} | {tv} | {yv} |\n")
    return "".join(lines)


def _block_hot_sectors(ds: str) -> str:
    raw = lb_get_safe("/hot-sectors", {"date": _iso(ds)})
    if not isinstance(raw, list):
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        if not isinstance(raw, list):
            return ""
    rows = []
    for i, sec in enumerate(raw[:8], 1):
        if not isinstance(sec, dict):
            continue
        rows.append(
            [
                str(i),
                _esc(sec.get("name") or sec.get("code")),
                _esc(sec.get("changePercent")),
                _esc(sec.get("limitUpNum")),
                _esc(sec.get("continuousPlateNum")),
                _esc(sec.get("highBoard")),
                _esc(sec.get("days")),
            ]
        )
    if not rows:
        return ""
    return _md_table(
        ["#", "板块", "涨幅%", "涨停数", "连板数", "高度", "活跃天数"],
        rows,
    )


def _block_rank_pair() -> str:
    """实时排行快照（无历史 date 参数，标注为拉取时刻）。"""
    g = lb_get_safe("/rank", {"type": "gainers", "market": "all", "limit": 15})
    l = lb_get_safe("/rank", {"type": "losers", "market": "all", "limit": 15})
    parts: list[str] = []
    for title, data in (("涨幅榜 TOP15（快照）", g), ("跌幅榜 TOP15（快照）", l)):
        if not isinstance(data, list):
            continue
        rows = []
        for it in data[:15]:
            if not isinstance(it, dict):
                continue
            rows.append(
                [
                    _esc(it.get("rank")),
                    _esc(it.get("code")),
                    _esc(it.get("name")),
                    _esc(it.get("changePercent")),
                    _esc(it.get("amount")),
                ]
            )
        if rows:
            parts.append(f"#### {title}\n\n")
            parts.append(_md_table(["排名", "代码", "名称", "涨跌幅%", "成交额"], rows))
            parts.append("\n")
    return "".join(parts)


def _block_concepts(ds: str) -> str:
    raw = lb_get_safe("/concepts/ranking", {"date": _compact(ds), "limit": 25})
    if raw is None:
        raw = lb_get_safe("/concepts/ranking", {"date": _iso(ds), "limit": 25})
    if not isinstance(raw, list):
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data") or raw.get("list")
        if not isinstance(raw, list):
            return ""
    rows = []
    for i, it in enumerate(raw[:20], 1):
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                str(i),
                _esc(it.get("ts_code") or it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("pct_chg") or it.get("changePercent") or it.get("pct")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["#", "概念代码", "名称", "涨幅%"], rows)


def _block_concept_top_stocks(ds: str) -> str:
    """取概念涨幅第一名的成分股（若接口可用）。"""
    raw = lb_get_safe("/concepts/ranking", {"date": _compact(ds), "limit": 5})
    if not isinstance(raw, list):
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data")
        if not isinstance(raw, list) or not raw:
            return ""
    top = raw[0]
    if not isinstance(top, dict):
        return ""
    ts = str(top.get("ts_code") or top.get("code") or "").strip()
    if not ts:
        return ""
    sub = lb_get_safe(f"/concepts/{ts}/stocks", {"date": _compact(ds)})
    if sub is None:
        sub = lb_get_safe(f"/concepts/{ts}/stocks", {"date": _iso(ds)})
    stocks = sub
    if isinstance(sub, dict):
        stocks = sub.get("stocks") or sub.get("data") or sub.get("items")
    if not isinstance(stocks, list):
        return ""
    rows = []
    for it in stocks[:15]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code") or it.get("ts_code")),
                _esc(it.get("name")),
                _esc(it.get("pct_chg") or it.get("changePercent")),
            ]
        )
    if not rows:
        return ""
    return (
        f"\n> 当日涨幅第一概念 **{_esc(top.get('name'))}**（`{_esc(ts)}`）成分股摘录：\n\n"
        + _md_table(["代码", "名称", "涨幅%"], rows)
    )


def _block_hotlist() -> str:
    raw = lb_get_safe("/hotlist", {"type": "general"})
    items = raw
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data") or raw.get("list") or raw.get("hotList")
    if not isinstance(items, list):
        return ""
    rows = []
    for it in items[:20]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("rank") or it.get("index")),
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("reason") or it.get("tag")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["#", "代码", "名称", "备注"], rows)


def _block_capital_flow(ds: str) -> str:
    parts: list[str] = []
    for flow_type, title in (("hsgt", "北向·资金流向"), ("market", "大盘·资金流向")):
        raw = lb_get_safe(
            "/capital-flow",
            {"flowType": flow_type, "date": _iso(ds), "limit": 15},
        )
        if raw is None:
            raw = lb_get_safe(
                "/capital-flow",
                {"flowType": flow_type, "date": _compact(ds), "limit": 15},
            )
        if isinstance(raw, list) and raw:
            rows = []
            for it in raw[:12]:
                if not isinstance(it, dict):
                    continue
                rows.append([_esc(it.get(k)) for k in list(it.keys())[:5]])
            if rows:
                hdr = [str(i) for i in range(len(rows[0]))]
                parts.append(f"#### {title}\n\n")
                parts.append(_md_table(hdr, rows))
                parts.append("\n")
        elif isinstance(raw, dict):
            parts.append(f"#### {title}\n\n```json\n{str(raw)[:1200]}\n```\n\n")
    return "".join(parts)


def _block_dragon_tiger(ds: str) -> str:
    raw = lb_get_safe(
        "/dragon-tiger",
        {"date": _iso(ds), "page": 1, "pageSize": 30},
    )
    items = raw
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data") or raw.get("list") or raw.get("records")
    if not isinstance(items, list):
        return ""
    rows = []
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code") or it.get("symbol")),
                _esc(it.get("name")),
                _esc(it.get("reason") or it.get("reasonName")),
                _esc(it.get("buy") or it.get("netBuy")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "上榜原因", "净买/特征"], rows)


def _block_limit_events() -> str:
    raw = lb_get_safe("/limit-events", {"type": "limit_up"})
    ev = raw
    if isinstance(raw, dict):
        ev = raw.get("events") or raw.get("data")
    if not isinstance(ev, list) or not ev:
        return ""
    lines = ["| 时间戳 | 代码 | 名称 | 类型 |\n| --- | --- | --- | --- |\n"]
    for it in ev[:12]:
        if not isinstance(it, dict):
            continue
        lines.append(
            f"| {it.get('time')} | {_esc(it.get('code'))} | {_esc(it.get('name'))} | {_esc(it.get('type'))} |\n"
        )
    return "".join(lines)


def _block_premium_window(trade_days: list[str], ds: str) -> str:
    """近若干交易日溢价统计（与当前复盘日对齐的区间）。"""
    if not trade_days or ds not in trade_days:
        return ""
    i = trade_days.index(ds)
    start = max(0, i - 19)
    sd = trade_days[start]
    ed = ds
    raw = lb_get_safe(
        "/limit-up/premium",
        {
            "startDate": _iso(sd),
            "endDate": _iso(ed),
            "limit": 15,
            "page": 1,
        },
    )
    if raw is None:
        raw = lb_get_safe(
            "/limit-up/premium",
            {
                "startDate": _compact(sd),
                "endDate": _compact(ed),
                "limit": 15,
                "page": 1,
            },
        )
    stocks = raw
    if isinstance(raw, dict):
        stocks = raw.get("stocks") or raw.get("items") or raw.get("data")
    if not isinstance(stocks, list):
        return ""
    rows = []
    for it in stocks[:12]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("avgPremium")),
                _esc(it.get("positiveRate")),
                _esc(it.get("totalCount")),
            ]
        )
    if not rows:
        return ""
    return _md_table(
        ["代码", "名称", "平均溢价%", "正溢价率%", "涨停次数"],
        rows,
    )


def build_lb_openclaw_assist_section(ds: str, trade_days: list[str]) -> str:
    """拼装完整扩展 Markdown（含多级标题）。任一字块成功则注入篇首标题；全部失败则返回空串。"""
    ds = _compact(ds)
    if len(ds) != 8:
        return ""

    chunks: list[str] = []

    sub = _block_calendar(ds)
    if sub:
        chunks.append("### 交易日历\n\n")
        chunks.append(sub)
        chunks.append("\n\n")

    mo = _block_market_overview(ds)
    if mo:
        chunks.append("### 市场概况（overview）\n\n")
        chunks.append(mo)
        chunks.append("\n")

    ls = _block_limit_stats(ds)
    if ls:
        chunks.append("### 涨跌停统计（limit-stats）\n\n")
        chunks.append(ls)
        chunks.append("\n")

    hs = _block_hot_sectors(ds)
    if hs:
        chunks.append("### 最强风口（hot-sectors）\n\n")
        chunks.append(hs)
        chunks.append("\n")

    rk = _block_rank_pair()
    if rk:
        chunks.append("### 多维排行（rank · 实时快照）\n\n")
        chunks.append(rk)

    cr = _block_concepts(ds)
    if cr:
        chunks.append("### 概念涨幅排行（concepts/ranking）\n\n")
        chunks.append(cr)
        chunks.append("\n")

    cst = _block_concept_top_stocks(ds)
    if cst:
        chunks.append(cst)
        chunks.append("\n")

    cf = _block_capital_flow(ds)
    if cf:
        chunks.append("### 资金流向（capital-flow）\n\n")
        chunks.append(cf)

    hl = _block_hotlist()
    if hl:
        chunks.append("### 智能热榜（hotlist · general）\n\n")
        chunks.append(hl)
        chunks.append("\n")

    dt = _block_dragon_tiger(ds)
    if dt:
        chunks.append("### 龙虎榜摘录（dragon-tiger）\n\n")
        chunks.append(dt)
        chunks.append("\n")

    ev = _block_limit_events()
    if ev:
        chunks.append("### 封板/炸板事件流（节选 limit-events）\n\n")
        chunks.append(ev)
        chunks.append("\n")

    pr = _block_premium_window(trade_days, ds)
    if pr:
        chunks.append("### 涨停溢价区间统计（近 20 交易日，premium）\n\n")
        chunks.append(pr)
        chunks.append("\n")

    if not chunks:
        return ""

    header = (
        "\n---\n\n## 【悟道 OpenClaw · 扩展数据】（协助复盘 · 与东财/程序表交叉验证）\n\n"
        "> 以下由 **悟道 API** 拉取，**失败子块会省略**；排行类无历史日期参数者为**拉取时刻快照**。\n\n"
    )
    return header + "".join(chunks)
