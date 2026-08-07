#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  金鹰集团数据管理中心 - 一键启动"
echo "============================================"

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

# 安装后端依赖
echo "[1/3] 安装后端依赖..."
pip3 install -q -r backend/requirements.txt

# 检查前端是否已构建
if [ ! -f "frontend/dist/index.html" ]; then
    echo "[2/3] 构建前端..."
    if ! command -v npm &>/dev/null; then
        echo "[错误] 未找到 npm，请先安装 Node.js 18+"
        exit 1
    fi
    cd frontend
    npm install
    npm run build
    cd ..
else
    echo "[2/3] 前端已构建，跳过"
fi

# 启动后端
echo "[3/3] 启动服务..."
echo ""
echo "  访问地址: http://localhost:5000"
echo "  访问地址: http://localhost:5000"
echo "  管理员密码: 见 data/admin_config.json（首次部署为初始默认密码，登录后请修改）"
echo "  项目密码: 由管理员在系统内配置"
echo ""

python3 backend/app.py
