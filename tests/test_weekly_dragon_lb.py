# -*- coding: utf-8 -*-
"""悟道梯队补全：龙头池明细 / 近四周与 resolve_week_dragon_records。"""
from unittest.mock import patch

import pandas as pd

from app.services.weekly_performance import (
    _merge_dragon_by_signal_date_code,
    resolve_week_dragon_records,
    synthetic_lb_ladder_records_for_iso_week,
)


def test_merge_prefers_local_over_lb():
    local = [
        {
            "signal_date": "20260415",
            "code": "000001",
            "name": "A",
            "rank": 1,
            "score": 1.0,
            "sector": "x",
            "tag": "程序",
        }
    ]
    lb = [
        {
            "signal_date": "20260415",
            "code": "000001",
            "name": "B",
            "rank": 1,
            "score": 0.0,
            "sector": "y",
            "tag": "悟道·涨停梯队",
        },
        {
            "signal_date": "20260415",
            "code": "600000",
            "name": "C",
            "rank": 2,
            "score": 0.0,
            "sector": "",
            "tag": "悟道·涨停梯队",
        },
    ]
    m = _merge_dragon_by_signal_date_code(local, lb)
    by_code = {x["code"]: x for x in m}
    assert by_code["000001"]["tag"] == "程序"
    assert "600000" in by_code


def test_synthetic_lb_from_ladder_df():
    df = pd.DataFrame(
        [
            {"code": "000001", "name": "A", "lb": 2, "industry": "银行"},
            {"code": "600000", "name": "B", "lb": 3, "industry": "证券"},
        ]
    )
    with patch(
        "app.services.lb_openclaw_client.get_lb_api_key", return_value="k"
    ):
        with patch(
            "app.services.weekly_market_snapshot.trade_days_in_iso_week",
            return_value=["20260415"],
        ):
            with patch(
                "app.services.lb_openclaw_pools.fetch_zt_pool_lb", return_value=df
            ):
                out = synthetic_lb_ladder_records_for_iso_week(
                    ["20260415"], 2026, 16
                )
    assert len(out) == 2
    assert out[0]["code"] == "600000"
    assert out[1]["code"] == "000001"
    assert out[0]["tag"] == "悟道·涨停梯队"
    assert out[0]["signal_date"] == "20260415"


def test_resolve_when_watchlist_empty_uses_lb():
    with patch("app.utils.config.ConfigManager") as cm_cls:
        cm_cls.return_value.get.side_effect = lambda k, d=None: {
            "weekly_dragon_lb_mode": "when_watchlist_empty",
        }.get(k, d)
        with patch(
            "app.services.weekly_performance.load_all_records", return_value=[]
        ):
            with patch(
                "app.services.lb_openclaw_client.get_lb_api_key", return_value="k"
            ):
                with patch(
                    "app.services.weekly_performance.synthetic_lb_ladder_records_for_iso_week",
                    return_value=[
                        {
                            "signal_date": "20260415",
                            "code": "000001",
                            "name": "x",
                            "rank": 1,
                            "score": 0.0,
                            "sector": "",
                            "tag": "悟道·涨停梯队",
                        }
                    ],
                ):
                    recs, note = resolve_week_dragon_records(
                        2026, 16, ["20260415"]
                    )
    assert len(recs) == 1
    assert "悟道" in note


def test_resolve_off_uses_local_only():
    with patch("app.utils.config.ConfigManager") as cm_cls:
        cm_cls.return_value.get.side_effect = lambda k, d=None: {
            "weekly_dragon_lb_mode": "off",
        }.get(k, d)
        with patch(
            "app.services.weekly_performance.load_all_records",
            return_value=[
                {
                    "signal_date": "20260415",
                    "code": "000001",
                    "name": "x",
                    "rank": 1,
                    "score": 1.0,
                    "sector": "",
                    "tag": "",
                }
            ],
        ):
            recs, _ = resolve_week_dragon_records(2026, 16, ["20260415"])
    assert len(recs) == 1
