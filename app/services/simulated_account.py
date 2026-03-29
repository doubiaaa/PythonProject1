# -*- coding: utf-8 -*-
"""
模拟账户：按程序龙头池与收盘价规则撮合，跟踪净值与交易；不引入新第三方依赖。
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Optional

_lock = threading.Lock()

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

DEFAULT_CONFIG: dict[str, Any] = {
    "buy_rule": "close_of_recommendation_day",
    "sell_rule": "stop_loss_profit_or_5_days",
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


class SimulatedAccount:
    """模拟盘：先卖后买；价格默认用推荐日收盘价（由调用方传入 price_getter）。"""

    def __init__(
        self,
        account_path: str = "data/simulated_account.json",
        config_path: str = "data/simulated_config.json",
        *,
        project_root: Optional[str] = None,
    ) -> None:
        self.project_root = project_root or _PROJECT_ROOT
        self.account_path = _abs_path(self.project_root, account_path)
        self.config_path = _abs_path(self.project_root, config_path)
        self._cfg: dict[str, Any] = {}
        self._state: dict[str, Any] = {}
        self._last_series_date: Optional[str] = None
        self._last_session_buys: list[dict[str, Any]] = []
        self._last_session_sells: list[dict[str, Any]] = []
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
        return True

    def _holding_days(self, buy_date: str, market_date: str) -> int:
        try:
            bd = datetime.strptime(buy_date[:8], "%Y%m%d")
            md = datetime.strptime(market_date[:8], "%Y%m%d")
            return max(0, (md - bd).days)
        except Exception:
            return 0

    def check_sell_signals(self, market_date: str) -> list[dict[str, Any]]:
        """止盈/止损/最长持有天数。"""
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
            hd = self._holding_days(bd, market_date)
            reason = ""
            if ret <= sl:
                reason = f"止损 {ret*100:.1f}%（阈值 {sl*100:.0f}%）"
            elif ret >= tp:
                reason = f"止盈 {ret*100:.1f}%（阈值 {tp*100:.0f}%）"
            elif hd >= max_days:
                reason = f"持有满 {hd} 日（最长 {max_days} 日）"
            if reason:
                out.append({"symbol": sym, "reason": reason, "price": cur})
        return out

    def execute_daily_trades(
        self,
        recommendations: list[dict[str, Any]],
        market_date: str,
        price_getter_func: Callable[[str], float],
    ) -> None:
        """
        recommendations: symbol, name, style_bucket, buy_reason
        先卖后买；买入金额≈当前总资产 × position_size_pct（A 股 100 股一手）。
        """
        self._last_session_buys = []
        self._last_session_sells = []
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

        for sig in self.check_sell_signals(market_date):
            sym = sig["symbol"]
            px = float(sig.get("price") or price_getter_func(sym))
            if px <= 0:
                px = float(price_getter_func(sym))
            rsn = str(sig.get("reason") or "规则卖出")
            if self.sell(sym, px, rsn, market_date):
                self._last_session_sells.append(
                    {"symbol": sym, "reason": rsn, "price": px}
                )

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

        if self._last_session_buys:
            lines.append(
                "- **今日模拟已买入**（仅供观察；若参与实盘常见为 **次日开盘** 自行择价，非指令）：\n"
            )
            for x in self._last_session_buys:
                lines.append(
                    f"  - `{x['symbol']}` {x['name']} ×{x['shares']} 股 @ {float(x['price']):.4f} "
                    f"（{x['reason']}）\n"
                )
        else:
            lines.append("- **今日模拟买入**：无（可能已满仓、现金不足或缺少有效收盘价）\n")

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
