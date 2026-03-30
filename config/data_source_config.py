# -*- coding: utf-8 -*-
"""
数据源：超时、重试、缓存 TTL、关键字段（供 data_fetcher 与校验使用）。
可被环境变量覆盖：AK_RETRY_ATTEMPTS、AK_HTTP_TIMEOUT、API_CACHE_TTL_SEC 等。
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
