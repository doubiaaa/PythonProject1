# -*- coding: utf-8 -*-
"""
校验配置与 data 下 JSON 的格式与一致性；用于本地或 CI。

用法：
  python scripts/validate.py
环境：
  VALIDATE_STRICT=1  时，缺失可选文件也记为失败（默认对缺失仅 [SKIP]）
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

STRICT = (os.environ.get("VALIDATE_STRICT") or "").strip() in ("1", "true", "yes")
FAILURES = 0


def _fail(msg: str) -> None:
    global FAILURES
    FAILURES += 1
    print(f"[FAIL] {msg}")


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _skip(msg: str) -> None:
    print(f"[SKIP] {msg}")


def _path(rel: str) -> str:
    return os.path.join(_ROOT, rel.replace("/", os.sep))


def check_strategy_preference() -> None:
    p = _path("data/strategy_preference.json")
    if not os.path.isfile(p):
        if STRICT:
            _fail("data/strategy_preference.json 不存在")
        else:
            _skip("data/strategy_preference.json 不存在")
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _fail(f"strategy_preference.json 非合法 JSON：{e}")
        return
    sw = data.get("strategy_weights") or {}
    buckets = ("打板", "低吸", "趋势", "龙头", "其他")
    s = sum(float(sw.get(k, 0) or 0) for k in buckets)
    if abs(s - 1.0) > 0.02:
        _fail(f"strategy_weights 之和 {s:.4f} 不在 0.98~1.02 附近")
    else:
        _ok("strategy_preference.json 权重和≈1")


def check_simulated_account(cm: dict) -> None:
    if not cm.get("enable_simulated_account"):
        _skip("未开启模拟账户，跳过 simulated_account.json 检查")
        return
    p = _path(cm.get("simulated_account_path") or "data/simulated_account.json")
    if not os.path.isfile(p):
        _fail("已开启模拟账户但 simulated_account.json 不存在")
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _fail(f"simulated_account.json：{e}")
        return
    for k in ("initial_capital", "cash", "holdings", "transactions", "daily_series", "total_value"):
        if k not in data:
            _fail(f"simulated_account.json 缺少字段 {k}")
            return
    if not isinstance(data.get("holdings"), list):
        _fail("simulated_account.json holdings 须为数组")
        return
    _ok("simulated_account.json 字段完整")


def check_simulated_config(cm: dict) -> None:
    if not cm.get("enable_simulated_account"):
        _skip("未开启模拟账户，跳过 simulated_config 检查")
        return
    p = _path(cm.get("simulated_config_path") or "data/simulated_config.json")
    if not os.path.isfile(p):
        _fail("已开启模拟账户但 simulated_config.json 不存在")
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _fail(f"simulated_config.json：{e}")
        return
    if float(data.get("stop_loss", 0)) >= 0:
        _fail("simulated_config stop_loss 应为负数")
        return
    if float(data.get("stop_profit", 0)) <= 0:
        _fail("simulated_config stop_profit 应为正数")
        return
    if int(data.get("max_positions", 0)) <= 0:
        _fail("simulated_config max_positions 应 > 0")
        return
    _ok("simulated_config.json 数值合理")


def check_evolution_log() -> None:
    p = _path("data/strategy_evolution_log.jsonl")
    if not os.path.isfile(p):
        _skip("strategy_evolution_log.jsonl 不存在")
        return
    n = 0
    bad = 0
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
    if bad:
        _fail(f"strategy_evolution_log.jsonl 有 {bad} 行非法 JSON（共 {n} 行）")
    else:
        _ok(f"strategy_evolution_log.jsonl 共 {n} 行 JSON 合法")


def check_env_keys() -> None:
    if not (os.environ.get("ZHIPU_API_KEY") or "").strip():
        _warn("未设置 ZHIPU_API_KEY（调用智谱时需要）")
    else:
        _ok("已设置 ZHIPU_API_KEY")


def check_imports() -> None:
    mods = [
        "flask",
        "akshare",
        "pandas",
        "requests",
        "markdown",
        "pytest",
        "tenacity",
        "config.data_source_config",
    ]
    for m in mods:
        try:
            __import__(m)
            _ok(f"import {m}")
        except Exception as e:
            _fail(f"import {m}：{e}")


def main() -> int:
    global FAILURES
    FAILURES = 0
    print("=== validate.py ===\n")
    check_imports()
    check_strategy_preference()
    from app.utils.config import ConfigManager

    cm = ConfigManager().config
    check_simulated_config(cm)
    check_simulated_account(cm)
    check_evolution_log()
    check_env_keys()
    print(f"\n失败项数：{FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
