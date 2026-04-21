# -*- coding: utf-8 -*-
"""失败告警：写入 errors.log + alerts.log（带 alert 标记）。"""

from __future__ import annotations

from typing import Any

from app.utils.logger import get_logger

_log = get_logger("alert")


def alert_failure(message: str, **ctx: Any) -> None:
    """
    业务失败告警：ERROR 级别 + alert=True，便于从 alerts.log 快速 grep。
    ctx 会进入 JSON 的 extra 字段。
    """
    extra: dict[str, Any] = {"alert": True, "event": "alert.failure", **ctx}
    _log.error(message, extra=extra)
