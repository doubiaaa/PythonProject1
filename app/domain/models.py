# -*- coding: utf-8 -*-
"""领域层：与框架无关的数据结构（DTO / 值对象）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class TradeDate:
    """交易日（通常为 YYYYMMDD 字符串）。"""

    value: str


@dataclass
class ReplayEmailBundle:
    """一次复盘邮件投递所需参数（输出层 / 编排层传递）。"""

    subject: str
    body_markdown: str
    extra_vars: dict[str, Any] = field(default_factory=dict)
    inline_images: Optional[list[tuple[str, str]]] = None
