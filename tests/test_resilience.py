# -*- coding: utf-8 -*-
from app.infrastructure.resilience.circuit_breaker import CircuitBreaker
from app.infrastructure.resilience.exceptions import FaultCategory, classify_exception
from app.infrastructure.resilience.registry import reset_registry_for_tests
from app.infrastructure.validation import normalize_trade_date_str
from app.services.data_source_errors import DataSourceCircuitOpenError


def test_circuit_opens_after_failures():
    import time

    cb = CircuitBreaker("t", failure_threshold=2, recovery_timeout_sec=0.08)
    assert cb.allow_request() is True
    cb.record_failure()
    assert cb.allow_request() is True
    cb.record_failure()
    assert cb.allow_request() is False
    time.sleep(0.12)
    assert cb.allow_request() is True


def test_classify_circuit():
    assert (
        classify_exception(DataSourceCircuitOpenError("x"))
        == FaultCategory.CIRCUIT_OPEN
    )


def test_normalize_trade_date():
    assert normalize_trade_date_str("20260328") == "20260328"
    assert normalize_trade_date_str(20260328) == "20260328"
    assert normalize_trade_date_str("bad") is None


def teardown_module():
    reset_registry_for_tests()
