# 第一阶段：构建前端
FROM node:18-alpine AS frontend

WORKDIR /app/frontend

# 复制前端依赖文件
COPY frontend/package.json frontend/package-lock.json ./

# 安装前端依赖
RUN npm install

# 复制前端源代码
COPY frontend/ ./

# 构建前端
RUN npm run build

# 第二阶段：构建后端
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# 复制后端依赖文件
COPY requirements.txt ./

# 安装后端依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端源代码
COPY . .

# 从前端构建阶段复制构建好的前端文件
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "server.py"]
