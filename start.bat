@echo off
title Assessment System v1.1

set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python312\python.exe

echo ==========================================
echo   Assessment System v1.1
echo ==========================================
echo.

echo [0/2] Stopping old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
echo Old processes cleaned.

echo [1/2] Starting backend...
start "Backend" "%PYTHON_PATH%" "%~dp0backend\app.py"

echo [2/2] Starting frontend dev server...
cd /d "%~dp0frontend"
start "Frontend" npx vite --port 3000

echo.
echo ==========================================
echo   Backend:  http://localhost:5000
echo   Frontend: http://localhost:3000
echo ==========================================
echo.
echo Opening browser in 3 seconds...
timeout /t 3 >nul
start "" http://localhost:5000
echo.
echo Close this window, services keep running.
pause >nul
