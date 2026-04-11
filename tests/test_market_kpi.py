"""market_kpi：昨日涨停溢价相对近 5 日序列的展示与分档。"""

import pytest

from app.services.market_kpi import _band_vs_mean, premium_analysis


class _FakeFetcher:
    """按日期返回预设溢价，用于单元测试。"""

    def __init__(self, by_date: dict[str, tuple[float, str]]):
        self._by_date = by_date

    def get_yest_zt_premium(self, date, trade_days=None):
        ds = str(date)[:8]
        return self._by_date.get(ds, (-99.0, "无数据"))


def test_band_vs_mean():
    assert _band_vs_mean(0.0) == 0.4
    assert _band_vs_mean(10.0) == pytest.approx(1.2)


def test_premium_analysis_percentile_and_display():
    days = [
        "20240102",
        "20240103",
        "20240104",
        "20240105",
        "20240108",
        "20240109",
        "20240110",
    ]
    # 前 5 个交易日（相对 20240110）：0104～0109 共 5 日（0102,0103 不在窗口内）
    # idx of 20240110 = 6, past_days = days[1:6] = 0103～0109
    by_date = {
        "20240103": (1.0, "正常"),
        "20240104": (1.0, "正常"),
        "20240105": (1.0, "正常"),
        "20240108": (1.0, "正常"),
        "20240109": (2.0, "正常"),
    }
    fx = _FakeFetcher(by_date)
    out = premium_analysis(2.11, "正常", "20240110", days, fx)
    assert out["mean_5"] == 1.2
    assert out["past_sample_n"] == 5
    assert out["rating"] == "偏高"
    assert "高于均值" in out["display_line"]
    assert "历史分位" in out["display_line"]


def test_premium_analysis_unavailable():
    out = premium_analysis(-99.0, "昨日无涨停", "20240110", ["20240110"], _FakeFetcher({}))
    assert out["rating"] == "不可用"
    assert "昨日无涨停" in out["display_line"]
