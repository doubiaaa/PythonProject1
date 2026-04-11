# -*- coding: utf-8 -*-
"""结构化决策辅助：一次低温 LLM 调用，输出可解析 JSON（非投资建议）。"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.services.llm_client import get_llm_client


def _strip_json_fence(text: str) -> str:
    s = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        return m.group(1).strip()
    return s


def call_structured_decision(
    api_key: str,
    *,
    program_facts_json: dict[str, Any],
    report_excerpt: str,
    program_facts_text: str,
    max_tokens: int = 600,
    temperature: float = 0.15,
) -> Optional[dict[str, Any]]:
    """
    让模型输出单一 JSON，表达与程序数据的对齐程度与风险，而非润色正文。
    解析失败返回 None。
    """
    sys_hint = (
        "你只允许输出一个 JSON 对象，不要 markdown，不要前言后语。"
        "字段必须齐全："
        '{"stance":"defensive|neutral|aggressive",'
        '"confidence":0.0,'
        '"program_alignment":"aligned|partial|conflict",'
        '"key_risks":[],'
        '"watch_next":[],'
        '"hallucination_risk":"low|medium|high",'
        '"decision_basis":"一句话说明结论如何依赖程序量化事实"}'
    )
    payload = {
        "程序量化摘要": program_facts_json,
        "程序事实文本摘录": (program_facts_text or "")[:6000],
        "复盘正文摘录": (report_excerpt or "")[:8000],
    }
    user = sys_hint + "\n\n" + json.dumps(payload, ensure_ascii=False)
    client = get_llm_client(api_key)
    raw = client.chat_completion(
        user,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not raw or "API" in raw[:80]:
        return None
    try:
        return json.loads(_strip_json_fence(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
