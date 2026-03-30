# -*- coding: utf-8 -*-
"""
磁盘 JSON 缓存：按 key 存取，用 mtime 判断 TTL（默认 1 天）。
用于同日多次复盘减少对行情接口的重复请求。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_DEFAULT_DIR = os.path.join(_PROJECT_ROOT, "data", "api_cache")


def _safe_key(key: str) -> str:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", key)[:80]
    return f"{safe}_{h}"


def cache_dir() -> str:
    return _DEFAULT_DIR


def get_json(key: str, ttl_sec: int, *, cache_root: Optional[str] = None) -> Optional[Any]:
    root = cache_root or _DEFAULT_DIR
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, _safe_key(key) + ".json")
    if not os.path.isfile(path):
        return None
    if ttl_sec > 0 and (time.time() - os.path.getmtime(path)) > ttl_sec:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def set_json(key: str, payload: Any, *, cache_root: Optional[str] = None) -> None:
    root = cache_root or _DEFAULT_DIR
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, _safe_key(key) + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def df_to_payload(df) -> dict[str, Any]:
    import pandas as pd

    if df is None:
        return {"empty": True, "columns": [], "records": []}
    if getattr(df, "empty", True):
        return {"empty": True, "columns": list(getattr(df, "columns", [])), "records": []}
    return {
        "empty": False,
        "columns": [str(c) for c in df.columns],
        "records": df.to_dict(orient="records"),
    }


def payload_to_df(payload: dict[str, Any]):
    import pandas as pd

    if not payload or payload.get("empty"):
        return pd.DataFrame()
    cols = payload.get("columns") or []
    recs = payload.get("records") or []
    return pd.DataFrame(recs, columns=cols)
