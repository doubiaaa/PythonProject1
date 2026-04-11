# -*- coding: utf-8 -*-
"""
统一日志：控制台 + 按天滚动文件；可选 JSON 结构化（见 observability）。

用法：from app.utils.logger import get_logger; get_logger(__name__).info("...")
追踪：from app.infrastructure.observability import trace_scope, get_trace_id
"""
from __future__ import annotations

import logging

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根日志器（幂等）；具体格式由 observability + replay_config 决定。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    from app.infrastructure.observability.logging_setup import configure_root_logging

    configure_root_logging()
    if level != logging.INFO:
        logging.getLogger().setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
