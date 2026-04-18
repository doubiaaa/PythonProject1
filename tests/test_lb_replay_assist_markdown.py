# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

from app.services.lb_replay_assist_markdown import build_lb_openclaw_assist_section


def _calendar():
    return {"isTradingDay": True, "prev_trade_date": "20260417"}


def _overview():
    return {
        "rise_count": 3000,
        "fall_count": 1500,
        "limit_up_count": 50,
        "limit_down_count": 10,
        "limit_up_broken_count": 20,
        "limit_up_broken_ratio": "12%",
        "yesterday_limit_up_avg_pcp": 1.2,
        "market_temperature": "温",
    }


def test_build_section_empty_when_no_data():
    with patch(
        "app.services.lb_replay_assist_markdown.lb_get_safe",
        return_value=None,
    ):
        assert build_lb_openclaw_assist_section("20260418", ["20260417", "20260418"]) == ""


def test_build_section_with_overview_and_calendar():
    def fake_get(path, params=None, timeout=None):
        if path == "/trading-calendar":
            return _calendar()
        if path == "/market-overview":
            return _overview()
        return None

    with patch(
        "app.services.lb_replay_assist_markdown.lb_get_safe",
        side_effect=fake_get,
    ):
        md = build_lb_openclaw_assist_section("20260418", ["20260417", "20260418"])
    assert "【悟道 OpenClaw · 扩展数据】" in md
    assert "交易日历" in md
    assert "市场概况" in md
    assert "3000" in md


def test_invalid_date_returns_empty():
    assert build_lb_openclaw_assist_section("bad", []) == ""
