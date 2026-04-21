# -*- coding: utf-8 -*-
"""输出层：复盘邮件标题拼装（无 SMTP）。"""

from __future__ import annotations

from typing import Optional


def build_replay_success_email_subject(
    *,
    summary_line: Optional[str],
    trade_date: str,
    mode_name: str,
    rule_status_suffix: str = "",
) -> str:
    """成功完成复盘时的邮件主题。"""
    suffix = f" {rule_status_suffix.strip()}" if str(rule_status_suffix).strip() else ""
    if summary_line:
        return f"【复盘】✅ {summary_line}{suffix} · {trade_date}"
    return f"【复盘】✅ 复盘完成{suffix} · {mode_name} · {trade_date}"


def build_replay_failure_email_subject(*, mode_name: str, trade_date: str) -> str:
    return f"【复盘】❌ 复盘失败 · {mode_name} · {trade_date}"
