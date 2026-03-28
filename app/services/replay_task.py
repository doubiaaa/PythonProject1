from datetime import datetime
import threading
import requests

from app.services.serverchan_notify import send_serverchan

ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-flash"  # 智谱免费模型
MAX_LOG_ENTRIES = 200

MODE_NAME = "次日竞价半路模式"


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
        """单一模式：次日竞价半路；市场数据中已含程序化选股结果。"""
        return f"""
你是一位专注 **{MODE_NAME}** 的 A 股短线策略分析师。该模式含义：在 **收盘后完成选股**，次日以 **集合竞价至早盘** 的强弱与承接为信号，在 **分时确认** 后考虑 **半路（追涨）** 介入，而非盲目顶板。

【策略要点（须与下方程序输出对照）】
1. **主线板块**：近 5 个交易日行业涨幅多次位居前列、成交额居前、板块内有强势龙头。
2. **龙头池**：区分人气龙头（高连板+换手）、趋势中军（大市值+均线多头）、活口核心（强于板块指数+放量）。
3. **评分**：主线强度、龙头地位、次日预期 K 线/涨幅结构、流动性（换手健康度）四维度加权。
4. **次日执行**：重视竞价量能、高开/低开后的分时弱转强；不追高无承接品种。

请严格依据用户提供的「市场数据」中的 **{MODE_NAME}** 程序化结果，结合基础情绪指标，输出 Markdown 报告。

## 1. 市场阶段判断
- 当前市场阶段：（主升期/震荡期/退潮期）
- 判断依据：（情绪温度、涨停溢价、炸板率、北向等）
- 建议仓位：（百分比区间）
- 对「次日竞价半路」的适宜度：（高/中/低及理由）

## 2. 主线与程序选股结果解读
- 是否认可程序筛出的主线板块（1～2 个）及理由
- 对龙头池标的逐一简评：是否符合该模式（人气/中军/活口）
- 程序得分靠前标的中，谁更值得关注次日竞价

## 3. 次日竞价半路预案
- 观察清单：（代码+名称，按优先级排序）
- 竞价关注点：（高开幅度、量比、封单/抛压等，定性即可）
- 分时介入条件：（例如：回踩分时均线不破、放量突破开盘高点等）
- 止损纪律：（价格或逻辑止损）

## 4. 风险预警
- 个股风险
- 市场风险
- 该模式特有风险（冲高回落、主线一日游等）

---
今日市场数据（含程序选股输出）：
{market_data}

**免责声明**：以上分析基于公开数据与程序规则，仅供参考，不构成投资建议。股市有风险，投资需谨慎。
"""

    def call_zhipu(self, api_key, prompt, temperature=0.7, max_tokens=4000):
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

    def run(self, date, api_key, data_fetcher, serverchan_sendkey=None):
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

            self.progress = 100
            self.result = result
            self.log("分析完成")
            self.status = "completed"
            ok, msg = send_serverchan(
                serverchan_sendkey,
                f"✅ 复盘完成 · {MODE_NAME} · {actual_date}",
                result,
            )
            if ok and msg != "skipped":
                self.log("微信通知已发送（Server酱）")
            elif not ok:
                self.log(f"微信通知发送失败：{msg}")
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
        finally:
            data_fetcher.set_current_task(None)
