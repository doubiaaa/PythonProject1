# -*- coding: utf-8 -*-
"""隔离子步骤失败，避免拖垮主流程。"""

from __future__ import annotations

from typing import Callable, Optional, TypeVar

from app.infrastructure.resilience.exceptions import format_fault_log
from app.utils.logger import get_logger

_log = get_logger(__name__)

T = TypeVar("T")


def safe_call(
    fn: Callable[[], T],
    *,
    default: T,
    step_name: str = "",
    swallow: tuple[type, ...] = (Exception,),
) -> T:
    """
    执行可调用对象；异常时记录日志并返回 default（默认捕获 Exception，不含 BaseException）。
    """
    try:
        return fn()
    except swallow as e:
        ctx = step_name or fn.__name__
        _log.warning("%s", format_fault_log(e, context=ctx))
        return default


def safe_call_optional(
    fn: Callable[[], T],
    *,
    step_name: str = "",
) -> Optional[T]:
    try:
        return fn()
    except Exception as e:
        ctx = step_name or fn.__name__
        _log.warning("%s", format_fault_log(e, context=ctx))
        return None
