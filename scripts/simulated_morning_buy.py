# -*- coding: utf-8 -*-
"""
模拟账户：在 T+1 交易日开盘后，执行前一日 pending_buys 中的买入（开盘价撮合）。

用法：
  python scripts/simulated_morning_buy.py

逻辑：北京时间当日若为交易日，取「上一交易日」为 signal_date，读取
  data/pending_buys_{signal_date}.json
若不存在则退出 0。用当日日 K 开盘价作为买入价（akshare）。

可与 GitHub Actions cron（北京时间 9:31 左右）或本机任务计划配合。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _prev_trading_day(trade_days: list[str], today: str) -> Optional[str]:
    prior = [t for t in trade_days if t < today]
    return prior[-1] if prior else None


def _fetch_open_price(code: str, day: str) -> float:
    import pandas as pd

    try:
        import akshare as ak
    except ImportError:
        return 0.0
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=day,
            end_date=day,
            adjust="qfq",
        )
        if df is None or df.empty or "开盘" not in df.columns:
            return 0.0
        return float(pd.to_numeric(df["开盘"], errors="coerce").iloc[0] or 0)
    except Exception:
        return 0.0


def main() -> int:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Shanghai")
    except Exception:
        tz = None  # type: ignore

    from datetime import datetime

    now = datetime.now(tz) if tz else datetime.now()
    today = now.strftime("%Y%m%d")

    from app.services.data_fetcher import DataFetcher
    from app.services.simulated_account import SimulatedAccount
    from app.utils.config import ConfigManager

    cm = ConfigManager()

    def _env_bool(name: str, default: bool) -> bool:
        raw = (os.environ.get(name) or "").strip().lower()
        if raw in ("1", "true", "yes"):
            return True
        if raw in ("0", "false", "no"):
            return False
        return default

    if not _env_bool("ENABLE_SIMULATED_ACCOUNT", cm.get("enable_simulated_account", False)):
        print("enable_simulated_account 为 false，跳过。", flush=True)
        return 0
    btype = (os.environ.get("SIMULATED_BUY_PRICE_TYPE") or "").strip() or cm.get(
        "simulated_buy_price_type", "close_of_recommendation_day"
    )
    if btype != "next_day_open":
        print("simulated_buy_price_type 非 next_day_open，跳过。", flush=True)
        return 0

    fetcher = DataFetcher(
        cache_expire=cm.get("cache_expire", 3600),
        retry_times=cm.get("retry_times", 2),
    )
    trade_days = fetcher.get_trade_cal()
    if not trade_days or today not in trade_days:
        print(f"{today} 非交易日，跳过。", flush=True)
        return 0

    prev_day = _prev_trading_day(trade_days, today)
    if not prev_day:
        print("无法解析上一交易日，跳过。", flush=True)
        return 0

    acc = SimulatedAccount(
        account_path=cm.get("simulated_account_path", "data/simulated_account.json"),
        config_path=cm.get("simulated_config_path", "data/simulated_config.json"),
    )
    acc._cfg["buy_price_type"] = "next_day_open"

    def price_getter(sym: str) -> float:
        return _fetch_open_price(sym, today)

    ok = acc.execute_pending_buys(
        today,
        prev_day,
        price_getter,
        trade_days=trade_days,
    )
    if ok:
        print(
            f"模拟账户已按开盘价买入（执行日 {today}，信号日 {prev_day}）。",
            flush=True,
        )
    else:
        print(
            f"无 pending 或未能成交（执行日 {today}，信号日 {prev_day}）。",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
