"""SMTP 邮件：统一 HTML 模板（Jinja2）+ 纯文本备选 + 可选内嵌图片（CID）。"""

from __future__ import annotations

import os
import re
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Optional

import markdown

from app.utils.email_template import (
    build_email_content_prefix,
    build_plain_text_email_header,
    markdown_to_email_html,
    render_email_template,
    should_skip_rich_email_prefix,
)

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
        "email_html_template_enabled": bool(cm.get("email_html_template_enabled", True)),
        "email_app_version": str(cm.get("email_app_version", "1.0")),
        "email_content_prefix": bool(cm.get("email_content_prefix", True)),
        "email_news_max_items": int(cm.get("email_news_max_items", 3)),
        "email_news_filter_prefix": str(
            cm.get("email_news_filter_prefix", "【本文系数据通用户提前专享】")
        ),
    }


def _markdown_to_plain(text: str) -> str:
    """将 Markdown 转为易读纯文本（无 **、## 等符号）。"""
    if not text:
        return ""
    s = text
    s = re.sub(r"^#{1,6}\s+(.+)$", r"\n\1\n", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^\s*[-*+]\s+", "• ", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*(\d+)\.\s+", r"\1. ", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _html_to_plain_fallback(html_s: str) -> str:
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html_s)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()[:120_000]


def _markdown_to_html_fragment_legacy(md: str) -> str:
    return markdown.markdown(
        md,
        extensions=[
            "markdown.extensions.nl2br",
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
        ],
        output_format="html5",
    )


def _wrap_email_html_legacy(fragment: str) -> str:
    """关闭统一模板时的旧版 HTML 外壳（与历史行为接近）。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.7;
  color: #1f2937;
  background: #f9fafb;
  margin: 0;
  padding: 12px;
}}
.wrap {{
  max-width: 720px;
  margin: 0 auto;
  background: #fff;
  border-radius: 12px;
  padding: 20px 18px 28px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
h1 {{ font-size: 1.35rem; margin: 0 0 16px; color: #111827; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; }}
h2 {{ font-size: 1.15rem; margin: 1.35em 0 0.5em; color: #374151; }}
h3 {{ font-size: 1.05rem; margin: 1.15em 0 0.45em; color: #4b5563; }}
p {{ margin: 0.55em 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.75em 0; font-size: 0.95em; }}
th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
th {{ background: #f3f4f6; }}
</style>
</head>
<body>
<div class="wrap">
{fragment}
</div>
</body>
</html>"""


