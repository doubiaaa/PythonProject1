#!/usr/bin/env bash
# 部署到 Linux 服务器后执行：创建/使用 venv 并安装依赖（由 GitHub Actions deploy 或手动 ssh 调用）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

# 安装前端依赖并构建前端项目
if [[ -d frontend ]]; then
  cd frontend
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build
  cd ..
fi

echo "[after_rsync] OK: $(which python)"
echo "[after_rsync] Frontend built successfully"

