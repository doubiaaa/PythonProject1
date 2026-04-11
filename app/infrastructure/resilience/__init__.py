# -*- coding: utf-8 -*-
"""企业级容错：熔断、异常分类、安全执行。"""

from app.infrastructure.resilience.circuit_breaker import CircuitBreaker
from app.infrastructure.resilience.exceptions import FaultCategory, classify_exception, format_fault_log
from app.infrastructure.resilience.registry import get_circuit, reset_registry_for_tests
from app.infrastructure.resilience.safe_execute import safe_call, safe_call_optional

__all__ = [
    "CircuitBreaker",
    "FaultCategory",
    "classify_exception",
    "format_fault_log",
    "get_circuit",
    "reset_registry_for_tests",
    "safe_call",
    "safe_call_optional",
]
