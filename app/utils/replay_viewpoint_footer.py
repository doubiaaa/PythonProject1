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
THEORY_REVIEW_DOC_TITLE = "每周温习 · 五人理论 + 架构目标"

# 仅周六温习邮件：六层架构示意图（非日复盘文末）
SIX_LAYERS_ASSET = "architecture_six_layers.png"
SIX_LAYERS_CID = "architecture_six_layers"


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


def _six_layers_weekly_block() -> str:
    """周六温习邮件专用：架构图 + 与图示一致的六点（需 assets 下 PNG 与 CID 同时存在）。"""
    p = os.path.join(_PROJECT_ROOT, "assets", SIX_LAYERS_ASSET)
    if not os.path.isfile(p):
        return ""
    return (
        "## 演进目标：企业级六层架构（新标准）\n\n"
        f"![企业级六层架构：Adapter / Domain / Service / Orchestration / Output / Infra](cid:{SIX_LAYERS_CID})\n\n"
        "1. **接口层（Adapter）** —— 所有外部数据源统一收口  \n"
        "2. **领域层（Domain）** —— 纯业务模型，不依赖任何框架  \n"
        "3. **服务层（Service）** —— 业务逻辑，无副作用  \n"
        "4. **编排层（Orchestration）** —— 流程控制  \n"
        "5. **输出层（Output）** —— 报告、邮件、渲染  \n"
        "6. **基础设施层（Infra）** —— 日志、缓存、配置、监控  \n\n"
        "> 分层说明与迁移路线见仓库 `docs/six_layer_architecture.md`。\n\n"
        "---\n\n"
    )


def build_theory_review_markdown() -> str:
    """
    每周温习邮件专用：先六层架构（若有图），再五人理论 Markdown 全文（含 CID 图与附录）。
    与 append_replay_viewpoint_footer 中五人块一致；日复盘不调用本函数中的架构块。
    """
    body = _build_footer_blocks_only()
    if not body:
        return ""
    intro = (
        f"# {THEORY_REVIEW_DOC_TITLE}\n\n"
        "> 固定于每周六发送：巩固 **企业级六层架构目标**，并温习 **炒股养家、退学炒股、Asking、92科比、涅槃重升** "
        "框架（五人图与文末「每日必看」一致）。\n\n"
    )
    arch = _six_layers_weekly_block()
    return intro + arch + body


def replay_footer_inline_images_weekly() -> Optional[list[tuple[str, str]]]:
    """周六温习邮件：五人图 CID + 六层架构图（若存在）。"""
    base = list(replay_footer_inline_images() or [])
    p6 = os.path.join(_PROJECT_ROOT, "assets", SIX_LAYERS_ASSET)
    if os.path.isfile(p6):
        base.insert(0, (SIX_LAYERS_CID, p6))
    return base if base else None


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
