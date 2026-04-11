# -*- coding: utf-8 -*-
"""熔断器注册表（按名称单例，状态跨调用保留）。"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.resilience.circuit_breaker import CircuitBreaker

_lock = threading.RLock()
_registry: dict[str, "CircuitBreaker"] = {}


def get_circuit(name: str) -> "CircuitBreaker":
    from app.infrastructure.resilience.circuit_breaker import CircuitBreaker
    from app.utils.config import ConfigManager

    with _lock:
        if name in _registry:
            return _registry[name]
        cm = ConfigManager()
        res = cm.config.get("resilience") or {}
        if not isinstance(res, dict):
            res = {}
        if res.get("circuit_breaker_enabled") is False:

            class _Passthrough:
                __slots__ = ()

                def allow_request(self) -> bool:
                    return True

                def record_success(self) -> None:
                    pass

                def record_failure(self) -> None:
                    pass

            cb = _Passthrough()  # type: ignore[assignment]
        else:
            block = (res.get("circuit_breaker") or {}).get(name) or {}
            if not isinstance(block, dict):
                block = {}
            ft = int(block.get("failure_threshold", 5))
            rec = float(block.get("recovery_timeout_sec", 60))
            cb = CircuitBreaker(name, failure_threshold=ft, recovery_timeout_sec=rec)
        _registry[name] = cb
        return cb


def reset_registry_for_tests() -> None:
    with _lock:
        _registry.clear()
