# -*- coding: utf-8 -*-
from app.application.llm_intel.audit import run_deterministic_audit
from app.application.llm_intel.reference_facts import ReferenceFacts


def test_audit_zt_mismatch():
    ref = ReferenceFacts(
        trade_date="20260101",
        zt_count=40,
        dt_count=5,
    )
    text = "今日涨停 12 家，情绪偏弱。"
    ar = run_deterministic_audit(text, ref)
    assert any(c.field == "zt_count" and c.status == "mismatch" for c in ar.fact_checks)


def test_audit_zt_ok():
    ref = ReferenceFacts(trade_date="20260101", zt_count=40)
    text = "涨停 40 家，结构尚可。"
    ar = run_deterministic_audit(text, ref)
    assert any(c.field == "zt_count" and c.status == "ok" for c in ar.fact_checks)


def test_reference_from_fetcher():
    class F:
        _last_market_phase = "退潮期"
        _last_email_kpi = {"zt_count": 30, "dt_count": 2, "premium": 1.2, "zhaban_rate": 0.25}

    r = ReferenceFacts.from_data_fetcher(F(), "20260328")
    assert r.zt_count == 30
    assert r.premium_pct == 1.2
    assert r.zhaban_rate == 0.25
