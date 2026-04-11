# -*- coding: utf-8 -*-
"""
邮件 HTML：Jinja2 基础模板 + Markdown 转换。
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


def enhance_html_tables_for_email(html: str) -> str:
    """为 Markdown 表格 td 注入 data-label，配合窄屏 CSS 叠成键值行。"""
    if not html or "<table" not in html.lower():
        return html
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        cls = table.get("class") or []
        if isinstance(cls, str):
            cls = [cls]
        cls = [c for c in cls if c]
        for tag in ("md-table", "email-table"):
            if tag not in cls:
                cls.append(tag)
        table["class"] = cls
        thead = table.find("thead")
        labels: list[str] = []
        if thead:
            for th in thead.find_all("th"):
                labels.append(th.get_text(strip=True))
        tbody = table.find("tbody")
        rows_parent = tbody if tbody else table
        for tr in rows_parent.find_all("tr"):
            if tr.find_parent("thead"):
                continue
            tds = tr.find_all("td")
            if not tds:
                continue
            for i, td in enumerate(tds):
                if i < len(labels) and labels[i]:
                    td["data-label"] = labels[i]
    return str(soup)


def markdown_to_email_html(md_text: str) -> str:
    """Markdown → HTML，并做邮件表格增强。"""
    return enhance_html_tables_for_email(markdown_to_html(md_text))


def truncate_finance_news_push_prefix(
    text: str,
    *,
    max_items: int = 3,
    filter_prefix: str = "【本文系数据通用户提前专享】",
) -> str:
    """
    压缩顶部「要闻速览」推送块：仅保留前 max_items 条关联/要闻行，并附查看全部提示。
    若文本中含独立 --- 分隔，会保留分隔后的内容不变。
    """
    if not (text or "").strip():
        return text or ""
    sep_pat = re.compile(r"\n\s*---\s*\n", re.MULTILINE)
    m = sep_pat.search(text)
    if m:
        head, tail = text[: m.start()], text[m.start() :]
    else:
        head, tail = text, ""
    if filter_prefix:
        head = head.replace(filter_prefix, "")
    lines = head.split("\n")
    item_indices: list[int] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("【关联") or s.startswith("【要闻】"):
            item_indices.append(i)
    n = len(item_indices)
    if n <= max_items:
        return head + tail
    fi = item_indices[0]
    header_lines = lines[:fi]
    kept_lines = [lines[j] for j in item_indices[:max_items]]
    note = (
        f"> 📰 查看全部 {n} 条要闻（完整内容请在系统内查看原文，邮件仅展示前 {max_items} 条）"
    )
    new_head = "\n".join(header_lines + kept_lines + ["", note, ""])
    return new_head.rstrip() + tail


def truncate_news(
    news_list: Optional[list[str]] = None,
    *,
    max_items: int = 3,
    filter_prefix: str = "【本文系数据通用户提前专享】",
) -> list[str]:
    """列表版要闻裁剪（逐条去前缀后取前 max_items 条）。"""
    if not news_list:
        return []
    cleaned = [(ln or "").replace(filter_prefix, "").strip() for ln in news_list]
    cleaned = [x for x in cleaned if x]
    return cleaned[:max_items]


def build_kpi_card_html(kpi: dict[str, Any]) -> str:
    """数据 KPI：涨停/跌停/炸板率/溢价 2×2 网格。"""
    if not kpi:
        return ""
    zt = kpi.get("zt_count")
    dt = kpi.get("dt_count")
    zb = kpi.get("zhaban_rate")
    prem = kpi.get("premium")
    prem_note = kpi.get("premium_note") or ""

    def cell(label: str, val_html: str, *, accent: str = "#0f172a") -> str:
        return (
            f'<td width="50%" style="padding:10px 12px;vertical-align:top;border:1px solid #e2e8f0;'
            f'background:#ffffff;">'
            f'<div style="font-size:22px;font-weight:700;color:{accent};line-height:1.2;">{val_html}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-top:6px;letter-spacing:0.04em;">{html.escape(label)}</div>'
            f"</td>"
        )

    zt_html = f'<span style="color:#15803d;">{html.escape(str(zt))}</span>'
    dt_html = f'<span style="color:#b91c1c;">{html.escape(str(dt))}</span>'
    zb_html = html.escape(f"{zb}%" if zb is not None else "—")
    if prem is not None:
        pcol = "#15803d" if float(prem) > 0 else "#64748b"
        prem_html = f'<span style="color:{pcol};">{html.escape(str(prem))}</span>'
        if prem_note:
            prem_html += f' <span style="font-size:11px;color:#94a3b8;">{html.escape(str(prem_note))}</span>'
    else:
        prem_html = html.escape(str(prem_note) or "—")

    return (
        '<div style="margin:0 0 16px;padding:0;">'
        '<div style="font-size:11px;font-weight:700;color:#64748b;letter-spacing:0.08em;margin:0 0 10px;">'
        "MARKET KPI · 程序侧快照</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;">'
        "<tr>"
        + cell("涨停家数", zt_html, accent="#15803d")
        + cell("跌停家数", dt_html, accent="#b91c1c")
        + "</tr><tr>"
        + cell("炸板率", zb_html)
        + cell("昨日涨停溢价", prem_html)
        + "</tr></table></div>"
    )


def strip_first_summary_line(md: str) -> str:
    """去掉正文里首条【摘要】行（若需与页头模块去重时由调用方使用）。"""
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
    在 Markdown 转 HTML 正文前追加：报告主标题区、程序 KPI 卡、连板梯队模块、报告说明段。
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
        '<div style="margin:0 0 18px;padding:18px 20px;border-radius:12px;border:1px solid #e2e8f0;'
        'background:linear-gradient(165deg,#f1f5f9 0%,#ffffff 60%);">'
        '<div style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#64748b;margin-bottom:8px;">'
        "Market review · 系统生成</div>"
        f'<div style="font-size:20px;font-weight:700;color:#0f172a;line-height:1.25;letter-spacing:-0.02em;">{title}</div>'
        f'<div style="font-size:13px;color:#64748b;margin-top:10px;">{sub}</div>'
        "</div>"
    ]

    kpi_html = build_kpi_card_html(ev.get("email_kpi") or {})
    if kpi_html:
        parts.append(kpi_html)

    ladder_html = build_ladder_distribution_email_html(ev.get("email_dragon_meta"))
    if ladder_html:
        parts.append(ladder_html)

    parts.append(
        '<p style="margin:0 0 20px;font-size:13px;color:#475569;line-height:1.65;border-left:4px solid #94a3b8;'
        'padding:12px 14px;background:#f8fafc;border-radius:0 8px 8px 0;">'
        "<strong style=\"color:#0f172a;\">报告说明</strong>：正文由<strong>程序侧数据</strong>（交易日历、行情与规则、龙头池、"
        "<strong>近5日连板梯队对比</strong>与标签等）"
        "与<strong>DeepSeek 大模型</strong>在固定章节结构下共同生成，通常依次包含：<strong>周期与情绪</strong>、"
        "<strong>核心股与明日预案</strong>、<strong>风险</strong>等。"
        "文中表格、列表与代码块仅用于展示数据与逻辑，<strong>不构成投资建议</strong>；请结合自身情况独立决策。"
        "</p>"
    )
    return "\n".join(parts)


def build_ladder_distribution_email_html(
    meta: Optional[dict[str, Any]] = None,
) -> str:
    """
    邮件内嵌：近 5 日连板历史表 + 当日梯队条形示意（邮件安全 table/div）。
    """
    if not meta:
        return ""
    hist = meta.get("ladder_history_5d") or []
    if not hist:
        return ""
    trend = html.escape(str(meta.get("ladder_trend") or ""))
    rows_html: list[str] = []
    for r in hist:
        lad = r.get("ladder") or {}
        ge5 = sum(int(lad[k]) for k in lad if int(k) >= 5)
        rows_html.append(
            "<tr>"
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;font-size:12px;">{html.escape(str(r.get("date", "")))}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{r.get("total_zt", 0)}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{r.get("multi_board_sum", 0)}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{lad.get(2, 0)}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{lad.get(3, 0)}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{lad.get(4, 0)}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:right;">{ge5}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:6px 8px;text-align:center;">{r.get("max_lb", 0)}板</td>'
            "</tr>"
        )
    last = hist[-1]
    lad0 = last.get("ladder") or {}
    tot = int(last.get("total_zt") or 0) or 1
    levels = [
        ("2 连板", int(lad0.get(2, 0))),
        ("3 连板", int(lad0.get(3, 0))),
        ("4 连板", int(lad0.get(4, 0))),
        ("5 连及以上", sum(int(lad0[k]) for k in lad0 if int(k) >= 5)),
    ]
    mx = max((x[1] for x in levels), default=1)
    bars: list[str] = []
    for label, cnt in levels:
        w = min(100, int(round(cnt / mx * 100))) if mx else 0
        pct_tot = round(cnt / tot * 100, 1) if tot else 0.0
        bars.append(
            '<tr><td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:12px;white-space:nowrap;">'
            f"{html.escape(label)}</td>"
            '<td style="padding:4px 8px;border:1px solid #e2e8f0;">'
            f'<div style="height:14px;background:#e2e8f0;border-radius:4px;overflow:hidden;max-width:100%;">'
            f'<div style="height:14px;width:{w}%;background:linear-gradient(90deg,#2563eb,#38bdf8);"></div></div>'
            f'</td><td style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;font-size:12px;">'
            f"{cnt} 只（占涨停 {pct_tot}%）</td></tr>"
        )
    return (
        '<div style="margin:0 0 18px;padding:16px 18px;border-radius:12px;border:1px solid #c7d2fe;'
        'background:linear-gradient(165deg,#f8fafc 0%,#ffffff 100%);">'
        '<div style="font-size:11px;font-weight:700;color:#3730a3;letter-spacing:0.06em;margin:0 0 10px;">'
        "LADDER · 连板梯队历史对比</div>"
        f'<p style="margin:0 0 10px;font-size:12px;color:#475569;">情绪倾向：<strong>{trend}</strong></p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;font-size:12px;margin:0 0 14px;">'
        "<thead><tr>"
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">日期</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">涨停</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">≥2连</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">2</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">3</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">4</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">5+</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">最高</th>'
        "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
        '<div style="font-size:11px;font-weight:700;color:#64748b;margin:0 0 8px;">'
        "当日梯队分布（条形长度为相对值，便于一眼对比）</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;font-size:12px;">'
        "<thead><tr>"
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;width:26%;">梯队</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;">图示</th>'
        '<th style="border:1px solid #e2e8f0;padding:6px 8px;background:#f1f5f9;width:22%;">数量</th>'
        "</tr></thead><tbody>"
        + "".join(bars)
        + "</tbody></table></div>"
    )


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
            "· 正文：DeepSeek 按固定章节输出，为 Markdown 结构；",
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
    _now = datetime.now().strftime("%Y-%m-%d %H:%M")
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
        "footer_generated_at": ev.get("footer_generated_at", _now),
        "show_intel_badge": ev.get("show_intel_badge", True),
        "intel_badge_text": ev.get("intel_badge_text", "INTERNAL INTELLIGENCE REPORT"),
        "footer_show_nav": ev.get("footer_show_nav", False),
        "content_prefix_html": ev.get("content_prefix_html", ""),
    }
    ctx.update({k: v for k, v in ev.items() if k not in ctx})
    tpl = _env.get_template("email_base.html")
    return tpl.render(**ctx)


def render_email(
    content_md: str,
    subject: str,
    template_name: str = "email_base.html",
    extra_vars: Optional[dict[str, Any]] = None,
) -> str:
    """Markdown 全文 → 邮件安全 HTML → 套统一 base（可换模板名做 A/B）。"""
    inner = markdown_to_email_html(content_md or "")
    ev = dict(extra_vars or {})
    if template_name and template_name != "email_base.html":
        tpl = _env.get_template(template_name)
        return tpl.render(content_html=inner, title=ev.get("title") or subject, **ev)
    return render_email_template(inner, subject, ev)


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

