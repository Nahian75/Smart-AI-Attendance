@echo off
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance - Edge Node - Stopping
echo  ================================================
echo.

docker compose -f docker-compose.edge.yml --env-file .env.edge down

echo.
echo  Stopped.
echo  Run start_edge.bat to start again.
echo.
pause
