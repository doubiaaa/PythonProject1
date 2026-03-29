# -*- coding: utf-8 -*-
"""
次日竞价半路模式 — 收盘后选股流程（东财行业板块数据近似实现）
说明：行业指数用东财行业板块；龙虎榜条件因数据可选未强制接入。
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd

from app.services.trend_momentum_strategy import (
    analyze_ohlcv,
    fetch_stock_hist_daily,
)

MODE_NAME = "次日竞价半路模式"
MAX_SECTORS_SCAN = 48
MAX_MAIN_SECTORS = 2
MAX_DRAGON_POOL = 5
TOP_N_DAYS = 5
VOL_DAYS = 3

HUO_KOU_TURNOVER_MIN = 1.5e8  # 元
RENQI_TURNOVER_LOW, RENQI_TURNOVER_HIGH = 10.0, 30.0
MCAP_MIN = 30e8  # 30 亿

# 趋势动量（EMA+RSI+ATR）接入评分：仅对预筛前列股票拉日 K，其余给中性分 2.5
ENABLE_TECH_MOMENTUM = True
TECH_EVAL_TOPN = 12

# 权重默认值（可被 replay_config.json 覆盖，见 _load_strategy_params）
W_MAIN = 0.22
W_DRAGON = 0.18
W_KLINE = 0.18
W_LIQ = 0.14
W_TECH = 0.28


def _load_strategy_params() -> dict:
    """从 ConfigManager 读权重与技术面开关；权重和须≈1，否则回退默认。"""
    from app.utils.config import ConfigManager

    cm = ConfigManager()

    def gf(key: str, default: float) -> float:
        try:
            return float(cm.get(key, default))
        except (TypeError, ValueError):
            return default

    w_main = gf("w_main", W_MAIN)
    w_dragon = gf("w_dragon", W_DRAGON)
    w_kline = gf("w_kline", W_KLINE)
    w_liq = gf("w_liq", W_LIQ)
    w_tech = gf("w_tech", W_TECH)
    s = w_main + w_dragon + w_kline + w_liq + w_tech
    if abs(s - 1.0) > 0.02:
        w_main, w_dragon, w_kline, w_liq, w_tech = W_MAIN, W_DRAGON, W_KLINE, W_LIQ, W_TECH
    try:
        topn = int(cm.get("tech_eval_topn", TECH_EVAL_TOPN))
    except (TypeError, ValueError):
        topn = TECH_EVAL_TOPN
    topn = max(3, min(48, topn))
    en = cm.get("enable_tech_momentum", ENABLE_TECH_MOMENTUM)
    if isinstance(en, str):
        enable_tech = en.strip().lower() in ("1", "true", "yes")
    else:
        enable_tech = bool(en)
    return {
        "w_main": w_main,
        "w_dragon": w_dragon,
        "w_kline": w_kline,
        "w_liq": w_liq,
        "w_tech": w_tech,
        "tech_eval_topn": topn,
        "enable_tech": enable_tech,
    }


def _log(fetcher, msg: str) -> None:
    t = getattr(fetcher, "current_task", None)
    if t and hasattr(t, "log"):
        t.log(msg)


def _prog(fetcher, p: int) -> None:
    t = getattr(fetcher, "current_task", None)
    if t is not None and hasattr(t, "progress"):
        t.progress = min(89, max(int(getattr(t, "progress", 0)), p))


def _norm_code(x) -> str:
    s = "".join(filter(str.isdigit, str(x)))
    return s.zfill(6)[:6] if s else ""


def _pick_sector_universe() -> list[str]:
    """优先取 5 日资金靠前的行业名称，缩小扫描范围。"""
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="5日", sector_type="行业资金流")
        if df is not None and not df.empty and "名称" in df.columns:
            names = df["名称"].dropna().astype(str).tolist()[:MAX_SECTORS_SCAN]
            if names:
                return names
    except Exception:
        pass
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty and "板块名称" in df.columns:
            return df["板块名称"].astype(str).tolist()[:MAX_SECTORS_SCAN]
    except Exception:
        pass
    return []


def _sector_hist_for_range(symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        df = ak.stock_board_industry_hist_em(
            symbol=symbol,
            start_date=start,
            end_date=end,
            period="日k",
            adjust="",
        )
        if df is None or df.empty:
            return None
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y%m%d")
        for c in ("涨跌幅", "成交额"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception:
        return None


def _last_n_trade_days(trade_days: list[str], date: str, n: int) -> list[str]:
    if date not in trade_days:
        return []
    i = trade_days.index(date)
    start = max(0, i - n + 1)
    return trade_days[start : i + 1]


def _sector_has_dragon(symbol: str) -> bool:
    """板块内是否存在涨幅>3% 的成份股（近似「龙头/军令状」）。"""
    try:
        cons = ak.stock_board_industry_cons_em(symbol=symbol)
        if cons is None or cons.empty or "涨跌幅" not in cons.columns:
            return False
        pct = pd.to_numeric(cons["涨跌幅"], errors="coerce")
        return bool((pct > 3).any())
    except Exception:
        return False


def _merge_spot_by_codes(codes: list[str], fetcher=None) -> dict[str, dict]:
    """全市场一次拉取，按代码取流通市值等（优先复用 DataFetcher 短缓存）。"""
    if not codes:
        return {}
    try:
        if fetcher is not None and hasattr(fetcher, "get_stock_zh_a_spot_em_cached"):
            spot = fetcher.get_stock_zh_a_spot_em_cached()
        else:
            spot = ak.stock_zh_a_spot_em()
    except Exception:
        return {}
    if spot is None or spot.empty or "代码" not in spot.columns:
        return {}
    spot = spot.copy()
    spot["code"] = spot["代码"].astype(str).map(_norm_code)
    want = set(codes)
    sub = spot[spot["code"].isin(want)]
    out = {}
    for _, r in sub.iterrows():
        c = r["code"]
        mv = None
        if "流通市值" in sub.columns:
            mv = float(pd.to_numeric(r.get("流通市值"), errors="coerce") or 0)
        elif "总市值" in sub.columns:
            mv = float(pd.to_numeric(r.get("总市值"), errors="coerce") or 0)
        out[c] = {
            "流通市值": mv,
            "涨跌幅": float(pd.to_numeric(r.get("涨跌幅"), errors="coerce") or 0),
            "换手率": float(pd.to_numeric(r.get("换手率"), errors="coerce") or 0),
        }
    return out


def _stock_ma_above(code: str, date: str, trade_days: list[str]) -> tuple[bool, bool]:
    """收盘价 > MA5 且 MA5 > MA20（用截止 date 的历史日 K）。"""
    try:
        i = trade_days.index(date)
    except ValueError:
        return False, False
    start_i = max(0, i - 60)
    start_d = trade_days[start_i]
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_d,
            end_date=date,
            adjust="qfq",
        )
        if df is None or len(df) < 20:
            return False, False
        close = pd.to_numeric(df["收盘"], errors="coerce")
        last = float(close.iloc[-1])
        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())
        return last > ma5, ma5 > ma20
    except Exception:
        return False, False


def _five_day_positive_spike(code: str, date: str, trade_days: list[str]) -> bool:
    """5 日内至少一日涨幅>=5%（资金活跃近似）。"""
    try:
        i = trade_days.index(date)
    except ValueError:
        return False
    start_i = max(0, i - 7)
    days = trade_days[start_i : i + 1]
    if len(days) < 2:
        return False
    start_d, end_d = days[0], days[-1]
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_d,
            end_date=end_d,
            adjust="qfq",
        )
        if df is None or df.empty or "涨跌幅" not in df.columns:
            return False
        pct = pd.to_numeric(df["涨跌幅"], errors="coerce")
        return bool((pct >= 5).any())
    except Exception:
        return False


def build_auction_halfway_report(
    date: str,
    trade_days: list[str],
    fetcher,
    df_zt: pd.DataFrame,
) -> tuple[str, dict]:
    """
    收盘后选股：主线板块 -> 龙头池 -> 评分。
    返回 (Markdown 文本, meta)。meta 供上层生成「数据质量 / 冲突提示」。
    """
    meta: dict = {
        "main_sectors": [],
        "top_pool": [],
        "program_completed": False,
        "abort_reason": None,
    }
    P = _load_strategy_params()
    W_MAIN = P["w_main"]
    W_DRAGON = P["w_dragon"]
    W_KLINE = P["w_kline"]
    W_LIQ = P["w_liq"]
    W_TECH = P["w_tech"]
    TECH_EVAL_TOPN = P["tech_eval_topn"]
    ENABLE_TECH_MOMENTUM = P["enable_tech"]
    lines = [f"## 【{MODE_NAME}】程序化选股结果\n"]
    lines.append(
        "- 数据来源：东方财富行业板块行情 + 成份股；与申万/同花顺分类存在差异，仅供参考。\n"
    )

    if not trade_days or date not in trade_days:
        lines.append("- 跳过：非交易日或交易日历缺失。\n\n")
        meta["abort_reason"] = "非交易日或交易日历缺失"
        return "".join(lines), meta

    last5 = _last_n_trade_days(trade_days, date, TOP_N_DAYS)
    if len(last5) < TOP_N_DAYS:
        lines.append("- 跳过：历史交易日不足 5 日。\n\n")
        meta["abort_reason"] = "历史交易日不足5日"
        return "".join(lines), meta

    universe = _pick_sector_universe()
    if not universe:
        lines.append("- 无法获取行业列表，跳过选股。\n\n")
        meta["abort_reason"] = "无法获取行业列表"
        return "".join(lines), meta

    _log(fetcher, "次日竞价半路：扫描行业板块行情…")
    _prog(fetcher, 22)
    end_dt = datetime.strptime(date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=45)
    start_s = start_dt.strftime("%Y%m%d")

    sector_daily: dict[str, dict[str, float]] = {}
    sector_vol_sum: dict[str, float] = {}

    for name in universe:
        try:
            h = _sector_hist_for_range(name, start_s, date)
            if h is None:
                continue
            row_map: dict[str, float] = {}
            for d in last5:
                sub = h[h["日期"] == d]
                if not sub.empty:
                    row_map[d] = float(sub["涨跌幅"].iloc[-1])
            if len(row_map) < TOP_N_DAYS:
                continue
            sector_daily[name] = row_map
            last3 = [h[h["日期"] == d] for d in last5[-VOL_DAYS:]]
            vols = []
            for x in last3:
                if not x.empty and "成交额" in x.columns:
                    vols.append(float(pd.to_numeric(x["成交额"].iloc[-1], errors="coerce") or 0))
            if vols:
                sector_vol_sum[name] = sum(vols) / len(vols)
        except Exception:
            continue
        time.sleep(0.05)

    if not sector_daily:
        lines.append("- 行业板块历史行情获取失败，跳过。\n\n")
        meta["abort_reason"] = "行业板块历史行情获取失败"
        return "".join(lines), meta

    _prog(fetcher, 38)
    # 每日涨幅榜 Top10 次数
    top10_count: dict[str, int] = defaultdict(int)
    for d in last5:
        day_pcts = [(name, sector_daily[name][d]) for name in sector_daily if d in sector_daily[name]]
        day_pcts.sort(key=lambda x: x[1], reverse=True)
        for name, _ in day_pcts[:10]:
            top10_count[name] += 1

    # 成交额排名（均值越大越靠前）
    vol_rank = {}
    if sector_vol_sum:
        sorted_v = sorted(sector_vol_sum.items(), key=lambda x: x[1], reverse=True)
        for r, (name, _) in enumerate(sorted_v, start=1):
            vol_rank[name] = r

    candidates: list[tuple[str, int, int]] = []
    for name in sector_daily:
        if top10_count[name] < 3:
            continue
        vr = vol_rank.get(name, 999)
        if vr > 3:
            continue
        if not _sector_has_dragon(name):
            continue
        candidates.append((name, top10_count[name], vr))

    candidates.sort(key=lambda x: x[1], reverse=True)
    main_sectors = [c[0] for c in candidates[:MAX_MAIN_SECTORS]]

    lines.append("### 第一步：主线板块（筛选）\n")
    lines.append(
        f"- 条件：近{TOP_N_DAYS}日涨幅榜前十出现 ≥3 次；近3日日均成交额排名全市场前三；"
        f"板块内存在涨幅>3%的成份股。\n"
    )
    if not main_sectors:
        lines.append("- 未筛出符合主线条件的板块（可能市场平淡或数据不完整）。\n\n")
        meta["abort_reason"] = "未筛出主线板块"
        return "".join(lines), meta

    for n in main_sectors:
        lines.append(
            f"- **{n}**：Top10出现{top10_count[n]}次；"
            f"3日均成交额排名：第{vol_rank.get(n, 0)}。\n"
        )
    lines.append("\n")

    # 当日板块指数日涨幅
    sector_index_pct: dict[str, float] = {}
    for n in main_sectors:
        if n in sector_daily and date in sector_daily[n]:
            sector_index_pct[n] = sector_daily[n][date]

    # 龙头池
    _prog(fetcher, 52)
    _log(fetcher, "次日竞价半路：构建龙头池…")
    zt_map: dict[str, int] = {}
    if df_zt is not None and not df_zt.empty and "code" in df_zt.columns and "lb" in df_zt.columns:
        for _, r in df_zt.iterrows():
            zt_map[_norm_code(r["code"])] = int(pd.to_numeric(r["lb"], errors="coerce") or 0)

    raw_rows: list[dict] = []
    for sec_name in main_sectors:
        try:
            cons = ak.stock_board_industry_cons_em(symbol=sec_name)
        except Exception:
            continue
        if cons is None or cons.empty:
            continue
        for _, r in cons.iterrows():
            code = _norm_code(r.get("代码", ""))
            if not code:
                continue
            name = str(r.get("名称", ""))
            tr = float(pd.to_numeric(r.get("换手率"), errors="coerce") or 0)
            pct = float(pd.to_numeric(r.get("涨跌幅"), errors="coerce") or 0)
            amt = float(pd.to_numeric(r.get("成交额"), errors="coerce") or 0)
            lb = zt_map.get(code, 0)
            si = sector_index_pct.get(sec_name, 0.0)
            raw_rows.append(
                {
                    "sector": sec_name,
                    "code": code,
                    "name": name,
                    "lb": lb,
                    "pct": pct,
                    "turn": tr,
                    "amt": amt,
                    "si": si,
                }
            )

    if not raw_rows:
        lines.append("### 第二步：龙头池\n")
        lines.append("- 主线板块成份股为空。\n\n")
        meta["main_sectors"] = list(main_sectors)
        meta["abort_reason"] = "主线成份股为空"
        return "".join(lines), meta

    spot_map = _merge_spot_by_codes(list({r["code"] for r in raw_rows}), fetcher)

    pool_rows: list[dict] = []
    for r in raw_rows:
        code = r["code"]
        tr, pct, amt, lb = r["turn"], r["pct"], r["amt"], r["lb"]
        si = r["si"]
        mv = spot_map.get(code, {}).get("流通市值") or 0.0

        tag = None
        if lb >= 3 and RENQI_TURNOVER_LOW <= tr <= RENQI_TURNOVER_HIGH:
            tag = "人气龙头"
        elif si >= 2 and pct > si + 3 and amt >= HUO_KOU_TURNOVER_MIN:
            tag = "活口核心"
        elif mv >= MCAP_MIN and 0 < pct < 11 and lb < 3:
            ma_ok, ma20_ok = _stock_ma_above(code, date, trade_days)
            spike = _five_day_positive_spike(code, date, trade_days)
            if ma_ok and ma20_ok and spike:
                tag = "趋势中军"

        if tag:
            pool_rows.append({**r, "tag": tag})

    seen: set[str] = set()
    uniq: list[dict] = []
    for row in pool_rows:
        if row["code"] not in seen:
            seen.add(row["code"])
            uniq.append(row)
    pool_rows = uniq[: MAX_DRAGON_POOL * 4]

    if not pool_rows:
        lines.append("### 第二步：龙头池\n")
        lines.append("- 未筛出符合分类标签的标的（可提高阈值或检查数据）。\n\n")
        meta["main_sectors"] = list(main_sectors)
        meta["abort_reason"] = "未筛出符合分类标签的标的"
        return "".join(lines), meta

    spot_full = spot_map
    by_sec: dict[str, list] = defaultdict(list)
    for r in pool_rows:
        by_sec[r["sector"]].append(r)

    def dragon_score(r: dict) -> int:
        items = by_sec[r["sector"]]
        max_lb = max(x["lb"] for x in items)
        if max_lb <= 0 or r["lb"] != max_lb:
            return 0
        tops = [x for x in items if x["lb"] == max_lb]
        leader = max(tops, key=lambda x: x["turn"])
        return 5 if r["code"] == leader["code"] else 3

    rows_scored: list[dict] = []
    for r in pool_rows:
        sec = r["sector"]
        code = r["code"]
        vr = vol_rank.get(sec, 99)
        s1 = 5 if vr == 1 else (4 if vr == 2 else (3 if vr == 3 else 0))
        s2 = dragon_score(r)
        pc = r["pct"]
        if pc >= 9.5:
            s3 = 5
        elif 5 <= pc <= 10:
            s3 = 4
        elif 3 <= pc < 5:
            s3 = 3
        else:
            s3 = 1
        tr = spot_full.get(code, {}).get("换手率") or r["turn"]
        s4 = 5 if 5 <= tr <= 15 else (4 if 3 <= tr < 20 else 2)
        pre = W_MAIN * s1 + W_DRAGON * s2 + W_KLINE * s3 + W_LIQ * s4
        rows_scored.append(
            {**r, "s1": s1, "s2": s2, "s3": s3, "s4": s4, "pre_partial": pre}
        )

    rows_scored.sort(key=lambda x: x["pre_partial"], reverse=True)

    tech_map: dict[str, dict] = {}
    if ENABLE_TECH_MOMENTUM:
        _prog(fetcher, 62)
        _log(fetcher, "趋势动量：EMA/RSI/ATR 复核前列标的…")
        for row in rows_scored[:TECH_EVAL_TOPN]:
            code = row["code"]
            df = fetch_stock_hist_daily(code, date)
            if df is not None:
                tech_map[code] = analyze_ohlcv(df)
            time.sleep(0.04)

    final_rows: list[tuple[float, dict]] = []
    for row in rows_scored:
        code = row["code"]
        if ENABLE_TECH_MOMENTUM:
            tinfo = tech_map.get(code)
            if tinfo is not None:
                ts = float(tinfo["score"])
                info = tinfo
            else:
                ts = 2.5
                info = {
                    "score": 2.5,
                    "detail": "中性分（未进入技术面精算队列）",
                    "rsi": None,
                }
        else:
            ts = 2.5
            info = {"score": 2.5, "detail": "趋势动量模块已关闭", "rsi": None}
        total = (
            W_MAIN * row["s1"]
            + W_DRAGON * row["s2"]
            + W_KLINE * row["s3"]
            + W_LIQ * row["s4"]
            + W_TECH * ts
        )
        row_out = {k: v for k, v in row.items() if k != "pre_partial"}
        final_rows.append(
            (
                total,
                {
                    **row_out,
                    "tech_score": ts,
                    "tech_info": info,
                    "score": total,
                },
            )
        )

    final_rows.sort(key=lambda x: x[0], reverse=True)
    top = [x[1] for x in final_rows[:MAX_DRAGON_POOL]]

    lines.append("### 第二步：龙头池（合并分类，最多展示 5 只）\n")
    lines.append(
        f"- 评分权重：主线{W_MAIN:.0%} / 龙头地位{W_DRAGON:.0%} / 次日K线预期{W_KLINE:.0%} / "
        f"流动性{W_LIQ:.0%} / **趋势动量{W_TECH:.0%}**（EMA200+EMA20/50+RSI，文档化框架）\n"
    )
    lines.append(
        "- 趋势动量默认参数：EMA200 / EMA50 / EMA20，RSI14（30/70），"
        "ATR14×2 为止损参考倍数（仅供分析，非实盘下单指令）。\n"
    )
    for r in top:
        ti = r.get("tech_info") or {}
        rsi_s = ti.get("rsi")
        rsi_part = f" RSI={rsi_s}" if rsi_s is not None else ""
        lines.append(
            f"- **{r['name']}({r['code']})** [{r['tag']}] 板块:{r['sector']} "
            f"连板{r['lb']} 涨跌幅{r['pct']:.2f}% 换手{r['turn']:.2f}% "
            f"综合={r['score']:.2f}｜技术面{r['tech_score']:.1f}/5{rsi_part} "
            f"（{ti.get('detail', '')}）\n"
        )
    lines.append("\n")

    lines.append("### 第三步：次日竞价半路关注点（程序结论）\n")
    lines.append(
        "- 优先观察上述得分较高标的在 **次日集合竞价** 的放量与高开幅度，"
        "结合主线板块是否延续；若低开弱转强再考虑半路介入。\n"
    )
    lines.append(
        "- 龙虎榜席位、分时五档等需盘中实时数据，本工具未接入。\n\n"
    )

    meta["main_sectors"] = list(main_sectors)
    meta["top_pool"] = [
        {
            "code": r["code"],
            "name": r["name"],
            "score": round(float(r["score"]), 2),
            "tech_score": round(float(r["tech_score"]), 2),
            "sector": r["sector"],
            "tag": r["tag"],
            "s1_main": int(r.get("s1", 0)),
        }
        for r in top
    ]
    meta["program_completed"] = True
    meta["abort_reason"] = None
    return "".join(lines), meta
