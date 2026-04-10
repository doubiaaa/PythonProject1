# -*- coding: utf-8 -*-
from app.services.data_fetcher import compute_short_term_market_phase


def test_market_phase_main_rise():
    p, pos = compute_short_term_market_phase(82, 40, 10, 30, 6, 2.0)
    assert p == "主升期"
    assert pos == "80%"


def test_market_phase_ice():
    p, pos = compute_short_term_market_phase(28, 10, 40, 50, 2, 0.5)
    assert "退潮" in p
    assert "0-10" in pos


def test_market_phase_chaos_zhaban():
    p, _ = compute_short_term_market_phase(55, 25, 15, 46, 4, 0.5)
    assert p == "混沌·试错期"


def test_market_phase_default_range():
    p, pos = compute_short_term_market_phase(50, 30, 20, 35, 4, 1.5)
    assert p == "高位震荡期"
    assert pos == "30%"
