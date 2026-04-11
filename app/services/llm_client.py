# -*- coding: utf-8 -*-
"""
大模型 Chat Completions（OpenAI 兼容）：默认 DeepSeek，可选智谱。
超时、传输重试、429 指数退避。
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app.utils.logger import get_logger

_log = get_logger(__name__)

DEEPSEEK_DEFAULT_URL = os.environ.get(
    "DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"
)
ZHIPU_DEFAULT_URL = os.environ.get(
    "ZHIPU_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"
)
DEFAULT_TIMEOUT = float(os.environ.get("LLM_TIMEOUT_SEC", "120"))
LLM_RETRIES = max(1, int(os.environ.get("LLM_RETRY_ATTEMPTS", "3")))
# 兼容旧环境变量名 ZHIPU_RETRY_*
LLM_429_RETRIES = max(
    0,
    int(
        os.environ.get("LLM_RETRY_429")
        or os.environ.get("ZHIPU_RETRY_429")
        or "6"
    ),
)
LLM_429_WAIT_SEC = max(
    5,
    int(os.environ.get("LLM_RETRY_429_WAIT_SEC") or os.environ.get("ZHIPU_RETRY_429_WAIT_SEC") or "30"),
)
LLM_429_WAIT_MAX_SEC = max(
    30,
    int(
        os.environ.get("LLM_RETRY_429_WAIT_MAX_SEC")
        or os.environ.get("ZHIPU_RETRY_429_WAIT_MAX_SEC")
        or "180"
    ),
)


class ChatCompletionClient:
    """OpenAI 兼容 POST /v1/chat/completions（DeepSeek、智谱等）。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        model: str,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.strip()
        self.model = model
        self.timeout = timeout

    def _post_once(self, payload: dict[str, Any]) -> requests.Response:
        return requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )

    @retry(
        stop=stop_after_attempt(LLM_RETRIES),
        wait=wait_fixed(3),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _post_with_transport_retry(self, payload: dict[str, Any]) -> requests.Response:
        return self._post_once(payload)

    def chat_completion(
        self,
        user_content: str,
        *,
        temperature: float = 0.42,
        max_tokens: int = 6144,
    ) -> str:
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        attempt_429 = 0
        while True:
            try:
                response = self._post_with_transport_retry(data)
            except (requests.Timeout, requests.ConnectionError) as e:
                _log.warning("大模型请求传输失败（已重试）：%s", e)
                return f"调用大模型 API 异常：{e!s}"
            except requests.RequestException as e:
                return f"调用大模型 API 异常：{e!s}"

            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError:
                    return "API 返回异常：非 JSON"
                choices = result.get("choices") or []
                if not choices:
                    return "API 返回异常：无 choices 字段"
                msg = (choices[0].get("message") or {}).get("content")
                if msg is None:
                    return "API 返回异常：无 content"
                return str(msg)

            if response.status_code == 429 and attempt_429 < LLM_429_RETRIES:
                attempt_429 += 1
                exp = int(LLM_429_WAIT_SEC * (2 ** max(0, attempt_429 - 1)))
                wait = min(exp, LLM_429_WAIT_MAX_SEC)
                try:
                    ra = response.headers.get("Retry-After")
                    if ra is not None:
                        wait = max(wait, int(float(ra)))
                except (TypeError, ValueError):
                    pass
                wait = min(wait, LLM_429_WAIT_MAX_SEC)
                _log.warning(
                    "大模型 API 429（限速），第 %s/%s 次退避，等待 %ss 后重试",
                    attempt_429,
                    LLM_429_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 402:
                return "错误：大模型 API 账户余额不足，请充值后重试。"
            if response.status_code == 429:
                return (
                    "调用大模型 API：速率限制（429），已多次退避仍失败。"
                    "请稍后重试或检查控制台配额。"
                    f"\n\n原始响应：{response.text}"
                )
            return f"API请求失败（{response.status_code}）：{response.text}"


def get_llm_client(api_key: str = "") -> ChatCompletionClient:
    """
    按配置组装客户端：默认 deepseek（deepseek-chat），llm_provider=zhipu 时用智谱。
    """
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    provider = (cm.get("llm_provider") or "deepseek").strip().lower()
    ds_cfg = cm.get("data_source") or {}
    conn = float(ds_cfg.get("zhipu_connect_timeout", 10))
    read = float(ds_cfg.get("zhipu_read_timeout", 120))
    timeout = (conn, read)

    key = (api_key or "").strip()
    if not key:
        if provider == "zhipu":
            key = (cm.get("zhipu_api_key") or "").strip()
        else:
            key = (
                cm.get("deepseek_api_key") or cm.get("llm_api_key") or cm.get("zhipu_api_key") or ""
            ).strip()

    if not key:
        raise ValueError("未配置大模型 API Key（deepseek_api_key 或请求传入 api_key）")

    custom_base = (cm.get("llm_api_base") or "").strip()

    if provider == "zhipu":
        base = custom_base or ZHIPU_DEFAULT_URL
        model = (
            (cm.get("zhipu_model_name") or cm.get("llm_model_name") or "").strip()
            or "glm-4-flash"
        )
    else:
        base = custom_base or DEEPSEEK_DEFAULT_URL
        model = (
            (cm.get("llm_model_name") or cm.get("deepseek_model_name") or "").strip()
            or "deepseek-chat"
        )

    return ChatCompletionClient(api_key=key, base_url=base, model=model, timeout=timeout)


# 兼容旧代码
ZhipuClient = ChatCompletionClient
