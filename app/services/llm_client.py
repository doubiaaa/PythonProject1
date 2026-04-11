# -*- coding: utf-8 -*-
"""
大模型 Chat Completions（OpenAI 兼容）：DeepSeek。
超时、传输重试、429 指数退避。参数来自统一配置（replay_config / 环境变量）。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

import requests

from app.utils.logger import get_logger

_log = get_logger(__name__)

_llm_spacing_lock = threading.Lock()
_last_llm_monotonic = 0.0


def _apply_llm_spacing() -> None:
    """配置项 resilience.llm_min_interval_sec：两次 LLM 请求最小间隔。"""
    global _last_llm_monotonic
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    res = cm.config.get("resilience") or {}
    if not isinstance(res, dict):
        return
    gap = float(res.get("llm_min_interval_sec") or 0)
    if gap <= 0:
        return
    with _llm_spacing_lock:
        now = time.monotonic()
        wait = gap - (now - _last_llm_monotonic)
        if wait > 0:
            time.sleep(wait)
        _last_llm_monotonic = time.monotonic()


def _read_timeouts(ds_cfg: dict[str, Any]) -> tuple[float, float]:
    """连接/读取超时（`data_source.llm_*`）。"""
    return (
        float(ds_cfg.get("llm_connect_timeout", 10)),
        float(ds_cfg.get("llm_read_timeout", 120)),
    )


class ChatCompletionClient:
    """OpenAI 兼容 POST …/chat/completions（DeepSeek）。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        model: str,
        timeout: float | tuple[float, float],
        transport_retries: int,
        retry_429: int,
        retry_429_wait_sec: int,
        retry_429_wait_max_sec: int,
        default_temperature: float,
        default_max_tokens: int,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.strip()
        self.model = model
        self.timeout = timeout
        self._transport_retries = max(1, int(transport_retries))
        self._retry_429 = max(0, int(retry_429))
        self._retry_429_wait_sec = max(5, int(retry_429_wait_sec))
        self._retry_429_wait_max_sec = max(30, int(retry_429_wait_max_sec))
        self._default_temperature = float(default_temperature)
        self._default_max_tokens = int(default_max_tokens)

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

    def _post_with_transport_retry(self, payload: dict[str, Any]) -> requests.Response:
        last_err: Optional[BaseException] = None
        for attempt in range(self._transport_retries):
            try:
                return self._post_once(payload)
            except (requests.Timeout, requests.ConnectionError) as e:
                last_err = e
                if attempt >= self._transport_retries - 1:
                    raise
                time.sleep(3)
        assert last_err is not None
        raise last_err

    def chat_completion(
        self,
        user_content: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        if temperature is None:
            temperature = self._default_temperature
        if max_tokens is None:
            max_tokens = self._default_max_tokens
        _apply_llm_spacing()
        from app.infrastructure.resilience import get_circuit

        cb = get_circuit("llm_http")
        if not cb.allow_request():
            return (
                "【系统】大模型 HTTP 熔断中（连续失败过多），请约 1～2 分钟后再试。"
            )

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
                cb.record_failure()
                return f"调用大模型 API 异常：{e!s}"
            except requests.RequestException as e:
                cb.record_failure()
                return f"调用大模型 API 异常：{e!s}"

            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError:
                    cb.record_failure()
                    return "API 返回异常：非 JSON"
                choices = result.get("choices") or []
                if not choices:
                    cb.record_failure()
                    return "API 返回异常：无 choices 字段"
                msg = (choices[0].get("message") or {}).get("content")
                if msg is None:
                    cb.record_failure()
                    return "API 返回异常：无 content"
                cb.record_success()
                return str(msg)

            if response.status_code == 429 and attempt_429 < self._retry_429:
                attempt_429 += 1
                exp = int(self._retry_429_wait_sec * (2 ** max(0, attempt_429 - 1)))
                wait = min(exp, self._retry_429_wait_max_sec)
                try:
                    ra = response.headers.get("Retry-After")
                    if ra is not None:
                        wait = max(wait, int(float(ra)))
                except (TypeError, ValueError):
                    pass
                wait = min(wait, self._retry_429_wait_max_sec)
                _log.warning(
                    "大模型 API 429（限速），第 %s/%s 次退避，等待 %ss 后重试",
                    attempt_429,
                    self._retry_429,
                    wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 402:
                cb.record_failure()
                return "错误：大模型 API 账户余额不足，请充值后重试。"
            if response.status_code == 429:
                cb.record_failure()
                return (
                    "调用大模型 API：速率限制（429），已多次退避仍失败。"
                    "请稍后重试或检查控制台配额。"
                    f"\n\n原始响应：{response.text}"
                )
            cb.record_failure()
            return f"API请求失败（{response.status_code}）：{response.text}"


def get_llm_client(api_key: str = "") -> ChatCompletionClient:
    """组装 DeepSeek 客户端；模型默认 deepseek-chat。"""
    from app.utils.config import ConfigManager

    cm = ConfigManager()
    ds_cfg = cm.get("data_source") or {}
    if not isinstance(ds_cfg, dict):
        ds_cfg = {}
    conn, read = _read_timeouts(ds_cfg)
    timeout: float | tuple[float, float] = (conn, read)

    key = (api_key or "").strip()
    if not key:
        key = (cm.get("deepseek_api_key") or cm.get("llm_api_key") or "").strip()

    if not key:
        raise ValueError("未配置大模型 API Key（deepseek_api_key 或请求传入 api_key）")

    custom_base = (cm.get("llm_api_base") or "").strip()
    default_url = (cm.get("llm_default_url") or "").strip()
    base = custom_base or default_url or "https://api.deepseek.com/v1/chat/completions"
    model = (
        (cm.get("llm_model_name") or cm.get("deepseek_model_name") or "").strip()
        or "deepseek-chat"
    )

    return ChatCompletionClient(
        api_key=key,
        base_url=base,
        model=model,
        timeout=timeout,
        transport_retries=int(cm.get("llm_retry_attempts", 3)),
        retry_429=int(cm.get("llm_retry_429", 6)),
        retry_429_wait_sec=int(cm.get("llm_retry_429_wait_sec", 30)),
        retry_429_wait_max_sec=int(cm.get("llm_retry_429_wait_max_sec", 180)),
        default_temperature=float(cm.get("llm_chat_default_temperature", 0.42)),
        default_max_tokens=int(cm.get("llm_chat_default_max_tokens", 6144)),
    )
