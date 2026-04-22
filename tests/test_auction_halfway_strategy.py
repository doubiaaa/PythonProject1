# -*- coding: utf-8 -*-
import pandas as pd

from app.services.auction_halfway_strategy import _lb_fallback_top_pool, _sector_hist_for_range


def test_lb_fallback_top_pool_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.lb_openclaw_client.is_lb_openclaw_enabled",
        lambda: False,
    )
    main, pool = _lb_fallback_top_pool("20260422", max_main=3, max_pool=5)
    assert main == []
    assert pool == []


def test_lb_fallback_top_pool_parses_hot_sectors(monkeypatch):
    monkeypatch.setattr(
        "app.services.lb_openclaw_client.is_lb_openclaw_enabled",
        lambda: True,
    )

    def _fake_lb_get_safe(path, params=None, timeout=None):
        assert path == "/hot-sectors"
        return [
            {
                "name": "机器人",
                "stocks": [
                    {
                        "code": "300123",
                        "name": "测试A",
                        "continueNum": 3,
                        "changePercent": 9.91,
                        "turnoverRate": 12.5,
                        "price": 23.45,
                    },
                    {
                        "code": "600111",
                        "name": "测试B",
                        "continueNum": 2,
                        "changePercent": 6.21,
                        "turnoverRate": 8.3,
                        "price": 10.01,
                    },
                ],
            }
        ]

    monkeypatch.setattr(
        "app.services.lb_openclaw_client.lb_get_safe",
        _fake_lb_get_safe,
    )
    main, pool = _lb_fallback_top_pool("20260422", max_main=3, max_pool=5)
    assert main == ["机器人"]
    assert len(pool) == 2
    assert pool[0]["code"] == "300123"
    assert pool[0]["tag"] == "悟道回退候选"


def test_sector_hist_for_range_retries(monkeypatch):
    calls = {"n": 0}

    def _fake_hist(**kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("temporary")
        return pd.DataFrame(
            {
                "日期": ["2026-04-21", "2026-04-22"],
                "涨跌幅": ["1.2", "2.3"],
                "成交额": ["100000000", "120000000"],
            }
        )

    monkeypatch.setattr(
        "app.services.auction_halfway_strategy.ak.stock_board_industry_hist_em",
        _fake_hist,
    )
    df = _sector_hist_for_range("机器人", "20260401", "20260422")
    assert df is not None and not df.empty
    assert calls["n"] >= 2
