from __future__ import annotations

import pandas as pd

from app.services.replay_rule_engine import (
    ReplayRuleConfig,
    _analyze_stock,
    _is_first_breakout,
    render_replay_rule_markdown,
)
from app.utils.email_template import build_next_day_alert_html


def _make_df(closes: list[float], highs: list[float], lows: list[float], vols: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "trade_date": [f"202601{(i+1):02d}" for i in range(n)],
            "open_v": closes,
            "high_v": highs,
            "low_v": lows,
            "close_v": closes,
            "vol_v": vols,
        }
    )


def test_first_breakout_true_when_no_prior_break():
    cfg = ReplayRuleConfig(first_breakout_lookback=6, consolidate_days=3)
    closes = [10, 10.1, 10.2, 10.25, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55, 10.6, 10.9]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    vols = [100] * 11 + [250]
    df = _make_df(closes, highs, lows, vols)
    assert _is_first_breakout(df, cfg) is True


def test_first_breakout_false_when_prior_break_exists():
    cfg = ReplayRuleConfig(first_breakout_lookback=6, consolidate_days=3)
    # day4 already breaks above day1-3 platform, so last signal is not "first breakout"
    closes = [9.0, 9.0, 9.0, 9.0, 10.0, 10.0, 10.0, 10.8, 10.2, 10.2, 10.2, 10.2, 10.2, 10.55]
    highs = [c + 0.02 for c in closes]
    lows = [c - 0.1 for c in closes]
    vols = [100] * (len(closes) - 1) + [260]
    df = _make_df(closes, highs, lows, vols)
    assert _is_first_breakout(df, cfg) is False


def test_analyze_stock_breakout_boundary_requires_strictly_above():
    cfg = ReplayRuleConfig(consolidate_days=3, ma_short=3, ma_mid=4, ma_long=5, volume_surge_ratio=1.5)
    closes = [9.8, 9.9, 10.0, 10.1, 10.2, 10.3, 10.4, 10.5]
    highs = [9.9, 10.0, 10.1, 10.2, 10.3, 10.45, 10.5, 10.5]  # last == platform_high
    lows = [9.7, 9.8, 9.9, 10.0, 10.1, 10.2, 10.3, 10.4]
    vols = [100, 100, 100, 100, 100, 110, 120, 220]
    df = _make_df(closes, highs, lows, vols)
    out = _analyze_stock(df, cfg)
    assert out["breakout_today"] is False
    assert out["volume_surge"] is True


def test_next_day_alert_html_renders_when_alerts_exist():
    html = build_next_day_alert_html(
        {
            "market_ok": True,
            "strong_sectors": ["人工智能"],
            "alerts_for_tomorrow": [
                {
                    "name": "测试中军",
                    "code": "000001",
                    "trigger_price": 11.31,
                    "require_sector_rise": 0.5,
                    "stop_loss": 10.8,
                    "sector": "人工智能",
                }
            ]
        }
    )
    assert "明日条件单" in html
    assert "000001" in html
    assert "11.31" in html
    assert "可执行" in html
    assert "可执行 1 条" in html
    assert "不可执行 0 条" in html
    assert "大盘阻塞 0 条，板块阻塞 0 条" in html


def test_next_day_alert_html_marks_blocked_when_market_not_ok():
    html = build_next_day_alert_html(
        {
            "market_ok": False,
            "strong_sectors": ["人工智能"],
            "alerts_for_tomorrow": [
                {
                    "name": "测试中军",
                    "code": "000001",
                    "trigger_price": 11.31,
                    "require_sector_rise": 0.5,
                    "stop_loss": 10.8,
                    "sector": "人工智能",
                }
            ],
        }
    )
    assert "不可执行" in html
    assert "大盘过滤未通过" in html
    assert "不可执行 1 条" in html
    assert "大盘阻塞 1 条，板块阻塞 0 条" in html


def test_markdown_render_includes_alert_summary_breakdown():
    md = render_replay_rule_markdown(
        {
            "date": "20260421",
            "market_ok": True,
            "market_reason": "ok",
            "strong_sectors": ["人工智能"],
            "watch_list": [],
            "buy_signals_today": [],
            "alerts_for_tomorrow": [
                {
                    "name": "可执行A",
                    "code": "000001",
                    "trigger_price": 10.1,
                    "require_sector_rise": 0.5,
                    "require_volume_surge": 1.5,
                    "stop_loss": 9.8,
                    "sector": "人工智能",
                },
                {
                    "name": "阻塞B",
                    "code": "000002",
                    "trigger_price": 12.2,
                    "require_sector_rise": 0.5,
                    "require_volume_surge": 1.5,
                    "stop_loss": 11.7,
                    "sector": "消费",
                },
            ],
            "position_actions": [],
        }
    )
    assert "明日条件单汇总" in md
    assert "可执行 **1** 条 / 不可执行 **1** 条" in md
    assert "大盘阻塞 **0** 条，板块阻塞 **1** 条" in md

