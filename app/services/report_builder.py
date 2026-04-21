# -*- coding: utf-8 -*-
"""复盘报告结构化拼装：统一四区域模板并补齐关键字段。"""
from __future__ import annotations

import json
import re
from typing import Any


SECTION_CORE_PLAN = "core_stocks_and_plan"
SECTION_FOUR_BLOCKS = "four_blocks"

def _has_heading(text: str, needle: str) -> bool:
    if not text:
        return False
    return needle in text


def _has_four_blocks(text: str) -> bool:
    t = text or ""
    required = (
        "## 数据快照",
        "## 情绪与周期",
        "## 主线与备选",
        "## 附录/心法",
    )
    return all(_has_heading(t, h) for h in required)


def missing_core_stocks_and_plan(text: str) -> tuple[bool, bool]:
    """兼容旧接口：返回(缺核心块, 缺计划块)。"""
    ok = _has_four_blocks(text)
    return (not ok, not ok)


def _insert_before_disclaimer(text: str, block: str) -> str:
    marker = "### 免责声明"
    if marker in text:
        parts = text.split(marker, 1)
        return parts[0].rstrip() + "\n\n" + block.strip() + "\n\n" + marker + parts[1]
    return text.rstrip() + "\n\n" + block.strip() + "\n"


def _pick_first(source: dict[str, Any], keys: tuple[str, ...], default: Any = "—") -> Any:
    for k in keys:
        v = source.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return default


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, "", "—"):
            return None
        return float(value)
    except Exception:
        return None


def _fmt_pct(value: Any) -> str:
    fv = _to_float(value)
    return "—" if fv is None else f"{fv:.1f}%"


def _fmt_amt(value: Any) -> str:
    fv = _to_float(value)
    return "—" if fv is None else f"{fv:.1f}"


def _normalize_action(tag: str) -> str:
    valid = {"✅ 可操作", "⚠️ 观望", "❌ 放弃", "🛑 强制空仓"}
    return tag if tag in valid else "⚠️ 观望"


