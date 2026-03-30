# -*- coding: utf-8 -*-
"""
策略偏好闭环：根据龙头池历史区间收益，更新「风格权重」，供每日复盘 prompt 动态侧重。
风格桶：打板 / 低吸 / 趋势 / 龙头 / 其他（与程序标签映射）。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from app.services.weekly_market_snapshot import trade_days_in_iso_week
from app.services.weekly_performance import (
    SignalReturnRow,
    compute_returns_for_records,
    records_for_iso_week,
)
from app.services.watchlist_store import load_all_records
from config.strategy_preference_config import (
    MAX_WEIGHT_DELTA_PER_UPDATE,
    WEIGHT_CLIP_HIGH,
    WEIGHT_CLIP_LOW,
    WEIGHT_HISTORY_MAX,
)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
PREF_FILE = os.path.join(DATA_DIR, "strategy_preference.json")
LOG_FILE = os.path.join(DATA_DIR, "strategy_evolution_log.jsonl")

_lock = threading.Lock()

BUCKETS = ("打板", "低吸", "趋势", "龙头", "其他")

DEFAULT_WEIGHTS = {k: 0.2 for k in BUCKETS}

ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-flash"


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


def _bucket_trade_counts(rows: list[SignalReturnRow]) -> dict[str, int]:
    c = {k: 0 for k in BUCKETS}
    for r in rows:
        if r.ret_pct is None or r.note != "ok":
            continue
        c[tag_to_bucket(r.tag)] += 1
    return c


def _suggested_weights_from_rows(
    rows: list[SignalReturnRow],
    old: dict[str, float],
    *,
    min_trades_per_style: int,
) -> tuple[dict[str, float], dict[str, int]]:
    """
    可结算样本按风格桶聚合；某桶交易次数 < min 则该桶建议值沿用 old（防小样本过拟合）。
    """
    by: dict[str, list[float]] = {k: [] for k in BUCKETS}
    for r in rows:
        if r.ret_pct is None or r.note != "ok":
            continue
        b = tag_to_bucket(r.tag)
        by[b].append(float(r.ret_pct))
    counts = {k: len(by[k]) for k in BUCKETS}
    scores: dict[str, float] = {}
    for k in BUCKETS:
        if counts[k] < min_trades_per_style:
            scores[k] = old.get(k, 0.2)
            continue
        vals = by[k]
        avg = sum(vals) / len(vals)
        scores[k] = max(avg + 5.0, 0.1)
    tot = sum(scores.values())
    if tot <= 0:
        return dict(DEFAULT_WEIGHTS), counts
    return {k: round(scores[k] / tot, 4) for k in BUCKETS}, counts


def _iter_iso_weeks_back(iso_year: int, iso_week: int, n: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, w = iso_year, iso_week
    for _ in range(n):
        out.append((y, w))
        d = datetime.fromisocalendar(y, w, 1) - timedelta(days=7)
        y, w, _ = d.isocalendar()
    return list(reversed(out))


def _anchor_for_iso_week(trade_days: list[str], y: int, w: int) -> Optional[str]:
    days = trade_days_in_iso_week(trade_days, y, w)
    return days[-1] if days else None


def _multi_week_suggested(
    trade_days: list[str],
    iso_year: int,
    iso_week: int,
    old: dict[str, float],
    *,
    weeks: int,
    decay: float,
    min_total_trades_per_bucket: int,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    最近 weeks 个自然周：每周按锚点结算收益，对每桶做时间衰减加权平均，再转成权重。
    min_total_trades_per_bucket：跨周合计仍不足则该桶沿用 old。
    """
    week_specs = _iter_iso_weeks_back(iso_year, iso_week, weeks)
    rows_by_week: list[list[SignalReturnRow]] = []
    meta: list[dict[str, Any]] = []
    for y, w in week_specs:
        anch = _anchor_for_iso_week(trade_days, y, w)
        if not anch:
            continue
        recs = records_for_iso_week(load_all_records(), y, w)
        rw = compute_returns_for_records(recs, trade_days, anch)
        rows_by_week.append(rw)
        meta.append({"iso": f"{y}-W{w:02d}", "anchor": anch, "n_ok": sum(1 for x in rw if x.note == "ok" and x.ret_pct is not None)})

    if not rows_by_week:
        return dict(old), meta

    nweeks = len(rows_by_week)
    combined: dict[str, tuple[float, float]] = {k: (0.0, 0.0) for k in BUCKETS}
    total_counts = {k: 0 for k in BUCKETS}
    for wi, rows in enumerate(rows_by_week):
        wdec = decay ** (nweeks - 1 - wi)
        for k in BUCKETS:
            vals = [
                float(r.ret_pct)
                for r in rows
                if r.note == "ok"
                and r.ret_pct is not None
                and tag_to_bucket(r.tag) == k
            ]
            total_counts[k] += len(vals)
            if vals:
                avg = sum(vals) / len(vals)
                num, den = combined[k]
                combined[k] = (num + wdec * avg, den + wdec)

    scores: dict[str, float] = {}
    for k in BUCKETS:
        if total_counts[k] < min_total_trades_per_bucket:
            scores[k] = old.get(k, 0.2)
            continue
        num, den = combined[k]
        if den <= 0:
            scores[k] = old.get(k, 0.2)
        else:
            scores[k] = max(num / den + 5.0, 0.1)
    tot = sum(scores.values())
    suggested = {k: round(scores[k] / tot, 4) for k in BUCKETS}
    return suggested, meta


