# -*- coding: utf-8 -*-
"""
实盘交易展示（程序记账）：信号日龙头池 → 下一交易日开盘价买入；
卖出由「信号日复盘正文」中的预案/核心股关键词，叠加止损、止盈、最长持仓判定，
在决策日收盘后登记，于下一交易日开盘价卖出。持久化见 paths.simulated_account_file。
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Optional

from app.utils.config_paths import data_dir
from app.utils.logger import get_logger

_log = get_logger(__name__)
_lock = threading.Lock()


def _state_path() -> str:
    try:
        from app.utils.config_paths import simulated_account_file

        return simulated_account_file()
    except Exception:
        return os.path.join(data_dir(), "simulated_account.json")


def _norm6(code: object) -> str:
    return "".join(c for c in str(code or "") if c.isdigit()).zfill(6)[:6]


def _next_trade_day(trade_days: list[str], ds: str) -> Optional[str]:
    ds = str(ds)[:8]
    if ds not in trade_days:
        return None
    i = trade_days.index(ds)
    if i + 1 < len(trade_days):
        return trade_days[i + 1]
    return None


def _trade_day_index(trade_days: list[str], ds: str) -> int:
    ds = str(ds)[:8]
    if ds not in trade_days:
        return -1
    return trade_days.index(ds)


def _load_config() -> tuple[bool, float, int, float, float, float, int]:
    try:
        from app.utils.config import ConfigManager

        cm = ConfigManager()
        en = bool(cm.get("enable_simulated_account", True))
        cash0 = float(cm.get("sim_account_initial_cash", 50_000) or 50_000)
        mx = int(cm.get("sim_account_max_stocks", 5) or 5)
        mx = max(1, min(20, mx))
        res = float(cm.get("sim_account_cash_reserve_pct", 0.02) or 0.02)
        res = max(0.0, min(0.5, res))
        sl = float(cm.get("sim_account_stop_loss_pct", 0.05) or 0.05)
        tp = float(cm.get("sim_account_take_profit_pct", 0.08) or 0.08)
        mxd = int(cm.get("sim_account_max_hold_days", 15) or 15)
        mxd = max(3, min(60, mxd))
        return en, cash0, mx, res, sl, tp, mxd
    except Exception:
        return True, 50_000.0, 5, 0.02, 0.05, 0.08, 15


def load_state() -> dict[str, Any]:
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data: dict[str, Any]) -> None:
    path = _state_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _ensure_state_shape(st: dict[str, Any], initial_cash: float) -> dict[str, Any]:
    if not st:
        st = {
            "version": 2,
            "initial_cash": initial_cash,
            "cash": initial_cash,
            "positions": [],
            "scheduled_buys": [],
            "pending_sells": [],
            "signal_reports": {},
            "trades": [],
            "daily_snapshots": [],
        }
    st.setdefault("version", 2)
    st.setdefault("initial_cash", initial_cash)
    st.setdefault("cash", float(st.get("initial_cash", initial_cash)))
    st.setdefault("positions", [])
    st.setdefault("scheduled_buys", [])
    st.setdefault("pending_sells", [])
    st.setdefault("signal_reports", {})
    st.setdefault("trades", [])
    st.setdefault("daily_snapshots", [])
    if not isinstance(st["pending_sells"], list):
        st["pending_sells"] = []
    if not isinstance(st["signal_reports"], dict):
        st["signal_reports"] = {}
    if int(st.get("version") or 1) < 2:
        for p in st.get("positions") or []:
            if isinstance(p, dict):
                p.pop("sell_date", None)
        st["version"] = 2
    return st


def _fetch_daily_ohlc(code: str, ds: str) -> dict[str, Optional[float]]:
    c = _norm6(code)
    out: dict[str, Optional[float]] = {
        "open": None,
        "high": None,
        "low": None,
        "close": None,
    }
    if len(c) != 6:
        return out
    try:
        import akshare as ak

        df = ak.stock_zh_a_hist(
            symbol=c,
            period="daily",
            start_date=ds,
            end_date=ds,
            adjust="",
        )
        if df is None or df.empty:
            return out
        row = df.iloc[-1]
        for k, col in (
            ("open", "开盘"),
            ("high", "最高"),
            ("low", "最低"),
            ("close", "收盘"),
        ):
            cc = next((x for x in (col, k.capitalize()) if x in row.index), None)
            if cc:
                try:
                    out[k] = float(row[cc])
                except (TypeError, ValueError):
                    pass
        return out
    except Exception as ex:
        _log.debug("实盘展示取价失败 %s %s: %s", c, ds, ex)
        return out


def _extract_plan_window(text: str) -> str:
    """合并明日预案、核心股等片段，供关键词检索。"""
    if not text or not str(text).strip():
        return ""
    t = str(text)
    chunks: list[str] = []
    for pat in (
        r"###\s*七[、.．]?\s*明日预案[\s\S]*?(?=###\s*八|$)",
        r"###\s*五[、.．]?\s*核心股[\s\S]*?(?=###\s*六|$)",
        r"明日预案[\s\S]{0,8000}",
    ):
        m = re.search(pat, t, re.I | re.M)
        if m:
            chunks.append(m.group(0))
    return "\n".join(chunks) if chunks else t[-12000:]


def _plan_suggests_exit_for_stock(plan_text: str, code: str, name: str) -> bool:
    """信号日复盘中是否对该标的给出偏空/离场类表述。"""
    if not plan_text.strip():
        return False
    code = _norm6(code)
    nm = str(name or "").strip()
    sell_kw = (
        "卖出",
        "止盈",
        "减仓",
        "离场",
        "止损",
        "兑现",
        "清仓",
        "减持",
        "离场观望",
        "回避",
        "不接",
    )
    hold_kw = ("持有", "观望", "不加仓", "锁仓", "躺赢")
    lines = plan_text.splitlines()
    for line in lines:
        if code not in line and (not nm or nm not in line):
            continue
        if any(k in line for k in hold_kw) and not any(k in line for k in sell_kw):
            continue
        if any(k in line for k in sell_kw):
            return True
    return False


def _append_trade(
    st: dict[str, Any],
    *,
    trade_date: str,
    side: str,
    code: str,
    name: str,
    qty: int,
    price: float,
    note: str = "",
) -> None:
    amt = round(qty * price, 2)
    st["trades"].append(
        {
            "date": trade_date[:8],
            "side": side,
            "code": _norm6(code),
            "name": str(name or ""),
            "qty": int(qty),
            "price": round(float(price), 4),
            "amount": amt,
            "note": note[:220],
        }
    )


def _equity_mark(st: dict[str, Any]) -> float:
    cash = float(st.get("cash", 0))
    pos_val = 0.0
    for p in st.get("positions") or []:
        if not isinstance(p, dict):
            continue
        q = int(p.get("qty") or 0)
        bp = float(p.get("buy_price") or 0)
        pos_val += q * bp
    return round(cash + pos_val, 2)


def _equity_market_at_close(st: dict[str, Any], date_ds: str) -> float:
    """现金 + 持仓按 date_ds 日线收盘价估值（与配图一致）。"""
    ds = str(date_ds)[:8]
    if len(ds) != 8:
        return round(float(st.get("cash", 0)), 2)
    cash = float(st.get("cash", 0))
    tot = cash
    for p in st.get("positions") or []:
        if not isinstance(p, dict):
            continue
        code = _norm6(p.get("code"))
        qty = int(p.get("qty") or 0)
        bp = float(p.get("buy_price") or 0)
        if len(code) != 6 or qty <= 0:
            continue
        bar = _fetch_daily_ohlc(code, ds)
        cl = bar.get("close")
        if cl is None or float(cl) <= 0:
            cl = bp if bp > 0 else 0.0
        tot += qty * float(cl)
    return round(tot, 2)


def _prev_trading_snapshot_before(
    snapshots: list[Any], date_ds: str
) -> Optional[dict[str, Any]]:
    ds = str(date_ds)[:8]
    best: Optional[dict[str, Any]] = None
    best_d = ""
    for s in snapshots or []:
        if not isinstance(s, dict):
            continue
        d = str(s.get("date") or "")[:8]
        if len(d) != 8 or d >= ds:
            continue
        if not best or d > best_d:
            best, best_d = s, d
    return best


def _patch_snapshot_equity_mkt_close(st: dict[str, Any], date_ds: str, mkt: float) -> None:
    ds = str(date_ds)[:8]
    snaps = st.get("daily_snapshots")
    if not isinstance(snaps, list):
        return
    for s in reversed(snaps):
        if isinstance(s, dict) and str(s.get("date") or "")[:8] == ds:
            s["equity_mkt_close"] = round(float(mkt), 2)
            return


def build_trade_display_summary(trade_date_ds: str) -> dict[str, Any]:
    """
    市值口径：今日收益（相对上一快照日收盘市值）、实盘至今收益/收益率。
    写回当日 `daily_snapshots[].equity_mkt_close` 供下一交易日计算。
    """
    out: dict[str, Any] = {}
    enabled, initial_cash, *_ = _load_config()
    if not enabled:
        return out
    ds = str(trade_date_ds)[:8]
    if len(ds) != 8:
        return out
    with _lock:
        st = _ensure_state_shape(load_state(), initial_cash)
        today_mkt = _equity_market_at_close(st, ds)
        ic = float(st.get("initial_cash", initial_cash))
        cum_pnl = round(today_mkt - ic, 2)
        cum_pct = round((today_mkt / ic - 1.0) * 100.0, 2) if ic > 0 else 0.0
        prev = _prev_trading_snapshot_before(st.get("daily_snapshots") or [], ds)
        if prev:
            prev_m = prev.get("equity_mkt_close")
            if prev_m is None:
                prev_m = prev.get("equity")
            try:
                prev_mf = float(prev_m)
            except (TypeError, ValueError):
                prev_mf = ic
            today_gain = round(today_mkt - prev_mf, 2)
        else:
            today_gain = round(today_mkt - ic, 2)
        _patch_snapshot_equity_mkt_close(st, ds, today_mkt)
        save_state(st)
        out = {
            "today_mkt": today_mkt,
            "today_gain": today_gain,
            "cum_pnl": cum_pnl,
            "cum_pct": cum_pct,
        }
    return out


def _pending_sell_exists(st: dict[str, Any], code: str) -> bool:
    c = _norm6(code)
    for x in st.get("pending_sells") or []:
        if isinstance(x, dict) and _norm6(x.get("code")) == c:
            return True
    return False


def save_signal_report(signal_date: str, report_text: str) -> None:
    """写入当日下午复盘正文，供后续按信号日检索预案。"""
    cfg = _load_config()
    enabled = cfg[0]
    initial_cash = cfg[1]
    if not enabled:
        return
    ds = str(signal_date)[:8]
    if len(ds) != 8:
        return
    with _lock:
        st = _ensure_state_shape(load_state(), initial_cash)
        sr = st["signal_reports"]
        if isinstance(sr, dict):
            sr[ds] = str(report_text or "")[-120000:]
        save_state(st)


def evaluate_exits_after_close(
    trade_date: str,
    trade_days: list[str],
) -> dict[str, Any]:
    """
    收盘后：用当日 K 线 + 信号日复盘正文，决定是否登记「下一交易日开盘卖出」。
    不在此处成交；成交在 process_session_opens。
    """
    enabled, initial_cash, _, _, sl_pct, tp_pct, max_hold = _load_config()
    out: dict[str, Any] = {"scheduled": [], "skipped": []}
    if not enabled or not trade_days:
        return out
    ds = str(trade_date)[:8]
    if len(ds) != 8 or ds not in trade_days:
        return out
    nx = _next_trade_day(trade_days, ds)
    if not nx:
        return out

    with _lock:
        st = _ensure_state_shape(load_state(), initial_cash)
        for pos in list(st.get("positions") or []):
            if not isinstance(pos, dict):
                continue
            code = _norm6(pos.get("code"))
            name = str(pos.get("name") or "")
            buy_d = str(pos.get("buy_date") or "")[:8]
            sig_d = str(pos.get("signal_date") or "")[:8]
            qty = int(pos.get("qty") or 0)
            bp = float(pos.get("buy_price") or 0)
            if len(code) != 6 or qty <= 0 or bp <= 0:
                continue
            if _pending_sell_exists(st, code):
                out["skipped"].append({"code": code, "reason": "已在卖出队列"})
                continue

            bar = _fetch_daily_ohlc(code, ds)
            lo, hi = bar.get("low"), bar.get("high")
            reason: Optional[str] = None

            ib, it_ = _trade_day_index(trade_days, buy_d), _trade_day_index(trade_days, ds)
            if lo is not None and lo <= bp * (1.0 - sl_pct):
                reason = f"止损（约 -{sl_pct:.0%}，当日最低 {lo:.4f}）"
            elif hi is not None and hi >= bp * (1.0 + tp_pct):
                reason = f"止盈（约 +{tp_pct:.0%}，当日最高 {hi:.4f}）"
            elif ib >= 0 and it_ >= 0 and (it_ - ib + 1) >= max_hold:
                reason = f"最长持仓（≥{max_hold} 个交易日）"
            elif buy_d and ds > buy_d:
                plan_txt = ""
                if isinstance(st.get("signal_reports"), dict):
                    plan_txt = str(st["signal_reports"].get(sig_d) or "")
                plan_win = _extract_plan_window(plan_txt)
                if _plan_suggests_exit_for_stock(plan_win, code, name):
                    reason = "复盘预案/核心股关键词（信号日正文）"

            if not reason:
                continue

            st["pending_sells"].append(
                {
                    "code": code,
                    "name": name,
                    "qty": qty,
                    "sell_execute_date": nx,
                    "reason": reason,
                    "decided_on": ds,
                    "signal_date": sig_d,
                    "buy_date": buy_d,
                }
            )
            out["scheduled"].append({"code": code, "reason": reason, "execute": nx})

        save_state(st)
    return out


def process_session_opens(
    fetcher: Any,
    trade_date: str,
    trade_days: list[str],
) -> dict[str, Any]:
    """
    复盘任务运行时序上代表「当日收盘后」：对 **trade_date 当日开盘价** 执行
    已登记的卖出、买入（与真实「下一交易日开盘」撮合对齐）。
    """
    enabled, initial_cash, max_stocks, reserve_pct, *_ = _load_config()
    out: dict[str, Any] = {
        "enabled": enabled,
        "trade_date": str(trade_date)[:8],
        "sells": [],
        "buys": [],
        "errors": [],
    }
    if not enabled:
        return out
    ds = str(trade_date)[:8]
    if len(ds) != 8 or not trade_days or ds not in trade_days:
        return out

    with _lock:
        st = _ensure_state_shape(load_state(), initial_cash)
        if float(st.get("cash", 0)) <= 0 and not st.get("positions"):
            st["cash"] = float(st.get("initial_cash", initial_cash))

        # --- 卖：pending_sells 中本日开盘执行的指令 ---
        kept_pending: list[dict[str, Any]] = []
        for pend in list(st.get("pending_sells") or []):
            if not isinstance(pend, dict):
                continue
            if str(pend.get("sell_execute_date") or "")[:8] != ds:
                kept_pending.append(pend)
                continue
            code = _norm6(pend.get("code"))
            qty = int(pend.get("qty") or 0)
            name = str(pend.get("name") or "")
            if len(code) != 6 or qty <= 0:
                kept_pending.append(pend)
                continue
            match = None
            for p in st.get("positions") or []:
                if isinstance(p, dict) and _norm6(p.get("code")) == code:
                    match = p
                    break
            if not match:
                kept_pending.append(pend)
                continue
            qty = min(qty, int(match.get("qty") or 0))
            if qty <= 0:
                kept_pending.append(pend)
                continue
            ohlc = _fetch_daily_ohlc(code, ds)
            op = ohlc.get("open")
            if op is None or op <= 0:
                out["errors"].append(f"{code} 卖出开盘价缺失")
                kept_pending.append(pend)
                continue
            proceeds = round(qty * op, 2)
            st["cash"] = round(float(st["cash"]) + proceeds, 2)
            _append_trade(
                st,
                trade_date=ds,
                side="sell",
                code=code,
                name=name or str(match.get("name") or ""),
                qty=qty,
                price=op,
                note=str(pend.get("reason") or "卖出")[:200],
            )
            new_pos: list[dict[str, Any]] = []
            for p in st.get("positions") or []:
                if not isinstance(p, dict):
                    continue
                if _norm6(p.get("code")) != code:
                    new_pos.append(p)
                    continue
                rem = int(p.get("qty") or 0) - qty
                if rem > 0:
                    p["qty"] = rem
                    new_pos.append(p)
            st["positions"] = new_pos
            out["sells"].append(
                {"code": code, "qty": qty, "price": op, "proceeds": proceeds}
            )

        st["pending_sells"] = kept_pending

        # --- 买 ---
        sched = [x for x in (st.get("scheduled_buys") or []) if isinstance(x, dict)]
        remaining_sched: list[dict[str, Any]] = []
        for s in sched:
            bd = str(s.get("buy_date") or "")[:8]
            if bd != ds:
                remaining_sched.append(s)
                continue
            picks = s.get("picks") or []
            if not isinstance(picks, list) or not picks:
                continue
            picks = picks[:max_stocks]
            cash = float(st["cash"])
            budget = cash * (1.0 - reserve_pct)
            per = budget / max(len(picks), 1)
            for pk in picks:
                if not isinstance(pk, dict):
                    continue
                code = _norm6(pk.get("code"))
                name = str(pk.get("name") or "")
                if len(code) != 6:
                    continue
                ohlc = _fetch_daily_ohlc(code, ds)
                o = ohlc.get("open")
                if o is None or o <= 0:
                    out["errors"].append(f"{code} 买入开盘价缺失")
                    continue
                lot = 100
                max_qty = int(per / o / lot) * lot
                if max_qty < lot:
                    continue
                cost = round(max_qty * o, 2)
                if cost > float(st["cash"]) * (1.0 - reserve_pct):
                    continue
                st["cash"] = round(float(st["cash"]) - cost, 2)
                st["positions"].append(
                    {
                        "code": code,
                        "name": name,
                        "qty": max_qty,
                        "buy_date": ds,
                        "buy_price": round(o, 4),
                        "signal_date": str(s.get("signal_date") or "")[:8],
                        "score": float(pk.get("score") or 0),
                    }
                )
                _append_trade(
                    st,
                    trade_date=ds,
                    side="buy",
                    code=code,
                    name=name,
                    qty=max_qty,
                    price=o,
                    note=f"信号日 {s.get('signal_date')} 龙头池·开盘",
                )
                out["buys"].append(
                    {"code": code, "name": name, "qty": max_qty, "price": o, "cost": cost}
                )

        st["scheduled_buys"] = remaining_sched

        snap = {
            "date": ds,
            "cash": round(float(st["cash"]), 2),
            "equity": _equity_mark(st),
            "equity_mkt_close": _equity_market_at_close(st, ds),
            "positions_n": len(st.get("positions") or []),
        }
        st["daily_snapshots"].append(snap)
        st["daily_snapshots"] = st["daily_snapshots"][-400:]

        save_state(st)
        out["snapshot"] = snap
        out["state"] = st
        return out


def schedule_next_buys(
    signal_date: str,
    trade_days: list[str],
    top_pool: list[dict[str, Any]],
) -> None:
    """登记：signal_date 龙头池 → 仅下一交易日开盘买入（卖出另由 evaluate 决定）。"""
    enabled, initial_cash, max_stocks, *_ = _load_config()
    if not enabled or not top_pool:
        return
    ds = str(signal_date)[:8]
    if len(ds) != 8 or ds not in trade_days:
        return
    bd = _next_trade_day(trade_days, ds)
    if not bd:
        return
    picks: list[dict[str, Any]] = []
    for p in top_pool[:max_stocks]:
        if not isinstance(p, dict):
            continue
        c = _norm6(p.get("code"))
        if len(c) != 6:
            continue
        picks.append(
            {
                "code": c,
                "name": str(p.get("name") or ""),
                "score": float(p.get("score") or 0),
            }
        )
    if not picks:
        return

    with _lock:
        st = _ensure_state_shape(load_state(), initial_cash)
        st["scheduled_buys"] = [
            x
            for x in (st.get("scheduled_buys") or [])
            if isinstance(x, dict) and str(x.get("buy_date") or "")[:8] != bd
        ]
        st["scheduled_buys"].append(
            {
                "signal_date": ds,
                "buy_date": bd,
                "picks": picks,
            }
        )
        save_state(st)


def build_simulated_account_markdown(
    trade_date: Optional[str] = None,
    *,
    image_rel: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
) -> str:
    """报告顶部「实盘交易展示」区块。若 `image_rel` 已生成资金页截图，则以图为主要展示并省略重复表格。"""
    enabled, initial_cash, *_ = _load_config()
    if not enabled:
        return ""
    st = _ensure_state_shape(load_state(), initial_cash)
    ds = str(trade_date)[:8] if trade_date else ""
    lines = [
        "\n---\n\n## 【实盘交易展示】\n\n",
    ]
    if image_rel and str(image_rel).strip():
        rel = str(image_rel).strip().replace(os.sep, "/")
        lines.append(f"![【实盘交易展示】]({rel})\n\n")
    if summary and "today_mkt" in summary:
        tg = float(summary.get("today_gain", 0))
        cp = float(summary.get("cum_pnl", 0))
        cr = float(summary.get("cum_pct", 0))
        lines.append(f"**今日收益：** {tg:+,.2f} 元\n\n")
        lines.append(f"**实盘至今收益：** {cp:+,.2f} 元\n\n")
        lines.append(f"**实盘至今收益率：** {cr:+.2f}%\n\n")
    lines.append(
        "> **说明**：买入为信号日龙头池、**下一交易日开盘价**；卖出在复盘日收盘后依据"
        "「信号日复盘」中预案/核心股关键词，并叠加止损/止盈/最长持仓，登记在**下一交易日开盘价**卖出。"
    )
    if image_rel and str(image_rel).strip():
        lines.append(
            "上方截图为**移动端资金页风格**，其中**现价/市值/浮动盈亏**按**当日日线收盘价**（akshare）回显；"
            "与次日开盘撮合成交价可能不一致。展示为程序记账，不构成投资建议。\n\n"
        )
    else:
        lines.append("展示为程序记账，不构成投资建议。\n\n")

    cash = float(st.get("cash", 0))
    ic = float(st.get("initial_cash", initial_cash))
    eq = _equity_mark(st)
    ret = round((eq / ic - 1.0) * 100, 2) if ic > 0 else 0.0
    lines.append(f"- **现金**：{cash:,.2f} 元\n")
    lines.append(f"- **持仓市值（按成本计）**：{eq - cash:,.2f} 元\n")
    lines.append(f"- **总资产（现金+持仓成本）**：{eq:,.2f} 元\n")
    lines.append(f"- **相对初始本金收益率**：**{ret}%**（本金 {ic:,.0f} 元）\n\n")

    compact = bool(image_rel and str(image_rel).strip())
    if not compact:
        pos = st.get("positions") or []
        if pos:
            lines.append("### 当前持仓\n\n")
            lines.append("| 代码 | 名称 | 数量 | 买入日 | 买入价 | 信号日 |\n")
            lines.append("| --- | --- | --- | --- | --- | --- |\n")
            for p in pos:
                if not isinstance(p, dict):
                    continue
                lines.append(
                    f"| `{p.get('code')}` | {p.get('name')} | {p.get('qty')} | "
                    f"{p.get('buy_date')} | {p.get('buy_price')} | {p.get('signal_date')} |\n"
                )
            lines.append("\n")
        else:
            lines.append("### 当前持仓\n\n- 空仓\n\n")

        ps = st.get("pending_sells") or []
        if ps:
            lines.append("### 已登记卖出（下一交易日开盘执行）\n\n")
            lines.append("| 代码 | 数量 | 执行日 | 决策日 | 原因 |\n")
            lines.append("| --- | --- | --- | --- | --- |\n")
            for p in ps:
                if not isinstance(p, dict):
                    continue
                lines.append(
                    f"| `{p.get('code')}` | {p.get('qty')} | {p.get('sell_execute_date')} | "
                    f"{p.get('decided_on')} | {p.get('reason')} |\n"
                )
            lines.append("\n")

        sb = st.get("scheduled_buys") or []
        if sb:
            lines.append("### 待执行买入（已登记）\n\n")
            for s in sb:
                if not isinstance(s, dict):
                    continue
                lines.append(
                    f"- 信号日 `{s.get('signal_date')}` → **`{s.get('buy_date')}` 开盘价** 买入"
                    f" {len(s.get('picks') or [])} 只\n"
                )
            lines.append("\n")

    tr = st.get("trades") or []
    if tr and ds:
        day_tr = [t for t in tr if isinstance(t, dict) and str(t.get("date"))[:8] == ds]
        if day_tr:
            lines.append(f"### 本交易日成交（{ds}）\n\n")
            lines.append("| 方向 | 代码 | 名称 | 数量 | 价 | 金额 | 备注 |\n")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |\n")
            for t in day_tr[-40:]:
                lines.append(
                    f"| {t.get('side')} | `{t.get('code')}` | {t.get('name')} | "
                    f"{t.get('qty')} | {t.get('price')} | {t.get('amount')} | {t.get('note', '')[:40]} |\n"
                )
            lines.append("\n")

    return "".join(lines)


def prepend_simulation_to_report_body(text: str, trade_date: str) -> str:
    """将「实盘交易展示」置于当日报告最顶端（正文、要闻、复盘脚注等均在其后）。"""
    if not _load_config()[0]:
        return text
    ds = str(trade_date)[:8]
    summary: dict[str, Any] = {}
    try:
        summary = build_trade_display_summary(ds)
    except Exception as ex:
        _log.debug("实盘展示收益汇总跳过: %s", ex)
    img_rel: Optional[str] = None
    try:
        from app.services.trade_display_ths_image import write_trade_display_png

        img_rel = write_trade_display_png(ds, summary=summary or None)
    except Exception as ex:
        _log.debug("实盘交易展示配图跳过: %s", ex)
    block = build_simulated_account_markdown(
        trade_date, image_rel=img_rel, summary=summary or None
    )
    if not block.strip():
        return text
    body = (text or "").strip()
    return block.strip() + "\n\n" + body


def append_simulation_to_report_body(text: str, trade_date: str) -> str:
    """兼容旧名：与 `prepend_simulation_to_report_body` 相同（展示已在报告顶部）。"""
    return prepend_simulation_to_report_body(text, trade_date)
