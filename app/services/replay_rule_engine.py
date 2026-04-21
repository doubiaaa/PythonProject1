# -*- coding: utf-8 -*-
"""程序化每日复盘规则引擎（主线中军 + 均线多头 + 放量突破 + 板块共振）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import akshare as ak
import pandas as pd

from app.utils.config import ConfigManager


@dataclass
class ReplayRuleConfig:
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20
    consolidate_days: int = 6
    consolidate_amplitude_max: float = 8.0
    distance_to_high_max: float = 2.0
    volume_surge_ratio: float = 1.5
    sector_rise_min: float = 0.5
    index_fall_limit: float = -1.5
    first_breakout_lookback: int = 20
    index_symbol: str = "sh000001"
    report_dir: str = "data/replay_rule_reports"
    stop_loss_ma: int = 10

    @classmethod
    def from_config(cls, cm: Optional[ConfigManager] = None) -> "ReplayRuleConfig":
        cm = cm or ConfigManager()
        return cls(
            ma_short=int(cm.get("rule_ma_short", 5)),
            ma_mid=int(cm.get("rule_ma_mid", 10)),
            ma_long=int(cm.get("rule_ma_long", 20)),
            consolidate_days=int(cm.get("rule_consolidate_days", 6)),
            consolidate_amplitude_max=float(cm.get("rule_consolidate_amplitude_max", 8.0)),
            distance_to_high_max=float(cm.get("rule_distance_to_high_max", 2.0)),
            volume_surge_ratio=float(cm.get("rule_volume_surge_ratio", 1.5)),
            sector_rise_min=float(cm.get("rule_sector_rise_min", 0.5)),
            index_fall_limit=float(cm.get("rule_index_fall_limit", -1.5)),
            first_breakout_lookback=int(cm.get("rule_first_breakout_lookback", 20)),
            index_symbol=str(cm.get("rule_index_symbol", "sh000001")),
            report_dir=str(cm.get("rule_report_dir", "data/replay_rule_reports")),
            stop_loss_ma=int(cm.get("rule_stop_loss_ma", 10)),
        )


def _as_trade_date(dt: str) -> str:
    s = str(dt).strip().replace("-", "")
    return s[:8]


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _load_account_holdings(cm: ConfigManager) -> list[dict[str, Any]]:
    p = cm.path("simulated_account_file")
    try:
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        hs = payload.get("holdings") or []
        return [h for h in hs if isinstance(h, dict)]
    except Exception:
        return []


def _fetch_index_frame(data_fetcher: Any, cfg: ReplayRuleConfig) -> pd.DataFrame:
    df = data_fetcher.fetch_with_retry(ak.stock_zh_index_daily_em, symbol=cfg.index_symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    date_col = "date" if "date" in out.columns else "日期"
    close_col = "close" if "close" in out.columns else "收盘"
    out["trade_date"] = pd.to_datetime(out[date_col], errors="coerce").dt.strftime("%Y%m%d")
    out["close_v"] = pd.to_numeric(out[close_col], errors="coerce")
    out = out.dropna(subset=["trade_date", "close_v"])
    out["ma20"] = out["close_v"].rolling(20).mean()
    out["pct"] = out["close_v"].pct_change() * 100.0
    return out


def _fetch_stock_frame(data_fetcher: Any, code: str, end_date: str, lookback_days: int) -> pd.DataFrame:
    td = data_fetcher.get_trade_cal() or []
    if not td:
        return pd.DataFrame()
    if end_date not in td:
        return pd.DataFrame()
    end_idx = td.index(end_date)
    start_idx = max(0, end_idx - lookback_days)
    start_date = td[start_idx]
    df = data_fetcher.fetch_with_retry(
        ak.stock_zh_a_hist,
        symbol=str(code),
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["日期"], errors="coerce").dt.strftime("%Y%m%d")
    out["open_v"] = pd.to_numeric(out["开盘"], errors="coerce")
    out["high_v"] = pd.to_numeric(out["最高"], errors="coerce")
    out["low_v"] = pd.to_numeric(out["最低"], errors="coerce")
    out["close_v"] = pd.to_numeric(out["收盘"], errors="coerce")
    out["vol_v"] = pd.to_numeric(out["成交量"], errors="coerce")
    out = out.dropna(subset=["trade_date", "open_v", "high_v", "low_v", "close_v", "vol_v"])
    return out


def _is_first_breakout(df: pd.DataFrame, cfg: ReplayRuleConfig) -> bool:
    if len(df) < cfg.first_breakout_lookback + cfg.consolidate_days + 1:
        return True
    window = df.tail(cfg.first_breakout_lookback + cfg.consolidate_days + 1).reset_index(drop=True)
    prior = window.iloc[:-1]
    for i in range(cfg.consolidate_days, len(prior)):
        base = prior.iloc[i - cfg.consolidate_days : i]
        base_high = float(base["high_v"].max())
        c = float(prior.iloc[i]["close_v"])
        if c > base_high:
            return False
    return True


def _analyze_stock(df: pd.DataFrame, cfg: ReplayRuleConfig) -> dict[str, Any]:
    if df.empty or len(df) < max(cfg.ma_long + 2, cfg.consolidate_days + 2):
        return {"valid": False}
    x = df.copy()
    x["ma5"] = x["close_v"].rolling(cfg.ma_short).mean()
    x["ma10"] = x["close_v"].rolling(cfg.ma_mid).mean()
    x["ma20"] = x["close_v"].rolling(cfg.ma_long).mean()
    x["vol_ma5"] = x["vol_v"].rolling(5).mean()
    last = x.iloc[-1]
    base = x.iloc[-(cfg.consolidate_days + 1) : -1]
    platform_high = float(base["high_v"].max())
    platform_low = float(base["low_v"].min())
    amp = (platform_high - platform_low) / max(platform_low, 1e-8) * 100.0
    distance = (platform_high - float(last["close_v"])) / max(float(last["close_v"]), 1e-8) * 100.0
    ma_bull = bool(
        float(last["ma5"]) > float(last["ma10"]) > float(last["ma20"])
        and float(last["close_v"]) > float(last["ma5"])
    )
    near_breakout = distance <= cfg.distance_to_high_max
    consolidating = amp < cfg.consolidate_amplitude_max
    breakout_today = float(last["close_v"]) > platform_high
    vol_surge = float(last["vol_v"]) > float(last["vol_ma5"]) * cfg.volume_surge_ratio
    first_breakout = _is_first_breakout(x, cfg)
    return {
        "valid": True,
        "ma5": round(float(last["ma5"]), 4),
        "ma10": round(float(last["ma10"]), 4),
        "ma20": round(float(last["ma20"]), 4),
        "close": round(float(last["close_v"]), 4),
        "platform_high": round(platform_high, 4),
        "platform_low": round(platform_low, 4),
        "amplitude": round(amp, 2),
        "distance_to_high": round(distance, 2),
        "ma_bull": ma_bull,
        "is_consolidating": consolidating,
        "near_breakout": near_breakout,
        "breakout_today": breakout_today,
        "volume_surge": vol_surge,
        "first_breakout": first_breakout,
    }


def evaluate_daily_replay_rules(date: str, data_fetcher: Any) -> dict[str, Any]:
    cfg = ReplayRuleConfig.from_config()
    cm = ConfigManager()
    ds = _as_trade_date(date)

    market_ok = False
    market_reason = "index_data_missing"
    idx_df = _fetch_index_frame(data_fetcher, cfg)
    if not idx_df.empty and ds in set(idx_df["trade_date"].tolist()):
        row = idx_df[idx_df["trade_date"] == ds].iloc[-1]
        c, ma20, pct = _to_float(row["close_v"]), _to_float(row["ma20"]), _to_float(row["pct"])
        market_ok = c > ma20 and pct > cfg.index_fall_limit
        market_reason = f"index_close={round(c,2)},ma20={round(ma20,2)},pct={round(pct,2)}%"

    ah_meta = getattr(data_fetcher, "_last_auction_meta", None) or {}
    main_sectors = [str(s) for s in (ah_meta.get("main_sectors") or []) if str(s).strip()]
    top_pool = [x for x in (ah_meta.get("top_pool") or []) if isinstance(x, dict)]

    sector_df = data_fetcher.get_sector_rank(ds)
    strong_sectors: list[str] = []
    sector_pct: dict[str, float] = {}
    if sector_df is not None and not sector_df.empty:
        for _, r in sector_df.iterrows():
            s = str(r.get("sector") or "").strip()
            pct = _to_float(r.get("pct"), 0.0)
            if not s:
                continue
            sector_pct[s] = pct
            if pct > cfg.sector_rise_min and (not main_sectors or s in main_sectors):
                strong_sectors.append(s)
    strong_sectors = list(dict.fromkeys(strong_sectors))

    watch_list: list[dict[str, Any]] = []
    buy_signals_today: list[dict[str, Any]] = []
    alerts_for_tomorrow: list[dict[str, Any]] = []
    position_actions: list[dict[str, Any]] = []

    for s in top_pool:
        code = str(s.get("code") or "").strip()
        if not code:
            continue
        hist = _fetch_stock_frame(data_fetcher, code, ds, lookback_days=90)
        analyzed = _analyze_stock(hist, cfg)
        if not analyzed.get("valid"):
            continue
        sector = str(s.get("sector") or "")
        sec_ok = _to_float(sector_pct.get(sector), 0.0) > cfg.sector_rise_min
        potential = bool(analyzed["ma_bull"] and analyzed["is_consolidating"] and analyzed["near_breakout"])
        if potential:
            watch_list.append(
                {
                    "code": code,
                    "name": str(s.get("name") or ""),
                    "sector": sector,
                    "platform_high": analyzed["platform_high"],
                    "current": analyzed["close"],
                    "distance": analyzed["distance_to_high"],
                    "consolidate_amplitude": analyzed["amplitude"],
                }
            )
        buy_today = bool(
            analyzed["breakout_today"]
            and analyzed["volume_surge"]
            and sec_ok
            and analyzed["first_breakout"]
        )
        if buy_today:
            vol_ratio = 0.0
            if not hist.empty and len(hist) >= 6:
                h = hist.copy()
                h["vol_ma5"] = h["vol_v"].rolling(5).mean()
                last = h.iloc[-1]
                vol_ratio = float(last["vol_v"]) / max(float(last["vol_ma5"]), 1e-8)
            buy_signals_today.append(
                {
                    "code": code,
                    "name": str(s.get("name") or ""),
                    "breakout_price": analyzed["platform_high"],
                    "volume_ratio": round(vol_ratio, 2),
                    "sector": sector,
                }
            )
        if potential and not analyzed["breakout_today"]:
            alerts_for_tomorrow.append(
                {
                    "code": code,
                    "name": str(s.get("name") or ""),
                    "trigger_price": round(analyzed["platform_high"] * 1.01, 4),
                    "sector": sector,
                    "require_sector_rise": cfg.sector_rise_min,
                    "require_volume_surge": cfg.volume_surge_ratio,
                    "stop_loss": analyzed["ma10"] if cfg.stop_loss_ma == 10 else analyzed["ma20"],
                }
            )

    for h in _load_account_holdings(cm):
        code = str(h.get("code") or "").strip()
        if not code:
            continue
        hist = _fetch_stock_frame(data_fetcher, code, ds, lookback_days=60)
        analyzed = _analyze_stock(hist, cfg)
        if not analyzed.get("valid"):
            continue
        close = analyzed["close"]
        breakout_low = _to_float(h.get("breakout_bar_low"), -1.0)
        below_ma5 = close < analyzed["ma5"]
        below_ma10 = close < analyzed["ma10"]
        below_breakout_low = breakout_low > 0 and close < breakout_low
        action = "持有"
        reason = "未破5日线"
        if below_ma10:
            action, reason = "清仓", "收盘跌破10日线"
        elif below_ma5 or below_breakout_low:
            action, reason = "减仓或清仓", "跌破5日线或突破阳线低点"
        position_actions.append(
            {
                "code": code,
                "name": str(h.get("name") or ""),
                "action": action,
                "reason": reason,
            }
        )

    return {
        "date": ds,
        "market_ok": market_ok,
        "market_reason": market_reason,
        "strong_sectors": strong_sectors,
        "watch_list": watch_list,
        "buy_signals_today": buy_signals_today,
        "alerts_for_tomorrow": alerts_for_tomorrow,
        "position_actions": position_actions,
        "config": cfg.__dict__,
    }


def save_replay_rule_report(report: dict[str, Any], cm: Optional[ConfigManager] = None) -> Optional[str]:
    cm = cm or ConfigManager()
    cfg = ReplayRuleConfig.from_config(cm)
    base = cm.path("data_dir")
    out_dir = f"{base}/{cfg.report_dir.split('/', 1)[-1]}"
    try:
        import os

        os.makedirs(out_dir, exist_ok=True)
        ds = str(report.get("date") or "")
        fp = os.path.join(out_dir, f"{ds}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return fp
    except Exception:
        return None


def render_replay_rule_markdown(report: dict[str, Any]) -> str:
    alerts = report.get("alerts_for_tomorrow") or []
    market_ok = bool(report.get("market_ok"))
    strong_sectors = {
        str(x) for x in (report.get("strong_sectors") or []) if str(x).strip()
    }
    executable_count = 0
    blocked_count = 0
    blocked_market_count = 0
    blocked_sector_count = 0
    for a in alerts:
        sector = str(a.get("sector") or "")
        sector_ok = (not strong_sectors) or (sector in strong_sectors)
        executable = market_ok and sector_ok
        if executable:
            executable_count += 1
        else:
            blocked_count += 1
            if not market_ok:
                blocked_market_count += 1
            else:
                blocked_sector_count += 1

    lines = [
        "\n## 【程序化复盘条件引擎】主线中军趋势规则\n\n",
        f"- 交易日：**{report.get('date','')}**\n",
        f"- 大盘环境：**{'可交易' if report.get('market_ok') else '观望/回避'}**（{report.get('market_reason','')})\n",
        f"- 强势主线板块：{'、'.join(report.get('strong_sectors') or []) or '无'}\n\n",
        "- 明日条件单汇总："
        f"可执行 **{executable_count}** 条 / 不可执行 **{blocked_count}** 条"
        f"（大盘阻塞 **{blocked_market_count}** 条，板块阻塞 **{blocked_sector_count}** 条）\n\n",
        "### 备选中军（均线多头+横盘临近突破）\n\n",
    ]
    wl = report.get("watch_list") or []
    if not wl:
        lines.append("- 无符合条件标的。\n")
    else:
        for r in wl[:12]:
            lines.append(
                f"- {r.get('name','')}({r.get('code','')}) / {r.get('sector','')}："
                f"平台顶 {r.get('platform_high')}，现价 {r.get('current')}，"
                f"距平台顶 {r.get('distance')}%\n"
            )
    lines.append("\n### 今日突破信号\n\n")
    bs = report.get("buy_signals_today") or []
    if not bs:
        lines.append("- 今日无“首次放量突破平台”信号。\n")
    else:
        for r in bs[:12]:
            lines.append(
                f"- {r.get('name','')}({r.get('code','')})：突破价 {r.get('breakout_price')}，"
                f"量比 {r.get('volume_ratio')}，板块 {r.get('sector','')}\n"
            )
    lines.append("\n### 明日预警条件单\n\n")
    if not alerts:
        lines.append("- 无预警标的。\n")
    else:
        for r in alerts[:12]:
            lines.append(
                f"- {r.get('name','')}({r.get('code','')})：触发价>{r.get('trigger_price')}，"
                f"板块涨幅>{r.get('require_sector_rise')}%，放量>{r.get('require_volume_surge')}x，"
                f"止损 {r.get('stop_loss')}\n"
            )
    pa = report.get("position_actions") or []
    lines.append("\n### 持仓应对\n\n")
    if not pa:
        lines.append("- 当前无持仓应对动作。\n")
    else:
        for r in pa[:20]:
            lines.append(f"- {r.get('name','')}({r.get('code','')})：{r.get('action')}（{r.get('reason')}）\n")
    return "".join(lines)

