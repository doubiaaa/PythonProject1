# -*- coding: utf-8 -*-
"""从 DataFetcher / KPI 抽取可与正文对照的参照事实（程序口径）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ReferenceFacts:
    """用于事实校验的量化参照（缺失项不参与比对）。"""

    trade_date: str
    market_phase: str = ""
    zt_count: Optional[int] = None
    dt_count: Optional[int] = None
    zb_count: Optional[int] = None
    zhaban_rate: Optional[float] = None  # 0~1 或 0~100 由 normalize 处理
    premium_pct: Optional[float] = None
    north_net: Optional[float] = None
    raw_kpi: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_data_fetcher(cls, data_fetcher: Any, actual_date: str) -> "ReferenceFacts":
        kpi: dict[str, Any] = {}
        raw = getattr(data_fetcher, "_last_email_kpi", None) or {}
        if isinstance(raw, dict):
            kpi = dict(raw)

        def _i(key: str) -> Optional[int]:
            v = kpi.get(key)
            if v is None:
                return None
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None

        def _f(key: str) -> Optional[float]:
            v = kpi.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        zh = _f("zhaban_rate")
        if zh is not None and zh > 1.0:
            zh = zh / 100.0

        phase = str(getattr(data_fetcher, "_last_market_phase", "") or "").strip()

        return cls(
            trade_date=str(actual_date)[:8],
            market_phase=phase,
            zt_count=_i("zt_count"),
            dt_count=_i("dt_count"),
            zb_count=_i("zb_count") or _i("zhaban_count"),
            zhaban_rate=zh,
            premium_pct=_f("premium"),
            north_net=_f("north_net") or _f("north_money"),
            raw_kpi=kpi,
        )

    def as_compact_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"trade_date": self.trade_date}
        if self.market_phase:
            d["market_phase"] = self.market_phase
        if self.zt_count is not None:
            d["zt_count"] = self.zt_count
        if self.dt_count is not None:
            d["dt_count"] = self.dt_count
        if self.zb_count is not None:
            d["zb_count"] = self.zb_count
        if self.zhaban_rate is not None:
            d["zhaban_rate"] = round(self.zhaban_rate, 4)
        if self.premium_pct is not None:
            d["premium_pct"] = round(self.premium_pct, 4)
        if self.north_net is not None:
            d["north_net"] = self.north_net
        return d
