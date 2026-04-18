# -*- coding: utf-8 -*-
"""将悟道 OpenClaw 涨跌停相关 JSON 转为 DataFetcher 内部 DataFrame 列。"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.services.lb_openclaw_client import lb_get


def _norm_code(code: object) -> str:
    s = re.sub(r"[^0-9]", "", str(code or ""))[:6]
    return s.zfill(6) if len(s) == 6 else ""


def _unwrap_inner_data(payload: Any) -> dict[str, Any]:
    """broken-limit-up / limit-down 等：兼容 { data: { stocks } } 或 { stocks }。"""
    if not isinstance(payload, dict):
        return {}
    d = payload.get("data")
    if isinstance(d, dict) and "stocks" in d:
        return d
    if "stocks" in payload:
        return payload
    if isinstance(d, dict) and isinstance(d.get("data"), dict):
        return d["data"]
    return payload if isinstance(payload, dict) else {}


def ladder_to_zt_dataframe(payload: Any) -> pd.DataFrame:
    """
    /ladder 返回体 → 涨停池 DataFrame（列与 get_zt_pool 内部一致）。
    `lb_get` 已解包外层 `data` 时，payload 形如 `{ dates: [...] }`。
    """
    if not isinstance(payload, dict):
        return pd.DataFrame()
    data = payload
    if "dates" not in payload and isinstance(payload.get("data"), dict):
        data = payload["data"]
    if not isinstance(data, dict):
        return pd.DataFrame()
    dates = data.get("dates")
    if not isinstance(dates, list) or not dates:
        return pd.DataFrame()
    day0 = dates[0]
    boards = day0.get("boards") or []
    rows: list[dict[str, Any]] = []
    for b in boards:
        try:
            level = int(b.get("level") or 1)
        except Exception:
            level = 1
        level = max(1, level)
        for s in b.get("stocks") or []:
            if not isinstance(s, dict):
                continue
            code = _norm_code(s.get("code"))
            if not code:
                continue
            cnum = s.get("continue_num")
            try:
                lb = int(cnum) if cnum is not None else level
            except Exception:
                lb = level
            lb = max(1, lb)

            latest = s.get("latest")
            try:
                price = float(latest) if latest is not None else float("nan")
            except Exception:
                price = float("nan")

            pct = s.get("change_rate")
            try:
                pct_chg = float(pct) if pct is not None else 0.0
            except Exception:
                pct_chg = 0.0

            onum = s.get("openNum", s.get("open_num"))
            try:
                zb_count = int(onum) if onum is not None else 0
            except Exception:
                zb_count = 0

            ft = s.get("first_limit_up_time") or s.get("firstLimitUpTime") or ""
            lt = s.get("last_limit_up_time") or s.get("lastLimitUpTime") or ""
            ft = str(ft).replace("：", ":").strip()
            lt = str(lt).replace("：", ":").strip()

            oa = s.get("order_amount") or s.get("orderAmount")
            try:
                seal = float(oa) if oa is not None else float("nan")
            except Exception:
                seal = float("nan")

            reason = str(s.get("reason_type") or s.get("reasonType") or "").strip()
            ind = str(s.get("industry") or "").strip()

            rows.append(
                {
                    "code": code,
                    "name": str(s.get("name") or "").strip(),
                    "price": price,
                    "pct_chg": pct_chg,
                    "lb": lb,
                    "zb_count": zb_count,
                    "industry": ind,
                    "reason": reason,
                    "first_time": ft,
                    "fb_time": lt,
                    "封板资金": seal,
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    _lb = pd.to_numeric(df["lb"], errors="coerce").fillna(1).astype(int)
    df["lb"] = _lb.mask(_lb <= 0, 1)
    return df


def fetch_zt_pool_lb(date_yyyymmdd: str) -> pd.DataFrame:
    d = date_yyyymmdd[:8]
    raw = lb_get("/ladder", {"date": d})
    return ladder_to_zt_dataframe({"data": raw} if isinstance(raw, dict) else raw)


def stocks_to_dt_or_zb_df(payload: Any) -> pd.DataFrame:
    """跌停/炸板池：均输出 code、name。"""
    inner = _unwrap_inner_data(payload)
    stocks = inner.get("stocks") or []
    if not isinstance(stocks, list):
        return pd.DataFrame()
    rows = []
    for s in stocks:
        if not isinstance(s, dict):
            continue
        code = _norm_code(s.get("code"))
        if not code:
            continue
        name = str(s.get("name") or "").strip()
        rows.append({"code": code, "name": name})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_zb_pool_lb(date_yyyymmdd: str) -> pd.DataFrame:
    d = date_yyyymmdd[:8]
    raw = lb_get("/broken-limit-up", {"date": d})
    return stocks_to_dt_or_zb_df(raw)


def fetch_dt_pool_lb(date_yyyymmdd: str) -> pd.DataFrame:
    d = date_yyyymmdd[:8]
    raw = lb_get("/limit-down", {"date": d})
    return stocks_to_dt_or_zb_df(raw)
