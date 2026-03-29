# -*- coding: utf-8 -*-
"""持久化每日复盘程序龙头池，供周度/月度收益统计。"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
RECORDS_FILE = os.path.join(DATA_DIR, "watchlist_records.json")

_lock = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict[str, Any]:
    if not os.path.isfile(RECORDS_FILE):
        return {"version": 1, "records": []}
    try:
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "records" not in data:
            return {"version": 1, "records": []}
        if not isinstance(data["records"], list):
            data["records"] = []
        return data
    except Exception:
        return {"version": 1, "records": []}


def _save(data: dict[str, Any]) -> None:
    _ensure_dir()
    tmp = RECORDS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RECORDS_FILE)


def append_daily_top_pool(signal_date: str, top_pool: list[dict[str, Any]]) -> None:
    """
    写入某日龙头池（来自程序 top_pool，与 AI 文案无关）。
    同一日同一代码只保留最后一次写入。
    """
    if not signal_date or len(signal_date) != 8 or not top_pool:
        return
    with _lock:
        data = _load()
        recs: list[dict[str, Any]] = [
            r
            for r in data["records"]
            if not (r.get("signal_date") == signal_date)
        ]
        for i, p in enumerate(top_pool):
            code = str(p.get("code") or "").strip()
            if not code:
                continue
            recs.append(
                {
                    "signal_date": signal_date,
                    "code": code.zfill(6)[:6],
                    "name": str(p.get("name") or ""),
                    "rank": i + 1,
                    "score": float(p.get("score") or 0),
                    "sector": str(p.get("sector") or ""),
                    "tag": str(p.get("tag") or ""),
                }
            )
        recs.sort(key=lambda x: (x["signal_date"], x["code"]))
        data["records"] = recs
        _save(data)


def load_all_records() -> list[dict[str, Any]]:
    with _lock:
        return list(_load()["records"])
