@echo off
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance System - Stopping
echo  ================================================
echo.

docker compose -f docker-compose.dev.yml down

echo.
echo  Stopped. All data is preserved.
echo  Run start.bat to start again.
echo.
pause
