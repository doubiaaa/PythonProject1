# 部署脚本

# 服务器信息
$SERVER_IP = "124.223.139.147"
$SERVER_USER = "ubuntu"
$SERVER_PATH = "/home/ubuntu/projects/rich"

# 复制文件到服务器
Write-Host "复制文件到服务器..."
robocopy . "\\$SERVER_IP\$($SERVER_PATH -replace '/', '\')" /E /XD node_modules .git __pycache__ /XF "*.pyc"

# 执行服务器上的部署后脚本
Write-Host "执行部署后脚本..."
ssh $SERVER_USER@$SERVER_IP "bash $SERVER_PATH/after_rsync.sh"

# 配置定时任务
Write-Host "配置定时任务..."
ssh $SERVER_USER@$SERVER_IP "(crontab -l 2>/dev/null | grep -v 'run_daily.sh'; echo '10 18 * * 1-5 cd /home/ubuntu/projects/rich && /usr/bin/env bash /home/ubuntu/projects/rich/run_daily.sh') | crontab -"

Write-Host "部署完成！"
