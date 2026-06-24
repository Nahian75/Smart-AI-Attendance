@echo off
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance System - Starting
echo  ================================================
echo.

:: Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker Desktop is not running.
    echo  Please start Docker Desktop and try again.
    pause
    exit /b 1
)

:: Check if images already exist — skip build if they do
docker image inspect smart-ai-attendance-main-backend >nul 2>&1
if errorlevel 1 (
    echo  [BUILD] First run - building images (this takes 10-20 min, only once^)...
    docker compose up -d --build
) else (
    echo  [START] Starting existing containers (no rebuild^)...
    docker compose up -d
)

if errorlevel 1 (
    echo  [ERROR] Failed to start. Check Docker logs.
    pause
    exit /b 1
)

echo.
echo  [WAIT]  Waiting for backend...
:waitloop
curl -s http://localhost:8000/health 2>nul | findstr /c:"ok" >nul 2>&1
if not errorlevel 1 goto ready
timeout /t 2 >nul
goto waitloop

:ready
echo  [OK]    All services are running.
echo.
echo  ================================================
echo   Dashboard  :  http://localhost:8080
echo   Login      :  admin@demo.com / admin123
echo   Stop       :  stop.bat
echo  ================================================
echo.
start "" "http://localhost:8080"
pause
