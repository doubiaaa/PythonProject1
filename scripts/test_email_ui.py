# -*- coding: utf-8 -*-
"""
本地验证邮件 HTML：构造示例 Markdown 与模拟成交，调用 send_report_email / send_simulated_trade_notification。

用法（需配置 replay_config.json 或环境变量 SMTP_*、MAIL_TO）：
  python scripts/test_email_ui.py
  python scripts/test_email_ui.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


SAMPLE_MD = """【摘要】市场阶段：震荡期｜适宜度：中｜置信度：低

### 1. 市场阶段与情绪

情绪温度示例，建议仓位 **30%**。

### 2. 观察清单（表格）

| 优先级 | 代码 | 名称 | 标签 | 简要理由 |
|--------|------|------|------|----------|
| 1 | 600000 | 示例股份 | 人气龙头 | 程序综合分第一 |
| 2 | 000001 | 示例控股 | 活口核心 | 承接健康 |

### 3. 免责声明

> **免责声明**：以上分析基于公开数据与程序规则，仅供参考。

"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 HTML 片段长度，不连接 SMTP",
    )
    args = parser.parse_args()

    from app.services.email_notify import (
        has_email_config,
        resolve_email_config,
        send_report_email,
        send_simulated_trade_notification,
    )
    from app.utils.config import ConfigManager
    from app.utils.email_template import (
        holdings_to_html_rows,
        render_email_template,
        markdown_to_email_html,
        build_email_content_prefix,
        strip_first_summary_line,
    )

    cm = ConfigManager()
    cfg = resolve_email_config(cm)

    inner = markdown_to_email_html(SAMPLE_MD)
    prefix = build_email_content_prefix(
        SAMPLE_MD,
        {
            "header_date": "交易日 20260328",
            "email_kpi": {
                "zt_count": 42,
                "dt_count": 5,
                "zhaban_rate": 28.5,
                "premium": 1.2,
                "premium_note": "",
                "position_suggestion": "30%",
            },
        },
    )
    md2 = strip_first_summary_line(SAMPLE_MD)
    inner2 = markdown_to_email_html(md2)
    full = render_email_template(
        inner2,
        "【测试】邮件 UI 样例",
        {
            "header_date": "交易日 20260328",
            "title": "【测试】邮件 UI 样例",
            "content_prefix_html": prefix,
            "email_kpi": {
                "zt_count": 42,
                "dt_count": 5,
                "zhaban_rate": 28.5,
                "premium": 1.2,
                "premium_note": "",
                "position_suggestion": "30%",
            },
        },
    )

    if args.dry_run:
        print("HTML length:", len(full))
        return 0

    if not has_email_config(cfg):
        print("未配置 SMTP，改用 --dry-run 查看 HTML 长度。", file=sys.stderr)
        print("HTML length:", len(full))
        return 1

    ok, msg = send_report_email(
        cfg,
        "【测试】邮件 UI 样例 · Markdown 报告",
        SAMPLE_MD,
        extra_vars={
            "header_date": "交易日 20260328",
            "email_kpi": {
                "zt_count": 42,
                "dt_count": 5,
                "zhaban_rate": 28.5,
                "premium": 1.2,
                "premium_note": "",
                "position_suggestion": "30%",
            },
        },
    )
    print("报告邮件:", ok, msg)

    rows = holdings_to_html_rows(
        [
            {
                "symbol": "000001",
                "name": "平安银行",
                "shares": 200,
                "current_price": 15.2,
            }
        ],
        limit=3,
        total_portfolio_value=50000,
    )
    trade_info = {
        "side": "buy",
        "symbol": "000001",
        "name": "平安银行",
        "shares": 200,
        "price": 15.2,
        "amount": 3040,
        "reason": "测试成交理由",
        "trade_date": "20260328",
        "subject": "【模拟账户买入】000001 平安银行 200股@15.20",
        "action_line": "建议跟随模拟账户【买入】000001 平安银行；以下为测试数据。",
        "top_holdings_html_rows": rows,
    }
    account_snapshot = {
        "total_value": 50000,
        "cash": 46960,
        "holding_market_value": 3040,
        "n_positions": 1,
        "initial_capital": 100000,
        "day_return_pct": 0.15,
    }
    ok2, msg2 = send_simulated_trade_notification(
        cfg,
        trade_info,
        account_snapshot,
        extra_vars={"header_date": "成交日 20260328"},
    )
    print("模拟成交邮件:", ok2, msg2)
    return 0 if ok and ok2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
