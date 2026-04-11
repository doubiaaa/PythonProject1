# -*- coding: utf-8 -*-
from app.services.strategy_engine import StrategyEngine, reset_strategy_engine_for_tests


def test_kebi_maps_legacy_phases():
    reset_strategy_engine_for_tests()
    eng = StrategyEngine()
    b = eng.get_kebi_stage_bundle("主升期")
    assert b["stage_id"] == "stage_2"
    assert b["stage"].get("primary_operation") == "龙头"


def test_kebi_markdown_contains_sections():
    reset_strategy_engine_for_tests()
    eng = StrategyEngine()
    md = eng.format_kebi_conclusion_markdown("高位震荡期", "20-40%")
    assert "92科比" in md
    assert "阶段3" in md or "高位震荡" in md
    assert "程序原建议仓位" in md or "程序仓位" in md
