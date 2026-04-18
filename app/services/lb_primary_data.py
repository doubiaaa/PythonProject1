# -*- coding: utf-8 -*-
"""
悟道 OpenClaw 优先取数：与 data_fetcher 中 akshare 互补。
失败返回 None / 空表，由调用方回退东财 akshare。

说明：全市场交易日历暂无单次拉全量接口，get_trade_cal 仍以 akshare 为主。
"""
from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from app.services.lb_openclaw_client import lb_get_safe, is_lb_openclaw_enabled
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _ds8(date: Any) -> str:
    s = re.sub(r"\D", "", str(date))[:8]
    return s if len(s) == 8 else ""


def _iso(ds8: str) -> str:
    return f"{ds8[:4]}-{ds8[4:6]}-{ds8[6:8]}" if len(ds8) == 8 else ds8


def lb_rise_fall_counts(ds: str) -> tuple[Optional[int], Optional[int]]:
    """市场概况：上涨/下跌家数。失败 (None, None)。"""
    if not is_lb_openclaw_enabled():
        return None, None
    d8 = _ds8(ds)
    if len(d8) != 8:
        return None, None
    raw = lb_get_safe("/market-overview", {"date": _iso(d8)})
    if not isinstance(raw, dict):
        return None, None
    try:
        up = raw.get("rise_count")
        down = raw.get("fall_count")
        if up is None or down is None:
            return None, None
        return int(up), int(down)
    except (TypeError, ValueError):
        return None, None


def lb_north_money_yi(ds: str) -> Optional[tuple[float, str]]:
    """
    北向净流入（亿元）与状态。失败返回 None。
    解析 capital-flow flowType=hsgt 的常见字段。
    """
    if not is_lb_openclaw_enabled():
        return None
    d8 = _ds8(ds)
    if len(d8) != 8:
        return None
    raw = lb_get_safe(
        "/capital-flow",
        {"flowType": "hsgt", "date": _iso(d8), "limit": 30},
    )
    if raw is None:
        raw = lb_get_safe(
            "/capital-flow",
            {"flowType": "hsgt", "date": d8, "limit": 30},
        )
    if raw is None:
        return None

    def _pick_net(obj: dict[str, Any]) -> Optional[float]:
        for k in (
            "north_money",
            "northMoney",
            "net_mf_amount",
            "hsgt_net",
            "net_inflow",
            "value",
        ):
            v = obj.get(k)
            if v is None:
                continue
            try:
                x = float(v)
                # 若为元级大数，转亿元
                if abs(x) > 1e6:
                    x = x / 1e8
                return round(x, 2)
            except (TypeError, ValueError):
                continue
        return None

    if isinstance(raw, dict):
        v = _pick_net(raw)
        if v is not None:
            st = "ok_zero" if v == 0.0 else "ok"
            return v, st
    if isinstance(raw, list) and raw:
        for it in raw:
            if isinstance(it, dict):
                v = _pick_net(it)
                if v is not None:
                    st = "ok_zero" if v == 0.0 else "ok"
                    return v, st
    return None


def lb_sector_rank_top(ds: str, top_n: int = 5) -> Optional[pd.DataFrame]:
    """
    最强风口 → 内部列 sector, pct, money（money 用涨停家数作排序代理，非东财净流入额）。
    """
    if not is_lb_openclaw_enabled():
        return None
    d8 = _ds8(ds)
    if len(d8) != 8:
        return None
    raw = lb_get_safe("/hot-sectors", {"date": _iso(d8)})
    if raw is None:
        raw = lb_get_safe("/hot-sectors", {"date": d8})
    if not isinstance(raw, list):
        if isinstance(raw, dict):
            raw = raw.get("data") or raw.get("items")
        if not isinstance(raw, list):
            return None
    rows = []
    for sec in raw[: max(top_n * 2, 12)]:
        if not isinstance(sec, dict):
            continue
        name = sec.get("name") or sec.get("sector") or ""
        if not name:
            continue
        try:
            pct = float(sec.get("changePercent") or sec.get("pct") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        try:
            lu = float(sec.get("limitUpNum") or sec.get("limit_up_num") or 0.0)
        except (TypeError, ValueError):
            lu = 0.0
        rows.append(
            {
                "sector": str(name).strip(),
                "pct": pct,
                "money": lu,
            }
        )
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df = df.sort_values("money", ascending=False).head(top_n)
    _log.info("板块排名：已用悟道 hot-sectors（涨停家数为序，非东财主力净流入）")
    return df


def lb_concept_flow_rank(ds: str, top_n: int = 12) -> Optional[pd.DataFrame]:
    """概念涨幅/涨停排行 → sector, pct, money（money 用涨停数 z_t_num）。"""
    if not is_lb_openclaw_enabled():
        return None
    d8 = _ds8(ds)
    if len(d8) != 8:
        return None
    raw = lb_get_safe("/concepts/ranking", {"date": d8, "limit": max(30, top_n * 2)})
    if raw is None:
        raw = lb_get_safe("/concepts/ranking", {"date": _iso(d8), "limit": max(30, top_n * 2)})
    if not isinstance(raw, list):
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data")
        if not isinstance(raw, list):
            return None
    rows = []
    for it in raw[: top_n * 2]:
        if not isinstance(it, dict):
            continue
        name = it.get("name") or ""
        if not name:
            continue
        try:
            zt_n = float(it.get("z_t_num") or it.get("zt_num") or 0.0)
        except (TypeError, ValueError):
            zt_n = 0.0
        try:
            pct = float(it.get("pct_chg") or it.get("pct") or it.get("changePercent") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        rows.append({"sector": str(name).strip(), "pct": pct, "money": zt_n})
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("money", ascending=False).head(top_n)
    _log.info("概念资金流排行：已用悟道 concepts/ranking（列为涨停家数代理）")
    return df
