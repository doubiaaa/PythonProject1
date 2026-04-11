# -*- coding: utf-8 -*-
"""
生成复盘文末第 3～11 张心智流程图（淘股吧名家系列）。

项目根目录执行:
  python scripts/generate_replay_footer_charts_extended.py
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.utils.replay_footer_chart_draw import FlowchartPalette, FlowchartSpec, save_flowchart_png


def _p(**kwargs) -> FlowchartPalette:
    base = FlowchartPalette()
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


CHARTS: list[tuple[str, str, str, FlowchartSpec]] = [
    (
        "replay_footer_wangtao.png",
        "replay_footer_wangtao",
        "职业炒手（王涛）校长·大盘势能",
        FlowchartSpec(
            core_title="帖子核心：借大盘之势，调动市场合力为我所用",
            b_diamond="「短线选手的三大致命错误」",
            c_items=[
                "逆势交易\n「弱市不做的道理，无数人做不到」",
                "只看个股不看大盘\n「龙头股必须能带动大盘和板块」",
                "割肉犹豫\n「无论水平多高，做不到及时止损都会亏损」",
            ],
            e_items=[
                "弱市中频繁交易\n利润大幅回吐",
                "误判龙头\n买到跟风股",
                "亏损扛单\n小亏变大亏",
            ],
            f_bad=("交易恶果", "长期无法突破百万门槛"),
            g_diamond="职业炒手的解决之道",
            h_items=[
                "弱市不做\n「短线炒手第一原则——弱市不做」",
                "借大盘势能\n「出击时间必须把握住大盘否级泰来的临界点」",
                "龙头定义\n「龙头股是能够带动大盘和板块的领涨股」",
                "调动合力\n「在特殊时间调动市场人气，启动市场合力为我所用」",
            ],
            i_good=("交易正果", "突破百万魔咒，稳定上亿"),
            palette=_p(bg="#fff8f5", title_fc="#ffe0b2", title_ec="#e65100"),
            fig_h_inch=24.0,
        ),
    ),
    (
        "replay_footer_yangjia.png",
        "replay_footer_yangjia",
        "炒股养家·情绪大师",
        FlowchartSpec(
            core_title="帖子核心：揣摩市场情绪，判断风险与收益的比较",
            b_diamond="「交易者的常见情绪误区」",
            c_items=[
                "执念持股\n「高手买入龙头，超级高手卖出龙头」",
                "跟风心理\n「盲目跟风，没有自己的判断」",
                "恐惧踏空\n「害怕错过每一个机会」",
                "逆势死扛\n「与市场对抗，不相信趋势」",
                "贪婪追高\n「高位接盘，不知进退」",
            ],
            e_items=[
                "不会卖\n坐过山车，利润回吐",
                "人云亦云\n被市场情绪左右",
                "冲动交易\n追涨杀跌",
                "深套不止损\n资金被锁定",
                "高位站岗\n成为接盘侠",
            ],
            f_bad=("交易恶果", "无法稳定盈利，账户大起大落"),
            g_diamond="炒股养家的解决之道",
            h_items=[
                "揣摩情绪\n「核心思想是基于对市场情绪的揣摩」",
                "识别阶段\n「高手买入龙头，超级高手卖出龙头」",
                "风险收益比\n「判断风险和收益的比较，指导实际操作」",
                "信念驱动\n「信念」二字是在股市立足的根本",
            ],
            i_good=("交易正果", "从几十万做到几十亿"),
            palette=_p(bg="#f3f8ff", title_fc="#bbdefb", title_ec="#1565c0"),
            fig_h_inch=28.0,
        ),
    ),
    (
        "replay_footer_longfeihu.png",
        "replay_footer_longfeihu",
        "龙飞虎·回撤控制",
        FlowchartSpec(
            core_title="帖子核心：控制回撤是职业炒手的首要标准",
            b_diamond="「短线选手的常见偏执」",
            c_items=[
                "手法歧视\n「认为打板才是正道，低吸不入流」",
                "重仓赌徒心态\n「每次都想一把翻倍」",
                "无视回撤\n「只关注进攻，不关注防守」",
                "追求速度\n「想一夜暴富，缺乏耐心」",
            ],
            e_items=[
                "手法单一\n遇到不适应行情就大亏",
                "账户大起大落\n多次坐过山车",
                "利润回吐严重\n辛苦赚的钱一次亏光",
                "心态崩溃\n越急越亏，恶性循环",
            ],
            f_bad=("交易恶果", "无法职业化，长期被市场淘汰"),
            g_diamond="龙飞虎的解决之道",
            h_items=[
                "多元化手法\n「封板也好，逢低也好，都是交易手段，没有厚薄之分」",
                "控制回撤\n「衡量能否职业炒股很重要的一条就是能控制回撤幅度」",
                "龟兔赛跑\n「不怕你跑得慢，就怕你老跑回头路」",
                "复利思维\n「靠着复利的神奇，靠着防守，争取年收益50-100%」",
            ],
            i_good=("交易正果", "稳定复利，走在不断复利的康庄大道"),
            palette=_p(bg="#f5fff8", title_fc="#c8e6c9", title_ec="#2e7d32"),
            fig_h_inch=26.0,
        ),
    ),
    (
        "replay_footer_zhaolaoge.png",
        "replay_footer_zhaolaoge",
        "赵老哥·八年一万倍",
        FlowchartSpec(
            core_title="帖子核心：只做龙头和主升，第一时间上车，及时切换",
            b_diamond="「散户选龙头的常见误区」",
            c_items=[
                "一板追龙头\n「一板能看出来个毛」",
                "无视爆量检验\n「没爆量的都不能说是龙头」",
                "抱死老题材\n「有新题材坚决抛弃老题材」",
                "买跟风股\n「只做龙头和主升，不买跟风票」",
            ],
            e_items=[
                "买到假龙头\n一进二就炸板",
                "追缩量板\n缺乏群众检验，容易A杀",
                "错失新周期\n在老题材上站岗",
                "收益有限\n龙头涨50%跟风只涨10%",
            ],
            f_bad=("交易恶果", "无法抓住真正的主升浪"),
            g_diamond="赵老哥的解决之道",
            h_items=[
                "二板定龙头\n「二板定龙头，一板能看出来个毛」",
                "爆量检验\n「没爆量的都不能说是龙头，既然是领袖，必须爆量」",
                "精神领袖\n「第一时间发现市场的精神领袖，第一时间上了她」",
                "果断切换\n「一直持有，直到发现市场新的精神领袖，果断切换」",
                "聚焦新题材\n「有新题材坚决抛弃老题材」",
            ],
            i_good=("交易正果", "八年一万倍，创造神话"),
            palette=_p(bg="#fff5f8", title_fc="#f8bbd9", title_ec="#c2185b"),
            fig_h_inch=27.0,
        ),
    ),
    (
        "replay_footer_niepan.png",
        "replay_footer_niepan",
        "涅槃重升·树干理论",
        FlowchartSpec(
            core_title="帖子核心：跟着情绪走，千万不要自以为是",
            b_diamond="「投机者的常见误区」",
            c_items=[
                "主观臆断\n「自以为是，不尊重市场」",
                "无视赚钱效应\n「只关心自己手里的股票」",
                "迷失于技术细节\n「只见树木不见森林」",
                "不敢买最强\n「总想买低位的，不敢追最强的」",
            ],
            e_items=[
                "逆势交易\n亏钱效应来了还强行操作",
                "踏空大行情\n错过主流热点",
                "交易混乱\n没有系统的交易框架",
                "收益平庸\n买不到真正的龙头",
            ],
            f_bad=("交易恶果", "无法实现从百万到亿级的跨越"),
            g_diamond="涅槃重升的解决之道",
            h_items=[
                "树干理论\n「投机做的是赚钱效应情绪的延续，对资金的吸引」",
                "情绪导向\n「跟着情绪走，千万不要自以为是」",
                "抓核心\n「做短线，就是抓核心，抓住当前阶段的龙头板块龙头个股」",
                "买最强\n「要学就学最牛逼的，要买就买最强的」",
            ],
            i_good=("交易正果", "4年100倍，从百万到过亿"),
            palette=_p(bg="#f8f6ff", title_fc="#d1c4e9", title_ec="#4527a0"),
            fig_h_inch=26.0,
        ),
    ),
    (
        "replay_footer_linghuchong.png",
        "replay_footer_linghuchong",
        "令胡冲·一念天堂一念地狱",
        FlowchartSpec(
            core_title="帖子核心：控制贪婪和恐惧，看盘即修心",
            b_diamond="「打板选手的心魔」",
            c_items=[
                "情绪失控\n「贪婪和恐惧无法控制」",
                "盲目打板\n「不是为了打板而打板」",
                "复盘懒惰\n「只看盘不复盘」",
                "时机错判\n「同一只股，昨天打板和今天打板是天堂地狱之别」",
            ],
            e_items=[
                "冲动交易\n无脑打板",
                "炸板大面\n缺乏逻辑支撑",
                "盘感迟钝\n无法感知市场变化",
                "高位接盘\n成为接盘侠",
            ],
            f_bad=("交易恶果", "打板变成吃面，账户腰斩"),
            g_diamond="令胡冲的解决之道",
            h_items=[
                "修心第一\n「心脏这一关必须得过，贪婪和恐惧必须能自己控制」",
                "打人气板\n「如果可以，尽量打人气板，人气板是盘中出现的」",
                "看盘即修心\n「看盘是训练你的情绪控制，对贪念和恐惧的控制力」",
                "复盘即勤奋\n「复盘是考验你的勤奋度，累积对市场的熟悉度」",
            ],
            i_good=("交易正果", "2015年50万做到800万"),
            palette=_p(bg="#fffef5", title_fc="#fff9c4", title_ec="#f9a825"),
            fig_h_inch=26.0,
        ),
    ),
    (
        "replay_footer_bangzhongbang.png",
        "replay_footer_bangzhongbang",
        "榜中榜·一年半150倍",
        FlowchartSpec(
            core_title="帖子核心：理解力是核心，打板只是工具",
            b_diamond="「超短选手的认知误区」",
            c_items=[
                "本末倒置\n「只关心打板技巧，不关心理解力」",
                "逆市操作\n「牛市任何利空都是利好，熊市任何利好都是利空」",
                "迷失于技术\n「只见形态，不见本质」",
                "情绪失控\n「被市场情绪牵着走」",
            ],
            e_items=[
                "形似神不似\n打板形态对了但逻辑不对",
                "屡买屡亏\n看不清大势",
                "交易僵化\n死板执行技术指标",
                "追涨杀跌\n情绪化交易",
            ],
            f_bad=("交易恶果", "实盘赛连续垫底"),
            g_diamond="榜中榜的解决之道",
            h_items=[
                "理解力至上\n「股票真正的大核心还是理解力，理解力透彻了，无需打板」",
                "寻找热点中的热点\n「寻找热点中的热点」",
                "情绪优先\n「更加注重市场情绪，其次是技术」",
                "看透牛熊\n「牛市任何利空都是利好，熊市任何利好都是利空」",
            ],
            i_good=("交易正果", "18个月从10万做到1000万+，百倍收益"),
            palette=_p(bg="#f5f8fa", title_fc="#b2ebf2", title_ec="#00838f"),
            fig_h_inch=26.0,
        ),
    ),
    (
        "replay_footer_shuige.png",
        "replay_footer_shuige",
        "水哥割股·3年300倍",
        FlowchartSpec(
            core_title="帖子核心：做主线的核心，不做杂毛",
            b_diamond="「年轻交易者的典型错误」",
            c_items=[
                "加杠杆\n「两融账户爆仓的惨痛教训」",
                "频繁翻倍腰斩\n「不停翻倍腰斩的恶性循环」",
                "追杂毛\n「不做主线核心，到处乱买」",
                "持股信心不足\n「拿不住真正的牛股」",
            ],
            e_items=[
                "账户爆仓\n杠杆放大亏损",
                "无法稳定盈利\n大起大落",
                "收益平庸\n错过真正的主升浪",
                "卖飞大牛股\n赚小亏大",
            ],
            f_bad=("交易恶果", "爆仓后被迫重新开始"),
            g_diamond="水哥割股的解决之道",
            h_items=[
                "去杠杆\n痛定思痛，卸掉杠杆，以4万本金重新开始",
                "做主线核心\n「第一是做主线的核心」",
                "做领涨异动\n「主线不明显的情况下，结合消息面做领涨的异动股」",
                "选股即持股\n「核心不在于是否满仓一股，而在于选股和持股」",
            ],
            i_good=("交易正果", "3年300倍，4万做到1300万"),
            palette=_p(bg="#f3fff5", title_fc="#a5d6a7", title_ec="#33691e"),
            fig_h_inch=26.0,
        ),
    ),
    (
        "replay_footer_linfengkuang.png",
        "replay_footer_linfengkuang",
        "林疯狂·9个月10倍",
        FlowchartSpec(
            core_title="帖子核心：快和简单，今日买明日卖，追求高赔率",
            b_diamond="「低吸选手的常见迷思」",
            c_items=[
                "害怕强势股\n「不敢低吸强势股和热门股」",
                "持股时间过长\n「参与调整段，浪费资金效率」",
                "仓位分散\n「不敢重仓出击」",
                "追半路板\n「在4-10个点之间追高」",
            ],
            e_items=[
                "收益平庸\n买不到真正的强势股",
                "资金周转慢\n效率低下",
                "盈利有限\n不敢重仓，赚不到大钱",
                "成本过高\n追在半山腰",
            ],
            f_bad=("交易恶果", "无法实现高速复利"),
            g_diamond="林疯狂的解决之道",
            h_items=[
                "超短模式\n「基本都是今日买，明日卖」",
                "低吸强势股\n「以低吸强势股和热门股为主，大多4个点之内低吸」",
                "精准买点\n「又以涨到1个点左右时买点多」",
                "全进全出\n「林疯狂的风格都是全进全出」",
                "快和简单\n「他最大的特点就是快和简单」",
            ],
            i_good=("交易正果", "9个月10倍，30万做到300万"),
            palette=_p(bg="#fff5f5", title_fc="#ffcdd2", title_ec="#c62828"),
            fig_h_inch=27.0,
        ),
    ),
]


def main() -> None:
    assets = os.path.join(_ROOT, "assets")
    for fname, _cid, label, spec in CHARTS:
        path = os.path.join(assets, fname)
        save_flowchart_png(spec, path)
        print(f"OK {label} -> {path}")


if __name__ == "__main__":
    main()
