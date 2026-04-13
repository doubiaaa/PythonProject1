# -*- coding: utf-8 -*-
"""
复盘「六大目录」程序拼装：与业务约定的章节目录对齐，供 get_market_summary 篇首注入。
数据源不足时仍输出小节标题 + 说明，避免结构缺失。
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional

import akshare as ak
import pandas as pd

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.services.data_fetcher import DataFetcher

_log = get_logger(__name__)

_CATALOG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def _norm6(code: object) -> str:
    return "".join(c for c in str(code or "") if c.isdigit()).zfill(6)[:6]


def _board_kind(code: object) -> str:
    c = _norm6(code)
    if not c or len(c) < 6:
        return "其他"
    if c.startswith("300"):
        return "创业板"
    if c.startswith("688"):
        return "科创板"
    if c[0] in ("8", "4") or c[:2] in ("43", "83", "87", "88", "92"):
        return "北交所"
    if c.startswith(("000", "001", "002", "003")):
        return "深市主板"
    if c.startswith("60"):
        return "沪市主板"
    return "其他"


def _is_yizi_row(row: pd.Series) -> bool:
    """一字涨停启发式：炸板次数为 0 且首封时间在早盘集合竞价/开盘附近。"""
    try:
        zb = int(float(row.get("zb_count") or 0))
    except Exception:
        zb = 0
    if zb != 0:
        return False
    ft = str(row.get("first_time") or row.get("首次封板时间") or "")
    ft = ft.replace("：", ":").strip()
    return bool(ft) and (
        "09:25" in ft
        or ft.startswith("09:30")
        or ft.startswith("9:30")
        or ft.startswith("09:31")
    )


def _first_time_series_to_datetime(ser: pd.Series) -> pd.Series:
    """
    首次封板时间列：多为 HH:MM / HH:MM:SS，少数为完整时间戳。
    用固定日期拼接时间字符串排序，避免 pd.to_datetime 无 format 时的推断告警。
    """
    t = ser.astype(str).str.replace("：", ":", regex=False).str.strip()
    prefix = "2000-01-01 "
    t2 = pd.to_datetime(prefix + t, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    t2 = t2.fillna(pd.to_datetime(prefix + t, format="%Y-%m-%d %H:%M", errors="coerce"))
    full_mask = t2.isna() & t.str.contains(r"\d{4}-\d{2}-\d{2}", regex=True, na=False)
    full = pd.Series(pd.NaT, index=ser.index, dtype="datetime64[ns]")
    if bool(full_mask.any()):
        full = pd.to_datetime(t.where(full_mask), errors="coerce")
    return t2.where(t2.notna(), full)


def _md_cell(val: object, max_len: int = 40) -> str:
    t = str(val if val is not None else "").strip()
    t = t.replace("|", "｜").replace("\n", " ")
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _ascii_lb_bars(df_zt: pd.DataFrame, max_width: int = 30) -> str:
    if df_zt is None or df_zt.empty or "lb" not in df_zt.columns:
        return "- （无涨停池）\n"
    from app.utils.output_formatter import draw_text_bar

    vc = df_zt["lb"].value_counts().sort_index()
    total = max(len(df_zt), 1)
    lines = []
    for lb, cnt in vc.items():
        line = draw_text_bar(f"{int(lb)}连板", int(cnt), total, max_len=max_width)
        lines.append(f"- {line}\n")
    return "".join(lines) + "\n"


def _watchlist_spot_followup_md(
    fetcher: "DataFetcher",
    ref_yyyymmdd: str,
    *,
    max_codes: int = 15,
) -> str:
    """监控池涉及代码在全 A 快照中的 5 日/今日涨跌（减轻手工对照）。"""
    try:
        from app.services.watchlist_store import load_all_records
        from app.services.market_style_indices import _find_5d_column
    except Exception:
        return ""
    ref = str(ref_yyyymmdd)[:8]
    recs = load_all_records()
    if not recs:
        return ""
    latest_by_code: dict[str, dict] = {}
    for r in recs:
        c = _norm6(r.get("code"))
        sd = str(r.get("signal_date") or "")[:8]
        if not c or len(sd) != 8 or not sd.isdigit() or sd > ref:
            continue
        prev = latest_by_code.get(c)
        if prev is None or sd > str(prev.get("signal_date") or "")[:8]:
            latest_by_code[c] = r
    codes: list[str] = []
    seen: set[str] = set()
    for r in sorted(
        recs,
        key=lambda x: (str(x.get("signal_date") or ""), str(x.get("code") or "")),
        reverse=True,
    ):
        if str(r.get("signal_date") or "")[:8] > ref:
            continue
        c = _norm6(r.get("code"))
        if c and c not in seen:
            seen.add(c)
            codes.append(c)
        if len(codes) >= max(5, int(max_codes)):
            break
    if not codes:
        return ""
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
    except Exception as e:
        return f"- 监控池快照对照：行情获取失败（{_md_cell(str(e), 60)}）。\n\n"
    if df is None or df.empty:
        return "- 监控池快照对照：行情为空。\n\n"
    col5 = _find_5d_column(df)
    code_c = next((c for c in df.columns if str(c).strip() == "代码"), None)
    if not code_c:
        code_c = next((c for c in df.columns if "代码" in str(c)), None)
    name_c = next((c for c in df.columns if str(c).strip() == "名称"), None)
    if not name_c:
        name_c = next((c for c in df.columns if "名称" in str(c)), None)
    pct1 = next((c for c in df.columns if str(c) == "涨跌幅"), None)
    if not pct1:
        pct1 = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    if not code_c or not name_c:
        return ""
    work = df.copy()
    work["_c6"] = work[code_c].map(_norm6)
    sub = work[work["_c6"].isin(codes)].drop_duplicates("_c6")
    if sub.empty:
        return "- 监控池快照对照：全 A 表中未匹配到上述代码（或数据源未覆盖）。\n\n"
    lines = [
        "#### 监控池标的·行情快照（5 日 / 今日）\n\n",
        "> 与上表档案联动：取最近监控涉及的代码在东财全 A 快照中的涨跌（**非**严格自然区间）。\n\n",
        "| 代码 | 名称 |5日涨跌幅% | 今日涨跌% | 标签（档案） |\n",
        "|------|------|------------|-----------|-------------|\n",
    ]
    want = {c: None for c in codes}
    for _, row in sub.iterrows():
        c6 = _norm6(row.get(code_c))
        if c6 in want:
            want[c6] = row
    for c6 in codes:
        row = want.get(c6)
        if row is None:
            continue
        nm = row.get(name_c)
        p5 = None
        if col5 and col5 in row.index:
            try:
                p5 = float(pd.to_numeric(row[col5], errors="coerce"))
            except Exception:
                p5 = None
        p1v = None
        if pct1 and pct1 in row.index:
            try:
                p1v = float(pd.to_numeric(row[pct1], errors="coerce"))
            except Exception:
                p1v = None
        tag = str(latest_by_code.get(c6, {}).get("tag") or "")[:10]
        lines.append(
            f"| {_md_cell(c6, 8)} | {_md_cell(nm, 8)} | "
            f"{(f'{p5:.2f}' if p5 is not None and pd.notna(p5) else '—')} | "
            f"{(f'{p1v:.2f}' if p1v is not None and pd.notna(p1v) else '—')} | "
            f"{_md_cell(tag, 10)} |\n"
        )
    lines.append(
        "\n> **走势曲线**请在终端查看；邮件内以表代图。\n\n"
    )
    return "".join(lines)


def _lhb_institution_md(date: str, fetcher: "DataFetcher") -> str:
    ds = str(date)[:8].replace("-", "")
    try:
        df = fetcher.fetch_with_retry(
            ak.stock_lhb_jgmmtj_em, start_date=ds, end_date=ds
        )
    except Exception as e:
        return f"- 机构买卖统计获取失败：{_md_cell(str(e), 80)}\n\n"
    if df is None or df.empty:
        return "- 当日机构买卖统计为空或接口无数据。\n\n"
    cols = list(df.columns)
    pick = []
    for i, row in df.head(12).iterrows():
        parts = [str(row.get(c, ""))[:32] for c in cols[:6]]
        pick.append("｜".join(parts))
    lines = ["| 条目（节选列） |\n|------|\n"]
    for p in pick[:10]:
        lines.append(f"| {_md_cell(p, 120)} |\n")
    lines.append("\n")
    return "".join(lines)


def _lhb_trader_md(fetcher: "DataFetcher") -> str:
    try:
        df = fetcher.fetch_with_retry(ak.stock_lhb_traderstatistic_em)
    except Exception as e:
        return f"- 游资/营业部统计获取失败：{_md_cell(str(e), 80)}\n\n"
    if df is None or df.empty:
        return "- 游资追踪数据为空。\n\n"
    cols = list(df.columns)
    lines = ["| 条目（节选） |\n|------|\n"]
    for _, row in df.head(10).iterrows():
        parts = [str(row.get(c, ""))[:40] for c in cols[:5]]
        lines.append(f"| {_md_cell('｜'.join(parts), 140)} |\n")
    lines.append("\n")
    return "".join(lines)


def _lhb_yyb_md(fetcher: "DataFetcher") -> str:
    try:
        df = fetcher.fetch_with_retry(ak.stock_lhb_yybph_em)
    except Exception as e:
        return f"- 营业部排行获取失败：{_md_cell(str(e), 80)}\n\n"
    if df is None or df.empty:
        return "- 营业部买入榜数据为空。\n\n"
    cols = list(df.columns)
    lines = ["| 条目（节选） |\n|------|\n"]
    for _, row in df.head(10).iterrows():
        parts = [str(row.get(c, ""))[:48] for c in cols[:4]]
        lines.append(f"| {_md_cell('｜'.join(parts), 140)} |\n")
    lines.append("\n")
    return "".join(lines)


def _format_fund_flow_block(
    df: pd.DataFrame, *, title: str, max_rows: int = 10
) -> str:
    """东财资金流排行 → Markdown 表（行业/概念并列展示）。"""
    if df is None or df.empty:
        return f"\n#### {title}\n\n- 暂无数据或接口未返回。\n\n"
    lines = [
        f"\n#### {title}\n\n",
        "| 名称 | 涨跌幅% | 主力净流入（亿） |\n|------|--------|------------------|\n",
    ]
    for _, row in df.head(max_rows).iterrows():
        nm = _md_cell(row.get("sector"), 14)
        try:
            pc = float(row.get("pct", 0))
            pc_s = f"{pc:.2f}"
        except Exception:
            pc_s = _md_cell(row.get("pct"), 8)
        try:
            my = float(row.get("money", 0))
            my_s = f"{my:.2f}"
        except Exception:
            my_s = _md_cell(row.get("money"), 10)
        lines.append(f"| {nm} | {pc_s} | {my_s} |\n")
    lines.append("\n")
    return "".join(lines)


def _sentiment_dashboard_block(
    up_n: Optional[int],
    down_n: Optional[int],
    rise_pct: Optional[float],
    zt_in_up_pct: Optional[float],
    zhaban_rate: float,
    seal_ok: Optional[float],
    sentiment_temp: int,
) -> str:
    """对标复盘长图「环形/百分比」：用表格呈现可读性更好的情绪刻度。"""
    lines = [
        "\n#### 情绪仪表盘（程序估算）\n\n",
        "| 维度 | 数值 | 说明 |\n|------|------|------|\n",
    ]
    if up_n is not None and down_n is not None and (up_n + down_n) > 0:
        up_ratio = round(100.0 * up_n / (up_n + down_n), 2)
        lines.append(
            f"| 全 A 上涨家数占比 | **{up_ratio}%** | 涨家数 / (涨+跌)，反映广度 |\n"
        )
        if down_n > 0:
            ud = round(up_n / down_n, 2)
            lines.append(f"| 涨跌家数比 | **{ud} : 1** | 涨家 / 跌家 |\n")
    if rise_pct is not None:
        lines.append(f"| 全 A 上涨率（快照） | **{rise_pct}%** | 与东财 spot 口径一致 |\n")
    if zt_in_up_pct is not None:
        lines.append(
            f"| 涨停家数 / 上涨家数 | **{zt_in_up_pct}%** | 情绪集中度参考 |\n"
        )
    lines.append(f"| 炸板率 | **{zhaban_rate}%** | 炸 / (涨停+炸) |\n")
    if seal_ok is not None:
        lines.append(f"| 封板成功率（估） | **{seal_ok}%** | 涨停 / (涨停+炸) |\n")
    lines.append(
        f"| 情绪温度（程序） | **{sentiment_temp}°C** | 与下文「情绪指数」一致 |\n"
    )
    lines.append(
        "\n> 上述指标对应专业报告中「市场温度 / 涨跌结构」类环形图；邮件环境以表代图。\n\n"
    )
    return "".join(lines)


def _dash_date_yyyymmdd(yyyymmdd: str) -> str:
    s = str(yyyymmdd)[:8]
    if len(s) != 8 or not s.isdigit():
        return s
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _monitor_window_end(signal_date: str, trade_days: list[str], span: int) -> str:
    """自 signal_date 起第 span 个交易日（含首日）的日期；无日历时退回原串。"""
    span = max(1, int(span))
    ds = str(signal_date)[:8]
    day_list = sorted({str(d)[:8] for d in (trade_days or []) if str(d)[:8].isdigit()})
    if not day_list:
        return ds
    start_idx = None
    for i, d in enumerate(day_list):
        if d >= ds:
            start_idx = i
            break
    if start_idx is None:
        start_idx = len(day_list) - 1
    end_idx = min(start_idx + span - 1, len(day_list) - 1)
    return day_list[end_idx]


def _watchlist_program_pool_md(
    trade_days: list[str],
    ref_yyyymmdd: str,
    *,
    max_rows: int,
    monitor_span: int,
) -> str:
    """程序龙头池持久化档案，对齐专业复盘「监控池」表意。"""
    try:
        from app.services.watchlist_store import load_all_records
    except Exception as e:
        return f"- 加载监控池模块失败：{_md_cell(str(e), 72)}\n\n"
    recs = load_all_records()
    if not recs:
        return (
            "- `data/watchlist_records.json` 尚无记录；龙头池随竞价/复盘写入后次日可见档案。\n\n"
        )
    ref = str(ref_yyyymmdd)[:8]
    filtered = [r for r in recs if str(r.get("signal_date") or "")[:8] <= ref]
    filtered.sort(
        key=lambda x: (
            str(x.get("signal_date") or ""),
            str(x.get("code") or ""),
        ),
        reverse=True,
    )
    take = filtered[: max(1, int(max_rows))]
    lines = [
        "> **口径**：监控开始 =程序写入的 `signal_date`；监控结束 = 该日起 **连续 "
        f"{monitor_span}** 个交易日（含首日）的末日，用于对照区间表现（与真实人工池可能不同）。\n\n",
        "| 代码 | 名称 | 监控开始 | 监控结束 | 池内序 | 标签 | 板块 |\n",
        "|------|------|----------|----------|--------|------|------|\n",
    ]
    for r in take:
        sd = str(r.get("signal_date") or "")[:8]
        ed = _monitor_window_end(sd, trade_days, monitor_span)
        lines.append(
            f"| {_md_cell(r.get('code'), 8)} | {_md_cell(r.get('name'), 10)} | "
            f"{_dash_date_yyyymmdd(sd)} | {_dash_date_yyyymmdd(ed)} | "
            f"{int(r.get('rank') or 0)} | {_md_cell(r.get('tag'), 10)} | "
            f"{_md_cell(r.get('sector'), 12)} |\n"
        )
    lines.append("\n")
    return "".join(lines)


def _spot_five_day_leaderboard_md(fetcher: "DataFetcher", top_n: int) -> str:
    """两市 A 股快照：按 5 日涨跌幅排序的 TOP N（东财列存在时）。"""
    try:
        from app.services.market_style_indices import _find_5d_column
    except Exception:
        _find_5d_column = None  # type: ignore

    n = max(3, min(50, int(top_n)))
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
    except Exception as e:
        return f"- 全市场行情获取失败：{_md_cell(str(e), 80)}\n\n"
    if df is None or df.empty:
        return "- 全市场行情为空。\n\n"
    col5 = _find_5d_column(df) if _find_5d_column else None
    code_c = next((c for c in df.columns if str(c).strip() == "代码"), None)
    if not code_c:
        code_c = next((c for c in df.columns if "代码" in str(c)), None)
    name_c = next((c for c in df.columns if str(c).strip() == "名称"), None)
    if not name_c:
        name_c = next((c for c in df.columns if "名称" in str(c)), None)
    pct1 = next((c for c in df.columns if str(c) == "涨跌幅"), None)
    if not pct1:
        pct1 = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    price_c = next(
        (c for c in df.columns if str(c) in ("最新价", "现价")),
        None,
    )
    if not col5 or not code_c or not name_c:
        return (
            "- 当前行情源无 **5 日涨跌幅** 列（如新浪备用源），本节跳过；可改用东财终端查看「5日涨幅榜」。\n\n"
        )
    work = df.copy()
    work["_p5"] = pd.to_numeric(work[col5], errors="coerce")
    work = work.dropna(subset=["_p5"])
    work = work.sort_values("_p5", ascending=False).head(n)
    lines = [
        f"> 快照口径，**非**严格「自然五日区间」复盘；列 **{col5}** ·今日涨跌 **{pct1 or '—'}**。\n\n",
        "| 排名 | 代码 | 名称 |5日涨跌幅% | 今日涨跌% | 最新价 | 备注 |\n",
        "|------|------|------|------------|-----------|--------|------|\n",
    ]
    for i, (_, row) in enumerate(work.iterrows(), start=1):
        c = row.get(code_c)
        nm = row.get(name_c)
        p5 = row.get("_p5")
        p1v = float(row[pct1]) if pct1 and pd.notna(row.get(pct1)) else None
        px = row.get(price_c) if price_c else None
        note = _board_kind(c)
        lines.append(
            f"| {i} | {_md_cell(c, 8)} | {_md_cell(nm, 10)} | "
            f"{float(p5):.2f} | "
            f"{(f'{p1v:.2f}' if p1v is not None else '—')} | "
            f"{(_md_cell(px, 10) if px is not None else '—')} | {note} |\n"
        )
    lines.append(
        "\n- **题材归纳**请见正文「涨停原因 / 核心股」；程序表不替代资讯解读。\n\n"
    )
    return "".join(lines)


def build_six_section_catalog(
    fetcher: "DataFetcher",
    date: str,
    trade_days: list[str],
    *,
    zt_count: int,
    dt_count: int,
    zb_count: int,
    zhaban_rate: float,
    up_n: Optional[int],
    down_n: Optional[int],
    north_money: float,
    north_status: str,
    sentiment_temp: int,
    market_phase: str,
    position_suggestion: str,
    df_zt: pd.DataFrame,
    df_zb: pd.DataFrame,
    df_sector: Optional[pd.DataFrame] = None,
    df_concept: Optional[pd.DataFrame] = None,
) -> str:
    ds = str(date)[:8]
    ds_fmt = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"

    turnover_yi, rise_pct, _ = fetcher._spot_turnover_rise_rate_flat()
    tags = fetcher._sentiment_tags_line(
        zt_count=zt_count,
        dt_count=dt_count,
        zb_count=zb_count,
        zhaban_rate=zhaban_rate,
        turnover_yi=turnover_yi,
        rise_pct=rise_pct,
    )
    north_s = (
        "北向：获取失败"
        if north_status == "fetch_failed"
        else (
            "北向：空表"
            if north_status == "empty_df"
            else (
                "北向净流入：0 亿（口径）"
                if north_status == "ok_zero"
                else f"北向净流入：{north_money} 亿"
            )
        )
    )
    max_lb = 0
    if not df_zt.empty and "lb" in df_zt.columns:
        try:
            max_lb = int(df_zt["lb"].max())
        except Exception:
            max_lb = 0
    seal_ok = (
        round(100.0 * zt_count / (zt_count + zb_count), 2)
        if zt_count + zb_count > 0
        else None
    )
    zt_in_up_pct = (
        round(100.0 * zt_count / up_n, 2)
        if up_n is not None and up_n > 0
        else None
    )

    if df_sector is None:
        df_sector = pd.DataFrame()
    if df_concept is None:
        df_concept = pd.DataFrame()

    lines: list[str] = [
        f"## 【程序生成】复盘数据目录（{ds_fmt}）\n",
        "> 下表为**可核对数据**；正文 **勿复述全表**，只摘结论与关键数字。\n\n",
        "---\n\n",
        "## 0. 盘面总览（结构化速览）\n\n",
        _sentiment_dashboard_block(
            up_n,
            down_n,
            rise_pct,
            zt_in_up_pct,
            zhaban_rate,
            seal_ok,
            sentiment_temp,
        ),
        _format_fund_flow_block(df_sector, title="行业 · 主力净流入 TOP（东财·今日）", max_rows=8),
        _format_fund_flow_block(
            df_concept, title="概念 · 主力净流入 TOP（东财·今日）", max_rows=10
        ),
        "---\n\n",
        "## 1. 复盘总结\n\n",
        "### 1.1 连板梯队\n\n",
    ]
    if not df_zt.empty and "lb" in df_zt.columns:
        vc = df_zt["lb"].value_counts().sort_index()
        lines.append("- 结构：" + "，".join(f"{k}连×{int(v)}只" for k, v in vc.items()) + "\n")
        lines.append(f"- 最高连板：**{max_lb}** 板\n\n")
        lines.append(_ascii_lb_bars(df_zt))
    else:
        lines.append("- 涨停池为空。\n\n")

    lines.append("### 1.2 市场数据概括\n\n")
    lines.append("| 项目 | 内容 |\n|------|------|\n")
    lines.append(f"| 涨跌停 | 涨停 **{zt_count}** / 跌停 **{dt_count}** |\n")
    lines.append(
        f"| 炸板 | **{zb_count}** 只 · 炸板率 **{zhaban_rate:.2f}%**（炸 / (涨停+炸)） |\n"
    )
    if up_n is not None and down_n is not None:
        lines.append(f"| 涨跌家数（全 A） | 涨 **{up_n}** / 跌 **{down_n}** |\n")
    if max_lb > 0:
        lines.append(f"| 最高连板 | **{max_lb}** 板 |\n")
    if zt_in_up_pct is not None:
        lines.append(f"| 涨停家数/上涨家数 | **{zt_in_up_pct}%** |\n")
    if seal_ok is not None:
        lines.append(f"| 封板成功率（估） | **{seal_ok}%** |\n")
    if rise_pct is not None:
        lines.append(f"| 上涨率 | **{rise_pct}%** |\n")
    if turnover_yi is not None:
        ty = (
            f"{round(turnover_yi / 10000, 2)} 万亿"
            if turnover_yi >= 10000
            else f"{round(turnover_yi, 2)} 亿"
        )
        lines.append(f"| 成交额（估） | **{ty}** |\n")
    lines.append(f"| 北向 | {north_s} |\n")
    pa = getattr(fetcher, "_last_premium_analysis", None) or {}
    if isinstance(pa, dict) and (pa.get("display_line") or "").strip():
        lines.append(f"| 昨日涨停溢价 | {pa['display_line']} |\n")
    bf = getattr(fetcher, "_last_big_face_count", None)
    if bf is not None and int(bf) >= 0:
        lines.append(
            f"| 大面（亏钱效应） | **{int(bf)}** 只（昨涨停今跌超 **5%** 或跌停） |\n"
        )
    lines.append(
        f"| 情绪温度 / 阶段 | **{sentiment_temp}°C** · **{market_phase}** · 建议仓位 **{position_suggestion}** |\n"
    )
    lines.append(f"| 情绪标签 | {tags} |\n\n")
    five_d = fetcher._five_day_market_table_markdown(date, trade_days, up_n, down_n)
    lines.append(five_d if five_d else "#### 近5交易日对照\n\n- 数据不足。\n\n")
    lines.append("#### 涨跌分布（全 A）\n\n")
    dist = fetcher._spot_price_distribution_markdown()
    lines.append(dist if dist else "- 暂不可用。\n\n")

    lines.append("### 1.3 市场指数\n\n")
    lines.append(fetcher._index_snapshot_markdown())

    lines.append("### 1.4 题材小结（程序·行业 TOP）\n\n")
    if not df_zt.empty and "industry" in df_zt.columns:
        for ind, cnt in df_zt["industry"].value_counts().head(5).items():
            lines.append(f"- **{_md_cell(ind, 16)}**：{int(cnt)} 家涨停\n")
        lines.append("\n")
    else:
        lines.append("- 无行业字段或涨停池为空。\n\n")

    lines.append("---\n\n## 2. 涨停原因\n\n")

    lines.append("### 2.1 一字涨停股（启发式）\n\n")
    lines.append(
        "> 规则：`炸板次数=0` 且首封时间在 **09:25～09:31** 附近；与真实一字仍有偏差，以行情软件为准。\n\n"
    )
    if not df_zt.empty:
        yz = df_zt[df_zt.apply(_is_yizi_row, axis=1)]
        if yz.empty:
            lines.append("- 未筛出符合启发式的一字样本。\n\n")
        else:
            lines.append("| 代码 | 名称 | 连板 | 首封 | 涨停原因 |\n|------|------|------|------|----------|\n")
            for _, row in yz.head(20).iterrows():
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | "
                    f"{int(row.get('lb') or 0)} | {_md_cell(row.get('first_time'), 10)} | "
                    f"{_md_cell(row.get('reason'), 28)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无数据。\n\n")

    lines.append("### 2.2 创业板涨停\n\n")
    if not df_zt.empty:
        cy = df_zt[df_zt["code"].map(lambda x: _norm6(x).startswith("300"))]
        if cy.empty:
            lines.append("- 当日无创业板涨停样本。\n\n")
        else:
            lines.append(
                "| 代码 | 名称 | 连板 | 涨跌幅% | 涨停原因 |\n|------|------|------|--------|----------|\n"
            )
            for _, row in cy.iterrows():
                try:
                    pc = f"{float(row.get('pct_chg', 0)):.2f}"
                except Exception:
                    pc = "—"
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | "
                    f"{int(row.get('lb') or 0)} | {pc} | {_md_cell(row.get('reason'), 32)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无。\n\n")

    lines.append("### 2.3 科创板与北交所涨停\n\n")
    if not df_zt.empty:
        kcb_bj = df_zt[
            df_zt["code"].map(
                lambda x: _board_kind(x) in ("科创板", "北交所")
            )
        ]
        if kcb_bj.empty:
            lines.append("- 当日无科创板/北交所涨停样本。\n\n")
        else:
            lines.append(
                "| 代码 | 名称 | 板块 | 连板 | 涨跌幅% | 涨停原因 |\n"
                "|------|------|------|------|--------|----------|\n"
            )
            for _, row in kcb_bj.iterrows():
                bk = _board_kind(row.get("code"))
                try:
                    pc = f"{float(row.get('pct_chg', 0)):.2f}"
                except Exception:
                    pc = "—"
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | {bk} | "
                    f"{int(row.get('lb') or 0)} | {pc} | {_md_cell(row.get('reason'), 28)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无。\n\n")

    lines.append("### 2.4 热点题材分类（行业聚合）\n\n")
    lines.append(fetcher._format_zt_industry_top_table_markdown(df_zt, top_n=8))
    lines.append(
        fetcher._format_zt_industry_detail_blocks_markdown(
            df_zt, top_industries=4, per_sector=8
        )
    )

    lines.append("### 2.5 其他涨停（非热点 TOP6 行业）\n\n")
    if not df_zt.empty and "industry" in df_zt.columns:
        hot = set(df_zt["industry"].value_counts().head(6).index.astype(str))
        rest = df_zt[~df_zt["industry"].astype(str).isin(hot)]
        if rest.empty:
            lines.append("- （全部落在热点 TOP6 内，或池为空。）\n\n")
        else:
            lines.append(
                "| 代码 | 名称 | 行业 | 连板 | 涨停原因 |\n|------|------|------|------|----------|\n"
            )
            for _, row in rest.head(25).iterrows():
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | "
                    f"{_md_cell(row.get('industry'), 10)} | {int(row.get('lb') or 0)} | "
                    f"{_md_cell(row.get('reason'), 32)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无法分类。\n\n")

    lines.append("### 2.6 涨停打开（炸板池）\n\n")
    if df_zb is not None and not df_zb.empty:
        lines.append(f"- 炸板 **{len(df_zb)}** 只（详见交易所「炸板池」口径）。\n")
        if "code" in df_zb.columns and "name" in df_zb.columns:
            lines.append("| 代码 | 名称 |\n|------|------|\n")
            for _, row in df_zb.head(25).iterrows():
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 12)} |\n"
                )
        lines.append("\n")
    else:
        lines.append("- 炸板池为空或未获取。\n\n")

    lines.append("---\n\n## 3. 特色数据补充\n\n")
    lines.append("### 3.1 最近涨停股（近5交易日·涨停家数轨迹）\n\n")
    hist, trend = fetcher.compute_ladder_history_5d(date, trade_days)
    if hist:
        lines.append("| 日期 | 涨停家数 | ≥2连合计 |\n|------|----------|----------|\n")
        for r in hist:
            lines.append(
                f"| {r.get('date','')} | {r.get('total_zt',0)} | {r.get('multi_board_sum',0)} |\n"
            )
        lines.append(f"\n- **倾向**：{trend}\n\n")
    else:
        lines.append("- 样本不足。\n\n")

    lines.append("---\n\n## 4. 龙虎榜数据\n\n")
    try:
        from app.utils.config import ConfigManager

        _lhb_on = bool(ConfigManager().get("enable_replay_lhb_catalog", True))
    except Exception:
        _lhb_on = True
    if not _lhb_on:
        lines.append(
            "> 已按配置 **跳过** 龙虎榜接口（`enable_replay_lhb_catalog: false`）。\n\n"
        )
    else:
        lines.append("> 口径差异大，仅供参考。\n\n")
        lines.append("### 4.1 游资追踪（营业部统计·节选）\n\n")
        lines.append(_lhb_trader_md(fetcher))
        lines.append("### 4.2 机构买卖（上榜日统计·节选）\n\n")
        lines.append(_lhb_institution_md(date, fetcher))
        lines.append("### 4.3 营业部买入榜（排行·节选）\n\n")
        lines.append(_lhb_yyb_md(fetcher))

    lines.append("---\n\n## 5. 情绪指数\n\n")
    lines.append("### 5.1 热点强度（程序）\n\n")
    lines.append(
        f"- 情绪温度 **{sentiment_temp}°C**，阶段 **{market_phase}**，标签：{tags}\n\n"
    )
    lines.append("### 5.2 程序龙头池档案（监控池）\n\n")
    cm5: Optional[Any] = None
    try:
        from app.utils.config import ConfigManager

        cm5 = ConfigManager()
    except Exception:
        cm5 = None
    if cm5 is None:
        lines.append("- （读取配置失败。）\n\n")
    else:
        if bool(cm5.get("enable_replay_watchlist_snapshot", True)):
            lines.append(
                _watchlist_program_pool_md(
                    trade_days,
                    ds,
                    max_rows=int(cm5.get("replay_watchlist_max_rows", 40)),
                    monitor_span=int(cm5.get("replay_watchlist_monitor_span", 5)),
                )
            )
            if bool(cm5.get("enable_replay_watchlist_spot_followup", True)):
                lines.append(
                    _watchlist_spot_followup_md(
                        fetcher,
                        ds,
                        max_codes=int(
                            cm5.get("replay_watchlist_spot_followup_max_codes", 15)
                        ),
                    )
                )
        else:
            lines.append(
                "> 已按配置跳过龙头池档案（`enable_replay_watchlist_snapshot: false`）。\n\n"
            )
        raw = cm5.get("concept_board_symbols") or []
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        if raw:
            lines.append(
                "- 另：配置的概念观察（`concept_board_symbols`）："
                + "、".join(str(x) for x in raw[:8])
                + "\n\n"
            )
        else:
            lines.append(
                "- 未配置 `concept_board_symbols` 时，仅上表 **程序龙头池** 与正文竞价块为准。\n\n"
            )

    lines.append("### 5.3 两市 A 股五日涨幅榜（快照 TOP）\n\n")
    if cm5 is not None and bool(cm5.get("enable_replay_spot_5d_leaderboard", True)):
        lines.append(
            _spot_five_day_leaderboard_md(
                fetcher, int(cm5.get("replay_spot_5d_top_n", 19))
            )
        )
    elif cm5 is not None:
        lines.append(
            "> 已按配置跳过五日涨幅榜（`enable_replay_spot_5d_leaderboard: false`）。\n\n"
        )
    else:
        lines.append("- （配置不可用，跳过全 A 五日榜。）\n\n")

    lines.append("#### 数据驱动的优化点（须正文落地）\n\n")
    lines.append(
        "> 正文收束处 **2～4 条**可执行项（与上表挂钩）。\n\n"
    )

    lines.append("---\n\n## 6. 个股解析（按涨停时间排序）\n\n")
    lines.append("> 按首封时间升序；解析见正文 **五、核心股聚焦**。\n\n")
    if not df_zt.empty and "first_time" in df_zt.columns:
        sub = df_zt.copy()
        sub["_ft"] = _first_time_series_to_datetime(sub["first_time"])
        sub = sub.sort_values("_ft", na_position="last")
        max_rows = 35
        sub_show = sub.head(max_rows)
        lines.append(
            "| 时间 | 代码 | 名称 | 连板 | 行业 | 涨停原因 |\n"
            "|------|------|------|------|------|----------|\n"
        )
        for _, row in sub_show.iterrows():
            lines.append(
                f"| {_md_cell(row.get('first_time'), 10)} | {_md_cell(row.get('code'), 8)} | "
                f"{_md_cell(row.get('name'), 8)} | {int(row.get('lb') or 0)} | "
                f"{_md_cell(row.get('industry'), 8)} | {_md_cell(row.get('reason'), 36)} |\n"
            )
        if len(sub) > max_rows:
            lines.append(f"\n> 共 {len(sub)} 只，表列前 **{max_rows}** 只；其余见终端。\n\n")
        else:
            lines.append("\n")
    elif not df_zt.empty:
        lines.append(
            "> 涨停池无「首次封板时间」列，改按 **连板分档** 展示。\n\n"
        )
        lines.append(fetcher._format_zt_tier_detail_tables_markdown(df_zt))
    else:
        lines.append("- 无涨停池。\n\n")

    lines.append("---\n\n")
    return "".join(lines)
