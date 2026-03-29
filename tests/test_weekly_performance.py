"""周度收益：交易日与周内卖出日逻辑（不访问行情）。"""
from app.services.weekly_performance import (
    entry_exit_for_signal,
    first_trade_day_after,
    last_trade_day_on_or_before,
)


def test_first_trade_day_after():
    td = ["20260323", "20260324", "20260325", "20260326", "20260327"]
    assert first_trade_day_after("20260324", td) == "20260325"


def test_entry_exit_same_week():
    td = ["20260323", "20260324", "20260325", "20260326", "20260327"]
    e, x = entry_exit_for_signal("20260324", td)
    assert e == "20260325"
    assert x == "20260327"


def test_last_trade_before_cap():
    td = ["20260324", "20260325", "20260326", "20260327"]
    assert last_trade_day_on_or_before(td, "20260326") == "20260326"