def _smooth(old: dict[str, float], new: dict[str, float], alpha: float) -> dict[str, float]:
    out = {}
    for k in BUCKETS:
        out[k] = (1.0 - alpha) * old[k] + alpha * new[k]
    s = sum(out.values())
    return {k: round(out[k] / s, 4) for k in BUCKETS}


def _apply_floor_cap(
    w: dict[str, float], *, max_single: float, min_each: float
) -> dict[str, float]:
    capped = {k: min(max(w[k], min_each), max_single) for k in BUCKETS}
    s = sum(capped.values())
    if s <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(capped[k] / s, 4) for k in BUCKETS}


def _clip_bucket_normalize(
    w: dict[str, float], low: float, high: float
) -> dict[str, float]:
    """每桶 clip 到 [low, high] 后再归一化到和为 1。"""
    clipped = {k: min(max(float(w.get(k, 0)), low), high) for k in BUCKETS}
    s = sum(clipped.values())
    if s <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(clipped[k] / s, 4) for k in BUCKETS}


def _limit_weight_delta_vs_old(
    new_w: dict[str, float],
    old_w: dict[str, float],
    *,
    max_delta: float,
) -> dict[str, float]:
    """限制每桶相对上一版合并权重的绝对变化，再归一化。"""
    out: dict[str, float] = {}
    for k in BUCKETS:
        target = float(new_w.get(k, 0))
        prev = float(old_w.get(k, 0.2))
        d = target - prev
        if abs(d) > max_delta:
            out[k] = prev + (max_delta if d > 0 else -max_delta)
        else:
            out[k] = target
    s = sum(out.values())
    if s <= 0:
        return dict(old_w)
    return {k: round(out[k] / s, 4) for k in BUCKETS}


def _penalize_large_shift(
    new_w: dict[str, float],
    old_w: dict[str, float],
    *,
    max_change: float,
    pullback: float,
) -> dict[str, float]:
    """单桶周变化超过 max_change 时向旧权重回拉。"""
    out = {}
    for k in BUCKETS:
        delta = new_w[k] - old_w.get(k, 0.2)
        if abs(delta) > max_change:
            out[k] = old_w.get(k, 0.2) + delta * (1.0 - pullback)
        else:
            out[k] = new_w[k]
    s = sum(out.values())
    if s <= 0:
        return dict(old_w)
    return {k: round(out[k] / s, 4) for k in BUCKETS}


