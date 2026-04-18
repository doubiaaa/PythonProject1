# -*- coding: utf-8 -*-
"""六维复盘框架：纯函数与 Markdown 结构烟测。"""
from __future__ import annotations

import pandas as pd

from app.services.replay_six_pillar import (
    build_six_pillar_framework_markdown,
    _PHASE_TO_CYCLE_NAME,
)


class _FakeFetcher:
    def get_stock_zh_a_spot_em_cached(self):
        return pd.DataFrame(
            {
                "涨跌幅": [6.0, -6.0, 1.0, -1.0],
            }
        )

    def _spot_turnover_rise_rate_flat(self):
        return 12000.0, 48.0, 10


def test_phase_mapping_covers_four_phases():
    assert len(_PHASE_TO_CYCLE_NAME) == 4


def test_build_six_pillar_contains_tables_and_checklist():
    fz = _FakeFetcher()
    fz._last_big_face_count = 3
    fz._last_premium_analysis = {"display_line": "+1.2%（示例）"}

    df_zt = pd.DataFrame(
        {
            "lb": [1, 2, 3],
            "industry": ["半导体", "半导体", "医药"],
            "封板资金": [1e8, 2e8, 3e8],
        }
    )

    md = build_six_pillar_framework_markdown(
        fz,
        date="20260417",
        trade_days=["20260417"],
        zt_count=3,
        dt_count=1,
        zb_count=2,
        zhaban_rate=30.0,
        up_n=2000,
        down_n=2500,
        north_money=12.3,
        north_status="ok",
        sentiment_temp=45,
        market_phase="主升期",
        position_suggestion="50%～70%",
        df_zt=df_zt,
    )

    assert "## 【六维复盘框架】" in md
    assert "| **赚钱效应** |" in md
    assert "涨幅>5%" in md
    assert "- [ ]" in md
    assert "主升期" in md
