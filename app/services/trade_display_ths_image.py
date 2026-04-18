# -*- coding: utf-8 -*-
"""
移动端「资金/持仓」风格截图：按交易日 akshare 日线收盘价回显市值与浮动盈亏，
仅作展示存档，不构成投资建议。界面为原创布局（参考常见证券交易 App 信息结构）。
"""
from __future__ import annotations

import os
import re
from typing import Any, Mapping, Optional

from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib import pyplot as plt

from app.utils.config_paths import data_dir
from app.utils.logger import get_logger

_log = get_logger(__name__)

_W = 390
_H = 848


def _trade_display_dir() -> str:
    return os.path.join(data_dir(), "trade_display")


def _format_trade_date(ds: str) -> str:
    s = str(ds)[:8]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _pick_cjk_font() -> Optional[fm.FontProperties]:
    windir = os.environ.get("WINDIR", "")
    candidates: list[str] = []
    if windir:
        candidates.extend(
            [
                os.path.join(windir, "Fonts", "msyh.ttc"),
                os.path.join(windir, "Fonts", "msyhbd.ttc"),
                os.path.join(windir, "Fonts", "simhei.ttf"),
                os.path.join(windir, "Fonts", "simsun.ttc"),
            ]
        )
    candidates.extend(
        [
            # Ubuntu `fonts-noto-cjk`（GitHub Actions 常见）
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
    )
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                return fm.FontProperties(fname=path)
            except Exception:
                continue
    return None


def _cfg_image_enabled() -> bool:
    try:
        from app.utils.config import ConfigManager

        return bool(ConfigManager().get("enable_trade_display_image", True))
    except Exception:
        return True


def _relative_url_for_markdown(abs_path: str) -> str:
    """报告与仓库根相对路径一致时使用正斜杠。"""
    try:
        from app.utils.config_paths import _project_root

        root = _project_root()
        ap = os.path.abspath(abs_path)
        rel = os.path.relpath(ap, root)
        return rel.replace(os.sep, "/")
    except Exception:
        return abs_path.replace(os.sep, "/")


def write_trade_display_png(
    trade_date: str,
    summary: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """
    写入 `data/trade_display/{trade_date}.png`，返回相对仓库根的路径供 Markdown 嵌入。
    失败时返回 None（附录回退为纯文本表格）。
    """
    from app.services import simulated_account as sa

    if not _cfg_image_enabled():
        return None
    cfg = sa._load_config()
    if not cfg[0]:
        return None
    enabled, initial_cash, *_ = cfg
    ds = str(trade_date)[:8]
    if len(ds) != 8 or not re.match(r"^\d{8}$", ds):
        return None

    st = sa._ensure_state_shape(sa.load_state(), initial_cash)
    cash = float(st.get("cash", 0))
    positions = [p for p in (st.get("positions") or []) if isinstance(p, dict)]

    fp = _pick_cjk_font()
    if fp is None:
        _log.warning("trade_display: 未找到中文字体，跳过生成图片")
        return None

    rows: list[dict[str, Any]] = []
    pos_cost = 0.0
    for p in positions:
        code = sa._norm6(p.get("code"))
        qty = int(p.get("qty") or 0)
        bp = float(p.get("buy_price") or 0)
        name = str(p.get("name") or "")[:8]
        if len(code) != 6 or qty <= 0 or bp <= 0:
            continue
        bar = sa._fetch_daily_ohlc(code, ds)
        close = bar.get("close")
        if close is None or close <= 0:
            close = bp
        mv = round(qty * float(close), 2)
        cost = round(qty * bp, 2)
        pos_cost += cost
        pl = round(mv - cost, 2)
        pct = round((float(close) / bp - 1.0) * 100.0, 2) if bp > 0 else 0.0
        rows.append(
            {
                "code": code,
                "name": name or code,
                "qty": qty,
                "close": float(close),
                "buy_price": bp,
                "mv": mv,
                "pl": pl,
                "pct": pct,
            }
        )

    total_mv = round(cash + sum(r["mv"] for r in rows), 2)
    float_pl = round(sum(r["pl"] for r in rows), 2)
    denom = pos_cost if pos_cost > 0 else 1.0
    float_pct = round(float_pl / denom * 100.0, 2)

    out_dir = _trade_display_dir()
    os.makedirs(out_dir, exist_ok=True)
    out_abs = os.path.join(out_dir, f"{ds}.png")

    try:
        plt.rcParams["axes.unicode_minus"] = False
        fig = plt.figure(figsize=(_W / 100, _H / 100), dpi=100, facecolor="#f2f2f2")
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, _W)
        ax.set_ylim(0, _H)
        ax.axis("off")

        # 顶栏（常见移动端证券 App 红顶栏）
        ax.add_patch(Rectangle((0, _H - 52), _W, 52, facecolor="#e62828", edgecolor="none"))
        ax.text(
            _W / 2,
            _H - 22,
            "实盘交易展示",
            ha="center",
            va="center",
            color="white",
            fontsize=17,
            fontproperties=fp,
        )
        ax.text(
            _W / 2,
            _H - 40,
            _format_trade_date(ds),
            ha="center",
            va="center",
            color="#ffd0d0",
            fontsize=11,
            fontproperties=fp,
        )

        y0 = _H - 52 - 12
        # 资产概要卡片
        card_h = 118
        ax.add_patch(
            FancyBboxPatch(
                (12, y0 - card_h),
                _W - 24,
                card_h,
                boxstyle="round,pad=0.008",
                facecolor="white",
                edgecolor="#e8e8e8",
                linewidth=0.8,
            )
        )
        ax.text(24, y0 - 22, "总资产（元）", fontsize=11, color="#888888", fontproperties=fp)
        ax.text(
            24,
            y0 - 52,
            f"{total_mv:,.2f}",
            fontsize=22,
            color="#111111",
            fontproperties=fp,
        )
        pl_color = "#e62828" if float_pl >= 0 else "#00a854"
        ax.text(
            24,
            y0 - 78,
            "持仓浮动盈亏",
            fontsize=11,
            color="#888888",
            fontproperties=fp,
        )
        ax.text(
            24,
            y0 - 98,
            f"{float_pl:+,.2f}  ({float_pct:+.2f}%)",
            fontsize=13,
            color=pl_color,
            fontproperties=fp,
        )
        ax.text(
            _W - 24,
            y0 - 98,
            f"可取 {cash:,.0f}",
            fontsize=11,
            color="#666666",
            ha="right",
            fontproperties=fp,
        )

        y = y0 - card_h - 20
        ax.text(16, y, "持仓", fontsize=14, color="#333333", fontproperties=fp)
        y -= 28

        if not rows:
            ax.text(
                24,
                y,
                "当前空仓",
                fontsize=13,
                color="#999999",
                fontproperties=fp,
            )
            y -= 36
        else:
            for r in rows[:8]:
                row_h = 86
                ax.add_patch(
                    FancyBboxPatch(
                        (12, y - row_h),
                        _W - 24,
                        row_h - 6,
                        boxstyle="round,pad=0.006",
                        facecolor="white",
                        edgecolor="#ebebeb",
                        linewidth=0.6,
                    )
                )
                title = f"{r['name']}  {r['code']}"
                ax.text(22, y - row_h + 20, title, fontsize=13, color="#111", fontproperties=fp)
                ax.text(
                    22,
                    y - row_h + 42,
                    f"市值 {r['mv']:,.0f}  ·  {r['qty']}股",
                    fontsize=11,
                    color="#666666",
                    fontproperties=fp,
                )
                c_up = "#e62828"
                c_dn = "#00a854"
                pc = c_up if r["pct"] >= 0 else c_dn
                ax.text(
                    _W - 22,
                    y - row_h + 22,
                    f"{r['pct']:+.2f}%",
                    fontsize=14,
                    color=pc,
                    ha="right",
                    fontproperties=fp,
                )
                ax.text(
                    22,
                    y - row_h + 62,
                    f"现价 {r['close']:.3f}    成本 {r['buy_price']:.3f}",
                    fontsize=10,
                    color="#999999",
                    fontproperties=fp,
                )
                y -= row_h

        pend = [x for x in (st.get("pending_sells") or []) if isinstance(x, dict)]
        if pend and y > 120:
            ax.text(16, y, "已登记卖出（次日开盘）", fontsize=12, color="#333333", fontproperties=fp)
            y -= 20
            for p in pend[:3]:
                line = (
                    f"{sa._norm6(p.get('code'))}  {p.get('qty')}股  "
                    f"→{str(p.get('sell_execute_date') or '')[:8]}"
                )
                ax.text(20, y, line[:42], fontsize=10, color="#666666", fontproperties=fp)
                y -= 16

        sb = [x for x in (st.get("scheduled_buys") or []) if isinstance(x, dict)]
        if sb and y > 80:
            ax.text(16, y, "待执行买入", fontsize=12, color="#333333", fontproperties=fp)
            y -= 20
            for s in sb[:2]:
                line = f"信号 {str(s.get('signal_date'))[:8]} → {str(s.get('buy_date'))[:8]} 开盘"
                ax.text(20, y, line, fontsize=10, color="#666666", fontproperties=fp)
                y -= 16

        eq_cost = sa._equity_mark(st)
        foot_y = 10
        if summary and "today_mkt" in summary:
            tg = float(summary.get("today_gain", 0))
            cp = float(summary.get("cum_pnl", 0))
            cr = float(summary.get("cum_pct", 0))
            foot_y = 46
            ax.text(
                12,
                58,
                f"今日收益：{tg:+,.2f} 元",
                fontsize=11,
                color="#333333",
                fontproperties=fp,
            )
            ax.text(
                12,
                40,
                f"实盘至今收益：{cp:+,.2f} 元",
                fontsize=11,
                color="#333333",
                fontproperties=fp,
            )
            ax.text(
                12,
                22,
                f"实盘至今收益率：{cr:+.2f}%",
                fontsize=11,
                color="#333333",
                fontproperties=fp,
            )
        ax.text(
            12,
            foot_y,
            f"成本口径总资产 {eq_cost:,.2f} 元 · 行情为当日收盘",
            fontsize=8,
            color="#aaaaaa",
            fontproperties=fp,
        )

        fig.savefig(out_abs, dpi=100, facecolor=fig.get_facecolor(), pad_inches=0.02)
        plt.close(fig)
    except Exception as ex:
        _log.warning("trade_display 生成失败: %s", ex)
        try:
            plt.close("all")
        except Exception:
            pass
        return None

    return _relative_url_for_markdown(out_abs)
