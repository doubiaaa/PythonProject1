# -*- coding: utf-8 -*-
"""
复盘断点：将市场摘要中间结果落盘，便于失败后跳过已完成的「数据获取」步骤。
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
STATUS_DIR = os.path.join(_PROJECT_ROOT, "data", "replay_status")


def _path_for(date: str, suffix: str) -> str:
    d = str(date)[:8]
    os.makedirs(STATUS_DIR, exist_ok=True)
    return os.path.join(STATUS_DIR, f"{d}_{suffix}")


def save_market_data_cache(date: str, market_data: str) -> None:
    p = _path_for(date, "market.txt")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(market_data)
    os.replace(tmp, p)


def load_market_data_cache(date: str) -> Optional[str]:
    p = _path_for(date, "market.txt")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def write_status(date: str, payload: dict[str, Any]) -> None:
    p = _path_for(date, "status.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def read_status(date: str) -> dict[str, Any]:
    p = _path_for(date, "status.json")
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_fetcher_bundle(date: str, market_data: str, fetcher: Any) -> None:
    """数据获取成功后写入，供 resume 时恢复 fetcher 侧变量。"""
    save_market_data_cache(date, market_data)
    zt_pool_records = None
    zt_df = getattr(fetcher, "_last_zt_pool", None)
    if zt_df is not None and not getattr(zt_df, "empty", True):
        try:
            zt_pool_records = json.loads(
                zt_df.to_json(orient="records", date_format="iso")
            )
        except Exception:
            zt_pool_records = None
    bundle = {
        "dragon": getattr(fetcher, "_last_dragon_trader_meta", None),
        "auction": getattr(fetcher, "_last_auction_meta", None),
        "email_kpi": getattr(fetcher, "_last_email_kpi", None),
        "news_prefix": getattr(fetcher, "_last_news_push_prefix", None),
        "zt_pool_records": zt_pool_records,
    }
    p = _path_for(date, "meta.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    write_status(date, {"data_ok": True, "saved": True})


def load_fetcher_bundle(date: str) -> Optional[dict[str, Any]]:
    p = _path_for(date, "meta.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
