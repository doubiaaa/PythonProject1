"""
财经要闻：相关性打分与过滤（弱化 OCR 噪声、弱关联快讯）。
"""

from __future__ import annotations

import re
from typing import Any

# 与 A 股/政策/市场直接相关的词根（命中越多分越高，上限 1.0）
_MARKET_KEYWORDS: tuple[tuple[str, float], ...] = (
    ("A股", 0.18),
    ("沪深", 0.12),
    ("股市", 0.14),
    ("证券", 0.12),
    ("证监会", 0.16),
    ("监管", 0.1),
    ("央行", 0.1),
    ("降准", 0.12),
    ("降息", 0.12),
    ("板块", 0.12),
    ("涨停", 0.14),
    ("跌停", 0.12),
    ("北向", 0.1),
    ("融资融券", 0.1),
    ("ETF", 0.08),
    ("指数", 0.1),
    ("沪指", 0.1),
    ("深成指", 0.1),
    ("创业板", 0.1),
    ("科创板", 0.1),
    ("港股", 0.08),
    ("人民币", 0.08),
    ("汇率", 0.08),
    ("地产", 0.06),
    ("新能源", 0.06),
    ("半导体", 0.06),
    ("人工智能", 0.06),
    ("业绩", 0.05),
    ("回购", 0.06),
    ("增持", 0.06),
    ("减持", 0.06),
    ("停牌", 0.06),
    ("复牌", 0.06),
)

# 明显非二级市场或易为噪声的来源式词（压低分）
_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"德黑兰|华融领|净空控段", re.I),
    re.compile(r"^[A-Za-z\s]{12,}$"),  # 纯外文长串
)


def relevance_scoring(text: str) -> float:
    """
    返回 0～1：与 A 股/宏观政策/板块情绪的相关性。
    用于过滤「宏观与市场要闻」中的弱关联或疑似 OCR 异常摘要。
    """
    s = (text or "").strip()
    if len(s) < 8:
        return 0.0
    score = 0.0
    for kw, w in _MARKET_KEYWORDS:
        if kw in s:
            score += w
    # 过长且无市场词：多为转载或乱码
    if len(s) > 120 and score < 0.12:
        score *= 0.35
    for pat in _NOISE_PATTERNS:
        if pat.search(s):
            score *= 0.2
            break
    return float(min(1.0, round(score, 4)))


def filter_news(
    items: list[dict[str, Any]],
    *,
    min_score: float = 0.6,
    max_items: int = 3,
    related_boost: bool = False,
) -> list[dict[str, Any]]:
    """
    对 ``{"tag","summary","hint?"}`` 列表按相关性过滤，仅保留 score > min_score，
    取分最高的前 max_items 条。related_boost=True 时（龙头池已命中）给予下限分，避免误杀纯个股公告。
    """
    if not items:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for it in items:
        raw = str(it.get("summary") or "")
        sc = relevance_scoring(raw)
        if related_boost:
            sc = max(sc, 0.62)
        if sc > min_score:
            scored.append((sc, dict(it)))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored[:max_items]]
