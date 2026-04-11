# -*- coding: utf-8 -*-
"""可观测性：追踪 ID、结构化日志、埋点、告警、崩溃钩子。"""

from app.infrastructure.observability.alerts import alert_failure
from app.infrastructure.observability.crash import install_crash_hooks
from app.infrastructure.observability.events import emit_event
from app.infrastructure.observability.trace_context import (
    get_trace_id,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
    trace_scope,
)

__all__ = [
    "alert_failure",
    "emit_event",
    "get_trace_id",
    "install_crash_hooks",
    "new_trace_id",
    "reset_trace_id",
    "set_trace_id",
    "trace_scope",
]