def _build_sector_strength_table(
    main_sectors: list[Any],
    top_pool: list[Any],
    market_env: dict[str, Any],
    data_fetcher: Any,
) -> list[str]:
    turnover_total = _to_float(market_env.get("turnover_yi")) or _to_float(
        (getattr(data_fetcher, "_last_email_kpi", None) or {}).get("turnover_yi_est")
    )
    rows: dict[str, dict[str, Any]] = {}
    for s in main_sectors[:6]:
        sec = str(s).strip()
        if sec:
            rows[sec] = {"name": sec, "zt": 0, "amt": None, "rps": None, "caps": 0}
    for p in top_pool:
        if not isinstance(p, dict):
            continue
        sec = str(p.get("sector") or "").strip()
        if not sec:
            continue
        row = rows.setdefault(sec, {"name": sec, "zt": 0, "amt": None, "rps": None, "caps": 0})
        row["zt"] += 1
        amt = _to_float(_pick_first(p, ("amount_yi", "turnover_yi", "amount"), None))
        if amt is not None and amt > 1e6:
            amt = amt / 1e8
        if amt is not None:
            row["amt"] = (row["amt"] or 0.0) + amt
            if amt >= 5.0:
                row["caps"] += 1
        rps = _to_float(_pick_first(p, ("rps20", "sector_rps20", "rps_20d"), None))
        if rps is not None:
            row["rps"] = max(float(row["rps"] or 0.0), rps)

    df_sector = getattr(data_fetcher, "_last_sector_rank_df", None)
    if df_sector is not None and not getattr(df_sector, "empty", True):
        try:
            for _, r in df_sector.iterrows():
                sec = str(r.get("sector") or "").strip()
                if not sec:
                    continue
                row = rows.setdefault(sec, {"name": sec, "zt": 0, "amt": None, "rps": None, "caps": 0})
                if row["amt"] is None:
                    mv = _to_float(r.get("money"))
                    if mv is not None:
                        row["amt"] = mv
                rv = _to_float(_pick_first(r, ("rps20", "RPS20", "rps"), None))
                if rv is not None:
                    row["rps"] = rv
        except Exception:
            pass

    lines = [
        "**主线板块评估（多维评分）**",
        "",
        "| 板块名称 | 涨停家数 | 板块成交额(亿) | 占全市场成交额比 | 板块RPS(20日) | 中军容量票(>=5亿) | 综合强度评分(1-5) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in list(rows.values())[:8]:
        zt = int(row.get("zt") or 0)
        amt = _to_float(row.get("amt"))
        share = (amt / turnover_total * 100.0) if (amt is not None and turnover_total and turnover_total > 0) else None
        rps = _to_float(row.get("rps"))
        caps = int(row.get("caps") or 0)
        hit_zt = zt >= 5
        hit_share = share is not None and share >= 3.0
        hit_rps = rps is not None and rps >= 80.0
        if hit_zt and hit_share and hit_rps:
            score = 5 if (zt >= 8 and (share or 0) >= 5.0 and (rps or 0) >= 90.0) else 4
        else:
            score = 1 + int(hit_zt) + int(hit_share) + int(hit_rps)
        lines.append(
            f"| {row['name']} | {zt} | {'无数据' if amt is None else f'{amt:.1f}'} | "
            f"{'无数据' if share is None else f'{share:.1f}%'} | "
            f"{'无数据' if rps is None else f'{rps:.1f}'} | {caps} | {score} |"
        )
    if len(lines) == 4:
        lines.append("| 无数据 | 0 | 无数据 | 无数据 | 无数据 | 0 | 1 |")
    return lines


def _detect_stage_92kebi(
    *,
    max_lb: int,
    premium_pct: float | None,
    zhaban_rate_pct: float | None,
    dt_count: int | None,
    mid_fall_limit: bool,
    has_new_theme_first_board: bool,
) -> tuple[str, str]:
    p = premium_pct
    zb = zhaban_rate_pct
    dt = int(dt_count or 0)
    # 主升期：连板高度≥5 + 昨日涨停溢价>3% + 炸板率<25%
    if max_lb >= 5 and (p is not None and p > 3.0) and (zb is not None and zb < 25.0):
        return "主升", "策略建议：聚焦龙头与核心中军，顺势做强。"
    # 高位震荡：连板高度≥4但≤5 + 炸板率25%-35% + 中位股出现跌停
    if 4 <= max_lb <= 5 and (zb is not None and 25.0 <= zb <= 35.0) and mid_fall_limit:
        return "高位震荡", "策略建议：轻仓试错，冲高兑现，弱转强再参与。"
    # 主跌期：连板高度≤3 + 跌停家数>15 + 昨日涨停溢价<0%
    if max_lb <= 3 and dt > 15 and (p is not None and p < 0.0):
        return "主跌", "策略建议：以防守为主，优先空仓或仅做低风险反抽。"
    # 低位震荡（试错）：连板高度≤3 + 炸板率>35% + 出现新题材首板
    if max_lb <= 3 and (zb is not None and zb > 35.0) and has_new_theme_first_board:
        return "试错", "策略建议：小仓位试错新题材首板，严格止损。"
    return "高位震荡", "策略建议：控制仓位，等待确定性信号再加仓。"


def _build_four_blocks_rules(actual_date: str, data_fetcher: Any) -> str:
    phase = str(getattr(data_fetcher, "_last_market_phase", "") or "—")
    pos = str(getattr(data_fetcher, "_last_position_suggestion", "") or "—")
    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
    kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
    top_pool = ah.get("top_pool") or []
    main_sectors = ah.get("main_sectors") or []
    facts = {}
    if isinstance(dm, dict):
        facts.update(dm)
    if isinstance(kpi, dict):
        facts.update(kpi)
    if isinstance(ah, dict):
        facts.update(ah)

    sh20 = _pick_first(facts, ("sh_above_ma20", "sse_above_ma20", "sh_on_20ma"), "—")
    cy20 = _pick_first(facts, ("cyb_above_ma20", "gem_above_ma20", "cy_on_20ma"), "—")
    turnover = _fmt_amt(_pick_first(facts, ("total_turnover", "market_turnover"), None))
    turnover_chg = _fmt_pct(
        _pick_first(facts, ("turnover_change_pct", "turnover_qoq_pct"), None)
    )
    yday_premium = _fmt_pct(
        _pick_first(
            facts,
            ("yesterday_limitup_avg_premium_pct", "zt_prev_avg_premium_pct"),
            None,
        )
    )
    zhaban_drawdown = _fmt_pct(
        _pick_first(
            facts,
            ("zhaban_avg_drawdown_pct", "broken_limit_avg_drawdown_pct"),
            None,
        )
    )
    ab_kill = _pick_first(facts, ("ab_kill_flag", "limitdown_contains_yday_zt"), "—")
    zt_count = _pick_first(facts, ("zt_count", "limit_up_count"), "—")
    dt_count = _pick_first(facts, ("dt_count", "limit_down_count"), "—")
    zhaban_rate = _fmt_pct(_pick_first(facts, ("zhaban_rate_pct", "broken_limit_rate_pct"), None))
    zhaban_rate_v = _to_float(_pick_first(facts, ("zhaban_rate_pct", "broken_limit_rate_pct"), None))
    premium_v = _to_float(
        _pick_first(
            facts,
            ("yesterday_limitup_avg_premium_pct", "zt_prev_avg_premium_pct", "premium"),
            None,
        )
    )
    action = "🛑 强制空仓" if "空仓" in pos else "⚠️ 观望"
    if isinstance(ab_kill, bool) and (not ab_kill):
        action = "✅ 可操作"
    action = _normalize_action(action)
    df_zt = getattr(data_fetcher, "_last_zt_pool", None)
    max_lb = 0
    if df_zt is not None and not getattr(df_zt, "empty", True) and "lb" in getattr(df_zt, "columns", []):
        try:
            max_lb = int(df_zt["lb"].max())
        except Exception:
            max_lb = 0
    has_new_theme_first_board = False
    try:
        tags = [str((x or {}).get("tag", "")) for x in top_pool if isinstance(x, dict)]
        lbs = [int((x or {}).get("lb", 0) or 0) for x in top_pool if isinstance(x, dict)]
        has_new_theme_first_board = any(lb == 1 for lb in lbs) or any("首板" in t for t in tags)
    except Exception:
        has_new_theme_first_board = False
    # 暂以跌停家数 >= 1 作为“中位股出现跌停”的程序近似口径
    mid_fall_limit = int(_to_float(dt_count) or 0) >= 1
    stage_92, stage_advice = _detect_stage_92kebi(
        max_lb=max_lb,
        premium_pct=premium_v,
        zhaban_rate_pct=zhaban_rate_v,
        dt_count=int(_to_float(dt_count) or 0),
        mid_fall_limit=mid_fall_limit,
        has_new_theme_first_board=has_new_theme_first_board,
    )

    lines = [
        "## 数据快照",
        "---",
        "| 指标 | 数据 | 结论 |",
        "|---|---|---|",
        f"| 涨停/跌停 | {zt_count}/{dt_count} | {action} |",
        f"| 炸板率/仓位 | {zhaban_rate}/{pos} | {action} |",
        "",
        "## 情绪与周期",
        "---",
        f"- 连板梯队与阶段：{phase}（{action}）",
        f"- 当前阶段 = [{stage_92}]，{stage_advice}",
        f"- 昨日涨停溢价：{yday_premium}（{action}）",
        f"- 炸板平均回撤：{zhaban_drawdown}（⚠️ 观望）",
        f"- 跌停是否含昨日涨停(A/B杀)：{ab_kill}（❌ 放弃）",
        "",
        "## 主线与备选",
        "---",
        f"- 大盘20日线：上证={sh20}，创业板={cy20}（{action}）",
        f"- 全市场成交额：{turnover}（环比 {turnover_chg}）",
        f"- 中军池：{'、'.join(str(x) for x in main_sectors[:3]) if main_sectors else '—'}",
        "",
    ]
    market_env = getattr(data_fetcher, "_last_market_env_snapshot", None) or {}
    lines.extend(_build_sector_strength_table(main_sectors, top_pool, market_env, data_fetcher))
    lines.extend(
        [
            "",
            "| 代码 | 名称 | 板块涨停数 | 结论 |",
            "|---|---|---|---|",
        ]
    )
    if top_pool:
        for p in top_pool[:8]:
            if not isinstance(p, dict):
                continue
            sec_zt = _to_float(
                _pick_first(
                    p,
                    (
                        "sector_limit_up_count",
                        "sector_zt_count",
                        "sector_up_limit_count",
                    ),
                    None,
                )
            )
            sec_zt_txt = "—" if sec_zt is None else f"{sec_zt:.1f}"
            pick = "✅ 可操作" if (sec_zt is not None and sec_zt >= 3.0) else "⚠️ 观望"
            lines.append(
                f"| `{p.get('code','')}` | {p.get('name','—')} | {sec_zt_txt} | {pick} |"
            )
    else:
        lines.append("| — | — | — | ❌ 放弃 |")

    lines.extend(
        [
            "",
            "**明日计划**",
            "- ✅ 可操作：仅做同板块涨停家数 >=3 且触发量化条件的候选。",
            "- ✅ 触发条件A：开盘后15分钟内，分时价格始终位于均价线上方，且任意一分钟收盘价不低于开盘价的-2%。",
            "- ✅ 触发条件B：前5分钟成交额 >= 昨日同期（9:30-9:35）成交额的1.5倍。",
            "- ✅ 触发条件C：价格突破过去5日最高价，且成交量大于过去5日均量的1.3倍。",
            "- ⚠️ 观望：高位震荡或炸板回撤扩大的板块。",
            "- ❌ 放弃：跌停扩散并出现 A/B 杀链条。",
            "- 若以下条件任一不满足，则当日开仓 0%",
            "  1) 上证与创业板至少一者站上20日线；",
            "  2) 全市场成交额环比不为显著缩量；",
            "  3) 候选股所在板块当日涨停家数 >=3。",
            "",
            "## 附录/心法",
            "---",
            f"- 当日情绪：{phase}，先处理风险再谈进攻。",
            "- 高位震荡看承接，主跌阶段先保命。",
            f"*生成时间：交易日 {actual_date} · report_builder 规则引擎*",
        ]
    )
    return "\n".join(lines)


def _build_core_stocks_and_plan_rules(
    actual_date: str,
    data_fetcher: Any,
) -> str:
    """兼容旧接口：返回新四区域模板。"""
    return _build_four_blocks_rules(actual_date, data_fetcher)


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
        "你是 A 股短线复盘助手。下列为程序提供的**事实 JSON**（须采信，勿编造）。\n"
        "请严格输出四个 Markdown 区域，标题必须完全一致：\n"
        "## 数据快照\n## 情绪与周期\n## 主线与备选\n## 附录/心法\n"
        "结论标签仅允许：✅ 可操作 / ⚠️ 观望 / ❌ 放弃 / 🛑 强制空仓。\n"
        "百分比统一一位小数。\n\n"
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
    """若主文缺少四区域模板，则在免责声明前插入程序补充。"""
    if not enable or not text or not str(text).strip():
        return text
    if _has_four_blocks(text):
        return text
    if use_llm and (api_key or "").strip():
        block = build_sections(
            SECTION_CORE_PLAN,
            actual_date=actual_date,
            data_fetcher=data_fetcher,
            api_key=api_key,
            use_llm=True,
        )
    else:
        block = _build_four_blocks_rules(actual_date, data_fetcher)
    if not block.strip():
        return text
    return _insert_before_disclaimer(text, block)


def _normalize_status_tags(text: str) -> tuple[str, int]:
    out = text
    replaced = 0
    mapping = (
        (r"结论[:：]\s*可交易", "结论：✅ 可操作"),
        (r"结论[:：]\s*回避", "结论：🛑 强制空仓"),
        (r"结论[:：]\s*观望", "结论：⚠️ 观望"),
        (r"\b符合买点\b", "✅ 可操作"),
        (r"\b等待\b", "⚠️ 观望"),
    )
    for pat, rep in mapping:
        out, n = re.subn(pat, rep, out)
        replaced += int(n)
    return out, replaced


def _normalize_trigger_conditions(text: str) -> tuple[str, int]:
    out = text
    replaced = 0
    mapping = (
        (
            r"分时重心上移",
            "开盘后15分钟内，分时价格始终位于均价线上方，且任意一分钟收盘价不低于开盘价的-2%",
        ),
        (
            r"放量确认|放量",
            "前5分钟成交额 >= 昨日同期（9:30-9:35）成交额的1.5倍",
        ),
        (
            r"快速突破近期平台|突破小平台|突破平台",
            "价格突破过去5日最高价，且成交量大于过去5日均量的1.3倍",
        ),
    )
    for pat, rep in mapping:
        out, n = re.subn(pat, rep, out)
        replaced += int(n)
    return out, replaced


def _table_to_list(lines: list[str]) -> list[str]:
    if len(lines) < 3:
        return lines
    headers = [x.strip() for x in lines[0].strip().strip("|").split("|")]
    body = [ln for ln in lines[2:] if ln.strip().startswith("|")]
    result: list[str] = ["- 表格已自动转列表（行宽超过 80 字符）"]
    for row in body:
        cells = [x.strip() for x in row.strip().strip("|").split("|")]
        kv = []
        for i, h in enumerate(headers):
            if i < len(cells) and h:
                kv.append(f"{h}={cells[i]}")
        if kv:
            result.append(f"- {'；'.join(kv)}")
    return result if len(result) > 1 else lines


def _compress_wide_tables(text: str, width_limit: int = 80) -> tuple[str, int]:
    lines = (text or "").splitlines()
    out: list[str] = []
    converted = 0
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            block: list[str] = []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                block.append(lines[j])
                j += 1
            if any(len(x) > width_limit for x in block):
                out.extend(_table_to_list(block))
                converted += 1
            else:
                out.extend(block)
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), converted


