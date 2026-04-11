# -*- coding: utf-8 -*-
from app.services.strategy_engine import StrategyEngine, reset_strategy_engine_for_tests


def test_market_phase_matches_legacy_vectors():
    eng = StrategyEngine()
    assert eng.compute_market_phase(82, 40, 10, 30, 6, 2.0) == ("主升期", "80%")
    p, pos = eng.compute_market_phase(28, 10, 40, 50, 2, 0.5)
    assert "退潮" in p and "0-10" in pos
    assert eng.compute_market_phase(55, 25, 15, 46, 4, 0.5)[0] == "混沌·试错期"
    assert eng.compute_market_phase(50, 30, 20, 35, 4, 1.5) == ("高位震荡期", "30%")


def test_sentiment_temperature_cap():
    reset_strategy_engine_for_tests()
    eng = StrategyEngine()
    t = eng.compute_sentiment_temperature(50, 3, 5.0, {"mean_5": 0, "past_sample_n": 3}, 20)
    assert 0 <= t <= 100
