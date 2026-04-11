# 企业级六层架构（目标模型）

本文描述复盘系统**演进目标**：将当前「数据 → 策略 → LLM → 推送」耦合实现，拆为**可独立替换、可测试**的分层结构。  
**现状**：大量逻辑仍在 `app/services/*`、`app/utils/*` 中；**不追求一次性搬迁**，按阶段把新代码放进对应层、旧代码逐步收口。

---

## 1. 一句话

**加数据源、加策略、加输出格式、换 LLM、换推送方式时，编排与领域规则保持稳定；仅替换 Adapter / Output / 具体 Provider 实现。**

---

## 2. 六层定义

| 层级 | 英文名 | 职责 | 依赖方向 |
|------|--------|------|----------|
| **接口层** | Adapter | 所有**外部系统**统一收口：行情、日历、新闻、LLM HTTP、SMTP、文件系统等 | 只依赖 **Infra** 与（必要时）**Domain** 的 DTO；不依赖 Service/Orchestration |
| **领域层** | Domain | **纯业务模型与不变量**：交易日、龙头候选、市场阶段、复盘报告结构等；**无** HTTP/SMTP/pandas 细节 | **零**依赖本仓库基础设施以外的框架 |
| **服务层** | Application（应用服务） | **用例级业务规则**：可单测、**副作用通过接口注入**（端口），不在此层直接 `requests.post` / 写文件 | 依赖 Domain；通过 **端口（Protocol）** 调用 Adapter，而非具体类 |
| **编排层** | Orchestration | **流程控制**：复盘流水线步骤、重试、断点、与周报/定时任务的衔接 | 组合 Application 服务；**不写**具体数据拉取与邮件拼接细节 |
| **输出层** | Output | **呈现与投递**：Markdown/HTML 模板、邮件 MIME、CID 附图、日志型输出 | 依赖 Domain DTO；可调用 Infra 做序列化 |
| **基础设施层** | Infrastructure | **横切能力**：配置、日志、缓存、监控、时钟；**技术型 Adapter 的默认实现**可放此处或 Adapter 子包 | 最底层；不依赖上层 |

### 2.1 依赖规则（示意）

```text
Orchestration → Application → Domain
     ↓              ↓
   Output      Adapter / Infra（经端口）
```

- **禁止**：Domain 引用 `requests`、`akshare`、`smtplib`、`ConfigManager` 单例。  
- **允许**：Application 依赖抽象端口（`Protocol`），运行期由 Infra/Adapter 注入实现。

---

## 3. 与当前代码的映射（迁移锚点）

| 目标层 | 当前主要落点（约） | 说明 |
|--------|-------------------|------|
| Adapter | `data_fetcher`（部分）、`news_fetcher`、`llm_client`、SMTP 调用侧 | 逐步拆为 `adapters/market/`、`adapters/llm/` 等 |
| Domain | （尚薄） | 抽取：`MarketSnapshot`、`DragonPool`、`ReplayPhase` 等值对象/实体 |
| Application | `auction_halfway_strategy`、`strategy_preference` 核心规则、`report_builder` 规则部分 | 与 IO 解耦后迁入 `application/` |
| Orchestration | `replay_task.py`、`nightly_replay.py` 主流程 | 变薄：只保留步骤与条件分支 |
| Output | `email_template`、`email_notify`、`replay_viewpoint_footer` | 统一为「报告渲染 + 投递」 |
| Infra | `config.py`、`logger.py`、`disk_cache`、`replay_checkpoint` | 保持；抽象接口供 Adapter 使用 |

**注意**：现有包名 **`app/services`** 为历史包袱，语义上混合了 Application + Adapter + Output；迁移期新代码**优先**写入 `application/`、`adapters/`、`output/`，旧模块**渐进搬迁**，不一次性重命名全仓库。

### 3.1 已落地锚点（与阶段 B 对齐，持续演进）

| 层 | 路径 | 作用 |
|----|------|------|
| Domain | `app/domain/ports.py`、`app/domain/models.py` | `Protocol`（LLM / 邮件 / 市场摘要 / 配置）与 DTO |
| Application | `app/application/replay_text_rules.py` | 摘要行、章节校验、失败载荷识别等纯规则 |
| Adapter | `app/adapters/llm_deepseek_adapter.py`、`app/adapters/email_smtp_adapter.py`、`app/adapters/market_summary_adapter.py` | 默认实现委托给既有 `llm_client` / `email_notify` / `DataFetcher` |
| Orchestration | `app/orchestration/replay_pipeline.py` | 流水线阶段名常量（与 `ReplayTask.run` 对齐） |
| Output | `app/output/replay_email_subject.py` | 邮件主题拼装（无 SMTP） |
| Infra | `app/infrastructure/config_adapter.py` | `ConfigManager` → `AppConfigPort` |
| 编排入口（过渡） | `app/services/replay_task.py` | `ReplayTask` 支持注入 `llm_port`、`email_port`，邮件/主题委托 Output 与端口 |

---

## 4. 分阶段迁移（建议）

1. **阶段 A（当前可做）**：在 **Domain** 补最小 DTO；**Orchestration** 把 `ReplayTask.run` 的步骤用私有函数划界并写清注释。  
2. **阶段 B（进行中）**：为「拉行情」「调 LLM」「发邮件」定义 **Protocol**，默认实现留在 Adapter/Infra；`ReplayTask` 已可注入 LLM/邮件端口。  
3. **阶段 C**：`DataFetcher.get_market_summary` 拆为多个 Adapter + 单一「组装用例」。  
4. **阶段 D**：删除 `services` 包内重复抽象，统一入口脚本只依赖 Orchestration。

---

## 5. 包目录（占位）

仓库已增加与目标层对应的 **空包骨架**（仅 `__init__.py` 说明），便于新代码从第一天起分层落位：

| 路径 | 对应层 |
|------|--------|
| `app/adapters/` | 接口层（Adapter） |
| `app/domain/` | 领域层 |
| `app/application/` | 服务层（应用服务，避免与历史 `services` 混淆） |
| `app/orchestration/` | 编排层 |
| `app/output/` | 输出层 |
| `app/infrastructure/` | 基础设施层（与 `app/utils` 并存，新横切能力优先放此） |

---

## 6. 与 README / ARCHITECTURE 的关系

- **`ARCHITECTURE.md`**：维护**当前**实现导航；在「路线图」中指向本文。  
- **本文**：**目标**架构与迁移原则；随阶段 B/C 推进更新映射表。

*若实现与本文冲突，以源码与测试为准；本文优先保证「分层意图」一致。*
