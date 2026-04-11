from datetime import datetime
import json
import threading
import time
from typing import Any, Optional

from app.utils.replay_viewpoint_footer import (
    append_replay_viewpoint_footer,
    replay_footer_inline_images,
)

import pandas as pd

from config.replay_prompt_templates import build_main_replay_prompt
from app.services.email_notify import has_email_config, send_report_email
from app.utils.email_template import truncate_finance_news_push_prefix
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
from app.services.llm_client import get_llm_client
from app.services.separation_confirmation import perform_separation_confirmation
from app.services.news_mapper import analyze_finance_news
from app.services.report_builder import append_core_stocks_and_plan_if_missing
from app.application.replay_text_rules import (
    ensure_dragon_report_sections as _ensure_dragon_report_sections,
    ensure_summary_line as _ensure_summary_line,
    extract_summary_line as _extract_summary_line,
    is_llm_failure_payload as _is_llm_failure_payload,
)
from app.domain.ports import EmailDeliveryPort, LLMCompletionPort
from app.output.replay_email_subject import (
    build_replay_failure_email_subject,
    build_replay_success_email_subject,
)

MAX_LOG_ENTRIES = 200

MODE_NAME = "次日竞价半路模式"


class ReplayTask:
    def __init__(
        self,
        *,
        llm_port: Optional[LLMCompletionPort] = None,
        email_port: Optional[EmailDeliveryPort] = None,
    ):
        self._llm_port = llm_port
        self._email_port = email_port
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
        news_mapping: str = "",
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
        
        separation_block = ""
        if separation_result:
            notes = separation_result.get("notes") or []
            if notes:
                separation_block += "\n## 【分离确认·说明】\n"
                for n in notes:
                    separation_block += f"- {n}\n"
            if separation_result.get("candidates"):
                separation_block += "\n## 【分离确认·候选】\n"
                ls = separation_result.get("leading_stock") or {}
                separation_block += "- 总龙头：{name}({code}) 连板{lb}\n".format(
                    name=ls.get("name", ""),
                    code=ls.get("code", ""),
                    lb=ls.get("lb", 0),
                )
                if separation_result.get("volatility_points"):
                    points = separation_result["volatility_points"]
                    separation_block += (
                        f"- 异动时间点：{len(points)} 个（{points[0]['type']}等）\n"
                    )
                separation_block += "- 分离确认候选（含判断依据）：\n"
                for i, candidate in enumerate(
                    separation_result["candidates"][:5], 1
                ):
                    separation_block += (
                        f"  {i}. {candidate['name']}({candidate['code']}) "
                        f"得分：{candidate.get('separation_score', 0):.2f}\n"
                    )
                    if candidate.get("remark"):
                        separation_block += f"     备注：{candidate['remark']}\n"
        
        # 添加要闻映射
        news_block = news_mapping if news_mapping else ""
        
        return build_main_replay_prompt(
            mode_name=MODE_NAME,
            date=str(date),
            market_data=market_data,
            addon=addon,
            meta_block=meta_block + separation_block + news_block,
        )

    def call_llm(self, api_key, prompt, temperature=0.42, max_tokens=6144):
        """调用大模型（默认 DeepSeek Chat API；可注入 llm_port 便于测试或换实现）。"""
        if self._llm_port is not None:
            return self._llm_port.complete(
                prompt, temperature=temperature, max_tokens=max_tokens
            )
        client = get_llm_client(api_key)
        return client.chat_completion(
            prompt, temperature=temperature, max_tokens=max_tokens
        )

    def _send_report_email(
        self,
        email_cfg: dict,
        subject: str,
        body: str,
        *,
        extra_vars: Optional[dict[str, Any]] = None,
        inline_images: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[bool, str]:
        if self._email_port is not None:
            return self._email_port.send_markdown_report(
                email_cfg,
                subject,
                body,
                extra_vars=extra_vars,
                inline_images=inline_images,
            )
        return send_report_email(
            email_cfg,
            subject,
            body,
            extra_vars=extra_vars,
            inline_images=inline_images,
        )

    def run(self, date, api_key, data_fetcher, email_cfg=None):
        actual_date = date
        _t0 = time.monotonic()
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
                    zrec = bundle.get("zt_pool_records")
                    if zrec:
                        try:
                            data_fetcher._last_zt_pool = pd.DataFrame(zrec)
                        except Exception:
                            pass
                    actual_date = str(date)[:8]
                    self.log("断点续跑：已加载市场摘要与程序缓存（跳过 get_market_summary）")
                    self.progress = 90

            if market_data is None:
                self.log("正在获取市场数据与次日竞价半路选股…")
                market_data, actual_date = data_fetcher.get_market_summary(date)
                self.log(f"阶段 get_market_summary 耗时 {time.monotonic() - _t0:.1f}s")
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
            
            # 执行分离确认分析（断点续跑时可能未经过 get_market_summary，须补拉涨停池）
            try:
                df_zt = getattr(data_fetcher, "_last_zt_pool", None)
                _need_zt = df_zt is None or (
                    hasattr(df_zt, "empty") and bool(df_zt.empty)
                )
                if _need_zt:
                    df_zt = data_fetcher.get_zt_pool(actual_date)
                    if df_zt is not None and not getattr(df_zt, "empty", True):
                        data_fetcher._last_zt_pool = df_zt.copy()
                if df_zt is not None and not getattr(df_zt, "empty", True):
                    _td = data_fetcher.get_trade_cal()
                    if _td:
                        separation_result = perform_separation_confirmation(
                            actual_date, df_zt, _td
                        )
                        if separation_result and separation_result.get("candidates"):
                            self.log(
                                "分离确认完成，找到 "
                                f"{len(separation_result['candidates'])} 个候选股"
                            )
            except Exception as ex:
                self.log(f"分离确认分析失败：{ex}")
            
            # 执行要闻映射分析
            news_mapping = ""
            try:
                finance_news = getattr(data_fetcher, "_last_finance_news", [])
                if finance_news:
                    ah_meta = getattr(data_fetcher, "_last_auction_meta", None) or {}
                    news_mapping = analyze_finance_news(
                        finance_news,
                        top_pool=ah_meta.get("top_pool"),
                    )
                    if news_mapping:
                        self.log("要闻映射分析完成")
            except Exception as ex:
                self.log(f"要闻映射分析失败：{ex}")
            
            # 风格稳定性探测（可选；与主长文各一次大模型调用，连发易 429）
            _cm2 = ConfigManager()
            if _cm2.get("enable_style_stability_probe", False):
                try:
                    stab = probe_style_stability(api_key, market_data)
                    stab_hint = stab
                    base = load_strategy_preference().get("strategy_weights") or {}
                    eff_w = effective_weights_from_stability(stab, dict(base))
                    self.log(f"风格稳定性探测：{stab}")
                except Exception as ex:
                    self.log(f"风格稳定性探测失败（沿用文件权重）：{ex}")
                gap = float(_cm2.get("replay_llm_spacing_sec", 15) or 0)
                if gap > 0:
                    self.log(
                        f"大模型调用间隔：等待 {gap:.0f}s 后再请求主长文（降低 429 限速概率）"
                    )
                    time.sleep(gap)

            # 构建prompt
            prompt = self.build_prompt(
                actual_date,
                market_data,
                effective_weights=eff_w,
                stability_hint=stab_hint,
                dragon_meta=getattr(data_fetcher, "_last_dragon_trader_meta", None) or {},
                separation_result=separation_result,
                news_mapping=news_mapping,
            )
            _t_ai = time.monotonic()
            result = self.call_llm(api_key, prompt)
            self.log(f"阶段 llm_chat 耗时 {time.monotonic() - _t_ai:.1f}s")
            # 从 data_fetcher 获取市场阶段，确保摘要一致性
            market_phase = getattr(data_fetcher, "_last_market_phase", "高位震荡期")
            result = _ensure_summary_line(result, market_phase)
            if not _is_llm_failure_payload(result):
                _cm_rb = ConfigManager()
                result = append_core_stocks_and_plan_if_missing(
                    result,
                    actual_date=actual_date,
                    data_fetcher=data_fetcher,
                    api_key=api_key,
                    enable=bool(
                        _cm_rb.get("enable_report_builder_core_stocks_plan", True)
                    ),
                    use_llm=bool(_cm_rb.get("enable_report_core_stocks_llm", False)),
                )
            result = _ensure_dragon_report_sections(result)
            if _is_llm_failure_payload(result):
                self.log("大模型未返回正文（限速/余额/网络等），已附加说明；请勿将「缺章节」提示理解为模型漏写")
            else:
                self.log("报告首行与龙头模板章节已校验（必要时已补全/提示）")
                _cm_en = ConfigManager()
                main_report_for_qc = result
                _en_main = bool(_cm_en.get("enable_replay_llm_enhancements", True))
                _en_qc = bool(_cm_en.get("enable_replay_llm_chapter_qc", True))
                _en_cmp = bool(_cm_en.get("enable_replay_llm_comparison_narrative", True))
                _en_news = bool(_cm_en.get("enable_replay_llm_news_deep", True))
                if _en_main or _en_qc or _en_cmp or _en_news:
                    try:
                        from app.services.replay_llm_enhancements import (
                            collect_program_facts_snapshot,
                            run_replay_chapter_quality,
                            run_replay_comparison_narrative,
                            run_replay_deepseek_enhancements,
                            run_replay_news_event_chain,
                        )

                        gap_en = float(
                            _cm_en.get("replay_llm_enhancements_spacing_sec", 8) or 0
                        )
                        if _en_main and gap_en > 0:
                            self.log(
                                f"DeepSeek 增强块前等待 {gap_en:.0f}s（降低连发限速）"
                            )
                            time.sleep(gap_en)
                        pf = collect_program_facts_snapshot(
                            actual_date,
                            market_data,
                            data_fetcher,
                            separation_result,
                        )
                        if _en_main:
                            mt = int(
                                _cm_en.get("replay_llm_enhancements_max_tokens", 6144)
                                or 6144
                            )
                            extra = run_replay_deepseek_enhancements(
                                api_key,
                                actual_date,
                                pf,
                                result,
                                max_tokens=mt,
                            )
                            result = result + extra
                            self.log("DeepSeek 增强块已附加")
                        gap_x = float(_cm_en.get("replay_llm_extra_spacing_sec", 8) or 0)
                        if _en_qc:
                            if gap_x > 0:
                                time.sleep(gap_x)
                            result = result + run_replay_chapter_quality(
                                api_key,
                                actual_date,
                                pf,
                                main_report_for_qc,
                            )
                            self.log("章节质控（周期/明日）已附加")
                        if _en_cmp:
                            if gap_x > 0:
                                time.sleep(gap_x)
                            result = result + run_replay_comparison_narrative(
                                api_key,
                                actual_date,
                                market_data,
                            )
                            self.log("近5日变化叙事已附加")
                        if _en_news:
                            rel_n = getattr(
                                data_fetcher, "_last_finance_news_related", None
                            ) or []
                            gen_n = getattr(
                                data_fetcher, "_last_finance_news_general", None
                            ) or []
                            if rel_n or gen_n:
                                if gap_x > 0:
                                    time.sleep(gap_x)
                                mi = int(_cm_en.get("email_news_max_items", 3) or 3)
                                result = result + run_replay_news_event_chain(
                                    api_key,
                                    actual_date,
                                    data_fetcher,
                                    max_items_push=mi,
                                )
                                self.log("要闻深化（事件链）已附加")
                    except Exception as ex:
                        self.log(f"DeepSeek 增强块失败：{ex}")
            try:
                from app.services.historical_matcher import append_historical_similarity_block

                result = append_historical_similarity_block(
                    result, data_fetcher, actual_date
                )
            except Exception as ex:
                self.log(f"历史相似形态回溯附加失败：{ex}")

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

            result = append_replay_viewpoint_footer(result)

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
            if email_cfg and has_email_config(email_cfg):
                subj = build_replay_success_email_subject(
                    summary_line=sum_line,
                    trade_date=str(actual_date),
                    mode_name=MODE_NAME,
                )
                _kpi = getattr(data_fetcher, "_last_email_kpi", None) or {}
                _dm = getattr(data_fetcher, "_last_dragon_trader_meta", None) or {}
                _title_tpl = str(
                    _cm.get("report_title_template")
                    or "T+0 竞价复盘 · 对 {trade_date} 的复盘"
                )
                _banner = _title_tpl.replace("{trade_date}", str(actual_date))
                eok, emsg = self._send_report_email(
                    email_cfg,
                    subj,
                    result,
                    extra_vars={
                        "header_date": f"交易日 {actual_date}",
                        "title": subj,
                        "report_banner_title": _banner,
                        "system_name": str(
                            _cm.get("email_system_name") or "T+0 竞价复盘系统"
                        ),
                        "email_kpi": _kpi,
                        "email_dragon_meta": _dm,
                    },
                    inline_images=replay_footer_inline_images(),
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
            if email_cfg and has_email_config(email_cfg):
                subj = build_replay_failure_email_subject(
                    mode_name=MODE_NAME,
                    trade_date=str(actual_date),
                )
                eok, emsg = self._send_report_email(
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
