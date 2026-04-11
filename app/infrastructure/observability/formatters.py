# -*- coding: utf-8 -*-
"""结构化日志行：JSON（便于采集）与文本（便于控制台）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

# LogRecord 内置字段，不作为业务扩展输出
_LOGRECORD_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "msecs",
        "relativeCreated",
        "levelno",
        "levelname",
        "pathname",
        "filename",
        "module",
        "lineno",
        "funcName",
        "exc_info",
        "exc_text",
        "stack_info",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
        "trace_id",
        "env",
    }
)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in record.__dict__.items():
        if k in _LOGRECORD_RESERVED or k.startswith("_"):
            continue
        if k in ("message",):
            continue
        try:
            json.dumps(v, default=str)
        except (TypeError, ValueError):
            v = str(v)
        out[k] = v
    return out


class JsonLogFormatter(logging.Formatter):
    """单行 JSON：ts、level、logger、trace_id、module、msg + 任意 extra。"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "trace_id": getattr(record, "trace_id", "-"),
            "env": getattr(record, "env", "dev"),
            "msg": record.getMessage(),
        }
        xf = _extra_fields(record)
        if xf:
            payload["extra"] = xf
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info).strip()
        line = json.dumps(payload, ensure_ascii=False, default=str)
        return line


class ConsoleTextFormatter(logging.Formatter):
    """控制台：时间 + 级别 + trace + logger + 消息。"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s [%(trace_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return super().format(record)
