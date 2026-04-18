# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

from app.services.lb_primary_data import (
    lb_concept_flow_rank,
    lb_north_money_yi,
    lb_rise_fall_counts,
    lb_sector_rank_top,
)


def test_lb_rise_fall_counts_parses():
    with patch(
        "app.services.lb_primary_data.lb_get_safe",
        return_value={"rise_count": 100, "fall_count": 200},
    ), patch(
        "app.services.lb_primary_data.is_lb_openclaw_enabled",
        return_value=True,
    ):
        assert lb_rise_fall_counts("20260418") == (100, 200)


def test_lb_rise_fall_counts_disabled():
    with patch(
        "app.services.lb_primary_data.is_lb_openclaw_enabled",
        return_value=False,
    ):
        assert lb_rise_fall_counts("20260418") == (None, None)


def test_lb_sector_rank_top_builds_df():
    raw = [
        {"name": "半导体", "changePercent": 3.1, "limitUpNum": 5},
        {"name": "银行", "changePercent": 0.5, "limitUpNum": 1},
    ]
    with patch(
        "app.services.lb_primary_data.lb_get_safe",
        return_value=raw,
    ), patch(
        "app.services.lb_primary_data.is_lb_openclaw_enabled",
        return_value=True,
    ):
        df = lb_sector_rank_top("20260418", top_n=2)
        assert df is not None
        assert len(df) == 2
        assert "sector" in df.columns


def test_lb_north_from_dict():
    with patch(
        "app.services.lb_primary_data.lb_get_safe",
        return_value={"north_money": 12.34},
    ), patch(
        "app.services.lb_primary_data.is_lb_openclaw_enabled",
        return_value=True,
    ):
        out = lb_north_money_yi("20260418")
        assert out is not None
        assert out[0] == 12.34


def test_lb_concept_rank():
    raw = [
        {"name": "人工智能", "z_t_num": 10, "pct_chg": 2.0},
    ]
    with patch(
        "app.services.lb_primary_data.lb_get_safe",
        return_value=raw,
    ), patch(
        "app.services.lb_primary_data.is_lb_openclaw_enabled",
        return_value=True,
    ):
        df = lb_concept_flow_rank("20260418", top_n=5)
        assert df is not None and len(df) == 1
