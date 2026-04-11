# -*- coding: utf-8 -*-
"""确定性文本审计：从正文中抽取与 KPI 可能冲突的数字与表述。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.application.llm_intel.reference_facts import ReferenceFacts


@dataclass
class FactCheck:
    field: str
    program_value: Optional[Any]
    claimed_values: list[Any]
    status: str  # "ok" | "mismatch" | "unknown"
    note: str = ""


@dataclass
class AuditResult:
    fact_checks: list[FactCheck] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    risk_hints: list[str] = field(default_factory=list)
    hallucination_score: float = 0.0  # 0 好 — 1 差
    claimed_numbers_summary: dict[str, list[int]] = field(default_factory=dict)


_ZT_PATTERNS = [
    re.compile(r"涨停[：:\s]*(\d{1,5})\s*家"),
    re.compile(r"(\d{1,5})\s*家\s*涨停"),
    re.compile(r"涨停\s*(\d{1,5})"),
    re.compile(r"共\s*(\d{1,5})\s*家\s*涨停"),
    re.compile(r"涨停\D{0,16}(\d{1,5})\s*家"),
]
_DT_PATTERNS = [
    re.compile(r"跌停[：:\s]*(\d{1,5})\s*家"),
    re.compile(r"(\d{1,5})\s*家\s*跌停"),
    re.compile(r"跌停\s*(\d{1,5})"),
]
_ZB_PATTERNS = [
    re.compile(r"炸板[：:\s]*(\d{1,5})\s*家"),
    re.compile(r"(\d{1,5})\s*家\s*炸板"),
]
_PREMIUM_PATTERNS = [
    re.compile(r"溢价[率]?[：:\s]*[+-]?(\d+\.?\d*)\s*%"),
    re.compile(r"昨日涨停溢价[：:\s]*[+-]?(\d+\.?\d*)\s*%"),
]
_ZHABAN_PATTERNS = [
    re.compile(r"炸板率[：:\s]*(\d+\.?\d*)\s*%"),
    re.compile(r"炸板率[：:\s]*(\d+\.?\d*)"),
]


def _ints_from_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[int]:
    out: list[int] = []
    for p in patterns:
        for m in p.finditer(text):
            try:
                out.append(int(m.group(1)))
            except (ValueError, IndexError):
                continue
    return list(dict.fromkeys(out))


def _floats_from_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[float]:
    out: list[float] = []
    for p in patterns:
        for m in p.finditer(text):
            try:
                out.append(float(m.group(1)))
            except (ValueError, IndexError):
                continue
    return list(dict.fromkeys(out))


def _score_mismatch(
    program_v: Optional[int],
    claimed: list[int],
    *,
    tol: int = 0,
) -> tuple[str, str]:
    if program_v is None or not claimed:
        return "unknown", ""
    for c in claimed:
        if abs(c - program_v) <= tol:
            return "ok", ""
    worst = min(claimed, key=lambda x: abs(x - program_v))
    return "mismatch", f"文中出现 {claimed}，与程序值 {program_v} 不一致（最近 {worst}）"


def run_deterministic_audit(text: str, ref: ReferenceFacts) -> AuditResult:
    """对复盘正文做规则审计（不调用 LLM）。"""
    t = text or ""
    checks: list[FactCheck] = []
    anomalies: list[str] = []
    risks: list[str] = []

    zt_claimed = _ints_from_patterns(t, _ZT_PATTERNS)
    dt_claimed = _ints_from_patterns(t, _DT_PATTERNS)
    zb_claimed = _ints_from_patterns(t, _ZB_PATTERNS)
    prem_claimed = _floats_from_patterns(t, _PREMIUM_PATTERNS)
    zhaban_claimed = _floats_from_patterns(t, _ZHABAN_PATTERNS)

    claimed_summary: dict[str, list[int]] = {}
    if zt_claimed:
        claimed_summary["zt_mentions"] = zt_claimed
    if dt_claimed:
        claimed_summary["dt_mentions"] = dt_claimed

    # 涨停家数
    if ref.zt_count is not None and zt_claimed:
        st, note = _score_mismatch(ref.zt_count, zt_claimed, tol=0)
        checks.append(
            FactCheck(
                "zt_count",
                ref.zt_count,
                list(zt_claimed),
                st,
                note,
            )
        )
        if st == "mismatch":
            anomalies.append(
                f"涨停家数表述疑与程序不一致：程序 KPI 为 {ref.zt_count}，"
                f"正文相关数字 {zt_claimed}。"
            )
            risks.append("核心数量级与程序快照冲突时，应以程序数据与交易所原始披露为准。")

    # 跌停
    if ref.dt_count is not None and dt_claimed:
        st, note = _score_mismatch(ref.dt_count, dt_claimed, tol=0)
        checks.append(
            FactCheck("dt_count", ref.dt_count, list(dt_claimed), st, note)
        )
        if st == "mismatch":
            anomalies.append(
                f"跌停家数表述疑与程序不一致：程序 KPI 为 {ref.dt_count}，正文相关数字 {dt_claimed}。"
            )

    # 炸板家数（若有）
    if ref.zb_count is not None and zb_claimed:
        st, note = _score_mismatch(ref.zb_count, zb_claimed, tol=1)
        checks.append(
            FactCheck("zb_count", ref.zb_count, list(zb_claimed), st, note)
        )
        if st == "mismatch":
            anomalies.append(
                f"炸板家数表述疑与程序不一致：程序为 {ref.zb_count}，正文相关数字 {zb_claimed}。"
            )

    # 溢价 %（允许 0.3 绝对误差）
    if ref.premium_pct is not None and prem_claimed:
        pv = float(ref.premium_pct)
        ok_any = any(abs(pv - c) <= 0.3 for c in prem_claimed)
        st = "ok" if ok_any else "mismatch"
        checks.append(
            FactCheck(
                "premium_pct",
                round(pv, 4),
                [round(x, 4) for x in prem_claimed],
                st,
                "" if ok_any else f"程序溢价 {pv:.2f}% 与文中 {prem_claimed} 不一致",
            )
        )
        if st == "mismatch":
            anomalies.append(
                f"溢价数值与程序 KPI（{pv:.2f}%）存在偏差，正文提及 {prem_claimed}。"
            )
            risks.append("溢价对接力情绪极敏感，请核对程序 KPI 与行情源时间切片。")

    # 炸板率：程序为 0~1 小数；正文常为百分比
    if ref.zhaban_rate is not None and zhaban_claimed:
        pv = float(ref.zhaban_rate)
        pv_pct = pv * 100.0 if pv <= 1.0 else pv
        ok_any = False
        for c in zhaban_claimed:
            c2 = c if c > 1.0 else c * 100.0
            if abs(pv_pct - c) <= 1.0 or abs(pv_pct - c2) <= 1.0:
                ok_any = True
                break
        st = "ok" if ok_any else "mismatch"
        checks.append(
            FactCheck(
                "zhaban_rate",
                round(pv, 4),
                [round(x, 4) for x in zhaban_claimed],
                st,
                "",
            )
        )
        if st == "mismatch":
            anomalies.append(
                f"炸板率表述与程序 KPI 可能不一致：程序约 {pv_pct:.2f}%，文中 {zhaban_claimed}%。"
            )

    # 幻觉风险打分：按失败条数
    mismatch_n = sum(1 for c in checks if c.status == "mismatch")
    denom = max(len([c for c in checks if c.status != "unknown"]), 1)
    hallu = min(1.0, mismatch_n / float(denom) * 0.9 + (0.1 if anomalies else 0))

    if not checks and (ref.raw_kpi or ref.market_phase):
        risks.append("正文未解析到与 KPI 对齐的关键数字，模型可能偏定性；请以程序量化块为准。")

    return AuditResult(
        fact_checks=checks,
        anomalies=anomalies,
        risk_hints=risks,
        hallucination_score=round(hallu, 4),
        claimed_numbers_summary=claimed_summary,
    )
