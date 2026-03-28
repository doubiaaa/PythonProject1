#!/usr/bin/env bash
# 生产环境启动（无 Docker）：先在本机执行 scripts/after_rsync.sh 装好依赖
# 用法：nohup bash scripts/run_gunicorn.sh > /tmp/replay.log 2>&1 &
# 建议配合 systemd 或 supervisor 守护，前面可再接 Nginx 反代。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
exec gunicorn -w 2 -b 0.0.0.0:5000 --timeout 300 --access-logfile - "app:app"
