# -*- coding: utf-8 -*-
"""
智谱 Chat Completions 封装：超时、有限次重试、返回结构校验。
"""
from __future__ import annotations

import os
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

ZHIPU_API_URL = os.environ.get(
    "ZHIPU_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"
)
DEFAULT_MODEL = os.environ.get("ZHIPU_MODEL", "glm-4-flash")
DEFAULT_TIMEOUT = float(os.environ.get("ZHIPU_TIMEOUT_SEC", "120"))
ZHIPU_RETRIES = max(1, int(os.environ.get("ZHIPU_RETRY_ATTEMPTS", "3")))


class ZhipuClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _post_once(self, payload: dict[str, Any]) -> requests.Response:
        return requests.post(
            ZHIPU_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )

    @retry(
        stop=stop_after_attempt(ZHIPU_RETRIES),
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
        """返回助手文本；HTTP 非 200 或结构异常时返回可读错误串（与旧 call_zhipu 行为兼容）。"""
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = self._post_with_transport_retry(data)
        except (requests.Timeout, requests.ConnectionError) as e:
            _log.warning("智谱请求传输失败（已重试）：%s", e)
            return f"调用智谱API异常：{e!s}"
        except requests.RequestException as e:
            return f"调用智谱API异常：{e!s}"

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
        if response.status_code == 402:
            return "错误：智谱API账户余额不足，请充值后重试。"
        return f"API请求失败（{response.status_code}）：{response.text}"
