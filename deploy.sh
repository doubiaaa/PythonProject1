#!/bin/bash

# 部署脚本

# 服务器信息
SERVER_IP="124.223.139.147"
SERVER_USER="ubuntu"
SERVER_PATH="/home/ubuntu/projects/rich"

# 构建前端项目
echo "构建前端项目..."
cd frontend
npm run build
cd ..

# 复制文件到服务器
echo "复制文件到服务器..."
rsync -av --exclude="node_modules" --exclude=".git" --exclude="__pycache__" --exclude="*.pyc" . $SERVER_USER@$SERVER_IP:$SERVER_PATH

# 执行服务器上的部署后脚本
echo "执行部署后脚本..."
ssh $SERVER_USER@$SERVER_IP "bash $SERVER_PATH/after_rsync.sh"

# 配置定时任务
echo "配置定时任务..."
ssh $SERVER_USER@$SERVER_IP "(crontab -l 2>/dev/null | grep -v 'run_daily.sh'; echo '10 18 * * 1-5 cd /home/ubuntu/projects/rich && /usr/bin/env bash /home/ubuntu/projects/rich/run_daily.sh') | crontab -"

echo "部署完成！"
