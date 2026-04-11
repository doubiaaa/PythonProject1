# -*- coding: utf-8 -*-
from app.services.replay_llm_enhancements import (
    build_enhancement_prompt,
    collect_program_facts_snapshot,
)


class _DF:
    _last_market_phase = "高位震荡期"
    _last_dragon_trader_meta = {"zt_count": 42}
    _last_email_kpi = {"x": 1}
    _last_auction_meta = {
        "top_pool": [
            {"code": "000001", "name": "测试", "tag": "打板", "lb": 3},
        ]
    }


def test_collect_program_facts_snapshot():
    s = collect_program_facts_snapshot(
        "20260328",
        "## 市场\n正文",
        _DF(),
        None,
    )
    assert "20260328" in s
    assert "程序判定市场阶段" in s
    assert "000001" in s


def test_build_enhancement_prompt_has_sections():
    p = build_enhancement_prompt(
        "20260328",
        "事实：涨停 40",
        "## 长文\n摘要",
    )
    assert "一致性核对" in p
    assert "多空对照" in p
    assert "龙头池逐票观察清单" in p
    assert "程序异常与假设验证" in p
    assert "主线与题材结构" in p
