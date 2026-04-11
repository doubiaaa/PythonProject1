"""纯文本图表：连板分档条形图等。"""

from __future__ import annotations


def draw_text_bar(
    label: str,
    count: int,
    total_for_pct: int,
    *,
    max_len: int = 30,
) -> str:
    """
    文本条形图，例如 ``2连板: 9 ████████░░░░░░░░░░░░░░░░░░░░ (15.3%)``。
    ``total_for_pct`` 为计算占比的分母（通常为当日涨停家数）。
    """
    label = str(label).strip()
    n = max(0, int(count))
    tot = max(0, int(total_for_pct))
    ml = max(8, int(max_len))
    if tot <= 0:
        pct = 0.0
        filled = 0
    else:
        pct = 100.0 * n / tot
        filled = int(round(n / tot * ml))
    filled = max(0, min(ml, filled))
    bar = "█" * filled + "░" * (ml - filled)
    return f"{label}: {n} {bar} ({pct:.1f}%)"
