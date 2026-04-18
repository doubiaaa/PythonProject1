# -*- coding: utf-8 -*-
"""
悟道 OpenClaw 全量扩展：在「市场摘要」中追加 Markdown，协助 AI 与人工复盘。
仅在 data_source.use_lb_openclaw 且已配置 LB_API_KEY 时由 get_market_summary 注入。

各子块独立 try/容错，单接口失败不影响其余。
"""
from __future__ import annotations

import html
from typing import Any, Optional

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


def _block_sh_index_kline(ds: str) -> str:
    """上证指数近几日收盘（K 线接口，endDate 对齐复盘日）。"""
    raw = lb_get_safe(
        "/kline/000001",
        {"days": 8, "endDate": _iso(ds)},
    )
    if raw is None:
        raw = lb_get_safe("/kline/000001.SH", {"days": 8, "endDate": _iso(ds)})
    if not isinstance(raw, list) or not raw:
        return ""
    rows = []
    for bar in raw[-6:]:
        if not isinstance(bar, dict):
            continue
        rows.append(
            [
                _esc(bar.get("date")),
                _esc(bar.get("close")),
                _esc(bar.get("pct_chg")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["日期", "收盘", "涨跌幅%"], rows)


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
    if isinstance(raw, dict) and isinstance(raw.get("themes"), list):
        lines = ["| # | 主题 | 摘要 | 热度 |\n| --- | --- | --- | --- |\n"]
        for i, t in enumerate(raw["themes"][:12], 1):
            if not isinstance(t, dict):
                continue
            lines.append(
                f"| {i} | {_esc(t.get('title'))} | {_esc((t.get('summary') or '')[:120])} | "
                f"{_esc(t.get('hotScore'))} |\n"
            )
        return "".join(lines)
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


def _block_hotlist_financial() -> str:
    raw = lb_get_safe("/hotlist", {"type": "financial"})
    if not isinstance(raw, dict) or not isinstance(raw.get("themes"), list):
        return ""
    lines = ["| # | 财经主题 | 摘要 |\n| --- | --- | --- |\n"]
    for i, t in enumerate(raw["themes"][:10], 1):
        if not isinstance(t, dict):
            continue
        lines.append(f"| {i} | {_esc(t.get('title'))} | {_esc((t.get('summary') or '')[:160])} |\n")
    return "".join(lines)


def _block_limit_up_filter(ds: str) -> str:
    raw = lb_get_safe(
        "/limit-up/filter",
        {"date": _iso(ds), "continueNumMin": 2, "limit": 25, "sortBy": "continue_num"},
    )
    if raw is None:
        raw = lb_get_safe(
            "/limit-up/filter",
            {"date": _compact(ds), "continueNumMin": 2, "limit": 25},
        )
    items = raw
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data")
    if not isinstance(items, list) or not items:
        return ""
    rows = []
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("continue_num") or it.get("continueNum")),
                _esc(it.get("reason_type") or it.get("reasonType")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "连板", "原因"], rows)


def _block_approaching_limit_up(ds: str) -> str:
    raw = lb_get_safe("/approaching-limit-up", {"date": _iso(ds)})
    if raw is None:
        raw = lb_get_safe("/approaching-limit-up", {"date": _compact(ds)})
    stocks = None
    if isinstance(raw, dict):
        inner = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        stocks = inner.get("stocks") if isinstance(inner, dict) else None
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
                _esc(it.get("changePercent")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "涨幅%"], rows)


def _block_anomalies(ds: str) -> str:
    raw = lb_get_safe("/anomalies", {"date": _iso(ds)})
    if raw is None:
        raw = lb_get_safe("/anomalies", {"date": _compact(ds)})
    items = raw
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data") or raw.get("list")
    if not isinstance(items, list):
        return ""
    rows = []
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("anomaly_level")),
                _esc(it.get("severe_triggered")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "异动级别", "严重异动"], rows)


