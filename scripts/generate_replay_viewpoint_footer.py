# -*- coding: utf-8 -*-
"""
生成复盘文末「小明」心智框架图的高分辨率 PNG（供邮件 CID 内嵌）。

用法（项目根目录）:
  python scripts/generate_replay_viewpoint_footer.py

依赖 matplotlib（已在 requirements.txt）。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OUT_PNG = os.path.join(_ROOT, "assets", "replay_viewpoint_footer.png")

# 高 DPI + 足够大的画布 → 邮件里缩放仍锐利
FIG_W_INCH = 11.0
FIG_H_INCH = 26.0
DPI = 280


def _configure_chinese_font():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for name in ("Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC"):
        plt.rcParams["font.sans-serif"] = [name]
        break
    plt.rcParams["axes.unicode_minus"] = False


def _rounded_box(ax, xy, w, h, text, *, fs=7.2, fc="#ede7f6", ec="#5e35b1", lw=1.1):
    from matplotlib import patches

    x, y = xy
    r = patches.FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.018,rounding_size=0.35",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        clip_on=False,
    )
    ax.add_patch(r)
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color="#1a1a1a",
        linespacing=1.15,
    )


def _diamond_text(ax, xy, w, h, text, *, fs=8.0):
    from matplotlib import patches

    x, y = xy
    r = patches.FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.5",
        linewidth=1.25,
        edgecolor="#4527a0",
        facecolor="#d1c4e9",
        clip_on=False,
    )
    ax.add_patch(r)
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color="#311b92",
        weight="bold",
    )


def _arrow(ax, x1, y1, x2, y2):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color="#333333",
            lw=1.0,
            shrinkA=0,
            shrinkB=4,
        ),
        clip_on=False,
    )


def main() -> None:
    _configure_chinese_font()
    import matplotlib.pyplot as plt
    from matplotlib import patches  # noqa: F401  # patches used in helpers

    fig, ax = plt.subplots(figsize=(FIG_W_INCH, FIG_H_INCH), dpi=DPI)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor("#faf8fc")
    ax.set_facecolor("#faf8fc")

    cx = 50.0
    xs = (22.0, 50.0, 78.0)

    y = 97.5
    _rounded_box(
        ax,
        (cx, y),
        88,
        4.2,
        "贴子核心：认清并战胜内心的「小明」",
        fs=11.5,
        fc="#e1bee7",
        ec="#6a1b9a",
    )
    _arrow(ax, cx, 95.2, cx, 93.0)

    y = 90.5
    _diamond_text(ax, (cx, y), 52, 5.5, "「小明」的六大人性弱点", fs=9.5)
    _arrow(ax, cx, 87.5, cx, 85.0)

    weaknesses = [
        ("傲慢", "收盘后就发呆混时间"),
        ("急躁", "踏空了，感觉很着急"),
        ("恐惧", "割完涨了怎么办"),
        ("贪婪", "赚了点就开始焦虑\n钱太多花不完怎么办"),
        ("偏执", "妄想掌控所有机会"),
        ("盲从", "别人赚钱了\n我也得买一个"),
    ]
    row1_y = 81.0
    row2_y = 74.5
    for i, (lab, sub) in enumerate(weaknesses[:3]):
        _rounded_box(ax, (xs[i], row1_y), 25.5, 7.5, f"{lab}\n{sub}", fs=7.0)
    for i, (lab, sub) in enumerate(weaknesses[3:]):
        _rounded_box(ax, (xs[i], row2_y), 25.5, 7.5, f"{lab}\n{sub}", fs=7.0)

    for x in xs:
        _arrow(ax, x, 87.5, x, row1_y + 4.2)
        _arrow(ax, x, row1_y - 4.2, x, row2_y + 4.2)
    _arrow(ax, cx, row2_y - 4.5, cx, 68.0)

    y = 65.0
    _rounded_box(
        ax,
        (cx, y),
        40,
        4.0,
        "造成的行为后果",
        fs=9.5,
        fc="#d7ccc8",
        ec="#5d4037",
    )
    _arrow(ax, cx, 62.8, cx, 60.5)

    behaviors = [
        "缺乏计划\n每日虚度",
        "冲动交易\n随意追涨杀跌",
        "不止损\n结果越套越深",
        "幻想暴利\n随意加码",
        "模式漂移\n什么钱都想赚",
        "踏空焦虑\n盲目跟风",
    ]
    b1_y = 56.5
    b2_y = 50.0
    for i, t in enumerate(behaviors[:3]):
        _rounded_box(
            ax, (xs[i], b1_y), 25.5, 6.8, t, fs=7.2, fc="#efebe9", ec="#4e342e"
        )
    for i, t in enumerate(behaviors[3:]):
        _rounded_box(
            ax, (xs[i], b2_y), 25.5, 6.8, t, fs=7.2, fc="#efebe9", ec="#4e342e"
        )

    for x in xs:
        _arrow(ax, x, 63.0, x, b1_y + 3.6)
        _arrow(ax, x, b1_y - 3.6, x, b2_y + 3.6)
    _arrow(ax, cx, b2_y - 4.0, cx, 42.5)

    y = 39.0
    _rounded_box(
        ax,
        (cx, y),
        86,
        5.5,
        "交易恶果\n持续亏损，无法稳定盈利",
        fs=9.0,
        fc="#ffcdd2",
        ec="#c62828",
    )
    _arrow(ax, cx, 36.0, cx, 33.5)

    dia_y = 30.5
    _diamond_text(ax, (cx, dia_y), 48, 5.2, "退神的解决之道", fs=9.5)

    solutions = [
        ("深度自省", "我一直在努力把小明提取出来"),
        ("认知觉醒", "我最大的问题是我自己"),
        ("坚守原则", "没有自己的标的就不买"),
        ("修炼心性", "理解勇气与自制力的真谛"),
    ]
    sx = (32.0, 68.0)
    sy_top, sy_bot = 20.5, 14.0
    placements = [
        (sx[0], sy_top),
        (sx[1], sy_top),
        (sx[0], sy_bot),
        (sx[1], sy_bot),
    ]
    for (px, py), (title, body) in zip(placements, solutions):
        _rounded_box(
            ax,
            (px, py),
            28.0,
            7.8,
            f"{title}\n{body}",
            fs=7.3,
            fc="#c8e6c9",
            ec="#2e7d32",
        )
        _arrow(ax, cx, dia_y - 2.8, px, py + 4.0)

    y_final = 7.5
    _rounded_box(
        ax,
        (cx, y_final),
        88,
        5.0,
        "交易正果\n克服人性，走向稳定盈利",
        fs=10.5,
        fc="#a5d6a7",
        ec="#1b5e20",
    )
    for px, py in placements:
        _arrow(ax, px, py - 4.2, cx, y_final + 2.8)

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(
        OUT_PNG,
        dpi=DPI,
        bbox_inches="tight",
        pad_inches=0.35,
        facecolor=fig.patch.get_facecolor(),
    )
    plt.close(fig)

    wpx = int(FIG_W_INCH * DPI)
    hpx = int(FIG_H_INCH * DPI)
    size_mb = os.path.getsize(OUT_PNG) / (1024 * 1024)
    print(f"已写入: {OUT_PNG}")
    print(f"约 {wpx}×{hpx} 像素（画布）, 文件 {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
