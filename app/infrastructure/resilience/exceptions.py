# -*- coding: utf-8 -*-
"""故障分类：日志、监控与降级策略共用。"""

from __future__ import annotations

from enum import Enum
from typing import Any


class FaultCategory(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_OPEN = "circuit_open"
    NETWORK = "network"
    VALIDATION = "validation"
    DATA_SOURCE = "data_source"
    DATA_INVALID = "data_invalid"
    LLM = "llm"
    UNKNOWN = "unknown"


def classify_exception(exc: BaseException) -> FaultCategory:
    """将异常粗分为企业级类别（用于日志与告警）。"""
    from requests.exceptions import ConnectionError, Timeout

    from app.services.data_source_errors import (
        DataSourceCircuitOpenError,
        DataSourceError,
        DataSourceExhaustedError,
        DataSourceInvalidError,
        DataSourceTimeoutError,
    )

    if isinstance(exc, DataSourceCircuitOpenError):
        return FaultCategory.CIRCUIT_OPEN
    if isinstance(exc, DataSourceTimeoutError):
        return FaultCategory.TIMEOUT
    if isinstance(exc, DataSourceInvalidError):
        return FaultCategory.DATA_INVALID
    if isinstance(exc, DataSourceExhaustedError):
        return FaultCategory.DATA_SOURCE
    if isinstance(exc, DataSourceError):
        return FaultCategory.DATA_SOURCE
    if isinstance(exc, (Timeout, TimeoutError)):
        return FaultCategory.TIMEOUT
    if isinstance(exc, ConnectionError):
        return FaultCategory.NETWORK
    if isinstance(exc, ValueError):
        return FaultCategory.VALIDATION
    s = str(exc).lower()
    if "429" in s or "限速" in s or "rate limit" in s:
        return FaultCategory.RATE_LIMIT
    return FaultCategory.UNKNOWN


def format_fault_log(exc: BaseException, *, context: str = "") -> str:
    cat = classify_exception(exc)
    ctx = f"{context}: " if context else ""
    return f"[{cat.value}] {ctx}{type(exc).__name__}: {exc!s}"
