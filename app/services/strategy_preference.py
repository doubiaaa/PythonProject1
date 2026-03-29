# -*- coding: utf-8 -*-
"""
策略偏好闭环：根据龙头池历史区间收益，更新「风格权重」，供每日复盘 prompt 动态侧重。
风格桶：打板 / 低吸 / 趋势 / 龙头 / 其他（与程序标签映射）。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any

from app.services.weekly_performance import (
    SignalReturnRow,
    compute_returns_for_records,
    records_for_iso_week,
)
from app.services.watchlist_store import load_all_records

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
PREF_FILE = os.path.join(DATA_DIR, "strategy_preference.json")
LOG_FILE = os.path.join(DATA_DIR, "strategy_evolution_log.jsonl")

_lock = threading.Lock()

BUCKETS = ("打板", "低吸", "趋势", "龙头", "其他")

DEFAULT_WEIGHTS = {k: 0.2 for k in BUCKETS}


def tag_to_bucket(tag: str) -> str:
    t = (tag or "").strip()
    if not t:
        return "其他"
    if "趋势" in t or "中军" in t:
        return "趋势"
    if "活口" in t:
        return "低吸"
    if "人气" in t or "龙头" in t:
        return "龙头"
    if "板" in t or "涨停" in t:
        return "打板"
    return "其他"


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def load_strategy_preference() -> dict[str, Any]:
    _ensure_dir()
    if not os.path.isfile(PREF_FILE):
        return {
            "version": 1,
            "active": True,
            "effective_date": datetime.now().strftime("%Y%m%d"),
            "strategy_weights": dict(DEFAULT_WEIGHTS),
            "notes": "初始均匀权重",
        }
    try:
        with open(PREF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("bad shape")
        sw = data.get("strategy_weights") or {}
        for k in BUCKETS:
            sw.setdefault(k, 0.2)
        s = sum(float(sw[k]) for k in BUCKETS)
        if s <= 0:
            sw = dict(DEFAULT_WEIGHTS)
        else:
            for k in BUCKETS:
                sw[k] = float(sw[k]) / s
        data["strategy_weights"] = sw
        data.setdefault("active", True)
        data.setdefault("version", 1)
        return data
    except Exception:
        return {
            "version": 1,
            "active": True,
            "effective_date": datetime.now().strftime("%Y%m%d"),
            "strategy_weights": dict(DEFAULT_WEIGHTS),
            "notes": "读取失败回退默认",
        }


def _save_pref(data: dict[str, Any]) -> None:
    _ensure_dir()
    tmp = PREF_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREF_FILE)


def _append_log(entry: dict[str, Any]) -> None:
    _ensure_dir()
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def _suggested_weights_from_rows(rows: list[SignalReturnRow]) -> dict[str, float]:
    """可结算样本按风格桶聚合，用平均收益（平移为正）归一化为权重。"""
    by: dict[str, list[float]] = {k: [] for k in BUCKETS}
    for r in rows:
        if r.ret_pct is None or r.note != "ok":
            continue
        b = tag_to_bucket(r.tag)
        by[b].append(float(r.ret_pct))
    scores: dict[str, float] = {}
    for k in BUCKETS:
        vals = by[k]
        if not vals:
            scores[k] = 1.0
        else:
            avg = sum(vals) / len(vals)
            scores[k] = max(avg + 5.0, 0.1)
    tot = sum(scores.values())
    return {k: round(scores[k] / tot, 4) for k in BUCKETS}


def _smooth(old: dict[str, float], new: dict[str, float], alpha: float) -> dict[str, float]:
    out = {}
    for k in BUCKETS:
        out[k] = (1.0 - alpha) * old[k] + alpha * new[k]
    s = sum(out.values())
    return {k: round(out[k] / s, 4) for k in BUCKETS}


def _apply_floor_cap(
    w: dict[str, float], *, max_single: float, min_each: float
) -> dict[str, float]:
    """单风格上限 + 每类保底，再归一化。"""
    capped = {k: min(max(w[k], min_each), max_single) for k in BUCKETS}
    s = sum(capped.values())
    if s <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(capped[k] / s, 4) for k in BUCKETS}


def update_from_recent_returns(
    trade_days: list[str],
    anchor_date: str,
    iso_year: int,
    iso_week: int,
    *,
    smoothing: float = 0.3,
    max_single: float = 0.55,
    min_each: float = 0.08,
) -> dict[str, Any]:
    """
    用「当前 ISO 周」内龙头池样本的区间收益，生成建议权重并平滑写入。
    在周报邮件脚本末尾调用。
    """
    recs = records_for_iso_week(load_all_records(), iso_year, iso_week)
    rows = compute_returns_for_records(recs, trade_days, anchor_date)
    suggested = _suggested_weights_from_rows(rows)
    with _lock:
        cur = load_strategy_preference()
        old = dict(cur.get("strategy_weights") or DEFAULT_WEIGHTS)
        merged = _smooth(old, suggested, smoothing)
        merged = _apply_floor_cap(merged, max_single=max_single, min_each=min_each)
        out = {
            **cur,
            "strategy_weights": merged,
            "effective_date": anchor_date,
            "notes": f"周{iso_year}-W{iso_week:02d} 归因更新；样本可结算 {sum(1 for r in rows if r.ret_pct is not None and r.note == 'ok')} 条",
            "last_suggested": suggested,
        }
        _save_pref(out)
        _append_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "anchor": anchor_date,
                "iso_week": f"{iso_year}-W{iso_week:02d}",
                "old": old,
                "suggested": suggested,
                "merged": merged,
            }
        )
    return out


def build_prompt_addon() -> str:
    """拼入每日复盘 prompt 的「动态侧重」段。"""
    p = load_strategy_preference()
    if not p.get("active", True):
        return ""
    sw = p.get("strategy_weights") or {}
    ranked = sorted(sw.items(), key=lambda x: -x[1])
    top = ranked[:3]
    lines = [
        "\n---\n",
        "## 【策略偏好·动态侧重】（由历史龙头池收益反馈自动更新，仅供参考）\n",
        f"- 生效参考日：**{p.get('effective_date', '—')}**；{p.get('notes', '')}\n",
    ]
    parts = "、".join(f"**{k}** {float(v):.0%}" for k, v in top)
    lines.append(f"- 当前权重排序：{parts}\n")
    lines.append(
        "- 写作要求：在「主线与程序选股」「次日竞价预案」中体现侧重——\n"
        "  - **龙头/打板**权重大时：更强调涨停时间、封单与板块联动、次日溢价环境；\n"
        "  - **趋势**权重大时：更强调均线与量能、趋势延续与回踩；\n"
        "  - **低吸**权重大时：更强调分歧转一致、承接与止损位；\n"
        "  - 权重较低的风格**仍须覆盖**程序给出的龙头池，不得整段忽略。\n"
    )
    return "".join(lines)
