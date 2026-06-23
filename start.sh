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

# ── 3. Detect first run ───────────────────────────────────────────
FIRST_RUN=0
if ! docker volume inspect smart-attendance_postgres_data > /dev/null 2>&1; then
    FIRST_RUN=1
fi

# ── 4. Build and start services ──────────────────────────────────
echo " [START] Building and starting services..."
echo " [INFO]  First build may take 3-5 minutes."
echo ""

docker compose -f docker-compose.dev.yml up -d --build

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

# ── 6. Seed on first run ──────────────────────────────────────────
if [ "$FIRST_RUN" -eq 1 ]; then
    echo ""
    echo " [SETUP] First run detected. Seeding the database..."
    docker compose -f docker-compose.dev.yml exec -T backend python seed.py && \
        echo " [OK]    Database seeded." || \
        echo " [WARN]  Seed may have failed. Check: docker compose logs backend"
fi

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
