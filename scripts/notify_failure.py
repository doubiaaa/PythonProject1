"""GitHub Actions 失败时可选：通过 Server酱 推送一次（不配置则静默退出）。"""
import os
import sys

import requests


def main() -> None:
    key = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not key:
        return
    url = f"https://sctapi.ftqq.com/{key}.send"
    try:
        r = requests.post(
            url,
            data={
                "title": "❌ Nightly 复盘失败",
                "desp": "请打开 GitHub Actions 查看日志。",
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"notify_failure: HTTP {r.status_code}", file=sys.stderr)
    except OSError as e:
        print(f"notify_failure: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)
