# -*- coding: utf-8 -*-
"""请求/任务级追踪 ID（asyncio 与线程安全，基于 contextvars）。"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    v = _trace_id_var.get()
    return v if v else "-"


def set_trace_id(trace_id: str) -> contextvars.Token[Optional[str]]:
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: contextvars.Token[Optional[str]]) -> None:
    _trace_id_var.reset(token)


@contextmanager
def trace_scope(trace_id: Optional[str] = None) -> Iterator[str]:
    """进入作用域时绑定 trace_id，退出时恢复。"""
    tid = trace_id or new_trace_id()
    token = set_trace_id(tid)
    try:
        yield tid
    finally:
        reset_trace_id(token)
