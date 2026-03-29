# -*- coding: utf-8 -*-
"""
邮件 HTML：Jinja2 基础模板 + Markdown 转换 + 模拟成交通知片段。
"""

from __future__ import annotations

import html
import os
import re
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
_APP_DIR = os.path.join(_PROJECT_ROOT, "app")
_TEMPLATE_DIR = os.path.join(_APP_DIR, "templates")

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def truncate_long_text(text: str, max_chars: int = 180_000) -> str:
    if not text or len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n\n…（正文过长已截断）"


def markdown_to_html(md_text: str) -> str:
    """Markdown → HTML 片段（不含外层邮件壳）。"""
    import markdown

    if not md_text or not str(md_text).strip():
        return "<p>（无正文）</p>"

    extensions = [
        "markdown.extensions.extra",
        "markdown.extensions.nl2br",
        "markdown.extensions.fenced_code",
        "markdown.extensions.tables",
    ]
    extension_configs: dict[str, Any] = {}
    try:
        import pygments  # noqa: F401

        extensions.append("markdown.extensions.codehilite")
        extension_configs["codehilite"] = {
            "css_class": "highlight",
            "guess_lang": False,
        }
    except ImportError:
        pass

    return markdown.markdown(
        md_text,
        extensions=extensions,
        extension_configs=extension_configs,
        output_format="html5",
    )


def render_email_template(
    content_html: str,
    subject: str,
    extra_vars: Optional[dict[str, Any]] = None,
) -> str:
    """
    将正文 HTML 嵌入 email_base.html，返回完整 HTML 文档。
    content_html 应为已转义安全的片段（来自 markdown 或受控模板）。
    """
    ev = extra_vars or {}
    ctx = {
        "title": ev.get("title") or subject or "复盘系统通知",
        "system_name": ev.get("system_name") or "次日竞价半路复盘系统",
        "header_date": ev.get("header_date") or "",
        "content_html": content_html,
        "disclaimer": ev.get(
            "disclaimer",
            "以上内容基于公开数据与程序规则自动生成，仅供参考，不构成投资建议。股市有风险，投资需谨慎。",
        ),
        "footer_line": ev.get(
            "footer_line",
            f"© 复盘系统 · 版本 {ev.get('app_version', '1.0')}",
        ),
    }
    ctx.update({k: v for k, v in ev.items() if k not in ctx})
    tpl = _env.get_template("email_base.html")
    return tpl.render(**ctx)


def embed_image_cid(html_str: str, image_path: str, cid: str) -> str:
    """在 HTML 末尾追加内嵌图片引用（multipart/related 中需同 cid 发送 MIME 附件）。"""
    if not os.path.isfile(image_path):
        return html_str
    safe_cid = re.sub(r"[^a-zA-Z0-9._-]", "", cid) or "img1"
    tag = (
        f'<p><img src="cid:{safe_cid}" alt="" '
        f'style="max-width:100%;height:auto;border-radius:8px;display:block;margin:12px auto;" /></p>'
    )
    return html_str + "\n" + tag


def embed_image(html_str: str, image_path: str, cid: str) -> str:
    """别名：在 HTML 末尾追加内嵌图片引用（multipart/related + MIMEImage）。"""
    return embed_image_cid(html_str, image_path, cid)


