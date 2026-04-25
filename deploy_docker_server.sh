#!/bin/bash

# 服务器端部署脚本 - Docker 版本

set -euo pipefail

# 切换到项目目录
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 检查 Docker 是否已安装
if ! command -v docker &> /dev/null; then
    echo "Docker 未安装，正在安装..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
    echo "Docker 安装完成，请重新登录以生效"
    exit 1
fi

# 检查 docker-compose 是否已安装
if ! command -v docker-compose &> /dev/null; then
    echo "docker-compose 未安装，正在安装..."
    sudo apt-get update
    sudo apt-get install -y docker-compose
    echo "docker-compose 安装完成"
fi

# 构建 Docker 镜像
echo "构建 Docker 镜像..."
docker-compose build

# 运行 Docker 容器
echo "运行 Docker 容器..."
docker-compose up -d

# 查看容器状态
echo "查看容器状态..."
docker ps -a

# 配置定时任务
echo "配置定时任务..."
(crontab -l 2>/dev/null | grep -v 'run_daily.sh'; echo '10 18 * * 1-5 cd /home/ubuntu/projects/rich && docker exec $(docker ps -q --filter name=rich_app_1) /usr/bin/env bash /app/run_daily.sh') | crontab -

echo "部署完成！"
