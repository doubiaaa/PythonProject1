# -*- coding: utf-8 -*-
"""
兼容入口：大模型调用已迁移至 `llm_client`（默认 DeepSeek OpenAI 兼容接口）。
"""
from app.services.llm_client import (  # noqa: F401
    ChatCompletionClient,
    ZhipuClient,
    get_llm_client,
)

__all__ = ["ChatCompletionClient", "ZhipuClient", "get_llm_client"]