def build_simulated_trade_html(
    *,
    side: str,
    symbol: str,
    name: str,
    shares: int,
    price: float,
    amount: float,
    reason: str,
    trade_date: str,
    total_value: float,
    cash: float,
    holding_market_value: float,
    n_positions: int,
    top_holdings_html_rows: str,
    initial_capital: float,
    day_return_pct: Optional[float] = None,
) -> tuple[str, str]:
    """
    模拟账户成交通知：返回 (html_fragment, plain_text)。
    top_holdings_html_rows：已格式化的 <tr>...</tr> 多行 HTML。
    """
    op = "买入" if side == "buy" else "卖出"
    badge_class = "badge-buy" if side == "buy" else "badge-sell"
    total_ret_pct = (
        ((total_value / initial_capital) - 1.0) * 100.0 if initial_capital > 0 else 0.0
    )
    day_row = ""
    if day_return_pct is not None:
        day_row = (
            f"<tr><td style=\"border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;\">"
            f"当日收益率（相对上一日）</td>"
            f"<td style=\"border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;\">"
            f"{day_return_pct:+.2f}%</td></tr>"
        )

    html_frag = f"""
<div style="margin-bottom:20px;">
  <span class="badge {badge_class}" style="display:inline-block;padding:6px 14px;border-radius:999px;font-size:13px;font-weight:600;letter-spacing:0.04em;background:{'#dcfce7' if side=='buy' else '#fee2e2'};color:{'#166534' if side=='buy' else '#991b1b'};">{html.escape(op)}</span>
</div>
<h2 style="margin:0 0 14px;font-size:17px;color:#0f172a;border-bottom:1px solid #e2e8f0;padding-bottom:8px;">成交明细</h2>
<table style="border-collapse:collapse;width:100%;margin:0 0 18px;font-size:14px;">
  <thead><tr>
    <th style="border:1px solid #cbd5e1;padding:10px 12px;background:#f1f5f9;text-align:left;">项目</th>
    <th style="border:1px solid #cbd5e1;padding:10px 12px;background:#f1f5f9;text-align:left;">内容</th>
  </tr></thead>
  <tbody>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">股票代码</td><td style="border:1px solid #cbd5e1;padding:10px 12px;"><strong>{html.escape(symbol)}</strong></td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">名称</td><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">{html.escape(name)}</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">数量</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{shares} 股</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">成交价</td><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">{price:.4f} 元</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">成交金额</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{amount:,.2f} 元</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">理由</td><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">{html.escape(reason)}</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">成交日</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{html.escape(trade_date)}</td></tr>
  </tbody>
</table>

<h2 style="margin:18px 0 12px;font-size:17px;color:#0f172a;border-bottom:1px solid #e2e8f0;padding-bottom:8px;">账户概况</h2>
<table style="border-collapse:collapse;width:100%;margin:0 0 18px;font-size:14px;">
  <tbody>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;width:40%;background:#f8fafc;">总资产</td><td style="border:1px solid #cbd5e1;padding:10px 12px;"><strong>{total_value:,.2f}</strong> 元</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">现金余额</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{cash:,.2f} 元</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">持仓市值（估算）</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{holding_market_value:,.2f} 元</td></tr>
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">持仓只数</td><td style="border:1px solid #cbd5e1;padding:10px 12px;background:#f8fafc;">{n_positions}</td></tr>
    {day_row}
    <tr><td style="border:1px solid #cbd5e1;padding:10px 12px;">累计收益率（相对初始本金）</td><td style="border:1px solid #cbd5e1;padding:10px 12px;">{total_ret_pct:+.2f}%</td></tr>
  </tbody>
</table>

<h2 style="margin:18px 0 12px;font-size:17px;color:#0f172a;border-bottom:1px solid #e2e8f0;padding-bottom:8px;">前三大持仓</h2>
<table style="border-collapse:collapse;width:100%;margin:0 0 18px;font-size:14px;">
  <thead><tr>
    <th style="border:1px solid #cbd5e1;padding:8px 10px;background:#f1f5f9;">代码</th>
    <th style="border:1px solid #cbd5e1;padding:8px 10px;background:#f1f5f9;">名称</th>
    <th style="border:1px solid #cbd5e1;padding:8px 10px;background:#f1f5f9;">股数</th>
    <th style="border:1px solid #cbd5e1;padding:8px 10px;background:#f1f5f9;">市值≈</th>
  </tr></thead>
  <tbody>{top_holdings_html_rows}</tbody>
</table>

<div class="alert-info" style="padding:12px 14px;border-radius:8px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;margin:12px 0;font-size:14px;">
  <strong>操作建议（非指令）：</strong>若您希望与程序保持一致，可<strong>参考并跟随模拟账户</strong>的买卖节奏；以下为模拟盘逻辑输出，请对照成交与账户概况，<strong>实盘请自行决策与风控</strong>。
</div>
"""

    day_plain = ""
    if day_return_pct is not None:
        day_plain = f"当日收益: {day_return_pct:+.2f}% | "
    plain = (
        f"【模拟账户{op}】{symbol} {name} {shares}股@{price:.2f}\n"
        f"成交金额: {amount:,.2f} 元\n理由: {reason}\n成交日: {trade_date}\n"
        f"总资产: {total_value:,.2f} 元 | 现金: {cash:,.2f} 元 | 持仓只数: {n_positions}\n"
        f"{day_plain}累计收益: {total_ret_pct:+.2f}%\n"
    )
    return html_frag.strip(), plain


def holdings_to_html_rows(
    holdings: list[dict[str, Any]], limit: int = 3
) -> str:
    """持仓列表取前 N，按市值排序，返回 <tr> 拼接。"""
    rows: list[tuple[float, dict[str, Any]]] = []
    for h in holdings or []:
        sh = int(h.get("shares") or 0)
        px = float(h.get("current_price") or h.get("cost_price") or 0)
        mv = sh * px
        rows.append((mv, h))
    rows.sort(key=lambda x: -x[0])
    out: list[str] = []
    for i, (_mv, h) in enumerate(rows[:limit]):
        sym = html.escape(str(h.get("symbol") or ""))
        nm = html.escape(str(h.get("name") or ""))
        sh = int(h.get("shares") or 0)
        mv = sh * float(h.get("current_price") or h.get("cost_price") or 0)
        bg = "#f8fafc" if i % 2 else "#ffffff"
        out.append(
            f"<tr style='background:{bg};'>"
            f"<td style='border:1px solid #cbd5e1;padding:8px 10px;'>{sym}</td>"
            f"<td style='border:1px solid #cbd5e1;padding:8px 10px;'>{nm}</td>"
            f"<td style='border:1px solid #cbd5e1;padding:8px 10px;'>{sh}</td>"
            f"<td style='border:1px solid #cbd5e1;padding:8px 10px;'>{mv:,.2f}</td>"
            f"</tr>"
        )
    if not out:
        return "<tr><td colspan='4' style='border:1px solid #cbd5e1;padding:10px;'>（无持仓）</td></tr>"
    return "".join(out)
