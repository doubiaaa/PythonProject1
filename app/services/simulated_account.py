# -*- coding: utf-8 -*-
"""
模拟账户：按程序龙头池与收盘价规则撮合，跟踪净值与交易；不引入新第三方依赖。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Optional

_logger = logging.getLogger(__name__)

_lock = threading.Lock()

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

DEFAULT_CONFIG: dict[str, Any] = {
    "buy_rule": "close_of_recommendation_day",
    "sell_rule": "stop_loss_profit_or_5_days",
    "buy_price_type": "close_of_recommendation_day",
    "stop_loss": -0.05,
    "stop_profit": 0.15,
    "max_holding_days": 5,
    "max_positions": 5,
    "position_size_pct": 0.2,
    "min_cash_reserve": 500,
}

DEFAULT_STATE: dict[str, Any] = {
    "initial_capital": 10000,
    "cash": 10000,
    "holdings": [],
    "transactions": [],
    "daily_series": [],
    "total_value": 10000,
}


def _abs_path(project_root: str, p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.join(project_root, p.replace("/", os.sep))


def _norm_symbol(s: str) -> str:
    return "".join(c for c in str(s) if c.isdigit())[:6].zfill(6)


def count_trade_days_held(
    trade_days: Optional[list[str]], buy_date: str, market_date: str
) -> int:
    """
    买入日之后至 market_date（含）之间的交易日数。
    无交易日历时退回自然日差（与旧行为兼容）。
    """
    bd_s, md_s = buy_date[:8], market_date[:8]
    if trade_days:
        return sum(1 for d in trade_days if bd_s < d <= md_s)
    try:
        bd = datetime.strptime(bd_s, "%Y%m%d")
        md = datetime.strptime(md_s, "%Y%m%d")
        return max(0, (md - bd).days)
    except Exception:
        return 0


def pending_buys_file(project_root: str, signal_date: str) -> str:
    return os.path.join(
        project_root, "data", f"pending_buys_{signal_date[:8]}.json"
    )


class SimulatedAccount:
    """模拟盘：先卖后买；价格默认用推荐日收盘价（由调用方传入 price_getter）。"""

    def __init__(
        self,
        account_path: str = "data/simulated_account.json",
        config_path: str = "data/simulated_config.json",
        *,
        project_root: Optional[str] = None,
        config_manager: Optional[Any] = None,
    ) -> None:
        self.project_root = project_root or _PROJECT_ROOT
        self.account_path = _abs_path(self.project_root, account_path)
        self.config_path = _abs_path(self.project_root, config_path)
        self._config_manager = config_manager
        self._cfg: dict[str, Any] = {}
        self._state: dict[str, Any] = {}
        self._last_series_date: Optional[str] = None
        self._last_session_buys: list[dict[str, Any]] = []
        self._last_session_sells: list[dict[str, Any]] = []
        self._last_pending_recs: list[dict[str, Any]] = []
        self.load_state()

    def _ensure_data_files(self) -> None:
        os.makedirs(os.path.dirname(self.account_path), exist_ok=True)
        if not os.path.isfile(self.config_path):
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        if not os.path.isfile(self.account_path):
            with open(self.account_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_STATE, f, ensure_ascii=False, indent=2)

    def load_state(self) -> None:
        with _lock:
            self._ensure_data_files()
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._cfg = {**DEFAULT_CONFIG, **json.load(f)}
            except Exception:
                self._cfg = deepcopy(DEFAULT_CONFIG)
            try:
                with open(self.account_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception:
                self._state = deepcopy(DEFAULT_STATE)
            for k in DEFAULT_STATE:
                self._state.setdefault(k, deepcopy(DEFAULT_STATE)[k])
            if not isinstance(self._state.get("holdings"), list):
                self._state["holdings"] = []
            if not isinstance(self._state.get("transactions"), list):
                self._state["transactions"] = []
            if not isinstance(self._state.get("daily_series"), list):
                self._state["daily_series"] = []
            self._last_series_date = None
            if self._state["daily_series"]:
                last = self._state["daily_series"][-1]
                if isinstance(last, dict) and last.get("date"):
                    self._last_series_date = str(last["date"])

    def save_state(self) -> None:
        with _lock:
            os.makedirs(os.path.dirname(self.account_path), exist_ok=True)
            tmp = self.account_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.account_path)

    def _holding_value(self) -> float:
        tot = 0.0
        for h in self._state["holdings"]:
            sh = int(h.get("shares") or 0)
            px = float(h.get("current_price") or h.get("cost_price") or 0)
            tot += sh * px
        return tot

    def recalculate_total_value(self, market_date: str) -> None:
        """更新 total_value，并按自然日只追加一条 daily_series。"""
        self._state["total_value"] = float(self._state["cash"]) + self._holding_value()
        tv = float(self._state["total_value"])
        ds: list = self._state["daily_series"]
        if self._last_series_date == market_date and ds:
            ds[-1] = {
                "date": market_date,
                "total_value": round(tv, 2),
                "cash": round(float(self._state["cash"]), 2),
            }
        else:
            ds.append(
                {
                    "date": market_date,
                    "total_value": round(tv, 2),
                    "cash": round(float(self._state["cash"]), 2),
                }
            )
            self._last_series_date = market_date

    def update_prices(self, price_dict: dict[str, float]) -> None:
        """根据 {symbol: price} 更新持仓现价。"""
        pmap = {_norm_symbol(k): float(v) for k, v in (price_dict or {}).items()}
        for h in self._state["holdings"]:
            sym = _norm_symbol(str(h.get("symbol") or ""))
            if sym in pmap and pmap[sym] > 0:
                h["current_price"] = pmap[sym]
        self._state["total_value"] = float(self._state["cash"]) + self._holding_value()

    def _holdings_top_summary(self, limit: int = 3) -> str:
        """按持仓市值近似排序，取前若干只，用于邮件正文。"""
        rows: list[tuple[float, str]] = []
        for h in self._state.get("holdings") or []:
            sh = int(h.get("shares") or 0)
            px = float(h.get("current_price") or h.get("cost_price") or 0)
            mv = sh * px
            sym = str(h.get("symbol") or "")
            nm = str(h.get("name") or "")
            rows.append((mv, f"`{sym}` {nm} ×{sh} 股 ≈ {mv:,.2f} 元"))
        rows.sort(key=lambda x: -x[0])
        if not rows:
            return "（无持仓）"
        return "\n".join(f"- {t[1]}" for t in rows[:limit])

    def _schedule_trade_notification(
        self,
        *,
        side: str,
        symbol: str,
        name: str,
        shares: int,
        price: float,
        reason: str,
        trade_date: str,
    ) -> None:
        """后台线程发送邮件，失败仅记日志，不影响成交。"""

        def _run() -> None:
            try:
                cm = self._config_manager
                if cm is None:
                    from app.utils.config import ConfigManager

                    cm = ConfigManager()
                if not cm.get("enable_simulated_trade_notification", False):
                    return
                from app.services.email_notify import (
                    has_email_config,
                    resolve_email_config,
                    send_simulated_trade_notification,
                )
                from app.utils.email_template import holdings_to_html_rows

                ecfg = resolve_email_config(cm)
                if not has_email_config(ecfg):
                    return
                op = "买入" if side == "buy" else "卖出"
                subj = f"【模拟账户{op}】{symbol} {name} {shares}股@{price:.2f}"
                tv = float(self._state.get("total_value") or 0)
                cash = float(self._state.get("cash") or 0)
                n_hold = len(self._state.get("holdings") or [])
                hmv = max(0.0, tv - cash)
                ic = float(self._state.get("initial_capital") or 0) or 10000.0
                day_ret: Optional[float] = None
                ds = self._state.get("daily_series") or []
                if isinstance(ds, list) and len(ds) >= 2:
                    try:
                        v0 = float(ds[-2].get("total_value") or 0)
                        v1 = float(ds[-1].get("total_value") or 0)
                        if v0 > 0:
                            day_ret = (v1 / v0 - 1.0) * 100.0
                    except Exception:
                        pass
                rows = holdings_to_html_rows(
                    list(self._state.get("holdings") or []),
                    limit=3,
                    total_portfolio_value=tv,
                )
                action_line = (
                    f"建议跟随模拟账户【{op}】{symbol} {name}；"
                    "以下为模拟盘逻辑输出，实盘请自行决策与风控。"
                )
                trade_info = {
                    "side": side,
                    "symbol": str(symbol),
                    "name": str(name),
                    "shares": int(shares),
                    "price": float(price),
                    "amount": float(shares) * float(price),
                    "reason": str(reason),
                    "trade_date": str(trade_date),
                    "subject": subj,
                    "action_line": action_line,
                    "top_holdings_html_rows": rows,
                }
                account_snapshot = {
                    "total_value": tv,
                    "cash": cash,
                    "holding_market_value": hmv,
                    "n_positions": n_hold,
                    "initial_capital": ic,
                    "day_return_pct": day_ret,
                }
                ok, msg = send_simulated_trade_notification(
                    ecfg,
                    trade_info,
                    account_snapshot,
                    extra_vars={
                        "header_date": f"成交日 {trade_date}",
                        "title": subj,
                        "email_app_version": ecfg.get("email_app_version", "1.0"),
                    },
                )
                if not ok and msg != "skipped":
                    _logger.warning("模拟账户成交邮件发送失败：%s", msg)
            except Exception as ex:
                _logger.warning("模拟账户成交邮件异常：%s", ex, exc_info=False)

        threading.Thread(target=_run, daemon=True).start()

    def buy(
        self,
        symbol: str,
        name: str,
        shares: int,
        price: float,
        reason: str,
        date: str,
    ) -> bool:
        if shares < 100 or shares % 100 != 0:
            return False
        if price <= 0:
            return False
        cost = shares * price
        if float(self._state["cash"]) < cost:
            return False
        sym = _norm_symbol(symbol)
        self._state["cash"] = float(self._state["cash"]) - cost
        self._state["holdings"].append(
            {
                "symbol": sym,
                "name": name or sym,
                "shares": shares,
                "cost_price": round(price, 4),
                "buy_date": date,
                "current_price": round(price, 4),
                "style_bucket": "",
            }
        )
        self._state["transactions"].append(
            {
                "date": date,
                "symbol": sym,
                "name": name or sym,
                "side": "buy",
                "shares": shares,
                "price": round(price, 4),
                "amount": round(cost, 2),
                "reason": reason,
            }
        )
        self._state["total_value"] = float(self._state["cash"]) + self._holding_value()
        self._schedule_trade_notification(
            side="buy",
            symbol=sym,
            name=str(name or sym),
            shares=shares,
            price=float(price),
            reason=reason,
            trade_date=date,
        )
        return True

    def sell(
        self, symbol: str, price: float, reason: str, date: str
    ) -> bool:
        sym = _norm_symbol(symbol)
        idx = None
        for i, h in enumerate(self._state["holdings"]):
            if _norm_symbol(str(h.get("symbol"))) == sym:
                idx = i
                break
        if idx is None:
            return False
        h = self._state["holdings"].pop(idx)
        sh = int(h.get("shares") or 0)
        if price <= 0 or sh <= 0:
            self._state["holdings"].insert(idx, h)
            return False
        proceeds = sh * price
        self._state["cash"] = float(self._state["cash"]) + proceeds
        self._state["transactions"].append(
            {
                "date": date,
                "symbol": sym,
                "name": str(h.get("name") or sym),
                "side": "sell",
                "shares": sh,
                "price": round(price, 4),
                "amount": round(proceeds, 2),
                "reason": reason,
            }
        )
        self._state["total_value"] = float(self._state["cash"]) + self._holding_value()
        self._schedule_trade_notification(
            side="sell",
            symbol=sym,
            name=str(h.get("name") or sym),
            shares=sh,
            price=float(price),
            reason=reason,
            trade_date=date,
        )
        return True

    def check_sell_signals(
        self,
        market_date: str,
        trade_days: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        卖出信号优先级：止盈 > 止损 > 持有天数上限。
        持有天数：若提供 trade_days 则为其间交易日数，否则为自然日差。
        """
        sl = float(self._cfg.get("stop_loss", -0.05))
        tp = float(self._cfg.get("stop_profit", 0.15))
        max_days = int(self._cfg.get("max_holding_days", 5))
        out: list[dict[str, Any]] = []
        for h in list(self._state["holdings"]):
            sym = _norm_symbol(str(h.get("symbol")))
            cost = float(h.get("cost_price") or 0)
            cur = float(h.get("current_price") or cost)
            if cost <= 0:
                continue
            ret = cur / cost - 1.0
            bd = str(h.get("buy_date") or market_date)
            hd = count_trade_days_held(trade_days, bd, market_date)
            reason = ""
            if ret >= tp:
                reason = f"止盈 {ret*100:.1f}%（阈值 {tp*100:.0f}%）"
            elif ret <= sl:
                reason = f"止损 {ret*100:.1f}%（阈值 {sl*100:.0f}%）"
            elif hd >= max_days:
                unit = "交易日" if trade_days else "自然日"
                reason = f"持有满 {hd} {unit}（最长 {max_days}）"
            if reason:
                out.append({"symbol": sym, "reason": reason, "price": cur})
        return out

    def write_pending_buys(
        self, signal_date: str, recommendations: list[dict[str, Any]]
    ) -> str:
        """写入 T 日待买清单，买入价留空，由次日开盘脚本执行。"""
        path = pending_buys_file(self.project_root, signal_date)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "signal_date": signal_date[:8],
            "recommendations": recommendations,
            "buy_prices": {},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def execute_pending_buys(
        self,
        execution_date: str,
        signal_date: str,
        price_getter_func: Callable[[str], float],
        trade_days: Optional[list[str]] = None,
    ) -> bool:
        """
        读取 pending_buys_{signal_date}.json，按开盘价（或 price_getter）执行买入，成功后删除文件。
        """
        path = pending_buys_file(self.project_root, signal_date)
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False
        recs = list(payload.get("recommendations") or [])
        if not recs:
            try:
                os.remove(path)
            except OSError:
                pass
            return False

        self._last_session_buys = []
        max_pos = int(self._cfg.get("max_positions", 5))
        pct = float(self._cfg.get("position_size_pct", 0.2))
        reserve = float(self._cfg.get("min_cash_reserve", 500))
        held = {_norm_symbol(str(h.get("symbol"))) for h in self._state["holdings"]}

        for rec in recs:
            if len(self._state["holdings"]) >= max_pos:
                break
            sym = _norm_symbol(str(rec.get("symbol") or ""))
            if not sym or sym in held:
                continue
            price = float(price_getter_func(sym))
            if price <= 0:
                continue
            self.recalculate_total_value(execution_date)
            tv = float(self._state["total_value"])
            budget = tv * pct
            if float(self._state["cash"]) - reserve < budget * 0.5:
                budget = max(0.0, float(self._state["cash"]) - reserve)
            raw_sh = int(budget / price)
            shares = (raw_sh // 100) * 100
            if shares < 100:
                continue
            cost = shares * price
            if float(self._state["cash"]) - cost < reserve:
                continue
            name = str(rec.get("name") or sym)
            reason = str(rec.get("buy_reason") or "次日开盘买入")
            style = str(rec.get("style_bucket") or "")
            if self.buy(sym, name, shares, price, reason, execution_date):
                for h in self._state["holdings"]:
                    if _norm_symbol(str(h.get("symbol"))) == sym:
                        h["style_bucket"] = style
                        break
                held.add(sym)
                self._last_session_buys.append(
                    {
                        "symbol": sym,
                        "name": name,
                        "shares": shares,
                        "price": price,
                        "reason": reason,
                    }
                )

        self.recalculate_total_value(execution_date)
        self.save_state()
        if self._last_session_buys or not recs:
            try:
                os.remove(path)
            except OSError:
                pass
        return bool(self._last_session_buys)

    def execute_daily_trades(
        self,
        recommendations: list[dict[str, Any]],
        market_date: str,
        price_getter_func: Callable[[str], float],
        *,
        trade_days: Optional[list[str]] = None,
    ) -> None:
        """
        recommendations: symbol, name, style_bucket, buy_reason
        先卖后买；若 buy_price_type 为 next_day_open 则只写 pending，不在 T 日买入。
        """
        mode = str(
            self._cfg.get("buy_price_type") or "close_of_recommendation_day"
        )
        self._last_session_buys = []
        self._last_session_sells = []
        self._last_pending_recs = []
        syms: set[str] = set()
        for h in self._state["holdings"]:
            syms.add(_norm_symbol(str(h.get("symbol"))))
        for rec in recommendations:
            s = _norm_symbol(str(rec.get("symbol") or ""))
            if s:
                syms.add(s)
        self.update_prices(
            {s: float(price_getter_func(s)) for s in syms if s}
        )
        self.recalculate_total_value(market_date)

        for sig in self.check_sell_signals(market_date, trade_days=trade_days):
            sym = sig["symbol"]
            px = float(sig.get("price") or price_getter_func(sym))
            if px <= 0:
                px = float(price_getter_func(sym))
            rsn = str(sig.get("reason") or "规则卖出")
            if self.sell(sym, px, rsn, market_date):
                self._last_session_sells.append(
                    {"symbol": sym, "reason": rsn, "price": px}
                )

        if mode == "next_day_open":
            if recommendations:
                self.write_pending_buys(market_date, recommendations)
                self._last_pending_recs = list(recommendations)
            self.recalculate_total_value(market_date)
            self.save_state()
            return

        max_pos = int(self._cfg.get("max_positions", 5))
        pct = float(self._cfg.get("position_size_pct", 0.2))
        reserve = float(self._cfg.get("min_cash_reserve", 500))

        held = {_norm_symbol(str(h.get("symbol"))) for h in self._state["holdings"]}

        for rec in recommendations:
            if len(self._state["holdings"]) >= max_pos:
                break
            sym = _norm_symbol(str(rec.get("symbol") or ""))
            if not sym or sym in held:
                continue
            price = float(price_getter_func(sym))
            if price <= 0:
                continue
            self.recalculate_total_value(market_date)
            tv = float(self._state["total_value"])
            budget = tv * pct
            if float(self._state["cash"]) - reserve < budget * 0.5:
                budget = max(0.0, float(self._state["cash"]) - reserve)
            raw_sh = int(budget / price)
            shares = (raw_sh // 100) * 100
            if shares < 100:
                continue
            cost = shares * price
            if float(self._state["cash"]) - cost < reserve:
                continue
            name = str(rec.get("name") or sym)
            reason = str(rec.get("buy_reason") or "推荐买入")
            style = str(rec.get("style_bucket") or "")
            if self.buy(sym, name, shares, price, reason, market_date):
                for h in self._state["holdings"]:
                    if _norm_symbol(str(h.get("symbol"))) == sym:
                        h["style_bucket"] = style
                        break
                held.add(sym)
                self._last_session_buys.append(
                    {
                        "symbol": sym,
                        "name": name,
                        "shares": shares,
                        "price": price,
                        "reason": reason,
                    }
                )

        self.recalculate_total_value(market_date)
        self.save_state()

    def generate_daily_plan(self, market_date: str) -> str:
        """T 日收盘后模拟成交后的「明日可参考」说明（非投资建议）。"""
        mode = str(
            self._cfg.get("buy_price_type") or "close_of_recommendation_day"
        )
        lines: list[str] = [
            "### 模拟账户 · 操作备忘（非投资建议）\n",
            f"- **复盘日**：{market_date}\n",
            f"- **模拟总资产**：{float(self._state['total_value']):,.2f} 元；"
            f"**现金**：{float(self._state['cash']):,.2f} 元\n",
        ]
        if self._last_session_sells:
            lines.append("- **今日模拟已卖出**（实盘若仍持仓请自行决策是否跟进卖出）：\n")
            for x in self._last_session_sells:
                lines.append(
                    f"  - `{x['symbol']}`：{x['reason']} @ {float(x['price']):.4f}\n"
                )
        else:
            lines.append("- **今日模拟卖出**：无\n")

        if mode == "next_day_open" and self._last_pending_recs:
            pfn = f"data/pending_buys_{market_date[:8]}.json"
            lines.append(
                "- **买入**：已写入 **次日开盘价** 队列（文件：**"
                + pfn
                + "**），将由定时任务或手动执行 `scripts/simulated_morning_buy.py` 撮合：\n"
            )
            for r in self._last_pending_recs:
                sym = _norm_symbol(str(r.get("symbol") or ""))
                lines.append(
                    f"  - `{sym}` {r.get('name') or ''}（{r.get('buy_reason') or ''}）\n"
                )
        elif self._last_session_buys:
            lines.append(
                "- **今日模拟已买入**（仅供观察；若参与实盘常见为 **次日开盘** 自行择价，非指令）：\n"
            )
            for x in self._last_session_buys:
                lines.append(
                    f"  - `{x['symbol']}` {x['name']} ×{x['shares']} 股 @ {float(x['price']):.4f} "
                    f"（{x['reason']}）\n"
                )
        else:
            lines.append(
                "- **今日模拟买入**：无（可能已满仓、现金不足、缺少有效收盘价，"
                "或已切换为次日开盘买入模式且未产生推荐）\n"
            )

        if self._state["holdings"]:
            lines.append("- **当前模拟持仓**：\n")
            for h in self._state["holdings"]:
                sym = str(h.get("symbol"))
                nm = str(h.get("name"))
                sh = int(h.get("shares") or 0)
                cp = float(h.get("current_price") or 0)
                lines.append(
                    f"  - `{sym}` {nm} ×{sh} ；现价≈{cp:.4f} "
                    f"（{h.get('style_bucket') or '—'}）\n"
                )
        else:
            lines.append("- **当前模拟持仓**：空仓\n")

        lines.append(
            "\n> 以上为模拟盘逻辑输出，与真实成交、滑点、税费无关；不构成投资建议。\n"
        )
        return "".join(lines)

    def get_weekly_summary(self, start_date: str, end_date: str) -> str:
        """Markdown 片段：周收益、累计收益、回撤、交易与胜率（按区间内卖出计）。"""
        sd, ed = start_date[:8], end_date[:8]
        series = [
            x
            for x in self._state.get("daily_series") or []
            if isinstance(x, dict)
            and str(x.get("date") or "") >= sd
            and str(x.get("date") or "") <= ed
        ]
        init = float(self._state.get("initial_capital") or 10000)
        if not series:
            return (
                f"*本周（{sd}～{ed}）无模拟净值打点（尚未在区间内运行过模拟）。* "
                f"当前总资产 ≈ {float(self._state.get('total_value') or init):,.2f} 元。\n"
            )

        v0 = float(series[0]["total_value"])
        v1 = float(series[-1]["total_value"])
        week_ret = (v1 / v0 - 1.0) if v0 > 0 else 0.0
        peak = v0
        mdd = 0.0
        for x in series:
            tv = float(x.get("total_value") or 0)
            if tv > peak:
                peak = tv
            if peak > 0:
                dd = (peak - tv) / peak
                if dd > mdd:
                    mdd = dd

        total_ret = (v1 / init - 1.0) if init > 0 else 0.0
        txs = self._state.get("transactions") or []
        in_week = [
            t
            for t in txs
            if isinstance(t, dict)
            and sd <= str(t.get("date") or "") <= ed
        ]
        sells = [t for t in in_week if t.get("side") == "sell"]
        wins = 0
        for t in sells:
            sym = _norm_symbol(str(t.get("symbol")))
            amt = float(t.get("amount") or 0)
            buys = [
                x
                for x in txs
                if isinstance(x, dict)
                and x.get("side") == "buy"
                and _norm_symbol(str(x.get("symbol"))) == sym
                and str(x.get("date") or "") <= str(t.get("date") or "")
            ]
            if not buys:
                continue
            last_buy = max(buys, key=lambda b: str(b.get("date") or ""))
            cost = float(last_buy.get("amount") or 0)
            if amt > cost:
                wins += 1
        win_rate = (wins / len(sells)) if sells else 0.0

        return (
            f"- **区间**：{sd} ～ {ed}\n"
            f"- **周净值涨跌**：{week_ret*100:.2f}%（区间首尾模拟总资产）\n"
            f"- **相对初始本金累计**：{total_ret*100:.2f}%（初始 {init:,.0f} 元 → 约 {v1:,.2f} 元）\n"
            f"- **区间内最大回撤（估算）**：{mdd*100:.2f}%\n"
            f"- **区间内成交笔数**：{len(in_week)}（卖出 {len(sells)} 笔）\n"
            f"- **卖出胜率（简化）**：{win_rate*100:.0f}%（{wins}/{len(sells) if sells else 0}）\n"
        )


def plot_simulated_equity_curve(account_path: str, output_path: str) -> bool:
    """根据 simulated_account.json 的 daily_series 绘制净值曲线。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    if not os.path.isfile(account_path):
        return False
    try:
        with open(account_path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return False
    series = st.get("daily_series") or []
    if not series:
        return False
    xs = range(len(series))
    ys = [float(x.get("total_value") or 0) for x in series if isinstance(x, dict)]
    if not ys:
        return False
    labels = [str(x.get("date") or "") for x in series if isinstance(x, dict)]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, ys, marker=".", label="total_value")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("元")
    ax.set_title("Simulated account equity (total_value)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()
    return True


def recommendations_from_top_pool(
    top_pool: list[dict[str, Any]],
    *,
    tag_to_bucket_func: Callable[[str], str],
) -> list[dict[str, Any]]:
    """由程序龙头池构造模拟买入推荐列表。"""
    out: list[dict[str, Any]] = []
    for p in top_pool or []:
        code = _norm_symbol(str(p.get("code") or ""))
        if not code:
            continue
        tag = str(p.get("tag") or "")
        out.append(
            {
                "symbol": code,
                "name": str(p.get("name") or ""),
                "style_bucket": tag_to_bucket_func(tag),
                "buy_reason": f"程序龙头池（{tag or '未分类'}）",
            }
        )
    return out


def price_map_from_top_pool(top_pool: list[dict[str, Any]]) -> dict[str, float]:
    m: dict[str, float] = {}
    for p in top_pool or []:
        sym = _norm_symbol(str(p.get("code") or ""))
        cl = float(p.get("close") or 0)
        if sym and cl > 0:
            m[sym] = cl
    return m


def price_from_map(price_map: dict[str, float], symbol: str) -> float:
    """供 execute_daily_trades 的 price_getter 使用。"""
    return float(price_map.get(_norm_symbol(symbol), 0) or 0)
