# -*- coding: utf-8 -*-
"""
应用服务层：复盘报告正文相关的纯规则（无 IO、无框架）。

由编排层调用；单元测试直接导入本模块，避免依赖 ReplayTask 全链路。
"""

from __future__ import annotations

from typing import Optional

_DRAGON_HEADINGS = (
    "盘面综述",
    "情绪与数据解读",
    "周期定性",
    "情绪数据量化",
    "核心股聚焦",
    "明日预案",
)


def is_llm_failure_payload(text: str) -> bool:
    """返回内容实为 API 错误串（无模型正文），避免误报「缺章节」。"""
    s = (text or "").strip()[:1200]
    markers = (
        "API请求失败（",
        "调用大模型 API",
        "错误：大模型 API",
        "API 返回异常",
        "您的账户已达到速率限制",
        '"code":"1302"',
        "请求频率",
        "账户余额不足",
    )
    return any(m in s for m in markers)


def ensure_dragon_report_sections(text: str) -> str:
    """若缺少龙头模板关键章节标题，在文末追加系统提示（不重试 API）。"""
    if not text or not str(text).strip():
        return text
    if is_llm_failure_payload(text):
        note = (
            "\n\n---\n\n> **【系统提示】** 本次 **未生成 AI 复盘长文**（上方为大模型接口报错或限速），"
            "**并非** 章节未写全。请间隔数分钟后重试，或检查 API Key、配额与并发；"
            "程序数据目录仍在上方市场摘要中可阅。\n"
        )
        return text.rstrip() + note
    missing = [h for h in _DRAGON_HEADINGS if h not in text]
    if not missing:
        return text
    note = (
        "\n\n---\n\n> **【系统提示】** 本次输出未检测到以下章节标题，"
        "请人工对照程序数据复核或缩小单节篇幅后重试："
        + "、".join(missing)
        + "。\n"
    )
    return text.rstrip() + note


def extract_summary_line(text: str) -> Optional[str]:
    """解析报告首行【摘要】…，用于推送标题。"""
    if not text:
        return None
    for line in text.strip().split("\n"):
        s = line.strip()
        if s.startswith("【摘要】"):
            return s[:220]
    return None


def ensure_summary_line(text: str, market_phase: str = "高位震荡期") -> str:
    """模型未输出规范【摘要】首行时补一行，便于推送解析与阅读。"""
    if not text or not str(text).strip():
        return text
    first = str(text).strip().split("\n")[0].strip()
    if first.startswith("【摘要】"):
        return text
    if is_llm_failure_payload(text):
        return (
            f"【摘要】周期阶段：{market_phase}｜适宜度：—｜置信度：低（未生成正文：大模型限速或服务异常，见下方）\n\n"
            + text
        )
    return (
        f"【摘要】周期阶段：{market_phase}｜适宜度：中｜置信度：低（系统补全：模型未输出规范首行摘要）\n\n"
        + text
    )
