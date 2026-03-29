from datetime import datetime
import threading
from typing import Optional

import requests

from app.services.email_notify import has_email_config, send_report_email
from app.services.serverchan_notify import send_serverchan
from app.services.strategy_preference import build_prompt_addon
from app.services.watchlist_store import append_daily_top_pool
from app.utils.config import ConfigManager

ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-flash"  # 智谱免费模型
MAX_LOG_ENTRIES = 200

MODE_NAME = "次日竞价半路模式"


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
        "【摘要】市场阶段：震荡期｜适宜度：中｜置信度：低（系统补全：模型未输出规范首行摘要）\n\n"
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

    def build_prompt(self, date, market_data):
        """单一模式：次日竞价半路；市场数据中已含程序化选股与 AI 提示块。"""
        return f"""
你是专注 **{MODE_NAME}** 的 A 股短线策略分析师。模式含义：**收盘后**完成程序选股，**次日集合竞价至早盘**结合分时强弱考虑**半路介入**，非盲目顶板。

## 硬性规则（违反则视为不合格输出）
1. **必须与程序数据对齐**：程序给出的主线板块名称、龙头池标的（代码/名称/综合分排序）须优先采信；若你不认可，须**单独用一小段写清理由**，不得静默忽略。
2. **须响应「【AI 提示】」块**：其中提到的数据缺失、置信度、冲突标的（技术面 vs 主线强度）须在正文中**逐条回应**，可合并叙述，不可省略。
3. 若市场数据中含 **【财经要闻·与程序观察标的】**：择要在「市场阶段」或「主线与程序选股」中呼应**与主线/龙头池相关**的外围信息，勿逐条复述快讯全文。
4. **全文须为 Markdown**；下列章节标题、顺序不得删改（可在节内增删，但总篇幅不宜过长）。

## 输出结构（按顺序）

### 报告首行（单独一行，勿加其它前缀）
`【摘要】市场阶段：主升期/震荡期/退潮期｜适宜度：高/中/低｜置信度：高/中/低`
（「置信度」须综合数据完整性、程序是否跑完龙头池、上述冲突提示。）

### 1. 市场阶段与情绪（≤220 字）
- 阶段判断（三选一）+ **两条**量化依据（引用市场数据中的涨停/跌停/炸板率/溢价/北向等）。
- 建议仓位区间（百分比）。
- 本模式**适宜度**（高/中/低）一句话理由。

### 2. 主线与程序选股（≤500 字）
- **程序主线板块**：逐条表态是否认可（名称须与数据一致）。
- **龙头池前 3 名**（按程序综合分）：每只固定四行——**结论一句**；**逻辑**（人气/中军/活口与模式匹配度）；**风险一句**；**次日竞价关注点一句**。
- 若存在「【AI 提示】」中的**冲突标的**，须单独加一小段写清**参与或不参与**及条件。

### 3. 次日竞价半路预案
**观察清单**须用 **Markdown 表格**，列至少包含：| 优先级 | 代码 | 名称 | 标签 | 简要理由 |
（行数与程序龙头池对应，按综合分排序；可少于等于 5 行。）

**表格示例（内容须替换为真实标的，勿照抄示例）：**

| 优先级 | 代码 | 名称 | 标签 | 简要理由 |
|--------|------|------|------|----------|
| 1 | 600000 | 示例股份 | 人气龙头 | 程序综合分第一且与主线一致 |
| 2 | 000001 | 示例控股 | 活口核心 | 承接与换手健康 |

然后分条写：竞价关注（高开、量比、封单/抛压定性）、分时介入条件、价格与逻辑止损。

### 4. 风险与不适用场景（≤280 字）
- 个股 / 市场 / 模式特有风险（冲高回落、主线一日游等）。
- **不适用场景**：至少列出两类（如：系统性急跌、程序未完整产出龙头池、数据源异常日），并说明今日是否命中。

---

### 免责声明（单独一节，勿与上文混排）
> **免责声明**：以上分析基于公开数据与程序规则，仅供参考，不构成投资建议。股市有风险，投资需谨慎。

---
{build_prompt_addon()}
## 今日市场数据（程序选股 + 基础指标 + AI 提示）
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
            prompt = self.build_prompt(actual_date, market_data)
            result = self.call_zhipu(api_key, prompt)
            result = _ensure_summary_line(result)
            self.log("报告首行已校验（必要时已补全摘要行）")
            sum_line = _extract_summary_line(result)
            news_pre = (getattr(data_fetcher, "_last_news_push_prefix", None) or "").strip()
            if news_pre:
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
                    f"✅ {sum_line} · {actual_date}"
                    if sum_line
                    else f"✅ 复盘完成 · {MODE_NAME} · {actual_date}"
                )
                eok, emsg = send_report_email(email_cfg, subj, result)
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
                subj = f"❌ 复盘失败 · {MODE_NAME} · {actual_date}"
                eok, emsg = send_report_email(email_cfg, subj, error_msg)
                if eok and emsg != "skipped":
                    self.log("失败通知邮件已发送")
                elif not eok:
                    self.log(f"邮件发送失败：{emsg}")
        finally:
            data_fetcher.set_current_task(None)
