"""Server酱 Turbo（微信）推送：https://sct.ftqq.com/ 支持多个 SendKey（多人收同一通知）"""

from __future__ import annotations

import os
import re
from typing import Optional

import requests

# Turbo 接口：SendKey 以 SCT 开头
SCT_API_TMPL = "https://sctapi.ftqq.com/{sendkey}.send"
# 正文过长可能被截断，保守限制
MAX_DESP_CHARS = 8000


def _split_sendkeys(blob: str) -> list[str]:
    """从一段字符串中拆出多个 key（逗号、分号、换行）。"""
    if not blob or not blob.strip():
        return []
    # 统一成分号再拆，避免 SCT 内误伤（SCT 不含逗号）
    t = blob.replace("\r", "\n").replace(",", "\n").replace(";", "\n")
    keys = [k.strip() for k in t.split("\n") if k.strip()]
    return keys


def _collect_sendkeys(sendkey: Optional[str]) -> list[str]:
    """
    合并参数与环境变量中的多个 SendKey，去重保序。
    环境变量：SERVERCHAN_SENDKEY、SERVERCHAN_SENDKEY_2、SERVERCHAN_SENDKEY_3
    """
    chunks: list[str] = []
    main = (sendkey or "").strip()
    if not main:
        main = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if main:
        chunks.append(main)
    for name in ("SERVERCHAN_SENDKEY_2", "SERVERCHAN_SENDKEY_3"):
        extra = os.environ.get(name, "").strip()
        if extra:
            chunks.append(extra)
    out: list[str] = []
    seen: set[str] = set()
    for part in chunks:
        for k in _split_sendkeys(part):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def _send_one(key: str, title: str, desp: str, timeout: float) -> tuple[bool, str]:
    url = SCT_API_TMPL.format(sendkey=key)
    try:
        r = requests.post(
            url,
            data={"title": title, "desp": desp or " "},
            timeout=timeout,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        try:
            body = r.json()
        except Exception:
            return True, "ok"
        code = body.get("code")
        if code == 0:
            return True, "ok"
        return False, str(body.get("message") or body)
    except Exception as e:
        return False, str(e)


def send_serverchan(
    sendkey: Optional[str],
    title: str,
    desp: str = "",
    *,
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """
    发送 Server酱 消息；可配置多个 SendKey，将逐一推送相同标题与正文。
    sendkey 与环境变量均可使用「逗号/分号/换行」分隔多个 key。
    全部成功返回 (True, "ok (n)")；任一失败返回 (False, 错误摘要)。
    """
    keys = _collect_sendkeys(sendkey)
    if not keys:
        return True, "skipped"
    if len(title) > 200:
        title = title[:197] + "..."
    if desp and len(desp) > MAX_DESP_CHARS:
        desp = desp[: MAX_DESP_CHARS - 20] + "\n\n…（已截断）"
    errs: list[str] = []
    for i, key in enumerate(keys):
        ok, msg = _send_one(key, title, desp, timeout)
        if not ok:
            # 日志里不打印完整 key，只显示序号
            errs.append(f"第{i + 1}个渠道: {msg}")
    if errs:
        return False, "; ".join(errs)
    return True, f"ok ({len(keys)})"


def has_serverchan_keys(sendkey: Optional[str] = None) -> bool:
    """是否配置了任意可用的 Server酱 SendKey（含环境变量 SERVERCHAN_SENDKEY / _2 / _3）。"""
    return len(_collect_sendkeys(sendkey)) > 0
