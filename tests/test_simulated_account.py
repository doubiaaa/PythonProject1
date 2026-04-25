# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import simulated_account as sa


def test_next_prev_trade_day():
    td = ["20260101", "20260102", "20260105"]
    assert sa._next_trade_day(td, "20260102") == "20260105"
    assert sa._trade_day_index(td, "20260105") == 2


def test_plan_exit_keyword():
    txt = "### 七、明日预案\n\n- **测试股（600000）**：不及预期则**止盈**离场。\n"
    assert sa._plan_suggests_exit_for_stock(txt, "600000", "测试股")


def test_roundtrip_buy_then_stop_loss(tmp_path):
    p = tmp_path / "sim.json"
    with patch.object(sa, "_state_path", return_value=str(p)):
        with patch.object(
            sa,
            "_load_config",
            return_value=(True, 50_000.0, 2, 0.0, 0.05, 0.08, 15),
        ):
            td = ["20260101", "20260102", "20260105", "20260106"]
            pool = [{"code": "600000", "name": "浦发", "score": 90.0}]
            sa.schedule_next_buys("20260101", td, pool)
            with patch.object(sa, "_fetch_daily_ohlc", return_value={"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1}):
                r = sa.process_session_opens(None, "20260102", td)
            assert len(r.get("buys") or []) == 1

            sa.save_signal_report("20260101", "预案正文")
            with patch.object(sa, "_fetch_daily_ohlc", return_value={"open": 10.0, "high": 10.1, "low": 8.0, "close": 9.5}):
                ev = sa.evaluate_exits_after_close("20260102", td)
            assert len(ev.get("scheduled") or []) == 1

            with patch.object(sa, "_fetch_daily_ohlc", return_value={"open": 9.0, "high": 9.2, "low": 8.9, "close": 9.1}):
                r2 = sa.process_session_opens(None, "20260105", td)
            assert len(r2.get("sells") or []) == 1


def test_prepend_simulation_before_body():
    fake = {
        "version": 2,
        "initial_cash": 50_000,
        "cash": 50_000,
        "positions": [],
        "pending_sells": [],
        "scheduled_buys": [],
        "signal_reports": {},
        "trades": [],
        "daily_snapshots": [],
    }
    with patch.object(sa, "load_state", return_value=fake):
        with patch.object(
            sa,
            "_load_config",
            return_value=(True, 50_000.0, 5, 0.02, 0.05, 0.08, 15),
        ):
            with patch.object(
                sa,
                "build_trade_display_summary",
                return_value={
                    "today_mkt": 50_000.0,
                    "today_gain": 0.0,
                    "cum_pnl": 0.0,
                    "cum_pct": 0.0,
                },
            ):
                with patch(
                    "app.services.trade_display_ths_image.write_trade_display_png",
                    return_value=None,
                ):
                    out = sa.prepend_simulation_to_report_body(
                        "## 复盘正文\n\n段落", "20260103"
                    )
    assert out.index("【实盘交易展示】") < out.index("复盘正文")


def test_markdown_title():
    fake = {
        "version": 2,
        "initial_cash": 50_000,
        "cash": 25_000,
        "positions": [],
        "pending_sells": [],
        "scheduled_buys": [],
        "signal_reports": {},
        "trades": [],
        "daily_snapshots": [],
    }
    with patch.object(sa, "load_state", return_value=fake):
        with patch.object(
            sa,
            "_load_config",
            return_value=(True, 50_000.0, 5, 0.02, 0.05, 0.08, 15),
        ):
            md = sa.build_simulated_account_markdown("20260103")
    assert "【实盘交易展示】" in md
    assert "模拟" not in md


def test_markdown_embeds_image_when_path_given():
    fake = {
        "version": 2,
        "initial_cash": 50_000,
        "cash": 40_000,
        "positions": [],
        "pending_sells": [],
        "scheduled_buys": [],
        "signal_reports": {},
        "trades": [],
        "daily_snapshots": [],
    }
    with patch.object(sa, "load_state", return_value=fake):
        with patch.object(
            sa,
            "_load_config",
            return_value=(True, 50_000.0, 5, 0.02, 0.05, 0.08, 15),
        ):
            md = sa.build_simulated_account_markdown(
                "20260103",
                image_rel="data/trade_display/20260103.png",
                summary={
                    "today_mkt": 51_000.0,
                    "today_gain": 100.0,
                    "cum_pnl": 1_000.0,
                    "cum_pct": 2.0,
                },
            )
    assert "data/trade_display/20260103.png" in md
    assert "当日日线收盘价" in md
    assert "今日收益：" in md and "+100.00" in md
    assert "实盘至今收益：" in md
    assert "实盘至今收益率：" in md
    assert "### 当前持仓" not in md


@pytest.mark.filterwarnings(
    "ignore:Glyph .* missing from font\\(s\\) DejaVu Sans\\.:UserWarning"
)
def test_write_trade_display_png_file(tmp_path, monkeypatch):
    from matplotlib import font_manager as fm

    from app.services import trade_display_ths_image as tdi

    fake = {
        "version": 2,
        "initial_cash": 50_000,
        "cash": 30_000,
        "positions": [
            {
                "code": "600000",
                "name": "浦发",
                "qty": 1000,
                "buy_price": 10.0,
                "buy_date": "20260102",
                "signal_date": "20260101",
            }
        ],
        "pending_sells": [],
        "scheduled_buys": [],
        "signal_reports": {},
        "trades": [],
        "daily_snapshots": [],
    }
    p = tmp_path / "sim.json"
    p.write_text(__import__("json").dumps(fake, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sa, "_state_path", lambda: str(p))
    monkeypatch.setattr(tdi, "_trade_display_dir", lambda: str(tmp_path / "trade_display"))
    monkeypatch.setattr(
        tdi, "_pick_cjk_font", lambda: fm.FontProperties(family="DejaVu Sans")
    )
    with patch.object(sa, "_fetch_daily_ohlc", return_value={"close": 10.5}):
        rel = tdi.write_trade_display_png("20260110")
    assert rel is not None
    out = tmp_path / "trade_display" / "20260110.png"
    assert out.is_file()
