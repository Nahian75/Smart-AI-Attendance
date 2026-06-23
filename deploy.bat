@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance - Production Deploy
echo  ================================================
echo.

:: Usage: deploy.bat [domain/IP] [--no-edge] [--update] [--gpu nvidia^|amd^|intel^|cpu]

:: ── Parse args ────────────────────────────────────────────────────
set UPDATE_ONLY=0
set NO_EDGE=0
set FORCE_GPU=
set SERVER_ARG=

:parse
if "%~1"=="" goto :done_parse
if /i "%~1"=="--update"   set UPDATE_ONLY=1 & shift & goto :parse
if /i "%~1"=="--no-edge"  set NO_EDGE=1     & shift & goto :parse
if /i "%~1"=="--gpu"      set FORCE_GPU=%~2 & shift & shift & goto :parse
if "%SERVER_ARG%"==""     set SERVER_ARG=%~1
shift
goto :parse
:done_parse

:: ── 1. Check Docker ──────────────────────────────────────────────
echo  [CHECK] Checking Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker Desktop is not running.
    pause & exit /b 1
)
echo  [OK]    Docker is running.

:: ── 2. Detect GPU ─────────────────────────────────────────────────
echo.
echo  [GPU]   Detecting GPU hardware...
set GPU_TYPE=cpu
set GPU_OVERRIDE=

if "%NO_EDGE%"=="1" (
    set GPU_TYPE=none
    goto :gpu_done
)

if not "%FORCE_GPU%"=="" (
    set GPU_TYPE=%FORCE_GPU%
    echo  [GPU]   Forced: %FORCE_GPU%
    goto :gpu_done
)

:: NVIDIA check
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    echo  [GPU]   NVIDIA GPU detected.
    docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi >nul 2>&1
    if not errorlevel 1 (
        set GPU_TYPE=nvidia
        set GPU_OVERRIDE=-f docker-compose.prod.gpu.yml
        echo  [GPU]   NVIDIA CUDA acceleration enabled.
        goto :gpu_done
    )
    echo  [WARN]  nvidia-container-toolkit not configured. Using CPU.
    goto :gpu_done
)

:: AMD/Intel on Windows: use DirectML (works for both via DirectX 12)
for /f "tokens=*" %%g in ('powershell -NoProfile -Command "(Get-WmiObject Win32_VideoController).Name" 2^>nul') do (
    echo %%g | findstr /i "AMD Radeon RX\|RX 6\|RX 7" >nul && (
        set GPU_TYPE=amd
        echo  [GPU]   AMD GPU detected - using DirectML on Windows.
        goto :gpu_done
    )
    echo %%g | findstr /i "Intel Arc\|Intel Iris\|Intel UHD\|Intel HD" >nul && (
        set GPU_TYPE=intel
        echo  [GPU]   Intel GPU detected - using DirectML on Windows.
        goto :gpu_done
    )
)

:gpu_done
if "%GPU_TYPE%"=="cpu"  echo  [GPU]   No accelerated GPU found - CPU mode.
if "%GPU_TYPE%"=="none" echo  [GPU]   Edge node disabled (--no-edge).

:: ── 3. Server address ─────────────────────────────────────────────
echo.
echo  [ADDR]  Determining server address...

if "%SERVER_ARG%"=="" (
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing -TimeoutSec 5).Content" 2^>nul') do set SERVER_ARG=%%i
)
if "%SERVER_ARG%"=="" (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
        for /f "tokens=1" %%b in ("%%a") do ( set SERVER_ARG=%%b & goto :got_ip )
    )
)
if "%SERVER_ARG%"=="" set SERVER_ARG=localhost
:got_ip
echo  [ADDR]  http://%SERVER_ARG%

:: ── 4. Generate .env ──────────────────────────────────────────────
echo.
if exist ".env" (
    echo  [ENV]   .env already exists - keeping secrets.
    if "%UPDATE_ONLY%"=="1" (
        powershell -NoProfile -Command "(Get-Content .env) -replace '^NEXT_PUBLIC_API_URL=.*','NEXT_PUBLIC_API_URL=http://%SERVER_ARG%' | Set-Content .env"
        powershell -NoProfile -Command "(Get-Content .env) -replace '^NEXT_PUBLIC_WS_URL=.*','NEXT_PUBLIC_WS_URL=ws://%SERVER_ARG%' | Set-Content .env"
    )
    goto :build
)

echo  [ENV]   Generating secure secrets...

