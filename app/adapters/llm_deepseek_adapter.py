# -*- coding: utf-8 -*-
"""LLM：OpenAI 兼容 Chat Completions（默认 DeepSeek），实现领域端口 LLMCompletionPort。"""

from __future__ import annotations

from app.domain.ports import LLMCompletionPort
from app.services.llm_client import get_llm_client


class DeepSeekLLMCompletionAdapter:
    """将 `get_llm_client` 封装为可注入的端口实现，便于测试替换为 Fake。"""

    __slots__ = ("_api_key", "_client")

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = get_llm_client(self._api_key)
        return self._client

    def complete(
        self,
        user_prompt: str,
        *,
        temperature: float = 0.42,
        max_tokens: int = 6144,
    ) -> str:
        client = self._ensure_client()
        return client.chat_completion(
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def llm_completion_port_from_api_key(api_key: str) -> LLMCompletionPort:
    """工厂：默认生产 DeepSeek 适配器。"""
    return DeepSeekLLMCompletionAdapter(api_key)
