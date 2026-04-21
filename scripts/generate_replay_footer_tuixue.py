# -*- coding: utf-8 -*-
"""生成「退学炒股」心智流程图 PNG。"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.utils.replay_footer_chart_draw import FlowchartPalette, FlowchartSpec, save_flowchart_png  # noqa: E402


def _p(**kwargs) -> FlowchartPalette:
    base = FlowchartPalette()
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


SPEC = FlowchartSpec(
    core_title="帖子核心：操作只有对错，盈利交给市场；没有自己的标的就不买",
    b_diamond="「退学炒股：常见心魔与误区」",
    c_items=[
        "踏空焦虑\n「看到别人赚钱就想乱买」",
        "连胜后浮躁\n「自信心爆棚、放大仓位」",
        "大亏后扳本\n「情绪化加仓想一把回本」",
        "方向性错误\n「庄股、迷信指标、盲从大神」",
        "幻想不止损\n「错了不割，抱有幻想」",
    ],
    e_items=[
        "陷入被动\n无计划瞎买",
        "大赚大亏\n回撤失控",
        "越套越深\n亏损扛单",
        "长期无进步\n运气主导",
        "心态崩溃\n影响操作",
    ],
    f_bad=("交易恶果", "难以稳定复利"),
    g_diamond="退学炒股的解决之道",
    h_items=[
        "性格修炼\n「人与人智商差小，性格差大」",
        "果断止损\n「错了就割，不要抱有幻想」",
        "标的纪律\n「没有自己的标的就不买」",
        "强势主升\n「主攻强势人气股主升段」",
    ],
    i_good=("交易正果", "十四个月百倍，几万到数百万"),
    palette=_p(bg="#f5f5f5", title_fc="#e0e0e0", title_ec="#424242"),
    fig_h_inch=28.0,
)


def main() -> None:
    out = os.path.join(_ROOT, "assets", "replay_footer_tuixue.png")
    save_flowchart_png(SPEC, out)
    print(f"已写入: {out}")


if __name__ == "__main__":
    main()
