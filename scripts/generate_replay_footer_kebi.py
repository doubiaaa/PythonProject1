# -*- coding: utf-8 -*-
"""生成 92科比 扩展框架图 PNG。"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.utils.replay_footer_chart_draw import save_kebi_framework_png


def main() -> None:
    out = os.path.join(_ROOT, "assets", "replay_footer_kebi.png")
    save_kebi_framework_png(out)
    print(f"已写入: {out}")


if __name__ == "__main__":
    main()
