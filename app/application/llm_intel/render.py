# -*- coding: utf-8 -*-
"""将审计结果与结构化决策渲染为 Markdown（插入复盘文末）。"""

from __future__ import annotations

from typing import Any, Optional

from app.application.llm_intel.audit import AuditResult
from app.application.llm_intel.reference_facts import ReferenceFacts


def render_intel_block(
    ref: ReferenceFacts,
    audit: AuditResult,
    decision: Optional[dict[str, Any]],
) -> str:
    lines: list[str] = [
        "---",
        "",
        "## 【程序智能校验与决策摘要】",
        "",
        "> 本块由**程序量化对照**与（可选）**结构化决策模型**生成，用于抑制幻觉、提示风险；"
        "**不构成投资建议**，买卖请自担风险。",
        "",
        "### 1. 与程序数据一致性（规则校验）",
    ]
    if not audit.fact_checks:
        lines.append("- 未抽取到可与 KPI 对齐的关键数字，或 KPI 缺失；请以下文程序数据块为准。")
    else:
        lines.append("| 项目 | 程序口径 | 文中识别数字 | 结果 |")
        lines.append("|------|----------|--------------|------|")
        for fc in audit.fact_checks:
            prog = "" if fc.program_value is None else str(fc.program_value)
            claimed = ",".join(str(x) for x in fc.claimed_values) if fc.claimed_values else "—"
            st = {"ok": "✓", "mismatch": "⚠", "unknown": "?"}.get(fc.status, fc.status)
            lines.append(f"| {fc.field} | {prog} | {claimed} | {st} |")
            if fc.note:
                lines.append(f"> {fc.note}")

    lines.extend(
        [
            "",
            f"- **幻觉风险评分（启发式）**: `{audit.hallucination_score}`（0 佳，1 差）",
            "",
            "### 2. 异常检测",
        ]
    )
    if audit.anomalies:
        for a in audit.anomalies:
            lines.append(f"- ⚠ {a}")
    else:
        lines.append("- 未发现与程序 KPI 明显冲突的数量级表述（仍可能有定性夸大）。")

    lines.extend(["", "### 3. 风险提示"])
    if audit.risk_hints:
        for r in audit.risk_hints:
            lines.append(f"- {r}")
    else:
        lines.append("- （无额外规则风险提示）")

    lines.extend(["", "### 4. 模型决策参与（结构化输出，非指令）"])
    if isinstance(decision, dict) and decision:
        stance = decision.get("stance", "—")
        conf = decision.get("confidence", "—")
        align = decision.get("program_alignment", "—")
        hallu = decision.get("hallucination_risk", "—")
        basis = decision.get("decision_basis", "—")
        lines.append(f"- **立场倾向**: `{stance}`（defensive=偏防守 / neutral=中性 / aggressive=偏激进）")
        lines.append(f"- **置信度**: `{conf}`（模型自评，非胜率）")
        lines.append(f"- **与程序对齐**: `{align}`")
        lines.append(f"- **幻觉风险（模型自评）**: `{hallu}`")
        lines.append(f"- **依据**: {basis}")
        risks = decision.get("key_risks") or []
        if isinstance(risks, list) and risks:
            lines.append("- **关注风险**:")
            for x in risks[:8]:
                lines.append(f"  - {x}")
        watch = decision.get("watch_next") or []
        if isinstance(watch, list) and watch:
            lines.append("- **次日观察**:")
            for x in watch[:8]:
                lines.append(f"  - {x}")
    else:
        lines.append("- 本次未生成结构化决策 JSON（可检查 API 或关闭 `llm_intel.structured_decision_llm`）。")

    lines.append("")
    lines.append(f"*程序参照快照键: `trade_date={ref.trade_date}`*")
    return "\n".join(lines)
