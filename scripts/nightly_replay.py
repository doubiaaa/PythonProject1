# -*- coding: utf-8 -*-
"""
定时复盘入口：拉取数据 → 智谱生成报告 → Server酱 推送微信。

默认使用「北京时间当日」作为复盘日；若该日不是 A 股交易日，则**不执行**复盘（退出码 0，不发微信），
适用于定时任务在周末/节假日自动跳过。

用法：
  python scripts/nightly_replay.py
  python scripts/nightly_replay.py --date 20260328

密钥优先级：环境变量 ZHIPU_API_KEY、SERVERCHAN_SENDKEY > replay_config.json
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# 项目根加入 path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _resolve_keys():
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    api_key = (os.environ.get("ZHIPU_API_KEY") or "").strip() or (cm.get("zhipu_api_key") or "").strip()
    sct = (os.environ.get("SERVERCHAN_SENDKEY") or "").strip() or (cm.get("serverchan_sendkey") or "").strip()
    return api_key, sct


def main() -> int:
    parser = argparse.ArgumentParser(description="夜间自动复盘（定时任务 / GitHub Actions）")
    parser.add_argument(
        "--date",
        metavar="YYYYMMDD",
        help="复盘日；默认不传则为当前北京时间自然日，且须为交易日才会执行",
    )
    args = parser.parse_args()

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        print("需要 Python 3.9+", file=sys.stderr)
        return 1

    if args.date:
        if len(args.date) != 8 or not args.date.isdigit():
            print("--date 须为 8 位 YYYYMMDD", file=sys.stderr)
            return 1
        date_str = args.date
    else:
        date_str = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")

    from app.services.data_fetcher import DataFetcher
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    fetcher = DataFetcher(
        cache_expire=cm.get("cache_expire", 3600),
        retry_times=cm.get("retry_times", 1),
    )
    trade_days = fetcher.get_trade_cal()
    if not trade_days:
        print("无法获取 A 股交易日历，请检查网络或 akshare 数据源", file=sys.stderr)
        return 1
    if date_str not in trade_days:
        print(
            f"[nightly] 跳过：{date_str} 非交易日（定时任务在非交易日不运行）",
            flush=True,
        )
        return 0

    api_key, serverchan_sendkey = _resolve_keys()
    if not api_key:
        print(
            "未配置智谱 API Key：请设置环境变量 ZHIPU_API_KEY 或在 replay_config.json 中填写 zhipu_api_key",
            file=sys.stderr,
        )
        return 1
    if not serverchan_sendkey:
        print(
            "未配置 Server酱：请设置环境变量 SERVERCHAN_SENDKEY 或在 replay_config.json 中填写 serverchan_sendkey",
            file=sys.stderr,
        )
        return 1

    from app.services.replay_task import ReplayTask

    task = ReplayTask()
    print(f"[nightly] 交易日={date_str}（北京时间自然日对应 A 股交易日）", flush=True)
    task.run(date_str, api_key, fetcher, serverchan_sendkey=serverchan_sendkey)

    if task.status == "error":
        print(task.result or "unknown error", file=sys.stderr)
        return 1
    print("[nightly] completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
