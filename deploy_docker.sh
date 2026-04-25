#!/bin/bash

# 部署脚本 - Docker 版本

# 服务器信息
SERVER_IP="124.223.139.147"
SERVER_USER="ubuntu"
SERVER_PATH="/home/ubuntu/projects/rich"

# 复制文件到服务器
echo "复制文件到服务器..."
rsync -av --exclude="node_modules" --exclude=".git" --exclude="__pycache__" --exclude="*.pyc" . $SERVER_USER@$SERVER_IP:$SERVER_PATH

# 执行服务器上的部署脚本
echo "执行部署脚本..."
ssh $SERVER_USER@$SERVER_IP "bash $SERVER_PATH/deploy_docker_server.sh"

echo "部署完成！"
