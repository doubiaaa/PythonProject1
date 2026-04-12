# -*- coding: utf-8 -*-
"""生成 README「业务全景」流程图 PNG（与 Mermaid 一致，无 DeepSeek 增强 / llm_intel 节点）。"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.utils.replay_footer_chart_draw import save_readme_business_overview_png


def main() -> None:
    out = os.path.join(_ROOT, "assets", "readme_business_overview.png")
    save_readme_business_overview_png(out)
    print(f"已写入: {out}")


if __name__ == "__main__":
    main()
