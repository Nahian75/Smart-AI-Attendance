@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart AI Attendance System
echo  ================================================
echo.

:: ── 1. Docker check ──────────────────────────────────────────────
docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker Desktop is not running.
    echo  Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)

:: ── 2. Create .env from .env.dev if missing ──────────────────────
if not exist ".env" (
    if not exist ".env.dev" (
        echo  [ERROR] .env.dev not found. Cannot create .env.
        pause
        exit /b 1
    )
    echo  [SETUP] Creating .env from .env.dev ...
    copy ".env.dev" ".env" >nul
    echo  [SETUP] .env created with development defaults.
    echo.
)

:: ── 3. Detect first run (no DB volume yet) ───────────────────────
set FIRST_RUN=0
docker volume inspect smart-attendance_postgres_data >nul 2>&1
if errorlevel 1 set FIRST_RUN=1

:: ── 4. Build and start services (including edge node) ───────────
echo  [START] Building and starting all services (backend, frontend, edge node)...
echo  [INFO]  First build may take 5-10 minutes (downloading AI models ^& packages).
echo.

docker compose -f docker-compose.dev.yml up -d --build
if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to start services. See output above.
    pause
    exit /b 1
)

:: ── 5. Wait for backend to become healthy ────────────────────────
echo.
echo  [WAIT]  Waiting for backend to be ready...
set TRIES=0
:healthloop
set "HEALTH="
for /f "tokens=*" %%s in ('curl -s http://localhost/health 2^>nul') do set "HEALTH=%%s"
echo !HEALTH! | findstr /c:"ok" >nul 2>&1
if not errorlevel 1 goto healthy
set /a TRIES+=1
if %TRIES% geq 60 (
    echo  [WARN]  Backend did not respond in time. Continuing anyway.
    goto seed
)
timeout /t 2 >nul
goto healthloop

:healthy
echo  [OK]    Backend is ready.

:seed
:: ── 6. Seed database on first run ────────────────────────────────
if "%FIRST_RUN%"=="1" (
    echo.
    echo  [SETUP] First run detected. Seeding the database...
    docker compose -f docker-compose.dev.yml exec -T backend python seed.py
    if errorlevel 1 (
        echo  [WARN]  Seed may have failed. Check with: docker compose logs backend
    ) else (
        echo  [OK]    Database seeded.
    )
)

:: ── 7. Wait for nginx to be ready ────────────────────────────────
echo.
echo  [WAIT]  Waiting for dashboard to be ready...
set TRIES=0
:nginxloop
curl -s -o nul -w "%%{http_code}" http://localhost 2>nul | findstr /c:"200" /c:"304" /c:"301" /c:"302" /c:"307" >nul 2>&1
if not errorlevel 1 goto done
set /a TRIES+=1
if %TRIES% geq 30 goto done
timeout /t 2 >nul
goto nginxloop

:done
:: ── 8. Print summary and open browser ────────────────────────────
echo.
echo  ================================================
echo   Smart AI Attendance is running
echo  ================================================
echo   Dashboard  :  http://localhost
echo   API docs   :  http://localhost/api/docs
echo   Login      :  admin@demo.com / admin123
echo.
echo   Camera streams auto-start once edge node loads AI models (~60s).
echo   Add cameras via Dashboard ^> Cameras ^> + Add camera
echo.
echo   To stop    :  stop.bat   (or double-click stop.bat)
echo  ================================================
echo.

start "" "http://localhost"

pause
endlocal
