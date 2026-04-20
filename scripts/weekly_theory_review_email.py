# -*- coding: utf-8 -*-
"""
每周六温习邮件：单独发送「五人理论框架」全文（表格式解读 + 附录），与日复盘独立。

用法：
  python scripts/weekly_theory_review_email.py

依赖：与日复盘相同，需配置 SMTP；正文为 **五人理论** Markdown 表格（无流程图 PNG）；不含仓库六层架构演进表。

定时：
  - GitHub Actions：见 .github/workflows/weekly-theory-review.yml（北京时间周六 09:00）
  - 本机：见 scripts/register_weekly_theory_review_task.ps1（Windows 任务计划程序）
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.email_notify import has_email_config, resolve_email_config, send_report_email
from app.utils.config import ConfigManager
from app.utils.replay_viewpoint_footer import (
    build_theory_review_markdown,
    replay_footer_inline_images_weekly,
)


def _beijing_today_str() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def main() -> int:
    cm = ConfigManager()
    cfg = resolve_email_config(cm)
    if not cfg or not has_email_config(cfg):
        print("[weekly-theory] 未配置 SMTP（SMTP_HOST + MAIL_TO 等），跳过发信")
        return 0

    body = build_theory_review_markdown()
    if not body.strip():
        print("[weekly-theory] 正文为空（replay_footer_commentary 缺失？），跳过")
        return 0

    date_s = _beijing_today_str()
    subj = f"【温习】五人理论 · {date_s}"
    _cm = ConfigManager()
    banner = f"每周温习 · 五人理论（{date_s}）"
    extra = {
        "header_date": f"发送日 {date_s}",
        "title": subj,
        "report_banner_title": banner,
        "system_name": str(_cm.get("email_system_name") or "龙头战法复盘 聚焦核心 拥抱龙头"),
    }
    ok, msg = send_report_email(
        cfg,
        subj,
        body,
        extra_vars=extra,
        inline_images=replay_footer_inline_images_weekly(),  # 表格式文末，无 CID图
    )
    if ok and msg != "skipped":
        print(f"[weekly-theory] 已发送：{subj}")
        return 0
    if not ok:
        print(f"[weekly-theory] 发送失败：{msg}")
        return 1
    print("[weekly-theory] skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
