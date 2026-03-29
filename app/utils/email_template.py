# -*- coding: utf-8 -*-
"""
邮件 HTML：Jinja2 基础模板 + Markdown 转换 + 模拟成交通知片段。
"""

from __future__ import annotations

import html
import os
import re
from datetime import datetime
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


def strip_first_summary_line(md: str) -> str:
    """去掉正文里首条【摘要】行，避免与邮件顶部「核心摘要」框重复。"""
    lines = (md or "").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().startswith("【摘要】"):
        new_lines = lines[:i] + lines[i + 1 :]
        return "\n".join(new_lines).lstrip("\n")
    return md or ""


def should_skip_rich_email_prefix(raw_md: str) -> bool:
    """极短失败栈或错误提示不套长篇说明，避免版式突兀。"""
    rs = (raw_md or "").strip()
    if len(rs) < 12:
        return True
    if len(rs) < 500 and (
        "复盘失败" in rs[:600]
        or "❌" in rs[:120]
        or rs.startswith("Traceback")
    ):
        return True
    return False


def build_email_content_prefix(
    raw_md: str,
    extra_vars: Optional[dict[str, Any]] = None,
) -> str:
    """
    在 Markdown 转 HTML 正文前追加：报告主标题区、【摘要】高亮、报告说明段。
    使系统邮件信息层级更接近「摘要报表」原型，而非裸 Markdown。
    """
    ev = extra_vars or {}
    if ev.get("email_content_prefix") == "none":
        return ""
    if should_skip_rich_email_prefix(raw_md):
        return ""

    title = html.escape(str(ev.get("report_banner_title") or "市场竞价深度复盘报告"))
    sub = html.escape(str(ev.get("header_date") or "").strip() or "（见页头日期）")
    parts: list[str] = [
        '<div style="margin:0 0 18px;padding:18px 20px;border-radius:10px;border:1px solid #e2e8f0;'
        'background:linear-gradient(165deg,#f1f5f9 0%,#ffffff 60%);">'
        '<div style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#64748b;margin-bottom:8px;">'
        "Market review · 系统生成</div>"
        f'<div style="font-size:20px;font-weight:700;color:#0f172a;line-height:1.25;letter-spacing:-0.02em;">{title}</div>'
        f'<div style="font-size:13px;color:#64748b;margin-top:10px;">{sub}</div>'
        "</div>"
    ]

    for line in (raw_md or "").split("\n"):
        s = line.strip()
        if s.startswith("【摘要】"):
            esc = html.escape(s)
            parts.append(
                '<div style="margin:0 0 16px;padding:14px 16px;border-radius:8px;border:1px solid #93c5fd;'
                'background:linear-gradient(135deg,#eff6ff 0%,#f0f9ff 100%);">'
                '<div style="font-size:11px;font-weight:700;color:#1d4ed8;letter-spacing:0.05em;margin-bottom:8px;">'
                "核心摘要 · EXECUTIVE SUMMARY</div>"
                f'<div style="font-size:14px;color:#1e293b;line-height:1.6;">{esc}</div>'
                "</div>"
            )
            break

    parts.append(
        '<p style="margin:0 0 20px;font-size:13px;color:#475569;line-height:1.65;border-left:4px solid #94a3b8;'
        'padding:12px 14px;background:#f8fafc;border-radius:0 8px 8px 0;">'
        "<strong style=\"color:#0f172a;\">报告说明</strong>：正文由<strong>程序侧数据</strong>（交易日历、行情与规则、龙头池与标签等）"
        "与<strong>智谱模型</strong>在固定章节结构下共同生成，通常依次包含：<strong>市场阶段与情绪</strong>、"
        "<strong>主线与程序选股</strong>、<strong>次日竞价预案</strong>、<strong>风险与不适用场景</strong>等。"
        "文中表格、列表与代码块仅用于展示数据与逻辑，<strong>不构成投资建议</strong>；请结合自身情况独立决策。"
        "</p>"
    )
    return "\n".join(parts)


def build_plain_text_email_header(extra_vars: Optional[dict[str, Any]] = None) -> str:
    """纯文本邮件顶部补充系统说明（与 HTML 前缀信息对齐）。"""
    ev = extra_vars or {}
    if ev.get("email_content_prefix") == "none":
        return ""
    lines = [
        "══════════════════════════════════════",
        " 次日竞价半路复盘系统 · 自动报告",
        "══════════════════════════════════════",
    ]
    hd = (ev.get("header_date") or "").strip()
    if hd:
        lines.append(f"日期 / 场景：{hd}")
    lines.extend(
        [
            "",
            "【报告说明】",
            "· 数据：程序拉取公开行情、交易日历，并按规则生成龙头池等；",
            "· 正文：智谱模型按固定章节输出，为 Markdown 结构；",
            "· 用途：个人研究与记录，不构成投资建议，股市有风险。",
            "",
            "────────── 正文（纯文本）──────────",
            "",
        ]
    )
    return "\n".join(lines)


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
    _yr = datetime.now().year
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
            f"© 次日竞价半路复盘系统 · 版本 {ev.get('email_app_version', ev.get('app_version', '1.0'))}",
        ),
        "footer_line_secondary": ev.get(
            "footer_line_secondary",
            f"© {_yr} NEXT-DAY BIDDING SYSTEM | INTERNAL INTELLIGENCE REPORT",
        ),
        "show_intel_badge": ev.get("show_intel_badge", True),
        "intel_badge_text": ev.get("intel_badge_text", "INTERNAL INTELLIGENCE REPORT"),
        "footer_show_nav": ev.get("footer_show_nav", True),
        "content_prefix_html": ev.get("content_prefix_html", ""),
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
