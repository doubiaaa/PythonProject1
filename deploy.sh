#!/bin/bash

# 部署脚本：在服务器上部署 A 股收盘智能复盘系统

set -e

echo "=== 开始部署 A 股收盘智能复盘系统 ==="

# 1. 检查 Docker 和 Docker Compose 是否已安装
if ! command -v docker &> /dev/null; then
    echo "错误：Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "错误：Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

echo "✓ Docker 和 Docker Compose 已安装"

# 2. 克隆代码仓库
echo "=== 克隆代码仓库 ==="
if [ -d ".git" ]; then
    echo "目录已存在，执行 git pull 更新代码"
    git pull
else
    echo "目录不存在，执行 git clone 克隆代码"
    git clone https://gitee.com/kkllll/python-project1.git .
fi

# 3. 创建环境变量文件
echo "=== 创建环境变量文件 ==="
cp .env.example .env

# 4. 构建 Docker 镜像
echo "=== 构建 Docker 镜像 ==="
docker-compose build

# 5. 启动服务
echo "=== 启动服务 ==="
docker-compose up -d

# 6. 检查服务状态
echo "=== 检查服务状态 ==="
docker-compose ps

# 7. 配置定时任务
echo "=== 配置定时任务 ==="
(crontab -l 2>/dev/null | grep -v 'run_daily.sh'; echo '10 18 * * 1-5 cd /opt/python-project1 && docker exec python-project1-backend /usr/bin/env bash /app/run_daily.sh') | crontab -

# 8. 输出部署信息
echo "=== 部署完成 ==="
echo "后端 API 地址: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "定时任务已配置，每个交易日 18:10 自动执行复盘。"
