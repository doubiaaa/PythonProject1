# -*- coding: utf-8 -*-
import pandas as pd
import pytest

from app.services.replay_catalog import (
    _board_kind,
    _norm6,
    _is_yizi_row,
    _format_fund_flow_block,
    _sentiment_dashboard_block,
    _dash_date_yyyymmdd,
    _monitor_window_end,
    _sim_closed_trades_stats,
    _max_drawdown_pct_from_series,
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


def test_dash_date_yyyymmdd():
    assert _dash_date_yyyymmdd("20260330") == "2026-03-30"


def test_monitor_window_end():
    days = ["20260325", "20260326", "20260327", "20260328", "20260330"]
    assert _monitor_window_end("20260326", days, 1) == "20260326"
    assert _monitor_window_end("20260326", days, 3) == "20260328"


def test_sim_closed_trades_stats_fifo():
    txs = [
        {"date": "20260101", "symbol": "000001", "side": "buy", "shares": 100, "amount": 1000},
        {"date": "20260102", "symbol": "000001", "side": "sell", "shares": 100, "amount": 1100},
    ]
    n, nw, gp, gl = _sim_closed_trades_stats(txs)
    assert n == 1 and nw == 1 and gp == 100 and gl == 0


def test_max_drawdown_pct():
    assert _max_drawdown_pct_from_series([100.0, 110.0, 88.0]) == pytest.approx(20.0)


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