def _append_position_conflict_table(text: str) -> tuple[str, int]:
    s = text or ""
    has_full = "满仓（100%）" in s or "开仓 100%" in s
    has_range = re.search(r"\b\d{1,3}(?:\.\d+)?\s*-\s*\d{1,3}(?:\.\d+)?\s*%", s) is not None
    if not (has_full and has_range):
        return s, 0
    if "仓位口径冲突说明" in s:
        return s, 0
    note = "\n\n| 仓位来源 | 建议 | 执行优先级 |\n|---|---|---|\n| 程序仓位 | 区间建议 | 低 |\n| 明日计划 | 满仓（100%） | 高 |\n"
    return s.rstrip() + note + ("\n" if s.endswith("\n") else ""), 1


def _trim_appendix_lines(text: str, max_lines: int = 10) -> tuple[str, int]:
    lines = (text or "").splitlines()
    try:
        i = next(idx for idx, v in enumerate(lines) if v.strip() == "## 附录/心法")
    except StopIteration:
        return text, 0
    j = i + 1
    while j < len(lines) and not lines[j].startswith("## "):
        j += 1
    block = lines[i:j]
    if len(block) <= max_lines:
        return text, 0
    keep = block[:max_lines]
    if not any("当日情绪" in x for x in keep):
        keep[-1] = "- 当日情绪关联：以风险优先。"
    merged = lines[:i] + keep + lines[j:]
    return "\n".join(merged), max(0, len(block) - len(keep))


