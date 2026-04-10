# -*- coding: utf-8 -*-
import pandas as pd

from app.services.replay_catalog import (
    _board_kind,
    _norm6,
    _is_yizi_row,
    _format_fund_flow_block,
    _sentiment_dashboard_block,
)


def test_norm6():
    assert _norm6("sz000001") == "000001"
    assert _norm6(300001) == "300001"


def test_board_kind():
    assert _board_kind("300001") == "创业板"
    assert _board_kind("688001") == "科创板"
    assert _board_kind("600000") == "沪市主板"
    assert _board_kind("000001") == "深市主板"


def test_is_yizi_row():
    row = pd.Series({"zb_count": 0, "first_time": "09:25:00"})
    assert _is_yizi_row(row) is True
    row2 = pd.Series({"zb_count": 1, "first_time": "09:25:00"})
    assert _is_yizi_row(row2) is False


def test_format_fund_flow_block_empty():
    assert "暂无" in _format_fund_flow_block(pd.DataFrame(), title="测试", max_rows=5)


def test_sentiment_dashboard_has_rows():
    s = _sentiment_dashboard_block(
        3000,
        2000,
        55.0,
        2.5,
        30.0,
        70.0,
        60,
    )
    assert "上涨家数占比" in s
    assert "60°C" in s
