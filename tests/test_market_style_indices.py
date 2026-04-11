"""风格指数：周涨跌计算逻辑（mock 行情，不访问网络）。"""
from unittest.mock import MagicMock

import pandas as pd

from app.services.market_style_indices import weekly_return_qfq


def test_weekly_return_qfq_basic():
    week_days = ["20260106", "20260107", "20260108"]
    fake_df = pd.DataFrame(
        {
            "日期": ["2026-01-06", "2026-01-07", "2026-01-08"],
            "开盘": [10.0, 10.5, 11.0],
            "收盘": [10.2, 10.8, 11.5],
        }
    )
    fetcher = MagicMock()
    fetcher.fetch_with_retry.return_value = fake_df
    r = weekly_return_qfq("600000", week_days, fetcher)
    assert r is not None
    assert abs(r - (11.5 - 10.0) / 10.0 * 100) < 0.01
