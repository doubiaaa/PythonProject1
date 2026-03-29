# -*- coding: utf-8 -*-
"""
周末龙头池周度表现邮件：读取 data/watchlist_records.json，按规则算区间收益，发 HTML 邮件。

用法：
  python scripts/weekly_performance_email.py
  python scripts/weekly_performance_email.py --dry-run
  python scripts/weekly_performance_email.py --anchor 20260328

依赖环境变量 / replay_config：SMTP（与 nightly 相同）、可选 ZHIPU_API_KEY（enable_weekly_ai_insight）。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _resolve_anchor_trade(trade_days: list[str], as_of: datetime) -> str:
    as_s = as_of.strftime("%Y%m%d")
    prior = [t for t in trade_days if t < as_s]
    if not prior:
        return trade_days[-1]
    return prior[-1]


def _call_zhipu_insight(api_key: str, md: str) -> str:
    import requests

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    prompt = (
        "你是 A 股短线复盘助手。根据下列「龙头池周度表现」统计（Markdown），"
        "用 5～8 条短句总结：哪些情况上涨概率高、哪些情况需谨慎、对下周方向的一句中性判断。"
        "不要重复表格数字，不要投资建议式措辞，用「观察」「统计上」等表述。\n\n"
        + md[:12000]
    )
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "glm-4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.35,
            "max_tokens": 1024,
        },
        timeout=90,
    )
    if r.status_code != 200:
        return f"（智谱简评失败：HTTP {r.status_code}）"
    data = r.json()
    ch = (data.get("choices") or [{}])[0].get("message") or {}
    return str(ch.get("content") or "（无内容）")


def main() -> int:
    parser = argparse.ArgumentParser(description="龙头池周度表现邮件")
    parser.add_argument(
        "--anchor",
        metavar="YYYYMMDD",
        help="报告锚点交易日（一般为周五）；默认取「北京时间今日之前最近一个交易日」",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 Markdown，不发邮件",
    )
    args = parser.parse_args()

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Shanghai")
    except Exception:
        tz = None  # type: ignore

    now = datetime.now(tz) if tz else datetime.now()
    from app.services.data_fetcher import DataFetcher
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    fetcher = DataFetcher(
        cache_expire=cm.get("cache_expire", 3600),
        retry_times=cm.get("retry_times", 2),
    )
    trade_days = fetcher.get_trade_cal()
    if not trade_days:
        print("无法获取交易日历", file=sys.stderr)
        return 1

    if args.anchor:
        anchor = args.anchor.strip()
        if anchor not in trade_days:
            print(f"锚点 {anchor} 非交易日，将回退", file=sys.stderr)
            anchor = _resolve_anchor_trade(trade_days, now)
    else:
        anchor = _resolve_anchor_trade(trade_days, now)

    adt = datetime.strptime(anchor, "%Y%m%d")
    iso_year, iso_week, _ = adt.isocalendar()

    from app.services.weekly_performance import build_weekly_report_markdown_auto

    md = build_weekly_report_markdown_auto(
        trade_days, anchor, iso_year, iso_week
    )

    if cm.get("enable_weekly_ai_insight", False):
        api_key = (os.environ.get("ZHIPU_API_KEY") or "").strip() or (
            cm.get("zhipu_api_key") or ""
        ).strip()
        if api_key:
            try:
                insight = _call_zhipu_insight(api_key, md)
                md += "\n## 智谱简评（统计归纳，非投资建议）\n\n" + insight + "\n"
            except Exception as e:
                md += f"\n## 智谱简评\n\n（生成失败：{e}）\n"
        else:
            md += "\n## 智谱简评\n\n（未配置 ZHIPU_API_KEY）\n"

    if args.dry_run:
        print(md)
        return 0

    from app.services.watchlist_store import RECORDS_FILE, load_all_records

    if not os.path.isfile(RECORDS_FILE) or not load_all_records():
        print(
            "无 data/watchlist_records.json 或内容为空，跳过发信。"
            "请在持久化环境跑复盘以积累龙头池存档。",
            file=sys.stderr,
        )
        return 0

    if not cm.get("enable_weekly_performance_email", True):
        print("enable_weekly_performance_email 为 false，跳过发信", file=sys.stderr)
        print(md)
        return 0

    from app.services.email_notify import has_email_config, resolve_email_config, send_report_email

    email_cfg = resolve_email_config(cm)
    if not has_email_config(email_cfg):
        print("未配置 SMTP，无法发邮件（可用 --dry-run 查看正文）", file=sys.stderr)
        return 1

    subj = f"📊 龙头池周度表现 · {iso_year}年第{iso_week}周 · 锚点{anchor}"
    ok, msg = send_report_email(email_cfg, subj, md)
    if not ok:
        print(f"发送失败：{msg}", file=sys.stderr)
        return 1
    print("已发送：", subj)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
