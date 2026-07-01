#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo " ================================================"
echo "  Smart AI Attendance System"
echo " ================================================"
echo ""

# ── 1. Docker check ──────────────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo " [ERROR] Docker is not running."
    echo " Please start Docker Desktop (Mac) or the Docker daemon (Linux) and try again."
    exit 1
fi

# ── 2. Create .env from .env.dev if missing ──────────────────────
if [ ! -f ".env" ]; then
    if [ ! -f ".env.dev" ]; then
        echo " [ERROR] .env.dev not found. Cannot create .env."
        exit 1
    fi
    echo " [SETUP] Creating .env from .env.dev ..."
    cp .env.dev .env
    echo " [SETUP] .env created with development defaults."
    echo ""
fi

# ── 3. Stop any previously running stack (prevents port conflicts) ─
echo " [CLEAN] Stopping any existing containers..."
docker compose -f docker-compose.dev.yml down > /dev/null 2>&1 || true

# ── 4. Build and start services ──────────────────────────────────
if ! docker image inspect smart-attendance-backend > /dev/null 2>&1; then
    echo " [BUILD] First run - building images (this takes 10-40 min, only once)..."
    docker compose -f docker-compose.dev.yml up -d --build
else
    echo " [START] Starting existing containers (no rebuild)..."
    docker compose -f docker-compose.dev.yml up -d
fi

# ── 5. Wait for backend ───────────────────────────────────────────
echo ""
echo " [WAIT]  Waiting for backend to be ready..."
TRIES=0
until curl -s http://localhost/health | grep -q '"ok"' 2>/dev/null; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 60 ]; then
        echo " [WARN]  Backend did not respond in time. Continuing anyway."
        break
    fi
    sleep 2
done
echo " [OK]    Backend is ready."

# ── 6. Seed database (safe to run multiple times) ─────────────────
echo ""
echo " [SEED]  Initialising database (safe to run multiple times)..."
docker compose -f docker-compose.dev.yml exec -T backend python seed.py && \
    echo " [OK]    Database seeded." || \
    echo " [WARN]  Seed may have failed. Check: docker compose logs backend"

# ── 7. Wait for dashboard ─────────────────────────────────────────
echo ""
echo " [WAIT]  Waiting for dashboard to be ready..."
TRIES=0
until curl -s -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null | grep -qE "^(200|301|302|304)$"; do
    TRIES=$((TRIES + 1))
    [ "$TRIES" -ge 30 ] && break
    sleep 2
done

# ── 8. Print summary and open browser ────────────────────────────
echo ""
echo " ================================================"
echo "  Smart AI Attendance is running"
echo " ================================================"
echo "  Dashboard  :  http://localhost"
echo "  API docs   :  http://localhost:8000/api/docs"
echo "             :  (only in ENVIRONMENT=development)"
echo "  Login      :  admin@demo.com / admin123"
echo ""
echo "  To stop    :  ./stop.sh"
echo "  With edge  :  docker compose -f docker-compose.dev.yml --profile edge up -d"
echo " ================================================"
echo ""

# Open browser
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://localhost" &
elif command -v open > /dev/null 2>&1; then
    open "http://localhost"
fi
