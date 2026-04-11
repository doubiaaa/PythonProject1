# -*- coding: utf-8 -*-
"""复盘正文末尾固定附图：心智框架图系列（邮件 CID 内嵌）。"""

from __future__ import annotations

import os
from typing import Optional

from app.utils.replay_footer_commentary import (
    COMMENTARY_MARKDOWN_BY_CID,
    FOOTER_BOTTOM_SUMMARY_MARKDOWN,
)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

# (相对 assets 的文件名, CID, Markdown 替代文字)
# 顺序：炒股养家 → 退学炒股 → Asking → 92科比 → 涅槃重升
FOOTER_CHART_ENTRIES: tuple[tuple[str, str, str], ...] = (
    (
        "replay_footer_yangjia.png",
        "replay_footer_yangjia",
        "炒股养家·情绪与风险收益",
    ),
    (
        "replay_footer_tuixue.png",
        "replay_footer_tuixue",
        "退学炒股·性格与标的纪律",
    ),
    (
        "replay_viewpoint_footer_asking.png",
        "replay_viewpoint_footer_asking",
        "人气股与龙头认知——五大误区与 Asking 之道",
    ),
    (
        "replay_footer_kebi.png",
        "replay_footer_kebi",
        "92科比·龙头-补涨-切换-空仓与情绪周期",
    ),
    (
        "replay_footer_niepan.png",
        "replay_footer_niepan",
        "涅槃重升·树干与情绪",
    ),
)

# 文末附图区块在邮件/ Markdown 中的总标题
FOOTER_SECTION_TITLE = "每日必看 吾日三省吾身"

# 每周温习独立邮件的文档标题（与每日复盘文末小标题区分）
THEORY_REVIEW_DOC_TITLE = "每周温习 · 五人理论框架"


def _build_footer_blocks_only() -> str:
    """附图 + 图下解读 + 附录（不含复盘正文前缀）。"""
    sections: list[str] = []
    for rel, cid, alt in FOOTER_CHART_ENTRIES:
        p = os.path.join(_PROJECT_ROOT, "assets", rel)
        if not os.path.isfile(p):
            continue
        chunk = [f"![{alt}](cid:{cid})"]
        extra = COMMENTARY_MARKDOWN_BY_CID.get(cid)
        if extra:
            chunk.append(extra.strip())
        sections.append("\n\n".join(chunk))
    if not sections:
        return ""
    sep = "\n\n---\n\n"
    header = f"## {FOOTER_SECTION_TITLE}\n\n"
    return header + sep.join(sections) + FOOTER_BOTTOM_SUMMARY_MARKDOWN.rstrip() + "\n"


def build_theory_review_markdown() -> str:
    """
    每周温习邮件专用：五人理论 Markdown 全文（含 CID 图与附录）。
    与 append_replay_viewpoint_footer 中追加块一致，另加文档级标题与说明。
    """
    body = _build_footer_blocks_only()
    if not body:
        return ""
    intro = (
        f"# {THEORY_REVIEW_DOC_TITLE}\n\n"
        "> 固定于每周六发送，用于巩固 **炒股养家、退学炒股、Asking、92科比、涅槃重升** "
        "的核心框架（与复盘文末「每日必看」内容一致）。\n\n"
    )
    return intro + body


def replay_viewpoint_footer_image_path() -> str:
    """兼容旧调用：当前列表第一张图路径。"""
    return os.path.join(_PROJECT_ROOT, "assets", FOOTER_CHART_ENTRIES[0][0])


def replay_viewpoint_footer_asking_image_path() -> str:
    return os.path.join(
        _PROJECT_ROOT, "assets", "replay_viewpoint_footer_asking.png"
    )


def append_replay_viewpoint_footer(md: str) -> str:
    """在 Markdown 文末追加分隔线、附图、图下解读与底部附录（邮件 HTML 用 cid 内嵌）。"""
    body = _build_footer_blocks_only()
    if not body:
        return md or ""
    sep = "\n\n---\n\n"
    return (md or "").rstrip() + sep + body


def replay_footer_inline_images() -> Optional[list[tuple[str, str]]]:
    """供 send_report_email(inline_images=...) 使用；仅包含磁盘上存在的图。"""
    out: list[tuple[str, str]] = []
    for rel, cid, _alt in FOOTER_CHART_ENTRIES:
        p = os.path.join(_PROJECT_ROOT, "assets", rel)
        if os.path.isfile(p):
            out.append((cid, p))
    return out if out else None
