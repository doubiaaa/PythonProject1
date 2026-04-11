# -*- coding: utf-8 -*-
"""日志 Filter：注入 trace_id、运行环境等。"""

from __future__ import annotations

import logging
import os

from app.infrastructure.observability.trace_context import get_trace_id


class AlertOnlyFilter(logging.Filter):
    """仅通过 `extra` 中带 alert=True 的记录（写入 alerts.log）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return bool(getattr(record, "alert", False))


class TraceContextFilter(logging.Filter):
    """为每条 LogRecord 设置 trace_id（供 Formatter 使用）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        if not hasattr(record, "env"):
            record.env = os.environ.get("APP_ENV", os.environ.get("ENV", "dev"))
        return True
