# -*- coding: utf-8 -*-
"""关键节点埋点：统一 event 字段，便于检索与仪表盘对接。"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.logger import get_logger

_log = get_logger("obs.event")


def emit_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """
    结构化埋点：写入主日志（JSON 模式下 extra 在 payload.extra）。

    建议 event 命名：域.动作，如 replay.data_complete、llm.circuit_open。
    """
    extra = {"event": event}
    for k, v in fields.items():
        if k not in ("msg", "message"):
            extra[k] = v
    _log.log(level, event, extra=extra)
