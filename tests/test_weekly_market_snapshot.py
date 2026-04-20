# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.weekly_market_snapshot import format_snapshot_markdown, snapshot_one_day


def test_snapshot_one_day_prefers_wudao_when_key_present():
    fetcher = MagicMock()
    fetcher.get_zt_pool = MagicMock(
        return_value=pd.DataFrame([{"code": "000001", "lb": 1, "industry": "银行"}])
    )
    fetcher.get_dt_pool = MagicMock(return_value=pd.DataFrame())
    fetcher.get_zb_pool = MagicMock(return_value=pd.DataFrame())
    fetcher.get_yest_zt_premium = MagicMock(return_value=(1.2, "ok"))

    zt_df = pd.DataFrame(
        [
            {
                "code": "600000",
                "lb": 2,
                "industry": "证券",
            }
        ]
    )
    with patch("app.utils.config.ConfigManager") as cm_cls:
        cm_cls.return_value.get.side_effect = lambda k, d=None: {
            "weekly_snapshot_use_lb_limit_pools": True,
            "weekly_snapshot_lb_fallback_ak": True,
        }.get(k, d)
        with patch(
            "app.services.lb_openclaw_client.get_lb_api_key", return_value="k"
        ):
            with patch(
                "app.services.lb_openclaw_pools.fetch_zt_pool_lb", return_value=zt_df
            ):
                with patch(
                    "app.services.lb_openclaw_pools.fetch_dt_pool_lb",
                    return_value=pd.DataFrame([{"code": "000002", "name": "b"}]),
                ):
                    with patch(
                        "app.services.lb_openclaw_pools.fetch_zb_pool_lb",
                        return_value=pd.DataFrame(),
                    ):
                        row = snapshot_one_day(
                            fetcher, "20260417", ["20260415", "20260416", "20260417"]
                        )
    assert row["pool_source"] == "wudao_lb"
    assert row["zt_n"] == 1
    assert row["dt_n"] == 1
    assert row["zb_n"] == 0
    fetcher.get_zt_pool.assert_not_called()


def test_snapshot_one_day_falls_back_when_lb_all_empty():
    fetcher = MagicMock()
    fetcher.get_zt_pool = MagicMock(
        return_value=pd.DataFrame([{"code": "000001", "lb": 1, "industry": "银行"}])
    )
    fetcher.get_dt_pool = MagicMock(return_value=pd.DataFrame())
    fetcher.get_zb_pool = MagicMock(return_value=pd.DataFrame())
    fetcher.get_yest_zt_premium = MagicMock(return_value=(-99.0, "x"))

    with patch("app.utils.config.ConfigManager") as cm_cls:
        cm_cls.return_value.get.side_effect = lambda k, d=None: {
            "weekly_snapshot_use_lb_limit_pools": True,
            "weekly_snapshot_lb_fallback_ak": True,
        }.get(k, d)
        with patch(
            "app.services.lb_openclaw_client.get_lb_api_key", return_value="k"
        ):
            with patch(
                "app.services.lb_openclaw_pools.fetch_zt_pool_lb",
                return_value=pd.DataFrame(),
            ):
                with patch(
                    "app.services.lb_openclaw_pools.fetch_dt_pool_lb",
                    return_value=pd.DataFrame(),
                ):
                    with patch(
                        "app.services.lb_openclaw_pools.fetch_zb_pool_lb",
                        return_value=pd.DataFrame(),
                    ):
                        row = snapshot_one_day(fetcher, "20260417", ["20260417"])
    assert row["pool_source"] == "akshare_fallback"
    assert row["zt_n"] == 1
    fetcher.get_zt_pool.assert_called_once()


def test_format_snapshot_shows_wudao_note():
    snap = {
        "daily": [
            {
                "date": "20260417",
                "zt_n": 50,
                "dt_n": 2,
                "zb_n": 3,
                "zhaban_rate": 5.0,
                "premium": 1.0,
                "premium_note": "",
                "max_lb": 5,
                "top3_zt_industry": "",
                "pool_source": "wudao_lb",
            }
        ],
        "trade_days": ["20260417"],
        "anchor_date": "20260417",
    }
    md = format_snapshot_markdown(snap)
    assert "悟道 OpenClaw" in md
    assert "/ladder" in md
