# -*- coding: utf-8 -*-
"""
编排层：复盘流水线阶段常量（与 `ReplayTask.run` 步骤对齐）。

用于日志打点、监控与后续将 `run` 拆为显式步骤时的参照；
不在此处重复业务规则实现。
"""

from __future__ import annotations

# 顺序与 replay_task.run 主路径一致（断点续跑时部分阶段缩短或跳过）。
REPLAY_PIPELINE_PHASES: tuple[str, ...] = (
    "attach_fetcher_task",
    "checkpoint_or_fetch_market",
    "separation_confirmation",
    "finance_news_mapping",
    "style_stability_probe",
    "build_prompt",
    "llm_main_completion",
    "summary_and_section_rules",
    "report_builder_core_plan",
    "news_prefix_truncate_and_prepend",
    "replay_viewpoint_footer",
    "persist_top_pool_and_style_indices",
    "email_notify",
)
