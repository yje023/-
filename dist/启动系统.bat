@echo off
chcp 65001 >nul
title 黔江区多维度精准考核评价系统 v1.1

echo ==========================================
echo   黔江区多维度精准考核评价系统 v1.1
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

REM 启动系统
start "" "%~dp0考核评价系统.exe"

echo 系统已启动，浏览器将自动打开。
echo 如未自动打开，请手动访问: http://localhost:5000
echo.
echo ==========================================
echo 提示：关闭浏览器不会停止系统。
echo 要停止系统，请关闭命令行窗口或结束进程。
echo ==========================================

:end
echo.
pause
