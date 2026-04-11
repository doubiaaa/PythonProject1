# -*- coding: utf-8 -*-
"""智能分析流水线：事实校验 + 异常 + 风险 + 可选结构化决策 LLM。"""

from __future__ import annotations

from typing import Any, Optional

from app.application.llm_intel.audit import AuditResult, run_deterministic_audit
from app.application.llm_intel.decision_llm import call_structured_decision
from app.application.llm_intel.reference_facts import ReferenceFacts
from app.application.llm_intel.render import render_intel_block
from app.application.replay_text_rules import is_llm_failure_payload
from app.services.replay_llm_enhancements import collect_program_facts_snapshot
from app.utils.config import ConfigManager


def run_replay_intel_layer(
    *,
    report_md: str,
    actual_date: str,
    market_data: str,
    data_fetcher: Any,
    separation_result: Optional[dict[str, Any]],
    api_key: str,
) -> tuple[str, dict[str, Any]]:
    """
    在复盘正文后追加「程序智能校验与决策摘要」块。

    返回 (追加后的正文, 调试信息字典)。
    """
    cm = ConfigManager()
    li = cm.config.get("llm_intel") or {}
    if not isinstance(li, dict):
        li = {}
    if li.get("enabled") is False:
        return report_md, {"skipped": True, "reason": "disabled"}

    if is_llm_failure_payload(report_md):
        return report_md, {"skipped": True, "reason": "llm_failure_payload"}

    ref = ReferenceFacts.from_data_fetcher(data_fetcher, actual_date)
    if bool(li.get("deterministic_audit", True)):
        audit = run_deterministic_audit(report_md, ref)
    else:
        audit = AuditResult()

    pf_text = collect_program_facts_snapshot(
        actual_date,
        market_data,
        data_fetcher,
        separation_result,
    )
    program_json = ref.as_compact_dict()

    decision: Optional[dict[str, Any]] = None
    if bool(li.get("structured_decision_llm", True)) and (api_key or "").strip():
        try:
            decision = call_structured_decision(
                api_key,
                program_facts_json=program_json,
                report_excerpt=report_md[:12000],
                program_facts_text=pf_text,
                max_tokens=int(li.get("decision_max_tokens", 600) or 600),
                temperature=float(li.get("decision_temperature", 0.15) or 0.15),
            )
        except Exception:
            decision = None

    block = render_intel_block(ref, audit, decision)
    meta = {
        "hallucination_score": audit.hallucination_score,
        "fact_checks": len(audit.fact_checks),
        "anomalies": len(audit.anomalies),
        "has_decision": decision is not None,
    }
    return report_md.rstrip() + "\n\n" + block, meta
