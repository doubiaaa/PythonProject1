# -*- coding: utf-8 -*-
"""
本地验证统一邮件 HTML：Markdown 表格、代码块、长文本、内嵌图片（CID）。

用法（需已配置 replay_config 或环境变量中的 SMTP）：
  python scripts/test_email_ui.py
  python scripts/test_email_ui.py --to user@example.com

不会修改业务数据；可选在项目根生成临时测试 PNG 用于 CID 校验。
"""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _make_sample_png(path: str) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(5, 2.2))
        ax.plot([1, 2, 3, 4, 5], [1.0, 1.02, 0.99, 1.03, 1.01], color="#1e3a5f", lw=2)
        ax.set_title("测试净值曲线（脚本生成）", fontsize=10)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return True
    except Exception:
        return False


SAMPLE_MD = """
## 邮件 UI 自检

这是一段**粗体**与 `行内代码`，下方为表格与围栏代码块。

| 列 A | 列 B | 数值 |
|------|------|------|
| 示例 | 斑马纹 | 12.34 |
| 第二行 | 测试 | -5.6 |

```python
def hello():
    return "markdown + codehilite（若已安装 pygments）"
```

> 引用块：以上内容仅供样式验证，不构成投资建议。

---

### 长文本占位

""" + ("\n".join(f"- 第 {i} 行列表项，用于检查移动端换行与层级。" for i in range(1, 16)))


def main() -> int:
    parser = argparse.ArgumentParser(description="发送测试邮件（统一 HTML 模板）")
    parser.add_argument(
        "--to",
        metavar="EMAIL",
        help="覆盖收件人（否则使用 replay_config / 环境变量 MAIL_TO）",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="不生成测试 PNG，跳过 CID 内嵌图",
    )
    args = parser.parse_args()

    from app.services.email_notify import (
        has_email_config,
        resolve_email_config,
        send_report_email,
    )
    from app.utils.config import ConfigManager
    from app.utils.email_template import embed_image_cid, markdown_to_html

    cm = ConfigManager()
    ecfg = resolve_email_config(cm)
    if args.to and ecfg:
        ecfg["mail_to"] = [args.to.strip()]
    elif args.to and not ecfg:
        print("SMTP 未配置，无法仅通过 --to 发信；请先配置 smtp_host。", file=sys.stderr)
        return 1

    if not ecfg or not has_email_config(ecfg):
        print(
            "未配置 SMTP（smtp_host + mail_to）。请在 replay_config.json 或环境变量中设置。",
            file=sys.stderr,
        )
        return 1

    html_frag = markdown_to_html(SAMPLE_MD)
    inline: list[tuple[str, str]] | None = None

    if not args.no_image:
        png = os.path.join(_ROOT, "data", "_test_email_ui_chart.png")
        if _make_sample_png(png) and os.path.isfile(png):
            html_frag = embed_image_cid(html_frag, png, "testchart")
            inline = [("testchart", png)]

    subj = "【复盘】[测试] 邮件 HTML 模板自检"
    ok, msg = send_report_email(
        ecfg,
        subj,
        SAMPLE_MD,
        html_fragment=html_frag,
        inline_images=inline,
        extra_vars={
            "header_date": "本地测试 · 邮件 UI",
            "title": subj,
        },
    )
    if ok:
        print("已发送：", subj)
        return 0
    print("发送失败：", msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
