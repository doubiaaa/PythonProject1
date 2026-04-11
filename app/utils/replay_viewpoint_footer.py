# -*- coding: utf-8 -*-
"""复盘正文末尾固定附图：认清并战胜内心的「小明」（心智框架图）。"""

from __future__ import annotations

import os
from typing import Optional

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
FOOTER_IMAGE_REL = os.path.join("assets", "replay_viewpoint_footer.png")
FOOTER_IMAGE_CID = "replay_viewpoint_footer"


def replay_viewpoint_footer_image_path() -> str:
    return os.path.join(_PROJECT_ROOT, FOOTER_IMAGE_REL)


def append_replay_viewpoint_footer(md: str) -> str:
    """在 Markdown 文末追加分隔线与附图（邮件 HTML 用 cid 内嵌）。"""
    p = replay_viewpoint_footer_image_path()
    if not os.path.isfile(p):
        return md or ""
    block = (
        "\n\n---\n\n"
        f"![认清并战胜内心的「小明」——人性弱点与退神之道](cid:{FOOTER_IMAGE_CID})\n"
    )
    return (md or "").rstrip() + block


def replay_footer_inline_images() -> Optional[list[tuple[str, str]]]:
    """供 send_report_email(inline_images=...) 使用；资源缺失时返回 None。"""
    p = replay_viewpoint_footer_image_path()
    if not os.path.isfile(p):
        return None
    return [(FOOTER_IMAGE_CID, p)]
