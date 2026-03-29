# 项目架构说明

本文描述「次日竞价半路」系统的模块职责、数据流与数据文件关系，便于维护与扩展。

---

## 1. 定位与分工

本仓库是一个 **B/S 架构** 的 A 股 **收盘后复盘 → 次日竞价预案** 工具：程序侧拉行情、选股与指标，将结构化「市场摘要 + 龙头池」交给 **智谱 GLM** 生成长文报告。

核心分工可以概括为：

> **程序算清量，模型写得像。**

量化与规则在 `DataFetcher`、策略模块与持久化中完成；大模型负责按固定结构输出可读、可推送的复盘文案。

---

## 2. 运行时入口

| 入口 | 说明 |
|------|------|
| `run.py` | 启动 Flask（默认 `0.0.0.0:5000`），提供网页与 `/api/*`。 |
| `scripts/nightly_replay.py` | 定时任务：指定日或「北京时间当日」为交易日时执行完整复盘，再走 Server酱 / 邮件。 |
| `scripts/weekly_performance_email.py` | 周末：周表现邮件、可选智谱周评、策略权重更新、异常提醒、`--plot` 权重图。 |
| `scripts/backtest_weights.py` | 占位：离线回测权重参数（待扩展）。 |

配置通过 `replay_config.json`（`ConfigManager`）与环境变量（如 `ZHIPU_API_KEY`）；密钥优先级一般为 **环境变量 > 配置文件**。

---

## 3. Web 交互流程

1. 用户访问 `templates/index.html`，提交复盘日、智谱 Key 等，POST **`/api/start_replay`**（`app/routes/main.py`）。
2. 校验参数、`ReplayTask.try_begin()` 防并发，后台线程执行 **`ReplayTask.run`**。
3. 前端轮询 **`/api/task_status`**；可选 SMTP / Server酱 在任务结束时推送或发信。

核心任务类：`app/services/replay_task.py`。

---

## 4. 单次复盘流水线

### 4.1 数据与程序选股（`DataFetcher`）

- `app/services/data_fetcher.py`：通过 akshare 等获取交易日历、行情、涨停/跌停/炸板、板块资金、北向、溢价等。
- 结合 `auction_halfway_strategy`、`trend_momentum_strategy` 等产出 **主线板块** 与 **龙头池 `top_pool`**（代码、名称、标签、技术分等），拼成 Markdown 形态的「今日市场数据」。
- 可选：财联社要闻等，按龙头关键词摘要后附在报告前（受配置控制）。
- 程序未完成或异常时，meta 中可带 `abort_reason`，prompt 要求模型降置信度说明。

### 4.2 策略偏好（闭环权重）

- `app/services/strategy_preference.py` 维护 `data/strategy_preference.json`：五桶（打板 / 低吸 / 趋势 / 龙头 / 其他）**动态权重**，由周度收益反馈更新。
- `build_prompt_addon` 将当前有效权重与写作侧重写入 prompt，引导模型在结构上偏向某类风格（仍须覆盖程序给出的龙头池）。

### 4.3 可选：风格稳定性探测

- 配置开启时，在主线智谱调用前增加轻量调用：`probe_style_stability` → `effective_weights_from_stability`，用于在风格拐点附近折中或均匀化权重。

### 4.4 主模型与输出

- `ReplayTask.build_prompt`：固定输出结构（摘要、主线、表格、竞价预案、风险、免责声明等）+ 策略 addon + 市场数据。
- `call_zhipu` 调用智谱 API；对返回做摘要行等校验，便于推送标题解析。

### 4.5 持久化与通知

- 成功时将当日程序 `top_pool` 写入 **`data/watchlist_records.json`**（`watchlist_store.append_daily_top_pool`），供周度统计与权重更新；与 AI 正文解耦。
- `serverchan_notify` / `email_notify`：推送与 HTML 邮件。

---

## 5. 周度与闭环

- `app/services/weekly_performance.py`：按自然周与锚点交易日，对 `watchlist_records` 计算区间收益与标签归因，生成周报 Markdown。
- `scripts/weekly_performance_email.py`：在开启 `enable_strategy_feedback_loop` 时调用 `update_from_recent_returns`（多周衰减、样本门槛、平滑与上下限、大幅变动惩罚等），写回 `strategy_preference.json` 并追加 `strategy_evolution_log.jsonl`；可选异常邮件与权重趋势图。
- `weekly_market_snapshot.py`、`market_style_indices.py`：为周报提供市场快照与风格指数等辅助内容。

---

## 6. 数据文件关系

| 文件 | 作用 |
|------|------|
| `data/watchlist_records.json` | 每日程序龙头池快照 → 周度收益与归因的输入。 |
| `data/strategy_preference.json` | 五桶权重与生效说明 → 次日复盘 prompt 的动态侧重。 |
| `data/strategy_evolution_log.jsonl` | 权重演进审计日志 → 可视化与未来回测。 |

---

## 7. 测试与脚本

- `tests/`：周报归因、策略偏好、风格指数、新闻摘要等。
- `scripts/notify_failure.py` 等：运维辅助。

---

## 8. 后续优化方向（讨论备忘）

以下方向与「持续迭代、控制风险」相关，尚未全部实现；落地时可拆成独立任务（配置项 + 函数签名 + 单测）。

1. **周内风格再校准**：在周中增加轻量统计，将「周内调整因子」与文件权重混合，仅作用于当日/次日 prompt，不写入 `strategy_preference.json`，以缓解「权重仅周更」带来的滞后。
2. **稳定性探测的成本与触发**：对 `probe_style_stability` 增加缓存与规则触发（如炸板率、连板高度等突变再探测）；稳定性除影响权重外，可进一步调节 prompt 中「侧重强度」与风险提示篇幅。
3. **标签仲裁**：当程序侧存在多标签冲突时，按优先级归入单一风格桶，并在存档中保留原始标签与最终桶，提高收益归因信噪比。
4. **未完结信号处理**：周度归因时对「当周末尾才发出、持仓不足一周」的信号标记 `incomplete` 或滚动至下周，避免区间与推荐滞后错配。
5. **离线回测**：在 `backtest_weights.py` 中基于 `strategy_evolution_log.jsonl` 与历史收益网格搜索平滑系数等参数。

---

*文档版本随代码演进更新；核心流水线以 `replay_task.py`、`data_fetcher.py`、`strategy_preference.py`、`weekly_performance.py` 为准。*
