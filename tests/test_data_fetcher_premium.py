# -*- coding: utf-8 -*-
from app.services.data_fetcher import DataFetcher


def test_get_yest_zt_premium_returns_missing_when_spot_unmatched():
    f = DataFetcher()
    f.get_trade_cal = lambda: ["20260420", "20260421"]

    class _DF:
        empty = False

        def __getitem__(self, key):
            if key == "code":
                class _S:
                    @staticmethod
                    def tolist():
                        return ["000001", "000002"]

                return _S()
            raise KeyError(key)

    f.get_zt_pool = lambda _date: _DF()
    f._pct_chg_for_codes_on_date = lambda _codes, _date: []
    f._yest_premium_from_full_spot = lambda _codes: None

    premium, note = f.get_yest_zt_premium("20260421", ["20260420", "20260421"])
    assert premium == -99.0
    assert note == "无匹配数据"
