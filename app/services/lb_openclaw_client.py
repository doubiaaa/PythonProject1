# -*- coding: utf-8 -*-
"""
悟道 OpenClaw HTTP 客户端（https://stock.quicktiny.cn/api/openclaw）。

环境变量：LB_API_KEY、LB_API_BASE（可选，默认官方 Base）。
配置：data_source.use_lb_openclaw、data_source.lb_api_key、data_source.lb_api_base

成功响应多为 { success, data }，本模块对调用方返回 **data** 载荷（dict/list）。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

from app.utils.logger import get_logger

_log = get_logger(__name__)

DEFAULT_LB_BASE = "https://stock.quicktiny.cn/api/openclaw"


def _data_source_dict() -> dict[str, Any]:
    try:
        from app.utils.config import ConfigManager

        ds = ConfigManager().get("data_source")
        return ds if isinstance(ds, dict) else {}
    except Exception:
        return {}


def get_lb_api_key() -> str:
    return (os.environ.get("LB_API_KEY") or "").strip() or str(
        _data_source_dict().get("lb_api_key") or ""
    ).strip()


def get_lb_api_base() -> str:
    b = (
        (os.environ.get("LB_API_BASE") or "").strip()
        or str(_data_source_dict().get("lb_api_base") or "").strip()
        or DEFAULT_LB_BASE
    )
    return b.rstrip("/")


def is_lb_openclaw_enabled() -> bool:
    ds = _data_source_dict()
    if not ds.get("use_lb_openclaw"):
        return False
    return bool(get_lb_api_key())


def lb_get(
    path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: Optional[float] = None,
) -> Any:
    """
    GET JSON，返回解析后的 **data**（若顶层含 success/data）；否则返回整棵 JSON。
    """
    key = get_lb_api_key()
    if not key:
        raise RuntimeError("LB_API_KEY 未配置")

    base = get_lb_api_base()
    p = path if path.startswith("/") else f"/{path}"
    url = f"{base}{p}"
    if timeout is None:
        try:
            timeout = float(_data_source_dict().get("timeout") or 15)
        except Exception:
            timeout = 15.0

    r = requests.get(
        url,
        params=params or {},
        headers={"Authorization": f"Bearer {key}"},
        timeout=(min(10.0, timeout), timeout),
    )
    r.raise_for_status()
    j = r.json()
    if isinstance(j, dict):
        if j.get("success") is False:
            msg = j.get("message") or j.get("error") or "LB API error"
            raise RuntimeError(str(msg))
        if "data" in j:
            return j["data"]
    return j


def lb_get_safe(
    path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: Optional[float] = None,
) -> Optional[Any]:
    """同 `lb_get`，失败时返回 None 并打日志，供复盘扩展块逐项容错。"""
    try:
        return lb_get(path, params, timeout=timeout)
    except Exception as ex:
        _log.debug("LB 请求跳过 %s %s: %s", path, params, ex)
        return None
