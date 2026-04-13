# -*- coding: utf-8 -*-
"""
复盘 DeepSeek 增强：一致性核对、多空对照、程序异常假设验证、主线叙事、龙头逐票观察、
独立章节质控（周期/明日量表）、近5日变化叙事、要闻事件链与噪声相关度。
周报：周度叙事、权重变动白话解释。
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional


def build_program_anomaly_hints(data_fetcher: Any) -> str:
    """从 KPI/快照生成「程序侧异常标签」提示，供模型写假设原因与验证点。"""
    lines: list[str] = []
    kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
    zh = kpi.get("zhaban_rate")
    if zh is not None:
        try:
            zf = float(zh)
        except (TypeError, ValueError):
            zf = None
        if zf is not None and zf == zf:
            if 0 < zf < 1:
                zf *= 100.0
            if zf >= 35.0:
                lines.append(
                    f"- **高炸板率**：程序口径炸板率 **{zf:.1f}%**"
                    "（偏高，情绪分歧或封板质量差）。"
                )
    pr = kpi.get("premium")
    if pr is not None:
        if float(pr) < 0:
            lines.append(f"- **负溢价环境**：昨日涨停溢价 **{float(pr):.2f}%**（接力意愿弱）。")
        elif float(pr) >= 3:
            lines.append(f"- **强溢价环境**：昨日涨停溢价 **{float(pr):.2f}%**（接力偏强）。")
    zt = kpi.get("zt_count")
    dt = kpi.get("dt_count")
    if zt is not None and dt is not None and int(zt) > 0:
        r = int(dt) / max(int(zt), 1)
        if r >= 0.25:
            lines.append(f"- **跌停家数相对偏高**：涨停 {int(zt)} / 跌停 {int(dt)}，亏钱效应扩散风险。")
    dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
    if isinstance(dm, dict) and dm.get("sector_empty"):
        lines.append("- **板块数据缺失或为空**：行业/概念排名结论置信度受限。")
    if not lines:
        lines.append("- （程序 KPI 未触发显式异常标签；仍请结合正文与 KPI 复核。）")
    return "\n".join(lines)


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
    parts.append("【程序异常标签提示】\n" + build_program_anomaly_hints(data_fetcher))
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
                        "sector": row.get("sector"),
                        "lb": row.get("lb"),
                        "pct": row.get("pct"),
                        "turn": row.get("turn"),
                        "score": row.get("score"),
                        "tech_score": row.get("tech_score"),
                    }
                )
        parts.append(
            "【程序龙头池·字段摘要】\n" + json.dumps(compact, ensure_ascii=False)
        )
    if separation_result:
        try:
            parts.append(
                "【分离确认摘要】\n"
                + json.dumps(separation_result, ensure_ascii=False)[:8000]
            )
        except (TypeError, ValueError):
            pass
    md_excerpt = (market_data or "")[:16000]
    parts.append("【市场数据正文摘录】\n" + md_excerpt)
    return "\n\n".join(parts)


def build_enhancement_prompt(
    actual_date: str,
    program_facts: str,
    main_report: str,
) -> str:
    mr = (main_report or "")[:26000]
    pf = (program_facts or "")[:34000]
    return (
        "你是 A 股短线复盘助手。下列【程序侧事实与数据】由本系统从行情与规则计算得到，必须视为权威；"
        "【主回复盘长文】由模型生成，可能存在笔误或与事实不一致之处。\n\n"
        "请严格基于【程序侧事实】对【主回复盘长文】做增强分析，用 Markdown 输出，必须包含以下四级标题（顺序不可打乱）：\n"
        "### 1. 一致性核对\n"
        "逐条列出：长文中与程序事实明显矛盾或无法从程序数据中推出的表述（若无则写「未发现明显矛盾」）。\n\n"
        "### 2. 多空对照（观察向）\n"
        "各用 3～6 句，基于同一程序事实，分别写「偏乐观解读」「偏谨慎解读」「中性整理」。"
        "禁止给出具体买卖价与指令。\n\n"
        "### 3. 程序异常与假设验证\n"
        "依据【程序异常标签提示】与 KPI：对每条已列异常（若无则选 1～2 个当日最值得警惕的数据点），"
        "用表格输出三列：**异常或数据点**｜**可能原因假设（非定论）**｜**次日可验证点**（可观察行情/盘口/公告）。至少 2 行。\n\n"
        "### 4. 主线与题材结构（投研向）\n"
        "结合程序行业/概念资金与涨停分布，判断当日更接近：**单主线** / **多题材并进** / **混沌**，"
        "并写 4～8 句依据（统计向、非荐股）。\n\n"
        "### 5. 龙头池逐票观察清单\n"
        "对【程序龙头池·字段摘要】中**每一只**标的用一行表格或列表行，至少包含："
        "代码、名称、连板/标签、换手或涨幅（若程序提供）、**次日观察信号**（仅观察项，禁止买卖价与指令）。"
        "若池内多于 8 只，可只写综合分最高的前 8 只并注明「其余从略」。\n\n"
        "### 6. 其他待验证点\n"
        "补充 1～3 条与上文不重复、值得次日复核的逻辑或数据点。\n\n"
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
    max_tokens: int = 6144,
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


def run_replay_chapter_quality(
    api_key: str,
    actual_date: str,
    program_facts: str,
    main_report: str,
    *,
    max_tokens: int = 3072,
) -> str:
    """独立调用：对「周期定性」「明日预案」做量表打分与缺口分析（与主文对表）。"""
    from app.services.llm_client import get_llm_client

    mr = (main_report or "")[:20000]
    pf = (program_facts or "")[:12000]
    prompt = (
        "你是 A 股复盘质检员。仅依据【程序侧事实】与【主文摘录】，"
        "不要编造行情。\n\n"
        "请输出 Markdown，顶级标题为「### 章节质控·周期与明日（独立评分）」，包含：\n"
        "1）**周期定性**：对照程序 §1.2 市场阶段与主文「三、周期定性」，给主文该节 **1～5 分**（5=与程序完全一致且依据充分），"
        "写 **缺口分析**（缺了哪些数据引用、与程序分歧点）。\n"
        "2）**明日预案**：对照主文「七、明日预案」与程序龙头池/阶段，给 **1～5 分**（5=可执行信号具体且与程序不矛盾），"
        "写 **缺口分析**。\n"
        "全文不超过 800 字；禁止买卖指令与具体价位。\n\n"
        f"交易日：{actual_date}\n---\n【程序侧事实】\n{pf}\n---\n【主文摘录】\n{mr}\n"
    )
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.2, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return "\n\n---\n\n## 章节质控（生成失败）\n\n" + (out or "")[:1500]
    return "\n\n---\n\n" + (out or "").strip() + "\n"


def run_replay_comparison_narrative(
    api_key: str,
    actual_date: str,
    market_data_excerpt: str,
    *,
    max_tokens: int = 2048,
) -> str:
    """相对昨日与近 5 交易日的「变化叙事」：哪些线在变、主线是否切换。"""
    from app.services.llm_client import get_llm_client

    body = (market_data_excerpt or "")[:18000]
    prompt = (
        "你是 A 股短线助手。下列为当日市场数据摘录（含近5交易日对照、指数与情绪 KPI 等），数字以正文为准。\n"
        "请只输出一段 Markdown，顶级标题为「### 相对昨日与近5日的变化叙事」，"
        "用 8～14 句说明：**哪些指标或结构相对前几日明显变化**、**主线题材是否切换或加强**、"
        "**与程序给出的市场阶段是否叙事一致**（若摘录不足请写「数据不足」）。"
        "禁止买卖指令与具体价位；不要重复粘贴整表。\n\n"
        f"交易日：{actual_date}\n---\n【市场数据摘录】\n{body}\n"
    )
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.28, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return "\n\n---\n\n## 变化叙事（生成失败）\n\n" + (out or "")[:1200]
    return "\n\n---\n\n" + (out or "").strip() + "\n"


def run_replay_news_event_chain(
    api_key: str,
    actual_date: str,
    data_fetcher: Any,
    *,
    max_items_push: int = 3,
    max_tokens: int = 3072,
) -> str:
    """要闻：事件—板块—情绪链；对未进推送的宏观条目写一句相关度。"""
    from app.services.llm_client import get_llm_client

    rel = getattr(data_fetcher, "_last_finance_news_related", None) or []
    gen = getattr(data_fetcher, "_last_finance_news_general", None) or []
    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    tp = ah.get("top_pool") or []
    pool_compact = [
        {"code": p.get("code"), "name": p.get("name"), "tag": p.get("tag")}
        for p in tp[:12]
        if isinstance(p, dict)
    ]
    rel_s = json.dumps(rel, ensure_ascii=False)[:8000]
    gen_s = json.dumps(gen, ensure_ascii=False)[:8000]
    pool_s = json.dumps(pool_compact, ensure_ascii=False)[:2000]
    prompt = (
        "你是财经与市场联动分析师。以下为当日要闻（关联池/主线）（related）与宏观摘录（general），"
        "以及程序龙头池摘要。\n\n"
        "请用 Markdown 输出，包含两级标题：\n"
        "## 要闻事件链（事件—板块—情绪）\n"
        "择要 **2～4 条** 要闻，每条用一行写清：**事件要点 → 可能影响板块 → 对短线情绪（强/弱/混沌）的含义**；"
        "优先写与龙头池或 related 命中相关的条目。\n\n"
        "## 噪声与弱相关说明\n"
        f"假设邮件推送仅展示前 {max_items_push} 条关联要闻摘要：对其余 **general** 或未被推送覆盖的条目，"
        "**每条用一句话**说明其与**当日盘面结构**（涨跌停家数、溢价、主线）相关性强、弱或无关及理由；"
        "若 general 为空则写「无补充条目」。\n\n"
        "禁止荐股与买卖指令。\n\n"
        f"交易日：{actual_date}\n---\n【related】\n{rel_s}\n---\n【general】\n{gen_s}\n---\n【龙头池】\n{pool_s}\n"
    )
    if not rel and not gen:
        return ""
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.25, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return "\n\n---\n\n## 要闻深化（生成失败）\n\n" + (out or "")[:1500]
    return "\n\n---\n\n## 要闻深化（事件链与相关度）\n\n" + (out or "").strip() + "\n"


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
        "用 10～18 句概括，且**必须显式包含**以下对比（若文中缺上周数据则如实写「未提供上周对照」）：\n"
        "1）**本周 vs 上周**：风格占优（打板/低吸/趋势等）、**涨停溢价环境**、**连板高度** 三方面，哪些是「变」、哪些是「不变」；\n"
        "2）本周情绪与结构相对常规周的偏强/偏弱/混乱；\n"
        "3）与龙头池标签相关的归因提示（统计向、非荐股）。\n"
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


def run_weekly_weight_explanation(
    api_key: str,
    *,
    previous_weights: dict[str, float],
    merged_weights: dict[str, float],
    suggested: dict[str, float],
    counts: dict[str, int],
    iso_year: int,
    iso_week: int,
    anchor: str,
    max_tokens: int = 2048,
) -> str:
    """五桶权重更新后的白话解释：数据为何推/拉各桶。"""
    from app.services.llm_client import get_llm_client

    buckets = ("打板", "低吸", "趋势", "龙头", "其他")
    rows = []
    for b in buckets:
        o = float(previous_weights.get(b, 0) or 0)
        m = float(merged_weights.get(b, 0) or 0)
        s = float(suggested.get(b, 0) or 0)
        c = int(counts.get(b, 0) or 0)
        rows.append(f"- {b}: 上周前={o:.2%} → 合并后={m:.2%}；数据建议≈{s:.2%}；本周可结算样本={c}")
    text = "\n".join(rows)
    prompt = (
        "你是量化策略说明员。下列为**程序**根据龙头池区间收益算出的五桶权重变化与样本数。\n"
        "请用 Markdown 输出，顶级标题为「### 五桶权重变动说明（白话）」，"
        "用 6～12 句解释：**哪些风格的收益/样本在把权重往上推或往下拉**，"
        "为何合并结果与「数据建议」可能不完全一致（平滑、上下限、多周衰减等，可概括）。"
        "禁止荐股与预测个股。\n\n"
        f"锚点周：{iso_year}-W{iso_week:02d}，锚点日 {anchor}\n\n{text}\n"
    )
    client = get_llm_client(api_key)
    out = client.chat_completion(prompt, temperature=0.25, max_tokens=max_tokens)
    head = (out or "")[:160]
    if "API请求失败" in head or "调用大模型 API" in head:
        return "\n\n（权重变动说明生成失败：" + (out or "")[:400] + "）\n"
    return "\n\n" + (out or "").strip() + "\n"


def run_replay_enhancement_bundle(
    *,
    parallel: bool,
    max_workers: int,
    gap_en: float,
    gap_x: float,
    actual_date: str,
    market_data: str,
    data_fetcher: Any,
    separation_result: Optional[dict[str, Any]],
    api_key: str,
    result: str,
    main_report_for_qc: str,
    _en_main: bool,
    _en_qc: bool,
    _en_cmp: bool,
    _en_news: bool,
    mt: int,
    mi: int,
    log: Callable[[str], None],
) -> str:
    """
    四类复盘增强块：按 extra → qc → cmp → news 顺序拼接。

    parallel=False 时与历史逐段串行 + 段间 sleep 行为一致。
    parallel=True 时在 gap_en 与 collect_program_facts_snapshot 之后并发调用 LLM，
    再按固定顺序拼接；**不**插入段间 sleep，可能增加 429 风险，需自行权衡。
    """
    if _en_main and gap_en > 0:
        log(
            f"DeepSeek 增强块前等待 {gap_en:.0f}s（降低连发限速）"
        )
        time.sleep(gap_en)
    pf = collect_program_facts_snapshot(
        actual_date,
        market_data,
        data_fetcher,
        separation_result,
    )

    if not parallel:
        suffix = ""
        if _en_main:
            extra = run_replay_deepseek_enhancements(
                api_key,
                actual_date,
                pf,
                result,
                max_tokens=mt,
            )
            suffix += extra
            log("DeepSeek 增强块已附加")
        gap_x_val = float(gap_x or 0)
        if _en_qc:
            if gap_x_val > 0:
                time.sleep(gap_x_val)
            suffix += run_replay_chapter_quality(
                api_key,
                actual_date,
                pf,
                main_report_for_qc,
            )
            log("章节质控（周期/明日）已附加")
        if _en_cmp:
            if gap_x_val > 0:
                time.sleep(gap_x_val)
            suffix += run_replay_comparison_narrative(
                api_key,
                actual_date,
                market_data,
            )
            log("近5日变化叙事已附加")
        if _en_news:
            rel_n = getattr(data_fetcher, "_last_finance_news_related", None) or []
            gen_n = getattr(data_fetcher, "_last_finance_news_general", None) or []
            if rel_n or gen_n:
                if gap_x_val > 0:
                    time.sleep(gap_x_val)
                suffix += run_replay_news_event_chain(
                    api_key,
                    actual_date,
                    data_fetcher,
                    max_items_push=mi,
                )
                log("要闻深化（事件链）已附加")
        return suffix

    workers = max(1, min(int(max_workers), 4))

    def _main() -> str:
        if not _en_main:
            return ""
        return run_replay_deepseek_enhancements(
            api_key,
            actual_date,
            pf,
            result,
            max_tokens=mt,
        )

    def _qc() -> str:
        if not _en_qc:
            return ""
        return run_replay_chapter_quality(
            api_key,
            actual_date,
            pf,
            main_report_for_qc,
        )

    def _cmp() -> str:
        if not _en_cmp:
            return ""
        return run_replay_comparison_narrative(
            api_key,
            actual_date,
            market_data,
        )

    def _news() -> str:
        if not _en_news:
            return ""
        rel_n = getattr(data_fetcher, "_last_finance_news_related", None) or []
        gen_n = getattr(data_fetcher, "_last_finance_news_general", None) or []
        if not rel_n and not gen_n:
            return ""
        return run_replay_news_event_chain(
            api_key,
            actual_date,
            data_fetcher,
            max_items_push=mi,
        )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        f_main = ex.submit(_main) if _en_main else None
        f_qc = ex.submit(_qc) if _en_qc else None
        f_cmp = ex.submit(_cmp) if _en_cmp else None
        f_news = ex.submit(_news) if _en_news else None
        extra = f_main.result() if f_main else ""
        qc = f_qc.result() if f_qc else ""
        cmp_t = f_cmp.result() if f_cmp else ""
        news = f_news.result() if f_news else ""

    if _en_main:
        log("DeepSeek 增强块已附加")
    if _en_qc:
        log("章节质控（周期/明日）已附加")
    if _en_cmp:
        log("近5日变化叙事已附加")
    if _en_news:
        rel_n2 = getattr(data_fetcher, "_last_finance_news_related", None) or []
        gen_n2 = getattr(data_fetcher, "_last_finance_news_general", None) or []
        if rel_n2 or gen_n2:
            log("要闻深化（事件链）已附加")

    return extra + qc + cmp_t + news
