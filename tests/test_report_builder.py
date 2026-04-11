# -*- coding: utf-8 -*-
from app.services.report_builder import (
    append_core_stocks_and_plan_if_missing,
    missing_core_stocks_and_plan,
)


def test_missing_detection():
    a = "### 五、核心股聚焦\nxx\n### 七、明日预案\nyy"
    assert missing_core_stocks_and_plan(a) == (False, False)
    b = "### 一、盘面\n"
    assert missing_core_stocks_and_plan(b) == (True, True)


def test_append_inserts_five_and_seven():
    class _F:
        _last_market_phase = "混沌·试错期"
        _last_position_suggestion = "15-25%"
        _last_auction_meta = {
            "top_pool": [{"code": "000001", "name": "测试", "tag": "龙头", "lb": 2, "sector": "银", "score": 8.1}],
            "main_sectors": ["银行"],
        }
        _last_dragon_trader_meta = {}
        _last_zt_pool = None

    raw = "# 标题\n### 免责声明\n> xx\n"
    out = append_core_stocks_and_plan_if_missing(
        raw,
        actual_date="20260408",
        data_fetcher=_F(),
        enable=True,
        use_llm=False,
    )
    assert "### 五、核心股聚焦（程序补充）" in out
    assert "### 七、明日预案" in out
    assert "### 免责声明" in out