def _market_env_block_and_missing(data_fetcher: Any) -> tuple[str, bool]:
    kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
    snap = getattr(data_fetcher, "_last_market_env_snapshot", None) or {}
    if isinstance(kpi, dict) and isinstance(kpi.get("market_env_snapshot"), dict):
        merged = dict(kpi.get("market_env_snapshot") or {})
        merged.update(snap)
        snap = merged
    sh_point = snap.get("sh_point")
    sh_pct = snap.get("sh_pct")
    sh_pos = snap.get("sh_ma20_position")
    sh_dir = snap.get("sh_ma20_direction")
    ty = snap.get("turnover_yi")
    tchg = snap.get("turnover_change_pct")
    gt8k = snap.get("turnover_gt_8000")
    up_n = snap.get("up_count")
    down_n = snap.get("down_count")
    ratio = snap.get("rise_fall_ratio")
    yli = snap.get("yest_limitup_index_pct")
    yli2 = snap.get("yest_limitup_gt_2pct")
    missing = bool(snap.get("has_missing"))

    def _fmtf(v: Any, nd: int = 1, suffix: str = "") -> str:
        fv = _to_float(v)
        return "—" if fv is None else f"{fv:.{nd}f}{suffix}"

    block = "\n".join(
        [
            "### 程序侧行情接口快照（系统性风险评估）",
            "",
            f"- 上证指数：{_fmtf(sh_point, 2)} 点，{_fmtf(sh_pct, 1, '%')}，20日线位置={sh_pos or '—'}，20日线方向={sh_dir or '—'}",
            f"- 全市场成交额：{_fmtf(ty, 1)} 亿，较前日变化={_fmtf(tchg, 1, '%')}，是否大于8000亿={'是' if gt8k is True else ('否' if gt8k is False else '—')}",
            f"- 涨跌家数比：{up_n if up_n is not None else '—'}/{down_n if down_n is not None else '—'}（比值={_fmtf(ratio, 2)}）",
            f"- 昨日涨停指数：当日涨幅={_fmtf(yli, 1, '%')}，是否高于2%={'是' if yli2 is True else ('否' if yli2 is False else '—')}",
            "",
            "---",
            "",
        ]
    )
    return block, missing