for /f "tokens=*" %%k in ('powershell -NoProfile -Command "[BitConverter]::ToString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set SK=%%k
for /f "tokens=*" %%k in ('powershell -NoProfile -Command "[BitConverter]::ToString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('-','').ToLower()"') do set ET=%%k
for /f "tokens=*" %%k in ('powershell -NoProfile -Command "[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).Replace('/','x').Replace('+','y').Replace('=','').Substring(0,24)"') do set PGP=%%k
for /f "tokens=*" %%k in ('powershell -NoProfile -Command "[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(18)).Replace('/','x').Replace('+','y').Replace('=','').Substring(0,20)"') do set RDP=%%k

echo  [ENV]   Generating Fernet key via Docker...
for /f "tokens=*" %%k in ('docker run --rm python:3.12-slim sh -c "pip install cryptography -q 2>/dev/null && python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""') do set FKEY=%%k

(
echo # ── Database ────────────────────────────────────────────────
echo POSTGRES_USER=attendance
echo POSTGRES_PASSWORD=!PGP!
echo POSTGRES_DB=attendance_db
echo.
echo # ── Redis ───────────────────────────────────────────────────
echo REDIS_PASSWORD=!RDP!
echo.
echo # ── Backend ─────────────────────────────────────────────────
echo SECRET_KEY=!SK!
echo ENVIRONMENT=production
echo FACE_ENCRYPTION_KEY=!FKEY!
echo CONFIDENCE_THRESHOLD=0.82
echo COOLDOWN_MINUTES=5
echo EVENT_RETENTION_DAYS=90
echo.
echo # ── Edge node ───────────────────────────────────────────────
echo TENANT_ID=demo
echo EDGE_TOKEN=!ET!
echo.
echo # ── Frontend ────────────────────────────────────────────────
echo NEXT_PUBLIC_API_URL=http://%SERVER_ARG%
echo NEXT_PUBLIC_WS_URL=ws://%SERVER_ARG%
echo NEXT_PUBLIC_EDGE_URL=
) > .env

echo  [OK]    .env created.
echo.
echo  !! SAVE THESE CREDENTIALS - shown only once !!
echo  ─────────────────────────────────────────────────────
echo  POSTGRES_PASSWORD : !PGP!
echo  REDIS_PASSWORD    : !RDP!
echo  SECRET_KEY        : !SK!
echo  EDGE_TOKEN        : !ET!
echo  ─────────────────────────────────────────────────────
echo.

:: ── 5. Build ──────────────────────────────────────────────────────
:build
echo  [BUILD] Building production images (10-20 min first run)...
docker compose -f docker-compose.prod.yml %GPU_OVERRIDE% build
if errorlevel 1 ( echo  [ERROR] Build failed. & pause & exit /b 1 )
echo  [OK]    Images built.

:: ── 6. Start ──────────────────────────────────────────────────────
echo  [START] Starting services...
docker compose -f docker-compose.prod.yml %GPU_OVERRIDE% up -d
if errorlevel 1 ( echo  [ERROR] Start failed. & pause & exit /b 1 )
echo  [OK]    Services started.

:: ── 7. Wait for backend ───────────────────────────────────────────
echo  [WAIT]  Waiting for backend...
set TRIES=0
:waitloop
set "H="
for /f "tokens=*" %%r in ('curl -s http://localhost:8000/health 2^>nul') do set "H=%%r"
echo !H! | findstr /c:"ok" >nul 2>&1 && goto :be_ready
set /a TRIES+=1
if %TRIES% geq 90 ( echo  [WARN] Backend slow to start. & goto :seed )
timeout /t 3 >nul & goto :waitloop
:be_ready
echo  [OK]    Backend ready.

:: ── 8. Seed ───────────────────────────────────────────────────────
:seed
echo  [SEED]  Seeding database...
docker compose -f docker-compose.prod.yml exec -T backend python seed.py
echo  [OK]    Done.

:: ── 9. Summary ────────────────────────────────────────────────────
echo.
echo  ================================================
echo   Deployment complete
echo  ================================================
echo   Dashboard   :  http://%SERVER_ARG%
echo   Login       :  admin@demo.com / admin123
echo.
echo   Change the admin password immediately
echo   after first login (sidebar - Change Password).
echo.
echo   GPU         :  %GPU_TYPE%
echo   Logs        :  docker compose -f docker-compose.prod.yml logs -f
echo   Stop        :  docker compose -f docker-compose.prod.yml down
echo   Update      :  deploy.bat --update
echo  ================================================
echo.
start "" "http://%SERVER_ARG%"
pause
endlocal
