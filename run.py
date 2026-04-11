# -*- coding: utf-8 -*-
"""
已移除 Flask Web 服务。请在项目根执行：

  夜间复盘：  python scripts/nightly_replay.py
  周报：      python scripts/weekly_performance_email.py
  周六温习：  python scripts/weekly_theory_review_email.py（五人理论单独邮件）
  健康检查：  python scripts/health_check.py
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "Web 前端已删除。请使用 scripts/nightly_replay.py 等脚本（见本文件注释）。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
