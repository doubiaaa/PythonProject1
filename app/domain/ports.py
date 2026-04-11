# -*- coding: utf-8 -*-
"""
领域端口（Protocol）：上层只依赖抽象，具体实现放在 adapters。

注意：Market 相关端口当前与现有 DataFetcher 行为对齐；后续可拆为更细粒度接口。
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class AppConfigPort(Protocol):
    """配置读取（由 Infra/Adapter 实现）。"""

    def get(self, key: str, default: Any = None) -> Any: ...


@runtime_checkable
class MarketSummaryPort(Protocol):
    """市场摘要与程序侧元数据入口（封装原 get_market_summary 契约）。"""

    def fetch_summary(self, date: str) -> tuple[str, str]:
        """返回 (market_data_markdown, actual_trade_date)。"""
        ...


@runtime_checkable
class LLMCompletionPort(Protocol):
    """大模型补全（可替换为 DeepSeek / 其他兼容 OpenAI 的端点）。"""

    def complete(
        self,
        user_prompt: str,
        *,
        temperature: float = 0.42,
        max_tokens: int = 6144,
    ) -> str: ...


@runtime_checkable
class EmailDeliveryPort(Protocol):
    """邮件投递（SMTP 或其他渠道）。"""

    def send_markdown_report(
        self,
        smtp_cfg: dict[str, Any],
        subject: str,
        body_md: str,
        *,
        extra_vars: Optional[dict[str, Any]] = None,
        inline_images: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[bool, str]:
        """返回 (success, message)。"""
        ...