def _inject_market_env_before_section(text: str, block: str) -> tuple[str, int]:
    s = text or ""
    if not s.strip():
        return s, 0
    if "### 程序侧行情接口快照（系统性风险评估）" in s:
        return s, 0
    markers = (
        "### 一、大盘与主线环境评估",
        "## 一、大盘与主线环境评估",
        "## 数据快照",
        "### 数据快照",
    )
    for m in markers:
        if m in s:
            parts = s.split(m, 1)
            return parts[0].rstrip() + "\n\n" + block + m + parts[1], 1
    return block + s, 1


def _mark_summary_if_missing(text: str, has_missing: bool) -> tuple[str, int]:
    if not has_missing:
        return text, 0
    s = text or ""
    flag = "数据缺失，系统性风险评估不完整"
    lines = s.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("【摘要】"):
            if flag in line:
                return s, 0
            lines[i] = line.rstrip() + f"｜{flag}"
            return "\n".join(lines), 1
    return s, 0


def _build_execution_review_block(data_fetcher: Any) -> str:
    ah = getattr(data_fetcher, "_last_auction_meta", None) or {}
    pool = ah.get("top_pool") or []

    def _stock_line(idx: int) -> str:
        if idx < len(pool) and isinstance(pool[idx], dict):
            p = pool[idx]
            label = f"{p.get('code', '—')} {p.get('name', '—')}".strip()
        else:
            label = "[代码+名称]"
        return "\n".join(
            [
                f"- 昨日计划标的{idx + 1}：{label}",
                "  - 触发条件是否满足：否",
                "  - 若触发，实际买入价：[价格]",
                "  - 今日收盘价：[价格]",
                "  - 盈亏状态：[盈利/亏损/持平]",
                "  - 若未触发，原因分析：[板块不及预期/个股走弱/情绪退潮/其他]",
            ]
        )

    return "\n".join(
        [
            "## 昨日计划执行评价",
            _stock_line(0),
            _stock_line(1),
            "- 昨日整体执行率：[已触发计划数/总计划数]",
            "- 复盘总结：[一句话反思]",
            "",
        ]
    )


