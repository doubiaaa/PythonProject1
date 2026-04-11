# -*- coding: utf-8 -*-
"""市场摘要：将 DataFetcher 收口为 MarketSummaryPort，供编排层只依赖抽象。"""

from __future__ import annotations

from typing import Any

from app.domain.ports import MarketSummaryPort


class DataFetcherMarketSummaryAdapter:
    """包装实现 `get_market_summary(date) -> (md, actual_date)` 的拉数对象。"""

    __slots__ = ("_fetcher",)

    def __init__(self, fetcher: Any) -> None:
        self._fetcher = fetcher

    def fetch_summary(self, date: str) -> tuple[str, str]:
        return self._fetcher.get_market_summary(date)


def market_summary_port_from_fetcher(fetcher: Any) -> MarketSummaryPort:
    return DataFetcherMarketSummaryAdapter(fetcher)
