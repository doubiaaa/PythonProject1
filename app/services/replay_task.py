from datetime import datetime
import json
import threading
from typing import Any, Optional

import requests

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

ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
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
    ):
        """
        龙头短线选手复盘模板 + 次日竞价半路程序约束。
        dragon_meta：程序侧结构化快照（连板梯队、大面数等），供引用。
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
        return f"""
你是一位资深的**龙头短线交易员**视角的 A 股分析师，同时须遵守本系统的 **{MODE_NAME}** 程序约束：
模式含义：**收盘后**完成程序选股，**次日集合竞价至早盘**可结合分时强弱考虑**半路介入**，非盲目顶板。

## 硬性规则（违反则视为不合格输出）
1. **必须与程序数据对齐**：程序给出的主线板块、**龙头池**（代码/名称/综合分排序）、「龙头选手·程序量化快照」中的数据须优先采信；不认可须**单独写清理由**，不得静默忽略。
2. **须完整响应「【AI 提示】」块**（若市场数据中有）：数据缺失、置信度、冲突标的等须**逐条回应**，可合并叙述。
3. 若含 **【财经要闻·与程序观察标的】**：仅在「周期定性 / 核心股聚焦」中**择要呼应**与主线/龙头池相关的外围信息，勿逐条复述快讯。
4. **全文 Markdown**；下列**章节标题（含「### 一、」…「### 七、」）须全部出现**，顺序不得打乱；节内篇幅可控制，但总结构不可删。

### 报告首行（单独一行）
`【摘要】周期阶段：主升期/高位震荡期/退潮·冰点期/混沌·试错期｜适宜度：高/中/低｜置信度：高/中/低`
（周期阶段须与下文「一、周期定性」一致；置信度综合数据完整性、龙头池是否完整、AI 提示风险。）

### 一、周期定性（核心）
- 判断当前市场处于：**主升期 / 高位震荡期 / 退潮·冰点期 / 混沌·试错期**（四选一或说明过渡）。
- **判断依据**：必须引用程序数据中的连板高度、涨停家数、**大面数**、昨日涨停溢价、炸板率、涨跌家数等中的至少三项。
- **总仓位上限建议**：重仓（≥6 成）/ 轻仓（约 2～4 成）/ 空仓或极轻仓；并与 {MODE_NAME} 的次日半路节奏相匹配。

### 二、情绪数据量化（简洁卡片）
用列表或表格概括（数据以程序块为准，勿编造）：
- 涨跌家数（若程序提供）、涨停家数、**连板梯队**（2 板×N、3 板×N…）、炸板率、**大面数**、昨日涨停溢价（若有首板/连板拆分须引用）。
- **结论**：赚钱效应（强/中/弱）与亏钱效应是否扩散。

### 三、核心股聚焦
- **总龙头**：当日市场**最高连板**标的（代码、名称、连板数），今日走势（加速/分歧/断板），明日预期。
- **板块龙**：最多 3 个主流题材及其领涨股（与程序主线/龙头池对齐）。
- **中位股风险**：昨日 **3～4 连板** 今日是否断板、跌停或大面（引用程序「中位股」小节）。
- **分离确认**：若程序提供了「分离确认·候选」，须点评其补涨/卡位意义；若无分时数据，须说明不可臆测盘口。

### 四、交易回溯（模拟账户 / 纪律）
- 若市场数据末含模拟账户备忘或持仓，则逐笔对照模式；若无持仓数据，则写「无程序持仓则本节从简」并强调纪律。

### 五、明日预案（三种剧本）
- **超预期**：核心龙头高开高走时的应对。
- **符合预期**：震荡、分化时的应对。
- **不及预期**：低开低走、中位核按钮时的应对。
- **新方向**：新题材是否可能卡位；与旧周期仓位如何切换。

### 六、备选标的（仅限 1～2 只）
须与程序 **龙头池** 对齐或说明为何不选池内标的；表格含：代码、名称、标签、**买入条件**（可执行、可观察）。

### 七、风险提示
- 市场、个股、模式特有风险；不适用场景至少两类。

---

### 免责声明（单独一节）
> **免责声明**：以上分析基于公开数据与程序规则，仅供参考，不构成投资建议。股市有风险，投资需谨慎。

---
{addon}
{meta_block}
## 今日市场数据（程序选股 + 基础指标 + 龙头量化 + AI 提示）
交易日：{date}

{market_data}
"""

    def call_zhipu(self, api_key, prompt, temperature=0.42, max_tokens=6144):
        """调用智谱API"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = requests.post(ZHIPU_API_URL, headers=headers, json=data, timeout=120)
            if response.status_code == 200:
                result = response.json()
                choices = result.get("choices") or []
                if not choices:
                    return "API 返回异常：无 choices 字段"
                msg = (choices[0].get("message") or {}).get("content")
                if msg is None:
                    return "API 返回异常：无 content"
                return msg
            else:
                if response.status_code == 402:
                    return "错误：智谱API账户余额不足，请充值后重试。"
                return f"API请求失败（{response.status_code}）：{response.text}"
        except Exception as e:
            return f"调用智谱API异常：{str(e)}"

    def run(self, date, api_key, data_fetcher, serverchan_sendkey=None, email_cfg=None):
        actual_date = date
        try:
            data_fetcher.set_current_task(self)

            self.progress = 10
            self.log("正在获取市场数据与次日竞价半路选股…")

            market_data, actual_date = data_fetcher.get_market_summary(date)
            self.progress = 90

            if actual_date != date:
                self.log(f"日期已自动调整为交易日: {actual_date}")

            self.progress = 95
            self.log("数据获取完成，正在调用AI…")
            eff_w = None
            stab_hint = ""
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
            prompt = self.build_prompt(
                actual_date,
                market_data,
                effective_weights=eff_w,
                stability_hint=stab_hint,
                dragon_meta=getattr(data_fetcher, "_last_dragon_trader_meta", None)
                or {},
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
                eok, emsg = send_report_email(
                    email_cfg,
                    subj,
                    result,
                    extra_vars={
                        "header_date": f"交易日 {actual_date}",
                        "title": subj,
                        "email_kpi": _kpi,
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
