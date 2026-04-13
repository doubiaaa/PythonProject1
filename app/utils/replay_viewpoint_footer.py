# -*- coding: utf-8 -*-
"""复盘正文末尾固定区块：名家框架表格式温习（Markdown；不再内嵌流程图 PNG）。"""

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

# 与 replay_footer_commentary 中条目顺序一致（仅 cid）
FOOTER_SECTION_ORDER: tuple[str, ...] = (
    "replay_footer_yangjia",
    "replay_footer_tuixue",
    "replay_viewpoint_footer_asking",
    "replay_footer_kebi",
    "replay_footer_niepan",
)

# 兼容旧资产路径（首图等）；邮件正文不再引用这些 CID。
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

# 文末区块在邮件 / Markdown 中的总标题
FOOTER_SECTION_TITLE = "每日必看 吾日三省吾身"

# 每周温习独立邮件的文档标题（与每日复盘文末小标题区分）
THEORY_REVIEW_DOC_TITLE = "每周温习 · 五人理论 + 架构目标"

def _six_layers_weekly_block() -> str:
    """周六温习邮件专用：六层架构表 + 与之一致的六点说明。"""
    return (
        "## 演进目标：企业级六层架构（新标准）\n\n"
        "| 层次 | 职责 |\n"
        "|------|------|\n"
        "| 1 接口层（Adapter） | 所有外部数据源统一收口 |\n"
        "| 2 领域层（Domain） | 纯业务模型，不依赖任何框架 |\n"
        "| 3 服务层（Service） | 业务逻辑，无副作用 |\n"
        "| 4 编排层（Orchestration） | 流程控制 |\n"
        "| 5 输出层（Output） | 报告、邮件、渲染 |\n"
        "| 6 基础设施层（Infra） | 日志、缓存、配置、监控 |\n\n"
        "1. **接口层（Adapter）** —— 所有外部数据源统一收口  \n"
        "2. **领域层（Domain）** —— 纯业务模型，不依赖任何框架  \n"
        "3. **服务层（Service）** —— 业务逻辑，无副作用  \n"
        "4. **编排层（Orchestration）** —— 流程控制  \n"
        "5. **输出层（Output）** —— 报告、邮件、渲染  \n"
        "6. **基础设施层（Infra）** —— 日志、缓存、配置、监控  \n\n"
        "> 分层说明与迁移路线见仓库 `docs/six_layer_architecture.md`。\n\n"
        "---\n\n"
    )


def _build_footer_blocks_only() -> str:
    """表格式名家框架 + 附录（不含复盘正文前缀）。"""
    sections: list[str] = []
    for cid in FOOTER_SECTION_ORDER:
        extra = COMMENTARY_MARKDOWN_BY_CID.get(cid)
        if extra:
            sections.append(extra.strip())
    if not sections:
        return ""
    sep = "\n\n---\n\n"
    header = f"## {FOOTER_SECTION_TITLE}\n\n"
    return header + sep.join(sections) + FOOTER_BOTTOM_SUMMARY_MARKDOWN.rstrip() + "\n"


def build_theory_review_markdown() -> str:
    """
    每周温习邮件专用：先六层架构表，再五人理论表格式全文（与 append_replay_viewpoint_footer 一致）。
    """
    body = _build_footer_blocks_only()
    if not body:
        return ""
    intro = (
        f"# {THEORY_REVIEW_DOC_TITLE}\n\n"
        "> 固定于每周六发送：巩固 **企业级六层架构目标**，并以 **表格**温习 **炒股养家、退学炒股、Asking、92科比、涅槃重升** "
        "框架（与日复盘文末「每日必看」一致，无流程图）。\n\n"
    )
    arch = _six_layers_weekly_block()
    return intro + arch + body


def replay_footer_inline_images_weekly() -> Optional[list[tuple[str, str]]]:
    """表格式正文不再内嵌 PNG；返回 None 以减小邮件体积、避免客户端缩放失真。"""
    return None


def replay_viewpoint_footer_image_path() -> str:
    """兼容旧调用：当前列表第一张图路径。"""
    return os.path.join(_PROJECT_ROOT, "assets", FOOTER_CHART_ENTRIES[0][0])


def replay_viewpoint_footer_asking_image_path() -> str:
    return os.path.join(
        _PROJECT_ROOT, "assets", "replay_viewpoint_footer_asking.png"
    )


def append_replay_viewpoint_footer(md: str) -> str:
    """在 Markdown 文末追加分隔线、表格式温习与底部附录。"""
    body = _build_footer_blocks_only()
    if not body:
        return md or ""
    sep = "\n\n---\n\n"
    return (md or "").rstrip() + sep + body


def replay_footer_inline_images() -> Optional[list[tuple[str, str]]]:
    """表格式文末不再附带 inline PNG。"""
    return None
