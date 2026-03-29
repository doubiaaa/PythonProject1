"""SMTP 邮件通知（标准库，无额外依赖）"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Optional

# 单封正文上限（字符），避免部分 SMTP 拒信
MAX_BODY_CHARS = 200_000


def _split_addrs(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in str(raw).replace(";", ",").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


def has_email_config(cfg: Optional[dict[str, Any]]) -> bool:
    """是否具备发信最小配置（host + 至少一个收件人）。"""
    if not cfg:
        return False
    host = (cfg.get("smtp_host") or "").strip()
    if not host:
        return False
    to = cfg.get("mail_to")
    if isinstance(to, list):
        return len(to) > 0
    return bool(_split_addrs(str(to or "")))


def resolve_email_config(cm) -> Optional[dict[str, Any]]:
    """
    合并环境变量与 replay_config（env 优先）。
    cm: ConfigManager 实例。
    """
    def g(env_name: str, cfg_key: str, default: str = "") -> str:
        ev = os.environ.get(env_name)
        if ev is not None and str(ev).strip() != "":
            return str(ev).strip()
        v = cm.get(cfg_key, default)
        if v is None:
            return default
        return str(v).strip() if v != "" else default

    host = g("SMTP_HOST", "smtp_host", "")
    if not host:
        return None
    port_s = g("SMTP_PORT", "smtp_port", "587")
    try:
        port = int(port_s)
    except ValueError:
        port = 587
    user = g("SMTP_USER", "smtp_user", "")
    password = g("SMTP_PASSWORD", "smtp_password", "")
    mail_from = g("SMTP_FROM", "smtp_from", "") or user
    mail_to_raw = g("MAIL_TO", "mail_to", "")
    ssl_env = (os.environ.get("SMTP_SSL") or "").strip().lower()
    use_ssl = ssl_env in ("1", "true", "yes")
    if not use_ssl:
        v = cm.get("smtp_ssl", False)
        use_ssl = v is True or (isinstance(v, str) and v.lower() in ("1", "true", "yes"))
    addrs = _split_addrs(mail_to_raw)
    if not addrs:
        return None
    if not mail_from:
        mail_from = user
    return {
        "smtp_host": host,
        "smtp_port": port,
        "smtp_user": user,
        "smtp_password": password,
        "smtp_from": mail_from,
        "mail_to": addrs,
        "smtp_ssl": use_ssl,
    }


def send_report_email(
    cfg: dict[str, Any],
    subject: str,
    body: str,
    *,
    timeout: float = 45.0,
) -> tuple[bool, str]:
    """
    发送纯文本邮件。cfg 由 resolve_email_config 生成。
    """
    if not has_email_config(cfg):
        return True, "skipped"
    host = cfg["smtp_host"]
    port = int(cfg.get("smtp_port") or 587)
    user = cfg.get("smtp_user") or ""
    password = cfg.get("smtp_password") or ""
    mail_from = cfg.get("smtp_from") or user
    to_list: list[str] = list(cfg.get("mail_to") or [])
    use_ssl = bool(cfg.get("smtp_ssl"))
    if len(subject) > 200:
        subject = subject[:197] + "..."
    if body and len(body) > MAX_BODY_CHARS:
        body = body[: MAX_BODY_CHARS - 80] + "\n\n…（正文过长已截断）"
    msg = MIMEText(body or " ", "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("复盘报告", mail_from)) if mail_from else ""
    msg["To"] = ", ".join(to_list)
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, to_list, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, to_list, msg.as_string())
        return True, "ok"
    except Exception as e:
        return False, str(e)
