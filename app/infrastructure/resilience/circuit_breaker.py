# -*- coding: utf-8 -*-
"""简单熔断器：连续失败后进入打开态，冷却结束后自动关闭。"""

from __future__ import annotations

import threading
import time
from typing import Optional


class CircuitBreaker:
    """
    - closed：正常；连续失败达阈 → open（记录 opened_at）。
    - open：在 recovery_timeout 内拒绝请求；超时后自动关闭并清零失败计数。
    """

    __slots__ = (
        "_name",
        "_failure_threshold",
        "_recovery_timeout_sec",
        "_failures",
        "_opened_at",
        "_lock",
    )

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout_sec: float = 60.0,
    ) -> None:
        self._name = name
        self._failure_threshold = max(1, int(failure_threshold))
        # 允许亚秒级冷却（测试与低延迟降级）；下限 50ms 避免忙等
        self._recovery_timeout_sec = max(0.05, float(recovery_timeout_sec))
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return self._name

    def allow_request(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if self._opened_at is None:
                return True
            if now - self._opened_at >= self._recovery_timeout_sec:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._opened_at = time.monotonic()

    def state_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "name": self._name,
                "failures": self._failures,
                "opened_at": self._opened_at,
            }
