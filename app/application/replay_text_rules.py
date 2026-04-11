# -*- coding: utf-8 -*-
"""
应用服务层：复盘报告正文相关的规则；阈值与文案由统一配置驱动。

由编排层调用；单元测试直接导入本模块。
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.config import ConfigManager


def _cfg() -> ConfigManager:
    return ConfigManager()


def _templates() -> dict[str, Any]:
    t = _cfg().get("replay_text_templates")
    return t if isinstance(t, dict) else {}


def _failure_markers() -> tuple[str, ...]:
    raw = _cfg().get("llm_failure_markers")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw if isinstance(x, str) and x.strip())
    return tuple()


def _dragon_headings() -> tuple[str, ...]:
    raw = _cfg().get("dragon_report_headings")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw if isinstance(x, str) and x.strip())
    return tuple()


def is_llm_failure_payload(text: str) -> bool:
    """返回内容实为 API 错误串（无模型正文），避免误报「缺章节」。"""
    cm = _cfg()
    n = int(cm.get("llm_failure_payload_scan_chars", 1200))
    s = (text or "").strip()[: max(1, n)]
    markers = _failure_markers()
    if not markers:
        return False
    return any(m in s for m in markers)


def ensure_dragon_report_sections(text: str) -> str:
    """若缺少龙头模板关键章节标题，在文末追加系统提示（不重试 API）。"""
    if not text or not str(text).strip():
        return text
    tpl = _templates()
    headings = _dragon_headings()
    if is_llm_failure_payload(text):
        note = str(tpl.get("dragon_llm_failure_note") or "")
        return text.rstrip() + note
    if not headings:
        return text
    missing = [h for h in headings if h not in text]
    if not missing:
        return text
    intro = str(tpl.get("dragon_missing_headings_intro") or "")
    sep = str(tpl.get("dragon_missing_headings_sep") or "、")
    end = str(tpl.get("dragon_missing_headings_end") or "。\n")
    note = intro + sep.join(missing) + end
    return text.rstrip() + note


def extract_summary_line(text: str) -> Optional[str]:
    """解析报告首行【摘要】…，用于推送标题。"""
    if not text:
        return None
    max_chars = int(_cfg().get("replay_summary_line_max_chars", 220))
    for line in text.strip().split("\n"):
        s = line.strip()
        if s.startswith("【摘要】"):
            return s[: max(1, max_chars)]
    return None


def ensure_summary_line(text: str, market_phase: str = "高位震荡期") -> str:
    """模型未输出规范【摘要】首行时补一行，便于推送解析与阅读。"""
    if not text or not str(text).strip():
        return text
    first = str(text).strip().split("\n")[0].strip()
    if first.startswith("【摘要】"):
        return text
    tpl = _templates()
    if is_llm_failure_payload(text):
        prefix = str(tpl.get("summary_fallback_api_error") or "").format(
            market_phase=market_phase
        )
        return prefix + text
    prefix = str(tpl.get("summary_fallback_generic") or "").format(
        market_phase=market_phase
    )
    return prefix + text
