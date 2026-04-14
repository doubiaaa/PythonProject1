# T+0 竞价复盘 · A 股收盘智能简报

本仓库是一套**命令行驱动的 A 股收盘复盘流水线**：在**当日收盘后**拉取交易日历、涨跌停池、板块与资金流等，按「**次日竞价半路**」策略（`auction_halfway_strategy`）生成**主线、龙头池（`top_pool`）**、市场阶段与篇首程序目录；再调用 **DeepSeek**（OpenAI 兼容 `chat/completions`）按固定章节输出 Markdown 长文，并由程序校验摘要与龙头模板章节，必要时补全「五、核心股聚焦」「七、明日预案」等；定稿后追加要闻前缀、文末「五人理论」温习区，并可选 **SMTP 邮件**投递。

**设计原则**：程序算清量、模型写得像——数据块与 KPI 和 Prompt、邮件同一口径。系统**无 Web 前端**（`run.py` 仅提示已移除 Flask，退出码 2）。

> **声明**：输出仅供研究或自用记录，不构成投资建议。程序不对第三方数据源（如 akshare）的准确性、实时性作担保。  
> **维护**：实现细节以源码与 `tests/` 为准；模块边界与排错见 **`ARCHITECTURE.md`**；分层演进目标见 **`docs/six_layer_architecture.md`**。

---

## 目录

