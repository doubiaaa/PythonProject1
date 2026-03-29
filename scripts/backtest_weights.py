# -*- coding: utf-8 -*-
"""
离线回测权重策略（占位）：读取 strategy_evolution_log.jsonl，未来可网格搜索
平滑系数 / 上限 / 保底等参数。

用法：
  python scripts/backtest_weights.py
  python scripts/backtest_weights.py --log data/strategy_evolution_log.jsonl

当前仅校验日志可读并打印周数；完整「假设当时用参数 X」的模拟待接入。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    p = argparse.ArgumentParser(description="权重策略离线回测（占位）")
    p.add_argument(
        "--log",
        default=os.path.join(_ROOT, "data", "strategy_evolution_log.jsonl"),
        help="evolution 日志路径",
    )
    args = p.parse_args()
    path = args.log
    if not os.path.isfile(path):
        print(f"找不到日志：{path}", file=sys.stderr)
        return 1
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                n += 1
            except json.JSONDecodeError:
                continue
    print(f"已读取 {n} 条 evolution 记录：{path}")
    print("（完整回测：按周重放 suggested→merged 与参数网格，待实现。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
