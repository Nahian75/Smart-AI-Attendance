@echo off
:: Relaunch inside a "cmd /k" window so it stays open no matter what happens
:: below — even a hard crash before reaching a pause won't close it.
if "%~1" neq "_run" (
    start "Smart AI Attendance - Edge Node" cmd /k ""%~f0" _run"
    exit /b
)

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance - Edge Node (on-prem)
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

:: Create .env.edge from template if missing
if not exist ".env.edge" (
    if not exist ".env.edge.example" (
        echo  [ERROR] .env.edge.example not found. Cannot create .env.edge.
        pause
        exit /b 1
    )
    echo  [SETUP] Creating .env.edge from template...
    copy /y ".env.edge.example" ".env.edge" >nul
    echo  [WARN]  .env.edge has placeholder values. Edit it with your real
    echo          CLOUD_HOST / REDIS_PASSWORD / EDGE_TOKEN / MTX_SRTPUBLISHPASS
    echo          then re-run this script.
    pause
    exit /b 1
)

:: Create edge\mediamtx.edge.yml (real camera credentials, gitignored) from
:: the committed placeholder template if missing
if not exist "edge\mediamtx.edge.yml" (
    if not exist "edge\mediamtx.edge.yml.example" (
        echo  [ERROR] edge\mediamtx.edge.yml.example not found.
        pause
        exit /b 1
    )
    echo  [SETUP] Creating edge\mediamtx.edge.yml from template...
    copy /y "edge\mediamtx.edge.yml.example" "edge\mediamtx.edge.yml" >nul
    echo  [WARN]  edge\mediamtx.edge.yml has placeholder camera RTSP URLs.
    echo          Edit it with your real cameras, then re-run this script.
    pause
    exit /b 1
)

:: Read CLOUD_HOST for the summary banner at the end
for /f "usebackq tokens=1,2 delims==" %%A in (".env.edge") do (
    if "%%A"=="CLOUD_HOST" set "CLOUD_HOST=%%B"
)

echo  [SETUP] Generating edge\mediamtx.edge.generated.yml from template...
powershell -NoProfile -ExecutionPolicy Bypass -File "edge\generate_mediamtx_config.ps1"
if errorlevel 1 (
    echo  [ERROR] Failed to generate mediamtx config. Check .env.edge values.
    pause
    exit /b 1
)

:: Check if edge image already exists — skip build if it does
docker image inspect smart-attendance-edge-edge_node >nul 2>&1
if errorlevel 1 (
    echo  [BUILD] First run - building edge image (this can take a while^)...
    docker compose -f docker-compose.edge.yml --env-file .env.edge up -d --build
) else (
    echo  [START] Starting existing edge containers (no rebuild^)...
    docker compose -f docker-compose.edge.yml --env-file .env.edge up -d
)

if errorlevel 1 (
    echo  [ERROR] Failed to start. Check Docker logs.
    pause
    exit /b 1
)

:: mediamtx only reads its config at startup — restart so a freshly
:: regenerated mediamtx.edge.generated.yml (new/edited cameras) takes effect.
docker compose -f docker-compose.edge.yml --env-file .env.edge restart mediamtx >nul 2>&1

echo.
echo  [OK]    Edge node is running.
echo.
echo  ================================================
echo   Local edge stream :  http://localhost:8001
echo   Cloud dashboard    :  http://%CLOUD_HOST%
echo   Stop               :  stop_edge.bat
echo  ================================================
echo.
echo  NOTE: edit edge\mediamtx.edge.yml to add your real camera RTSP
echo  URLs (one path block per camera), then run start_edge.bat again
echo  to regenerate the config and restart mediamtx.
echo.
pause