1. [快速开始](#快速开始)  
2. [核心理念与术语](#核心理念与术语)  
3. [技术栈与依赖](#技术栈与依赖)  
4. [仓库结构（与代码布局）](#仓库结构与代码布局)  
5. [业务全景：日度与周度](#业务全景日度与周度)  
6. [日度复盘流水线](#日度复盘流水线)  
7. [能力与模块索引](#能力与模块索引)  
8. [数据获取与策略核心](#数据获取与策略核心)  
9. [大模型客户端](#大模型客户端)  
10. [复盘增强包与 LLM 智能层（代码现状）](#复盘增强包与-llm-智能层代码现状)  
11. [邮件与模板](#邮件与模板)  
12. [文末温习与绘图脚本](#文末温习与绘图脚本)  
13. [持久化与路径](#持久化与路径)  
14. [周度闭环与策略偏好](#周度闭环与策略偏好)  
15. [配置说明](#配置说明)  
16. [环境变量](#环境变量)  
17. [脚本一览](#脚本一览)  
18. [测试、CI、GitHub Actions](#测试cigithub-actions)  
19. [部署](#部署)  
20. [辅助文档](#辅助文档)

---

## 快速开始

**环境**：Python **3.10+**（CI 使用3.11）。

```bash
pip install -r requirements.txt
```

**最小运行**（需 `DEEPSEEK_API_KEY` 或 `replay_config.json` 中的 key）：

```bash
python scripts/nightly_replay.py
python scripts/nightly_replay.py --date 20260328
```

非交易日且未指定 `--date` 时，`nightly_replay.py` 会跳过复盘并成功退出（退出码 0），适合定时任务。

**配置文件**：项目根 **`replay_config.json`**（可选）。合并规则见下文 [配置说明](#配置说明)。也可用环境变量 **`REPLAY_CONFIG_FILE`** 指向其他路径。

**健康检查**：

```bash
python scripts/validate.py
python scripts/health_check.py
```

---

## 核心理念与术语

| 术语 | 含义 |
|------|------|
| **龙头池 / top_pool** | `auction_halfway_strategy` 按规则输出的程序观察列表，非投资建议。 |
| **信号日** | 复盘成功且 `program_completed` 时写入 `watchlist_records.json` 的交易日。 |
| **五桶权重** | 打板、低吸、趋势、龙头、其他；存于 `strategy_preference.json`，经 `build_prompt_addon` 注入主复盘 Prompt。 |
| **自然周** | 周报以 ISO 周与锚点交易日组织（`weekly_performance.py`）。 |
| **市场阶段** | `compute_short_term_market_phase` 四象限文案；与正文【摘要】及 §1.2 须对齐。 |
| **建议仓位（程序）** | `position_sizer.calc_position` 给出的区间字符串，非固定百分比。 |
| **情绪量化评分** | `sentiment_scorer.calculate_sentiment_score`（0～10），辅助刻度。 |
| **大面** | 昨日涨停今日跌超 **-5%** 或跌停计数；与 KPI、§1.2 一致。 |

---

## 技术栈与依赖

| 类别 | 说明 |
|------|------|
| 语言 | Python 3.10+（CI 3.11） |
| 数据 | **pandas**、**akshare**；`get_market_summary` 可 **ThreadPoolExecutor** 并行（`market_summary_parallel_fetch`） |
| 缓存 | `disk_cache`（默认 `data/api_cache/`）、`price_cache`；可选启动时按 mtime 清扫（`disk_cache_sweep_ttl_sec`） |
| 大模型 | **requests**；**tenacity** 传输重试；HTTP **429** 业务层指数退避 |
| 邮件 | SMTP；**markdown** + **Jinja2**（`email_template`） |
| 配置 | `app/infrastructure/config_defaults.py` → **`DEFAULT_CONFIG`**；经 **`app/infrastructure/unified_config.py`** 与 **`app/utils/config.py`** 加载 |
| 质量 | **pytest**、`scripts/validate.py`；CI 额外 **`pip install ruff`** 对部分路径做静态检查 |

**`requirements.txt`**：`akshare`、`pandas`、`requests`、`markdown`、`pygments`、`jinja2`、`beautifulsoup4`、`pytest`、`matplotlib`、`tenacity`。

---

## 仓库结构与代码布局

| 路径 | 说明 |
|------|------|
| **`app/services/`** | 核心业务：`data_fetcher`、`replay_task`、`auction_halfway_strategy`、`replay_catalog`、`report_builder`、KPI/情绪/仓位/连板统计、邮件通知、LLM 客户端、周报与策略偏好等 |
| **`app/adapters/`** | 外系统适配：如 `email_smtp_adapter`、`llm_deepseek_adapter`、`market_summary_adapter` |
| **`app/application/`** | 应用用例：`replay_text_rules`（摘要与龙头章节规则）、**`llm_intel/`**（审计与结构化决策流水线，见下文） |
| **`app/domain/`** | `models`、`ports`（如 `LLMCompletionPort`、`EmailDeliveryPort`） |
| **`app/orchestration/`** | `replay_pipeline.py`：`REPLAY_PIPELINE_PHASES` 与 `ReplayTask.run` 步骤对齐 |
| **`app/output/`** | 输出侧组装：如 `replay_email_subject`（邮件主题） |
| **`app/infrastructure/`** | `config_defaults`、`unified_config`、`validation`、**`resilience/`**（熔断、`safe_execute`）、**`observability/`**（日志、事件、告警） |
| **`app/utils/`** | `config`、`logger`、`email_template`、`disk_cache`、`replay_viewpoint_footer`、`output_formatter` 等 |
| **`config/`** | `replay_prompt_templates.py`、`data_source_config.py`、`strategy_preference_config.py` |
| **`scripts/`** | 可执行入口与辅助脚本 |
| **`tests/`** | pytest |
| **`.github/workflows/`** | `ci.yml`、`scheduled-nightly.yml`、`weekly-report.yml`、`weekly-theory-review.yml`、`deploy.yml` |
| **`docs/`** | 如 `smtp_env.md`、`six_layer_architecture.md` |

---

## 业务全景：日度与周度

| 主线 | 主要环节 |
|------|----------|
| **日度复盘** | `get_market_summary` → 断点（可选）→ 分离确认、要闻映射 → 风格探测（可选）→ `build_prompt` / `call_llm` → 摘要与章节规则 → 五/七补全（可选）→ 要闻前缀 → 文末温习 → 龙头池与风格指数持久化 → SMTP |
| **周度闭环** | `weekly_performance_email.py`：周报 Markdown → 可选 LLM 附录 → `update_from_recent_returns` → 权重异常邮件与周报 SMTP |

**衔接**：日度 **watchlist**供周报统计；周末 **五桶权重** 经 `build_prompt_addon` 反馈日度 Prompt。

可选流程图：`python scripts/generate_readme_business_overview_chart.py` → `assets/readme_business_overview.png`（邮件正文不依赖该图）。

---

## 日度复盘流水线

编排阶段名见 **`app/orchestration/replay_pipeline.py`**（`REPLAY_PIPELINE_PHASES`），与 **`ReplayTask.run`**（`app/services/replay_task.py`）主路径一致。

| 顺序 | 行为 |
|------|------|
| 1 | **`resume_replay_if_available`** 且 **`enable_replay_checkpoint`**：尝试加载断点，恢复 fetcher 缓存字段，**跳过** `get_market_summary`。 |
| 2 | 否则 **`data_fetcher.get_market_summary(date)`**，得到 `market_data` 与 `actual_date`。 |
| 3 | 断点开启时 **`save_fetcher_bundle`** → `data/replay_status/{date}_market.txt`、`_meta.json`。 |
| 4 | **分离确认**：必要时补拉涨停池，**`perform_separation_confirmation`**。 |
| 5 | **要闻映射**：**`analyze_finance_news`**（带 `top_pool`）。 |
| 6 | **风格稳定性探测**（`enable_style_stability_probe`，默认关）：**`probe_style_stability`** → **`effective_weights_from_stability`**；**`replay_llm_spacing_sec`** 睡眠后主文。 |
| 7 | **`build_prompt`**：`build_prompt_addon`、dragon JSON、分离块、要闻块、**`MAIN_REPLAY_PROMPT`**。 |
| 8 | **`call_llm`** → **`ensure_summary_line`** → **`append_core_stocks_and_plan_if_missing`**（`enable_report_builder_core_stocks_plan` / `enable_report_core_stocks_llm`）→ **`ensure_dragon_report_sections`**。 |
| 9 | 截断并前置 **`_last_news_push_prefix`**。 |
| 10 | **`append_replay_viewpoint_footer`**（表格式五人理论 + 附录）。 |
| 11 | **`program_completed` 且 top_pool**：**`append_daily_top_pool`**。 |
| 12 | **`enable_daily_style_indices_persist`**：**`persist_daily_indices`**。 |
| 13 | **`send_report_email`**（若配置了 SMTP）。 |

注入端口：**`ReplayTask`** 可传入 **`llm_port`**、**`email_port`**（`app/domain/ports.py`），便于测试或替换实现。

---

## 能力与模块索引

| 能力 | 模块 |
|------|------|
| 昨日涨停溢价分档 | `market_kpi.premium_analysis` |
| 大面 / 亏钱效应 | `DataFetcher.compute_big_face_count`、`market_kpi.big_loss_metrics` |
| 要闻过滤 | `news_fetcher`相关性打分、`filter_news` |
| 连板梯队文本条 | `output_formatter.draw_text_bar` |
| 建议仓位 | `position_sizer.calc_position` |
| 明日情绪推演 | `cycle_analyzer.sentiment_forecast` |
| 连板晋级率表 | `ladder_stats.compute_promotion_rates_md` |
| 五/七节补全 | `report_builder.append_core_stocks_and_plan_if_missing` |
| 主 Prompt | `config/replay_prompt_templates.py`；别名 re-export：`llm_section_generator` |
| 篇首目录 | `replay_catalog` |
| 分离确认 / 要闻映射 | `separation_confirmation`、`news_mapper` |
| 策略权重附加 | `strategy_preference.build_prompt_addon` 等 |

---

## 数据获取与策略核心

- **`DataFetcher`**（`app/services/data_fetcher.py`）：交易日历、指数与个股快照、涨跌停池、板块与资金流、财联社要闻（经 `news_fetcher`）、龙虎榜、概念/行业资金等；**`get_market_summary`** 串联目录、溢价、大面、晋级率、情绪推演、龙头快照、半路选股块，形成注入主 Prompt 的 **`market_data`**。
- **`auction_halfway_strategy`**：主线与 **`top_pool`**；与 `meta.program_completed`、`abort_reason` 等配合。
- **`sentiment_scorer`**、**`technical_indicators`**、**`trend_momentum_strategy`**：情绪打分与技术面/动量（调用链见源码）。
- **`config/data_source_config.py`**：AK 重试、磁盘缓存 TTL、DataFrame 列约定；环境变量覆盖见该文件。
- **`data_source_errors`**：数据源异常类型辅助。
- **并行**：`market_summary_parallel_fetch` 为真时多路基础拉取并行；**`fetch_parallel_max_workers`** 在代码中有上下限钳制。

---

## 大模型客户端

- **`app/services/llm_client.py`**：**`ChatCompletionClient`**；URL 默认 **`llm_default_url`**（配置或 **`DEEPSEEK_API_URL`** 环境变量映射）。
- **超时**：**`get_llm_client`** 使用 **`data_source.llm_connect_timeout`** / **`llm_read_timeout`**（连接/读响应拆分秒数）。环境变量 **`LLM_TIMEOUT_SEC`** 映射到顶层 **`llm_transport_timeout_sec`**（默认值存在于配置中；当前 **`ChatCompletionClient` 未读取该字段**，以源码为准）。
- **传输重试**：**`llm_retry_attempts`**（`LLM_RETRY_ATTEMPTS`）。
- **429**：**`llm_retry_429`**、**`llm_retry_429_wait_sec`**、**`llm_retry_429_wait_max_sec`**；指数退避并尊重 **`Retry-After`**。
- **模型名**：**`llm_model_name`** / **`deepseek_model_name`**，缺省 **`deepseek-chat`**。
- **请求间隔**：**`resilience.llm_min_interval_sec`**（>0 时在 `llm_client` 侧节流）。
- **`get_llm_client(api_key)`**：参数优先，否则配置中 **`deepseek_api_key`** / **`llm_api_key`**。

---

## 复盘增强包与 LLM 智能层（代码现状）

| 组件 | 路径 | 与主流程关系 |
|------|------|----------------|
| **复盘增强四段** | `app/services/replay_llm_enhancements.py`（**`run_replay_enhancement_bundle`** 等） | **`ReplayTask` 日度主路径不调用**。周报等仍可使用其中部分函数（如周度叙事）。配置项 **`enable_replay_llm_*`**、**`replay_llm_enhancements_parallel`** 等保留给实验脚本或未来接回。 |
| **LLM 智能层** | `app/application/llm_intel/`（**`run_replay_intel_layer`**、确定性审计、结构化决策 LLM、**`render_intel_block`**） | **默认配置 `llm_intel.enabled: True`，但 `ReplayTask` 未接入**；可通过测试或自研脚本调用。见 **`tests/test_llm_intel.py`**。 |

---

## 邮件与模板

- **`email_notify`**：**`resolve_email_config`**、**`send_report_email`**、**`send_simple_email`**（环境变量优先于配置文件项）。
- **`email_template`**：Markdown→HTML、KPI 卡、要闻截断、周报内嵌图等。
- 常用配置键：**`report_title_template`**（`{trade_date}`）、**`email_system_name`**、**`email_news_max_items`**、**`email_news_filter_prefix`**、**`email_max_body_chars`** / **`email_max_subject_chars`**、**`weekly_email_attach_charts`**。

---

## 文末温习与绘图脚本

定稿由 **`append_replay_viewpoint_footer`**（`replay_viewpoint_footer.py`）追加：**表格式**五人框架 + **`replay_footer_commentary`** 附录；**`replay_footer_inline_images()`** 恒为无内嵌 CID图。

| 脚本 | 用途 |
|------|------|
| `weekly_theory_review_email.py` | 周六单独发送温习邮件 |
| `send_flowchart_preview_email.py` | 表格式预览邮件 |
| `generate_replay_footer_charts_extended.py` 等 | 本地生成 PNG 示意图（与邮件正文脱钩） |
| `register_weekly_theory_review_task.ps1` | Windows 计划任务注册 |

---

## 持久化与路径

配置 **`paths`**（`config_defaults`）约定相对路径，并由 **`ConfigManager.path(...)`** 解析到绝对路径：

| 逻辑文件 | 默认相对路径 |
|----------|----------------|
| 龙头池档案 | `data/watchlist_records.json` |
| 风格指数 | `data/market_style_indices.json` |
| 五桶权重 | `data/strategy_preference.json` |
| 权重演进日志 | `data/strategy_evolution_log.jsonl` |
| 断点 | `data/replay_status/` |
| 可观测性日志 | `data/logs/`（见 **`observability`**） |

磁盘 API 缓存默认 **`data/api_cache/`**；数据源侧缓存目录见 **`data_source.cache_dir`**（默认 `data_cache`）。

---

## 周度闭环与策略偏好

1. **`scripts/weekly_performance_email.py`**：`--anchor`、`--dry-run`、`--plot`（`weights_trend.png`）。
2. **`weekly_performance.build_weekly_report_markdown_auto`**：收益、归因、市场快照、`weekly_market_snapshot`、严格涨幅前 20 等。
3. **`enable_weekly_ai_insight`**：风格诊断 LLM。
4. **`enable_weekly_llm_trend_narrative`**、**`enable_weekly_weight_llm_explanation`**：周度叙事与权重白话（各依赖对应开关）。
5. **`enable_strategy_feedback_loop`**：**`update_from_recent_returns`**；**`enable_weekly_weight_anomaly_email`** 时权重异常另发邮件。
6. **`enable_weekly_performance_email`**：SMTP 发周报。

策略边界与衰减：**`strategy_preference.py`**、**`config/strategy_preference_config.py`**、环境变量 **`STRATEGY_*`**（见 **`ENV_FLAT_BINDINGS`**）。

---

## 配置说明

**有效配置构造**（`build_effective_config`）顺序：

1. 代码内 **`DEFAULT_CONFIG`**  
2. **`replay_config.json`**（或 **`REPLAY_CONFIG_FILE`**）——与上一步 **深度合并**  
3. **`strategy_profiles[active_strategy_profile]`**——再深度合并（profile 内嵌套键会递归覆盖）  
4. 注入 **`paths.project_root`**  
5. 扁平环境变量（**`ENV_FLAT_BINDINGS`**，见 `unified_config.py`）  
6. 嵌套环境变量：前缀 **`REPLAY__`**，键路径用 **`__`** 分隔，例如 `REPLAY__data_source__timeout=12`

**顶层键（节选，完整以 `config_defaults.py` 为准）**

| 分组 | 键 |
|------|-----|
| LLM | `deepseek_api_key`、`llm_api_key`、`llm_model_name`、`deepseek_model_name`、`llm_api_base`、`llm_default_url`、`llm_transport_timeout_sec`、`llm_retry_*`、`llm_chat_default_*` |
|邮件 | `smtp_*`、`mail_to`、`email_*`、`report_title_template`、`email_system_name` |
| 性能 | `market_summary_parallel_fetch`、`fetch_parallel_max_workers`、`disk_cache_sweep_ttl_sec` |
| 复盘目录/断点 | `enable_replay_*`、`replay_watchlist_*`、`replay_spot_5d_*`、`enable_replay_checkpoint`、`resume_replay_if_available` |
| 周报/策略 | `enable_weekly_*`、`strategy_*`、`min_trades_*`、`multi_week_*` |
| 复盘 LLM 附加（主流程未用增强包时仍可能用于其他脚本） | `enable_replay_llm_enhancements`、`replay_llm_enhancements_*`、`enable_replay_llm_chapter_qc` 等 |
| 文本规则 | `llm_failure_markers`、`llm_failure_payload_scan_chars`、`dragon_report_headings`、`replay_summary_line_max_chars`、`replay_text_templates` |
| 嵌套 | **`data_source`**、`**paths**`、**`resilience`**（熔断、`llm_min_interval_sec`）、**`observability`**（日志目录、级别、JSON/text、告警文件）、**`llm_intel`**（`enabled`、`deterministic_audit`、`structured_decision_llm` 等） |

---

## 环境变量

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` / `LLM_API_KEY` | API Key |
| `DEEPSEEK_API_URL` | 映射到 `llm_default_url` |
| `LLM_API_BASE` | OpenAI 兼容 Base（与默认 URL 组合逻辑见 `get_llm_client`） |
| `LLM_TIMEOUT_SEC` | 写入 `llm_transport_timeout_sec`（见上文「大模型客户端」超时说明） |
| `LLM_RETRY_ATTEMPTS`、`LLM_RETRY_429*` | 重试与 429 退避 |
| `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM`、`MAIL_TO` | SMTP（`resolve_email_config` 优先环境变量） |
| `SMTP_SSL` | `email_notify` 直接读取（`true`/`1` → SMTPS） |
| `REPLAY_CONFIG_FILE` | 自定义配置文件路径 |
| `STRATEGY_*` | 见 `ENV_FLAT_BINDINGS` 与 `strategy_preference_config.py` |
| `AK_*`、`API_*` 等 | 见 `config/data_source_config.py` |
| `VALIDATE_STRICT` | `validate.py` 严格模式 |
| `REPLAY__*` | 嵌套覆盖，见上文 |

---

## 脚本一览

| 脚本 | 说明 |
|------|------|
| `nightly_replay.py` | 日度复盘入口；`--date YYYYMMDD` |
| `weekly_performance_email.py` | 周报；`--anchor`、`--dry-run`、`--plot` |
| `weekly_theory_review_email.py` | 周六温习邮件 |
| `send_flowchart_preview_email.py` | 温习样式预览邮件 |
| `validate.py` | 依赖、权重和、演进日志 JSON 行、环境提示 |
| `health_check.py` |配置与服务导入探测 |
| `backtest_weights.py` | 离线权重网格与绘图（见脚本 docstring） |
| `generate_readme_business_overview_chart.py` | README 业务全景 PNG |
| `generate_replay_footer_charts_extended.py` | 文末示意图 PNG（多风格） |
| `generate_replay_footer_kebi.py`、`generate_replay_footer_tuixue.py` | 单主题脚注图 |
| `generate_replay_viewpoint_footer.py`、`generate_replay_viewpoint_footer_asking.py` | 生成/调试 viewpoint 片段 |
| `register_weekly_theory_review_task.ps1` | Windows 计划任务 |
| `after_rsync.sh` | 部署后 venv + `pip install -r requirements.txt` |
| `run.py` | 提示 Web 已删除，退出码 2 |

---

## 测试、CI、GitHub Actions

### `tests/` 一览

| 文件 | 大致覆盖 |
|------|----------|
| `test_replay_catalog.py` | 篇首目录 |
| `test_replay_summary.py` | 摘要行 |
| `test_replay_llm_failure.py` | LLM 失败载荷识别 |
| `test_replay_enhancements.py` | 增强包拼接、并行顺序 |
| `test_report_builder.py` | 五/七节补全 |
| `test_finance_news.py`、`test_news_fetcher.py`、`test_news_mapper_pool.py` | 要闻与映射 |
| `test_market_kpi.py`、`test_market_phase.py`、`test_market_style_indices.py` | KPI、阶段、风格指数 |
| `test_output_formatter.py`、`test_ladder_utils.py` | 条形图、连板工具 |
| `test_strategy_engine.py`、`test_kebi_strategy.py` | 策略引擎相关 |
| `test_strategy_preference.py` | 五桶与 profile |
| `test_weekly_performance.py`、`test_weekly_attribution.py` | 周报与归因 |
| `test_resilience.py` | 熔断与安全执行 |
| `test_observability.py` | 可观测性 |
| `test_unified_config.py` | 配置合并与环境绑定 |
| `test_llm_intel.py` | LLM 智能层单元逻辑 |

### CI（`.github/workflows/ci.yml`）

`push` / `pull_request` 至 `main` 或 `master`：`pip install -r requirements.txt` → 导入烟测 `ReplayTask` → **`pytest tests/ -q`** → **ruff**（指定文件列表）→ **`validate.py`** → **`health_check.py`**。

### 定时与手动

| Workflow | 说明 |
|----------|------|
| `scheduled-nightly.yml` | UTC `0 10 * * *`（约北京时间 **18:00**）；`workflow_dispatch` 可选输入 `date`；Secrets：`DEEPSEEK_API_KEY`，SMTP 可选 |
| `weekly-report.yml` | UTC `0 2 * * 0`（北京时间 **周日 10:00**）；依赖 `data/watchlist_records.json` |
| `weekly-theory-review.yml` | UTC `0 1 * * 6`（北京时间 **周六 09:00**）；温习邮件 |
| `deploy.yml` | 仅 `workflow_dispatch`；rsync +远端 `after_rsync.sh`；Secrets：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`、`DEPLOY_PATH` |

---

## 部署

- 在 **`DEPLOY_PATH`** 放置 **`replay_config.json`** 或仅用环境变量。  
- 定时：GitHub **Nightly**、本机 cron 或 Windows 任务计划程序。  
- **GitHub 托管 Runner 不持久化 `data/`**：周报依赖的 **`watchlist_records.json`** 需在自托管或同步策略下积累。

---

## 辅助文档

| 文档 | 内容 |
|------|------|
| `ARCHITECTURE.md` | 模块边界、数据契约、排错、术语 |
| `docs/six_layer_architecture.md` | 六层架构目标与代码映射 |
| `docs/smtp_env.md` | 纯环境变量 SMTP 说明 |

**常见情况**：无龙头池 / `abort_reason`；周报无邮件；**429**；**`VALIDATE_STRICT`**；摘要或章节异常——详见 `ARCHITECTURE.md`。

---

*行为以主分支源码与 `pytest` 为准。新增能力时请同步更新 **`app/infrastructure/config_defaults.py`**、本 README、**`ARCHITECTURE.md`**，以及涉及分层时 **`docs/six_layer_architecture.md`**。*