def send_report_email(
    cfg: dict[str, Any],
    subject: str,
    body: str,
    *,
    html_fragment: Optional[str] = None,
    html_document: Optional[str] = None,
    extra_vars: Optional[dict[str, Any]] = None,
    inline_images: Optional[list[tuple[str, str]]] = None,
    timeout: float = 45.0,
) -> tuple[bool, str]:
    """
    发送邮件：纯文本 + HTML（统一模板或旧版外壳）。

    - body：用于 text/plain；Markdown 报告请传原始 MD，会生成纯文本备选。
    - html_fragment：仅正文片段时，套入 email_base.html（若开启模板）。
    - html_document：已完整 HTML 文档时直接使用，不再套模板。
    - inline_images：[(cid, 绝对路径), ...]，HTML 内使用 <img src="cid:xxx">。
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
    use_template = bool(cfg.get("email_html_template_enabled", True))

    if len(subject) > 200:
        subject = subject[:197] + "..."

    raw_body = body or " "
    if len(raw_body) > MAX_BODY_CHARS:
        raw_body = raw_body[: MAX_BODY_CHARS - 80] + "\n\n…（正文过长已截断）"

    ev = dict(extra_vars or {})
    ev.setdefault("title", subject)
    ev.setdefault(
        "footer_line",
        f"© 次日竞价半路复盘系统 · 版本 {cfg.get('email_app_version', '1.0')}",
    )
    if cfg.get("email_content_prefix") is False:
        ev["email_content_prefix"] = "none"

    # 统一 Markdown 模板信：正文前缀 HTML + 去重摘要后的 MD 源码（HTML 与纯文本共用）
    content_prefix_html = ""
    md_src = raw_body
    if not html_document and not html_fragment and use_template:
        ev_mail = dict(ev)
        content_prefix_html = build_email_content_prefix(raw_body, ev_mail)
        # 已不再在页头渲染「核心摘要」卡；正文保留首行【摘要】，不再默认剔除。

    # 纯文本部分
    if raw_body.strip():
        if not html_document and not html_fragment and use_template:
            plain_part = _markdown_to_plain(md_src)
        else:
            plain_part = _markdown_to_plain(raw_body)
    else:
        plain_part = ""

    # HTML 最终文档
    final_html: str
    if html_document:
        final_html = html_document
        if not plain_part.strip():
            plain_part = _html_to_plain_fallback(final_html)
    elif html_fragment:
        if use_template:
            final_html = render_email_template(html_fragment, subject, ev)
        else:
            final_html = _wrap_email_html_legacy(html_fragment)
    else:
        if use_template:
            ev_mail = dict(ev)
            ev_mail["content_prefix_html"] = content_prefix_html
            inner = markdown_to_email_html(md_src)
            final_html = render_email_template(inner, subject, ev_mail)
        else:
            inner = _markdown_to_html_fragment_legacy(raw_body)
            final_html = _wrap_email_html_legacy(inner)

    if (
        raw_body.strip()
        and not html_document
        and ev.get("email_content_prefix") != "none"
        and not should_skip_rich_email_prefix(raw_body)
    ):
        plain_part = build_plain_text_email_header(ev) + plain_part

    if not plain_part.strip():
        plain_part = _html_to_plain_fallback(final_html) or "（请使用支持 HTML 的邮箱客户端查看）"

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_part, "plain", "utf-8"))

    if inline_images:
        rel = MIMEMultipart("related")
        rel.attach(MIMEText(final_html, "html", "utf-8"))
        for cid, img_path in inline_images:
            if not img_path or not os.path.isfile(img_path):
                continue
            safe_cid = re.sub(r"[^a-zA-Z0-9._-]", "", cid) or "img"
            with open(img_path, "rb") as fp:
                img_data = fp.read()
            mime_img = MIMEImage(img_data)
            mime_img.add_header("Content-ID", f"<{safe_cid}>")
            mime_img.add_header(
                "Content-Disposition",
                "inline",
                filename=os.path.basename(img_path),
            )
            rel.attach(mime_img)
        alt.attach(rel)
    else:
        alt.attach(MIMEText(final_html, "html", "utf-8"))

    mime_root = alt
    mime_root["Subject"] = subject
    mime_root["From"] = formataddr(("复盘系统", mail_from)) if mail_from else ""
    mime_root["To"] = ", ".join(to_list)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, to_list, mime_root.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.sendmail(mail_from, to_list, mime_root.as_string())
        return True, "ok"
    except Exception as e:
        return False, str(e)


def send_simple_email(
    subject: str,
    body: str,
    cfg: dict[str, Any],
    *,
    html_fragment: Optional[str] = None,
    extra_vars: Optional[dict[str, Any]] = None,
    inline_images: Optional[list[tuple[str, str]]] = None,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """
    短通知：body 为纯文本或 Markdown；可传 html_fragment 走统一模板。
    """
    return send_report_email(
        cfg,
        subject,
        body,
        html_fragment=html_fragment,
        extra_vars=extra_vars,
        inline_images=inline_images,
        timeout=timeout,
    )


def send_beautiful_email(
    subject: str,
    md_content: str,
    cfg: dict[str, Any],
    *,
    extra_vars: Optional[dict[str, Any]] = None,
    inline_images: Optional[list[tuple[str, str]]] = None,
    timeout: float = 45.0,
) -> tuple[bool, str]:
    """
    高级接口：Markdown 正文，统一走模板渲染（由 send_report_email 内部转换）。
    """
    return send_report_email(
        cfg,
        subject,
        md_content,
        extra_vars=extra_vars,
        inline_images=inline_images,
        timeout=timeout,
    )

