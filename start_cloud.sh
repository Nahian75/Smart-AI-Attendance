#!/usr/bin/env bash
# ================================================================
#  Cloud bootstrap + update script — runs on the GCP VM.
#  Idempotent: safe to run on first install AND on every subsequent
#  deploy (this is exactly what .github/workflows/deploy-cloud.yml
#  invokes over SSH on every push to the `cloud` branch).
#
#  Runs everything except the edge node (postgres, redis, backend,
#  celery, frontend, nginx, mediamtx). The edge node runs separately
#  on-prem via start_edge.bat and talks to this stack remotely.
# ================================================================
set -euo pipefail

REPO_URL="https://github.com/Nahian75/Smart-AI-Attendance.git"
REPO_BRANCH="cloud"
REPO_DIR="$HOME/Smart-AI-Attendance"
# Compose auto-loads ./.env — same convention as docker-compose.prod.yml / deploy.sh.
# In CI, .github/workflows/deploy-cloud.yml writes .env from repo secrets before
# calling this script. For a manual VM run, this script falls back to the
# .env.cloud.example template if .env doesn't exist yet.
COMPOSE="docker compose -f docker-compose.cloud.yml"

echo ""
echo " ================================================"
echo "  Smart AI Attendance — Cloud Deploy"
echo " ================================================"
echo ""

# ── 1. Install Docker if missing ──────────────────────────────────
if ! command -v docker > /dev/null 2>&1; then
    echo " [SETUP] Docker not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo " [OK]    Docker installed. You may need to log out/in for group changes to apply."
fi

# ── 2. Clone repo if missing, else pull latest ─────────────────────
if [ ! -d "$REPO_DIR/.git" ]; then
    echo " [SETUP] Cloning $REPO_URL (branch=$REPO_BRANCH) ..."
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
echo " [SYNC]  Pulling latest from $REPO_BRANCH ..."
git fetch origin "$REPO_BRANCH"
git checkout "$REPO_BRANCH"
git reset --hard "origin/$REPO_BRANCH"

# ── 3. .env must exist ───────────────────────────────────────────────
# Normally written by .github/workflows/deploy-cloud.yml from repo secrets
# right before this script runs. This fallback only matters if you're
# bootstrapping the VM manually, outside of CI.
if [ ! -f ".env" ]; then
    if [ ! -f ".env.cloud.example" ]; then
        echo " [ERROR] .env.cloud.example not found. Cannot create .env."
        exit 1
    fi
    echo " [SETUP] Creating .env from template — EDIT IT WITH REAL SECRETS."
    cp .env.cloud.example .env
    echo " [WARN]  .env uses placeholder secrets. Edit $REPO_DIR/.env"
    echo "         then re-run this script."
fi

# ── 4. Build and start services ────────────────────────────────────
echo " [START] Building and starting cloud services..."
$COMPOSE up -d --build

# ── 5. Wait for backend ─────────────────────────────────────────────
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

# ── 6. Seed demo credentials (idempotent) ──────────────────────────
echo ""
echo " [SEED]  Seeding demo credentials (safe to run multiple times)..."
$COMPOSE exec -T backend python seed.py && \
    echo " [OK]    Database seeded." || \
    echo " [WARN]  Seed may have failed. Check: $COMPOSE logs backend"

# ── 7. Summary ───────────────────────────────────────────────────────
echo ""
echo " ================================================"
echo "  Smart AI Attendance (cloud) is running"
echo " ================================================"
echo "  Dashboard  :  http://$(curl -s -4 ifconfig.me 2>/dev/null || echo '<VM_IP>')"
echo "  Login      :  admin@demo.com / admin123"
echo "  Edge video :  SRT ingest on :8890 (see edge/mediamtx.edge.yml)"
echo ""
echo "  GCP firewall must allow inbound: 80/tcp, 6379/tcp (redis, restrict"
echo "  source to your edge node's IP), 8890/udp (SRT), 8888/tcp (HLS)."
echo " ================================================"
echo ""
