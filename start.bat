@echo off
title Assessment System v1.1

set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python312\python.exe

echo ==========================================
echo   Assessment System v1.1
echo ==========================================
echo.

echo [1/2] Starting backend...
start "Backend" "%PYTHON_PATH%" "%~dp0backend\app.py"

echo [2/2] Starting frontend...
cd /d "%~dp0frontend"
start "Frontend" npx vite --port 3000

echo.
echo ==========================================
echo   Backend:  http://localhost:5000
echo   Frontend: http://localhost:3000
echo   Open browser: http://localhost:3000
echo ==========================================
echo.
echo You can close this window, services will keep running.
pause >nul
