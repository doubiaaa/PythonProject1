#!/bin/bash

# 启动后端 API 服务

# 加载环境变量
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | xargs)
fi

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
