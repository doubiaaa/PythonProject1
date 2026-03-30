from datetime import datetime
import json
import threading
from typing import Any, Optional

from config.replay_prompt_templates import build_main_replay_prompt
from app.services.email_notify import has_email_config, send_report_email
from app.utils.email_template import truncate_finance_news_push_prefix
from app.services.serverchan_notify import send_serverchan
from app.services.strategy_preference import (
    build_prompt_addon,
    effective_weights_from_stability,
    load_strategy_preference,
    probe_style_stability,
)
from app.services.watchlist_store import append_daily_top_pool
from app.utils.config import ConfigManager
from app.services.replay_checkpoint import (
    load_fetcher_bundle,
    load_market_data_cache,
    save_fetcher_bundle,
)
from app.services.zhipu_client import ZhipuClient
from app.services.separation_confirmation import perform_separation_confirmation

MODEL_NAME = "glm-4-flash"  # 智谱免费模型
MAX_LOG_ENTRIES = 200

MODE_NAME = "次日竞价半路模式"

_DRAGON_HEADINGS = (
    "周期定性",
    "情绪数据量化",
    "核心股聚焦",
    "明日预案",
)


def _ensure_dragon_report_sections(text: str) -> str:
    """若缺少龙头模板关键章节标题，在文末追加系统提示（不重试 API）。"""
    if not text or not str(text).strip():
        return text
    missing = [h for h in _DRAGON_HEADINGS if h not in text]
    if not missing:
        return text
    note = (
        "\n\n---\n\n> **【系统提示】** 本次输出未检测到以下章节标题，"
        "请人工对照程序数据复核或缩小单节篇幅后重试："
        + "、".join(missing)
        + "。\n"
    )
    return text.rstrip() + note


def _extract_summary_line(text: str) -> Optional[str]:
    """解析报告首行【摘要】…，用于推送标题。"""
    if not text:
        return None
    for line in text.strip().split("\n"):
        s = line.strip()
        if s.startswith("【摘要】"):
            return s[:220]
    return None


def _ensure_summary_line(text: str) -> str:
    """模型未输出规范【摘要】首行时补一行，便于推送解析与阅读。"""
    if not text or not str(text).strip():
        return text
    first = str(text).strip().split("\n")[0].strip()
    if first.startswith("【摘要】"):
        return text
    return (
        "【摘要】周期阶段：震荡期｜适宜度：中｜置信度：低（系统补全：模型未输出规范首行摘要）\n\n"
        + text
    )


