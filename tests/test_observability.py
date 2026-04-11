# -*- coding: utf-8 -*-
import json
import logging

from app.infrastructure.observability.formatters import JsonLogFormatter
from app.infrastructure.observability.logging_setup import reset_logging_for_tests
from app.infrastructure.observability.trace_context import get_trace_id, trace_scope


def test_trace_scope():
    assert get_trace_id() == "-"
    with trace_scope() as tid:
        assert get_trace_id() == tid
        assert len(tid) == 16
    assert get_trace_id() == "-"


def test_json_formatter_includes_trace():
    fmt = JsonLogFormatter()
    r = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    r.trace_id = "abc123"
    r.env = "test"
    line = fmt.format(r)
    d = json.loads(line)
    assert d["trace_id"] == "abc123"
    assert d["level"] == "INFO"
    assert d["msg"] == "hello"


def teardown_module():
    reset_logging_for_tests()