def enforce_execution_review_block(text: str, data_fetcher: Any) -> tuple[str, dict[str, int]]:
    """在“五、持仓标的的应对预案”前强制插入昨日计划执行评价。"""
    stats = {"execution_review_inserted": 0}
    s = text or ""
    if not s.strip():
        return s, stats
    if "## 昨日计划执行评价" in s:
        return s, stats
    block = _build_execution_review_block(data_fetcher)
    markers = (
        "### 五、持仓标的的应对预案",
        "## 五、持仓标的的应对预案",
    )
    for m in markers:
        if m in s:
            parts = s.split(m, 1)
            stats["execution_review_inserted"] = 1
            return parts[0].rstrip() + "\n\n" + block + "\n" + m + parts[1], stats
    # 若不存在「五」节，则回退在“明日计划”后补充
    fallback = "## 明日计划"
    if fallback in s:
        parts = s.split(fallback, 1)
        stats["execution_review_inserted"] = 1
        return parts[0] + fallback + parts[1] + "\n\n" + block, stats
    stats["execution_review_inserted"] = 1
    return s.rstrip() + "\n\n" + block, stats


def _clean_abnormal_chars(text: str) -> tuple[str, int]:
    # 保留：中英文、数字、常见中英文标点、空白与 Markdown 必要符号
    pat = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9\s\u3000，。！？；：、（）【】《》“”‘’·—…,.!?;:()\[\]{}<>+\-*/=_%#|`~\"']")
    out, n = re.subn(pat, "", text or "")
    return out, int(n)


def _normalize_percent_spacing(text: str) -> tuple[str, int]:
    out, n = re.subn(r"(\d(?:\.\d+)?)\s+%", r"\1%", text or "")
    return out, int(n)


def _dedupe_headings(text: str) -> tuple[str, int]:
    lines = (text or "").splitlines()
    out: list[str] = []
    last_heading = ""
    removed = 0
    for ln in lines:
        s = ln.strip()
        if s.startswith("#"):
            if s == last_heading:
                removed += 1
                continue
            last_heading = s
        elif s:
            last_heading = ""
        out.append(ln)
    return "\n".join(out), removed


