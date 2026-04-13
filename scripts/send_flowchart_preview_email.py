# -*- coding: utf-8 -*-
"""发送流程图 PNG 预览邮件（需已配置 SMTP，与 nightly 相同：replay_config 或 SMTP_* 环境变量）。"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.email_notify import resolve_email_config
from app.utils.config import ConfigManager


def _smtp_cfg_fallback() -> dict | None:
    """无 replay_config / MAIL_TO 时，仅用环境变量发信（与 GitHub Actions Secrets 一致）。"""
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


def _build_message(
    *,
    mail_from: str,
    to_list: list[str],
    subject: str,
    image_paths: list[str],
) -> MIMEMultipart:
    html_parts: list[str] = [
        "<div style='font-family:Segoe UI,Microsoft YaHei,sans-serif;font-size:14px;color:#1e293b;'>",
        "<p>以下为 <strong>流程图修复预览</strong>（内嵌显示；若客户端屏蔽图片请查附件）。</p>",
    ]
    related = MIMEMultipart("related")
    cid_list: list[tuple[str, str]] = []
    for i, path in enumerate(image_paths):
        cid = f"flowchart{i}"
        cid_list.append((cid, path))
        name = os.path.basename(path)
        html_parts.append(
            f"<p style='margin:16px 0 8px;font-weight:600;'>{name}</p>"
            f"<img src='cid:{cid}' alt='{name}' style='max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:8px;'/>"
        )
    html_parts.append("<p style='margin-top:20px;font-size:12px;color:#64748b;'>由 scripts/send_flowchart_preview_email.py 发送</p></div>")
    html_body = "\n".join(html_parts)

    plain_lines = ["流程图修复预览", ""]
    for _, path in cid_list:
        plain_lines.append(f"- {os.path.basename(path)}（见 HTML 内嵌图或附件）")
    plain_lines.append("")
    plain_lines.append("由 scripts/send_flowchart_preview_email.py 发送")
    plain = "\n".join(plain_lines)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain", "utf-8"))
    related.attach(MIMEText(html_body, "html", "utf-8"))

    for cid, path in cid_list:
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fp:
            img = MIMEImage(fp.read())
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
        related.attach(img)

    alt.attach(related)

    root = MIMEMultipart("mixed")
    root.attach(alt)
    for _, path in cid_list:
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fp:
            raw = fp.read()
        att = MIMEImage(raw)
        att.add_header(
            "Content-Disposition",
            "attachment",
            filename=os.path.basename(path),
        )
        root.attach(att)

    root["Subject"] = subject
    root["From"] = formataddr(("流程图预览", mail_from)) if mail_from else ""
    root["To"] = ", ".join(to_list)
    return root


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

    host = cfg["smtp_host"]
    port = int(cfg["smtp_port"])
    user = cfg.get("smtp_user") or ""
    password = cfg.get("smtp_password") or ""
    mail_from = cfg.get("smtp_from") or user
    use_ssl = bool(cfg.get("smtp_ssl"))

    paths = [
        os.path.join(_ROOT, "assets", "readme_business_overview.png"),
        os.path.join(_ROOT, "assets", "replay_footer_kebi.png"),
    ]
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        print("未找到 PNG：请先运行 generate_readme_business_overview_chart.py 与 generate_replay_footer_kebi.py", file=sys.stderr)
        return 1

    subject = "【流程图预览】业务全景 +科比框架（修复后）"
    msg = _build_message(
        mail_from=mail_from,
        to_list=[to_addr],
        subject=subject,
        image_paths=paths,
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=45) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=45) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, [to_addr], msg.as_string())
    except Exception as e:
        print(f"发送失败：{e}", file=sys.stderr)
        return 1

    print(f"已发送至 {to_addr}（{len(paths)} 张图：内嵌 + 附件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
