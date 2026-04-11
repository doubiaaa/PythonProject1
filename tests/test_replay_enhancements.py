# -*- coding: utf-8 -*-
from app.services.replay_llm_enhancements import (
    build_enhancement_prompt,
    collect_program_facts_snapshot,
    run_replay_enhancement_bundle,
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


def test_run_replay_enhancement_bundle_parallel_concat_order(monkeypatch):
    """并行模式下拼接顺序固定为 main → qc → cmp → news。"""
    from app.services import replay_llm_enhancements as mod

    monkeypatch.setattr(
        mod, "collect_program_facts_snapshot", lambda *a, **k: "pf"
    )

    def fake_main(*a, **k):
        return "M"

    def fake_qc(*a, **k):
        return "Q"

    def fake_cmp(*a, **k):
        return "C"

    def fake_news(*a, **k):
        return "N"

    monkeypatch.setattr(mod, "run_replay_deepseek_enhancements", fake_main)
    monkeypatch.setattr(mod, "run_replay_chapter_quality", fake_qc)
    monkeypatch.setattr(mod, "run_replay_comparison_narrative", fake_cmp)
    monkeypatch.setattr(mod, "run_replay_news_event_chain", fake_news)

    class _DF:
        _last_finance_news_related = [1]
        _last_finance_news_general = []

    out = run_replay_enhancement_bundle(
        parallel=True,
        max_workers=4,
        gap_en=0,
        gap_x=0,
        actual_date="20260101",
        market_data="",
        data_fetcher=_DF(),
        separation_result=None,
        api_key="k",
        result="base",
        main_report_for_qc="qcin",
        _en_main=True,
        _en_qc=True,
        _en_cmp=True,
        _en_news=True,
        mt=100,
        mi=3,
        log=lambda _m: None,
    )
    assert out == "MQCN"
