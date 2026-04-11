# -*- coding: utf-8 -*-
"""未捕获异常钩子：保证崩溃栈写入结构化日志，便于事后定位。"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Callable, Optional

_installed = False


def install_crash_hooks() -> None:
    """安装进程级与（Python 3.8+）线程级未捕获异常钩子。可重复调用（幂等）。"""
    global _installed
    if _installed:
        return
    from app.utils.logger import setup_logging

    setup_logging()

    def _excepthook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: Any,
    ) -> None:
        logging.getLogger("crash").critical(
            "uncaught_exception",
            exc_info=(exc_type, exc, tb),
            extra={
                "event": "crash.uncaught",
                "fatal": True,
                "alert": True,
            },
        )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook

    if hasattr(threading, "excepthook"):
        _prev_thread: Optional[Callable[..., Any]] = getattr(
            threading, "excepthook", None
        )

        def _thread_excepthook(args: Any) -> None:
            logging.getLogger("crash").critical(
                "thread_uncaught_exception",
                exc_info=(
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                ),
                extra={
                    "event": "crash.thread",
                    "fatal": True,
                    "alert": True,
                    "thread_name": getattr(args.thread, "name", ""),
                },
            )
            if callable(_prev_thread) and _prev_thread is not _thread_excepthook:
                _prev_thread(args)

        threading.excepthook = _thread_excepthook  # type: ignore[attr-defined]

    _installed = True
