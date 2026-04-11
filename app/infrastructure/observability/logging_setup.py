# -*- coding: utf-8 -*-
"""根日志器配置：控制台 + app.log（JSON）+ errors.log + alerts.log。"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Any

_CONFIGURED = False


def _level_from_config(raw: Any) -> int:
    if isinstance(raw, int):
        return raw
    s = str(raw or "INFO").upper()
    return getattr(logging, s, logging.INFO)


def configure_root_logging(force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    from app.infrastructure.observability.filters import TraceContextFilter
    from app.infrastructure.observability.formatters import (
        ConsoleTextFormatter,
        JsonLogFormatter,
    )
    from app.utils.config import ConfigManager, get_project_root

    cm = ConfigManager()
    obs = cm.config.get("observability") or {}
    if not isinstance(obs, dict):
        obs = {}

    log_dir_rel = str(obs.get("log_dir") or "data/logs")
    root_path = get_project_root()
    log_dir = os.path.normpath(os.path.join(root_path, log_dir_rel.replace("/", os.sep)))
    os.makedirs(log_dir, exist_ok=True)

    level = _level_from_config(obs.get("log_level", "INFO"))
    file_fmt = str(obs.get("file_log_format") or "json").lower()
    console_fmt = str(obs.get("console_log_format") or "text").lower()
    error_enabled = obs.get("error_log_enabled", True)
    alert_enabled = obs.get("alert_log_enabled", True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    trace_filt = TraceContextFilter()

    # 控制台
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.addFilter(trace_filt)
    if console_fmt == "json":
        sh.setFormatter(JsonLogFormatter())
    else:
        sh.setFormatter(ConsoleTextFormatter())
    root.addHandler(sh)

    # 主文件（JSON 推荐）
    app_log = os.path.join(log_dir, "app.log")
    fh = TimedRotatingFileHandler(
        app_log,
        when="midnight",
        interval=1,
        backupCount=int(obs.get("log_backup_count", 30)),
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.addFilter(trace_filt)
    if file_fmt == "text":
        fh.setFormatter(ConsoleTextFormatter())
    else:
        fh.setFormatter(JsonLogFormatter())
    root.addHandler(fh)

    # 仅 ERROR+
    if error_enabled:
        err_path = os.path.join(log_dir, "errors.log")
        eh = TimedRotatingFileHandler(
            err_path,
            when="midnight",
            interval=1,
            backupCount=int(obs.get("error_log_backup_count", 14)),
            encoding="utf-8",
        )
        eh.setLevel(logging.ERROR)
        eh.addFilter(trace_filt)
        eh.setFormatter(JsonLogFormatter())
        root.addHandler(eh)

    # 告警专用（带 alert=True 的日志）
    if alert_enabled:
        from app.infrastructure.observability.filters import AlertOnlyFilter

        alert_path = os.path.join(log_dir, "alerts.log")
        ah = TimedRotatingFileHandler(
            alert_path,
            when="midnight",
            interval=1,
            backupCount=int(obs.get("alert_log_backup_count", 30)),
            encoding="utf-8",
        )
        ah.setLevel(logging.ERROR)
        ah.addFilter(trace_filt)
        ah.addFilter(AlertOnlyFilter())
        ah.setFormatter(JsonLogFormatter())
        root.addHandler(ah)

    _CONFIGURED = True


def reset_logging_for_tests() -> None:
    global _CONFIGURED
    _CONFIGURED = False
    logging.getLogger().handlers.clear()
    try:
        import app.utils.logger as logger_mod

        logger_mod._CONFIGURED = False  # type: ignore[attr-defined]
    except Exception:
        pass