def probe_style_stability(api_key: str, market_data_excerpt: str, timeout: float = 45.0) -> str:
    """轻量探测：返回 稳定 / 可能切换 / 混乱。"""
    prompt = (
        "你是市场风格观察员。根据下列复盘用市场数据摘录，只输出下面三个词之一，不要标点与解释：\n"
        "稳定\n可能切换\n混乱\n\n"
        "判断：涨停/跌停/炸板/溢价/板块是否指向同一主导风格；分歧大则「混乱」，拐点则「可能切换」。\n\n"
        "【数据摘录】\n"
        + (market_data_excerpt or "")[:9000]
    )
    try:
        r = requests.post(
            ZHIPU_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 32,
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return "稳定"
        text = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        text = text.strip()
        if "混乱" in text:
            return "混乱"
        if "可能切换" in text or "切换" in text:
            return "可能切换"
        return "稳定"
    except Exception:
        return "稳定"


def effective_weights_from_stability(
    stability: str, base: dict[str, float]
) -> dict[str, float]:
    u = {k: 0.2 for k in BUCKETS}
    st = (stability or "").strip()
    if "混乱" in st:
        return dict(u)
    if "可能切换" in st or "切换" in st:
        blended = {k: 0.5 * base.get(k, 0.2) + 0.5 * u[k] for k in BUCKETS}
        s = sum(blended.values())
        return {k: round(blended[k] / s, 4) for k in BUCKETS}
    return dict(base)


def update_from_recent_returns(
    trade_days: list[str],
    anchor_date: str,
    iso_year: int,
    iso_week: int,
    *,
    smoothing: float = 0.3,
    max_single: float = 0.55,
    min_each: float = 0.08,
    min_trades_per_style: int = 3,
    use_multi_week_decay: bool = True,
    multi_week_lookback: int = 4,
    week_decay_factor: float = 0.75,
    min_total_trades_per_bucket: int = 3,
    max_change_per_week: float = 0.25,
    shift_pullback: float = 0.5,
    max_weight_delta_per_update: Optional[float] = None,
) -> dict[str, Any]:
    """
    更新策略偏好。multi_week：用最近 multi_week_lookback 周衰减合成 suggested，再平滑。
    """
    from app.utils.config import ConfigManager

    _cm = ConfigManager()
    if max_weight_delta_per_update is None:
        max_weight_delta_per_update = float(
            _cm.get(
                "strategy_max_weight_delta_per_update",
                MAX_WEIGHT_DELTA_PER_UPDATE,
            )
        )

    with _lock:
        cur = load_strategy_preference()
        old = dict(cur.get("strategy_weights") or DEFAULT_WEIGHTS)

    if use_multi_week_decay:
        suggested, wmeta = _multi_week_suggested(
            trade_days,
            iso_year,
            iso_week,
            old,
            weeks=multi_week_lookback,
            decay=week_decay_factor,
            min_total_trades_per_bucket=min_total_trades_per_bucket,
        )
        recs = records_for_iso_week(load_all_records(), iso_year, iso_week)
        rows_single = compute_returns_for_records(recs, trade_days, anchor_date)
        counts = _bucket_trade_counts(rows_single)
    else:
        recs = records_for_iso_week(load_all_records(), iso_year, iso_week)
        rows_single = compute_returns_for_records(recs, trade_days, anchor_date)
        suggested, counts = _suggested_weights_from_rows(
            rows_single,
            old,
            min_trades_per_style=min_trades_per_style,
        )
        wmeta = [{"mode": "single_week"}]

    merged = _smooth(old, suggested, smoothing)
    merged = _penalize_large_shift(
        merged, old, max_change=max_change_per_week, pullback=shift_pullback
    )
    merged = _apply_floor_cap(merged, max_single=max_single, min_each=min_each)
    merged = _clip_bucket_normalize(merged, WEIGHT_CLIP_LOW, WEIGHT_CLIP_HIGH)
    merged = _limit_weight_delta_vs_old(
        merged, old, max_delta=max_weight_delta_per_update
    )

    notes = (
        f"周{iso_year}-W{iso_week:02d}；"
        f"可结算 {sum(1 for r in rows_single if r.ret_pct is not None and r.note == 'ok')} 条；"
        f"多周衰减={use_multi_week_decay}"
    )
    alerts = detect_weight_anomalies(old, merged, counts)
    hist = list(cur.get("weight_history") or [])
    hist.append({"anchor": anchor_date, "weights": dict(merged)})
    hist = hist[-WEIGHT_HISTORY_MAX:]

    out = {
        **cur,
        "strategy_weights": merged,
        "effective_date": anchor_date,
        "notes": notes,
        "last_suggested": suggested,
        "last_bucket_counts": counts,
        "last_week_meta": wmeta,
        "weight_alerts": alerts,
        "weight_history": hist,
    }
    with _lock:
        _save_pref({k: v for k, v in out.items() if k != "weight_alerts"})
        _append_log(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "anchor": anchor_date,
                "iso_week": f"{iso_year}-W{iso_week:02d}",
                "old": old,
                "suggested": suggested,
                "merged": merged,
                "counts": counts,
            }
        )
    return out