def _block_sector_analysis_quadrants() -> str:
    raw = lb_get_safe(
        "/sector-analysis",
        {"source": "dongcai_concept", "period": "60", "strengthPeriod": "5"},
    )
    if not isinstance(raw, dict):
        return ""
    q = raw.get("quadrants") or {}
    if not isinstance(q, dict):
        return ""
    lines = ["| 象限 | 代表板块（至多 3） |\n| --- | --- |\n"]
    for name, key in (
        ("强势主升", "highStrong"),
        ("高位回调", "highWeak"),
        ("底部反转", "lowStrong"),
        ("弱势下跌", "lowWeak"),
    ):
        arr = q.get(key)
        if not isinstance(arr, list):
            continue
        names = []
        for sec in arr[:3]:
            if isinstance(sec, dict) and sec.get("name"):
                names.append(str(sec.get("name")))
        lines.append(f"| {name} | {', '.join(names) if names else '—'} |\n")
    meta = raw.get("meta") or {}
    if isinstance(meta, dict) and meta:
        lines.append(f"\n> meta：`{ _esc(str(meta)[:300]) }`\n")
    return "".join(lines)


def _block_correlation(code6: str) -> str:
    c = "".join(x for x in str(code6) if x.isdigit())[:6]
    if len(c) != 6:
        return ""
    raw = lb_get_safe(f"/correlation/{c}")
    if not isinstance(raw, dict):
        return ""
    cors = raw.get("correlations") or raw.get("data")
    if not isinstance(cors, list):
        return ""
    rows = []
    for it in cors[:8]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("relatedCode") or it.get("related_code")),
                _esc(it.get("relatedName") or it.get("related_name")),
                _esc(it.get("strengthLevel")),
                _esc(it.get("relationshipType")),
            ]
        )
    if not rows:
        return ""
    head = f"> 标的 `{c}`（{ _esc(raw.get('name')) }）关联股摘录\n\n"
    return head + _md_table(["关联代码", "名称", "强度", "关系"], rows)


def _block_briefings(ds: str) -> str:
    for typ in ("closing", "evening", "midday", "morning"):
        raw = lb_get_safe("/briefings", {"date": _iso(ds), "type": typ})
        if raw is None:
            raw = lb_get_safe("/briefings", {"date": _compact(ds), "type": typ})
        items = raw
        if isinstance(raw, dict):
            items = raw.get("items") or raw.get("data") or raw.get("briefings")
        if isinstance(items, list) and items:
            it0 = items[0]
            if not isinstance(it0, dict):
                continue
            content = it0.get("content") or {}
            if not isinstance(content, dict):
                continue
            core = content.get("coreSummary") or content.get("fullContent")
            if core:
                return f"**简报类型** `{typ}`\n\n{_esc(str(core)[:2000])}\n"
    return ""


def _block_research_snippets() -> str:
    raw = lb_get_safe("/research-reports", {"keyword": "涨停", "pageSize": 5, "page": 1})
    items = raw
    if isinstance(raw, dict):
        items = raw.get("reports") or raw.get("items") or raw.get("data")
    if not isinstance(items, list):
        return ""
    rows = []
    for it in items[:5]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("stockName") or it.get("stock_name")),
                _esc(it.get("title"))[:80],
                _esc(it.get("orgSName") or it.get("org")),
                _esc(it.get("emRatingName") or it.get("rating")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["标的", "标题", "机构", "评级"], rows)


def _block_auction_batch(codes: list[str], ds: str) -> str:
    if not codes:
        return ""
    part = ",".join(codes[:20])
    raw = lb_get_safe(
        "/auction",
        {"codes": part, "trade_date": _compact(ds)},
    )
    if raw is None:
        raw = lb_get_safe("/auction", {"codes": part, "trade_date": _iso(ds)})
    items = raw
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data")
    if not isinstance(items, list):
        return ""
    rows = []
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("changeRate")),
                _esc(it.get("bidAmountPercentile")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "竞价涨跌%", "竞价额分位"], rows)


def _block_rank_volume() -> str:
    raw = lb_get_safe("/rank", {"type": "volume", "market": "all", "limit": 12})
    if not isinstance(raw, list):
        return ""
    rows = []
    for it in raw[:12]:
        if not isinstance(it, dict):
            continue
        rows.append(
            [
                _esc(it.get("code")),
                _esc(it.get("name")),
                _esc(it.get("changePercent")),
                _esc(it.get("amount")),
            ]
        )
    if not rows:
        return ""
    return _md_table(["代码", "名称", "涨跌幅%", "成交额"], rows)


