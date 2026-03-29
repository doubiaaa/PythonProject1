# -*- coding: utf-8 -*-
"""
周末龙头池周度表现邮件：读取 data/watchlist_records.json，按规则算区间收益，发 HTML 邮件。

用法：
  python scripts/weekly_performance_email.py
  python scripts/weekly_performance_email.py --dry-run
  python scripts/weekly_performance_email.py --anchor 20260328
  python scripts/weekly_performance_email.py --plot

依赖环境变量 / replay_config：SMTP（与 nightly 相同）、可选 ZHIPU_API_KEY（enable_weekly_ai_insight）。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _resolve_anchor_trade(trade_days: list[str], as_of: datetime) -> str:
    as_s = as_of.strftime("%Y%m%d")
    prior = [t for t in trade_days if t < as_s]
    if not prior:
        return trade_days[-1]
    return prior[-1]


def _call_zhipu_weekly_style(api_key: str, md: str) -> str:
    """周度「风格诊断」：归纳本周赚钱效应与模式，非简单复述数字。"""
    import requests

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    prompt = (
        "你是一位 A 股短线交易风格分析师。请根据下列「本周周报」全文（Markdown，"
        "含市场快照、**风格指数近日走势**（打板/趋势/低吸）、**严格周涨幅前 20**、"
        "龙头池区间收益、按标签的策略归因、近四周与月度汇总），"
        "完成**归纳与判断**，不要逐条复述表格中的数字。\n\n"
        "【请按以下结构用 Markdown 输出】\n"
        "### 风格诊断\n"
        "- **情绪阶段**（四选一：主升期 / 震荡分歧 / 退潮期 / 数据不足）：简述依据（1～2 点）。\n"
        "- **占优模式**（四选一：打板接力 / 趋势抱团 / 低吸反包 / 混沌难辨）：结合涨停家数、炸板率、溢价、连板高度、标签归因等简述。\n"
        "- **体量风格**（大盘 / 小盘 / 数据不足）：参考文中「锚点日涨幅前 20」的市值与换手。\n"
        "- **与上周对比**：若文中有上周溢价对比，写一句；若无则写「本周数据未提供上周对比」。\n\n"
        "### 策略归因摘要\n"
        "- 用一句话概括：本周程序龙头池样本中，哪类标签（若有）平均表现相对更好/更差（统计向，非荐股）。\n\n"
        "### 下周侧重（观察向，非投资建议）\n"
        "- 给出 2～4 条**观察清单式**建议（如更关注分歧转一致、控制追高节奏等），避免「买入/卖出」指令式措辞。\n\n"
        "---\n\n"
        "【本周周报全文】\n"
        + md[:14000]
    )
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "glm-4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.38,
            "max_tokens": 2048,
        },
        timeout=120,
    )
    if r.status_code != 200:
        return f"（智谱简评失败：HTTP {r.status_code}）"
    data = r.json()
    ch = (data.get("choices") or [{}])[0].get("message") or {}
    return str(ch.get("content") or "（无内容）")


def _maybe_plot_weights() -> None:
    """将 data/strategy_evolution_log.jsonl 画为项目根目录 weights_trend.png。"""
    from app.services.strategy_preference import plot_evolution_log

    outp = os.path.join(_ROOT, "weights_trend.png")
    if plot_evolution_log(outp):
        print(f"已生成 {outp}", flush=True)
    else:
        print(
            "权重趋势图未生成（需 matplotlib，且 data/strategy_evolution_log.jsonl 有有效记录）",
            file=sys.stderr,
        )


def _maybe_plot_sim_equity(cm) -> None:
    """将模拟账户 daily_series 画为 simulated_equity.png。"""
    from app.services.simulated_account import plot_simulated_equity_curve

    rel = cm.get("simulated_account_path", "data/simulated_account.json")
    acc_path = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel.replace("/", os.sep))
    outp = os.path.join(_ROOT, "simulated_equity.png")
    if plot_simulated_equity_curve(acc_path, outp):
        print(f"已生成 {outp}", flush=True)
    else:
        print(
            "模拟净值曲线未生成（需 matplotlib，且 simulated_account.json 含 daily_series）",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="龙头池周度表现邮件")
    parser.add_argument(
        "--anchor",
        metavar="YYYYMMDD",
        help="报告锚点交易日（一般为周五）；默认取「北京时间今日之前最近一个交易日」",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 Markdown，不发邮件",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="生成 weights_trend.png（权重）与 simulated_equity.png（模拟净值，若启用模拟账户）（需 matplotlib）",
    )
    args = parser.parse_args()
    cm = None

    try:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("Asia/Shanghai")
        except Exception:
            tz = None  # type: ignore

        now = datetime.now(tz) if tz else datetime.now()
        from app.services.data_fetcher import DataFetcher
        from app.utils.config import ConfigManager

        cm = ConfigManager()
        fetcher = DataFetcher(
            cache_expire=cm.get("cache_expire", 3600),
            retry_times=cm.get("retry_times", 2),
        )
        trade_days = fetcher.get_trade_cal()
        if not trade_days:
            print("无法获取交易日历", file=sys.stderr)
            return 1

        if args.anchor:
            anchor = args.anchor.strip()
            if anchor not in trade_days:
                print(f"锚点 {anchor} 非交易日，将回退", file=sys.stderr)
                anchor = _resolve_anchor_trade(trade_days, now)
        else:
            anchor = _resolve_anchor_trade(trade_days, now)

        adt = datetime.strptime(anchor, "%Y%m%d")
        iso_year, iso_week, _ = adt.isocalendar()

        from app.services.weekly_performance import build_weekly_report_markdown_auto

        md = build_weekly_report_markdown_auto(
            trade_days, anchor, iso_year, iso_week, fetcher=fetcher
        )

        if cm.get("enable_simulated_account", False):
            try:
                from app.services.simulated_account import SimulatedAccount
                from app.services.weekly_market_snapshot import trade_days_in_iso_week

                wd = trade_days_in_iso_week(trade_days, iso_year, iso_week)
                if wd:
                    w0, w1 = wd[0], wd[-1]
                else:
                    w0, w1 = anchor, anchor
                acc = SimulatedAccount(
                    account_path=cm.get(
                        "simulated_account_path", "data/simulated_account.json"
                    ),
                    config_path=cm.get(
                        "simulated_config_path", "data/simulated_config.json"
                    ),
                )
                md += (
                    "\n\n## 模拟账户本周表现\n\n"
                    + acc.get_weekly_summary(w0, w1)
                )
            except Exception as e:
                md += f"\n\n## 模拟账户本周表现\n\n（读取失败：{e}）\n"

        if cm.get("enable_weekly_ai_insight", False):
            api_key = (os.environ.get("ZHIPU_API_KEY") or "").strip() or (
                cm.get("zhipu_api_key") or ""
            ).strip()
            if api_key:
                try:
                    insight = _call_zhipu_weekly_style(api_key, md)
                    md += (
                        "\n## 智谱 · 风格诊断与下周侧重（归纳，非投资建议）\n\n"
                        + insight
                        + "\n"
                    )
                except Exception as e:
                    md += f"\n## 智谱 · 风格诊断\n\n（生成失败：{e}）\n"
            else:
                md += "\n## 智谱 · 风格诊断\n\n（未配置 ZHIPU_API_KEY）\n"

        if args.dry_run:
            print(md)
            return 0

        from app.services.watchlist_store import RECORDS_FILE, load_all_records

        has_recs = os.path.isfile(RECORDS_FILE) and bool(load_all_records())

        if has_recs and cm.get("enable_strategy_feedback_loop", True):
            try:
                from app.services.strategy_preference import update_from_recent_returns

                upd = update_from_recent_returns(
                    trade_days,
                    anchor,
                    iso_year,
                    iso_week,
                    smoothing=float(cm.get("strategy_weight_smoothing", 0.3)),
                    max_single=float(cm.get("strategy_weight_max_single", 0.55)),
                    min_each=float(cm.get("strategy_weight_min_each", 0.08)),
                    min_trades_per_style=int(
                        cm.get("min_trades_per_style_for_weight", 3)
                    ),
                    use_multi_week_decay=bool(
                        cm.get("use_multi_week_decay_for_strategy", True)
                    ),
                    multi_week_lookback=int(cm.get("multi_week_lookback", 4)),
                    week_decay_factor=float(
                        cm.get("strategy_week_decay_factor", 0.75)
                    ),
                    min_total_trades_per_bucket=int(
                        cm.get("min_total_trades_per_bucket_multiweek", 3)
                    ),
                    max_change_per_week=float(
                        cm.get("strategy_max_change_per_week", 0.25)
                    ),
                    shift_pullback=float(cm.get("strategy_shift_pullback", 0.5)),
                )
                print(
                    "策略偏好已更新（data/strategy_preference.json，供次日复盘动态侧重）",
                    flush=True,
                )
                alerts = upd.get("weight_alerts") or []
                if alerts and cm.get("enable_weekly_weight_anomaly_email", True):
                    from app.services.email_notify import (
                        has_email_config,
                        resolve_email_config,
                        send_report_email,
                    )

                    ecfg = resolve_email_config(cm)
                    if has_email_config(ecfg):
                        subj_a = (
                            f"【复盘】⚠️ 策略权重异常 · {iso_year}-W{iso_week:02d} · {anchor}"
                        )
                        body_a = "## 策略权重异常\n\n" + "\n".join(
                            f"- {x}" for x in alerts
                        )
                        ok_a, msg_a = send_report_email(
                            ecfg,
                            subj_a,
                            body_a,
                            extra_vars={
                                "header_date": f"{iso_year} 年第 {iso_week} 周",
                                "title": subj_a,
                            },
                        )
                        if ok_a:
                            print("已发送权重异常提醒邮件。", flush=True)
                        else:
                            print(
                                f"权重异常提醒发送失败：{msg_a}",
                                file=sys.stderr,
                            )
                    else:
                        print(
                            "存在权重异常但未配置 SMTP，跳过异常邮件：\n"
                            + "\n".join(alerts),
                            file=sys.stderr,
                        )
            except Exception as e:
                print(f"策略偏好更新失败：{e}", file=sys.stderr)

        if not has_recs:
            print(
                "无 data/watchlist_records.json 或内容为空，跳过发信。"
                "请在持久化环境跑复盘以积累龙头池存档。",
                file=sys.stderr,
            )
            return 0

        if not cm.get("enable_weekly_performance_email", True):
            print("enable_weekly_performance_email 为 false，跳过发信", file=sys.stderr)
            print(md)
            return 0

        from app.services.email_notify import (
            has_email_config,
            resolve_email_config,
            send_report_email,
        )

        email_cfg = resolve_email_config(cm)
        if not has_email_config(email_cfg):
            print("未配置 SMTP，无法发邮件（可用 --dry-run 查看正文）", file=sys.stderr)
            return 1

        if cm.get("weekly_email_attach_charts", True):
            _maybe_plot_weights()
            if cm.get("enable_simulated_account", False):
                _maybe_plot_sim_equity(cm)

        from app.utils.email_template import embed_image_cid, markdown_to_html

        html_frag = markdown_to_html(md)
        inline_images: list[tuple[str, str]] = []
        for cid, fname in (
            ("wchart", "weights_trend.png"),
            ("eqchart", "simulated_equity.png"),
        ):
            p = os.path.join(_ROOT, fname)
            if os.path.isfile(p):
                html_frag = embed_image_cid(html_frag, p, cid)
                inline_images.append((cid, p))

        subj = (
            f"【复盘】📊 龙头池周度表现 · {iso_year}年第{iso_week}周 · 锚点{anchor}"
        )
        ok, msg = send_report_email(
            email_cfg,
            subj,
            md,
            html_fragment=html_frag,
            inline_images=inline_images or None,
            extra_vars={
                "header_date": f"{iso_year}年第{iso_week}周 · 锚点 {anchor}",
                "title": subj,
            },
        )
        if not ok:
            print(f"发送失败：{msg}", file=sys.stderr)
            return 1
        print("已发送：", subj)
        return 0
    finally:
        if args.plot:
            _maybe_plot_weights()
            if cm is not None and cm.get("enable_simulated_account", False):
                _maybe_plot_sim_equity(cm)


if __name__ == "__main__":
    raise SystemExit(main())
