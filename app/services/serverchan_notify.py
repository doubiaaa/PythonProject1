"""Server酱 Turbo（微信）推送：https://sct.ftqq.com/"""

from __future__ import annotations

import os
from typing import Optional

import requests

# Turbo 接口：SendKey 以 SCT 开头
SCT_API_TMPL = "https://sctapi.ftqq.com/{sendkey}.send"
# 正文过长可能被截断，保守限制
MAX_DESP_CHARS = 8000


def send_serverchan(
    sendkey: Optional[str],
    title: str,
    desp: str = "",
    *,
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """
    发送 Server酱 消息。sendkey 为空则跳过，返回 (True, "skipped")。
    失败返回 (False, 错误说明)，不抛异常。
    """
    key = (sendkey or "").strip() or os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not key:
        return True, "skipped"
    if len(title) > 200:
        title = title[:197] + "..."
    if desp and len(desp) > MAX_DESP_CHARS:
        desp = desp[: MAX_DESP_CHARS - 20] + "\n\n…（已截断）"
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
