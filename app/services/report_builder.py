# -*- coding: utf-8 -*-
"""
复盘报告结构化拼装：在模型漏写固定章节时，用程序数据生成补充块。
"""
from __future__ import annotations

import json
from typing import Any, Optional


SECTION_CORE_PLAN = "core_stocks_and_plan"


def _has_heading(text: str, needle: str) -> bool:
    if not text:
        return False
    return needle in text


def missing_core_stocks_and_plan(text: str) -> tuple[bool, bool]:
    """是否缺少「五、核心股聚焦」或「七、明日预案」标题行。"""
    t = text or ""
    has_core = _has_heading(t, "### 五、核心股聚焦") or _has_heading(t, "## 五、核心股聚焦")
    has_plan = _has_heading(t, "### 七、明日预案") or _has_heading(t, "## 七、明日预案")
    return (not has_core, not has_plan)


def _insert_before_disclaimer(text: str, block: str) -> str:
    marker = "### 免责声明"
    if marker in text:
        parts = text.split(marker, 1)
        return parts[0].rstrip() + "\n\n" + block.strip() + "\n\n" + marker + parts[1]
    return text.rstrip() + "\n\n" + block.strip() + "\n"


def _markdown_section_five_rules(actual_date: str, data_fetcher: Any) -> str:
    """### 五、核心股聚焦（程序补充）"""
    phase = str(getattr(data_fetcher, "_last_market_phase", "") or "—")
    pos = str(getattr(data_fetcher, "_last_position_suggestion", "") or "—")
    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    top_pool = ah.get("top_pool") or []
    main_sectors = ah.get("main_sectors") or []
    dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
    top_dragon = dm.get("top_dragon") if isinstance(dm, dict) else None
    if not isinstance(top_dragon, dict):
        top_dragon = {}

    lines: list[str] = [
        "### 五、核心股聚焦（程序补充）",
        "",
        "> 由程序根据当日涨停池、龙头池与市场阶段生成，**与上文 AI 互补**；非投资建议。",
        "",
        f"- **程序判定市场阶段**：{phase}",
        f"- **建议仓位区间（程序口径）**：{pos}",
    ]
    if main_sectors:
        lines.append(
            f"- **主线/板块关注**：{'、'.join(str(x) for x in main_sectors[:6])}",
        )
    if top_dragon.get("name"):
        lines.append(
            f"- **总龙头（当日涨停池最高连板）**：{top_dragon.get('name')}（`{top_dragon.get('code', '')}`）"
            f" **{int(top_dragon.get('lb') or 0)} 连板**"
            + (
                f"，行业：{top_dragon.get('industry', '—')}"
                if top_dragon.get("industry")
                else ""
            ),
        )
    elif top_pool:
        lines.append(
            "- **总龙头**：程序龙头池首条为当日综合分领先标的（详见下表），请以涨停池「最高连板」为准交叉验证。",
        )

    lines.extend(["", "**程序龙头池（观察列表，按综合分序）**", ""])
    if top_pool:
        lines.append("| 代码 | 名称 | 标签 | 连板 | 板块 | 综合分 |")
        lines.append("|------|------|------|------|------|--------|")
        for p in top_pool[:12]:
            if not isinstance(p, dict):
                continue
            lines.append(
                f"| `{p.get('code', '')}` | {p.get('name', '—')} | {p.get('tag', '—')} | "
                f"{int(p.get('lb') or 0) if p.get('lb') is not None else '—'} | "
                f"{p.get('sector', '—')} | {p.get('score', '—')} |"
            )
    else:
        lines.append("（程序未完成选股或龙头池为空，仅保留阶段与仓位参考。）")

    df_zt = getattr(data_fetcher, "_last_zt_pool", None)
    if df_zt is not None and not getattr(df_zt, "empty", True) and "lb" in df_zt.columns:
        try:
            mx = int(df_zt["lb"].max())
            lines.append("")
            lines.append(f"- **当日涨停池最高连板高度**：**{mx}** 板（来自行情涨停池统计）。")
        except Exception:
            pass
    return "\n".join(lines)


def _markdown_section_seven_rules(actual_date: str, data_fetcher: Any) -> str:
    """### 七、明日预案（程序补充）"""
    phase = str(getattr(data_fetcher, "_last_market_phase", "") or "—")
    return "\n".join(
        [
            "### 七、明日预案（三种剧本 + 可执行信号）（程序补充）",
            "",
            "**超预期**：若主线龙头 **竞价高开并放量**，且同梯队无批量核按钮，可沿程序阶段与仓位区间 **试错观察**（非指令买入）。",
            "**符合预期**：若 **震荡分化**，优先处理持仓节奏，新仓以龙头池 **分时转强** 为观察信号。",
            "**不及预期**：若 **核心票低开低走** 或 **中位股批量跌停**，则 **降杠杆/空仓观望**，等待情绪修复。",
            "",
            "**可执行信号（观察向，非买卖价）**：",
            f"- 与程序阶段 **{phase}** 对齐：仓位不超过上文建议区间。",
            "- 集合竞价：观察龙头池标的 **高开幅度、量比** 是否匹配剧本。",
            "- 盘中：同题材 **助攻家数** 是否维持；炸板率若快速升高则 **收缩风险暴露**。",
            "",
            f"*生成时间：交易日 {actual_date} · report_builder 规则引擎*",
        ]
    )


