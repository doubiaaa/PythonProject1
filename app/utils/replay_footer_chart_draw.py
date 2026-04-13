# -*- coding: utf-8 -*-
"""复盘文末心智流程图：通用 Matplotlib 绘制（高分辨率 PNG）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
import matplotlib

matplotlib.use("Agg")


def _configure_font() -> None:
    import matplotlib.pyplot as plt

    for name in ("Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC"):
        plt.rcParams["font.sans-serif"] = [name]
        break
    plt.rcParams["axes.unicode_minus"] = False


def _rounded_box(ax, xy, w, h, text, *, fs=7.2, fc="#ede7f6", ec="#5e35b1", lw=1.1) -> None:
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


def _diamond_text(
    ax, xy, w, h, text, *, fs=8.0, ec="#4527a0", fc="#d1c4e9", tcolor="#311b92"
) -> None:
    from matplotlib import patches

    x, y = xy
    r = patches.FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.5",
        linewidth=1.25,
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
        color=tcolor,
        weight="bold",
    )


def _arrow(ax, x1, y1, x2, y2) -> None:
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


def _dashed_arrow(
    ax, x1, y1, x2, y2, *, color: str = "#616161", lw: float = 1.05
) -> None:
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=lw,
            linestyle=(0, (4, 3)),
            shrinkA=0,
            shrinkB=4,
        ),
        clip_on=False,
    )


def _dashed_line_segments(
    ax,
    points: list[tuple[float, float]],
    *,
    color: str = "#616161",
    lw: float = 1.05,
) -> None:
    """虚折线（无箭头），用于绕行避免压住节点。"""
    if len(points) < 2:
        return
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(
        xs,
        ys,
        linestyle=(0, (4, 3)),
        color=color,
        lw=lw,
        solid_capstyle="round",
        clip_on=False,
        zorder=1,
    )


def _elbow_chain_arrow(
    ax,
    pts: list[tuple[float, float]],
    *,
    color: str = "#37474f",
    lw: float = 1.05,
    z: int = 2,
) -> None:
    """折线箭头：最后一段带箭头，前面为直线段（正交管线路由）。"""
    if len(pts) < 2:
        return
    if len(pts) == 2:
        ax.annotate(
            "",
            xy=pts[1],
            xytext=pts[0],
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=lw,
                shrinkA=0,
                shrinkB=5,
            ),
            clip_on=False,
            zorder=z,
        )
        return
    for i in range(len(pts) - 2):
        ax.plot(
            [pts[i][0], pts[i + 1][0]],
            [pts[i][1], pts[i + 1][1]],
            color=color,
            lw=lw,
            solid_capstyle="round",
            zorder=z,
        )
    ax.annotate(
        "",
        xy=pts[-1],
        xytext=pts[-2],
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=lw,
            shrinkA=0,
            shrinkB=5,
        ),
        clip_on=False,
        zorder=z,
    )


def _hub_fan_down(
    ax,
    cx: float,
    y_from: float,
    dests: list[tuple[float, float]],
    *,
    color: str = "#37474f",
    lw: float = 1.05,
    bus_frac: float = 0.42,
) -> None:
    """自 (cx,y_from) 经水平汇流层直角扇出到各箱顶 (bx, y_to)；减少斜线交叉。"""
    if not dests:
        return
    y_hi = max(y for _, y in dests)
    y_bus = y_from - (y_from - y_hi) * bus_frac
    ax.plot(
        [cx, cx],
        [y_from, y_bus],
        color=color,
        lw=lw,
        solid_capstyle="round",
        zorder=2,
    )
    for bx, y_to in dests:
        _elbow_chain_arrow(
            ax, [(cx, y_bus), (bx, y_bus), (bx, y_to)], color=color, lw=lw
        )


def _fan_merge_up(
    ax,
    cx: float,
    y_to: float,
    sources: list[tuple[float, float]],
    *,
    color: str = "#37474f",
    lw: float = 1.05,
    bus_frac: float = 0.48,
) -> None:
    """多路箱底 (bx,y_from) 汇至中心顶 (cx,y_to)。"""
    if not sources:
        return
    y_lo = min(y for _, y in sources)
    y_bus = y_lo + (y_to - y_lo) * bus_frac
    for bx, y_from in sources:
        ax.plot(
            [bx, bx, cx],
            [y_from, y_bus, y_bus],
            color=color,
            lw=lw,
            solid_capstyle="round",
            zorder=2,
        )
    ax.annotate(
        "",
        xy=(cx, y_to),
        xytext=(cx, y_bus),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=lw,
            shrinkA=0,
            shrinkB=5,
        ),
        clip_on=False,
        zorder=2,
    )


def _edge_label(ax, x: float, y: float, text: str, *, fs: float = 6.2) -> None:
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color="#424242",
        style="italic",
    )


def _split_indices(n: int) -> list[list[int]]:
    if n <= 3:
        return [list(range(n))]
    if n == 4:
        return [[0, 1], [2, 3]]
    if n == 5:
        return [[0, 1, 2], [3, 4]]
    if n == 6:
        return [[0, 1, 2], [3, 4, 5]]
    raise ValueError(f"unsupported box count {n}")


def _xs_for_row(count: int) -> tuple[float, ...]:
    if count == 1:
        return (50.0,)
    if count == 2:
        return (36.0, 64.0)
    return (22.0, 50.0, 78.0)


def _split_h(n: int) -> list[list[int]]:
    """H 区：4→2×2；5→3+2；≤3→一行。"""
    if n <= 3:
        return [list(range(n))]
    if n == 4:
        return [[0, 1], [2, 3]]
    if n == 5:
        return [[0, 1, 2], [3, 4]]
    raise ValueError(f"unsupported H count {n}")


@dataclass
class FlowchartPalette:
    bg: str = "#faf8fc"
    title_fc: str = "#e1bee7"
    title_ec: str = "#6a1b9a"
    b_ec: str = "#4527a0"
    b_fc: str = "#d1c4e9"
    b_tc: str = "#311b92"
    c_fc: str = "#ede7f6"
    c_ec: str = "#5e35b1"
    d_fc: str = "#d7ccc8"
    d_ec: str = "#5d4037"
    e_fc: str = "#efebe9"
    e_ec: str = "#4e342e"
    f_fc: str = "#ffcdd2"
    f_ec: str = "#c62828"
    g_ec: str = "#4527a0"
    g_fc: str = "#d1c4e9"
    g_tc: str = "#311b92"
    h_fc: str = "#c8e6c9"
    h_ec: str = "#2e7d32"
    i_fc: str = "#a5d6a7"
    i_ec: str = "#1b5e20"


@dataclass
class FlowchartSpec:
    core_title: str
    b_diamond: str
    c_items: list[str]
    d_mid: str = "造成的行为后果"
    e_items: list[str] = field(default_factory=list)
    f_bad: tuple[str, str] = ("交易恶果", "")
    g_diamond: str = ""
    h_items: list[str] = field(default_factory=list)
    i_good: tuple[str, str] = ("交易正果", "")
    palette: FlowchartPalette = field(default_factory=FlowchartPalette)
    fig_w_inch: float = 13.2
    fig_h_inch: float = 22.0
    dpi: int = 280
    c_fs: float = 6.85
    e_fs: float = 7.0
    h_fs: float = 6.95


def save_flowchart_png(spec: FlowchartSpec, out_path: str) -> None:
    import matplotlib.pyplot as plt

    _configure_font()
    pal = spec.palette
    cx = 50.0
    GAP = 1.35

    fig, ax = plt.subplots(figsize=(spec.fig_w_inch, spec.fig_h_inch), dpi=spec.dpi)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor(pal.bg)
    ax.set_facecolor(pal.bg)

    # A
    y = 98.0
    h_a = 4.0
    _rounded_box(
        ax,
        (cx, y),
        90,
        h_a,
        spec.core_title,
        fs=10.4,
        fc=pal.title_fc,
        ec=pal.title_ec,
    )
    y_a_bot = y - h_a / 2
    _arrow(ax, cx, y_a_bot - 0.1, cx, y_a_bot - GAP - 0.5)

    # B
    y = y_a_bot - GAP - 0.5 - 2.75
    h_b = 5.2
    _diamond_text(
        ax,
        (cx, y),
        56,
        h_b,
        spec.b_diamond,
        fs=8.95,
        ec=pal.b_ec,
        fc=pal.b_fc,
        tcolor=pal.b_tc,
    )
    b_bot = y - h_b / 2

    nc = len(spec.c_items)
    groups_c = _split_indices(nc)
    bh_c = 8.2 if nc >= 5 else 7.6
    row_step = bh_c + 1.1
    y_row1 = b_bot - GAP - 1.2 - bh_c / 2
    row_c_y = [y_row1]
    if len(groups_c) == 2:
        row_c_y.append(y_row1 - row_step)

    c_centers: list[tuple[float, float, float]] = []
    for ri, idxs in enumerate(groups_c):
        cy = row_c_y[ri]
        xs = _xs_for_row(len(idxs))
        bw = 26.2 if nc >= 5 else 25.8
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw,
                bh_c,
                spec.c_items[ii],
                fs=spec.c_fs,
                fc=pal.c_fc,
                ec=pal.c_ec,
            )
            c_centers.append((xs[j], cy, bh_c / 2))

    _hub_fan_down(
        ax, cx, b_bot, [(bx, by + hh) for bx, by, hh in c_centers], color="#455a64"
    )

    c_bottom = min(by - hh for _, by, hh in c_centers)

    # D
    h_d = 3.85
    d_y = c_bottom - GAP - h_d / 2
    _rounded_box(
        ax,
        (cx, d_y),
        44,
        h_d,
        spec.d_mid,
        fs=9.0,
        fc=pal.d_fc,
        ec=pal.d_ec,
    )
    d_top = d_y + h_d / 2
    d_bot = d_y - h_d / 2
    _fan_merge_up(
        ax, cx, d_top, [(bx, by - hh) for bx, by, hh in c_centers], color="#455a64"
    )

    ne = len(spec.e_items)
    groups_e = _split_indices(ne)
    bh_e = 7.15 if ne >= 5 else 6.85
    row_step_e = bh_e + 1.05
    y_e1 = d_bot - GAP - 1.0 - bh_e / 2
    row_e_y = [y_e1]
    if len(groups_e) == 2:
        row_e_y.append(y_e1 - row_step_e)

    e_centers: list[tuple[float, float, float]] = []
    for ri, idxs in enumerate(groups_e):
        cy = row_e_y[ri]
        xs = _xs_for_row(len(idxs))
        bw = 26.0
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw,
                bh_e,
                spec.e_items[ii],
                fs=spec.e_fs,
                fc=pal.e_fc,
                ec=pal.e_ec,
            )
            e_centers.append((xs[j], cy, bh_e / 2))

    _hub_fan_down(
        ax, cx, d_bot, [(bx, by + hh) for bx, by, hh in e_centers], color="#455a64"
    )

    e_bottom = min(by - hh for _, by, hh in e_centers)

    # F
    f1, f2 = spec.f_bad
    f_txt = f"{f1}\n{f2}" if f2 else f1
    h_f = 5.0
    f_y = e_bottom - GAP - h_f / 2
    _rounded_box(
        ax,
        (cx, f_y),
        88,
        h_f,
        f_txt,
        fs=8.6,
        fc=pal.f_fc,
        ec=pal.f_ec,
    )
    f_top = f_y + h_f / 2
    _fan_merge_up(
        ax, cx, f_top, [(bx, by - hh) for bx, by, hh in e_centers], color="#455a64"
    )

    # G
    h_g = 5.0
    g_y = f_y - h_f / 2 - GAP - h_g / 2
    _diamond_text(
        ax,
        (cx, g_y),
        54,
        h_g,
        spec.g_diamond,
        fs=8.6,
        ec=pal.g_ec,
        fc=pal.g_fc,
        tcolor=pal.g_tc,
    )
    g_bot = g_y - h_g / 2

    nh = len(spec.h_items)
    groups_h = _split_h(nh)
    bh_h = 8.6 if nh >= 5 else 8.0
    row_step_h = bh_h + 1.0
    y_h1 = g_bot - GAP - 1.0 - bh_h / 2
    row_h_y = [y_h1]
    if len(groups_h) == 2:
        row_h_y.append(y_h1 - row_step_h)

    h_centers: list[tuple[float, float, float]] = []
    bw_h = 28.8 if nh >= 5 else 28.2
    for ri, idxs in enumerate(groups_h):
        cy = row_h_y[ri]
        xs = _xs_for_row(len(idxs))
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw_h,
                bh_h,
                spec.h_items[ii],
                fs=spec.h_fs,
                fc=pal.h_fc,
                ec=pal.h_ec,
            )
            h_centers.append((xs[j], cy, bh_h / 2))

    _hub_fan_down(
        ax, cx, g_bot, [(bx, by + hh) for bx, by, hh in h_centers], color="#455a64"
    )

    h_bottom = min(by - hh for _, by, hh in h_centers)

    # I
    g1, g2 = spec.i_good
    i_txt = f"{g1}\n{g2}" if g2 else g1
    h_i = 5.0
    i_y = h_bottom - GAP - h_i / 2 - 0.5
    if i_y < 6.0:
        i_y = 6.0
    _rounded_box(
        ax,
        (cx, i_y),
        90,
        h_i,
        i_txt,
        fs=9.8,
        fc=pal.i_fc,
        ec=pal.i_ec,
    )
    i_top = i_y + h_i / 2
    _fan_merge_up(
        ax, cx, i_top, [(bx, by - hh) for bx, by, hh in h_centers], color="#455a64"
    )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(
        out_path,
        dpi=spec.dpi,
        bbox_inches="tight",
        pad_inches=0.35,
        facecolor=fig.patch.get_facecolor(),
    )
    plt.close(fig)


def save_readme_business_overview_png(out_path: str, *, dpi: int = 240) -> None:
    """
    README「业务全景」Mermaid 的静态 PNG：日度主链 + 周度闭环 + 两条虚线关联。
    不含已移除的「DeepSeek 增强四段」与「程序智能校验与决策摘要」节点。

    布局：日度列靠左、周度列靠右，留出中间走廊；「五桶权重→prompt」用折线虚线，避免横穿节点。
    """
    import matplotlib.pyplot as plt
    from matplotlib import patches

    _configure_font()
    pal = FlowchartPalette(
        bg="#f5f7fb",
        title_fc="#e3f2fd",
        title_ec="#1565c0",
    )
    GAP = 1.02
    bh = 3.45
    bw = 26.0
    bw_w = 21.5
    # 横向略加宽、纵向压扁，整体更接近「展板」比例
    fig_w, fig_h = 14.0, 11.2
    y_max = 102.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, y_max)
    ax.axis("off")
    fig.patch.set_facecolor(pal.bg)
    ax.set_facecolor(pal.bg)

    cx = 50.0
    y_title = 98.0
    h_t = 3.35
    _rounded_box(
        ax,
        (cx, y_title),
        94,
        h_t,
        "业务全景 · 日度复盘 / 周度闭环（与 README Mermaid 一致）",
        fs=9.5,
        fc=pal.title_fc,
        ec=pal.title_ec,
    )

    daily_rect = patches.FancyBboxPatch(
        (3.5, 7.5),
        50.5,
        88.0,
        boxstyle="round,pad=0.02,rounding_size=0.85",
        linewidth=1.0,
        edgecolor="#90caf9",
        facecolor="#e3f2fd",
        alpha=0.32,
        zorder=0,
    )
    weekly_rect = patches.FancyBboxPatch(
        (56.5, 7.5),
        40.0,
        88.0,
        boxstyle="round,pad=0.02,rounding_size=0.85",
        linewidth=1.0,
        edgecolor="#81c784",
        facecolor="#e8f5e9",
        alpha=0.38,
        zorder=0,
    )
    ax.add_patch(daily_rect)
    ax.add_patch(weekly_rect)
    ax.text(28.5, 92.5, "日度复盘", ha="center", fontsize=8.75, color="#0d47a1", weight="bold", zorder=2)
    ax.text(78.0, 92.5, "周度闭环", ha="center", fontsize=8.75, color="#1b5e20", weight="bold", zorder=2)

    fs = 6.55
    x_chain = 33.0
    x_b, x_a = 13.5, 33.0
    y_a = 87.0
    _rounded_box(
        ax,
        (x_b, y_a),
        17.0,
        bh,
        "断点恢复\n可选",
        fs=5.85,
        fc="#fff3e0",
        ec="#ef6c00",
    )
    _rounded_box(
        ax,
        (x_a, y_a),
        bw,
        bh,
        "get_market_summary",
        fs=fs,
        fc="#e3f2fd",
        ec="#1565c0",
    )
    _dashed_arrow(ax, x_b + 8.5, y_a, x_a - bw / 2 + 0.5, y_a)

    chain_labels = [
        "分离确认与\n要闻映射",
        "可选风格探测",
        "build_prompt\n与 call_llm",
        "摘要与龙头\n章节校验",
        "要闻前缀\n/ 文末附图",
    ]
    y_cur = y_a - bh / 2 - GAP - bh / 2
    centers: list[tuple[float, float]] = []
    for i, lab in enumerate(chain_labels):
        _rounded_box(ax, (x_chain, y_cur), bw, bh, lab, fs=fs, fc="#e3f2fd", ec="#1565c0")
        centers.append((x_chain, y_cur))
        if i == 0:
            _arrow(ax, x_a, y_a - bh / 2, x_chain, y_cur + bh / 2)
        else:
            py = centers[i - 1][1]
            _arrow(ax, x_chain, py - bh / 2, x_chain, y_cur + bh / 2)
        y_cur = y_cur - bh - GAP

    x_h = 19.5
    x_w = 77.0
    y_g = centers[-1][1]
    g_bot = y_g - bh / 2
    y_hw = y_g - bh / 2 - GAP - bh / 2
    _rounded_box(
        ax,
        (x_h, y_hw),
        24.0,
        bh,
        "龙头池存档 ·\n风格指数 · 邮件",
        fs=6.0,
        fc="#e8eaf6",
        ec="#4527a0",
    )
    _rounded_box(
        ax,
        (x_w, y_hw),
        bw_w,
        bh,
        "程序统计周报\nMarkdown",
        fs=6.0,
        fc="#c8e6c9",
        ec="#2e7d32",
    )
    _arrow(ax, x_chain, g_bot, x_h, y_hw + bh / 2)
    # G → W1：折线经中间走廊（先横移再落到 W1 左侧），避免斜穿两列
    half_ww = bw_w / 2
    _dashed_line_segments(
        ax,
        [
            (x_chain + bw / 2 + 0.3, g_bot),
            (54.0, g_bot),
            (54.0, y_hw),
        ],
    )
    _dashed_arrow(ax, 54.0, y_hw, x_w - half_ww - 0.2, y_hw)
    _edge_label(ax, 58.5, (g_bot + y_hw) / 2, "watchlist", fs=5.7)

    weekly_rest = [
        "可选大模型附录",
        "update_from_recent_returns",
        "权重异常邮件与\n周报 SMTP",
    ]
    prev_wy = y_hw - bh / 2
    y_w = y_hw - bh / 2 - GAP - bh / 2
    w_centers: list[tuple[float, float]] = []
    for j, wlab in enumerate(weekly_rest):
        _rounded_box(
            ax,
            (x_w, y_w),
            bw_w,
            bh,
            wlab,
            fs=5.95 if j < 2 else 5.75,
            fc="#e8f5e9",
            ec="#388e3c",
        )
        w_centers.append((x_w, y_w))
        _arrow(ax, x_w, prev_wy, x_w, y_w + bh / 2)
        prev_wy = y_w - bh / 2
        y_w = y_w - bh - GAP

    x_e, y_e = centers[2]
    _w3_x, w3_y = w_centers[1]
    half_w = bw_w / 2
    y_e_top = y_e + bh / 2
    # 折线：W3 右侧 → 右缘竖直抬升到 E 顶高 → 水平指向 E（不穿过中间蓝框）
    x_r = 96.0
    w3_right = _w3_x + half_w
    y_lane = y_e_top + 0.45
    _dashed_line_segments(
        ax,
        [(w3_right, w3_y), (x_r, w3_y), (x_r, y_lane)],
    )
    _dashed_arrow(ax, x_r, y_lane, x_chain + bw / 2 - 0.25, y_lane)
    _edge_label(ax, 90.0, (w3_y + y_lane) / 2, "五桶权重 → prompt", fs=5.4)

    ax.text(
        50.0,
        3.2,
        "实线：主执行顺序；灰虚线：数据/权重回流。"
        " 不含 DeepSeek 增强四段与 llm_intel（与当前 ReplayTask 一致）。",
        ha="center",
        va="center",
        fontsize=6.15,
        color="#546e7a",
        linespacing=1.15,
    )

    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fig.savefig(
        out_path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.35,
        facecolor=fig.patch.get_facecolor(),
    )
    plt.close(fig)


def save_kebi_framework_png(out_path: str, *, dpi: int = 220) -> None:
    """
    92科比「龙头-补涨-切换-空仓」扩展图：在标准误区—对策之上，
    增加「情绪周期四阶段」与分阶段策略（I→I1～I4→J1～J4→K）。
    """
    import matplotlib.pyplot as plt

    _configure_font()
    cx = 50.0
    GAP = 1.15
    pal = FlowchartPalette(
        bg="#f5f4ff",
        title_fc="#e8eaf6",
        title_ec="#3949ab",
        b_ec="#5c6bc0",
        b_fc="#c5cae9",
        b_tc="#1a237e",
        c_fc="#ede7f6",
        c_ec="#5e35b1",
        d_fc="#d7ccc8",
        d_ec="#5d4037",
        e_fc="#efebe9",
        e_ec="#4e342e",
        f_fc="#ffcdd2",
        f_ec="#c62828",
        g_ec="#3949ab",
        g_fc="#c5cae9",
        g_tc="#1a237e",
        h_fc="#c8e6c9",
        h_ec="#2e7d32",
        i_fc="#b2dfdb",
        i_ec="#00695c",
    )

    # 加宽、压扁画布比例，避免「细长条」变形；连线改为正交汇流
    fig_w, fig_h = 15.5, 27.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 128)
    ax.axis("off")
    fig.patch.set_facecolor(pal.bg)
    ax.set_facecolor(pal.bg)

    # —— A ——
    y = 122.0
    h_a = 4.2
    _rounded_box(
        ax,
        (cx, y),
        92,
        h_a,
        "帖子核心：情绪周期四阶段 × 龙头-补涨-切换-空仓 框架",
        fs=10.2,
        fc=pal.title_fc,
        ec=pal.title_ec,
    )
    y_a_bot = y - h_a / 2
    _arrow(ax, cx, y_a_bot - 0.1, cx, y_a_bot - GAP - 0.35)

    # —— B ——
    y = y_a_bot - GAP - 0.45 - 2.45
    h_b = 5.0
    _diamond_text(
        ax,
        (cx, y),
        58,
        h_b,
        "「短线选手的五大底层误区」",
        fs=8.8,
        ec=pal.b_ec,
        fc=pal.b_fc,
        tcolor=pal.b_tc,
    )
    b_bot = y - h_b / 2

    c_items = [
        "迷失本质\n「迷于表象,死于本质，把投机当投资」",
        "手法执念\n「把悟道等同于学会某种固定手法」",
        "中位股思维\n「既不敢追高龙头，又不愿埋伏低位」",
        "题材错判\n「过于在意题材内容，忽视题材出现的时机」",
        "扛单不止损\n「被套后死拿，等待解套」",
    ]
    bh_c = 6.5
    groups_c = _split_indices(5)
    row_step_c = bh_c + 0.88
    y_c1 = b_bot - GAP - 0.95 - bh_c / 2
    row_c_y = [y_c1, y_c1 - row_step_c]
    c_centers: list[tuple[float, float, float]] = []
    bw = 26.0
    for ri, idxs in enumerate(groups_c):
        cy = row_c_y[ri]
        xs = _xs_for_row(len(idxs))
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw,
                bh_c,
                c_items[ii],
                fs=6.35,
                fc=pal.c_fc,
                ec=pal.c_ec,
            )
            c_centers.append((xs[j], cy, bh_c / 2))
    _hub_fan_down(
        ax, cx, b_bot, [(bx, by + hh) for bx, by, hh in c_centers], color="#455a64"
    )
    c_bottom = min(by - hh for _, by, hh in c_centers)

    # —— D ——
    h_d = 3.5
    d_y = c_bottom - GAP - h_d / 2 - 0.2
    _rounded_box(
        ax,
        (cx, d_y),
        44,
        h_d,
        "造成的行为后果",
        fs=8.5,
        fc=pal.d_fc,
        ec=pal.d_ec,
    )
    d_top, d_bot = d_y + h_d / 2, d_y - h_d / 2
    _fan_merge_up(
        ax, cx, d_top, [(bx, by - hh) for bx, by, hh in c_centers], color="#455a64"
    )

    e_items = [
        "高位接盘\n信了趋势故事后不止损",
        "模式固化\n遇到不适应行情就大亏",
        "两头挨打\n买中位股，涨跌都难受",
        "错过主升\n在错误的题材上浪费时间",
        "一波大亏\n利润回吐甚至爆仓",
    ]
    bh_e = 5.85
    groups_e = _split_indices(5)
    row_step_e = bh_e + 0.88
    y_e1 = d_bot - GAP - 0.85 - bh_e / 2
    row_e_y = [y_e1, y_e1 - row_step_e]
    e_centers: list[tuple[float, float, float]] = []
    for ri, idxs in enumerate(groups_e):
        cy = row_e_y[ri]
        xs = _xs_for_row(len(idxs))
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw,
                bh_e,
                e_items[ii],
                fs=6.45,
                fc=pal.e_fc,
                ec=pal.e_ec,
            )
            e_centers.append((xs[j], cy, bh_e / 2))
    _hub_fan_down(
        ax, cx, d_bot, [(bx, by + hh) for bx, by, hh in e_centers], color="#455a64"
    )
    e_bottom = min(by - hh for _, by, hh in e_centers)

    # —— F ——
    h_f = 4.6
    f_y = e_bottom - GAP - h_f / 2 - 0.15
    _rounded_box(
        ax,
        (cx, f_y),
        90,
        h_f,
        "交易恶果\n无法完成从初级盈利到高阶悟道的跨越",
        fs=8.0,
        fc=pal.f_fc,
        ec=pal.f_ec,
    )
    f_top = f_y + h_f / 2
    _fan_merge_up(
        ax, cx, f_top, [(bx, by - hh) for bx, by, hh in e_centers], color="#455a64"
    )

    # —— G（双行）——
    h_g = 6.2
    g_y = f_y - h_f / 2 - GAP - h_g / 2 - 0.15
    _diamond_text(
        ax,
        (cx, g_y),
        58,
        h_g,
        "92科比的解决之道\n「大道无形，无所不及」",
        fs=7.8,
        ec=pal.g_ec,
        fc=pal.g_fc,
        tcolor=pal.g_tc,
    )
    g_bot = g_y - h_g / 2

    h_items = [
        "洞察本质\n「投机是市场的本质，股票是筹码交换的游戏」",
        "大道无形\n「真正的悟道不是限制于某种手法」",
        "框架思维\n「龙头-补涨-切换-空仓」",
        "择时第一\n「题材内容不重要，题材出现的时机才是重点」",
        "杀伐果断\n「超短做隔日，不及预期就走人」",
    ]
    bh_h = 6.85
    groups_h = _split_h(5)
    row_step_h = bh_h + 0.88
    y_h1 = g_bot - GAP - 0.88 - bh_h / 2
    row_h_y = [y_h1, y_h1 - row_step_h]
    h_centers: list[tuple[float, float, float]] = []
    bw_h = 28.0
    for ri, idxs in enumerate(groups_h):
        cy = row_h_y[ri]
        xs = _xs_for_row(len(idxs))
        for j, ii in enumerate(idxs):
            _rounded_box(
                ax,
                (xs[j], cy),
                bw_h,
                bh_h,
                h_items[ii],
                fs=6.3,
                fc=pal.h_fc,
                ec=pal.h_ec,
            )
            h_centers.append((xs[j], cy, bh_h / 2))
    _hub_fan_down(
        ax, cx, g_bot, [(bx, by + hh) for bx, by, hh in h_centers], color="#455a64"
    )
    h_bottom = min(by - hh for _, by, hh in h_centers)

    # —— I 菱形（情绪周期应用）——
    h_id = 4.85
    id_y = h_bottom - GAP - h_id / 2 - 0.38
    _diamond_text(
        ax,
        (cx, id_y),
        56,
        h_id,
        "情绪周期四阶段的框架应用",
        fs=8.0,
        ec=pal.g_ec,
        fc=pal.g_fc,
        tcolor=pal.g_tc,
    )
    id_top = id_y + h_id / 2
    id_bot = id_y - h_id / 2
    _fan_merge_up(
        ax, cx, id_top, [(bx, by - hh) for bx, by, hh in h_centers], color="#455a64"
    )

    # —— I1～I4 ——
    stage_labels = [
        "阶段一\n低位试错期",
        "阶段二\n主升浪阶段",
        "阶段三\n高位震荡期",
        "阶段四\n主跌阶段",
    ]
    xs4 = (14.0, 38.0, 62.0, 86.0)
    h_st = 4.15
    y_st = id_bot - GAP - h_st / 2 - 0.3
    st_centers: list[tuple[float, float, float]] = []
    for i, lab in enumerate(stage_labels):
        _rounded_box(
            ax,
            (xs4[i], y_st),
            22.0,
            h_st,
            lab,
            fs=6.75,
            fc="#e1f5fe",
            ec="#0277bd",
        )
        st_centers.append((xs4[i], y_st, h_st / 2))
    _hub_fan_down(
        ax,
        cx,
        id_bot,
        [(bx, by + hh) for bx, by, hh in st_centers],
        color="#455a64",
        bus_frac=0.38,
    )

    # —— J1～J4 策略块 ——
    j_texts = [
        "策略：切换\n仓位≤20%\n布局低位新题材，试错积极\n案例：轴研科技2板切入4连板",
        "策略：龙头\n仓位≥70%\n分歧时介入龙头，预判题材延续性\n案例：星期六、省广集团主升",
        "策略：空仓/轻仓\n仓位≤10%\n不建议博弈穿越，性价比太低\n高位震荡期轻仓应对",
        "策略：空仓/尾盘轻仓试错\n仓位≤10%\n主跌后尾盘找买点\n主跌后必定有切换的蛛丝马迹",
    ]
    h_j = 10.2
    w_j = 22.5
    st_bottom = min(sy - sh for (_, sy, sh) in st_centers)
    y_j = st_bottom - GAP - h_j / 2 - 0.3
    j_centers: list[tuple[float, float, float]] = []
    for i, txt in enumerate(j_texts):
        _rounded_box(
            ax,
            (xs4[i], y_j),
            w_j,
            h_j,
            txt,
            fs=5.05,
            fc="#fff8e1",
            ec="#ff8f00",
        )
        j_centers.append((xs4[i], y_j, h_j / 2))
    for (sx, sy, shh), (jx, jy, jhh) in zip(st_centers, j_centers):
        _elbow_chain_arrow(
            ax, [(sx, sy - shh), (jx, sy - shh), (jx, jy + jhh)], color="#455a64"
        )

    # —— K ——
    h_k = 5.6
    j_bottom = min(jy - jhh for (_, jy, jhh) in j_centers)
    y_k = j_bottom - GAP - h_k / 2 - 0.28
    if y_k < 3.5:
        y_k = 3.5
    _rounded_box(
        ax,
        (cx, y_k),
        94,
        h_k,
        "交易正果\n四年从数万元做到上亿，半年500万做到2300万",
        fs=8.2,
        fc=pal.i_fc,
        ec=pal.i_ec,
    )
    k_top = y_k + h_k / 2
    _fan_merge_up(
        ax, cx, k_top, [(bx, by - hh) for bx, by, hh in j_centers], color="#455a64"
    )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(
        out_path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.4,
        facecolor=fig.patch.get_facecolor(),
    )
    plt.close(fig)
