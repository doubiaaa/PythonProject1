# -*- coding: utf-8 -*-
"""
复盘 DeepSeek 增强：在程序事实已锁定的前提下，追加一致性核对、多空对照、龙头观察、异常提示。
周报：追加「周度节奏与变化叙事」（仅基于当周 Markdown）。
"""
from __future__ import annotations

import json
from typing import Any, Optional


def collect_program_facts_snapshot(
    actual_date: str,
    market_data: str,
    data_fetcher: Any,
    separation_result: Optional[dict[str, Any]],
) -> str:
    """汇总程序侧可核对事实，供增强块与主文对照（不替代行情拉取）。"""
    parts: list[str] = [f"交易日: {actual_date}"]
    phase = getattr(data_fetcher, "_last_market_phase", None)
    if phase:
        parts.append(f"程序判定市场阶段: {phase}")
    dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
    if dm:
        try:
            parts.append(
                "【程序结构化快照·JSON】\n"
                + json.dumps(dm, ensure_ascii=False)[:12000]
            )
        except (TypeError, ValueError):
            pass
    kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
    if kpi:
        try:
            parts.append(
                "【邮件KPI】\n" + json.dumps(kpi, ensure_ascii=False)[:4000]
            )
        except (TypeError, ValueError):
            pass
    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    tp = ah.get("top_pool") or []
    if tp:
        compact: list[dict[str, Any]] = []
        for row in tp[:28]:
            if isinstance(row, dict):
                compact.append(
                    {
                        "code": row.get("code") or row.get("symbol"),
                        "name": row.get("name"),
                        "tag": row.get("tag") or row.get("bucket"),
                        "lb": row.get("lb") or row.get("limit_up_days"),
                    }
                )
        parts.append(
            "【程序龙头池摘要】\n" + json.dumps(compact, ensure_ascii=False)
        )
    if separation_result:
        try:
            parts.append(
                "【分离确认摘要】\n"
                + json.dumps(separation_result, ensure_ascii=False)[:8000]
            )
        except (TypeError, ValueError):
            pass
    md_excerpt = (market_data or "")[:14000]
    parts.append("【市场数据正文摘录】\n" + md_excerpt)
    return "\n\n".join(parts)


def build_enhancement_prompt(
    actual_date: str,
    program_facts: str,
    main_report: str,
) -> str:
    mr = (main_report or "")[:28000]
    pf = (program_facts or "")[:32000]
    return (
        "你是 A 股短线复盘助手。下列【程序侧事实与数据】由本系统从行情与规则计算得到，必须视为权威；"
        "【主回复盘长文】由模型生成，可能存在笔误或与事实不一致之处。\n\n"
        "请严格基于【程序侧事实】对【主回复盘长文】做增强分析，用 Markdown 输出，必须包含四级标题：\n"
        "### 1. 一致性核对\n"
        "逐条列出：长文中与程序事实明显矛盾或无法从程序数据中推出的表述（若无则写「未发现明显矛盾」）。\n\n"
        "### 2. 多空对照（观察向）\n"
        "各用 3～6 句，基于同一程序事实，分别写「偏乐观解读」「偏谨慎解读」「中性整理」。"
        "禁止给出具体买卖价与指令。\n\n"
        "### 3. 龙头池观察清单\n"
        "针对程序龙头池中的标的，列出 3～8 条观察要点（次日看盘时关注什么信号），非荐股。\n\n"
        "### 4. 异常与待验证点\n"
        "列出 2～5 条值得次日复核的数据或逻辑点（如与常识偏离、需交叉验证的推断）。\n\n"
        f"交易日：{actual_date}\n\n"
        "---\n【程序侧事实与数据】\n"
        f"{pf}\n\n---\n【主回复盘长文】\n{mr}\n"
    )


def run_replay_deepseek_enhancements(
    api_key: str,
    actual_date: str,
    program_facts: str,
    main_report: str,
    *,
    max_tokens: int = 4096,
) -> str:
    from app.services.llm_client import get_llm_client

    prompt = build_enhancement_prompt(actual_date, program_facts, main_report)
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.25, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return (
            "\n\n---\n\n## DeepSeek 增强块（生成失败）\n\n"
            + (out or "")[:2000]
        )
    return "\n\n---\n\n## DeepSeek 增强块\n\n" + (out or "").strip()


def run_weekly_trend_narrative(
    api_key: str,
    weekly_md: str,
    *,
    max_tokens: int = 3072,
) -> str:
    """周报全文基础上追加「节奏与变化」叙事（仅基于当周 Markdown 中的程序统计）。"""
    from app.services.llm_client import get_llm_client

    body = (weekly_md or "")[:24000]
    prompt = (
        "你是 A 股周度复盘助手。下列【本周周报 Markdown】由程序统计生成，文中数字与表格为权威。\n"
        "请只输出一段 Markdown，顶级标题为「### 周度节奏与变化叙事」，"
        "用 8～15 句概括：本周情绪与结构相对「常规周」的偏强/偏弱/混乱点、与龙头池标签相关的归因提示（统计向、非荐股）。"
        "不要重复粘贴表格中的数字。\n\n"
        "---\n【本周周报】\n"
        + body
    )
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.3, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return "\n\n（周度叙事生成失败：" + (out or "")[:500] + "）\n"
    return "\n\n" + (out or "").strip() + "\n"
