# -*- coding: utf-8 -*-
"""
复盘「六大目录」程序拼装：与业务约定的章节目录对齐，供 get_market_summary 篇首注入。
数据源不足时仍输出小节标题 + 说明，避免结构缺失。
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import akshare as ak
import pandas as pd

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.services.data_fetcher import DataFetcher

_log = get_logger(__name__)


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


def _md_cell(val: object, max_len: int = 40) -> str:
    t = str(val if val is not None else "").strip()
    t = t.replace("|", "｜").replace("\n", " ")
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _index_spot_df(fetcher: "DataFetcher") -> Optional[pd.DataFrame]:
    try:
        return fetcher.fetch_with_retry(ak.stock_zh_index_spot_em)
    except Exception as e:
        _log.warning("index spot for catalog: %s", e)
        return None


def _index_pct_row(df: Optional[pd.DataFrame], name_subs: tuple[str, ...]) -> Optional[tuple[str, float]]:
    if df is None or df.empty:
        return None
    name_col = next((c for c in df.columns if str(c) in ("名称", "name")), None)
    pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    if not name_col or not pct_col:
        return None
    for sub in name_subs:
        m = df[df[name_col].astype(str).str.contains(sub, na=False)]
        if not m.empty:
            try:
                return str(m.iloc[0][name_col]).strip()[:14], float(m.iloc[0][pct_col])
            except Exception:
                continue
    return None


def _ascii_lb_bars(df_zt: pd.DataFrame, max_width: int = 28) -> str:
    if df_zt is None or df_zt.empty or "lb" not in df_zt.columns:
        return "- （无涨停池）\n"
    vc = df_zt["lb"].value_counts().sort_index()
    mx = max(int(vc.max()), 1)
    lines = []
    for lb, cnt in vc.items():
        w = max(1, int(round(cnt / mx * max_width)))
        lines.append(f"- {int(lb)} 连板 │{'█' * w} {int(cnt)} 只\n")
    return "".join(lines) + "\n"


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


def _nine_grid_markdown(sentiment_temp: int, market_phase: str) -> str:
    """简版情绪九宫格：温度分档 × 周期阶段。"""
    t = sentiment_temp
    if t < 35:
        row = "偏冷"
    elif t < 65:
        row = "中性"
    else:
        row = "偏热"
    col = market_phase[:4] if market_phase else "—"
    return (
        "|  | 低位承接 | 中位震荡 | 高位分歧 |\n"
        "|--|---------|---------|---------|\n"
        f"| **情绪温度** | {t}°C（{row}） | 程序阶段：{col} | 详见周期定性 |\n\n"
        "> 精细九宫格需自定义规则；此处为**扫读占位**，与正文「周期定性」一致即可。\n\n"
    )


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

    idx_df = _index_spot_df(fetcher)
    if df_sector is None:
        df_sector = pd.DataFrame()
    if df_concept is None:
        df_concept = pd.DataFrame()

    lines: list[str] = [
        f"## 【程序生成】复盘数据目录（{ds_fmt}）\n",
        "> 以下为固定 **六大块** 结构；篇首增加 **盘面总览**，对齐专业复盘长图中的大盘概览、情绪刻度与分类强弱表（以 **Markdown 表格** 呈现，便于邮件与推送）。\n\n",
        "---\n\n",
        "## 0. 盘面总览（结构化速览）\n\n",
        "> **说明**：参考专业复盘中的 K 线、分时、环形图等，程序侧以 **可审计数据表** 为主；"
        "精细图请使用行情终端。\n\n",
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
            df_concept, title="概念 · 主力净流入 TOP（东财·今日）", max_rows=12
        ),
        "#### 多维趋势提示\n\n",
        "- **涨停家数 / 连板** 近 5 日轨迹见下文 **第 3 节** 与 **第 1.1 节**。\n",
        "- **分档涨停、题材明细** 见 **第 2 节**；**指数点位** 见 **第 1.3 节**。\n\n",
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

    lines.append("### 1.4 盘面小结\n\n")
    lines.append(
        "> **程序不写定性小结**；请阅读正文 **「### 一、盘面综述」**，并与本节 1.2 数据对齐。\n\n"
    )

    lines.append("### 1.5 题材小结（程序·行业 TOP）\n\n")
    if not df_zt.empty and "industry" in df_zt.columns:
        for ind, cnt in df_zt["industry"].value_counts().head(8).items():
            lines.append(f"- **{_md_cell(ind, 16)}**：{int(cnt)} 家涨停\n")
        lines.append("\n")
    else:
        lines.append("- 无行业字段或涨停池为空。\n\n")

    lines.append("---\n\n## 2. 涨停原因\n\n")

    lines.append("### 2.1 连板图（分布示意）\n\n")
    lines.append(_ascii_lb_bars(df_zt))

    lines.append("### 2.2 一字涨停股（启发式）\n\n")
    lines.append(
        "> 规则：`炸板次数=0` 且首封时间在 **09:25～09:31** 附近；与真实一字仍有偏差，以行情软件为准。\n\n"
    )
    if not df_zt.empty:
        yz = df_zt[df_zt.apply(_is_yizi_row, axis=1)]
        if yz.empty:
            lines.append("- 未筛出符合启发式的一字样本。\n\n")
        else:
            lines.append("| 代码 | 名称 | 连板 | 首封 | 涨停原因 |\n|------|------|------|------|----------|\n")
            for _, row in yz.head(30).iterrows():
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | "
                    f"{int(row.get('lb') or 0)} | {_md_cell(row.get('first_time'), 10)} | "
                    f"{_md_cell(row.get('reason'), 28)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无数据。\n\n")

    lines.append("### 2.3 N 字板\n\n")
    lines.append(
        "- 需多日 K 线与断板识别，**当前程序未计算**；可在正文由模型结合题材简述。\n\n"
    )

    lines.append("### 2.4 创业板涨停\n\n")
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

    lines.append("### 2.5 科创板与北交所涨停\n\n")
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

    lines.append("### 2.6 热点题材分类（行业聚合）\n\n")
    lines.append(fetcher._format_zt_industry_top_table_markdown(df_zt))
    lines.append(fetcher._format_zt_industry_detail_blocks_markdown(df_zt))

    lines.append("### 2.7 其他涨停（非热点 TOP6 行业）\n\n")
    if not df_zt.empty and "industry" in df_zt.columns:
        hot = set(df_zt["industry"].value_counts().head(6).index.astype(str))
        rest = df_zt[~df_zt["industry"].astype(str).isin(hot)]
        if rest.empty:
            lines.append("- （全部落在热点 TOP6 内，或池为空。）\n\n")
        else:
            lines.append(
                "| 代码 | 名称 | 行业 | 连板 | 涨停原因 |\n|------|------|------|------|----------|\n"
            )
            for _, row in rest.head(40).iterrows():
                lines.append(
                    f"| {_md_cell(row.get('code'), 8)} | {_md_cell(row.get('name'), 8)} | "
                    f"{_md_cell(row.get('industry'), 10)} | {int(row.get('lb') or 0)} | "
                    f"{_md_cell(row.get('reason'), 32)} |\n"
                )
            lines.append("\n")
    else:
        lines.append("- 无法分类。\n\n")

    lines.append("### 2.8 涨停打开（炸板池）\n\n")
    if df_zb is not None and not df_zb.empty:
        lines.append(f"- 炸板 **{len(df_zb)}** 只（详见交易所「炸板池」口径）。\n")
        if "code" in df_zb.columns and "name" in df_zb.columns:
            lines.append("| 代码 | 名称 |\n|------|------|\n")
            for _, row in df_zb.head(40).iterrows():
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

    lines.append("### 3.2 创业板指数\n\n")
    cyb = _index_pct_row(idx_df, ("创业板", "创业板指", "创业板指"))
    if cyb:
        lines.append(f"- **{cyb[0]}** 涨跌幅：**{cyb[1]}%**（东财指数快照）\n\n")
    else:
        lines.append("- 未匹配到创业板指行，请见 **1.3 市场指数** 全表。\n\n")

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
        lines.append("> 东财/新浪口径差异大，**仅供资金关注度参考**。\n\n")
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
    lines.append("### 5.2 情绪九宫格（简版）\n\n")
    lines.append(_nine_grid_markdown(sentiment_temp, market_phase))
    lines.append("### 5.3 监控池\n\n")
    try:
        from app.utils.config import ConfigManager

        cm = ConfigManager()
        raw = cm.get("concept_board_symbols") or []
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        if raw:
            lines.append(
                "- 配置的概念观察（`concept_board_symbols`）："
                + "、".join(str(x) for x in raw[:8])
                + "\n\n"
            )
        else:
            lines.append(
                "- 未配置 `concept_board_symbols`；**龙头池**见下文竞价选股块。\n\n"
            )
    except Exception:
        lines.append("- （读取配置失败。）\n\n")

    lines.append("### 5.4 三大抱团区间涨幅（宽基/风格快照）\n\n")
    hs300 = _index_pct_row(idx_df, ("沪深300", "沪深 300"))
    zz500 = _index_pct_row(idx_df, ("中证500", "中证 500"))
    cyb2 = _index_pct_row(idx_df, ("创业板", "创业板指"))
    for label, tup in (("沪深300", hs300), ("中证500", zz500), ("创业板指", cyb2)):
        if tup:
            lines.append(f"- **{label}**（{tup[0]}）：**{tup[1]}%**\n")
    if not any([hs300, zz500, cyb2]):
        lines.append("- 指数快照未匹配到上述宽基，请见 **1.3** 原始表。\n")
    lines.append("\n")

    lines.append("---\n\n## 6. 个股解析（按涨停时间排序）\n\n")
    lines.append(
        "> 程序按「首次封板时间」升序；**细化解析**见正文「核心股聚焦」等章节。\n\n"
    )
    if not df_zt.empty and "first_time" in df_zt.columns:
        sub = df_zt.copy()
        sub["_ft"] = pd.to_datetime(
            sub["first_time"].astype(str).str.replace("：", ":", regex=False),
            errors="coerce",
        )
        sub = sub.sort_values("_ft", na_position="last")
        lines.append(
            "| 时间 | 代码 | 名称 | 连板 | 行业 | 涨停原因 |\n"
            "|------|------|------|------|------|----------|\n"
        )
        for _, row in sub.iterrows():
            lines.append(
                f"| {_md_cell(row.get('first_time'), 10)} | {_md_cell(row.get('code'), 8)} | "
                f"{_md_cell(row.get('name'), 8)} | {int(row.get('lb') or 0)} | "
                f"{_md_cell(row.get('industry'), 8)} | {_md_cell(row.get('reason'), 36)} |\n"
            )
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
