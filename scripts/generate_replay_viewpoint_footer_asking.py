# -*- coding: utf-8 -*-
"""
生成复盘文末第二张图：人气股/龙头 + 五大认知误区 + Asking 之道（高分辨率 PNG）。

用法（项目根目录）:
  python scripts/generate_replay_viewpoint_footer_asking.py

依赖 matplotlib（已在 requirements.txt）。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OUT_PNG = os.path.join(_ROOT, "assets", "replay_viewpoint_footer_asking.png")

FIG_W_INCH = 11.0
FIG_H_INCH = 25.0
DPI = 280

XS3 = (22.0, 50.0, 78.0)
XS2 = (36.0, 64.0)


def _configure_chinese_font():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for name in ("Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC"):
        plt.rcParams["font.sans-serif"] = [name]
        break
    plt.rcParams["axes.unicode_minus"] = False


def _rounded_box(ax, xy, w, h, text, *, fs=7.2, fc="#e3f2fd", ec="#1565c0", lw=1.1):
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
        linespacing=1.12,
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
        edgecolor="#0277bd",
        facecolor="#b3e5fc",
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
        color="#01579b",
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

    fig, ax = plt.subplots(figsize=(FIG_W_INCH, FIG_H_INCH), dpi=DPI)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor("#f5fbff")
    ax.set_facecolor("#f5fbff")

    cx = 50.0

    y = 98.0
    _rounded_box(
        ax,
        (cx, y),
        90,
        4.0,
        "帖子核心：做人气股、领涨股，资金最安全，效率最高",
        fs=10.8,
        fc="#fff3e0",
        ec="#e65100",
    )
    _arrow(ax, cx, 95.8, cx, 93.5)

    y = 91.0
    _diamond_text(ax, (cx, y), 54, 5.2, "「人性的五大认知误区」", fs=9.2)

    misconceptions = [
        ("选股误区", "「认为基本面比题材更重要」"),
        ("追涨恐惧", "「害怕追高，总想买在最低点」"),
        ("时间误区", "「不参与任何级别调整就等于短线」"),
        ("心态失衡", "「十分里心态占7分，技术只占3分」"),
        ("预测执念", "「总想预测市场，而不是跟随市场」"),
    ]
    r1, r2 = 83.0, 76.0
    bw, bh = 25.5, 8.2
    for i, (a, b) in enumerate(misconceptions[:3]):
        _rounded_box(ax, (XS3[i], r1), bw, bh, f"{a}\n{b}", fs=6.65)
    for i, (a, b) in enumerate(misconceptions[3:]):
        _rounded_box(ax, (XS2[i], r2), bw, bh, f"{a}\n{b}", fs=6.65)

    b_bottom = 91.0 - 5.2 / 2  # 菱形下沿
    for x in XS3:
        _arrow(ax, cx, b_bottom, x, r1 + bh / 2)
    for x in XS2:
        _arrow(ax, cx, b_bottom, x, r2 + bh / 2)

    d_top = 69.0 + 3.8 / 2
    for x in XS3:
        _arrow(ax, x, r1 - bh / 2, cx, d_top)
    for x in XS2:
        _arrow(ax, x, r2 - bh / 2, cx, d_top)

    y = 69.0
    _rounded_box(
        ax,
        (cx, y),
        42,
        3.8,
        "造成的行为后果",
        fs=9.2,
        fc="#eceff1",
        ec="#455a64",
    )
    d_bottom = 69.0 - 3.8 / 2
    _arrow(ax, cx, d_bottom, cx, 64.8)

    behaviors = [
        ("买跟风股", "错过真正的龙头"),
        ("犹豫不决", "龙头启动时不敢上车"),
        ("参与调整", "浪费时间成本"),
        ("情绪化交易", "追涨杀跌"),
        ("逆势操作", "与市场对抗"),
    ]
    e1, e2 = 62.0, 55.5
    for i, (a, b) in enumerate(behaviors[:3]):
        _rounded_box(ax, (XS3[i], e1), bw, 7.2, f"{a}\n{b}", fs=7.0)
    for i, (a, b) in enumerate(behaviors[3:]):
        _rounded_box(ax, (XS2[i], e2), bw, 7.2, f"{a}\n{b}", fs=7.0)

    eh1, eh2 = 7.2 / 2, 7.2 / 2
    for x in XS3:
        _arrow(ax, cx, d_bottom, x, e1 + eh1)
    for x in XS2:
        _arrow(ax, cx, d_bottom, x, e2 + eh2)
    f_top = 46.5 + 5.0 / 2
    for x in XS3:
        _arrow(ax, x, e1 - eh1, cx, f_top)
    for x in XS2:
        _arrow(ax, x, e2 - eh2, cx, f_top)

    y = 46.5
    _rounded_box(
        ax,
        (cx, y),
        88,
        5.0,
        "交易恶果\n抓不住龙头，效率低下",
        fs=8.8,
        fc="#ffccbc",
        ec="#bf360c",
    )
    _arrow(ax, cx, 43.8, cx, 41.2)

    dia_y = 37.5
    _diamond_text(ax, (cx, dia_y), 50, 5.0, "Asking的解决之道", fs=9.0)

    solutions = [
        ("只做龙头", "「炒股一定要炒龙头股，有板块效应的最好」"),
        ("跟随市场", "「我只跟市场走，不预测，不操纵」"),
        ("仓位管理", "「追涨时先进半仓，当天涨停次日再加仓」"),
        ("心态修炼", "「心态、控制力占7分，技术占3分」"),
    ]
    sx = (32.0, 68.0)
    sy_top, sy_bot = 28.5, 20.5
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
            28.5,
            8.2,
            f"{title}\n{body}",
            fs=6.85,
            fc="#c8e6c9",
            ec="#1b5e20",
        )
        _arrow(ax, cx, dia_y - 2.6, px, py + 4.3)

    y_final = 11.0
    _rounded_box(
        ax,
        (cx, y_final),
        90,
        5.0,
        "交易正果\n抓住龙头，稳定盈利",
        fs=10.2,
        fc="#a5d6a7",
        ec="#1b5e20",
    )
    for px, py in placements:
        _arrow(ax, px, py - 4.3, cx, y_final + 2.6)

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(
        OUT_PNG,
        dpi=DPI,
        bbox_inches="tight",
        pad_inches=0.35,
        facecolor=fig.patch.get_facecolor(),
    )
    plt.close(fig)

    print(f"已写入: {OUT_PNG} ({os.path.getsize(OUT_PNG) / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
