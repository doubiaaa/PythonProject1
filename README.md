# 次日竞价半路 · 复盘系统（脚本 / CI）

程序侧拉取行情与规则数据，**DeepSeek** 生成复盘长文与增强块；**无 Web 前端**，适合本机或 GitHub Actions 定时运行。

## 入口

| 脚本 | 说明 |
|------|------|
| `scripts/nightly_replay.py` | 夜间自动复盘（非交易日跳过） |
| `scripts/weekly_performance_email.py` | 周末龙头池周报与策略权重更新 |
| `scripts/simulated_morning_buy.py` | 模拟盘次日开盘撮合（需本地持久化 `data/`） |
| `scripts/validate.py` | 依赖与数据校验 |
| `scripts/health_check.py` | 导入与环境变量粗检 |

配置：项目根 `replay_config.json`（与 `app/utils/config.py` 默认合并）。密钥优先环境变量 `DEEPSEEK_API_KEY`。

## 依赖

```bash
pip install -r requirements.txt
```

## 架构说明

见 `ARCHITECTURE.md`。