def _normalize_title_date(text: str, actual_date: str) -> tuple[str, int]:
    if not actual_date or len(str(actual_date)) != 8:
        return text, 0
    out, n = re.subn(r"(交易日)\s*[0-9]{4}[-/年]?[0-9]{2}[-/月]?[0-9]{2}日?", rf"\1 {actual_date}", text or "")
    return out, int(n)


def _normalize_markdown_tables(text: str) -> tuple[str, int]:
    lines = (text or "").splitlines()
    out: list[str] = []
    i = 0
    changed = 0
    while i < len(lines):
        if "|" not in lines[i]:
            out.append(lines[i])
            i += 1
            continue
        j = i
        block = []
        while j < len(lines) and "|" in lines[j]:
            block.append(lines[j].replace("｜", "|"))
            j += 1
        if len(block) >= 2 and "---" in block[1]:
            rows = []
            for b in block:
                cells = [c.strip() for c in b.strip().strip("|").split("|")]
                rows.append(cells)
            cols = max(len(r) for r in rows)
            widths = [3] * cols
            for r in rows:
                for k in range(cols):
                    v = r[k] if k < len(r) else ""
                    widths[k] = max(widths[k], len(v))
            norm = []
            for idx, r in enumerate(rows):
                vals = [(r[k] if k < len(r) else "").ljust(widths[k]) for k in range(cols)]
                if idx == 1:
                    vals = ["-" * widths[k] for k in range(cols)]
                norm.append("| " + " | ".join(vals) + " |")
            out.extend(norm)
            changed += 1
        else:
            out.extend(block)
        i = j
    return "\n".join(out), changed


def enforce_final_report_cleanup(text: str, actual_date: str) -> tuple[str, dict[str, int]]:
    stats = {
        "abnormal_chars_removed": 0,
        "tables_normalized": 0,
        "percent_spacing_fixed": 0,
        "duplicate_headings_removed": 0,
        "title_date_normalized": 0,
    }
    s = text or ""
    s, stats["abnormal_chars_removed"] = _clean_abnormal_chars(s)
    s, stats["tables_normalized"] = _normalize_markdown_tables(s)
    s, stats["percent_spacing_fixed"] = _normalize_percent_spacing(s)
    s, stats["duplicate_headings_removed"] = _dedupe_headings(s)
    s, stats["title_date_normalized"] = _normalize_title_date(s, str(actual_date))
    return s, stats


def sanitize_replay_report_output_with_stats(text: str) -> tuple[str, dict[str, int]]:
    """最终输出校验器（含统计）：标签、仓位冲突、表格宽度、附录长度。"""
    s = text or ""
    stats = {
        "status_replacements": 0,
        "trigger_replacements": 0,
        "position_conflicts": 0,
        "wide_tables_converted": 0,
        "appendix_lines_trimmed": 0,
        "market_env_block_inserted": 0,
        "summary_missing_marked": 0,
    }
    if not s.strip():
        return s, stats
    s, stats["status_replacements"] = _normalize_status_tags(s)
    s, stats["trigger_replacements"] = _normalize_trigger_conditions(s)
    s, stats["position_conflicts"] = _append_position_conflict_table(s)
    s, stats["wide_tables_converted"] = _compress_wide_tables(s, width_limit=80)
    s, stats["appendix_lines_trimmed"] = _trim_appendix_lines(s, max_lines=10)
    return s, stats


def sanitize_replay_report_output(text: str) -> str:
    """最终输出校验器：标签、仓位冲突、表格宽度、附录长度。"""
    out, _ = sanitize_replay_report_output_with_stats(text)
    return out


def enforce_market_env_block(text: str, data_fetcher: Any) -> tuple[str, dict[str, int]]:
    """强制插入“程序侧行情接口快照”，并在数据缺失时标记摘要。"""
    stats = {
        "market_env_block_inserted": 0,
        "summary_missing_marked": 0,
    }
    block, missing = _market_env_block_and_missing(data_fetcher)
    s, stats["market_env_block_inserted"] = _inject_market_env_before_section(text, block)
    s, stats["summary_missing_marked"] = _mark_summary_if_missing(s, missing)
    return s, stats
