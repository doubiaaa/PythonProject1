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


def test_get_yest_zt_premium_uses_partial_hist_sample():
    f = DataFetcher()
    f.get_trade_cal = lambda: ["20260420", "20260421"]

    class _DF:
        empty = False

        def __getitem__(self, key):
            if key == "code":
                class _S:
                    @staticmethod
                    def tolist():
                        return ["000001", "000002", "000003", "000004"]

                return _S()
            raise KeyError(key)

    f.get_zt_pool = lambda _date: _DF()
    f._pct_chg_for_codes_on_date = lambda _codes, _date: [2.0]
    f._yest_premium_from_full_spot = lambda _codes: None

    premium, note = f.get_yest_zt_premium("20260421", ["20260420", "20260421"])
    assert premium == 2.0
    assert note == "样本偏少(1/4)"


def test_compute_big_face_count_refills_missing_from_hist():
    f = DataFetcher()

    class _DFZT:
        empty = False

        def __getitem__(self, key):
            if key == "code":
                class _S:
                    @staticmethod
                    def tolist():
                        return ["000001", "000002", "000003"]

                return _S()
            raise KeyError(key)

    class _DFDT:
        empty = True
        columns = []

    f.get_zt_pool = lambda _date: _DFZT()
    f._pct_map_for_codes_on_date = (
        lambda codes, _date: {codes[0]: -6.2}
        if len(codes) == 3
        else {codes[0]: -5.5, codes[1]: -5.1}
    )
    f._pct_map_from_spot_for_codes = lambda _codes: {}

    n = f.compute_big_face_count("20260421", ["20260420", "20260421"], _DFDT())
    assert n == 3


def test_get_yest_zt_premium_prefers_market_overview():
    f = DataFetcher()
    f.get_trade_cal = lambda: ["20260420", "20260421"]

    class _DF:
        empty = False

        def __getitem__(self, key):
            if key == "code":
                class _S:
                    @staticmethod
                    def tolist():
                        return ["000001"]

                return _S()
            raise KeyError(key)

    f.get_zt_pool = lambda _date: _DF()
    f._yest_premium_from_market_overview = lambda _date: 1.23
    f._yest_premium_from_lb = lambda _d: None
    f._pct_chg_for_codes_on_date = lambda _codes, _date: [9.99]
    premium, note = f.get_yest_zt_premium("20260421", ["20260420", "20260421"])
    assert premium == 1.23
    assert note == "悟道总览"


def test_get_yest_zt_premium_uses_market_overview_even_if_zt_empty():
    f = DataFetcher()
    f.get_trade_cal = lambda: ["20260420", "20260421"]

    class _EmptyDF:
        empty = True

    f.get_zt_pool = lambda _date: _EmptyDF()
    f._yest_premium_from_market_overview = lambda _date: 0.88

    premium, note = f.get_yest_zt_premium("20260421", ["20260420", "20260421"])
    assert premium == 0.88
    assert note == "悟道总览"
