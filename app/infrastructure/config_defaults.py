# -*- coding: utf-8 -*-
"""
应用默认配置（唯一真源）：JSON 与环境变量在其上合并。

业务键名保持稳定，与历史 `replay_config.json` 字段兼容。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    # 大模型：DeepSeek（OpenAI 兼容）
    "deepseek_api_key": "",
    "llm_api_key": "",
    "llm_model_name": "",
    "deepseek_model_name": "",
    "llm_api_base": "",
    "llm_default_url": "https://api.deepseek.com/v1/chat/completions",
    "llm_transport_timeout_sec": 120,
    "llm_retry_attempts": 3,
    "llm_retry_429": 6,
    "llm_retry_429_wait_sec": 30,
    "llm_retry_429_wait_max_sec": 180,
    "llm_chat_default_temperature": 0.42,
    "llm_chat_default_max_tokens": 6144,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "mail_to": "",
    "smtp_ssl": False,
    "email_html_template_enabled": True,
    "email_content_prefix": True,
    "email_news_max_items": 3,
    "email_news_filter_prefix": "【本文系数据通用户提前专享】",
    "email_app_version": "1.0",
    "email_max_body_chars": 200000,
    "email_max_subject_chars": 200,
    "report_title_template": "T+0 竞价复盘 · 对 {trade_date} 的复盘",
    "email_system_name": "T+0 竞价复盘系统",
    "market_summary_parallel_fetch": True,
    "fetch_parallel_max_workers": 8,
    "zhaban_percentile_lookback": 15,
    "weekly_email_attach_charts": True,
    "cache_expire": 3600,
    "retry_times": 2,
    "w_main": 0.22,
    "w_dragon": 0.18,
    "w_kline": 0.18,
    "w_liq": 0.14,
    "w_tech": 0.28,
    "tech_eval_topn": 12,
    "enable_tech_momentum": True,
    "enable_finance_news": True,
    "enable_individual_fund_flow_rank": True,
    "individual_fund_flow_top_n": 12,
    "enable_concept_cons_snapshot": True,
    "concept_board_symbols": [],
    "enable_intraday_tick_probe": False,
    "intraday_tick_probe_symbol": "",
    "enable_weekly_performance_email": True,
    "enable_weekly_ai_insight": True,
    "enable_weekly_market_snapshot": True,
    "enable_daily_style_indices_persist": True,
    "enable_strict_weekly_top20": True,
    "weekly_strict_top20_max_universe": 2800,
    "enable_strategy_feedback_loop": True,
    "strategy_weight_smoothing": 0.3,
    "strategy_weight_max_single": 0.55,
    "strategy_weight_min_each": 0.08,
    "strategy_weight_clip_low": 0.01,
    "strategy_weight_clip_high": 0.99,
    "strategy_weight_history_max": 10,
    "min_trades_per_style_for_weight": 3,
    "use_multi_week_decay_for_strategy": True,
    "multi_week_lookback": 4,
    "strategy_week_decay_factor": 0.75,
    "min_total_trades_per_bucket_multiweek": 3,
    "strategy_max_change_per_week": 0.25,
    "strategy_shift_pullback": 0.5,
    "enable_style_stability_probe": False,
    "replay_llm_spacing_sec": 15,
    "enable_report_builder_core_stocks_plan": True,
    "enable_report_core_stocks_llm": False,
    "enable_replay_llm_enhancements": True,
    "replay_llm_enhancements_max_tokens": 6144,
    "replay_llm_enhancements_spacing_sec": 8,
    "enable_replay_llm_chapter_qc": True,
    "enable_replay_llm_comparison_narrative": True,
    "enable_replay_llm_news_deep": True,
    "replay_llm_extra_spacing_sec": 8,
    "replay_llm_enhancements_parallel": False,
    "replay_llm_parallel_max_workers": 4,
    "disk_cache_sweep_ttl_sec": 86400,
    "enable_weekly_llm_trend_narrative": True,
    "enable_weekly_weight_anomaly_email": True,
    "enable_weekly_weight_llm_explanation": True,
    "enable_replay_lhb_catalog": True,
    "enable_replay_concept_fund_snapshot": True,
    "enable_replay_watchlist_snapshot": True,
    "replay_watchlist_max_rows": 40,
    "replay_watchlist_monitor_span": 5,
    "enable_replay_watchlist_spot_followup": True,
    "replay_watchlist_spot_followup_max_codes": 15,
    "enable_replay_spot_5d_leaderboard": True,
    "replay_spot_5d_top_n": 19,
    "enable_replay_checkpoint": True,
    "enable_replay_six_pillar_framework": True,
    "resume_replay_if_available": False,
    "strategy_max_weight_delta_per_update": 0.10,
    "active_strategy_profile": "default",
    "strategy_profiles": {
        "default": {},
    },
    "llm_failure_markers": [
        "API请求失败（",
        "调用大模型 API",
        "错误：大模型 API",
        "API 返回异常",
        "您的账户已达到速率限制",
        '"code":"1302"',
        "请求频率",
        "账户余额不足",
    ],
    "llm_failure_payload_scan_chars": 1200,
    "dragon_report_headings": [
        "盘面综述",
        "情绪与数据解读",
        "周期定性",
        "情绪数据量化",
        "核心股聚焦",
        "明日预案",
    ],
    "replay_summary_line_max_chars": 220,
    "replay_text_templates": {
        "summary_fallback_api_error": (
            "【摘要】周期阶段：{market_phase}｜适宜度：—｜置信度：低"
            "（未生成正文：大模型限速或服务异常，见下方）\n\n"
        ),
        "summary_fallback_generic": (
            "【摘要】周期阶段：{market_phase}｜适宜度：中｜置信度：低"
            "（系统补全：模型未输出规范首行摘要）\n\n"
        ),
        "dragon_llm_failure_note": (
            "\n\n---\n\n> **【系统提示】** 本次 **未生成 AI 复盘长文**（上方为大模型接口报错或限速），"
            "**并非** 章节未写全。请间隔数分钟后重试，或检查 API Key、配额与并发；"
            "程序数据目录仍在上方市场摘要中可阅。\n"
        ),
        "dragon_missing_headings_intro": (
            "\n\n---\n\n> **【系统提示】** 本次输出未检测到以下章节标题，"
            "请人工对照程序数据复核或缩小单节篇幅后重试："
        ),
        "dragon_missing_headings_sep": "、",
        "dragon_missing_headings_end": "。\n",
    },
    "paths": {
        "data_dir": "data",
        "replay_status_dir": "data/replay_status",
        "watchlist_records_file": "data/watchlist_records.json",
        "market_style_indices_file": "data/market_style_indices.json",
        "strategy_preference_file": "data/strategy_preference.json",
        "strategy_evolution_log_file": "data/strategy_evolution_log.jsonl",
    },
    "data_source": {
        "timeout": 8,
        "retry_times": 3,
        "cache_expire_days": 1,
        "cache_dir": "data_cache",
        "llm_connect_timeout": 10,
        "llm_read_timeout": 120,
        # 悟道 OpenClaw：涨停梯队/炸板/跌停等（需 LB_API_KEY；见 app/services/lb_openclaw_client.py）
        "use_lb_openclaw": False,
        "lb_api_base": "https://stock.quicktiny.cn/api/openclaw",
        "lb_api_key": "",
    },
    # 容错：熔断（akshare / LLM HTTP 独立计数）、LLM 最小调用间隔（秒，0 表示不限制）
    "resilience": {
        "circuit_breaker_enabled": True,
        "circuit_breaker": {
            "akshare": {"failure_threshold": 8, "recovery_timeout_sec": 45},
            "llm_http": {"failure_threshold": 6, "recovery_timeout_sec": 90},
        },
        "llm_min_interval_sec": 0,
    },
    # 可观测性：结构化日志、埋点、告警文件（无界面，纯日志）
    # LLM 智能分析层：正文后追加「程序校验 + 结构化决策」（非投资建议）
    "llm_intel": {
        "enabled": True,
        "deterministic_audit": True,
        "structured_decision_llm": True,
        "decision_max_tokens": 600,
        "decision_temperature": 0.15,
    },
    "observability": {
        "log_dir": "data/logs",
        "log_level": "INFO",
        "file_log_format": "json",
        "console_log_format": "text",
        "log_backup_count": 30,
        "error_log_enabled": True,
        "error_log_backup_count": 14,
        "alert_log_enabled": True,
        "alert_log_backup_count": 30,
    },
}


def frozen_defaults() -> dict[str, Any]:
    """深拷贝，避免运行期修改污染模板。"""
    return deepcopy(DEFAULT_CONFIG)
