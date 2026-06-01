@echo off
chcp 65001 >nul
title 黔江区多维度精准考核评价系统 v1.3

echo ==========================================
echo   黔江区多维度精准考核评价系统 v1.3
echo ==========================================
echo.
echo 正在启动系统，请稍候...
echo.

REM 检查是否已在运行
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    echo 系统已在运行中 (端口 5000)，无需重复启动。
    echo.
    start "" http://localhost:5000
    goto :end
)

REM 从源代码启动（使用最新代码，不依赖打包EXE）
set PYTHON_PATH=C:\Users\qcd11\AppData\Local\Programs\Python\Python312\python.exe
set BACKEND_DIR=%~dp0..\backend

if not exist "%PYTHON_PATH%" (
    echo Python 未找到: %PYTHON_PATH%
    echo 请确认 Python 路径是否正确。
    pause
    goto :end
)

cd /d "%BACKEND_DIR%"
echo 后端目录: %CD%
echo.
start "" "%PYTHON_PATH%" app.py

echo 系统已启动，即将打开浏览器...
echo 如未自动打开，请手动访问: http://localhost:5000
echo.
echo ==========================================
echo 提示：关闭浏览器不会停止系统。
echo 要停止系统，请关闭命令行窗口或结束进程。
echo ==========================================

REM 等待后端启动后打开浏览器
timeout /t 3 /nobreak >nul
start "" http://localhost:5000

:end
echo.
pause