class ReplayTask:
    def __init__(self):
        self._lock = threading.RLock()
        self.status = "idle"
        self.result = None
        self.logs = []
        self.progress = 0

    def try_begin(self):
        """若已有任务在跑则返回 False；否则占用任务并清空状态。"""
        with self._lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.logs = []
            self.result = None
            self.progress = 0
            return True

    def log(self, message):
        with self._lock:
            self.logs.append(
                {"time": datetime.now().strftime("%H:%M:%S"), "message": message}
            )
            if len(self.logs) > MAX_LOG_ENTRIES:
                del self.logs[: len(self.logs) - MAX_LOG_ENTRIES]

    def snapshot(self):
        """供 HTTP 轮询读取，避免与后台线程日志写入竞态。"""
        with self._lock:
            return {
                "status": self.status,
                "result": self.result,
                "logs": list(self.logs),
                "progress": self.progress,
            }

    def build_prompt(
        self,
        date,
        market_data,
        *,
        effective_weights=None,
        stability_hint: str = "",
        dragon_meta: Optional[dict[str, Any]] = None,
        separation_result: Optional[dict[str, Any]] = None,
    ):
        """
        龙头短线选手复盘模板 + 次日竞价半路程序约束。
        dragon_meta：程序侧结构化快照（连板梯队、大面数等），供引用。
        separation_result：分离确认结果。
        """
        addon = build_prompt_addon(
            effective_weights=effective_weights,
            stability_hint=stability_hint or "",
        )
        meta_block = ""
        if dragon_meta:
            try:
                meta_json = json.dumps(dragon_meta, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                meta_json = "{}"
            meta_block = (
                "\n## 【程序结构化快照·JSON】（须与「龙头选手·程序量化快照」Markdown 交叉验证）\n"
                f"```json\n{meta_json}\n```\n"
            )
        
        # 添加分离确认结果
        separation_block = ""
        if separation_result and separation_result.get('candidates'):
            separation_block = "\n## 【分离确认·候选】\n"
            separation_block += "- 总龙头：{name}({code}) 连板{lb}\n".format(
                name=separation_result['leading_stock'].get('name', ''),
                code=separation_result['leading_stock'].get('code', ''),
                lb=separation_result['leading_stock'].get('lb', 0)
            )
            if separation_result.get('volatility_points'):
                points = separation_result['volatility_points']
                separation_block += f"- 异动时间点：{len(points)} 个（{points[0]['type']}等）\n"
            separation_block += "- 分离确认候选：\n"
            for i, candidate in enumerate(separation_result['candidates'][:5], 1):
                separation_block += f"  {i}. {candidate['name']}({candidate['code']}) 得分：{candidate.get('separation_score', 0):.2f}\n"
        
        return build_main_replay_prompt(
            mode_name=MODE_NAME,
            date=str(date),
            market_data=market_data,
            addon=addon,
            meta_block=meta_block + separation_block,
        )

    def call_zhipu(self, api_key, prompt, temperature=0.42, max_tokens=6144):
        """调用智谱API（封装重试与超时；连接与读取超时见 replay_config data_source）。"""
        cm = ConfigManager()
        ds = cm.get("data_source") or {}
        conn = float(ds.get("zhipu_connect_timeout", 10))
        read = float(ds.get("zhipu_read_timeout", 120))
        timeout = (conn, read)
        client = ZhipuClient(api_key, model=MODEL_NAME, timeout=timeout)
        return client.chat_completion(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

    def run(self, date, api_key, data_fetcher, serverchan_sendkey=None, email_cfg=None):
        actual_date = date
        try:
            data_fetcher.set_current_task(self)

            self.progress = 10
            _cfg = ConfigManager()
            use_resume = bool(
                _cfg.get("resume_replay_if_available", False)
                and _cfg.get("enable_replay_checkpoint", True)
            )
            market_data = None
            if use_resume:
                md = load_market_data_cache(date)
                bundle = load_fetcher_bundle(date)
                if md and bundle is not None:
                    market_data = md
                    data_fetcher._last_dragon_trader_meta = bundle.get("dragon") or {}
                    data_fetcher._last_auction_meta = bundle.get("auction") or {}
                    data_fetcher._last_email_kpi = bundle.get("email_kpi") or {}
                    data_fetcher._last_news_push_prefix = str(
                        bundle.get("news_prefix") or ""
                    )
                    actual_date = str(date)[:8]
                    self.log("断点续跑：已加载市场摘要与程序缓存（跳过 get_market_summary）")
                    self.progress = 90

            if market_data is None:
                self.log("正在获取市场数据与次日竞价半路选股…")
                market_data, actual_date = data_fetcher.get_market_summary(date)
                self.progress = 90
                if _cfg.get("enable_replay_checkpoint", True):
                    try:
                        save_fetcher_bundle(actual_date, market_data, data_fetcher)
                    except Exception as ex:
                        self.log(f"写入复盘断点缓存失败（可忽略）：{ex}")

            if actual_date != date:
                self.log(f"日期已自动调整为交易日: {actual_date}")

            self.progress = 95
            self.log("数据获取完成，正在调用AI…")
            eff_w = None
            stab_hint = ""
            separation_result = None
            
            # 执行分离确认分析
            try:
                df_zt = getattr(data_fetcher, "_last_zt_pool", None)
                if df_zt is not None:
                    _td = data_fetcher.get_trade_cal()
                    if _td:
                        separation_result = perform_separation_confirmation(actual_date, df_zt, _td)
                        if separation_result and separation_result.get('candidates'):
                            self.log(f"分离确认完成，找到 {len(separation_result['candidates'])} 个候选股")
            except Exception as ex:
                self.log(f"分离确认分析失败：{ex}")
            
            # 风格稳定性探测
            _cm2 = ConfigManager()
            if _cm2.get("enable_style_stability_probe", True):
                try:
                    stab = probe_style_stability(api_key, market_data)
                    stab_hint = stab
                    base = load_strategy_preference().get("strategy_weights") or {}
                    eff_w = effective_weights_from_stability(stab, dict(base))
                    self.log(f"风格稳定性探测：{stab}")
                except Exception as ex:
                    self.log(f"风格稳定性探测失败（沿用文件权重）：{ex}")
            
            # 构建prompt
            prompt = self.build_prompt(
                actual_date,
                market_data,
                effective_weights=eff_w,
                stability_hint=stab_hint,
                dragon_meta=getattr(data_fetcher, "_last_dragon_trader_meta", None) or {},
                separation_result=separation_result,
            )
            result = self.call_zhipu(api_key, prompt)
            result = _ensure_dragon_report_sections(_ensure_summary_line(result))
            self.log("报告首行与龙头模板章节已校验（必要时已补全/提示）")
            sum_line = _extract_summary_line(result)
            news_pre = (getattr(data_fetcher, "_last_news_push_prefix", None) or "").strip()
            if news_pre:
                _cm_news = ConfigManager()
                news_pre = truncate_finance_news_push_prefix(
                    news_pre,
                    max_items=int(_cm_news.get("email_news_max_items", 3)),
                    filter_prefix=str(
                        _cm_news.get(
                            "email_news_filter_prefix",
                            "【本文系数据通用户提前专享】",
                        )
                    ),
                )
                result = news_pre + result
                self.log("已附加财经要闻摘要（推送与正文顶部）")

            self.progress = 100
            self.result = result
            self.log("分析完成")
            self.status = "completed"
            ah_meta = getattr(data_fetcher, "_last_auction_meta", None) or {}
            if ah_meta.get("program_completed") and ah_meta.get("top_pool"):
                try:
                    append_daily_top_pool(actual_date, ah_meta["top_pool"])
                    self.log("龙头池已记入周度统计档案（data/watchlist_records.json）")
                except Exception as ex:
                    self.log(f"龙头池存档失败：{ex}")
            _cm = ConfigManager()
            if _cm.get("enable_daily_style_indices_persist", True):
                try:
                    from app.services.market_style_indices import persist_daily_indices

                    _td = data_fetcher.get_trade_cal()
                    if _td:
                        persist_daily_indices(data_fetcher, actual_date, _td)
                        self.log("风格指数已入库（data/market_style_indices.json）")
                except Exception as ex:
                    self.log(f"风格指数入库失败：{ex}")
            if _cm.get("enable_simulated_account", False) and ah_meta.get(
                "program_completed"
            ) and ah_meta.get("top_pool"):
                try:
                    from app.services.simulated_account import (
                        SimulatedAccount,
                        price_from_map,
                        price_map_from_top_pool,
                        recommendations_from_top_pool,
                    )
                    from app.services.strategy_preference import tag_to_bucket

                    tp = ah_meta["top_pool"]
                    pmap = price_map_from_top_pool(tp)
                    recs = recommendations_from_top_pool(
                        tp, tag_to_bucket_func=tag_to_bucket
                    )
                    acc = SimulatedAccount(
                        account_path=_cm.get(
                            "simulated_account_path", "data/simulated_account.json"
                        ),
                        config_path=_cm.get(
                            "simulated_config_path", "data/simulated_config.json"
                        ),
                        config_manager=_cm,
                    )
                    acc._cfg["buy_price_type"] = _cm.get(
                        "simulated_buy_price_type",
                        acc._cfg.get("buy_price_type", "close_of_recommendation_day"),
                    )
                    acc.update_prices(pmap)
                    _td = data_fetcher.get_trade_cal()
                    acc.execute_daily_trades(
                        recs,
                        actual_date,
                        lambda s: price_from_map(pmap, s),
                        trade_days=_td,
                    )
                    plan = acc.generate_daily_plan(actual_date)
                    result = result + "\n\n---\n\n" + plan
                    self.result = result
                    self.log("模拟账户已更新（见文末操作备忘）")
                except Exception as ex:
                    self.log(f"模拟账户更新失败：{ex}")
            sc_title = (
                f"✅ {sum_line} · {actual_date}"
                if sum_line
                else f"✅ 复盘完成 · {MODE_NAME} · {actual_date}"
            )
            ok, msg = send_serverchan(
                serverchan_sendkey,
                sc_title,
                result,
            )
            if ok and msg != "skipped":
                self.log("微信通知已发送（Server酱）")
            elif not ok:
                self.log(f"微信通知发送失败：{msg}")
            if email_cfg and has_email_config(email_cfg):
                subj = (
                    f"【复盘】✅ {sum_line} · {actual_date}"
                    if sum_line
                    else f"【复盘】✅ 复盘完成 · {MODE_NAME} · {actual_date}"
                )
                _kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
                _dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
                eok, emsg = send_report_email(
                    email_cfg,
                    subj,
                    result,
                    extra_vars={
                        "header_date": f"交易日 {actual_date}",
                        "title": subj,
                        "email_kpi": _kpi,
                        "email_dragon_meta": _dm,
                    },
                )
                if eok and emsg != "skipped":
                    self.log("邮件通知已发送")
                elif not eok:
                    self.log(f"邮件发送失败：{emsg}")
        except Exception as e:
            error_msg = f"❌ 复盘失败：{str(e)}"
            self.log(error_msg)
            self.result = error_msg
            self.status = "error"
            ok, msg = send_serverchan(
                serverchan_sendkey,
                f"❌ 复盘失败 · {MODE_NAME} · {actual_date}",
                error_msg,
            )
            if ok and msg != "skipped":
                self.log("失败通知已发送（Server酱）")
            elif not ok:
                self.log(f"微信通知发送失败：{msg}")
            if email_cfg and has_email_config(email_cfg):
                subj = f"【复盘】❌ 复盘失败 · {MODE_NAME} · {actual_date}"
                eok, emsg = send_report_email(
                    email_cfg,
                    subj,
                    error_msg,
                    extra_vars={
                        "header_date": f"交易日 {actual_date}",
                        "title": subj,
                    },
                )
                if eok and emsg != "skipped":
                    self.log("失败通知邮件已发送")
                elif not eok:
                    self.log(f"邮件发送失败：{emsg}")
        finally:
            data_fetcher.set_current_task(None)
