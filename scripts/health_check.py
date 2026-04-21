# -*- coding: utf-8 -*-
"""
健康检查：依赖导入、可选配置、数据源轻量探测（不保证行情接口实时可用）。
用法：python scripts/health_check.py
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    ok = True
    print("=== health_check ===\n")

    try:
        import config.data_source_config  # noqa: F401

        print("[OK] config.data_source_config")
    except Exception as e:
        print(f"[FAIL] config: {e}")
        ok = False

    try:
        import pandas as pd

        _ = pd.__version__
        print("[OK] akshare / pandas")
    except Exception as e:
        print(f"[FAIL] akshare/pandas: {e}")
        ok = False

    try:
        from app.utils.config import ConfigManager

        cm = ConfigManager()
        print(f"[OK] ConfigManager keys: {len(cm.config)}")
    except Exception as e:
        print(f"[FAIL] ConfigManager: {e}")
        ok = False

    try:
        from app.services.replay_llm_enhancements import (  # noqa: F401
            collect_program_facts_snapshot,
        )

        print("[OK] app.services.replay_llm_enhancements")
    except Exception as e:
        print(f"[FAIL] replay_llm_enhancements: {e}")
        ok = False

    llm_key = os.environ.get("DEEPSEEK_API_KEY") or ""
    if llm_key.strip():
        print("[OK] DEEPSEEK_API_KEY 已设置（未实际调用 API）")
    else:
        print("[WARN] 未设置 DEEPSEEK_API_KEY，复盘 AI 不可用")

    print("\n完成。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
