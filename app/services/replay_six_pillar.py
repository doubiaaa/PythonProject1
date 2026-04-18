# -*- coding: utf-8 -*-
"""
六维复盘框架：将「数据锚定—周期—反人性边界—仓位—心法闭环—每日三省」
固化为篇首程序块，供大模型与人工同一口径对齐。

与 `strategy_engine.compute_short_term_market_phase` 四象限阶段联动；
定量部分依赖全 A 快照、涨跌停池与 fetcher 已计算字段。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import pandas as pd

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.services.data_fetcher import DataFetcher

_log = get_logger(__name__)

# 程序四象限 → 情绪周期六维表述（酝酿 / 开展 / 蔓延 / 退潮）
_PHASE_TO_CYCLE_NAME: dict[str, str] = {
    "混沌·试错期": "酝酿期（冰点 / 试错）",
    "主升期": "开展期（发酵 / 主升）",
    "高位震荡期": "蔓延期（高潮 / 分歧）",
    "退潮·冰点期": "退潮期（衰退 / 冰点）",
}


def _spot_pct_extremes(fetcher: "DataFetcher") -> tuple[Optional[int], Optional[int]]:
    """全 A 涨幅>5% 家数、跌幅<-5% 家数（快照口径）。"""
    try:
        df = fetcher.get_stock_zh_a_spot_em_cached()
        if df is None or df.empty or "涨跌幅" not in df.columns:
            return None, None
        s = pd.to_numeric(df["涨跌幅"], errors="coerce").dropna()
        if s.empty:
            return None, None
        ge5 = int((s > 5).sum())
        lt5 = int((s < -5).sum())
        return ge5, lt5
    except Exception:
        return None, None


def _sum_seal_funds(df_zt: pd.DataFrame) -> tuple[Optional[float], str]:
    """涨停池封单资金合计（若列存在）；东财多为元。"""
    if df_zt is None or df_zt.empty:
        return None, "无涨停池"
    for col in ("封板资金",):
        if col in df_zt.columns:
            try:
                total = pd.to_numeric(df_zt[col], errors="coerce").sum()
                if total is None or pd.isna(total):
                    return None, "封单列无效"
                yi = float(total) / 1e8
                n = len(df_zt)
                avg = float(total) / max(n, 1) / 1e8
                return total, f"合计约 **{yi:.2f}** 亿、均 **{avg:.2f}** 亿/只（粗）"
            except Exception:
                break
    return None, "涨停池无封单资金列（可忽略）"


def _mainline_zt_lines(df_zt: pd.DataFrame) -> tuple[str, Optional[float]]:
    """主线涨停占比：TOP1 行业家数 / 涨停家数。"""
    if df_zt is None or df_zt.empty or "industry" not in df_zt.columns:
        return "—（无行业字段）", None
    vc = df_zt["industry"].fillna("").astype(str).value_counts()
    if vc.empty:
        return "—", None
    top_n = int(vc.iloc[0])
    tot = len(df_zt)
    pct = round(100.0 * top_n / tot, 1) if tot else 0.0
    name = str(vc.index[0])[:20]
    return f"TOP1 行业「{name}」涨停 **{top_n}** 只，占涨停池 **{pct}%**", pct


def _multi_ge2_count(df_zt: pd.DataFrame) -> int:
    if df_zt is None or df_zt.empty or "lb" not in df_zt.columns:
        return 0
    try:
        lb = pd.to_numeric(df_zt["lb"], errors="coerce").fillna(1)
        return int((lb >= 2).sum())
    except Exception:
        return 0


def _north_line(north_money: float, north_status: str) -> str:
    if north_status == "fetch_failed":
        return "获取失败（勿作核心依据）"
    if north_status == "empty_df":
        return "空表（置信度低）"
    if north_status == "ok_zero":
        return "净流入 **0**（口径）"
    return f"净流入 **{north_money}** 亿元"


def _phase_position_cap(market_phase: str) -> str:
    m = str(market_phase or "")
    if "退潮" in m or "冰点" in m:
        return "总仓位建议 **≤20%**（退潮期情绪杀优先于个案胜率）"
    if "主升" in m:
        return "总仓位可 **50%～70%**，一般不高于 **80%**"
    if "震荡" in m or "高位" in m:
        return "总仓位 **≤50%**，逐步兑现后排"
    if "混沌" in m or "试错" in m:
        return "总仓位 **≤30%**，轻仓试错"
    return "与程序 **建议仓位** 区间一致"


def _cycle_signal_hint(
    *,
    zhaban_rate: float,
    zt_count: int,
    dt_count: int,
    max_lb: int,
    multi_ge2: int,
    big_face: int,
) -> str:
    parts: list[str] = []
    if zhaban_rate >= 38:
        parts.append("炸板率偏高，分歧加剧")
    if dt_count >= 15:
        parts.append("跌停家数偏多")
    if big_face >= 10:
        parts.append("大面家数偏高")
    if max_lb >= 6 and multi_ge2 >= 15:
        parts.append("连板高度与梯队尚可")
    if zt_count >= 60 and zhaban_rate < 28:
        parts.append("涨停多且炸板率可控")
    if not parts:
        parts.append("结合下表四象限与数据")
    return "；".join(parts[:4])


def build_six_pillar_framework_markdown(
    fetcher: "DataFetcher",
    *,
    date: str,
    trade_days: list[str],
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
) -> str:
    """
    生成「六维复盘框架」Markdown，插入篇首目录 **之前** 或目录内靠前位置。
    """
    ds = str(date)[:8]
    ge5, lt5 = _spot_pct_extremes(fetcher)
    ge5_s = str(ge5) if ge5 is not None else "—"
    lt5_s = str(lt5) if lt5 is not None else "—"

    max_lb = 0
    if not df_zt.empty and "lb" in df_zt.columns:
        try:
            max_lb = int(pd.to_numeric(df_zt["lb"], errors="coerce").max() or 0)
        except Exception:
            max_lb = 0

    multi_ge2 = _multi_ge2_count(df_zt)
    ml_line, _ml_pct = _mainline_zt_lines(df_zt)
    _seal_total, seal_note = _sum_seal_funds(df_zt)

    bf = int(getattr(fetcher, "_last_big_face_count", 0) or 0)
    prem = getattr(fetcher, "_last_premium_analysis", None) or {}
    prem_line = prem.get("display_line") if isinstance(prem, dict) else ""
    if not (prem_line and str(prem_line).strip()):
        prem_line = "见目录 1.2 市场数据概括"
    prem_line = str(prem_line).replace("|", "｜")[:120]

    cycle_name = _PHASE_TO_CYCLE_NAME.get(
        str(market_phase).strip(), f"（与程序阶段对齐：{market_phase}）"
    )

    signal_hint = _cycle_signal_hint(
        zhaban_rate=zhaban_rate,
        zt_count=zt_count,
        dt_count=dt_count,
        max_lb=max_lb,
        multi_ge2=multi_ge2,
        big_face=bf,
    )
    pos_cap = _phase_position_cap(market_phase)

    turnover_yi, rise_pct, _ = fetcher._spot_turnover_rise_rate_flat()
    ty_s = (
        f"{round(turnover_yi / 10000, 2)} 万亿"
        if turnover_yi is not None and turnover_yi >= 10000
        else (
            f"{round(turnover_yi, 2)} 亿"
            if turnover_yi is not None
            else "—"
        )
    )

    lines: list[str] = [
        "\n## 【六维复盘框架】程序锚定（群体博弈 · 与「**市场阶段**」联动）\n\n",
        "> **短线须单独看主线**：大盘强弱与主线情绪可能背离；下表用**当日程序数据**锚定博弈天平，避免纯主观「感觉好坏」。\n\n",
        "### 一、底层世界观：四组核心数据\n\n",
        "| 维度 | 量化指标（当日程序口径） | 博弈方向（解读） |\n",
        "|------|--------------------------|------------------|\n",
        f"| **赚钱效应** | 涨停 **{zt_count}**；最高 **{max_lb}** 板；≥2 连 **{multi_ge2}** 家；"
        f"主线涨停结构：**{ml_line}**；涨幅>5% 家数 **{ge5_s}**（全A快照） | "
        f"数值整体越高，场外资金进攻意愿越强（须与主线一致） |\n",
        f"| **亏钱效应** | 跌停 **{dt_count}**；炸板率 **{zhaban_rate:.2f}%**；"
        f"跌幅<-5% 家数 **{lt5_s}**；大面 **{bf}** 只；昨日涨停溢价 **{prem_line}** | "
        f"跌停/炸板/大面偏高则筹码兑现意愿强，接力须降档 |\n",
        "| **主线强度** | 以涨停池行业 TOP 占比表征；**连板晋级率**见本文后续「连板晋级率」块 | "
        "主线越强、梯队越健康，赚钱效应越可能延续 |\n",
        f"| **流动性** | 两市成交额（估）**{ty_s}**；上涨家数占比 **{rise_pct if rise_pct is not None else '—'}%**；"
        f"北向 {_north_line(north_money, north_status)}；涨停封单 **{seal_note}** | "
        "缩量且封单弱时，场外资金偏观望 |\n\n",
        "### 二、情绪周期：阶段 + 信号 + 操作（与程序四象限对齐）\n\n",
        f"- **程序当前阶段**：**{market_phase}** → 六维映射为 **{cycle_name}**。\n",
        f"- **当日信号摘要**：{signal_hint}。\n",
        f"- **建议仓位（程序）**：**{position_suggestion}**（情绪温度 **{sentiment_temp}°C**）。\n\n",
        "| 周期阶段（六维） | 核心信号（参考） | 对应操作纪律（与程序建议仓位一致） |\n",
        "|------------------|------------------|------------------------------------|\n",
        "| 酝酿期（冰点/试错） | 连板高度压缩、炸板率高、亏钱效应重、零星首板/二板试探 | 轻仓试错，≤30%；低位首板/弱转强，不追高 |\n",
        "| 开展期（发酵/主升） | 主线清晰、高度打开、跟风批量涨停、扩散 | 聚焦主线龙头/前排，50%～70%；不碰杂毛 |\n",
        "| 蔓延期（高潮/分歧） | 后排补涨、龙头加速、过热后炸板分化 | 减后排、锁利润，≤50%；准备止盈 |\n",
        "| 退潮期（衰退/冰点） | 龙头断板、高度骤降、亏钱扩散、炸板率>40% 等 | 空仓或 ≤20%；不抄底、不接盘；退潮末恐慌常为酝酿起点 |\n\n",
        "> **避坑**：勿把退潮中的反弹当主升；信号未确认前不加仓。\n\n",
        "### 三、反人性名句：使用边界（避免追涨杀跌式误读）\n\n",
        "- **「高手买龙头，超高手卖龙头」**  \n"
        "  - **适用**：买在龙头**分歧**（主升中首次分歧、缩量分歧低吸）；卖在情绪**高潮**（加速一字、跟风全面补涨）。  \n"
        "  - **禁用**：高潮期接盘；龙头刚启动就卖飞（未区分阶段）。\n\n",
        "- **「别人贪婪我更贪婪，别人恐慌我更恐慌」**  \n"
        "  - **适用**：仅在情绪**极端**（冰点试错、高潮止盈）小仓执行。  \n"
        "  - **禁用**：日常波动里「别人涨我追、别人跌我割」——这是被情绪带着走。\n\n",
        "- **底线**：**截断亏损，让利润奔跑**——「赚一点就跑、亏了死扛」比追涨杀跌更致命；复盘须对照。\n\n",
        "### 四、仓位与情绪周期绑定（优先级高于「个案胜率」）\n\n",
        f"- **总仓约束（随阶段）**：{pos_cap}。\n",
        "- **满仓/重仓前提（补充）**：① 须**主线龙头**、主升期**分歧低吸**为主，而非后排跟风；② **非**退潮期（无系统性情绪杀）；③ 即使重仓，也宜 **2～3 只**分散，避免单票黑天鹅。\n",
        "- **止损纪律（程序建议）**：单票浮亏超过 **5%** 减仓一半；超过 **8%** 止损离场；**禁止**摊平补仓。\n\n",
        "### 五、心法闭环：预判 → 试错 → 确认 → 加仓\n\n",
        "1. **预判**：结合上表阶段与主线，列出可能龙头与方向（须与程序龙头池可交叉验证）。\n"
        "2. **试错**：**10%～20%** 试探，观察承接与板块是否认可。\n"
        "3. **确认**：主线发酵、龙头走强再加至 **50%～70%**（与阶段上限一致）。\n"
        "4. **加仓**：仅在**确认信号**后出现；**禁止**下跌摊平。\n\n"
        "**卖出触发（参考）**：龙头放量炸板、承接转弱；主线退潮、跟风大跌；达到止盈或亏钱效应确立。\n\n"
        "**信念**：可支撑执行纪律；**若市场证伪主线**（龙头走弱、梯队崩），须认错，勿用「信念」对抗盘面。\n\n",
        "### 六、每日三省（收盘后自评，可逐项打勾）\n\n",
        "- [ ] 情绪数据是否按上表「四组锚」核对（非主观感受）。\n",
        f"- [ ] 当前阶段是否判定为 **{market_phase}** / **{cycle_name}**，信号是否自洽。\n",
        "- [ ] 主线与龙头承接、是否具备切换风险。\n",
        "- [ ] 今日操作是否遵守计划与止损；盈亏原因是否可复盘。\n",
        "- [ ] 明日：方向、**仓位上限**、加仓/止损条件、不及预期应对是否写明。\n\n",
        f"> 交易日 `{ds}`；交易日序列用于连板/晋级等见程序后续块。\n\n",
        "---\n\n",
    ]
    return "".join(lines)


def should_emit_six_pillar() -> bool:
    try:
        from app.utils.config import ConfigManager

        return bool(ConfigManager().get("enable_replay_six_pillar_framework", True))
    except Exception:
        return True
