# -*- coding: utf-8 -*-
"""模拟账户：买卖、止盈止损、仓位上限。"""

import json
import os
import tempfile

import pytest

from app.services.simulated_account import (
    SimulatedAccount,
    count_trade_days_held,
    pending_buys_file,
    price_from_map,
    recommendations_from_top_pool,
)


def _make_acc():
    d = tempfile.mkdtemp()
    ap = os.path.join(d, "simulated_account.json")
    cp = os.path.join(d, "simulated_config.json")
    return SimulatedAccount(ap, cp, project_root=d), d, ap, cp


def test_buy_lot_and_cash():
    acc, _, _, _ = _make_acc()
    assert acc.buy("600000", "浦发银行", 100, 10.0, "测", "20260101")
    assert acc._state["cash"] == pytest.approx(9000.0)
    assert len(acc._state["holdings"]) == 1


def test_buy_rejects_bad_lot():
    acc, _, _, _ = _make_acc()
    assert not acc.buy("600000", "浦发银行", 50, 10.0, "测", "20260101")


def test_stop_loss_triggers():
    acc, _, _, _ = _make_acc()
    assert acc.buy("600000", "A", 100, 10.0, "测", "20260101")
    acc.update_prices({"600000": 9.4})
    sigs = acc.check_sell_signals("20260105")
    assert any(s["symbol"] == "600000" for s in sigs)


def test_stop_profit_triggers():
    acc, _, _, _ = _make_acc()
    assert acc.buy("600000", "A", 100, 10.0, "测", "20260101")
    acc.update_prices({"600000": 11.6})
    sigs = acc.check_sell_signals("20260105")
    assert any("止盈" in s.get("reason", "") for s in sigs)


def test_max_positions_in_execute():
    acc, _, ap, cp = _make_acc()
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "stop_loss": -0.5,
                "stop_profit": 9.0,
                "max_holding_days": 99,
                "max_positions": 2,
                "position_size_pct": 0.45,
                "min_cash_reserve": 100,
            },
            f,
        )
    acc.load_state()
    recs = [
        {"symbol": "600001", "name": "A", "style_bucket": "龙头", "buy_reason": "t"},
        {"symbol": "600002", "name": "B", "style_bucket": "龙头", "buy_reason": "t"},
        {"symbol": "600003", "name": "C", "style_bucket": "龙头", "buy_reason": "t"},
    ]
    prices = {"600001": 10.0, "600002": 10.0, "600003": 10.0}

    acc.execute_daily_trades(
        recs,
        "20260110",
        lambda s: price_from_map(prices, s),
    )
    assert len(acc._state["holdings"]) <= 2


def test_sell_before_buy_releases_cash():
    acc, _, _, _ = _make_acc()
    acc._cfg["max_positions"] = 1
    acc._cfg["position_size_pct"] = 0.5
    acc._cfg["min_cash_reserve"] = 0
    assert acc.buy("600000", "A", 100, 10.0, "首笔", "20260101")
    acc.update_prices({"600000": 9.0})
    acc.execute_daily_trades(
        [{"symbol": "600001", "name": "B", "style_bucket": "x", "buy_reason": "r"}],
        "20260110",
        lambda s: 10.0 if s == "600001" else 9.0,
    )
    assert any(t.get("side") == "sell" for t in acc._state["transactions"])


def test_count_trade_days_held():
    td = ["20260101", "20260102", "20260103", "20260106"]
    assert count_trade_days_held(td, "20260101", "20260103") == 2


def test_take_profit_before_max_hold_days():
    acc, _, _, _ = _make_acc()
    acc._cfg["max_holding_days"] = 1
    acc._cfg["stop_profit"] = 0.1
    acc._cfg["stop_loss"] = -0.5
    assert acc.buy("600000", "A", 100, 10.0, "测", "20260101")
    acc.update_prices({"600000": 12.0})
    sigs = acc.check_sell_signals("20260110", trade_days=["20260101", "20260102", "20260103"])
    assert sigs and "止盈" in sigs[0].get("reason", "")


def test_next_day_open_writes_pending():
    acc, d, _, cp = _make_acc()
    with open(cp, "w", encoding="utf-8") as f:
        import json

        json.dump(
            {
                **acc._cfg,
                "buy_price_type": "next_day_open",
                "max_positions": 5,
                "position_size_pct": 0.2,
                "min_cash_reserve": 100,
            },
            f,
        )
    acc.load_state()
    recs = [
        {"symbol": "600001", "name": "A", "style_bucket": "龙头", "buy_reason": "t"},
    ]
    prices = {"600001": 10.0}
    acc.execute_daily_trades(
        recs,
        "20260110",
        lambda s: price_from_map(prices, s),
    )
    pf = pending_buys_file(acc.project_root, "20260110")
    assert os.path.isfile(pf)
    os.remove(pf)


def test_recommendations_from_top_pool():
    def _tb(tag: str) -> str:
        return "龙头" if "人气" in tag else "其他"

    tp = [{"code": "000001", "name": "X", "tag": "人气龙头"}]
    r = recommendations_from_top_pool(tp, tag_to_bucket_func=_tb)
    assert r[0]["symbol"] == "000001"
    assert r[0]["style_bucket"] == "龙头"