def _block_limit_events_down() -> str:
    raw = lb_get_safe("/limit-events", {"type": "limit_down"})
    ev = raw
    if isinstance(raw, dict):
        ev = raw.get("events") or raw.get("data")
    if not isinstance(ev, list) or not ev:
        return ""
    lines = ["| 时间戳 | 代码 | 名称 | 类型 |\n| --- | --- | --- | --- |\n"]
    for it in ev[:10]:
        if not isinstance(it, dict):
            continue
        lines.append(
            f"| {it.get('time')} | {_esc(it.get('code'))} | {_esc(it.get('name'))} | {_esc(it.get('type'))} |\n"
        )
    return "".join(lines)


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


def build_lb_openclaw_assist_section(
    ds: str,
    trade_days: list[str],
    *,
    zt_sample_codes: Optional[list[str]] = None,
) -> str:
    """
    拼装完整扩展 Markdown（含多级标题）。任一字块成功则注入篇首标题；全部失败则返回空串。

    zt_sample_codes：当日涨停池代码（6 位），用于关联股、竞价批量等；可为空。
    """
    ds = _compact(ds)
    if len(ds) != 8:
        return ""

    codes: list[str] = []
    if zt_sample_codes:
        for c in zt_sample_codes:
            s = "".join(x for x in str(c) if x.isdigit())[:6]
            if len(s) == 6 and s not in codes:
                codes.append(s)

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

    kln = _block_sh_index_kline(ds)
    if kln:
        chunks.append("### 上证指数 K 线摘录（kline/000001）\n\n")
        chunks.append(kln)
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

    # —— 以下为悟道 skills 中其余接口（分析 / 情报 / 筛选），逐项容错 ——
    lfu = _block_limit_up_filter(ds)
    if lfu:
        chunks.append("### 涨停筛选（连板≥2，limit-up/filter）\n\n")
        chunks.append(lfu)
        chunks.append("\n")

    ap = _block_approaching_limit_up(ds)
    if ap:
        chunks.append("### 冲刺涨停（approaching-limit-up）\n\n")
        chunks.append(ap)
        chunks.append("\n")

    an = _block_anomalies(ds)
    if an:
        chunks.append("### 异动检测（anomalies）\n\n")
        chunks.append(an)
        chunks.append("\n")

    sa = _block_sector_analysis_quadrants()
    if sa:
        chunks.append("### 板块轮动四象限（sector-analysis）\n\n")
        chunks.append(sa)
        chunks.append("\n")

    rv = _block_rank_volume()
    if rv:
        chunks.append("### 成交额排行 TOP（rank · volume 快照）\n\n")
        chunks.append(rv)
        chunks.append("\n")

    hf = _block_hotlist_financial()
    if hf:
        chunks.append("### 财经主题热榜（hotlist · financial）\n\n")
        chunks.append(hf)
        chunks.append("\n")

    br = _block_briefings(ds)
    if br:
        chunks.append("### AI 市场简报摘录（briefings）\n\n")
        chunks.append(br)
        chunks.append("\n")

    rs = _block_research_snippets()
    if rs:
        chunks.append("### 研报检索摘录（research-reports · 关键词「涨停」）\n\n")
        chunks.append(rs)
        chunks.append("\n")

    if codes:
        cr = _block_correlation(codes[0])
        if cr:
            chunks.append("### 龙头关联股（correlation）\n\n")
            chunks.append(cr)
            chunks.append("\n")

    ac = _block_auction_batch(codes, ds)
    if ac:
        chunks.append("### 样本涨停·集合竞价（auction · 程序代码表）\n\n")
        chunks.append(ac)
        chunks.append("\n")

    led = _block_limit_events_down()
    if led:
        chunks.append("### 跌停侧事件流节选（limit-events · limit_down）\n\n")
        chunks.append(led)
        chunks.append("\n")

    if not chunks:
        return ""

    header = (
        "\n---\n\n## 【悟道 OpenClaw · 扩展数据】（协助复盘 · 与东财/程序表交叉验证）\n\n"
        "> 以下由 **悟道 API** 拉取，**失败子块会省略**；无历史日期的排行/关联为**拉取时刻**或与复盘日对齐的接口为准。\n\n"
    )
    return header + "".join(chunks)