def _build_core_stocks_and_plan_rules(
    actual_date: str,
    data_fetcher: Any,
) -> str:
    """五 + 七 完整块（规则）。"""
    return "\n\n".join(
        [
            _markdown_section_five_rules(actual_date, data_fetcher),
            _markdown_section_seven_rules(actual_date, data_fetcher),
        ]
    )


def _build_core_stocks_and_plan_llm(
    api_key: str,
    actual_date: str,
    data_fetcher: Any,
    *,
    max_tokens: int = 2048,
) -> str:
    """可选：用 DeepSeek 将程序事实改写为与模板一致的「五 + 七」正文。"""
    from app.services.llm_client import get_llm_client

    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
    facts = {
        "date": actual_date,
        "market_phase": getattr(data_fetcher, "_last_market_phase", ""),
        "position_suggestion": getattr(data_fetcher, "_last_position_suggestion", ""),
        "top_pool": ah.get("top_pool")[:16] if ah.get("top_pool") else [],
        "main_sectors": ah.get("main_sectors") or [],
        "top_dragon": dm.get("top_dragon"),
    }
    payload = json.dumps(facts, ensure_ascii=False)[:12000]
    prompt = (
        "你是 A 股短线复盘助手。下列为程序提供的**事实 JSON**（须采信，勿编造代码与数字）。\n"
        "**总龙头**须与 JSON 中 `top_dragon`（名称、代码、连板数）一致；若缺失，则写「以涨停池最高连板为准」勿臆造个股名。\n"
        "请严格输出两段 Markdown，标题必须完全一致：\n"
        "### 五、核心股聚焦（程序补充）\n"
        "（2～5 个短段落：总龙头、板块龙、程序龙头池要点；禁止买卖价与荐股指令。）\n\n"
        "### 七、明日预案（三种剧本 + 可执行信号）（程序补充）\n"
        "（必须包含小标题 **超预期** / **符合预期** / **不及预期**，"
        "以及 **可执行信号** 列表句，每条为可观察条件，非具体价位。）\n\n"
        "---\n【程序事实】\n"
        f"{payload}\n"
    )
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.32, max_tokens=max_tokens)
    head = (out or "")[:200]
    if "API请求失败" in head or "调用大模型 API" in head:
        return _build_core_stocks_and_plan_rules(actual_date, data_fetcher)
    return (out or "").strip()


def build_sections(
    section: str,
    *,
    actual_date: str,
    data_fetcher: Any,
    api_key: str = "",
    use_llm: bool = False,
) -> str:
    """
    生成固定章节块。当前支持：
    - section=\"core_stocks_and_plan\"：核心股聚焦 + 明日预案（规则或可选 LLM）。
    """
    if section != SECTION_CORE_PLAN:
        return ""
    if use_llm and (api_key or "").strip():
        return _build_core_stocks_and_plan_llm(
            api_key.strip(), actual_date, data_fetcher
        )
    return _build_core_stocks_and_plan_rules(actual_date, data_fetcher)


def append_core_stocks_and_plan_if_missing(
    text: str,
    *,
    actual_date: str,
    data_fetcher: Any,
    api_key: str = "",
    enable: bool = True,
    use_llm: bool = False,
) -> str:
    """
    若主文缺少「五、核心股聚焦」或「七、明日预案」，则插入程序补充（插在免责声明之前）。
    仅缺其中一节时只补该节，避免重复。
    """
    if not enable or not text or not str(text).strip():
        return text
    miss_core, miss_plan = missing_core_stocks_and_plan(text)
    if not miss_core and not miss_plan:
        return text
    # 仅缺一节时用规则只补该节；两节皆缺且开启 LLM 时用一次生成
    if (
        use_llm
        and (api_key or "").strip()
        and miss_core
        and miss_plan
    ):
        block = build_sections(
            SECTION_CORE_PLAN,
            actual_date=actual_date,
            data_fetcher=data_fetcher,
            api_key=api_key,
            use_llm=True,
        )
    else:
        chunks: list[str] = []
        if miss_core:
            chunks.append(_markdown_section_five_rules(actual_date, data_fetcher))
        if miss_plan:
            chunks.append(_markdown_section_seven_rules(actual_date, data_fetcher))
        block = "\n\n".join(chunks)
    if not block.strip():
        return text
    return _insert_before_disclaimer(text, block)