def build_prompt_addon(
    effective_weights: Optional[dict[str, float]] = None,
    stability_hint: str = "",
) -> str:
    """拼入每日复盘 prompt。effective_weights 为探测后的有效权重（可不同于文件）。"""
    p = load_strategy_preference()
    if not p.get("active", True):
        return ""
    sw = effective_weights if effective_weights is not None else (p.get("strategy_weights") or {})
    ranked = sorted(sw.items(), key=lambda x: -x[1])
    top = ranked[:3]
    lines = [
        "\n---\n",
        "## 【策略偏好·动态侧重】（由历史龙头池收益反馈自动更新，仅供参考）\n",
        f"- 生效参考日：**{p.get('effective_date', '—')}**；{p.get('notes', '')}\n",
    ]
    if stability_hint:
        lines.append(f"- **风格稳定性探测**：{stability_hint}（混乱时程序已折中/均匀化有效权重）\n")
    parts = "、".join(f"**{k}** {float(v):.0%}" for k, v in top)
    lines.append(f"- 当前有效权重排序：{parts}\n")
    lines.append(
        "- 写作要求：在「主线与程序选股」「次日竞价预案」中体现侧重——\n"
        "  - **龙头/打板**权重大时：更强调涨停时间、封单与板块联动、次日溢价环境；\n"
        "  - **趋势**权重大时：更强调均线与量能、趋势延续与回踩；\n"
        "  - **低吸**权重大时：更强调分歧转一致、承接与止损位；\n"
        "  - 权重较低的风格**仍须覆盖**程序给出的龙头池，不得整段忽略。\n"
    )
    return "".join(lines)


def plot_evolution_log(output_path: str) -> bool:
    """从 evolution_log 绘制权重曲线。需 matplotlib。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    if not os.path.isfile(LOG_FILE):
        return False
    rows: list[dict[str, Any]] = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return False
    dates = [r.get("anchor") or r.get("time", "")[:10] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 5))
    for b in BUCKETS:
        ys = []
        for r in rows:
            m = r.get("merged") or r.get("suggested") or {}
            ys.append(float(m.get(b, 0)))
        ax.plot(range(len(ys)), ys, label=b, marker=".", markersize=4)
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("weight")
    ax.set_title("Strategy weights evolution (merged)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()
    return True


def detect_weight_anomalies(
    old: dict[str, float],
    merged: dict[str, float],
    counts: dict[str, int],
) -> list[str]:
    """返回人类可读异常说明列表。"""
    alerts: list[str] = []
    if sum(counts.values()) == 0:
        alerts.append("本周各风格可结算交易次数均为 0，权重未反映实盘样本。")
    for k in BUCKETS:
        if counts.get(k, 0) == 0 and sum(counts.values()) > 0:
            alerts.append(f"风格「{k}」本周有效交易次数为 0。")
    for k in BUCKETS:
        d = abs(float(merged.get(k, 0)) - float(old.get(k, 0)))
        if d > 0.4:
            alerts.append(f"风格「{k}」权重变动 {d:.2f}（超过 0.4 阈值）。")
    return alerts
