# -*- coding: utf-8 -*-
from __future__ import annotations


from app.services.lb_openclaw_pools import (
    ladder_to_zt_dataframe,
    stocks_to_dt_or_zb_df,
)


def test_ladder_to_zt_flattens_boards():
    payload = {
        "dates": [
            {
                "boards": [
                    {
                        "level": 2,
                        "stocks": [
                            {
                                "code": "600000",
                                "name": "浦发",
                                "latest": 10.0,
                                "change_rate": 9.98,
                                "open_num": 0,
                                "first_limit_up_time": "09:31:00",
                                "last_limit_up_time": "14:55:00",
                                "reason_type": "测试",
                                "industry": "银行",
                                "continue_num": 2,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    df = ladder_to_zt_dataframe(payload)
    assert len(df) == 1
    assert df.iloc[0]["code"] == "600000"
    assert int(df.iloc[0]["lb"]) == 2


def test_stocks_broken_limit():
    raw = {"stocks": [{"code": "000001", "name": "AAA"}], "total": 1}
    df = stocks_to_dt_or_zb_df(raw)
    assert len(df) == 1
    assert df.iloc[0]["name"] == "AAA"


def test_stocks_nested_data():
    raw = {"data": {"stocks": [{"code": "300001", "name": "B"}], "total": 1}}
    df = stocks_to_dt_or_zb_df(raw)
    assert len(df) == 1
