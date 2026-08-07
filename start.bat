@echo off
chcp 65001 >nul
title 金鹰集团数据管理中心

echo ============================================
echo   金鹰集团数据管理中心 - 一键启动
echo ============================================
echo.

cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 安装后端依赖
echo [1/3] 安装后端依赖...
pip install -q -r backend\requirements.txt 2>nul

REM 检查前端是否已构建
if not exist "frontend\dist\index.html" (
    echo [2/3] 构建前端...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 npm，请先安装 Node.js 18+
        pause
        exit /b 1
    fi
    cd frontend
    call npm install
    call npm run build
    cd ..
) else (
    echo [2/3] 前端已构建，跳过
)

REM 启动后端
echo [3/3] 启动服务...
echo.
echo   访问地址: http://localhost:5000
echo   访问地址: http://localhost:5000
echo   管理员密码: 见 data\admin_config.json（首次部署为初始默认密码，登录后请修改）
echo   项目密码: 由管理员在系统内配置
echo   按 Ctrl+C 停止
echo.

python backend\app.py
pause
