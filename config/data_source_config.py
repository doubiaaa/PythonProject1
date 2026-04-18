# -*- coding: utf-8 -*-
"""
数据源：超时、重试、缓存 TTL、关键字段（供 data_fetcher 与校验使用）。
可被环境变量覆盖：AK_RETRY_ATTEMPTS、AK_HTTP_TIMEOUT、API_CACHE_TTL_SEC 等。

悟道 OpenClaw（可选，主数据源；失败回退 akshare）：
  环境变量 LB_API_KEY、LB_API_BASE；
  或 ``data_source.use_lb_openclaw`` / ``lb_api_key`` / ``lb_api_base``（见 replay_config）。
  启用后优先：涨停/炸板/跌停池、涨跌家数 market-overview、北向 capital-flow、hottest-sectors、
  concepts/ranking；扩展复盘块见 ``lb_replay_assist_markdown``。
  仍主要用 akshare：全市场交易日历（无单次全量 LB 接口）、东财 spot 回退、K 线/分笔/要闻/龙虎榜等。
"""
from __future__ import annotations

import os

# ---- 网络 / 重试（tenacity）----
AK_RETRY_ATTEMPTS: int = max(1, int(os.environ.get("AK_RETRY_ATTEMPTS", "3")))
AK_RETRY_WAIT_MIN_SEC: float = float(os.environ.get("AK_RETRY_WAIT_MIN_SEC", "2"))
AK_RETRY_WAIT_MAX_SEC: float = float(os.environ.get("AK_RETRY_WAIT_MAX_SEC", "32"))

# 与旧 DataFetcher.fetch_with_retry 兼容：retry_times 表示「额外重试次数」
AK_FETCH_EXTRA_RETRIES: int = max(0, int(os.environ.get("AK_FETCH_EXTRA_RETRIES", "1")))

# ---- 磁盘缓存（按自然日键，秒）----
API_DISK_CACHE_TTL_SEC: int = int(os.environ.get("API_CACHE_TTL_SEC", "86400"))

# ---- 各数据集必需列（用于校验）----
REQUIRED_ZT_POOL_COLUMNS: tuple[str, ...] = ("代码", "名称", "连板数")
REQUIRED_DT_POOL_COLUMNS: tuple[str, ...] = ("代码", "名称")
REQUIRED_ZB_POOL_COLUMNS: tuple[str, ...] = ("代码", "名称")
REQUIRED_TRADE_CAL_COLUMNS: tuple[str, ...] = ("trade_date",)
