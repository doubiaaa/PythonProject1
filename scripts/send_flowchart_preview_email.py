# -*- coding: utf-8 -*-
"""发送「五人理论」表格式预览邮件（与正式温习正文一致，无流程图 PNG）。

需已配置 SMTP：replay_config 或 SMTP_* 环境变量（与 nightly 相同）。
默认收件人 1961141860@qq.com；可传参覆盖：python scripts/send_flowchart_preview_email.py user@example.com
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.email_notify import resolve_email_config, send_report_email
from app.utils.config import ConfigManager
from app.utils.replay_viewpoint_footer import build_theory_review_markdown


def _smtp_cfg_fallback() -> dict | None:
    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host:
        return None
    try:
        port = int((os.environ.get("SMTP_PORT") or "587").strip())
    except ValueError:
        port = 587
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    mail_from = (os.environ.get("SMTP_FROM") or "").strip() or user
    ssl_env = (os.environ.get("SMTP_SSL") or "").strip().lower()
    use_ssl = ssl_env in ("1", "true", "yes")
    return {
        "smtp_host": host,
        "smtp_port": port,
        "smtp_user": user,
        "smtp_password": password,
        "smtp_from": mail_from,
        "smtp_ssl": use_ssl,
    }


def main() -> int:
    to_addr = "1961141860@qq.com"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        to_addr = sys.argv[1].strip()

    cm = ConfigManager()
    cfg = resolve_email_config(cm) or _smtp_cfg_fallback()
    if not cfg:
        print(
            "未找到 SMTP：请在 replay_config.json 配置 smtp_host，"
            "或设置 SMTP_HOST、SMTP_USER、SMTP_PASSWORD、SMTP_FROM、SMTP_PORT（可选 SMTP_SSL）。",
            file=sys.stderr,
        )
        return 1

    body = build_theory_review_markdown()
    if not body.strip():
        print("正文为空：请检查 app/utils/replay_footer_commentary.py。", file=sys.stderr)
        return 1

    subject = "【温习预览】五人理论（表格式）"
    extra = {
        "header_date": "表格式预览",
        "title": subject,
        "report_banner_title": "五人理论 · 表格式预览",
        "system_name": str(cm.get("email_system_name") or "T+0 竞价复盘系统"),
    }

    cfg_send = dict(cfg)
    cfg_send["mail_to"] = [to_addr]

    ok, msg = send_report_email(
        cfg_send,
        subject,
        body,
        extra_vars=extra,
        inline_images=None,
    )
    if ok and msg != "skipped":
        print(f"已发送至 {to_addr}（Markdown 表格式正文，无内嵌流程图）")
        return 0
    if not ok:
        print(f"发送失败：{msg}", file=sys.stderr)
        return 1
    print("skipped", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
